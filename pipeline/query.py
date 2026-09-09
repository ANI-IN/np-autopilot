#!/usr/bin/env python3
"""Deterministic query layer for the plugin commands.

Commands call THIS, not the graph directly. Retrieval and tiering happen here in
Python so they cannot be paraphrased, reordered or merged by a language model.
The command's job is to present what this returns, not to decide it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                            # noqa: E402

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR               # noqa: E402

G = json.loads((KNOWLEDGE_DIR / "graph.json").read_text(encoding="utf-8"))
NODES, EDGES = G["nodes"], G["edges"]
BY = {n["id"]: n for n in NODES}
OUT = defaultdict(list)
IN = defaultdict(list)
for e in EDGES:
    OUT[e["source"]].append(e)
    IN[e["target"]].append(e)

_facts = yaml.safe_load((CONFIG_DIR / "out-of-corpus-facts.yaml").read_text(encoding="utf-8"))
NO_INSTRUCTOR_DOMAINS = {s for f in _facts["facts"]
                         for s in (f.get("subject") or []) if "no instructors" in f["fact"]}

TEACHES = taxonomy.edge_for_role("instructor_module")
EXPERT = taxonomy.edge_for_role("instructor_domain")
COVERS = taxonomy.edge_for_role("program_domain")
CONTAINS = taxonomy.edge_for_role("program_module")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s).lower()).strip()


def find_domain(q):
    """Exact, else prefix, else unique substring. AMBIGUITY IS RETURNED, not guessed.

    Silently resolving "Data Science" to "AI Data Science Switch-up (DS 2.0)" is
    the same class of error as the alias sibling problem: one plausible reading
    chosen out of several, with no signal to the caller.
    """
    n = norm(q)
    doms = [d for d in NODES if d["type"] == "domain"]
    exact = [d for d in doms if norm(d["label"]) == n]
    if exact:
        return exact[0]
    # strip a parenthetical qualifier: "Data Science (IP course)" -> "data science"
    base = [d for d in doms if norm(re.sub(r"\(.*?\)", " ", d["label"])) == n]
    if len(base) == 1:
        return base[0]
    pref = [d for d in doms if norm(d["label"]).startswith(n)]
    if len(pref) == 1:
        return pref[0]
    part = [d for d in doms if n in norm(d["label"])]
    cands = base or pref or part
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        return {"ambiguous": [d["label"] for d in sorted(cands, key=lambda x: len(x["label"]))]}
    return None


def modules_of(domain):
    """Domain -> modules, via the programs that cover it. All inferred."""
    progs = [BY[e["source"]] for e in IN[domain["id"]] if e["rel"] == COVERS]
    mods = {}
    for p in progs:
        for e in OUT[p["id"]]:
            if e["rel"] == CONTAINS:
                mods[e["target"]] = BY[e["target"]]
    return mods


def staffing(query):
    d = find_domain(query)
    if isinstance(d, dict) and "ambiguous" in d:
        return {"ambiguous": d["ambiguous"],
                "message": f"{query!r} matches {len(d['ambiguous'])} domains. "
                           "Ask which one; do not pick."}
    if not d:
        return {"error": f"no domain matching {query!r}",
                "known": sorted(n["label"] for n in NODES if n["type"] == "domain")}
    mods = modules_of(d)
    taught = defaultdict(list)
    for mid in mods:
        for e in IN[mid]:
            if e["rel"] == TEACHES:
                taught[e["source"]].append(e)

    tier1 = []
    for iid, es in taught.items():
        n = BY[iid]
        last = max((e.get("last_taught") or "" for e in es), default="")
        tier1.append({
            "name": n["label"], "modules": sorted({BY[e["target"]]["label"] for e in es}),
            "last_taught": last or None,
            "sessions_past": sum(e.get("sessions_past") or 0 for e in es),
            "sessions_scheduled": sum(e.get("sessions_scheduled") or 0 for e in es),
            "declined": n.get("declined_count"), "confirmed": n.get("confirmed_count"),
            "decline_rate": n.get("decline_rate"),
            "source": (es[0].get("provenance") or {}).get("file"),
            "source_sheet": (es[0].get("provenance") or {}).get("sheet"),
        })
    tier1.sort(key=lambda r: (r["last_taught"] or "", r["sessions_past"]), reverse=True)

    tiers = defaultdict(list)
    for e in IN[d["id"]]:
        if e["rel"] != EXPERT:
            continue
        n = BY[e["source"]]
        if n["label"] in {r["name"] for r in tier1}:
            continue
        key = e.get("basis", "unknown") + ("+via_alias" if e.get("via_alias") else "")
        tiers[key].append({"name": n["label"], "subject_raw": e.get("subject_raw"),
                           "declined": n.get("declined_count")})

    return {
        "domain": d["label"], "cadence": d.get("cadence"),
        "modules_total": len(mods),
        "modules_with_teaching_history": len({m for m in mods
                                              if any(e["rel"] == TEACHES for e in IN[m])}),
        "no_instructors_confirmed": d["label"] in NO_INSTRUCTOR_DOMAINS,
        "taught": tier1,
        "declared": {k: sorted(v, key=lambda r: r["name"]) for k, v in tiers.items()},
        "owners": [BY[e["target"]]["label"] for e in OUT[d["id"]] if e["rel"] == "owned_by"],
    }


def coverage():
    doms = [n for n in NODES if n["type"] == "domain"]
    progs = [n for n in NODES if n["type"] == "program"]
    mods = [n for n in NODES if n["type"] == "module"]
    joined = {e["source"] for e in EDGES if e["rel"] == COVERS}
    contained = {e["target"] for e in EDGES if e["rel"] == CONTAINS}
    taught = {e["target"] for e in EDGES if e["rel"] == TEACHES}
    owned = {e["source"] for e in EDGES if e["rel"] in ("owned_by", "supported_by",
                                                        "delivered_by")}
    prov = taxonomy.edge_for_role("provenance")
    deg = defaultdict(int)
    for e in EDGES:
        if e["rel"] != prov:
            deg[e["source"]] += 1
            deg[e["target"]] += 1
    dom_no_teach = []
    for d in doms:
        m = modules_of(d)
        if m and not any(mid in taught for mid in m):
            dom_no_teach.append(d["label"])
    return {
        "programs_without_domain": sorted(p["label"] for p in progs if p["id"] not in joined),
        "modules_without_program": len([m for m in mods if m["id"] not in contained]),
        "modules_without_instructor": len([m for m in mods if m["id"] not in taught]),
        "domains_without_owner": sorted(d["label"] for d in doms if d["id"] not in owned),
        "domains_with_modules_but_no_teaching": [
            x for x in dom_no_teach if x not in NO_INSTRUCTOR_DOMAINS],
        "excluded_from_report_by_owner_confirmation": sorted(NO_INSTRUCTOR_DOMAINS),
        "isolated_records": len([n for n in NODES
                                 if n["type"] not in ("file",) and deg[n["id"]] == 0]),
        "workflow_ownership": "OUT OF SCOPE — ownership in NP attaches to domains, "
                              "not workflows. Never report 92 workflows as missing an owner.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["staffing", "coverage"])
    ap.add_argument("target", nargs="?", default="")
    a = ap.parse_args()
    out = staffing(a.target) if a.command == "staffing" else coverage()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
