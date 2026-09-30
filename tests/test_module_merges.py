"""The answered MOD rows, and the things a merge is most likely to lose.

A merge is destructive by nature: two nodes become one. Every assertion here
is about something that must SURVIVE that, because the failure mode is silent
— a merged graph looks complete whether or not it kept the evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import module_merge as mm                          # noqa: E402
from pipeline.lib import taxonomy                                    # noqa: E402

MAIN = REPO / "knowledge" / "graph.json"
CONTENT = REPO / "knowledge" / "content_graph.json"
pytestmark = pytest.mark.skipif(
    not (MAIN.exists() and CONTENT.exists()),
    reason="both graphs must be built; run pipeline/07_build_content_graph.py")


@pytest.fixture(scope="module")
def graphs():
    return (json.loads(MAIN.read_text(encoding="utf-8")),
            json.loads(CONTENT.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def merged(graphs):
    return mm.merge(*graphs)


def _mods(g):
    return [n for n in g["nodes"] if n["type"] == "module"]


def _mod(g, slug, seq):
    return next(n for n in _mods(g)
                if n.get("domain_slug") == slug and n.get("sequence") == seq)


# ---------------------------------------------------------------------------
# The explicit owner instruction on MOD-14
# ---------------------------------------------------------------------------

def _module_in_another_domain(main, avoid_family):
    """A module that genuinely REACHES a domain unlike `avoid_family`.

    Picking any module is not enough: most legacy modules have no domain edge
    at all, and a side with no domain reach is "cannot tell", not a conflict —
    which is precisely the distinction the check is built on. The first
    version of this fixture picked such a module and the mutation silently
    did nothing.
    """
    by_id = {n["id"]: n for n in main["nodes"]}
    dom_rel = taxonomy.edge_for_role("domain_module")
    for e in main["edges"]:
        if e["rel"] not in (dom_rel, "covers", "contains"):
            continue
        src, tgt = by_id.get(e["source"]), by_id.get(e["target"])
        if not src or not tgt or tgt["type"] != "module":
            continue
        fam = mm._family(src.get("label"))
        if fam and fam != avoid_family:
            return tgt
    raise AssertionError("no module reaching a different domain; fixture broken")


def test_automation_testing_and_test_automation_are_never_joined(merged):
    """MOD-14's condition, asserted rather than left to convention.

    `Automation Testing` (SD4/4) and `Test Automation` (SD4/5) are two
    modules whose labels are near-anagrams of each other. Any future
    normalise-and-match step would be very likely to pair them.
    """
    a = _mod(merged, "testing", 4)
    b = _mod(merged, "testing", 5)
    assert a["id"] != b["id"], "SD4/4 and SD4/5 were joined into one module"
    labels_a = {a.get("label"), *(a.get("merged_label_raw") or [])}
    labels_b = {b.get("label"), *(b.get("merged_label_raw") or [])}
    assert not (labels_a & labels_b), (
        f"SD4/4 and SD4/5 now share a label: {labels_a & labels_b}")


def test_the_never_join_rule_is_declared_in_the_spec_not_only_here():
    """A test asserting a rule the config does not state is a rule that
    disappears the moment someone regenerates the config."""
    spec = mm.load_spec()
    m14 = next(m for m in spec["merges"] if m["id"] == "MOD-14")
    assert m14.get("never_join") == {"domain": "testing", "sequence": 5}


# ---------------------------------------------------------------------------
# What a merge must not lose
# ---------------------------------------------------------------------------

def test_no_edge_is_dropped(graphs, merged):
    before = len(graphs[0]["edges"]) + len(graphs[1]["edges"])
    assert len(merged["edges"]) == before


def test_every_absorbed_label_survives_as_merged_label_raw(graphs, merged):
    """§1: a label is the citation key back to the source. It survives even
    when it is not the one displayed."""
    main = graphs[0]
    by_id = {n["id"]: n for n in main["nodes"]}
    kept = {lab for n in merged["nodes"] for lab in (n.get("merged_label_raw") or [])}
    for m in mm.load_spec()["merges"]:
        for legacy_id in m.get("legacy", []) + [s["legacy"] for s in m.get("sessions", [])]:
            original = by_id[legacy_id]
            lab = original.get("label_raw") or original.get("label")
            assert lab in kept, f"{m['id']}: lost the label {lab!r}"


def test_every_touched_edge_records_the_merge_that_moved_it(merged):
    """Reversibility. Without `mod_id` on the edge, undoing one merge means
    recomputing all of them."""
    moved = [e for e in merged["edges"] if "merged_from" in e]
    assert moved, "no edge was retargeted; the merge did nothing"
    untagged = [e for e in moved if not (e.get("mod_id") or e.get("ins_id"))]
    assert not untagged, (
        f"{len(untagged)} retargeted edges carry no review id, so the merge "
        "that moved them cannot be reversed")
    # Any answered REVIEW-QUEUE group, not just the two that existed when this
    # was written. PPL-11 ("Bharath" is Bharath Anand) is a confirmed identity
    # and moves edges exactly as an INS row does.
    GROUPS = ("MOD-", "INS-", "PPL-", "TOPv-", "TOPm-", "TOPt-", "DCK-")
    for e in moved:
        rid = e.get("mod_id") or e.get("ins_id")
        assert rid.startswith(GROUPS), f"unrecognised review id on an edge: {rid}"


def test_provenance_is_unioned_not_replaced(graphs, merged):
    main_by_id = {n["id"]: n for n in graphs[0]["nodes"]}
    spec = mm.load_spec()
    m = next(x for x in spec["merges"] if x["id"] == "MOD-09")
    legacy = main_by_id[m["legacy"][0]]
    tgt = _mod(merged, "backend", 3)
    assert len(tgt.get("sources", [])) >= len(legacy.get("sources", []))


# ---------------------------------------------------------------------------
# Evidence tiers — the staffing rule
# ---------------------------------------------------------------------------

def test_the_two_staffing_tiers_are_tagged_and_kept_apart(merged):
    """CLAUDE.md §4 one level up: a legacy `teaches` and a mastersheet
    `taught_by` are two claims by two unreconciled sources. Collapsing them
    would manufacture agreement."""
    tiers = {e.get("tier") for e in merged["edges"] if e.get("tier")}
    assert tiers == {mm.TIER_LEGACY, mm.TIER_MASTERSHEET}
    legacy_rel = taxonomy.edge_for_role("instructor_module")
    sheet_rel = taxonomy.edge_for_role("module_instructor")
    assert legacy_rel != sheet_rel
    for e in merged["edges"]:
        if e.get("tier") == mm.TIER_LEGACY:
            assert e["rel"] == legacy_rel
        elif e.get("tier") == mm.TIER_MASTERSHEET:
            assert e["rel"] == sheet_rel


def test_mod_01_keeps_the_tiers_apart(merged):
    """MOD-01 merged the legacy module into SD1/1. The legacy instructors stay
    legacy-tier; the mastersheet roles are the sheet's own.

    CORRECTED 2026-09-30: this test used to assert the mastersheet cell was
    BLANK. It never was — `Week 1/5: Databases` was skipped by the parser, and
    the test pinned the bug."""
    m = _mod(merged, "full-stack", 1)
    N = {n["id"]: n for n in merged["nodes"]}
    sheet = sorted((e.get("instructor_role"), N[e["target"]]["label"]) for e in merged["edges"]
                   if e.get("tier") == mm.TIER_MASTERSHEET and e["source"] == m["id"])
    legacy = [e for e in merged["edges"]
              if e.get("tier") == mm.TIER_LEGACY
              and m["id"] in (e["source"], e["target"])]
    assert sheet == [("backup_1", "Ashish Kaila"), ("backup_2", "Nikhil Kolekar"),
                     ("primary", "Konstantinos Pappas")]
    assert legacy, "the legacy instructors were lost"
    assert not any(e.get("instructor_role") for e in legacy), "a legacy edge wears a sheet role"


# ---------------------------------------------------------------------------
# MOD-04 — kept, not asserted
# ---------------------------------------------------------------------------

def test_mod_04_legacy_programme_edges_survive_marked_unconfirmed(merged):
    m = _mod(merged, "frontend", 2)
    kept = [e for e in merged["edges"]
            if e.get("mod_id") == "MOD-04" and e.get("confirmed") is False]
    assert kept, "the legacy Full-Stack programme edges were deleted"
    for e in kept:
        assert m["id"] in (e["source"], e["target"])


# ---------------------------------------------------------------------------
# MOD-15 — sessions, not the module
# ---------------------------------------------------------------------------

def test_mod_15_legacy_session_rows_land_on_sessions_not_the_module(merged):
    m = _mod(merged, "testing", 5)
    assert "MOD-15" in (m.get("merge_ids") or [])
    absorbed_elsewhere = [n for n in merged["nodes"]
                          if "MOD-15" in (n.get("merge_ids") or [])
                          and n["type"] != "module"]
    assert len(absorbed_elsewhere) == 2, (
        "the two legacy `... Class` rows should land on SD4/5's class and "
        "review sessions, not on the module")


# ---------------------------------------------------------------------------
# Identity: confirmed merges, unconfirmed ones do NOT
# ---------------------------------------------------------------------------

def test_a_confirmed_instructor_alias_is_merged(merged):
    labs = [n for n in merged["nodes"] if n["type"] == "instructor"
            and (n.get("label") or "").strip().lower() == "balaram velega"]
    assert not labs, "the alias spelling is still a separate instructor node"
    canon = [n for n in merged["nodes"] if n["type"] == "instructor"
             and (n.get("label") or "").strip() == "Balaram Velaga"]
    assert len(canon) == 1
    assert "Balaram Velega" in (canon[0].get("merged_label_raw") or []), (
        "§1: the alias spelling must survive as evidence")


# Owner answers of 2026-09-30 (checklist review, docs/REVIEW-QUEUE.md): the
# first-name and short forms are the same people. They SUPERSEDE the
# 2026-09-29 "left apart" answers these tests used to hold.
CONFIRMED_ALIASES = {
    "Konstantinos Pappas": "Konstantinos", "Shelby Cohen": "Shelby",
    "William David Ogden": "Bill Ogden", "Faraaz Sareshwala": "Faraaz",
    "Cathy Ma": "Cathy", "Nisarg Tanna": "Nisarg", "Robert Kreznarich": "Robert K",
    "Reginald Johnson": "Reginald",        # PPL-13, part 3 — supersedes PPL-09's "unresolved"
}


def test_a_confirmed_alias_is_merged_and_kept_as_a_citation_key(merged):
    labels = {(n.get("label") or "").strip() for n in merged["nodes"]
              if n["type"] == "instructor"}
    for full, alias in CONFIRMED_ALIASES.items():
        assert alias not in labels, f"{alias} still stands apart from {full}"
        hits = [n for n in merged["nodes"] if n["type"] == "instructor"
                and n.get("label") == full]
        assert len(hits) == 1, f"{full}: {len(hits)} nodes"
        raws = {hits[0].get("label_raw"), *(hits[0].get("merged_label_raw") or [])}
        assert alias in raws, f"{alias} lost as a citation key on {full}"


def test_the_merged_person_keeps_both_evidence_tiers_apart(merged):
    """Merging a PERSON never merges a legacy `teaches` claim into a
    mastersheet role."""
    kp = next(n for n in merged["nodes"] if n["type"] == "instructor"
              and n.get("label") == "Konstantinos Pappas")
    tiers = {e.get("tier") for e in merged["edges"]
             if kp["id"] in (e["source"], e["target"]) and e.get("tier")}
    assert mm.TIER_MASTERSHEET in tiers
    ms_edges = [e for e in merged["edges"] if kp["id"] in (e["source"], e["target"])
                and e.get("tier") == mm.TIER_MASTERSHEET]
    assert ms_edges, "Konstantinos Pappas lost the first-name form's module rows"


def test_no_identity_is_left_unconfirmed(merged):
    """PPL-13 confirmed Reginald; no instructor carries identity_unconfirmed."""
    assert not [n["label"] for n in merged["nodes"] if n.get("identity_unconfirmed")]


def test_no_instructor_label_remains_duplicated(merged):
    """32 -> 4 after the INS bulk; 4 -> 0 after the 2026-09-30 answers."""
    import collections
    c = collections.Counter((n.get("label") or "").strip()
                            for n in merged["nodes"] if n["type"] == "instructor")
    assert not {k for k, v in c.items() if v > 1}


def test_the_bulk_safeguard_excluded_nothing_and_says_so(merged):
    """0 exclusions is a RESULT, not an absence of checking. It is asserted so
    that a check which silently stops running is visible."""
    assert merged["meta"]["excluded_pairs"] == []


def test_the_conflict_check_CAN_exclude_a_pair(graphs):
    """Mutation: give one side of a merged pair a wholly different domain and
    the pair must be excluded. Without this, the 0 above proves nothing."""
    import copy
    main, content = copy.deepcopy(graphs[0]), copy.deepcopy(graphs[1])
    # Tilo Dickopp reaches `backend` from both sides. Re-point the main-graph
    # node's teaching onto a module in an unrelated domain.
    tilo = next(n for n in main["nodes"] if n["type"] == "instructor"
                and n.get("label") == "Tilo Dickopp")
    rel = taxonomy.edge_for_role("instructor_module")
    alien = _module_in_another_domain(main, "backend")
    main["edges"] = [e for e in main["edges"]
                     if not (e["rel"] == rel and e["source"] == tilo["id"])]
    main["edges"].append({"rel": rel, "source": tilo["id"], "target": alien["id"],
                          "sources": [{"origin": "hand", "evidence": "mutation"}]})
    out = mm.merge(main, content)
    excluded = {x["id"] for x in out["meta"]["excluded_pairs"]}
    assert excluded, "the conflict check excluded nothing when domains diverged"


def test_an_excluded_pair_is_never_silently_merged(graphs):
    """The exclusion must actually prevent the merge, not just log it."""
    import copy
    main, content = copy.deepcopy(graphs[0]), copy.deepcopy(graphs[1])
    tilo = next(n for n in main["nodes"] if n["type"] == "instructor"
                and n.get("label") == "Tilo Dickopp")
    rel = taxonomy.edge_for_role("instructor_module")
    alien = _module_in_another_domain(main, "backend")
    main["edges"] = [e for e in main["edges"]
                     if not (e["rel"] == rel and e["source"] == tilo["id"])]
    main["edges"].append({"rel": rel, "source": tilo["id"], "target": alien["id"],
                          "sources": [{"origin": "hand", "evidence": "mutation"}]})
    out = mm.merge(main, content)
    if any(x["canonical"] == "Tilo Dickopp" for x in out["meta"]["excluded_pairs"]):
        hits = [n for n in out["nodes"] if n["type"] == "instructor"
                and (n.get("label") or "").strip() == "Tilo Dickopp"]
        assert len(hits) == 2, "an excluded pair was merged anyway"


def test_absence_of_evidence_is_not_treated_as_a_conflict(merged):
    """9 pairs had domain evidence on only one side. They merged, because
    "I cannot tell" and "they differ" are different answers."""
    for lab in ("Shelby Cohen", "Rushi Vyas", "Nisarg Tanna"):
        hits = [n for n in merged["nodes"] if n["type"] == "instructor"
                and (n.get("label") or "").strip() == lab]
        assert len(hits) == 1, f"{lab} was excluded for having no evidence"


# ---------------------------------------------------------------------------
# The outcome
# ---------------------------------------------------------------------------

# Adopting the mastersheet names (TOPv/TOPm, 2026-09-30) made two row-B
# modules collide with legacy modules of the same name. MOD-17/18, answered
# the same day: KEEP SEPARATE (config/module-merges.yaml `kept_separate`).
def test_the_only_duplicate_module_labels_are_the_ones_kept_separate(merged):
    import collections
    kept = mm.yaml.safe_load(mm.MERGES_FILE.read_text(encoding="utf-8"))["kept_separate"]
    assert {k["id"] for k in kept} == {"MOD-17", "MOD-18"}
    assert all(k["origin"] == "hand" and k["decided_by"] for k in kept)
    c = collections.Counter((n.get("label") or "").strip().lower()
                            for n in _mods(merged))
    assert {k for k, v in c.items() if v > 1} == {k["label"].lower() for k in kept}
    ids = {n["id"] for n in _mods(merged)}
    assert all(k["legacy"] in ids for k in kept), "a kept-separate legacy node was merged away"
