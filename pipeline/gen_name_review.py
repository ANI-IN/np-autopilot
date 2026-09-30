"""Write config/instructor-name-review.yaml — the NAM rows of REVIEW-QUEUE.

Instructor labels from the OLDER sheets whose shape cannot be one person's
name (pipeline/lib/name_review.py). REPORTED ONLY: nothing is renamed, split
or removed until the owner answers a row (owner review 2026-09-30).

    python3 pipeline/gen_name_review.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml                                                              # noqa: E402

from pipeline.lib import graphio, name_review                           # noqa: E402
from pipeline.lib.paths import CONFIG_DIR                               # noqa: E402

OUT = CONFIG_DIR / "instructor-name-review.yaml"


def rows(g: dict) -> list[dict]:
    current = set()
    for e in g["edges"]:
        if e.get("tier") == "mastersheet":
            current |= {e["source"], e["target"]}
    found = []
    for n in g["nodes"]:
        if n["type"] != "instructor" or n["id"] in current:
            continue
        why = name_review.reasons(n["label"])
        if why:
            found.append({
                "label": n["label"],
                "node": n["id"],
                "reasons": why,
                "recommend": "; ".join(name_review.RECOMMEND[w] for w in why),
                "files": sorted({s["file"] for s in n.get("sources", []) if s.get("file")}),
                "answer": None,
            })
    found.sort(key=lambda r: r["label"].casefold())
    for i, r in enumerate(found, 1):
        r["id"] = f"NAM-{i:02d}"
    return found


def main() -> int:
    found = rows(graphio.load_merged())
    doc = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rule": "pipeline/lib/name_review.py — reported only, never applied",
           "rows": [{k: r[k] for k in ("id", "label", "node", "reasons",
                                      "recommend", "files", "answer")} for r in found]}
    OUT.write_text("# Instructor labels that are not one person's name (NAM).\n"
                   "# Owner review 2026-09-30: queued for later, NOT changed now.\n"
                   + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    print(f"  {len(found)} NAM rows -> {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
