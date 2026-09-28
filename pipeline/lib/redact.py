"""The contact-data control for CONTENT, applied before anything reaches disk.

This is `docs/SCALE-PLAN.md` Q3's answer for the row-B content crawl.
`lib/sources.py` is an allow-list over `(file, sheet, column)` and a document
or a slide has none of those three, so the control has to MOVE rather than
widen — `docs/REGISTRY-INVENTORY.md` §8 Q3, in those words.

TWO THINGS THIS DELIBERATELY DOES NOT DO.

**No density threshold.** `check_no_payroll_committed.py` uses one and is right
to: a payroll signature is a column HEADER, and headers appear in prose that
describes the exclusion. Carrying that rule here would have waved through the
near-miss the class was built for — four personal addresses in a Markdown file
(`docs/A7B.md`, "the borrowed rule"). **A header is a word; an address is a
person.** Threshold is one, anywhere.

**No equality matching.** D4's contact strip compared spreadsheet headers to
node property keys by equality and caught 15 of 35 contact-shaped headers.
Matching here is substring and case-insensitive.

It is a REDACTOR, not a detector: the caller gets text with the values already
removed, so there is no path where a caller forgets to act on a finding.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/[\w\-/%.]+",
                      re.IGNORECASE)
#: Candidate shape. A MATCH HERE IS NOT A REDACTION — `_is_phone_shaped`
#: decides, below.
PHONE = re.compile(r"(?<![\w.])(?:(?P<intl>\+\d{1,3})[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?"
                   r"\d{2,5}(?:[\s.\-]\d{2,5}){1,4}(?![\w.])")

#: AUDITED AGAINST THE RUN-3 CACHE, 2026-09-29, AND TIGHTENED.
#:
#: The first version required only `\d{3,5}[sep]\d{3,5}` — six digits with a
#: separator. Measured over 919 exported files: **148 phone redactions across
#: 132 files, and not one had phone-shaped surrounding context.** The cost was
#: not over-redaction of contact data, it was DESTRUCTION OF CURRICULUM:
#:
#:     "what does 200 300 400 500 HTTP Response code mean?"
#:       -> "what does 200 <phone redacted> 500 HTTP Response code mean?"
#:
#: on a slide teaching HTTP status codes. Also hit: a year range on a careers
#: deck, ports, row counts, and a teaching dataset of tournament dates repeated
#: across five Databases decks.
#:
#: `CLAUDE.md` §4 asks what a correct answer excluded by a rule would look
#: like. Here it looks like `300 400`. So the shape is narrowed — and narrowed
#: on SHAPE, never on density or count, because A7B's borrowed rule still
#: holds: one real number is enough.
#:
#: A candidate is a phone only if ONE of these is true:
#:   * it carries an international `+NN` prefix; or
#:   * it has 3+ separated groups AND at least one group of 4+ digits
#:     (real numbers do; `200 300 400 500` does not); or
#:   * it has 10+ digits in total.
_MIN_DIGITS = 7
_MAX_DIGITS = 15


def _is_phone_shaped(m: "re.Match") -> bool:
    text = m.group(0)
    groups = re.findall(r"\d+", text)
    n = sum(len(g) for g in groups)
    if not (_MIN_DIGITS <= n <= _MAX_DIGITS):
        return False
    if m.groupdict().get("intl"):
        return True
    if (len(groups) >= 3 and any(len(g) >= 4 for g in groups)
            and all(len(g) >= 3 for g in groups)):
        # Every group >= 3 is what separates `619 555 0147` from
        # `1998 04 1981` — a tournament date in a Databases teaching dataset,
        # repeated across five decks. A 2-digit group mid-number is a date or
        # an index, not a national format; the international ones that do use
        # short groups carry a `+` prefix and are accepted above.
        return True
    return max((len(g) for g in groups), default=0) >= 10

#: Order matters: LinkedIn URLs are matched before the generic patterns so a
#: profile URL is reported as `linkedin` rather than shredded by PHONE.
CATEGORIES = (("linkedin", LINKEDIN), ("email", EMAIL), ("phone", PHONE))


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return (redacted text, {category: count}).

    The ONLY way content is allowed to leave this module.
    """
    counts: dict[str, int] = {}
    for name, rx in CATEGORIES:
        if name == "phone":
            def _sub(m):
                return "<phone redacted>" if _is_phone_shaped(m) else m.group(0)
            text, seen = rx.subn(_sub, text)
            n = text.count("<phone redacted>")
        else:
            text, n = rx.subn(f"<{name} redacted>", text)
        if n:
            counts[name] = n
    return text, counts


def scan(text: str) -> dict[str, int]:
    """Counts only, never the values — for reporting on a file we do not emit."""
    out: dict[str, int] = {}
    for name, rx in CATEGORIES:
        n = (sum(1 for m in rx.finditer(text) if _is_phone_shaped(m))
             if name == "phone" else len(rx.findall(text)))
        if n:
            out[name] = n
    return out
