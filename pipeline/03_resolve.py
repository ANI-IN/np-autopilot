#!/usr/bin/env python3
"""Pass 3 — resolve identities. Fuzzy matching PROPOSES, never applies.

Separate from extraction on purpose. The reference implementation fused merge
with classification in one script, which is why nothing in their pipeline could
say "'Workflows are powerful' is not a person".

Two resolution mechanisms, and only the first changes the graph:

  1. config/people.yaml aliases — hand-confirmed. APPLIED.
  2. string similarity           — PROPOSED to people-review.yaml. Never applied.

IDs are a hash of (type, canonical normalised name). Deterministic by
construction: two runs over unchanged input produce byte-identical output.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from collections import defaultdict
from datetime import timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                            # noqa: E402

from pipeline.lib.paths import BUILD_LOG, CONFIG_DIR, KNOWLEDGE_DIR    # noqa: E402

RESOLVED = KNOWLEDGE_DIR / "resolved.json"
REVIEW = CONFIG_DIR / "people-review.yaml"

T_PERSON, T_INSTRUCTOR = "person", "instructor"
FUZZY_THRESHOLD = 0.70


def node_id(node_type: str, canonical: str) -> str:
    """Deterministic id. Hash of type + canonical name, never of the raw label.

    The reference implementation derived ids from the raw label ('I:workflows
    are powerful'), so any label edit silently created a new node and orphaned
    every edge pointing at the old one.
    """
    digest = hashlib.sha256(f"{node_type}\x00{canonical}".encode()).hexdigest()
    return f"{node_type[:3]}_{digest[:16]}"


def load_people() -> tuple[dict, dict]:
    data = yaml.safe_load(REVIEW.parent.joinpath("people.yaml").read_text(encoding="utf-8"))
    alias_to_canon, meta = {}, {}
    for p in data["people"]:
        canon = p["canonical"]
        meta[canon] = p
        for a in p.get("aliases", []) or []:
            alias_to_canon[a.strip().lower()] = canon
        alias_to_canon[canon.strip().lower()] = canon
    return alias_to_canon, meta


def main() -> int:
    payload = json.loads((KNOWLEDGE_DIR / "candidates.json").read_text(encoding="utf-8"))
    cands = payload["candidates"]
    alias_to_canon, people_meta = load_people()

    print("=" * 78)
    print("PASS 3 — resolve")
    print("=" * 78)
    print(f"candidates : {len(cands)}")
    print(f"people.yaml: {len(people_meta)} canonical, "
          f"{len(alias_to_canon)} alias strings")
    print()

    by_type = defaultdict(list)
    for c in cands:
        by_type[c["type"]].append(c)

    applied, proposed, unmatched = [], [], []
    resolved_nodes: dict[str, dict] = {}

    # ---------------- persons: hand-confirmed aliases only ------------------
    for c in by_type[T_PERSON]:
        raw = c["raw"].strip()
        canon = alias_to_canon.get(raw.lower())
        if canon:
            if raw.lower() != canon.lower():
                applied.append({"from": raw, "to": canon, "basis": "people.yaml alias",
                                "confidence": "confirmed"})
        else:
            unmatched.append(c)
            canon = raw
        nid = node_id(T_PERSON, canon)
        node = resolved_nodes.setdefault(nid, {
            "id": nid, "type": T_PERSON, "label": canon, "label_raw": raw,
            "sources": [], "sensitive": False, "quarters": [], "sheets": [],
        })
        node["sources"].extend(c["sources"])
        if c.get("quarter"):
            node["quarters"].append((c["quarter_order"], c["quarter"]))
        if c.get("sheet"):
            node["sheets"].append(c["sheet"])
        if c.get("employee_id"):
            node.setdefault("employee_ids", [])
            if c["employee_id"] not in node["employee_ids"]:
                node["employee_ids"].append(c["employee_id"])

    # first/last seen quarter — legible only while IAims keeps one sheet per
    # quarter. Captured now because consolidation would destroy it permanently.
    for node in resolved_nodes.values():
        qs = sorted(set(node.pop("quarters", [])))
        if qs:
            node["first_seen_quarter"] = qs[0][1]
            node["last_seen_quarter"] = qs[-1][1]
        node["seen_in_sheets"] = sorted(set(node.pop("sheets", [])))
        meta = people_meta.get(node["label"], {})
        node["team"] = meta.get("team", "other")
        for key in ("title", "seniority", "status", "corpus_disagrees"):
            if meta.get(key) is not None:
                node[key] = meta[key]

    # ---------------- fuzzy: PROPOSE ONLY -----------------------------------
    canon_names = sorted({n["label"] for n in resolved_nodes.values()})
    unresolved_names = sorted({c["raw"].strip() for c in unmatched})
    for name in unresolved_names:
        close = difflib.get_close_matches(name, canon_names, n=3, cutoff=FUZZY_THRESHOLD)
        close = [m for m in close if m.lower() != name.lower()]
        for m in close:
            ratio = difflib.SequenceMatcher(None, name.lower(), m.lower()).ratio()
            proposed.append({"candidate": name, "possible_match": m,
                             "similarity": round(ratio, 3), "applied": False,
                             "reason_not_applied":
                                 "fuzzy matching proposes only; a human confirms in people.yaml"})

    # ---------------- other types -------------------------------------------
    for t, items in by_type.items():
        if t == T_PERSON:
            continue
        for c in items:
            canon = c["raw"].strip()
            nid = node_id(t, c["norm"])
            node = resolved_nodes.setdefault(nid, {
                "id": nid, "type": t, "label": canon, "label_raw": canon,
                "sources": [], "sensitive": False, "file_count": 0,
            })
            node["sources"].extend(c["sources"])
            for k in ("workflow_id", "theme_id", "cadence", "stage", "doctype", "family"):
                if c.get(k) is not None and k not in node:
                    node[k] = c[k]

    for node in resolved_nodes.values():
        files = {s.get("file") for s in node["sources"] if s.get("file")}
        node["file_count"] = len(files)
        if node["type"] == T_INSTRUCTOR:
            node["cross_validated"] = len(files) >= 2
            node["roster_count"] = len(files)

    print("-" * 78)
    print("MERGES APPLIED  (people.yaml aliases — hand-confirmed)")
    print("-" * 78)
    seen = set()
    for a in applied:
        key = (a["from"].lower(), a["to"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  {a['from']!r:<34} -> {a['to']!r}   [{a['basis']}]")
    print(f"  {len(seen)} distinct alias merges applied")
    print()

    print("-" * 78)
    print("MERGES PROPOSED  (fuzzy — NONE APPLIED)")
    print("-" * 78)
    if not proposed:
        print("  none above threshold %.2f" % FUZZY_THRESHOLD)
    for p in proposed:
        print(f"  {p['candidate']!r:<30} ~ {p['possible_match']!r:<26} "
              f"sim={p['similarity']}  applied={p['applied']}")
    print(f"  {len(proposed)} proposed, 0 applied")
    print()

    REVIEW.write_text(yaml.safe_dump({
        "version": 1,
        "note": ("Fuzzy matches PROPOSED by pass 3. Nothing here is applied. "
                 "To accept one, add the string to that person's aliases in "
                 "people.yaml and re-run. Deleting a row here rejects it."),
        "threshold": FUZZY_THRESHOLD,
        "proposed_merges": proposed,
        "unresolved_names": unresolved_names,
    }, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")

    print("-" * 78)
    print(f"people-review.yaml — FULL CONTENT ({len(unresolved_names)} unresolved)")
    print("-" * 78)
    print(REVIEW.read_text(encoding="utf-8"))

    nodes = sorted(resolved_nodes.values(), key=lambda n: (n["type"], n["label"].lower()))
    RESOLVED.write_text(json.dumps({"nodes": nodes}, indent=1, sort_keys=True),
                        encoding="utf-8")

    print("-" * 78)
    print("RESOLVED NODES BY TYPE")
    print("-" * 78)
    counts = defaultdict(int)
    for n in nodes:
        counts[n["type"]] += 1
    for t in sorted(counts):
        print(f"  {t:<12} {counts[t]:>6}")
    print(f"  {'TOTAL':<12} {len(nodes):>6}")
    print()

    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        from datetime import datetime
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 03_resolve\n\n")
        fh.write(f"- Nodes {len(nodes)} | alias merges applied {len(seen)} | "
                 f"fuzzy proposed {len(proposed)} | applied 0\n")
    print(f"wrote {RESOLVED.name} ({len(nodes)} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
