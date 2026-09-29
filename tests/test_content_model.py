"""Phase 3 — the content model's invariants, before the extractor exists.

Every rule here is an owner decision from Phases 0-2 or a standing rule from
`CLAUDE.md`. They are tested at the level of pure functions so the pass script
stays a thin caller — the same shape as `lib/content_scope.py` for the crawl.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import content_model as cm             # noqa: E402
from pipeline.lib import curriculum as cur               # noqa: E402


# ---------------------------------------------------------------------------
# Module identity — (domain_slug, sequence), never the label
# ---------------------------------------------------------------------------

def test_a_module_folder_yields_a_domain_and_a_sequence():
    got = cm.parse_module("/SD3: Backend Engineering/Module-3: API Design/"
                          "2. Live Class Slides/deck.pptx")
    assert got.domain == "SD3: Backend Engineering"
    assert got.sequence == 3
    assert got.label == "API Design"


@pytest.mark.parametrize("path,seq,label", [
    ("/SD1: Full Stack/IK: Full Stack: Content Repo/"
     "2. Module - API Design and Implementation - Content/x", 2,
     "API Design and Implementation"),
    ("/SD2: Frontend/IK: Frontend Content Repo/Week 3/4 - Frontend System Design/x",
     3, "Frontend System Design"),
    ("/SD4: Test Engineering/IK Test Engineering: Content Repo/Week 6/"
     "6 - Cloud Testing/x", 6, "Cloud Testing"),
    ("/SD3: Backend Engineering/Module-1: Database Design/Uplevel shared/"
     "Week 3/5 - API Design/Slides/d.pptx", 3, "API Design"),
])
def test_every_domain_shape_resolves_to_a_sequence(path, seq, label):
    got = cm.parse_module(path)
    assert (got.sequence, got.label) == (seq, label)


def test_sd3s_nested_uplevel_tree_does_not_file_everything_under_module_1():
    """All five Backend week folders sit under `Module-1: Database Design`.
    A parent-path rule files every Backend module under Database Design."""
    got = cm.parse_module("/SD3: Backend Engineering/Module-1: Database Design/"
                          "Uplevel shared/Week 5/5 - Concurrency/Slides/x.pptx")
    assert got.sequence == 5 and got.label == "Concurrency"


def test_a_path_with_no_module_folder_yields_nothing():
    """Negative control: `Additional Docs` is not a module."""
    assert cm.parse_module("/SD1: Full Stack/Additional Docs/Full Stack Topics") is None


# ---------------------------------------------------------------------------
# Curriculum docs and their kinds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,kind", [
    ("Intro to Course - Front-EndEngineering - KYP Doc.pdf", "kyp"),
    ("Test Engineering: Handbook", "handbook"),
    ("Full Stack Course Outline v2", "outline"),
    ("Lesson Plan 2 - UI & DOM", "lesson_plan"),
    ("Backend: Lesson plans", "lesson_plan"),
])
def test_curriculum_documents_are_classified_by_kind(name, kind):
    assert cm.curriculum_kind(name) == kind


def test_an_ordinary_deck_is_not_a_curriculum_document():
    assert cm.curriculum_kind("Databases Live Class - Ashish.pdf") is None


# ---------------------------------------------------------------------------
# Program week — curriculum doc or the owner fact, never arithmetic
# ---------------------------------------------------------------------------

def test_sd1_program_weeks_come_from_the_owner_fact_and_are_hand_origin():
    w = cm.program_week_for("full-stack", 2)
    assert w.value == 10                      # modules 1-5 -> weeks 9-13
    assert w.source_kind == "hand"
    assert "Animesh Kumar" in w.source_file


def test_sd3_has_no_program_week_and_reports_a_gap():
    assert cm.program_week_for("backend", 3) is None


def test_no_program_week_is_ever_computed_from_a_folder_sequence():
    with pytest.raises(cur.ArithmeticWeekRefused):
        cur.program_week_from_local(local=3, offset=8)


# ---------------------------------------------------------------------------
# Attachment: everything hangs off the MODULE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,kind", [
    ("/D/Module-3: API Design/2. Live Class Slides/deck.pptx", "live_class"),
    ("/D/Module-3: API Design/3. Assignments/API Assignment", "assignment"),
    ("/D/Module-5: X/3. Assignment/Assignment Review/notes.md", "assignment_review"),
    ("/D/Module-1: X/1. Foundation Materials/intro", "foundation"),
])
def test_files_are_attached_by_the_folder_that_names_their_role(path, kind):
    assert cm.role_of(path) == kind


def test_a_deck_is_recognised_by_mime_not_by_folder():
    assert cm.is_deck("application/vnd.google-apps.presentation") is True
    assert cm.is_deck("application/vnd.google-apps.document") is False


# ---------------------------------------------------------------------------
# Topics — lesson plans first, then decks/docs, always with a locator
# ---------------------------------------------------------------------------

def test_a_topic_from_a_deck_carries_its_slide_number():
    text = "[slide 4]\nREST constraints\nHATEOAS and statelessness"
    got = cm.topics_from_text(text, source="deck")
    assert got
    assert all(t.locator_kind == "slide" for t in got)
    assert got[0].locator == 4


def test_a_topic_from_a_pdf_carries_its_page_number():
    got = cm.topics_from_text("[page 7]\nNormalisation and BCNF", source="doc")
    assert got[0].locator_kind == "page" and got[0].locator == 7


def test_a_topic_with_no_locator_is_refused_rather_than_guessed():
    """A topic that cannot cite where it came from is not evidence."""
    assert cm.topics_from_text("REST constraints", source="deck") == []


def test_topics_are_scoped_to_their_module_not_global():
    a = cm.topic_key("backend", 3, "API Design")
    b = cm.topic_key("testing", 3, "API Design")
    assert a != b


# ---------------------------------------------------------------------------
# D1 — a deck never yields a person, whatever it says
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "Instructor: Micah Jaffe",
    "IK: Technical Mentor - Roland Kunkel",
    "Introduction - Julie Wilkins, Senior Product Manager, Amazon",
    "Hello, my name is Roland and I've worked as a test engineer",
])
def test_deck_text_never_produces_a_person_node(line):
    text = f"[slide 1]\n{line}"
    assert cm.people_from_text(text) == []


# ---------------------------------------------------------------------------
# Download-disabled files are nodes, marked, never dropped
# ---------------------------------------------------------------------------

def test_a_download_disabled_file_becomes_a_marked_node():
    row = {"path": "/D/Module-3: API Design/2. Live Class Slides/x.pptx",
           "name": "x.pptx", "rule": "download-disabled-by-owner",
           "action": "metadata_only",
           "mime": "application/vnd.openxmlformats-officedocument."
                   "presentationml.presentation"}
    n = cm.node_for_unavailable(row)
    assert n["content_available"] is False
    assert "download disabled by owner" in n["unavailable_reason"]


def test_an_unavailable_node_is_never_given_inferred_content():
    row = {"path": "/D/Module-3: API Design/x.pptx", "name": "x.pptx",
           "rule": "download-disabled-by-owner", "action": "metadata_only",
           "mime": "application/pdf"}
    n = cm.node_for_unavailable(row)
    assert "text" not in n and "topics" not in n


# ---------------------------------------------------------------------------
# Revamp currency — the owner fact, and the one left ambiguous
# ---------------------------------------------------------------------------

def test_a_revamp_subtree_is_marked_superseded():
    assert cm.revision_of("/D/Module-3: API Design/Revamp 2024/x") == "revamp"
    assert cm.revision_of("/D/Module-3: API Design/2. Live Class Slides/x") == "base"


def test_the_concurrency_updated_content_folder_is_left_ambiguous():
    """It sits INSIDE the base live-class folder, not beside the numbered
    units, so it has no sibling base to point at."""
    p = ("/SD3: Backend Engineering/Module-5: Concurrency/2. Live Class Slides/"
         "Updated Content - Aug 2023/x.pptx")
    assert cm.revision_of(p) == "ambiguous"


# ---------------------------------------------------------------------------
# Provenance — every node carries one, and it never holds an address
# ---------------------------------------------------------------------------

def test_every_node_carries_a_file_and_an_origin():
    row = {"path": "/D/Module-3: API Design/2. Live Class Slides/d.pptx",
           "name": "d.pptx", "mime": "application/pdf", "action": "export",
           "owner_domain": "gmail.com"}
    src = cm.provenance(row)
    assert src["file"] and src["origin"] == "corpus"
    assert "@" not in str(src)
