#!/usr/bin/env python3
"""C4 — prove a graph matches the frozen migration reference.

Written while the graph is still only files, and run file-against-file first. A
verification script that has never passed is not a verification script: it is an
untested assertion about a system that does not exist yet, and it will be
debugged during the migration, which is exactly when nobody can tell whether the
script or the migration is wrong.

Expected values live in config/migration-baseline.yaml, NOT in this file. Three
alias decisions are still open (ML, Agentic AI, Product Management — 272
edges), and resolving them will legitimately move node counts, edge counts and
component structure. When that happens the baseline is re-frozen deliberately,
in a commit that says so, rather than by editing a constant here.

    python3 pipeline/verify_migration.py            # verify graph.json
    python3 pipeline/verify_migration.py --freeze   # re-record the reference
    python3 pipeline/verify_migration.py --graph path/to/graph.json

`--source` is reserved: the same checks will run against the Supabase projection
once it exists, so the migration is proven by the same assertions that pass
today, not by new ones written after the fact.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                            # noqa: E402

from pipeline.lib import graphio, taxonomy                             # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR, REPO_ROOT    # noqa: E402

BASELINE = CONFIG_DIR / "migration-baseline.yaml"
PLUGIN = REPO_ROOT / ".claude-plugin" / "plugin.json"


def measure(g: dict) -> dict:
    """Every figure the baseline pins, measured from one graph."""
    nodes, edges = g["nodes"], g["edges"]
    prov = taxonomy.edge_for_role("provenance")

    triples = collections.Counter((e["source"], e["target"], e["rel"]) for e in edges)
    colliding = {k: c for k, c in triples.items() if c > 1}

    origins = collections.Counter()
    for n in nodes:
        for s in n.get("sources", []):
            origins[s.get("origin")] += 1

    hand = taxonomy.origin_hand()
    hand_nodes = sum(1 for n in nodes
                     if any(s.get("origin") == hand for s in n.get("sources", [])))

    # Components ignoring provenance. sourced_from is a citation, not a path —
    # its file nodes reach degree 18,134, so including it collapses the graph
    # into one blob and the number stops meaning anything.
    adj = collections.defaultdict(set)
    for e in edges:
        if e["rel"] == prov:
            continue
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])
    seen, sizes = set(), []
    for n in nodes:
        if n["type"] == "file" or n["id"] in seen:
            continue
        stack, size = [n["id"]], 0
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            size += 1
            stack.extend(adj[cur] - seen)
        sizes.append(size)
    sizes.sort(reverse=True)

    return {
        "content_hash": graphio.content_hash(g),
        "totals": {"nodes": len(nodes), "edges": len(edges)},
        "node_counts": dict(sorted(collections.Counter(n["type"] for n in nodes).items())),
        "edge_counts": dict(sorted(collections.Counter(e["rel"] for e in edges).items())),
        "duplicates": {
            "distinct_colliding_triples": len(colliding),
            "extra_rows": sum(c - 1 for c in colliding.values()),
            "by_rel": dict(sorted(collections.Counter(
                k[2] for k in colliding).items())),
        },
        "provenance": {
            "entries_by_origin": dict(sorted(origins.items())),
            "nodes_total": len(nodes),
            "nodes_with_sources": sum(1 for n in nodes if n.get("sources")),
            "nodes_with_hand_provenance": hand_nodes,
        },
        "components": {
            "excluding_provenance": len([s for s in sizes if s > 1]),
            "largest": sizes[0] if sizes else 0,
            "isolated": sum(1 for s in sizes if s == 1),
        },
    }


def graph_from_db() -> dict:
    """Rebuild the graph dict from Postgres, in the shape measure() expects.

    Deliberately reconstructive rather than a set of SQL COUNT queries. Counting
    in SQL would answer "are the totals the same"; rebuilding answers "is it the
    same graph", and it is the same measure() running on both sides — so a bug
    in the measurement cannot pass on one side and fail on the other.
    """
    from pipeline.lib import db

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select id, type, label, label_raw, sensitive, props "
                    "from nodes")
        nodes = {}
        for nid, ntype, label, label_raw, sensitive, props in cur.fetchall():
            n = {"id": nid, "type": ntype, "label": label,
                 "sensitive": sensitive, "sources": []}
            if label_raw is not None:
                n["label_raw"] = label_raw
            n.update(props or {})
            nodes[nid] = n

        # Group assertion rows back into source entries. One row per established
        # property, so rows sharing coordinates are one entry whose
        # `establishes` list is rebuilt in prop_ordinal order.
        cur.execute("""
            select node_id, origin, file, sheet, row_num, col_num, col_name,
                   page, within_cell, ordinal, evidence, entered_at,
                   prop, prop_ordinal
            from node_sources
            order by node_id, ordinal, prop_ordinal
        """)
        grouped: dict[tuple, dict] = {}
        order: list[tuple] = []
        for (node_id, origin, file, sheet, row_num, col_num, col_name, page,
             within_cell, ordinal, evidence, entered_at, prop,
             prop_ordinal) in cur.fetchall():
            key = (node_id, origin, file, sheet, row_num, col_num, col_name,
                   page, within_cell, ordinal)
            if key not in grouped:
                entry = {"origin": origin, "ordinal": ordinal}
                if file is not None:
                    entry["file"] = file
                if sheet is not None:
                    entry["sheet"] = sheet
                if row_num is not None:
                    entry["row"] = row_num
                if col_num is not None:
                    entry["column"] = col_num
                elif col_name is not None:
                    entry["column"] = col_name
                if page is not None:
                    entry["page"] = page
                if within_cell is not None:
                    entry["within_cell"] = within_cell
                if evidence is not None:
                    entry["evidence"] = evidence
                if entered_at is not None:
                    entry["entered_at"] = entered_at.isoformat()
                grouped[key] = entry
                order.append(key)
            if prop is not None:
                grouped[key].setdefault("_props", []).append((prop_ordinal, prop))
        for key in order:
            entry = grouped[key]
            props = entry.pop("_props", None)
            if props:
                entry["establishes"] = [p for _, p in sorted(props)]
            nodes[key[0]]["sources"].append(entry)

        cur.execute("select rel, source_id, target_id, props from edges")
        edges = []
        for rel, src, tgt, props in cur.fetchall():
            e = {"rel": rel, "source": src, "target": tgt}
            e.update(props or {})
            edges.append(e)

        cur.execute("select scope, content_hash, node_count, edge_count, "
                    "source_count, projected_at from projection_meta where id=1")
        row = cur.fetchone()
        meta = {}
        if row:
            meta = {"scope": row[0], "projected_content_hash": row[1],
                    "projected_at": row[5].isoformat()}
    return {"meta": meta, "nodes": list(nodes.values()), "edges": edges}


def compare(expected: dict, actual: dict) -> list[tuple[bool, str, str]]:
    """Walk both dicts and return (ok, path, detail) per leaf."""
    out: list[tuple[bool, str, str]] = []

    def walk(exp, act, path):
        if isinstance(exp, dict):
            for key in sorted(set(exp) | set(act if isinstance(act, dict) else {})):
                walk(exp.get(key), (act or {}).get(key), f"{path}.{key}" if path else key)
            return
        ok = exp == act
        detail = f"{act}" if ok else f"expected {exp!r}, got {act!r}"
        out.append((ok, path, detail))

    walk(expected, actual, "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true",
                    help="re-record the baseline from the current graph. Use only "
                         "in a commit that explains why the reference moved.")
    ap.add_argument("--graph", default=str(KNOWLEDGE_DIR / "graph.json"))
    ap.add_argument("--source", default="file", choices=["file", "supabase"],
                    help="where to measure: the built files, or the projection")
    ap.add_argument("--scope", default=None, choices=["full", "public"],
                    help="which baseline to assert against. Defaults to full for "
                         "--source file and public for --source supabase, which "
                         "is what each actually holds in this phase.")
    args = ap.parse_args()

    scope = args.scope or ("public" if args.source == "supabase" else "full")
    if args.source == "supabase":
        g = graph_from_db()
    else:
        # `full` is the union of both halves; `public` is the committed file
        # alone, which is what this phase projects.
        g = graphio.load_graph(Path(args.graph),
                               include_sensitive=(scope == "full"))
    actual = measure(g)

    if args.freeze:
        payload = {
            "version": 1,
            "note": ("Frozen migration reference. Every migration-verification run "
                     "asserts against THIS, never against a live rebuild — a live "
                     "rebuild would move with the corpus and prove nothing. "
                     "Re-freeze only in a commit that says why."),
            "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "built_as_of": g["meta"].get("as_of"),
            "plugin_version": json.loads(PLUGIN.read_text(encoding="utf-8"))["version"],
            "taxonomy_version": g["meta"].get("taxonomy_version"),
            "open_questions_that_will_move_these": [
                "Q7 aliases ML / Agentic AI / Product Management — 272 expert_in "
                "edges currently unjoined. Resolving any of them moves edge_counts "
                "and component structure.",
            ],
            "scopes": {
                # TWO scopes, because the database deliberately holds only the
                # public half in this phase. Verifying it against the full
                # baseline would fail on every count and prove nothing.
                "full": measure(graphio.load_graph(Path(args.graph),
                                                   include_sensitive=True)),
                "public": measure(graphio.load_graph(Path(args.graph),
                                                     include_sensitive=False)),
            },
            **actual,
        }
        BASELINE.write_text(yaml.safe_dump(payload, sort_keys=False, width=88),
                            encoding="utf-8")
        print(f"FROZE {BASELINE.relative_to(REPO_ROOT)}")
        print(f"  content_hash {actual['content_hash'][:16]}")
        print(f"  {actual['totals']['nodes']} nodes, {actual['totals']['edges']} edges")
        return 0

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE}. Run with --freeze to create one.")
        return 2
    expected = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    section = (expected.get("scopes") or {}).get(scope, expected)
    checked = {k: section[k] for k in
               ("content_hash", "totals", "node_counts", "edge_counts",
                "duplicates", "provenance", "components") if k in section}

    rows = compare(checked, actual)
    failed = [r for r in rows if not r[0]]

    print("=" * 78)
    print("MIGRATION VERIFICATION")
    print("=" * 78)
    print(f"  baseline : {BASELINE.relative_to(REPO_ROOT)}  "
          f"(frozen {expected.get('frozen_at', '?')})")
    print(f"  target   : {args.source}  "
          f"{'postgres' if args.source == 'supabase' else args.graph}")
    print(f"  scope    : {scope}")
    print()
    for ok, path, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {path:<46} {detail}")
    print()
    print("=" * 78)
    print(f"RESULT: {len(rows) - len(failed)}/{len(rows)} checks passed — "
          f"{'VERIFIED' if not failed else 'MISMATCH'}")
    print("=" * 78)
    if failed:
        print("\nA mismatch is not automatically a migration bug. If the corpus or a")
        print("curation decision changed, re-freeze deliberately and say so in the")
        print("commit. Never edit the baseline to make a diff go away.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
