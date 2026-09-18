"""The lists where a missing entry costs EXPOSURE rather than accuracy.

From the included-by-default sweep. Twelve hand-written lists fail open; eight
of them cost accuracy — a junk node, a missed variant — and those are left
alone, because they encode judgement nobody should derive. These four cost
exposure.

THE FINDING THAT ORDERED THIS WORK: D4's contact strip is described everywhere
as the control that keeps contact data out of the graph. It is not, and never
was. `is_excluded_field` had exactly one caller — validate.py — where it was
matched against DERIVED property names rather than the raw spreadsheet headers
the patterns describe, so it could not fire. What has actually kept contact data
out is `pipeline/lib/sources.py`: extraction reads only declared
(file, sheet, column) triples, and only 20 distinct columns have ever been read.
That is an allow-list, it holds, and it was chosen for coverage rather than
safety. See DECISIONS §A.7b, "the control that never worked".
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import sources as SRC                                # noqa: E402
from pipeline.lib import taxonomy                                      # noqa: E402


# ---------------------------------------------------------------------------
# 1. The real control, named and asserted
# ---------------------------------------------------------------------------

def _declared_columns() -> set[str]:
    """Every column any extractor is declared to read."""
    cols: set[str] = set()
    for name in dir(SRC):
        if name.startswith("_"):
            continue
        val = getattr(SRC, name)
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, (tuple, list)) and len(entry) >= 3:
                    cols.add(str(entry[2]))
    return cols


def test_no_declared_extraction_column_is_a_contact_field():
    """THE INVERSION, made explicit.

    Extraction is already an allow-list — sources.py names every
    (file, sheet, column) triple an extractor may read. This asserts that the
    allow-list contains no contact column, which is the property the deny-list
    was believed to provide and did not.
    """
    offenders = sorted(c for c in _declared_columns()
                       if taxonomy.is_excluded_field(c))
    assert not offenders, (
        f"sources.py declares contact columns as extractable: {offenders}. "
        "The allow-list is the control; adding a contact column to it puts the "
        "data in the graph regardless of what excluded.field_patterns says.")


def test_the_header_matcher_catches_the_variants_equality_missed():
    """NEGATIVE CONTROL for the hardening.

    Equality let 20 of 35 contact-shaped headers through, measured across the
    corpus. These nine are the ones that carried real contact data; the others
    were metadata like `Email Sent?`.
    """
    must_exclude = [
        "Student Email", "Phone Number", "Email (personal)", "personal_email",
        "Alternate Email ID (for instructor/interviewer account)",
        "Discord ID (please create one if you don't have it)",
        "person.linkedInUrl", "company.phone", "IK email (If applicable)",
    ]
    missed = [h for h in must_exclude if not taxonomy.is_excluded_field(h)]
    assert not missed, f"still not excluded: {missed}"

    # ...and it must not swallow the columns extraction depends on.
    must_keep = ["Full Name", "Instructor", "Module Name", "Coach",
                 "Session_Title", "SME Name", "Candidate Name"]
    swallowed = [h for h in must_keep if taxonomy.is_excluded_field(h)]
    assert not swallowed, f"over-excluded: {swallowed}"


# ---------------------------------------------------------------------------
# 2. excluded.files — content-keyed, not only path-keyed
# ---------------------------------------------------------------------------

def test_the_excluded_file_is_also_caught_by_content():
    """`excluded.files` has ONE entry and fails open. The content check is the
    independent layer, and this asserts the two agree about the same file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "chk2", REPO / "pipeline" / "check_no_payroll_committed.py")
    chk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chk)

    excluded = taxonomy.excluded_files()
    assert excluded, "excluded.files is empty"
    for rel in excluded:
        path = REPO / rel
        if not path.exists():
            pytest.skip(f"{rel} not in this checkout")
        found = set()
        for blob in chk._blobs(path):
            for sig in chk.SIGNATURES:
                if sig in blob:
                    found.add(sig.decode())
        assert found, (
            f"{rel} is excluded by PATH but matches no content signature. The "
            "two layers would not agree if it were renamed.")


# ---------------------------------------------------------------------------
# 3. .vercelignore — derived from what pass 1 treats as corpus
# ---------------------------------------------------------------------------

def test_vercelignore_excludes_every_corpus_directory():
    """The corpus half was a hand-written list of 16 paths, so a new corpus
    directory would be UPLOADED by default. Derived here from pass 1's own
    rule: a top-level directory it walks as corpus must not ship to Vercel."""
    skip = set()
    src = (REPO / "pipeline" / "01_walk_corpus.py").read_text(encoding="utf-8")
    import ast
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SKIP_DIRS":
            skip = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    assert skip, "could not read SKIP_DIRS from pass 1"

    corpus_dirs = {d.name for d in REPO.iterdir()
                   if d.is_dir() and not d.name.startswith(".")
                   and d.name not in skip
                   and d.name not in {"web", "api", "public", "docs", "eval",
                                      "commands", "db", "node_modules"}}
    ignore = (REPO / ".vercelignore").read_text(encoding="utf-8")
    listed = {ln.strip().rstrip("/") for ln in ignore.splitlines()
              if ln.strip() and not ln.strip().startswith("#")}
    missing = sorted(d for d in corpus_dirs if d not in listed)
    assert not missing, (
        f"corpus directories that would be uploaded to Vercel: {missing}. "
        "Pass 1 walks them as corpus; nothing in the bundle needs them.")


# ---------------------------------------------------------------------------
# 4. Security headers — asserted against the DEPLOYED response
# ---------------------------------------------------------------------------

REQUIRED_HEADERS = ["strict-transport-security", "x-content-type-options",
                    "x-frame-options", "referrer-policy", "permissions-policy",
                    "content-security-policy", "cross-origin-opener-policy"]


@pytest.mark.skipif(not os.environ.get("NP_VERIFY_URL"),
                    reason="set NP_VERIFY_URL to check the live deployment")
def test_the_deployed_response_carries_every_security_header():
    """vercel.json is the INTENTION; the response is the fact.

    A header list in a config file is another hand-written list that fails
    open — a missing entry is a header silently not sent, and the page looks
    identical. Opt-in so CI without network still passes.
    """
    url = os.environ["NP_VERIFY_URL"]
    req = urllib.request.Request(url, headers={"User-Agent": "np-header-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        got = {k.lower() for k in r.headers.keys()}
    missing = [h for h in REQUIRED_HEADERS if h not in got]
    assert not missing, f"{url} is missing security headers: {missing}"
