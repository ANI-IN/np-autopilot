"""Parsing `Resource Collection Mastersheet (Software + System).xlsx`.

The sheet is STRUCTURED — module rows, session rows, a per-module instructor
block and an instructor table — so this is the evidence shape the graph already
trusts, and the opposite of the deck text D1 refuses. Nothing here reads a
slide.

Each domain tab has three sections and they are NOT separated by a blank line:
the per-module instructor block reuses `Week N - <name>` for its own rows, so a
regex over the whole tab counts every module twice in Frontend and Testing.
Sections are found by their headers, not by pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import mastersheet as ms                   # noqa: E402

from pipeline.lib import freshness                             # noqa: E402

# The LIVE sheet (owner decision 2026-09-30), exported outside the repo.
SHEET = freshness.live_path()
pytestmark = pytest.mark.skipif(
    not SHEET.exists(),
    reason="the live mastersheet is not fetched; run pipeline/fetch_mastersheet.py")


@pytest.fixture(scope="module")
def tabs():
    return {t: ms.parse_tab(SHEET, t) for t in ms.DOMAIN_TABS}


# ---------------------------------------------------------------------------
# Modules and the folder join
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tab,n", [
    ("Full Stack Engineering", 5), ("Frontend Engineering", 4),
    ("Backend Engineering", 5), ("Test Engineering", 6),
])
def test_each_tab_yields_its_modules_once(tabs, tab, n):
    """A whole-tab regex counts Frontend's 4 as 8 and Testing's 6 as 12,
    because the instructor block reuses `Week N - <name>`."""
    assert len(tabs[tab].modules) == n


def test_a_module_carries_its_sequence_name_and_uplevel_link(tabs):
    m = tabs["Backend Engineering"].modules[2]
    assert m.sequence == 3
    assert m.name == "API Design"
    assert m.uplevel_link.startswith("http")


def test_the_drive_folder_row_gives_the_row_b_folder(tabs):
    """The sheet states the join the crawler had to infer from paths."""
    assert tabs["Backend Engineering"].drive_folder == "SD3: Backend Engineering"
    assert tabs["Full Stack Engineering"].drive_folder == "IK: Full Stack: Content Repo"


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_a_module_has_its_sessions_with_kinds(tabs):
    kinds = [s.kind for s in tabs["Backend Engineering"].modules[2].sessions]
    assert kinds == ["pre_class", "class", "alternate_class", "task",
                     "review", "alternate_review",
                     "post_class"]


def test_a_session_kind_comes_from_the_NAME_not_only_the_type_column(tabs):
    """The `Type` column has four values; `Class` and `Alternate Class` are
    both `Live Class` there and are told apart by the resource NAME."""
    s = tabs["Backend Engineering"].modules[2].sessions
    alt = [x for x in s if x.kind == "alternate_class"]
    assert len(alt) == 1
    assert "Alternate" in alt[0].name


def test_every_session_keeps_its_uplevel_link(tabs):
    for t in tabs.values():
        for m in t.modules:
            for s in m.sessions:
                assert s.uplevel_link.startswith("http"), (m.name, s.name)


def test_test_engineering_has_no_post_class_sessions(tabs):
    """Measured, not assumed — it is a real difference between the domains."""
    kinds = {s.kind for m in tabs["Test Engineering"].modules for s in m.sessions}
    assert "post_class" not in kinds


# ---------------------------------------------------------------------------
# Instructors — the structured source, un-deferred
# ---------------------------------------------------------------------------

def test_each_module_has_a_primary_instructor_and_its_backups(tabs):
    a = tabs["Backend Engineering"].assignments_by_sequence[1]
    assert a["primary"] == ["Konstantinos"]
    assert a["backup_1"] == ["Robert Kreznarich"]
    assert a["backup_2"] == ["Shelby"]


def test_a_slash_cell_holds_two_people_and_becomes_two_primaries(tabs):
    """`Robert Kreznarich/Tilo Dickopp` is two instructors, not one whose name
    contains a slash."""
    a = tabs["Backend Engineering"].assignments_by_sequence[3]
    assert len(a["primary"]) == 2
    assert "Robert Kreznarich" in a["primary"]


def test_the_instructor_table_is_parsed_with_every_column(tabs):
    t = tabs["Backend Engineering"].instructors
    row = next(r for r in t if r["name"] == "Robert Kreznarich")
    assert row["years_experience"] and row["current_company"]
    assert row["linkedin_url"] and row["contact_email"]


def test_a_short_first_name_only_form_is_flagged_for_review(tabs):
    """`Shelby` and `Faraaz` are first names; the table has `Shelby Cohen` and
    `Faraaz Sareshwala`. That is a proposal, never an automatic merge."""
    assert ms.needs_people_review("Shelby") is True
    assert ms.needs_people_review("Robert Kreznarich") is False


# ---------------------------------------------------------------------------
# Contact data is separated AT PARSE TIME, not later
# ---------------------------------------------------------------------------

def test_contact_fields_are_returned_separately_from_public_ones(tabs):
    row = tabs["Backend Engineering"].instructors[0]
    public, private = ms.split_instructor_row(row)
    assert set(private) <= set(ms.SENSITIVE_FIELDS)
    for v in public.values():
        assert "@" not in str(v)


def test_no_public_instructor_field_carries_an_address_or_a_profile(tabs):
    for t in tabs.values():
        for row in t.instructors:
            public, _ = ms.split_instructor_row(row)
            blob = " ".join(str(v) for v in public.values())
            assert "@" not in blob
            assert "linkedin.com" not in blob.lower()


def test_contact_data_pasted_into_a_public_column_is_moved_not_published(tabs):
    """FOUND BY THE TEST ABOVE, on Test Engineering row 69: a row whose NAME
    column holds an email and a LinkedIn URL and no name at all.

    Neither silently dropping it (CLAUDE.md §4) nor publishing it is
    acceptable. The contact tokens move to the private side, what remains of
    the public field is kept, and the row is FLAGGED so a human sees it.
    """
    pub, priv = ms.split_instructor_row(
        # contact-ok: synthetic. A linkedin.com-shaped token is REQUIRED here —
        # `_CONTACT_TOKEN` keys on that host, so a reserved domain would make
        # the regex miss and the test would assert nothing. The claim IS that
        # this token moves off the public side.
        {"name": "someone@example.org https://www.linkedin.com/in/x/",
         "current_company": "Acme"})
    assert "@" not in " ".join(str(v) for v in pub.values())
    assert "linkedin.com" not in " ".join(str(v) for v in pub.values()).lower()
    assert priv.get("scrubbed_from_public")


def test_a_clean_row_is_not_flagged_as_scrubbed(tabs):
    """Negative control: the flag must mean something."""
    _, priv = ms.split_instructor_row({"name": "Robert Kreznarich",
                                       "current_company": "Sterling Wilson"})
    assert "scrubbed_from_public" not in priv


def test_a_row_left_with_no_usable_name_is_reported_not_ingested(tabs):
    pub, priv = ms.split_instructor_row(
        # contact-ok: synthetic, same reason as above — the host must be real
        # for `_CONTACT_TOKEN` to fire, and the assertion is that nothing
        # publishable survives.
        {"name": "someone@example.org https://www.linkedin.com/in/x/"})
    assert ms.is_unusable(pub) is True
    assert ms.is_unusable({"name": "Robert Kreznarich"}) is False
