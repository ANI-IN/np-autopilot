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
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                            # noqa: E402

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR, REPO_ROOT    # noqa: E402

BASELINE = CONFIG_DIR / "migration-baseline.yaml"
PLUGIN = REPO_ROOT / ".claude-plugin" / "plugin.json"


def content_hash(g: dict) -> str:
    """Hash of nodes+edges only. Excludes meta, which carries a timestamp."""
    return hashlib.sha256(json.dumps(
        {"nodes": g["nodes"], "edges": g["edges"]},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
        "content_hash": content_hash(g),
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
    ap.add_argument("--source", default="file", choices=["file"],
                    help="reserved — 'supabase' lands with the projection")
    args = ap.parse_args()

    g = json.loads(Path(args.graph).read_text(encoding="utf-8"))
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
    checked = {k: expected[k] for k in
               ("content_hash", "totals", "node_counts", "edge_counts",
                "duplicates", "provenance", "components") if k in expected}

    rows = compare(checked, actual)
    failed = [r for r in rows if not r[0]]

    print("=" * 78)
    print("MIGRATION VERIFICATION")
    print("=" * 78)
    print(f"  baseline : {BASELINE.relative_to(REPO_ROOT)}  "
          f"(frozen {expected.get('frozen_at', '?')})")
    print(f"  target   : {args.source}  {args.graph}")
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
