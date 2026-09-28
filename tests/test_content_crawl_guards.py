"""Guards for the row-B content crawl. Each one is a decision from
`docs/PRE-CRAWL-DECISIONS.md` (D1, D3-D6) or from the owner's Phase-0 answers,
written as a test BEFORE the code it governs exists.

WHY THE TESTS COME FIRST HERE SPECIFICALLY. §"What is enforced, and what is
only written here" says five of six pre-crawl decisions are prose, and
`docs/A7B.md` question 2 is the failure of reading a document as a control:
*for any constraint a document asserts, what in the program would fail if it
stopped being true?* Until this file existed the answer for D1, D4, D5 and D6
was "nothing".

Every guard below has a NEGATIVE CONTROL — a test that fails if the guard is
removed — because A7B instances 2 and 3 were checks that passed while doing
nothing. A test that the guard *allows* the good case is not enough; the
mutation record is in the Phase 1 report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import content_scope as cs          # noqa: E402
from pipeline.lib import curriculum as cur            # noqa: E402
from pipeline.lib import redact as rd                 # noqa: E402

SLIDES = "application/vnd.google-apps.presentation"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
FOLDER = "application/vnd.google-apps.folder"
MP4 = "video/mp4"
ZIP = "application/zip"


# ---------------------------------------------------------------------------
# D1 — no person extraction from slide or deck content. At any confidence.
# ---------------------------------------------------------------------------

def test_people_may_never_be_extracted_from_deck_content():
    """REGISTRY-INVENTORY §7: four instructor-shaped tuples on decks, two of
    them fabricated, structurally identical to the two real ones. Ranking a
    fabrication yields a ranked fabrication."""
    for mime in (SLIDES, PPTX):
        assert cs.may_extract_people(mime) is False


def test_people_may_never_be_extracted_from_a_deck_filename_either():
    """The owner deferred instructors, and a filename is not slide content —
    so D1 is silent on it. Deferred means deferred: `Databases - Ashish.pdf`
    must not become a person until that phase runs."""
    assert cs.may_extract_people_from_filename("Databases - Ashish.pdf") is False


def test_a_structured_roster_is_not_caught_by_the_deck_rule():
    """Negative control in the other direction. D1 forbids decks, not the
    structured sources. A guard that refused everything would pass every test
    above and destroy the instructor phase."""
    assert cs.may_extract_people(SHEET) is True


# ---------------------------------------------------------------------------
# D4 — owner domain, never the address. And nothing carries an '@'.
# ---------------------------------------------------------------------------

def test_a_file_owner_is_reduced_to_its_domain():
    assert cs.owner_domain("someone@interviewkickstart.com") == "interviewkickstart.com"
    assert cs.owner_domain("instructor@gmail.com") == "gmail.com"


def test_owner_domain_never_returns_a_local_part():
    for addr in ("a.b+c@example.com", "SHOUTY@Example.COM"):
        out = cs.owner_domain(addr)
        assert "@" not in out
        assert out == out.lower()


def test_no_provenance_field_may_contain_an_at_sign():
    """D4's enforceable form, and it is DERIVED over the row rather than a list
    of field names somebody maintains — the instance-8 fix applied in advance.
    A new provenance column is covered by default."""
    good = {"file": "SD3/Module-1/x.pptx", "owner_domain": "gmail.com", "row": 4}
    bad = {"file": "SD3/Module-1/x.pptx", "owner": "sme@gmail.com"}
    assert cs.provenance_is_clean(good) is True
    assert cs.provenance_is_clean(bad) is False


# ---------------------------------------------------------------------------
# D5 / D6 and the learner-content rule — declared skips, always reported
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,rule", [
    ("Assignment Submission Form (File responses)", "D6"),
    ("SMEs consent", "D5"),
])
def test_declared_folder_skips_are_by_name_and_carry_their_rule(name, rule):
    d = cs.classify_folder(path=f"/X/{name}", name=name)
    assert d.action == "skip"
    assert d.rule == rule
    assert d.reason


def test_a_big_folder_is_not_skipped_for_being_big():
    """D6 is a declared skip, NOT a size cap. A size cap would also drop the
    17.66 MB teaching deck — CLAUDE.md §4 in a new place."""
    d = cs.classify_folder(path="/X/2. Live Class Slides", name="2. Live Class Slides")
    assert d.action == "walk"


def test_learner_interaction_files_are_metadata_only():
    """Owner's Phase-0 answer 5: ingest assignment-review files as metadata
    only; never export their text."""
    d = cs.classify_file(
        path="/IK Test Engineering: Content Repo/Week 5/6 - X/3. Assignment/"
             "Assignment Review/Assignment Session - Students Interactions.txt",
        name="Assignment Session - Students Interactions.txt", mime="text/plain")
    assert d.action == "metadata_only"
    assert d.rule == "learner-content"


def test_a_learner_submitted_repo_is_metadata_only():
    d = cs.classify_file(
        path="/X/3. Assignment/Assignment Review - Roland/"
             "(Incomplete) Aspiration Bank Testing Framework/__docs/notes.md",
        name="notes.md", mime="text/markdown")
    assert d.action == "metadata_only"
    assert d.rule == "learner-content"


def test_an_ordinary_assignment_doc_is_still_exported():
    """Negative control: the learner rule must not swallow the assignment."""
    d = cs.classify_file(path="/X/3. Assignment/Object Modeling: Assignment",
                         name="Object Modeling: Assignment", mime=DOC)
    assert d.action == "export"


# ---------------------------------------------------------------------------
# Media — metadata only, never downloaded. 15.55 GiB of the 16.67 GiB measured.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mime", [MP4, "video/quicktime", "audio/x-m4a",
                                  "image/jpeg", ZIP, "application/x-zip-compressed"])
def test_media_and_archives_are_never_downloaded(mime):
    d = cs.classify_file(path="/X/y", name="y", mime=mime)
    assert d.action == "metadata_only"
    assert d.rule == "no-media-download"


def test_a_deck_is_still_exported():
    d = cs.classify_file(path="/X/deck.pptx", name="deck.pptx", mime=PPTX)
    assert d.action == "export"


# ---------------------------------------------------------------------------
# Scope — the registry's rows, never "the account can read it"
# ---------------------------------------------------------------------------

def test_scope_is_the_declared_rows_not_readability():
    """REGISTRY-INVENTORY §12: for row C that proxy's answer includes the
    public internet."""
    assert cs.in_scope(cs.ROW_B_ID) is True
    assert cs.in_scope("1aVg_UbUCsuDxv9XXICIxbmpMbjUz5ETm") is False   # row C
    assert cs.in_scope("some-folder-the-account-can-read") is False


def test_only_the_four_approved_domains_are_in_scope():
    assert cs.domain_in_scope("SD3: Backend Engineering") is True
    assert cs.domain_in_scope("Sys3: Embedded Software Engineering") is False


# ---------------------------------------------------------------------------
# Redaction — applied BEFORE anything reaches disk
# ---------------------------------------------------------------------------

def test_an_address_is_redacted_at_threshold_one():
    """A7B 'the borrowed rule': a header is a word, an address is a person.
    Density is the right question for one and a category error for the other."""
    out, counts = rd.redact("contact ops@interviewkickstart.com for access")
    assert "@" not in out
    assert counts["email"] == 1


def test_a_linkedin_url_is_redacted():
    out, counts = rd.redact("profile https://www.linkedin.com/in/someone-1234")
    assert "linkedin.com" not in out
    assert counts["linkedin"] == 1


def test_redaction_reports_counts_without_the_values():
    counts = rd.scan("a@b.com and c@d.org")
    assert counts["email"] == 2
    assert all(isinstance(v, int) for v in counts.values())


def test_ordinary_curriculum_text_survives_redaction_unchanged():
    """Negative control. A redactor that ate prose would pass every test above
    and silently destroy the content this crawl exists to read."""
    text = "REST design principles: statelessness, cacheability, HATEOAS."
    out, counts = rd.redact(text)
    assert out == text
    assert counts == {}


# ---------------------------------------------------------------------------
# WEEKS — the owner's clarification. A folder "Week N" is a SEQUENCE.
# ---------------------------------------------------------------------------

def test_a_week_folder_yields_a_module_sequence_not_a_week():
    """Owner: 'The folder "Week N" is NOT a week. It is local sequencing inside
    the domain folder, used only to order modules.'"""
    assert cur.module_sequence_from_folder("Week 3") == 3
    assert cur.module_sequence_from_folder("Week 1") == 1


def test_no_week_node_is_ever_created_from_a_folder_name():
    assert cur.week_node_from_folder("Week 3") is None


def test_a_program_week_is_never_derived_arithmetically():
    """Owner: 'Never derive a program week arithmetically (no local + offset).
    A module can sit at different program weeks in different programs.'"""
    with pytest.raises(cur.ArithmeticWeekRefused):
        cur.program_week_from_local(local=1, offset=8)


def test_a_program_week_must_carry_the_curriculum_source_it_came_from():
    w = cur.program_week(value=9, source_kind="kyp",
                         source_file="Intro to Course - Front-EndEngineering - KYP Doc.pdf")
    assert w.value == 9
    assert w.source_kind == "kyp"
    assert w.source_file


def test_a_program_week_with_no_curriculum_source_is_refused():
    """A VALID kind with a missing file, deliberately.

    The first version of this test passed `source_kind=None`, and mutation
    testing showed it passed whether or not the source check existed — with the
    check removed, the *kind* validation raised `ValueError` for `None` and the
    assertion was satisfied by the wrong mechanism. That is `docs/A7B.md`
    instances 2 and 3 in a test: two different reasons producing one green.

    Using a kind that IS in the vocabulary leaves exactly one thing that can
    raise, so the test now names its own mechanism.
    """
    with pytest.raises(ValueError, match="must carry the curriculum source"):
        cur.program_week(value=9, source_kind="kyp", source_file=None)


def test_an_unknown_curriculum_kind_is_refused_separately():
    """The mechanism the previous test used to lean on, now tested in its own
    right so removing either one goes red on its own line."""
    with pytest.raises(ValueError, match="unknown curriculum kind"):
        cur.program_week(value=9, source_kind="brochure", source_file="x.pdf")


def test_a_domain_with_no_curriculum_week_reports_a_gap_rather_than_guessing():
    """SD3 today: the Backend lesson plans have no week column at all."""
    assert cur.program_week_or_gap(None) == (None, "no-curriculum-week")


# ---------------------------------------------------------------------------
# Date coercion — '1-5' became 2023-01-05 in the outlines
# ---------------------------------------------------------------------------

def test_a_coerced_week_range_is_recovered_and_flagged():
    got = cur.recover_week_range("2023-01-05 00:00:00")
    assert got.value == "1-5"
    assert got.recovered_from_date_coercion is True


def test_a_plain_week_number_is_not_flagged_as_recovered():
    got = cur.recover_week_range("9")
    assert got.value == "9"
    assert got.recovered_from_date_coercion is False


# ---------------------------------------------------------------------------
# Module identity — (domain_slug, sequence). Never an implicit merge.
# ---------------------------------------------------------------------------

def test_a_module_is_keyed_on_domain_and_sequence_not_on_its_label():
    a = cur.module_key("backend", 3)
    b = cur.module_key("full-stack", 3)
    assert a != b


def test_two_modules_sharing_a_label_are_not_merged():
    """`API Design` exists in Backend and `API Design and Implementation` in
    Full Stack, and the existing graph holds 922 label-keyed modules."""
    assert cur.module_key("backend", 3) != cur.module_key("full-stack", 2)


def test_a_label_collision_becomes_a_review_row_not_a_join():
    row = cur.propose_alias("API Design", "backend", 3, "existing-module-id")
    assert row["confirmed"] is False


def test_normalisation_is_proposed_never_applied_implicitly():
    """Owner: 'JS→JavaScript and similar go into a curated alias file,
    confirmed individually, never applied implicitly.'"""
    assert cur.normalise_for_join("JS Language & Libraries") != \
        cur.normalise_for_join("JavaScript Language & Libraries")


# ---------------------------------------------------------------------------
# SD3's anomaly — module comes from the module-named folder, never the parent
# ---------------------------------------------------------------------------

def test_the_module_folder_wins_over_the_parent_path():
    """All five Backend week folders sit under `Module-1: Database Design`.
    A parent-path rule files every Backend module under Database Design."""
    path = ("/Module-1: Database Design/Uplevel shared/Week 3/"
            "5 - API Design/Slides/deck.pptx")
    assert cur.module_folder_from_path(path) == "5 - API Design"


def test_a_module_named_folder_is_preferred_at_any_depth():
    path = "/Module-2: Object Modeling/2. Live Class Slides/deck.pptx"
    assert cur.module_folder_from_path(path) == "Module-2: Object Modeling"


# ---------------------------------------------------------------------------
# Phone precision — audited against the run-3 cache, 2026-09-29
# ---------------------------------------------------------------------------

#: Drawn from contexts actually present in the cache, not invented.
PHONE_CASES = [
    ("what does 200 300 400 500 HTTP Response code mean?", False),
    ("New Data Jobs Projected 2024 2034 (BLS: 33.5% growth)", False),
    ("listen on 8080 3000 for the dev server", False),
    ("rows 1200 4500 scanned in the query plan", False),
    ("Winner DOB Ohio International 1998 04 1981 Iowa Open", False),
    ("call me on +1 415 555 0134 any time", True),
    ("San Diego, CA 619 555 0147 | someone@example.com", True),
    ("Tel: 020 7946 0958", True),
    ("+91 98765 43210", True),
]


@pytest.mark.parametrize("text,is_phone", PHONE_CASES)
def test_phone_redaction_keeps_curriculum_numbers(text, is_phone):
    """The audit's finding, as a test.

    The first pattern required only `\\d{3,5}[sep]\\d{3,5}` — six digits — so
    `200 300 400 500` on a slide teaching HTTP status codes became
    `200 <phone redacted> 500`. That is not over-redaction of contact data, it
    is DESTRUCTION OF CURRICULUM, and it is the cost `CLAUDE.md` §4 is about:
    a rule that silently removes correct answers.

    Measured on the run-3 cache: 148 phone redactions across 132 files, and
    not one had phone-shaped context.
    """
    out, counts = rd.redact(text)
    assert bool(counts.get("phone")) is is_phone


def test_phone_redaction_still_has_no_density_threshold():
    """Negative control. Tightening the SHAPE must not reintroduce a count
    rule — A7B's borrowed rule: one address, or one number, is enough."""
    out, counts = rd.redact("+1 415 555 0134")
    assert counts["phone"] == 1
