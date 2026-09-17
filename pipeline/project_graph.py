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
    for e in graph["edges"]:
        props = {k: v for k, v in e.items() if k not in EDGE_COLUMNS}
        edges.append((e["rel"], e["source"], e["target"],
                      json.dumps(props, sort_keys=True)))
    return nodes, edges, sources


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="public", choices=["public", "full"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.scope == "full":
        sys.exit(
            "--scope full is refused in this phase.\n"
            "The sensitive half is 277 hiring rejections and 1,625 in-pipeline "
            "candidates about named external people. Projecting it needs the "
            "`recruiting` RLS path, which does not exist yet — and a table with "
            "no policy denies everyone, which would look like it worked."
        )

    # PUBLIC HALF ONLY. include_sensitive=False is the whole scope decision, in
    # one argument, rather than a filter applied later that someone can forget.
    graph = graphio.load_graph(include_sensitive=False)
    assert graph["meta"]["sensitive_loaded"] is False
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
    print(f"  edges        : {len(edges):,}")
    print(f"  node_sources : {len(sources):,}")
    print(f"  content hash : {content[:16]}")
    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    manifest = json.loads((KNOWLEDGE_DIR / "files.json").read_text(encoding="utf-8"))
    files = [(r["path"], r.get("sha256"), r.get("bytes"), r.get("sheet_count"),
              bool(r.get("parsed")))
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
                "insert into files(relative_path,sha256,bytes,sheet_count,parsed) "
                "values (%s,%s,%s,%s,%s)", files)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
