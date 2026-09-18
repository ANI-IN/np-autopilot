#!/usr/bin/env python3
"""SECOND LAYER — refuse to let payroll/HR data into git, keyed on CONTENT.

WHY A SECOND LAYER, AND WHY IT MUST NOT LOOK LIKE THE FIRST.

`US Instructor Cost Analysis.xlsx` — 5,387 named people, employment status
including "Exited (Terminated)", last working day, per-labour-code rates — is
kept out of the graph by `taxonomy.yaml -> excluded.files`, and out of git by one
line: `.gitignore:87  03-instructors/`.

That reads as two layers and is one. Pass 0 and pass 1 both read the SAME
exclusion list (§A.7a), so a wrong entry defeats both at once; and `.gitignore`
is a single path rule that a `git add -f`, a moved file, a renamed directory or
a copy into another folder all walk straight past. Every one of those protections
is keyed on WHERE the file is.

So this layer is keyed on WHAT IT CONTAINS, and it deliberately shares no source
of truth with the other: it does not read taxonomy.yaml, it does not read
.gitignore, and it does not know the file's name. Rename it, move it, or paste a
sheet of it into a new workbook and this still fires.

    python3 pipeline/check_no_payroll_committed.py            # tracked + staged
    python3 pipeline/check_no_payroll_committed.py --staged   # pre-commit use

It reports the PATH and WHICH SIGNATURE matched. It never prints a matched row:
a leak-detector that echoes the leak is not a detector.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Column headers and labels that identify HR/payroll content. Taken from the
#: real file, and chosen to be things that do not occur in ordinary curriculum
#: or scheduling data.
#:
#: "Employement Status" keeps its misspelling ON PURPOSE — the corpus's typos are
#: load-bearing (CLAUDE.md §1), and a misspelling is a far more specific
#: fingerprint than the correct spelling would be.
SIGNATURES = [
    b"Employee File Number",
    b"Employement Status",
    b"Hourly Rates - Labor code",
    b"Exited (Terminated)",
    b"Exited (Resigned)",
    b"51 - Coaching",
    b"53 - Pre Live Session Prep",
]

#: This file and its test necessarily contain the signatures they look for.
SELF_EXEMPT = {
    "pipeline/check_no_payroll_committed.py",
    "tests/test_no_payroll_committed.py",
}

#: USES, NOT MENTIONS — the same distinction tests/test_login_flow.py had to
#: learn for SERVICE_ROLE. The first version of this check flagged seven files:
#: 01-corpus-inventory.md, 07-risks.md, BUILD_LOG.md, config/taxonomy.yaml,
#: docs/CACHE-EXPOSURE.md, pipeline/00_fetch_drive.py and
#: tests/test_fetch_time_exclusion.py — every one of them PROSE DESCRIBING THE
#: EXCLUSION. A check that cannot tell a prohibition from its own description is
#: one that gets silenced by deleting the comment, which is the documentation
#: most worth keeping.
#:
#: The distinction that actually holds: payroll DATA is a spreadsheet, and it
#: carries the whole header set. Prose mentions a term or two.
#:
#:   * a data-shaped file (spreadsheet, csv, tsv) needs ONE signature, because
#:     nothing else explains why it is there — and this catches the file renamed,
#:     moved, or pasted into a new workbook;
#:   * any other file needs 50 OCCURRENCES, which is a pasted table rather than a
#:     paragraph about one.
#:
#: 50 IS MEASURED, NOT GUESSED, and CLAUDE.md §4 says a cutoff must answer "what
#: would a correct answer excluded by this look like?". Measured across the
#: repository: the most signature-dense prose is 01-corpus-inventory.md at 7
#: occurrences, then 07-risks.md at 6 and CACHE-EXPOSURE.md at 3. The real
#: payroll workbook carries 342,821. That is five orders of magnitude of
#: separation, so 50 excludes nothing but a dump of fewer than ~10 employee rows
#: — which is not the 5,387-person file this exists to stop. A data-shaped file
#: is still caught at one.
DATA_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".numbers", ".parquet"}
PROSE_OCCURRENCES = 50


def _candidate_paths(staged_only: bool) -> list[str]:
    def run(*args: str) -> list[str]:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
        return [ln for ln in r.stdout.splitlines() if ln.strip()]

    paths = set(run("diff", "--cached", "--name-only"))
    if not staged_only:
        paths |= set(run("ls-files"))
    return sorted(paths - SELF_EXEMPT)


def _blobs(path: Path):
    """Yield the bytes to scan. Magic bytes, never the extension (CLAUDE.md).

    A .xlsx is a zip, so the readable strings live in its members; a file that
    merely CLAIMS to be one is scanned as plain bytes.
    """
    raw = path.read_bytes()
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.endswith((".xml", ".rels", ".txt")):
                        try:
                            yield z.read(name)
                        except Exception:              # noqa: BLE001, S112
                            continue
            return
        except zipfile.BadZipFile:
            pass
    yield raw


def scan(staged_only: bool = False) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for rel in _candidate_paths(staged_only):
        path = REPO / rel
        if not path.is_file():
            continue
        # Magic bytes decide "data-shaped", not just the suffix: a spreadsheet
        # saved with the wrong extension is exactly the case a path rule misses.
        try:
            head = path.open("rb").read(2)
        except Exception:                               # noqa: BLE001
            continue
        data_shaped = path.suffix.lower() in DATA_SUFFIXES or head == b"PK"

        found: set[str] = set()
        occurrences = 0
        try:
            for blob in _blobs(path):
                for sig in SIGNATURES:
                    c = blob.count(sig)
                    if c:
                        found.add(sig.decode())
                        occurrences += c
        except Exception:                               # noqa: BLE001
            continue

        if not found:
            continue
        if data_shaped or occurrences >= PROSE_OCCURRENCES:
            hits.append((rel, f"{', '.join(sorted(found))} "
                              f"({occurrences} occurrences)"))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true",
                    help="scan only the staged diff (pre-commit hook use)")
    args = ap.parse_args()

    hits = scan(staged_only=args.staged)
    if not hits:
        print("no HR/payroll content in tracked or staged files")
        return 0

    print("REFUSING: HR/payroll content is about to enter git.", file=sys.stderr)
    for rel, sig in hits:
        print(f"  {rel}\n      matched signature: {sig!r}", file=sys.stderr)
    print("\nThis check is keyed on CONTENT, not on the path, so .gitignore and\n"
          "taxonomy.yaml -> excluded.files did not catch it — which is the point:\n"
          "those are one layer keyed on WHERE the file is. If this file genuinely\n"
          "belongs in the repository, that is a decision to record, not a check\n"
          "to silence.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
