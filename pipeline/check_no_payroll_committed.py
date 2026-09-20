#!/usr/bin/env python3
"""SECOND LAYER — refuse to let payroll/HR or CONTACT data into git, by CONTENT.

Two signature classes, added at different times for the same reason.

TWO CLASSES, AND WHY THE SECOND ONE EXISTS
------------------------------------------
The payroll class came first. The **contact** class was added 2026-09-20 after a
near-miss: the first draft of `docs/REGISTRY-INVENTORY.md` — a document whose
subject is that the registry leaks contact data — reproduced four instructors'
personal email addresses verbatim. They were redacted before the commit, by
hand, because nothing here would have caught them.

That is the A7B question-3 shape, about this repository rather than the corpus:

    The guard was content-keyed and its signatures were payroll-only. The only
    reason no email address had ever been committed is that nobody had had a
    reason to type one.

Inventorying 2,000 files from other people's Drives is that reason, permanently:
**every finding about contact data gets written up by quoting the contact data.**
`docs/CONTACT-DATA.md` declined email and LinkedIn for all three populations, and
that decision had no enforcement anywhere in the program — only `sources.py`'s
column allow-list, which `REGISTRY-INVENTORY.md` §5 showed does not reach four of
the five shapes contact data actually arrives in.

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
import re
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

#: ---------------------------------------------------------------- CONTACT ---
#:
#: DELIBERATELY NOT READ FROM `taxonomy.yaml`. That file's 18 exclusion patterns
#: are the FIRST layer (`taxonomy.is_excluded_field`, hardened 2026-09-19). The
#: whole argument of this module is that a second layer must share no source of
#: truth with the first — §A.7a — so these are written out here, and the two
#: lists are allowed to disagree. If they drift, that is two independent
#: opinions about what contact data looks like, which is the point.
#:
#: CLASS 1 — COLUMN HEADERS. Names of the columns that carry contact data.
#: These occur constantly in this project's own prose, so they get a density
#: rule exactly like the payroll one (see CONTACT_HEADER_PROSE_OCCURRENCES).
CONTACT_HEADERS = [
    b"Personal email",
    b"Personal Email",
    b"personal_email",
    b"LinkedIn Profile",
    b"LinkedIn URL",
    b"linkedin_url",
    b"Student Email",
    b"Student Name",
    b"learner_email",
    b"Learner Email",
    b"Phone Number",
    b"Contact Number",
    b"Mobile Number",
    b"Email Address",
]

#: MEASURED 2026-09-20 WITH THIS EXACT LIST, the same way PROSE_OCCURRENCES was.
#: Across every tracked file, the densest legitimate prose is
#: `docs/CACHE-EXPOSURE.md` and `01-corpus-inventory.md` at 10 occurrences each,
#: then `docs/CONTACT-DATA.md` and `docs/A7B.md` at 9 — every one of them the
#: project's own record of why contact data is excluded. (This module itself
#: reaches 14 and is SELF_EXEMPT.)
#:
#: MEASURE WITH THE MATCHER YOU SHIP. The first draft of this comment claimed a
#: worst case of 19, taken from a case-insensitive grep over a wider pattern set
#: than the list below. The signatures here are case-sensitive byte literals, so
#: that number described a check nobody was running — a measured threshold
#: justified by a measurement of something else, which is this project's most
#: repeated mistake in miniature.
#:
#: CLAUDE.md §4: what would a correct answer excluded by this look like? It would
#: be a document discussing contact columns TEN TIMES more densely than
#: CACHE-EXPOSURE.md does. Nothing in the repository is close, and a file that is
#: has stopped being prose and become a pasted table — which is the thing being
#: caught. A data-shaped file is still caught at ONE.
CONTACT_HEADER_PROSE_OCCURRENCES = 100

#: CLASS 2 — LITERAL IDENTIFIERS. An actual address or profile URL that
#: identifies a specific human being.
#:
#: THIS CLASS HAS NO DENSITY RULE AND THE THRESHOLD IS ONE, ANYWHERE. The
#: near-miss was FOUR addresses in a Markdown file; a density rule calibrated
#: against prose would have waved it through, so the distinction that works for
#: headers is exactly the wrong one here. A header is a word. An address is a
#: person.
#:
#: Free-mail domains only, and that is a STATED LIMIT rather than an oversight —
#: see `KNOWN_GAP` below.
FREEMAIL_RE = re.compile(
    rb"[A-Za-z0-9._%+-]+@(?:gmail|googlemail|yahoo|ymail|rocketmail|outlook|"
    rb"hotmail|live|msn|icloud|proton|protonmail|aol|gmx|zoho|yandex|"
    rb"rediffmail|mail)\.[A-Za-z][A-Za-z.]{1,}",
    re.IGNORECASE,
)

#: A LinkedIn profile path identifies one person and nothing else. Measured
#: 2026-09-20: ZERO occurrences in tracked files, so this threshold costs
#: nothing today and fires the first time a roster is pasted in.
LINKEDIN_RE = re.compile(rb"linkedin\.com/(?:in|pub)/[A-Za-z0-9._%+-]",
                         re.IGNORECASE)

#: WHAT THIS CLASS DOES NOT CATCH, stated because A7B question 3 requires
#: knowing which mechanism holds a guarantee:
#:
#:   * a personal address at a CORPORATE domain (`someone@microsoft.com`) —
#:     indistinguishable by shape from an institutional one;
#:   * an address at `@interviewkickstart.com`. Those are work identities and
#:     several are already tracked ON PURPOSE in `config/people-firstnames.yaml`,
#:     carrying an `evidence:` field that records them as out-of-corpus facts
#:     entered by hand. Flagging those would flag the project's own recorded
#:     provenance — the "prose describing the exclusion" trap in a new costume;
#:   * a phone number, which has no shape distinct enough to match without
#:     flagging every id, row count and date in the repository.
#:
#: So this is a BACKSTOP, not the control. The control for the corpus is still
#: `sources.py`'s column allow-list; the control for THIS repository is that
#: somebody reads the refusal and redacts.
KNOWN_GAP = "corporate-domain addresses, @interviewkickstart.com, phone numbers"

#: An exemption needs a REASON, and a marker with no reason is itself an
#: offence — the same rule `test_taxonomy_single_source.py` uses for
#: `# taxonomy-literal-ok:`. An exemption with no cost is a hole.
CONTACT_OK_RE = re.compile(rb"contact-ok:[ \t]*(\S)")
CONTACT_OK_BARE_RE = re.compile(rb"contact-ok\b")

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


def _count_literals(blobs: list[bytes], sigs: list[bytes]) -> tuple[set[str], int]:
    found: set[str] = set()
    occurrences = 0
    for blob in blobs:
        for sig in sigs:
            c = blob.count(sig)
            if c:
                found.add(sig.decode())
                occurrences += c
    return found, occurrences


def _exempt_lines(lines: list[bytes]) -> tuple[set[int], int]:
    """Which line numbers a `contact-ok:` marker covers, and bare-marker count.

    SAME SCOPE RULE AS `taxonomy-literal-ok` in
    `tests/test_taxonomy_single_source.py`: a reasoned marker covers its own
    line and the next line that is actually code, so it may trail the offending
    line or sit in a comment block above it. Two marker conventions in one
    repository that scope differently is a trap; there is one rule.
    """
    exempt: set[int] = set()
    bare = 0
    for i, raw in enumerate(lines):
        if not CONTACT_OK_BARE_RE.search(raw):
            continue
        if not CONTACT_OK_RE.search(raw):
            bare += 1                      # a marker with no reason is a hole
            continue
        exempt.add(i)
        for j in range(i + 1, len(lines)):
            nxt = lines[j].strip()
            if not nxt or nxt.startswith(b"#"):
                continue
            exempt.add(j)
            break
    return exempt, bare


def _count_identifiers(blobs: list[bytes]) -> tuple[set[str], int, int]:
    """Contact identifiers, line by line, so an exemption can be line-scoped.

    Returns (kinds, occurrences, bare_markers). NEVER returns a matched value —
    a leak-detector that echoes the leak is not a detector.
    """
    kinds: set[str] = set()
    occurrences = 0
    bare_markers = 0
    for blob in blobs:
        lines = blob.split(b"\n")
        exempt, bare = _exempt_lines(lines)
        bare_markers += bare
        for i, line in enumerate(lines):
            if i in exempt:
                continue
            for kind, rx in (("personal-email", FREEMAIL_RE),
                             ("linkedin-profile", LINKEDIN_RE)):
                n = len(rx.findall(line))
                if n:
                    kinds.add(kind)
                    occurrences += n
    return kinds, occurrences, bare_markers


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

        try:
            blobs = list(_blobs(path))
        except Exception:                               # noqa: BLE001
            continue

        # --- class 0: payroll. Data-shaped needs one; prose needs a table. ---
        found, occurrences = _count_literals(blobs, SIGNATURES)
        if found and (data_shaped or occurrences >= PROSE_OCCURRENCES):
            hits.append((rel, f"HR/payroll: {', '.join(sorted(found))} "
                              f"({occurrences} occurrences)"))

        # --- class 1: contact column headers. Same shape of rule, own number. --
        c_found, c_occ = _count_literals(blobs, CONTACT_HEADERS)
        if c_found and (data_shaped
                        or c_occ >= CONTACT_HEADER_PROSE_OCCURRENCES):
            hits.append((rel, f"contact columns: {', '.join(sorted(c_found))} "
                              f"({c_occ} occurrences)"))

        # --- class 2: literal identifiers. One is enough, anywhere. -----------
        kinds, k_occ, bare = _count_identifiers(blobs)
        if kinds:
            hits.append((rel, f"contact identifiers: {', '.join(sorted(kinds))} "
                              f"({k_occ} occurrences) — threshold is 1"))
        if bare:
            hits.append((rel, f"bare `contact-ok` marker with no reason "
                              f"({bare}x) — an exemption with no cost is a hole"))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true",
                    help="scan only the staged diff (pre-commit hook use)")
    args = ap.parse_args()

    hits = scan(staged_only=args.staged)
    if not hits:
        print("no HR/payroll or contact content in tracked or staged files")
        return 0

    print("REFUSING: HR/payroll or contact content is about to enter git.",
          file=sys.stderr)
    for rel, sig in hits:
        print(f"  {rel}\n      matched signature: {sig!r}", file=sys.stderr)
    print("\nThis check is keyed on CONTENT, not on the path, so .gitignore and\n"
          "taxonomy.yaml -> excluded.files did not catch it — which is the point:\n"
          "those are one layer keyed on WHERE the file is. If this file genuinely\n"
          "belongs in the repository, that is a decision to record, not a check\n"
          "to silence.", file=sys.stderr)
    print("\nFor a `contact identifiers` hit the answer is almost always to\n"
          "REDACT and describe instead — a finding about contact data does not\n"
          "need the contact data to make its point. Where an identifier is\n"
          "genuinely required (a test fixture asserting an identity is refused),\n"
          "mark the line `contact-ok: <reason>`. A marker with no reason is\n"
          f"itself an offence. Known gap, on purpose: {KNOWN_GAP}.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
