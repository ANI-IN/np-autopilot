#!/usr/bin/env python3
"""D3 — project the built graph into Postgres.

REPLACE-ALL IN ONE TRANSACTION, per DECISIONS §B.3. The graph is derived: the
pipeline is its source of truth and nothing else writes it, so there is no merge
to do and no conflict to resolve. A half-applied graph is not merely incomplete
— it is wrong in a way that looks fine, with edges pointing at nodes that were
not inserted yet.

DECISIONS §B.2 argued for a content-addressed set-diff so `updated_at` stays
meaningful. That is right for a graph Postgres OWNS. This phase projects a
read-only mirror of a file the pipeline owns, nothing consumes `updated_at` yet,
and replace-all is the version whose failure mode is "the old graph is still
there".

SWITCH TO THE SET-DIFF WHEN EITHER OF THESE BECOMES TRUE. They are conditions,
not a vague "later", so nobody has to reconstruct why replace-all was acceptable:

  1. GRAPH MUTATIONS BECOME AUDITED. The §E.4 audit trail answers "who changed
     what, when". Replace-all rewrites every row on every build, so every row
     looks modified every time and the audit log stops distinguishing a real
     change from a rebuild. The log is then worse than absent, because it looks
     like a record.

  2. THE PROJECTION RUNS ON A SCHEDULE rather than on demand. A nightly rebuild
     under replace-all truncates and reloads 68,379 rows whether or not the
     corpus moved — a window where the graph is empty, on a timer, unattended.
     On demand, a human is watching and the window is seconds.

Neither is true today: nothing reads `updated_at`, and this runs when someone
runs it. `test_replace_all_switch_conditions` in tests/test_db_migration_
verification.py asserts both are still false, so the day one becomes true the
suite says so rather than the behaviour quietly degrading.

SCOPE: this phase projects the PUBLIC half only. `graph-sensitive.json` — 277
hiring rejections and 1,625 in-pipeline candidates — is not projected at all,
and `--scope full` refuses until the recruiting RLS path exists.

Usage:
    python3 pipeline/project_graph.py            # public half
    python3 pipeline/project_graph.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import db, graphio, taxonomy                        # noqa: E402
from pipeline.lib.paths import KNOWLEDGE_DIR                          # noqa: E402

#: Coordinates that make an assertion id. Mirrors ASSERTION_COORDS in
#: 03_resolve.py — the collision check in DECISIONS §A.4 is what fixed this set.
COORDS = ("origin", "file", "sheet", "row", "column", "page", "within_cell", "ordinal")

#: Node keys that become columns rather than props.
NODE_COLUMNS = {"id", "type", "label", "label_raw", "sensitive", "sources"}
#: Edge keys that become columns rather than props.
EDGE_COLUMNS = {"rel", "source", "target"}


def assertion_id(node_id: str, prop: str | None, src: dict) -> str:
    """Content-addressed, deterministic, and stable across rebuilds.

    The canonical form is explicit rather than json.dumps of the dict, so adding
    an unrelated key to a source entry cannot silently change every id.
    """
    parts = [node_id, prop or ""] + [str(src.get(k, "")) for k in COORDS]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def rows_for(graph: dict):
    """(nodes, edges, sources) as tuples ready for COPY."""
    nodes, edges, sources = [], [], []
    for n in graph["nodes"]:
        props = {k: v for k, v in n.items() if k not in NODE_COLUMNS}
        nodes.append((n["id"], n["type"], n["label"], n.get("label_raw"),
                      bool(n["sensitive"]), json.dumps(props, sort_keys=True)))
        seen: dict[str, int] = {}
        for src in n.get("sources", []):
            # `establishes` names the properties a HAND entry justifies. One row
            # per property, so provenance is property-grained where properties
            # genuinely come from different places (AUDIT §A.5). A corpus entry
            # establishes the node itself and gets prop NULL.
            props_established = src.get("establishes") or [None]
            for prop_ordinal, prop in enumerate(props_established):
                aid = assertion_id(n["id"], prop, src)
                if aid in seen:          # cannot happen; asserted, not assumed
                    raise SystemExit(f"assertion id collision on {n['id']} {prop}")
                seen[aid] = 1
                # `column` carries two shapes: an integer index from the grid
                # and owner extractors, a header STRING from scan_column. Both
                # are real provenance and they are not the same fact, so they
                # land in different columns rather than being flattened to text.
                col = src.get("column")
                sources.append((
                    aid, n["id"], prop, src.get("origin"), src.get("file"),
                    src.get("sheet"), src.get("row"),
                    col if isinstance(col, int) else None,
                    col if isinstance(col, str) else None,
                    src.get("page"), src.get("within_cell"),
                    src.get("ordinal", 0), src.get("evidence"),
                    src.get("entered_at"), prop_ordinal,
                ))
    # PROVENANCE IS NOT AN EDGE HERE. DECISIONS §A.3: moving it to its own table
    # is what makes the dangerous join impossible to write by accident, and
    # `edges` becomes 4,021 rows instead of 36,677.
    #
    # Projecting sourced_from into BOTH tables — which the first version of this
    # loader did — stored provenance twice and handed every traversal back the
    # degree-18,134 file hubs it was supposed to be unable to reach. Caught by a
    # test asserting the property the design claims.
    #
    # Nothing is lost: each sourced_from edge corresponds one-to-one with a
    # node_sources row that names a file, so the graph shape is DERIVED on read
    # rather than stored. That makes the verifier's round trip a proof of
    # equivalence instead of a copy.
    prov = taxonomy.edge_for_role("provenance")
    for e in graph["edges"]:
        if e["rel"] == prov:
            continue
        props = {k: v for k, v in e.items() if k not in EDGE_COLUMNS}
        edges.append((e["rel"], e["source"], e["target"],
                      json.dumps(props, sort_keys=True)))
    return nodes, edges, sources


#: What the sensitive half needs before it may be projected. Checked, not
#: assumed — see the refusal in main().
RECRUITING_POLICY = "nodes_recruiting_select"
RECRUITING_FUNC = "np_can_see_sensitive"


def _missing_recruiting_path() -> list[str]:
    """Which pieces of the recruiting RLS path are absent. Empty means ready."""
    missing = []
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select 1 from pg_policies where schemaname='public' "
                    "and tablename='nodes' and policyname=%s", (RECRUITING_POLICY,))
        if cur.fetchone() is None:
            missing.append(f"policy {RECRUITING_POLICY} on nodes")
        cur.execute("select 1 from pg_proc where proname=%s", (RECRUITING_FUNC,))
        if cur.fetchone() is None:
            missing.append(f"function {RECRUITING_FUNC}()")
        # A sensitive row is only protected if the tables that REACH it are too.
        # edges and node_sources gate on node visibility, so a missing policy
        # there would expose sensitive rows by association rather than directly.
        for table in ("edges", "node_sources"):
            cur.execute("select 1 from pg_policies where schemaname='public' "
                        "and tablename=%s", (table,))
            if cur.fetchone() is None:
                missing.append(f"any policy on {table}")
    return missing


def _refuse_unclassified_properties(graph: dict) -> None:
    """EVERY projected property must be classified. Absence stops the build.

    The default used to be "goes into the public half", which is how three
    widening requests moved the same boundary without any one of them looking
    wrong. There is no default now.
    """
    reserved = {"id", "type", "label", "label_raw", "sensitive", "sources",
                "source", "target", "rel"}
    scopes = taxonomy.property_scopes()
    unclassified: dict[str, int] = {}
    misplaced: dict[str, int] = {}

    for node in graph.get("nodes", []):
        for key in node:
            if key in reserved:
                continue
            scope = scopes.get(key)
            if scope is None:
                unclassified[key] = unclassified.get(key, 0) + 1
            elif scope == "sensitive" and not node.get("sensitive"):
                misplaced[key] = misplaced.get(key, 0) + 1
    for edge in graph.get("edges", []):
        for key in edge:
            if key not in reserved and scopes.get(key) is None:
                unclassified[key] = unclassified.get(key, 0) + 1

    if unclassified:
        listed = "\n".join(f"    {k}  ({c:,} rows)"
                            for k, c in sorted(unclassified.items()))
        sys.exit(
            "REFUSING TO PROJECT: unclassified properties.\n"
            f"{listed}\n\n"
            "Every property must declare a scope in config/taxonomy.yaml ->\n"
            "property_scopes before it can be projected. This is deliberate: the\n"
            "old default put a new field in the PUBLIC half — a tracked file —\n"
            "unless somebody remembered otherwise, so widening defaulted toward\n"
            "exposure. Classify each as `public` or `sensitive` and re-run.")

    if misplaced:
        listed = "\n".join(f"    {k}  ({c:,} public rows)"
                            for k, c in sorted(misplaced.items()))
        sys.exit(
            "REFUSING TO PROJECT: sensitive properties on public rows.\n"
            f"{listed}\n\n"
            "These are classified `sensitive` in config/taxonomy.yaml but appear\n"
            "on rows without sensitive: true. Either the row is misclassified or\n"
            "the extractor is attaching the field too widely.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="public", choices=["public", "full"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.scope == "full":
        # WAS A HARDCODED REFUSAL SAYING THE RECRUITING RLS PATH "DOES NOT EXIST
        # YET". It does — `nodes_recruiting_select` and `np_can_see_sensitive()`
        # both landed, and the refusal was never revisited. A guard that asserts
        # a conclusion instead of checking one is wrong in whichever direction
        # the world moves: it blocked correct work here, and had the policy been
        # DROPPED it would have waved the projection through.
        #
        # So it now checks. It refuses again, automatically, if either piece
        # disappears — and a table with no policy denies everyone, which looks
        # exactly like it worked.
        missing = _missing_recruiting_path()
        if missing:
            sys.exit(
                "--scope full is refused: the recruiting RLS path is incomplete.\n"
                f"  missing: {', '.join(missing)}\n"
                "The sensitive half is 277 hiring rejections and 1,625 in-pipeline "
                "candidates about named external people. Without the policy they "
                "would be projected into a table that denies everyone — which "
                "looks identical to having worked.")
        # The path is READY and that is not the same as APPROVED. Projecting
        # 1,902 rows about named external people is a recorded decision, not a
        # flag someone passes — docs/INGEST-SCOPE-REVERSAL.md carries the
        # approval block and it is deliberately blank.
        sys.exit(
            "--scope full is refused: the RLS path is ready, the DECISION is not.\n"
            "  recruiting policy : present\n"
            "  np_can_see_sensitive() : present\n"
            "\nProjecting the sensitive half is 277 hiring rejections and 1,625\n"
            "in-pipeline candidates about named external people. That is a\n"
            "recorded decision under R6 — see docs/INGEST-SCOPE-REVERSAL.md,\n"
            "whose approval block is blank. Fill it in, then remove this refusal\n"
            "in the same commit so the record and the capability arrive together.\n"
            "\nAND DECIDE THIS TOO, because approving the scope decides it\n"
            "silently: since migration 0015 (2026-09-18) `member` is granted\n"
            "AUTOMATICALLY to every verified @interviewkickstart.com Workspace\n"
            "identity on first sign-in. When this refusal was written, the\n"
            "readership was whoever an administrator had chosen — two people.\n"
            "It is now every employee, by default.\n"
            "That is safe only while the sensitive half is not projected, which\n"
            "is the thing you are about to change. Should the default, automatic\n"
            "role still read what --scope full projects?\n"
            "  docs/AUTH.md -> 'Say it plainly'\n"
            "  docs/INGEST-SCOPE-REVERSAL.md -> 'A dependency that did not exist'")

    # PUBLIC HALF ONLY. include_sensitive=False is the whole scope decision, in
    # one argument, rather than a filter applied later that someone can forget.
    graph = graphio.load_graph(include_sensitive=(args.scope == "full"))
    _refuse_unclassified_properties(graph)
    # SCOPE-AWARE, and it used to be a bare `assert`. An AssertionError names
    # nothing: it said "False is not False" where it meant "you asked for the
    # sensitive half on a code path that only handles the public one".
    if args.scope == "public":
        if graph["meta"]["sensitive_loaded"] is not False:
            sys.exit("the loader returned the sensitive half for --scope public "
                     "— refusing before anything is written")
        leaked = [n["id"] for n in graph["nodes"] if n.get("sensitive")]
        if leaked:
            sys.exit(f"{len(leaked)} sensitive nodes in the public half — refusing")

    nodes, edges, sources = rows_for(graph)
    content = graphio.content_hash(graph)

    print("=" * 74)
    print("PROJECT GRAPH -> POSTGRES")
    print("=" * 74)
    print(f"  scope        : {args.scope} (sensitive half NOT projected)")
    print(f"  nodes        : {len(nodes):,}")
    print(f"  edges        : {len(edges):,}  (traversable only — "
          f"provenance lives in node_sources)")
    print(f"  node_sources : {len(sources):,}")
    print(f"  content hash : {content[:16]}")
    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    manifest = json.loads((KNOWLEDGE_DIR / "files.json").read_text(encoding="utf-8"))
    # DRIVE_URL IS DERIVED HERE, not stored by pass 1, so the shape of the link
    # is one decision in one place. `open?id=` rather than `/file/d/<id>/view`
    # because the corpus holds several Drive types and only the generic form
    # resolves all of them.
    def _drive_url(fid):
        return f"https://drive.google.com/open?id={fid}" if fid else None

    files = [(r["path"], r.get("sha256"), r.get("bytes"), r.get("sheet_count"),
              bool(r.get("parsed")), r.get("drive_file_id"),
              _drive_url(r.get("drive_file_id")))
             for r in manifest["files"] + manifest["failures"]]
    node_types = [(n["name"], (n.get("description") or "").strip()[:400])
                  for n in taxonomy.node_types()]
    edge_rels = [(e["name"], e["from"], e["to"], (e.get("source") or "").strip()[:400])
                 for e in taxonomy.edge_types()]

    started = time.time()
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            # ONE transaction. psycopg opens one implicitly and commits on exit;
            # any exception rolls the whole thing back and the previous graph
            # survives intact.
            cur.execute("truncate node_sources, edges, nodes, files, "
                        "edge_rels, node_types, projection_meta restart identity")

            cur.executemany("insert into node_types(name,description) values (%s,%s)",
                            node_types)
            cur.executemany(
                "insert into edge_rels(name,from_type,to_type,description) "
                "values (%s,%s,%s,%s)", edge_rels)
            cur.executemany(
                "insert into files(relative_path,sha256,bytes,sheet_count,parsed,"
                "drive_file_id,drive_url) values (%s,%s,%s,%s,%s,%s,%s)", files)

            with cur.copy("copy nodes (id,type,label,label_raw,sensitive,props) "
                          "from stdin") as cp:
                for row in nodes:
                    cp.write_row(row)
            with cur.copy("copy edges (rel,source_id,target_id,props) "
                          "from stdin") as cp:
                for row in edges:
                    cp.write_row(row)
            with cur.copy("copy node_sources (id,node_id,prop,origin,file,sheet,"
                          "row_num,col_num,col_name,page,within_cell,ordinal,evidence,"
                          "entered_at,prop_ordinal) from stdin") as cp:
                for row in sources:
                    cp.write_row(row)

            cur.execute(
                "insert into projection_meta(id,scope,content_hash,built_as_of,"
                "plugin_version,taxonomy_version,node_count,edge_count,source_count) "
                "values (1,%s,%s,%s,%s,%s,%s,%s,%s)",
                (args.scope, content, graph["meta"].get("as_of"),
                 json.loads((KNOWLEDGE_DIR.parent / ".claude-plugin" /
                             "plugin.json").read_text())["version"],
                 graph["meta"].get("taxonomy_version"),
                 len(nodes), len(edges), len(sources)))
        conn.commit()
    elapsed = time.time() - started

    print()
    print(f"  projected in {elapsed:.1f}s "
          f"({(len(nodes)+len(edges)+len(sources))/max(elapsed,0.01):,.0f} rows/s)")
    print("  one transaction — a failure would have left the previous graph intact")

    # The landing page's counts describe THIS projection, so they are
    # regenerated by the thing that creates it rather than by refresh.py. A
    # generated file that someone has to remember to regenerate is a
    # hand-written file with extra steps, and the landing page is the surface
    # where a stale number is least likely to be noticed.
    if args.scope == "public" and not args.dry_run:
        from pipeline import gen_landing_stats
        with db.connect(db.SESSION) as meta_conn:
            stats = gen_landing_stats.collect(meta_conn)
        payload = json.dumps(stats, indent=2, sort_keys=True) + "\n"
        gen_landing_stats.OUT.write_text(payload, encoding="utf-8")
        print(f"  public/stats.json regenerated — {stats['nodes']:,} nodes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
