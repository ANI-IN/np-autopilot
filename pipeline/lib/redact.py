"""The contact-data control for CONTENT, applied before anything reaches disk.

This is `docs/project-history/decisions/SCALE-PLAN.md` Q3's answer for the row-B content crawl.
`lib/sources.py` is an allow-list over `(file, sheet, column)` and a document
or a slide has none of those three, so the control has to MOVE rather than
widen — `docs/project-history/REGISTRY-INVENTORY.md` §8 Q3, in those words.

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

#: BUMP THIS WHENEVER A RULE BELOW CHANGES WHAT GETS REDACTED.
#:
#: The cache stores REDACTED text, so these rules are part of its contract: a
#: file unchanged in Drive is still stale if the rules that produced its text
#: have moved. The crawler re-exports on a version mismatch, which is what
#: keeps the cache from holding two versions at once — and a cache at two
#: versions cannot be reasoned about at all, because "why is this number
#: still here" has two possible answers.
#:
#:   1  initial — six-digit phone shape, no domain exemptions
#:   2  2026-09-29 audit: phone tightened on SHAPE (148 false positives, one
#:      of them destroying an HTTP-status-code slide); bare digit runs made
#:      reachable but conditioned on a phone word; RFC 2606 / RFC 6761
#:      reserved documentation domains exempted from email redaction
REDACTION_VERSION = 2

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

#: RFC 2606 §3 and RFC 6761 §6.3 — names the standards RESERVE for
#: documentation and testing, so that examples cannot collide with anything
#: real. `user@example.com` in an API-testing lesson is teaching content, and
#: redacting it removes curriculum while protecting nobody.
#:
#: This is a STANDARDS-DEFINED set, which is why it is allowed to be a list:
#: it is closed, published, and changes only when an RFC does. A list of
#: "domains we think are fake" would be the rotting name-list this project
#: keeps finding.
RESERVED_SLD = ("example.com", "example.net", "example.org")
RESERVED_TLD = (".example", ".test", ".invalid", ".localhost")


def _is_reserved_domain(addr: str) -> bool:
    """True for a reserved documentation name. Anchored at the END of the
    domain, never a substring: `example.com.somereal.net` is a REAL domain
    that merely contains a reserved one."""
    domain = addr.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if domain == "localhost":
        return True
    return domain in RESERVED_SLD or domain.endswith(RESERVED_TLD)
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/[\w\-/%.]+",
                      re.IGNORECASE)
#: Candidate shape. A MATCH HERE IS NOT A REDACTION — `_is_phone_shaped`
#: decides, below.
PHONE = re.compile(r"(?<![\w.])(?:(?P<intl>\+\d{1,3})[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?"
                   r"(?:\d{2,5}(?:[\s.\-]\d{2,5}){1,4}|\d{10,15})(?![\w.])")

# THE BARE-RUN ALTERNATIVE IS NEW, AND THE AUDIT IS WHY IT IS SAFE TO ADD.
# The previous pattern required a separator, so `4155550134` written solid was
# never a candidate at all — the `>= 10 digits` branch below could only ever
# fire on a group INSIDE a separated match, which is close to unreachable.
# Measuring the cache for bare runs found 32: 15 Unix timestamps, 1 ms
# timestamp, 16 O'Reilly ISBNs, 0 phones. So the branch was not dangerous; it
# was inert. It is made reachable here AND conditioned on a phone word beside
# it, which gains the protection without the 32 false positives.

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

#: Words that make a bare digit run a phone number rather than an identifier.
_PHONE_WORD = re.compile(r"\b(tel|telephone|phone|mobile|cell|fax|call|whatsapp|"
                         r"contact)\b", re.IGNORECASE)


def _bare_run(text: str) -> bool:
    """A single unseparated run of digits, e.g. `4155550134` or `1735689600`."""
    return bool(re.fullmatch(r"\d{10,15}", text.strip()))


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
    if max((len(g) for g in groups), default=0) >= 10:
        # A run of 10-15 digits with no separators. MEASURED ON THE CACHE,
        # 2026-09-29: 32 such runs across 919 texts and NOT ONE is a phone —
        # 15 Unix timestamps (JWT `exp`, `X-RateLimit-Reset`, inside the API
        # Testing curriculum), 1 millisecond timestamp, 16 O'Reilly ISBNs in
        # book URLs. So it needs a phone word beside it. The branch keeps its
        # capability and gains a condition rather than being deleted.
        window = m.string[max(0, m.start() - 45):m.end() + 25]
        return bool(_PHONE_WORD.search(window))
    return False

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
        elif name == "email":
            def _esub(m):
                return (m.group(0) if _is_reserved_domain(m.group(0))
                        else "<email redacted>")
            text, _ = rx.subn(_esub, text)
            n = text.count("<email redacted>")
        else:
            text, n = rx.subn(f"<{name} redacted>", text)
        if n:
            counts[name] = n
    return text, counts


def scan(text: str) -> dict[str, int]:
    """Counts only, never the values — for reporting on a file we do not emit."""
    out: dict[str, int] = {}
    for name, rx in CATEGORIES:
        if name == "phone":
            n = sum(1 for m in rx.finditer(text) if _is_phone_shaped(m))
        elif name == "email":
            n = sum(1 for m in rx.finditer(text)
                    if not _is_reserved_domain(m.group(0)))
        else:
            n = len(rx.findall(text))
        if n:
            out[name] = n
    return out
