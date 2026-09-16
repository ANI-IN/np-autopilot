#!/usr/bin/env python3
"""B6 — validate the graph. Every category must be able to fire.

A clean report on the first run means the checks are broken, not that the graph
is perfect. Categories that find nothing print NOT EXERCISED so a silent check
is visible as a gap rather than read as a pass.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import KNOWLEDGE_DIR, build_log                # noqa: E402

FAIL, WARN, INFO = "FAIL", "WARN", "INFO"


class Report:
    def __init__(self) -> None:
        self.findings: list[tuple[str, str, str]] = []
        self.exercised: set[str] = set()
        self.categories: list[str] = []

    def category(self, name: str) -> None:
        self.categories.append(name)

    def add(self, level: str, category: str, message: str) -> None:
        self.findings.append((level, category, message))
        self.exercised.add(category)


def categories_fired(graph_path: Path) -> list[str]:
    """Run the checks on `graph_path` silently and return the categories that fired.

    Used by tests/test_validate_categories.py to prove each check actually works
    by deliberately corrupting a graph. A check that never fires is untested.
    """
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return _run(graph_path)[0]


def _run(graph_path: Path | None = None):
    g = json.loads((graph_path or (KNOWLEDGE_DIR / "graph.json")).read_text(encoding="utf-8"))
    nodes, edges = g["nodes"], g["edges"]
    by_id = {n["id"]: n for n in nodes}
    by_type = defaultdict(list)
    for n in nodes:
        by_type[n["type"]].append(n)
    r = Report()
    review_flags = Counter()

    print("=" * 78)
    print("VALIDATION REPORT")
    print("=" * 78)
    print(f"graph      : {len(nodes)} nodes, {len(edges)} edges")
    print(f"taxonomy   : v{taxonomy.version()}")
    print(f"source     : {g['meta']['source']}  (Drive deferred to v2)")
    print()

    # --- version-bump enforcement. The documented failure mode is a forgotten
    # bump meaning fixes never reach anyone. Automatic is not enough; it must
    # also be ENFORCED, or a manual build silently ships an unreachable graph.
    lock_path = KNOWLEDGE_DIR / ".version-lock.json"
    plugin_path = KNOWLEDGE_DIR.parent / ".claude-plugin" / "plugin.json"
    if lock_path.exists() and plugin_path.exists():
        import hashlib as _h
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        cur_ver = json.loads(plugin_path.read_text(encoding="utf-8"))["version"]
        payload = json.dumps({"nodes": g["nodes"], "edges": g["edges"]},
                             sort_keys=True, separators=(",", ":"))
        cur_hash = _h.sha256(payload.encode()).hexdigest()
        if cur_hash != lock.get("content_hash") and cur_ver == lock.get("plugin_version"):
            r.add(FAIL, "version-bump",
                  f"graph.json content changed but plugin.json is still {cur_ver}. "
                  "Teammates would never receive this build. Run pipeline/refresh.py, "
                  "which bumps automatically.")
        else:
            r.add(INFO, "version-bump",
                  f"plugin {cur_ver}, graph hash {cur_hash[:12]} — consistent with the lock")

    for c in ["provenance", "sensitive-flag", "junk-label", "cadence-collision",
              "endpoint-type", "wildcard-edge", "count-vs-expect", "empty-edge-type",
              "orphan-node", "components", "absolute-path", "excluded-file",
              "excluded-field", "duplicate-id", "blank-identifier", "quarter-map",
              "version-bump"]:
        r.category(c)

    # provenance
    for n in nodes:
        if not n.get("sources"):
            r.add(FAIL, "provenance", f"{n['type']} {n['label']!r} has no sources")
    # sensitive
    for n in nodes:
        if "sensitive" not in n:
            r.add(FAIL, "sensitive-flag", f"{n['type']} {n['label']!r} has no sensitive flag")
    # junk labels — person/instructor only
    for n in nodes:
        if n["type"] not in ("person", "instructor"):
            continue
        lab = n["label"]
        if len(lab) > 40:
            r.add(WARN, "junk-label", f"{n['type']} label >40 chars: {lab[:44]!r}")
        if "@" in lab or "http" in lab.lower():
            r.add(FAIL, "junk-label", f"{n['type']} label contains @/http: {lab!r}")
        # Review flags are RETAINED records, not defects. Counted, not
        # enumerated — 199 individual lines would drown the real findings.
        if n.get("review"):
            review_flags[n["review"]] += 1
    if review_flags:
        total_rf = sum(review_flags.values())
        r.add(WARN, "junk-label",
              f"{total_rf} nodes retained with a shape flag (not rejected): "
              + ", ".join(f"{v}x {k}" for k, v in review_flags.most_common()))

    # cadence collision — R5 guard
    vocab = {v.lower() for v in taxonomy.cadences() + taxonomy.stages()}
    for n in by_type["person"]:
        if n["label"].lower() in vocab:
            r.add(FAIL, "cadence-collision", f"person label is a cadence/stage: {n['label']!r}")
    # endpoint types
    wild = set(taxonomy.wildcard_edge_names())
    for e in edges:
        src, dst = by_id.get(e["source"]), by_id.get(e["target"])
        if src is None or dst is None:
            r.add(FAIL, "endpoint-type", f"dangling edge {e['rel']}")
            continue
        if e["rel"] in wild:
            continue
        want_from, want_to = taxonomy.edge_endpoints(e["rel"])
        if src["type"] != want_from or dst["type"] != want_to:
            r.add(FAIL, "endpoint-type",
                  f"{e['rel']}: {src['type']}->{dst['type']}, expected {want_from}->{want_to}")
    # wildcard
    if len(wild) != 1:
        r.add(FAIL, "wildcard-edge", f"expected exactly one wildcard edge, got {sorted(wild)}")
    else:
        r.add(INFO, "wildcard-edge",
              f"{sorted(wild)[0]} uses from:'*' by design; endpoint check skips it")
    # counts vs expect
    for t in taxonomy.node_type_names():
        exp, tol = taxonomy.expected_count(t), taxonomy.tolerance(t)
        got = len(by_type[t])
        if exp is None:
            r.add(INFO, "count-vs-expect",
                  f"{t}: {got} — expect is null (floor, coverage incomplete); not asserted")
            continue
        if abs(got - exp) > (tol or 0):
            r.add(FAIL, "count-vs-expect", f"{t}: {got}, expected {exp} +/- {tol}")
    # empty edge types
    seen_rel = Counter(e["rel"] for e in edges)
    for name in taxonomy.edge_type_names():
        if seen_rel.get(name, 0) == 0:
            r.add(WARN, "empty-edge-type", f"{name} produced ZERO edges")
    # orphans
    deg = Counter()
    for e in edges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    prov = taxonomy.edge_for_role("provenance")
    real = Counter()
    for e in edges:
        if e["rel"] != prov:
            real[e["source"]] += 1
            real[e["target"]] += 1
    orphans = [n for n in nodes if n["type"] != "file" and real[n["id"]] == 0]
    if orphans:
        c = Counter(n["type"] for n in orphans)
        r.add(WARN, "orphan-node",
              f"{len(orphans)} nodes have only provenance edges: {dict(c)}")
    # components (ignoring the file hub, which is not a bridge)
    adj = defaultdict(set)
    for e in edges:
        if e["rel"] == prov:
            continue
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])
    seen, comps = set(), []
    for n in nodes:
        if n["type"] == "file" or n["id"] in seen:
            continue
        stack, comp = [n["id"]], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(adj[cur] - seen)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    big = [c for c in comps if len(c) > 1]
    r.add(WARN if len(big) > 1 else INFO, "components",
          f"{len(big)} connected components (excluding provenance hub); "
          f"largest {len(big[0]) if big else 0}, "
          f"{len([c for c in comps if len(c)==1])} isolated")
    # absolute paths
    for n in nodes:
        for s in n.get("sources", []):
            if str(s.get("file", "")).startswith("/"):
                r.add(FAIL, "absolute-path", f"absolute path in provenance: {s['file']}")
    # excluded file / field
    excluded = set(taxonomy.excluded_files())
    for n in nodes:
        for s in n.get("sources", []):
            if s.get("file") in excluded:
                r.add(FAIL, "excluded-file", f"excluded file reached the graph: {s['file']}")
    for n in nodes:
        for k in n:
            if taxonomy.is_excluded_field(k):
                r.add(FAIL, "excluded-field", f"{n['type']} carries excluded field {k!r}")
    # duplicate ids
    dupes = [i for i, c in Counter(n["id"] for n in nodes).items() if c > 1]
    if dupes:
        r.add(FAIL, "duplicate-id", f"{len(dupes)} duplicate node ids")
    # blank identifiers (retained, reported)
    cand = json.loads((KNOWLEDGE_DIR / "candidates.json").read_text(encoding="utf-8"))
    blanks = cand.get("blank_identifiers", [])
    if blanks:
        names = sorted({b.get("name", b.get("raw", "?")) for b in blanks})
        r.add(WARN, "blank-identifier",
              f"{len(blanks)} rows retained with a blank/empty identifier: {names}")
    # quarter map
    qs = {q["sheet"] for q in taxonomy._raw()["quarter_vocabulary"]}
    seen_sheets = {s.get("sheet") for n in by_type["person"] for s in n.get("sources", [])
                   if s.get("sheet")}
    unmapped = sorted(s for s in seen_sheets
                      if s not in qs and re.search(r"Q\s?\d", s or ""))
    if unmapped:
        r.add(FAIL, "quarter-map", f"quarter-labelled sheets not in the map: {unmapped}")
    else:
        r.add(INFO, "quarter-map", f"all {len(qs)} quarter sheets resolve through the map")

    # ---------------- output -------------------------------------------------
    order = {FAIL: 0, WARN: 1, INFO: 2}
    for level in (FAIL, WARN, INFO):
        rows = [f for f in r.findings if f[0] == level]
        print("-" * 78)
        print(f"{level}  ({len(rows)})")
        print("-" * 78)
        if not rows:
            print("  none")
        shown = Counter()
        for lv, cat, msg in rows:
            shown[cat] += 1
            if shown[cat] <= 6:
                print(f"  [{cat}] {msg}")
        for cat, n in shown.items():
            if n > 6:
                print(f"  [{cat}] ... {n-6} more")
        print()

    print("-" * 78)
    print("CATEGORY EXERCISE CHECK")
    print("-" * 78)
    print("  A category that never fires is an untested check, not a clean graph.")
    never = [c for c in r.categories if c not in r.exercised]
    for c in r.categories:
        print(f"  {'EXERCISED    ' if c in r.exercised else 'NOT EXERCISED'}  {c}")
    print()
    print(f"  {len(r.exercised)}/{len(r.categories)} categories exercised")
    if never:
        print(f"  NOT EXERCISED: {never}")
    print()

    fails = sum(1 for f in r.findings if f[0] == FAIL)
    warns = sum(1 for f in r.findings if f[0] == WARN)
    print("=" * 78)
    print(f"RESULT: {fails} FAIL, {warns} WARN, "
          f"{len(r.findings)-fails-warns} INFO — "
          f"{'GRAPH REJECTED' if fails else 'graph accepted with warnings'}")
    print("=" * 78)

    return sorted(r.exercised), fails, warns, len(nodes), len(edges), r.categories


def main() -> int:
    exercised, fails, warns, nnodes, nedges, cats = _run()
    delta = (f"- validate: {fails} FAIL, {warns} WARN, "
             f"{len(exercised)}/{len(cats)} categories exercised, "
             f"{nnodes} nodes, {nedges} edges")
    with build_log().open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — validate\n\n")
        fh.write(delta + "\n")
    print(f"\nBUILD_LOG delta line:\n  {delta}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
