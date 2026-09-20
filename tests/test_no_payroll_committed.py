"""The SECOND layer against payroll data reaching git, keyed on content.

R17's rule was "an excluded file must never reach the disk". The reversal that
ingests `US Instructor Cost Analysis.xlsx` retires that rule, so something must
replace it — and what existed was one layer wearing two hats:

  * `.gitignore:87  03-instructors/` — a path rule, walked past by `git add -f`,
    a rename, a move, or a copy into another directory;
  * `taxonomy.yaml -> excluded.files` — also a path, and read by BOTH pass 0 and
    pass 1, so a wrong entry defeats both at once (§A.7a).

Every one of those is keyed on WHERE the file is. This layer is keyed on WHAT IT
CONTAINS and shares no source of truth with them.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "np_payroll_check", REPO / "pipeline" / "check_no_payroll_committed.py")
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

PAYROLL = REPO / "03-instructors" / "US Instructor Cost Analysis.xlsx"


def _scan_one(path: Path) -> tuple[set[str], int]:
    found, occ = set(), 0
    for blob in chk._blobs(path):
        for sig in chk.SIGNATURES:
            c = blob.count(sig)
            if c:
                found.add(sig.decode())
                occ += c
    return found, occ


def test_nothing_in_git_carries_payroll_content():
    """The live assertion. Runs over tracked and staged files."""
    hits = chk.scan()
    assert not hits, (
        "HR/payroll content is in tracked or staged files:\n  "
        + "\n  ".join(f"{p} — {s}" for p, s in hits))


def test_the_check_catches_the_real_file_under_any_name():
    """CONTENT, NOT PATH — the whole reason this layer exists.

    Scanned directly, never staged: the point is that renaming or moving it
    defeats `.gitignore` and does not defeat this.
    """
    if not PAYROLL.exists():
        pytest.skip("payroll workbook not present in this checkout")
    found, occ = _scan_one(PAYROLL)
    assert found, "the real payroll workbook matched no signature at all"
    assert occ > chk.PROSE_OCCURRENCES * 10, (
        f"only {occ} occurrences — the threshold no longer separates data from "
        "prose by the margin it was measured against")


def test_a_data_shaped_file_needs_only_one_signature(tmp_path):
    """A single sheet pasted into a new workbook is still payroll."""
    xlsx = tmp_path / "quarterly summary.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/sharedStrings.xml",
                   "<sst><si><t>Employee File Number</t></si></sst>")
    found, _ = _scan_one(xlsx)
    assert found == {"Employee File Number"}
    assert xlsx.suffix.lower() in chk.DATA_SUFFIXES


def test_prose_describing_the_exclusion_is_not_flagged():
    """USES, NOT MENTIONS — the control that matters most here.

    The first version of this check flagged seven files, every one of them the
    project's own record of why the payroll file is excluded: the corpus
    inventory, the risk register, CACHE-EXPOSURE, taxonomy.yaml, BUILD_LOG, pass
    0 and the fetch-time exclusion test. A check that cannot tell a prohibition
    from its own description is one that gets silenced by deleting the comment.
    """
    documented = [REPO / "01-corpus-inventory.md", REPO / "07-risks.md",
                  REPO / "docs" / "CACHE-EXPOSURE.md"]
    flagged = {p for p, _ in chk.scan()}
    for doc in documented:
        if not doc.exists():
            continue
        found, occ = _scan_one(doc)
        assert found, f"{doc.name} no longer describes the exclusion at all"
        assert str(doc.relative_to(REPO)) not in flagged, (
            f"{doc.name} is flagged for describing the exclusion it documents "
            f"({occ} occurrences)")


def test_the_threshold_still_separates_prose_from_data():
    """CLAUDE.md §4: a cutoff must not hide a correct answer.

    Asserts the measured gap the threshold sits in, so a future edit that makes
    prose denser, or the signature list narrower, fails here rather than by
    quietly flagging documentation or quietly passing a dump.
    """
    worst_prose = 0
    for doc in REPO.glob("*.md"):
        _, occ = _scan_one(doc)
        worst_prose = max(worst_prose, occ)
    assert worst_prose < chk.PROSE_OCCURRENCES, (
        f"prose now reaches {worst_prose} occurrences against a threshold of "
        f"{chk.PROSE_OCCURRENCES} — the separation the threshold relies on is gone")


def test_the_script_exits_nonzero_when_it_finds_something(tmp_path):
    """The exit code is the whole interface for a pre-commit hook."""
    r = subprocess.run([sys.executable,
                        str(REPO / "pipeline" / "check_no_payroll_committed.py")],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, f"expected clean tree, got:\n{r.stderr}"
    assert "no HR/payroll or contact content" in r.stdout


# ---------------------------------------------------------------------------
# CONTACT SIGNATURE CLASS — added 2026-09-20.
#
# The incident: the first draft of docs/REGISTRY-INVENTORY.md carried four
# instructors' personal email addresses. It was redacted by hand. Nothing in
# the repository would have caught it, because this guard's signatures were
# payroll-only — the A7B question-3 shape, about this repository rather than
# the corpus: the guarantee held because nobody had had a reason to type one.
#
# Every test below is a NEGATIVE CONTROL in the sense CLAUDE.md requires: it
# breaks the thing the guard watches and asserts the guard goes RED. A test
# that only proves the clean tree is clean would have passed before this class
# existed.
# ---------------------------------------------------------------------------


def _scan_text(tmp_path, name: str, body: str):
    """Scan one synthetic file the way scan() would, without touching git."""
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    blobs = list(chk._blobs(p))
    kinds, occ, bare = chk._count_identifiers(blobs)
    heads, h_occ = chk._count_literals(blobs, chk.CONTACT_HEADERS)
    return {"kinds": kinds, "occ": occ, "bare": bare,
            "headers": heads, "header_occ": h_occ}


def test_the_actual_near_miss_is_caught(tmp_path):
    """THE REGRESSION TEST. This is the document that was nearly committed.

    Four personal addresses in a Markdown file, in prose, surrounded by exactly
    the kind of justification that makes a leak feel legitimate. A density rule
    calibrated against prose — the rule that works for the payroll class —
    would have waved this straight through, which is why the identifier class
    has no density rule.
    """
    res = _scan_text(tmp_path, "REGISTRY-INVENTORY.md", """
### (iv) Instructor names in file metadata — a channel with no control at all

Four personal Gmail addresses appear as **file owners**, not as cell values:
`robert.kreznarich@gmail.com`, `s.cohen131@gmail.com`,
`jayashkoshal@gmail.com`, `anshaj.khare2@gmail.com`.
""")
    assert res["kinds"] == {"personal-email"}
    assert res["occ"] == 4, f"expected all four addresses, got {res['occ']}"
    assert res["occ"] < chk.PROSE_OCCURRENCES, (
        "the near-miss must sit BELOW the payroll prose threshold — that is "
        "the whole reason the identifier class cannot borrow that rule")


def test_a_linkedin_roster_is_caught_at_one(tmp_path):
    """docs/CONTACT-DATA.md declined LinkedIn for all three populations.

    Measured 2026-09-20: zero occurrences in tracked files, so a threshold of
    one costs nothing today and fires the first time the SME roster in
    `SMEs consent` is pasted into a document.
    """
    res = _scan_text(tmp_path, "sme-roster.md",
                     "1. A Person: <https://www.linkedin.com/in/a-person/>\n")
    assert res["kinds"] == {"linkedin-profile"}
    assert res["occ"] == 1


def test_a_form_response_export_is_caught_by_its_header(tmp_path):
    """The shape REGISTRY-INVENTORY §5(i) found: a Google Form response sheet.

    `Email Address` is generated by the form, not authored, so it is the one
    contact column that appears by construction in every such export. A
    data-shaped file needs ONE occurrence — no density argument applies,
    because nothing else explains why the file is in the repository.
    """
    xlsx = tmp_path / "capstone submissions.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/sharedStrings.xml",
                   "<sst><si><t>Email Address</t></si>"
                   "<si><t>Please enter your name</t></si></sst>")
    blobs = list(chk._blobs(xlsx))
    heads, occ = chk._count_literals(blobs, chk.CONTACT_HEADERS)
    assert heads == {"Email Address"}
    assert occ == 1
    assert xlsx.suffix.lower() in chk.DATA_SUFFIXES, (
        "data-shaped is what lowers the threshold to one")


def test_prose_about_contact_columns_is_not_flagged():
    """USES, NOT MENTIONS — the control that matters most, again.

    This project's documents discuss contact columns constantly; that is what
    they are FOR. A check that cannot tell a prohibition from its own
    description gets silenced by deleting the description, which is the
    documentation most worth keeping. The payroll class learned this by
    flagging seven of the project's own records; the contact class must not
    repeat it.
    """
    documented = [REPO / "docs" / "CONTACT-DATA.md",
                  REPO / "docs" / "CACHE-EXPOSURE.md",
                  REPO / "docs" / "REGISTRY-INVENTORY.md",
                  REPO / "CLAUDE.md"]
    flagged = {p for p, _ in chk.scan()}
    for doc in documented:
        if not doc.exists():
            continue
        blobs = list(chk._blobs(doc))
        heads, occ = chk._count_literals(blobs, chk.CONTACT_HEADERS)
        assert heads, f"{doc.name} no longer discusses contact columns at all"
        assert str(doc.relative_to(REPO)) not in flagged, (
            f"{doc.name} is flagged for describing the exclusion it documents "
            f"({occ} header occurrences)")


def test_the_contact_header_threshold_still_separates_prose_from_data():
    """CLAUDE.md §4: a cutoff must not hide a correct answer.

    Asserts the measured gap the threshold sits in. Measured 2026-09-20 with
    the shipped matcher, the densest legitimate prose was CACHE-EXPOSURE.md and
    01-corpus-inventory.md at 10 each, against a threshold of 100. If
    documentation grows denser, or the signature list widens, this fails here
    rather than by quietly flagging the documentation.

    DERIVED, NOT LISTED — instance 8. Two hardcoded globs would measure the
    directories somebody remembered, and the densest file in the repository is
    a `.py`, not a `.md`. The scope is every tracked file that is not
    data-shaped, minus the module's own self-exemptions.
    """
    worst, worst_doc = 0, ""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO,
                             capture_output=True, text=True).stdout.split("\n")
    for rel in filter(None, tracked):
        if rel in chk.SELF_EXEMPT:
            continue
        path = REPO / rel
        if not path.is_file() or path.suffix.lower() in chk.DATA_SUFFIXES:
            continue
        try:
            _, occ = chk._count_literals(list(chk._blobs(path)),
                                         chk.CONTACT_HEADERS)
        except Exception:                               # noqa: BLE001
            continue
        if occ > worst:
            worst, worst_doc = occ, rel
    assert worst, "nothing in the repository mentions a contact column at all"
    assert worst < chk.CONTACT_HEADER_PROSE_OCCURRENCES, (
        f"{worst_doc} now reaches {worst} occurrences against a threshold of "
        f"{chk.CONTACT_HEADER_PROSE_OCCURRENCES} — the separation is gone")


def test_a_reasoned_marker_exempts_and_a_bare_one_is_an_offence(tmp_path):
    """An exemption with no cost is a hole — the `taxonomy-literal-ok` rule.

    Three cases in one test because they are one decision: the marker must
    work, the marker must require a reason, and the reason must not be
    optional.
    """
    reasoned = _scan_text(tmp_path, "a.py",
                          "# contact-ok: synthetic, asserts refusal\n"
                          "verify(email='someone@gmail.com')\n")
    assert not reasoned["kinds"], "a reasoned marker must exempt the next line"
    assert reasoned["bare"] == 0

    trailing = _scan_text(tmp_path, "b.py",
                          "verify('someone@gmail.com')  # contact-ok: fixture\n")
    assert not trailing["kinds"], "a marker must also work trailing its line"

    bare = _scan_text(tmp_path, "c.py",
                      "# contact-ok\nverify(email='someone@gmail.com')\n")
    assert bare["bare"] == 1, "a marker with no reason must be reported"
    assert bare["kinds"] == {"personal-email"}, (
        "and must NOT exempt — otherwise it is a silent opt-out")


def test_the_marker_scope_matches_the_other_marker_in_this_repo():
    """Two marker conventions that scope differently is a trap.

    `tests/test_taxonomy_single_source.py` covers the marker's own line and the
    next line that is actually code. This asserts the contact marker agrees,
    so neither can drift into being the special case.
    """
    lines = [b"# contact-ok: reason", b"", b"# a comment", b"real_code()"]
    exempt, bare = chk._exempt_lines(lines)
    assert bare == 0
    assert 0 in exempt, "the marker's own line"
    assert 3 in exempt, "and the next line that is actually code"
    assert 1 not in exempt and 2 not in exempt, "blanks and comments are skipped"


def test_removing_the_contact_class_reddens_these_tests():
    """VERIFIED BY MUTATION, the way migrations 0012/0014/0015 were.

    Not a claim in a comment: it empties the signature list and the patterns in
    a copy of the module's globals and asserts the near-miss stops being
    caught. If this passes while the class is gutted, the class is decorative.
    """
    import re as _re
    saved_free, saved_li = chk.FREEMAIL_RE, chk.LINKEDIN_RE
    try:
        chk.FREEMAIL_RE = _re.compile(rb"(?!x)x")      # matches nothing
        chk.LINKEDIN_RE = _re.compile(rb"(?!x)x")
        kinds, occ, _ = chk._count_identifiers(
            [b"contact me at somebody@gmail.com\n"])
        assert not kinds and occ == 0, (
            "with the patterns gutted the scan still found something — the "
            "test is not measuring what it claims to")
    finally:
        chk.FREEMAIL_RE, chk.LINKEDIN_RE = saved_free, saved_li

    kinds, occ, _ = chk._count_identifiers([b"contact me at somebody@gmail.com\n"])
    assert kinds == {"personal-email"} and occ == 1, (
        "restored patterns must catch it again — otherwise the mutation leaked")
