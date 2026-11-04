#!/usr/bin/env python3
"""Pass 8 — apply the answered REVIEW-QUEUE merges and write ONE graph.

Separate from pass 7 on purpose. Pass 7 builds the content graph from the
crawl and knows nothing about the legacy 922; this pass joins the two, and the
join is a HUMAN DECISION read from config/module-merges.yaml. Fusing them would
put an answer sheet inside a build step and make the build unreproducible
whenever the answers change.

Writes `knowledge/merged_graph.json` (gitignored; a local output, not
tracked). The projection and every reader merge in memory instead
(graphio.load_merged) and never read the file; nothing here projects.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import module_merge as mm                          # noqa: E402
from pipeline.lib import taxonomy                                    # noqa: E402
from pipeline.lib.paths import KNOWLEDGE_DIR                         # noqa: E402

MAIN = KNOWLEDGE_DIR / "graph.json"
CONTENT = KNOWLEDGE_DIR / "content_graph.json"
OUT = KNOWLEDGE_DIR / "merged_graph.json"


def _modules(g):
    return [n for n in g["nodes"] if n["type"] == "module"]


def _dupes(g):
    c = collections.Counter((n.get("label") or "").strip().lower()
                            for n in _modules(g))
    return {k: v for k, v in c.items() if v > 1}


def main() -> int:
    main_g = json.loads(MAIN.read_text(encoding="utf-8"))
    content_g = json.loads(CONTENT.read_text(encoding="utf-8"))
    spec = mm.load_spec()
    merged = mm.merge(main_g, content_g, spec)
    not_topics = sorted(n["id"] for n in merged["nodes"] if n.get(mm.NOT_A_TOPIC))

    before_nodes = len(main_g["nodes"]) + len(content_g["nodes"])
    before_edges = len(main_g["edges"]) + len(content_g["edges"])
    before_mods = len(_modules(main_g)) + len(_modules(content_g))
    before_dupes = _dupes({"nodes": main_g["nodes"] + content_g["nodes"]})

    print("=" * 78)
    print("PASS 8 — merged graph")
    print("=" * 78)
    print(f"\n  {'':22} {'before':>10} {'after':>10}")
    print("  " + "-" * 44)
    print(f"  {'nodes':22} {before_nodes:10} {len(merged['nodes']):10}")
    print(f"  {'edges':22} {before_edges:10} {len(merged['edges']):10}"
          "   (none dropped)")
    print(f"  {'module nodes':22} {before_mods:10} {len(_modules(merged)):10}")
    print(f"  {'duplicate labels':22} {len(before_dupes):10} "
          f"{len(_dupes(merged)):10}")
    print(f"  {'absorbed nodes':22} {'':10} {merged['meta']['absorbed_nodes']:10}")

    rem = _dupes(merged)
    if rem:
        print(f"\n  DUPLICATE MODULE LABELS REMAINING ({len(rem)})")
        for lab, n in sorted(rem.items(), key=lambda kv: -kv[1])[:12]:
            print(f"    {n}x  {lab[:60]}")

    # -- instructors per merged module, BY TIER ---------------------------
    by_id = {n["id"]: n for n in merged["nodes"]}
    tiers = collections.defaultdict(lambda: collections.defaultdict(set))
    for e in merged["edges"]:
        t = e.get("tier")
        if not t:
            continue
        # the module end is whichever end is a module
        for end, other in (("source", "target"), ("target", "source")):
            n = by_id.get(e[end])
            if n is not None and n["type"] == "module":
                who = by_id.get(e[other])
                if who is not None:
                    tiers[n["id"]][t].add(who.get("label"))
    merged_mods = [n for n in _modules(merged) if n.get("merge_ids")]
    print(f"\n  INSTRUCTORS PER MERGED MODULE, BY TIER ({len(merged_mods)} merged)")
    print(f"    {'MOD':8} {'module':34} {'mastersheet':>12} {'legacy':>8}")
    print("    " + "-" * 66)
    for m in sorted(merged_mods, key=lambda x: (x.get("domain_slug") or "",
                                                x.get("sequence") or 0)):
        t = tiers.get(m["id"], {})
        print(f"    {','.join(m['merge_ids'])[:8]:8} "
              f"{(m.get('domain_slug','')+'/'+str(m.get('sequence'))+' '+m['label'])[:34]:34} "
              f"{len(t.get(mm.TIER_MASTERSHEET, ())):12} "
              f"{len(t.get(mm.TIER_LEGACY, ())):8}")

    unconf = [e for e in merged["edges"] if e.get("confirmed") is False]
    print(f"\n  edges kept but NOT asserted (unconfirmed): {len(unconf)}")

    # MOD-15 put its legacy instructors on the SESSIONS, not the module, so
    # the per-module table above shows 0 for it. Showing only that table would
    # report the evidence as lost when it was deliberately placed elsewhere.
    others = [n for n in merged["nodes"]
              if n.get("merge_ids") and n["type"] != "module"]
    for n in sorted(others, key=lambda x: x["type"]):
        who = sorted({by_id[e["source"]].get("label")
                      for e in merged["edges"]
                      if e.get("tier") and e["target"] == n["id"]
                      and e["source"] in by_id}
                     | {by_id[e["target"]].get("label")
                        for e in merged["edges"]
                        if e.get("tier") and e["source"] == n["id"]
                        and e["target"] in by_id})
        print(f"  absorbed into {n['type']:14} {n['label'][:34]:34} "
              f"{','.join(n['merge_ids'])}"
              + (f"  legacy-tier: {', '.join(x for x in who if x)}" if who else ""))

    # -- instructor identity ----------------------------------------------
    def dupes(g, typ):
        c = collections.Counter((n.get("label") or "").strip()
                                for n in g["nodes"] if n["type"] == typ)
        return {k: v for k, v in c.items() if v > 1}

    before_ins = dupes({"nodes": main_g["nodes"] + content_g["nodes"]}, "instructor")
    after_ins = dupes(merged, "instructor")
    print(f"\n  INSTRUCTOR IDENTITY")
    print(f"    duplicate labels      {len(before_ins):5} -> {len(after_ins)}")
    ex = merged["meta"].get("excluded_pairs") or []
    print(f"    pairs excluded by the safeguard: {len(ex)}")
    for x in ex:
        print(f"      {x['id']:8} {x['canonical']:24} {x['reason']}")
    if after_ins:
        print("    still duplicated, and why:")
        for lab in sorted(after_ins):
            print(f"      {after_ins[lab]}x {lab}")

    by_id = {n["id"]: n for n in merged["nodes"]}
    print(f"\n  D1: topics that are a person's name, marked {mm.NOT_A_TOPIC}: "
          f"{len(not_topics)}")
    for i in not_topics:
        print(f"      {by_id[i]['label']}")

    OUT.write_text(json.dumps(merged, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\n  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
