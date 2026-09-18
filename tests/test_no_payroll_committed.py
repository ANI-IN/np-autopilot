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
    assert "no HR/payroll content" in r.stdout
