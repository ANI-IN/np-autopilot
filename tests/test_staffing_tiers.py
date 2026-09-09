"""B9: a staffing result must never rank declared expertise above teaching history.

The tiering is the command's correctness requirement, not its presentation. This
test exists so a future refactor cannot quietly undo it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.query import coverage, staffing                          # noqa: E402
from pipeline.lib.resolve import Ambiguous, resolve                    # noqa: E402

DOMAINS = ["Backend", "TPM", "Fullstack", "Security", "Cloud", "Frontend"]


@pytest.mark.parametrize("dom", DOMAINS)
def test_taught_and_declared_are_separate_collections(dom):
    r = staffing(dom)
    assert "taught" in r and "declared" in r
    taught_names = {x["name"] for x in r["taught"]}
    declared_names = {x["name"] for v in r["declared"].values() for x in v}
    # A name with teaching history must NEVER also appear in a declared tier;
    # that is how a form response gets laundered into evidence.
    assert not (taught_names & declared_names), (
        f"{dom}: {sorted(taught_names & declared_names)} appear in BOTH tiers"
    )


@pytest.mark.parametrize("dom", DOMAINS)
def test_every_taught_row_names_its_source_sheet(dom):
    for row in staffing(dom)["taught"]:
        assert row.get("source"), f"{dom}: {row['name']} has no source file"
        assert row.get("source_sheet"), f"{dom}: {row['name']} has no source sheet"


@pytest.mark.parametrize("dom", DOMAINS)
def test_taught_is_ordered_by_recency_then_volume(dom):
    rows = staffing(dom)["taught"]
    keys = [(r["last_taught"] or "", r["sessions_past"]) for r in rows]
    assert keys == sorted(keys, reverse=True), f"{dom}: taught tier is not ranked"


def test_owner_confirmed_no_instructor_domains_return_no_names():
    for dom in ("Android", "iOS"):
        r = staffing(dom)
        assert r["no_instructors_confirmed"] is True
        assert r["taught"] == [], f"{dom} must return no taught names"
        assert not any(r["declared"].values()), f"{dom} must return no declared names"


def test_coverage_never_reports_workflows_as_missing_an_owner():
    c = coverage()
    assert "OUT OF SCOPE" in c["workflow_ownership"]
    # Check the reported GAP LISTS, not the prose — the prohibition text itself
    # legitimately contains the phrase it forbids reporting.
    gap_lists = [v for k, v in c.items()
                 if isinstance(v, list) and k != "excluded_from_report_by_owner_confirmation"]
    for lst in gap_lists:
        assert not any("workflow" in str(x).lower() for x in lst), \
            f"a workflow appears in a coverage gap list: {lst}"


def test_coverage_excludes_owner_confirmed_domains_from_the_gap_list():
    c = coverage()
    for dom in ("Android", "iOS"):
        assert dom not in c["domains_with_modules_but_no_teaching"]
        assert dom in c["excluded_from_report_by_owner_confirmation"]


def test_ambiguity_is_returned_not_guessed():
    labels = ["Machine Learning (IP course)", "Flagship ML/ ML Program",
              "ML Switch-up (Adv ML)", "Advanced ML Ops"]
    r = resolve("ML", labels)
    assert isinstance(r, Ambiguous), "ML must not resolve to one domain"
    assert len(r.candidates) > 1
    # and a genuinely unique name still resolves
    assert resolve("Advanced ML Ops", labels) == "Advanced ML Ops"
