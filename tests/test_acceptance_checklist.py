"""docs/ACCEPTANCE-CHECKLIST.md lists EVERY attached file, by its full name.

The owner ticks each module against the mastersheet (ACCURACY-STANDARD §4),
so a link missing from the checklist is a link nobody checks. It listed the
first three per session, each cut to 34 characters, with no count — API
Design's Class row showed 3 of 13 decks. Held to the graph, not to a count.
"""
from __future__ import annotations

import collections
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, taxonomy                            # noqa: E402

CHECKLIST = REPO / "docs" / "ACCEPTANCE-CHECKLIST.md"


def _attached_by_module():
    g = graphio.load_merged(include_sensitive=False)
    rel = taxonomy.edge_for_role("module_session")
    mods = {n["id"]: n for n in g["nodes"]
            if n["type"] == "module" and n.get("domain_slug")}
    out = collections.defaultdict(list)
    for e in g["edges"]:
        if e["rel"] == rel and e["source"] in mods and e.get("attached_file"):
            out[e["source"]].append(e["attached_file"].replace("|", "/"))
    return mods, out


def test_the_committed_checklist_is_current():
    before = CHECKLIST.read_text(encoding="utf-8")
    subprocess.run([sys.executable, "pipeline/gen_acceptance_checklist.py"],
                   cwd=REPO, check=True, capture_output=True)
    after = CHECKLIST.read_text(encoding="utf-8")
    CHECKLIST.write_text(before, encoding="utf-8")        # never dirty the tree
    assert before == after, "regenerate: python3 pipeline/gen_acceptance_checklist.py"


def test_every_attached_file_appears_by_its_full_name():
    text = CHECKLIST.read_text(encoding="utf-8")
    mods, attached = _attached_by_module()
    blocks = {b.split("\n", 1)[0]: b for b in text.split("\n## ")[1:]}
    missing = []
    for mid, names in attached.items():
        head = next((h for h in blocks if h.endswith(" · " + mods[mid]["label"])), None)
        assert head, f"no checklist block for {mods[mid]['label']}"
        missing += [(mods[mid]["label"], n) for n in names if f"[{n}]" not in blocks[head]
                    and n not in blocks[head]]
    assert not missing, f"{len(missing)} attached files absent: {missing[:5]}"
    assert sum(map(len, attached.values())) > 20, "vacuous: too few attached files"
