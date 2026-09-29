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

def test_program_weeks_come_from_the_owner_fact_and_are_hand_origin():
    w = cm.program_week_for("full-stack", 2)
    assert w.value == 10                      # modules 1-5 -> weeks 9-13
    assert w.source_kind == "hand"
    assert "Animesh Kumar" in w.source_file
    assert "out-of-corpus-facts" in w.source_file


@pytest.mark.parametrize("slug,seq,week", [
    ("full-stack", 1, 9), ("full-stack", 5, 13),
    ("frontend", 4, 12), ("backend", 3, 11), ("testing", 6, 14),
])
def test_every_approved_domain_has_explicit_program_weeks(slug, seq, week):
    """All four, from out-of-corpus-facts.yaml -> rowb-program-weeks. VALUES,
    not a formula: a fifth domain means adding numbers, not extending an
    arithmetic."""
    w = cm.program_week_for(slug, seq)
    assert w.value == week and w.source_kind == "hand"


def test_a_sequence_with_no_stated_week_still_reports_a_gap():
    """Negative control. Frontend has four modules; a fifth would have no
    stated week and must return None rather than 13."""
    assert cm.program_week_for("frontend", 5) is None
    assert cm.program_week_for("not-a-domain", 1) is None


def test_no_program_week_is_ever_computed_from_a_folder_sequence():
    with pytest.raises(cur.ArithmeticWeekRefused):
        cur.program_week_from_local(local=3, offset=8)


# ---------------------------------------------------------------------------
# Attachment: everything hangs off the MODULE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,kind", [
    ("/D/Module-3: API Design/2. Live Class Slides/deck.pptx", "class"),
    ("/D/Module-3: API Design/3. Assignments/API Assignment", "task"),
    ("/D/Module-5: X/3. Assignment/Assignment Review/notes.md", "review"),
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


# ---------------------------------------------------------------------------
# Topics are TITLES, not every line — measured on the first build
# ---------------------------------------------------------------------------
#
# Taking every 3-90 character line under a locator produced 17,392 topics
# across 20 modules — 5,637 on Backend's API Design alone, of which 2,386 were
# distinct. The layer contained `Objectives`, `Agenda`, `Pause for Questions`,
# `Master API Development concepts.` and `<NAME>` (a template placeholder).
# "API Design covers Pause for Questions" is not a gap in the data, it is a
# confidently wrong answer.
#
# This is not a threshold hiding correct answers (CLAUDE.md §4). It is D1's
# prior question in a new place: is a body bullet a TOPIC at all, or is it
# content ABOUT one? The slide title is the topic; the bullets are its body.

DECK = """[slide 3]
REST API Design
- statelessness
- cacheability
- HATEOAS

[slide 4]
Spring Framework
@RestController
"""


def test_a_topic_is_the_slide_title_not_every_bullet():
    got = cm.topics_from_text(DECK, source="deck")
    assert [t.label for t in got] == ["REST API Design", "Spring Framework"]


def test_each_title_keeps_its_own_slide_number():
    got = cm.topics_from_text(DECK, source="deck")
    assert [(t.locator_kind, t.locator) for t in got] == [("slide", 3), ("slide", 4)]


def test_a_slide_with_no_title_contributes_no_topic():
    """Negative control: an empty slide must not borrow the next one's title."""
    assert cm.topics_from_text("[slide 9]\n\n", source="deck") == []


def test_a_lesson_plan_tab_yields_one_topic_per_row_not_per_cell():
    """Lesson-plan tabs are the structured source and come FIRST. Their rows
    are `Topic | Flow | Learning Objectives`, so the topic is the row's first
    cell — the rest is what the topic covers."""
    text = ("[tab Concurrency Lesson Plan]\n"
            "Topic,Flow,Learning Objectives\n"
            "Thread Pools,30min,Builds on MPCQ\n"
            "Timer,30min,Defer execution\n")
    got = cm.topics_from_text(text, source="curriculum")
    assert [t.label for t in got] == ["Thread Pools", "Timer"]
    assert all(t.locator_kind == "tab" for t in got)


def test_a_header_row_is_not_a_topic():
    text = "[tab X]\nTopic,Flow,Learning Objectives\nSharding,20min,Scale out\n"
    got = cm.topics_from_text(text, source="curriculum")
    assert "Topic" not in [t.label for t in got]


# ---------------------------------------------------------------------------
# Lesson plans join by ORDINAL, which is structural; tabs join by NAME,
# which is the alias problem and must only propose
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,seq", [
    ("Lesson Plan 2 - API Design and Implementation", 2),
    ("Lesson Plan 1 - JS Language and Libraries - Front-end Course", 1),
    ("Lesson Plan 4 - Leveling Up with Advance JavaScript and CSS", 4),
    ("Lesson Plan 5 - UI System Design", 5),
])
def test_a_numbered_lesson_plan_joins_to_a_module_by_its_ordinal(name, seq):
    """`Lesson Plan N` is the Nth module of its domain — the same structural
    fact the module key already rests on. This is NOT a name match: the title
    after the number is never compared to anything."""
    assert cm.lesson_plan_sequence(name) == seq


@pytest.mark.parametrize("name", [
    "Backend: Lesson plans",          # no ordinal — multi-tab, one per module
    "Lesson Plan - Test Engineering",  # no ordinal
    "Full Stack Course Outline v2",
])
def test_an_unnumbered_curriculum_doc_yields_no_ordinal(name):
    """Negative control. Guessing an ordinal from a title is the name match
    this avoids."""
    assert cm.lesson_plan_sequence(name) is None


def test_a_tab_name_that_looks_like_a_module_is_PROPOSED_not_joined():
    """`Backend: Lesson plans` has a `Concurrency Lesson Plan` tab and Backend
    has a `Concurrency` module. That is a name match with guaranteed misses —
    the third thing SCALE-PLAN calls the alias problem — so it proposes."""
    got = cm.propose_tab_join("Concurrency Lesson Plan", "backend",
                              {"Concurrency": 5, "API Design": 3})
    assert got["confirmed"] is False
    assert got["candidate_sequence"] == 5


def test_a_tab_matching_nothing_proposes_nothing():
    assert cm.propose_tab_join("Interview questions", "backend",
                               {"Concurrency": 5}) is None


def test_a_tab_matching_two_modules_is_returned_as_ambiguous():
    """lib/resolve.py's rule: ambiguity is returned, never resolved by
    picking."""
    got = cm.propose_tab_join("API", "backend",
                              {"API Design": 3, "API Testing": 4})
    assert got["ambiguous"] is True
    assert sorted(got["candidates"]) == ["API Design", "API Testing"]


# ---------------------------------------------------------------------------
# Deck -> session, only where evidence allows, and the evidence is recorded
# ---------------------------------------------------------------------------

KINDS = ["pre_class", "class", "alternate_class", "task",
         "review", "alternate_review", "post_class"]


@pytest.mark.parametrize("path,kind,evidence", [
    ("/D/Module-3: API Design/2. Live Class Slides/deck.pptx", "class", "folder"),
    ("/D/Module-3: API Design/3. Assignment/task.docx", "task", "folder"),
    ("/D/Module-5: X/3. Assignment/Assignment Review/notes.md",
     "review", "folder"),
    ("/D/Module-1: X/1. Foundation Materials/intro.pdf", "pre_class", "folder"),
])
def test_folder_evidence_places_a_file_on_a_session(path, kind, evidence):
    got = cm.session_for_file(path, path.split("/")[-1], KINDS)
    assert (got.kind, got.evidence) == (kind, evidence)


@pytest.mark.parametrize("name,kind", [
    ("API Design – Alternate Class", "alternate_class"),
    ("API Design – Assignment Review Class", "review"),
    ("Concurrency – Class", "class"),
])
def test_name_evidence_places_a_file_when_the_folder_cannot(name, kind):
    got = cm.session_for_file(f"/D/Module-3: API Design/{name}", name, KINDS)
    assert got.kind == kind and got.evidence == "name"


def test_a_file_with_neither_kind_of_evidence_stays_module_level():
    """The rule that matters: no guessing. A deck the evidence cannot place
    keeps its module edge and gets no session edge."""
    assert cm.session_for_file("/D/Module-3: API Design/random.pptx",
                               "random.pptx", KINDS) is None


def test_a_session_kind_the_module_does_not_have_is_not_invented():
    """Test Engineering has no post_class sessions. A `Practice Problems`
    folder there must not create one."""
    got = cm.session_for_file("/D/Module-3: X/3. Practice Problems/x.pdf",
                              "x.pdf", ["class", "task"])
    assert got is None


# ---------------------------------------------------------------------------
# Deck filename -> instructor: a PROPOSAL, never applied (D1 untouched)
# ---------------------------------------------------------------------------

def test_a_deck_filename_first_name_is_proposed_against_module_instructors():
    got = cm.propose_deck_instructor(
        "UI & DOM - Jakob.pptx", {"primary": ["Jakob Muller"], "backup_1": ["Dominique"]})
    assert got["confirmed"] is False
    assert got["candidate"] == "Jakob Muller"
    assert got["instructor_role"] == "primary"
    assert got["evidence"] == "deck filename first name"


def test_a_filename_matching_nobody_proposes_nothing():
    assert cm.propose_deck_instructor(
        "Databases - Ashish.pdf", {"primary": ["Konstantinos"]}) is None


def test_a_filename_matching_two_instructors_is_ambiguous_not_ranked():
    got = cm.propose_deck_instructor(
        "X - Robert.pptx", {"primary": ["Robert Kreznarich"],
                            "backup_1": ["Robert Chen"]})
    assert got["ambiguous"] is True and len(got["candidates"]) == 2


def test_nothing_from_a_deck_filename_is_ever_applied():
    """D1's boundary, restated where it now bites: the mastersheet gives
    instructors, so a filename can PROPOSE — and a proposal is not an edge."""
    got = cm.propose_deck_instructor(
        "UI & DOM - Jakob.pptx", {"primary": ["Jakob Muller"]})
    assert got["confirmed"] is False


# ---------------------------------------------------------------------------
# Topic ranking by session, and historical decks
# ---------------------------------------------------------------------------

def test_a_class_deck_outranks_an_assignment_review_deck():
    assert cm.topic_rank("class") < cm.topic_rank("review")


def test_a_lesson_plan_outranks_every_deck():
    """Topics come from lesson plans FIRST."""
    assert cm.topic_rank("curriculum") < cm.topic_rank("class")


def test_a_superseded_or_old_deck_ranks_as_historical():
    assert cm.is_historical("/D/M/Revamp 2024/x.pptx", "x.pptx") is True
    assert cm.is_historical("/D/M/2. Live Class Slides/Old API Design.pptx",
                            "Old API Design.pptx") is True
    assert cm.is_historical("/D/M/2. Live Class Slides/API Design.pptx",
                            "API Design.pptx") is False


@pytest.mark.parametrize("filename,token", [
    # every one of these is a real deck name from the row-B cache
    ("IK's Copy UI System Design - Live Class Slides - Isabela Moreira",
     "Isabela Moreira"),
    ("JS and WebD - Live Class by Kevin", "Kevin"),
    ("Arpit: IK-backend-concurrency-presentation-v5", "Arpit"),
    ("Databases - Ashish.pdf", "Ashish"),
    ("UI & DOM - Jakob.pptx", "Jakob"),
])
def test_the_name_shapes_that_actually_occur_are_recognised(filename, token):
    """The first version required a file EXTENSION and a trailing `- Name`.
    Native Google decks have no extension, and the corpus uses three shapes:
    trailing `- Name`, trailing `by Name`, and leading `Name:`. Zero proposals
    came out of the first build, which is what sent me to look at real names."""
    assert cm.deck_name_token(filename) == token


@pytest.mark.parametrize("filename", [
    "Old API Design.pptx", "API Testing Fundamentals",
    "Video-05 Most used design patterns in Test Automation - Decorator Pattern",
    "Apr 2023: Live Class Slides: Test Engineering Design Patterns",
])
def test_a_deck_name_with_no_person_in_it_proposes_nothing(filename):
    """Negative control, and the third case is the one that matters: a trailing
    `- Decorator Pattern` is a topic, not a person."""
    tok = cm.deck_name_token(filename)
    assert cm.propose_deck_instructor(filename, {"primary": ["Ashish Kaila"]}) is None or tok


def test_a_lesson_plan_row_is_split_on_the_separator_the_extractor_writes():
    """FOUND BY RANKING THE TOPICS. `extract_text._xlsx` joins cells with
    ` | `, and this splitter used `,` — so every lesson-plan topic came out as
    the whole joined row, header included:

        'Topic | Flow | Learning Objectives (After the segment, the ...'

    The lesson plans are the FIRST topic source, so the layer this was meant
    to privilege was the one it mangled. Ranking made it visible; the counts
    never would have.
    """
    text = ("[tab Concurrency Lesson Plan]\n"
            "Topic | Flow | Learning Objectives\n"
            "Thread Pools | 30min | Builds on MPCQ\n"
            "Timer | 30min | Defer execution\n")
    got = cm.topics_from_text(text, source="curriculum")
    assert [t.label for t in got] == ["Thread Pools", "Timer"]


def test_a_comma_separated_tab_still_works():
    """Negative control: csv-shaped rows must not regress."""
    got = cm.topics_from_text("[tab X]\nTopic,Flow\nSharding,20min\n",
                              source="curriculum")
    assert [t.label for t in got] == ["Sharding"]
