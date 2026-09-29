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


# --- the full §D.4 block, each part held to the graph ------------------------

def _graph():
    g = graphio.load_merged(include_sensitive=False)
    N = {n["id"]: n for n in g["nodes"]}
    mods = [n for n in g["nodes"] if n["type"] == "module" and n.get("domain_slug")]
    return g, N, mods


def _blocks():
    text = CHECKLIST.read_text(encoding="utf-8")
    return {b.split("\n", 1)[0].split(" · ", 1)[1]: b for b in text.split("\n## ")[1:]}


def _md(s):
    return str(s or "").replace("|", "/").replace("\n", " ")


def test_every_module_has_a_block_with_an_owner_tickbox():
    _, _, mods = _graph()
    blocks = _blocks()
    assert len(blocks) == len(mods) == 20
    assert all("- [ ] **Owner check**" in b for b in blocks.values())


def test_programme_week_is_the_graphs_and_says_it_is_an_owner_fact():
    g, N, mods = _graph()
    rel = taxonomy.edge_for_role("module_week")
    blocks = _blocks()
    for m in mods:
        e = next(e for e in g["edges"] if e["rel"] == rel and e["source"] == m["id"])
        row = next(l for l in blocks[m["label"]].split("\n") if l.startswith("| Programme week |"))
        assert f"| {N[e['target']]['number']}" in row, (m["label"], row)
        if e.get("source_kind") == "hand":
            assert "owner fact" in row


def test_instructors_are_the_mastersheet_roles_and_nothing_else_in_that_table():
    g, N, mods = _graph()
    labels = collections.Counter(n["label"] for n in g["nodes"] if n["type"] == "instructor")
    blocks = _blocks()
    for m in mods:
        want = sorted((e.get("instructor_role"), N[e["target"]]["label"]) for e in g["edges"]
                      if e["source"] == m["id"] and e["rel"] == taxonomy.edge_for_role("module_instructor")
                      and e.get("tier") == "mastersheet")
        b = blocks[m["label"]]
        table = b.split("**Instructors — mastersheet", 1)[1].split("\n\n", 2)[1]
        rows = [l for l in table.split("\n") if l.startswith("| ") and "---" not in l
                and not l.startswith("| role")]
        assert len(rows) == len(want), (m["label"], rows, want)
        for role, name in want:
            hit = [r for r in rows if f"| {_md(name)}" in r]
            assert hit, (m["label"], name)
            assert (labels[name] > 1) == ("unconfirmed identity" in hit[0]), (m["label"], name)


def test_legacy_evidence_is_listed_separately_when_present():
    g, N, mods = _graph()
    blocks = _blocks()
    for m in mods:
        legacy = {N[e["source"]]["label"] for e in g["edges"] if e["target"] == m["id"]
                  and e.get("tier") == "legacy" and N[e["source"]]["type"] == "instructor"}
        b = blocks[m["label"]]
        if legacy:
            line = next(l for l in b.split("\n") if l.startswith("_Legacy evidence"))
            assert all(_md(x) in line for x in legacy), (m["label"], legacy)


def test_every_deck_assignment_and_other_file_is_linked():
    g, N, mods = _graph()
    R = {r: taxonomy.edge_for_role(r) for r in ("module_deck", "module_assignment",
                                                 "module_repo", "curriculum_module",
                                                 "module_class_file")}
    blocks = _blocks()
    missing = []
    for m in mods:
        b = blocks[m["label"]]
        want = [N[e["target"]] for e in g["edges"] if e["source"] == m["id"]
                and e["rel"] in (R["module_deck"], R["module_assignment"], R["module_repo"],
                                  R["module_class_file"])]
        want += [N[e["source"]] for e in g["edges"] if e["target"] == m["id"]
                 and e["rel"] == R["curriculum_module"]]
        for n in want:
            if n.get("drive_url") and f"]({n['drive_url']})" not in b:
                missing.append((m["label"], n["label"]))
        decks = sum(1 for e in g["edges"] if e["source"] == m["id"] and e["rel"] == R["module_deck"])
        assert f"**Decks ({decks})**" in b
    assert not missing, f"{len(missing)} links absent: {missing[:5]}"


def test_topics_state_how_many_there_are_and_show_five_real_ones():
    g, N, mods = _graph()
    rel = taxonomy.edge_for_role("module_topic")
    blocks = _blocks()
    for m in mods:
        # a person's name is not a topic (D1) and is held back from N
        mine = [N[e["target"]]["label"] for e in g["edges"] if e["source"] == m["id"]
                and e["rel"] == rel and not N[e["target"]].get("not_a_topic")]
        b = blocks[m["label"]]
        assert f"of {len(mine)} topics**" in b, m["label"]
        listed = [l for l in b.split("**Top", 1)[1].split("\n\n", 2)[1].split("\n")
                  if l[:2].rstrip(".").isdigit()]
        assert len(listed) == min(5, len(mine))
        assert all(any(l.startswith(f"{i}. {_md(t)} —") for t in mine)
                   for i, l in enumerate(listed, 1)), (m["label"], listed[:2])
