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
    # instructor-alias moves carry merged_from without a mod_id, by design:
    # they belong to an INS row, recorded on the node.
    module_moves = [e for e in moved if e.get("mod_id")]
    assert len(module_moves) >= len(moved) - 60
    for e in module_moves:
        assert e["mod_id"].startswith("MOD-")


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


def test_mod_01_keeps_its_legacy_instructors_without_inventing_a_sheet_role(merged):
    """The mastersheet cell is blank. The legacy tier must not fill it."""
    m = _mod(merged, "full-stack", 1)
    sheet = [e for e in merged["edges"]
             if e.get("tier") == mm.TIER_MASTERSHEET
             and m["id"] in (e["source"], e["target"])]
    legacy = [e for e in merged["edges"]
              if e.get("tier") == mm.TIER_LEGACY
              and m["id"] in (e["source"], e["target"])]
    assert not sheet, "a mastersheet role appeared where the source cell is blank"
    assert legacy, "the legacy instructors were lost"


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


def test_an_unconfirmed_identity_is_NOT_merged(merged):
    """INS-08/30 were answered 'unsure'. That answer must hold.

    TWO nodes each, not one, and that is the correct outcome: these labels
    occur in BOTH graphs, and the INS row asks whether the two are the same
    person. Answering "unsure" leaves them apart. A test asserting one node
    would be asserting the merge the owner declined.
    """
    for lab in ("Bill Ogden", "William David Ogden"):
        hits = [n for n in merged["nodes"] if n["type"] == "instructor"
                and (n.get("label") or "").strip() == lab]
        assert len(hits) == 2, (
            f"{lab}: expected the cross-graph pair to stay separate, got "
            f"{len(hits)}")
        assert not any(h.get("merge_ids") for h in hits), (
            f"{lab} was merged despite an unconfirmed identity")


def test_first_name_forms_keep_their_module_attachments(merged):
    """INS-31/32: moving real modules onto an unconfirmed full name would
    attach them to a guess."""
    for lab in ("Konstantinos", "Shelby"):
        hits = [x for x in merged["nodes"] if x["type"] == "instructor"
                and (x.get("label") or "").strip() == lab]
        assert hits, f"{lab} disappeared"
        attached = [e for e in merged["edges"]
                    if e.get("tier") == mm.TIER_MASTERSHEET
                    and any(n["id"] in (e["source"], e["target"]) for n in hits)]
        assert attached, f"{lab} lost its module rows"


def test_the_unanswered_INS_bulk_is_visible_as_remaining_duplicates(merged):
    """NOT a failure — a measurement, asserted so it cannot drift silently.

    26 exact-full-name INS rows were offered for bulk confirmation and have
    not been answered, so those instructors are still two nodes each. If a
    later change merged them without an answer, this goes red.
    """
    import collections
    c = collections.Counter((n.get("label") or "").strip().lower()
                            for n in merged["nodes"] if n["type"] == "instructor")
    dupes = {k for k, v in c.items() if v > 1}
    assert len(dupes) == 30, (
        f"{len(dupes)} duplicated instructor labels; expected 30 while the "
        "INS bulk is unanswered (26 bulk rows + the 4 answered 'leave apart')")
    assert "balaram velega" not in dupes and "balaram velaga" not in dupes


# ---------------------------------------------------------------------------
# The outcome
# ---------------------------------------------------------------------------

def test_no_duplicate_module_labels_remain(merged):
    import collections
    c = collections.Counter((n.get("label") or "").strip().lower()
                            for n in _mods(merged))
    assert not {k: v for k, v in c.items() if v > 1}
