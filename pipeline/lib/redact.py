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
#: Deliberately broad. A false positive costs a redacted string; a false
#: negative costs a person's phone number in a graph. Requires a separator so
#: that version strings and slide numbers survive.
PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?"
                   r"\d{3,5}[\s.\-]\d{3,5}(?:[\s.\-]\d{2,5})?(?![\w.])")

#: Order matters: LinkedIn URLs are matched before the generic patterns so a
#: profile URL is reported as `linkedin` rather than shredded by PHONE.
CATEGORIES = (("linkedin", LINKEDIN), ("email", EMAIL), ("phone", PHONE))


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return (redacted text, {category: count}).

    The ONLY way content is allowed to leave this module.
    """
    counts: dict[str, int] = {}
    for name, rx in CATEGORIES:
        text, n = rx.subn(f"<{name} redacted>", text)
        if n:
            counts[name] = n
    return text, counts


def scan(text: str) -> dict[str, int]:
    """Counts only, never the values — for reporting on a file we do not emit."""
    out: dict[str, int] = {}
    for name, rx in CATEGORIES:
        n = len(rx.findall(text))
        if n:
            out[name] = n
    return out
