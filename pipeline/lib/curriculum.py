"""Module identity, sequence, and the program week — with the week semantics
the corpus owner fixed in the Phase-0 answers.

THE ONE THING TO UNDERSTAND BEFORE CHANGING ANYTHING HERE.

A folder called `Week 3` inside a domain folder **is not a week.** It is local
sequencing, used to order the modules within that domain. The real week is the
PROGRAM week and it comes only from a curriculum document — the SD2 KYP, the
SD4 handbook, an outline. Measured 2026-09-29: the SD2 KYP places its four
modules at program weeks 9-12 while the folders call them `Week 1..4`, because
weeks 1-5 are Algorithms and 6-8 is Scalable System Design.

**The difference of 8 is expected, not a conflict** — and it must never be
used as an offset. A module can sit at a different program week in a different
program, so a program week that was computed rather than read is a fact with no
source. `program_week_from_local` exists only to refuse, loudly, and to give
that refusal a name somebody can grep for.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import NamedTuple

from . import ids as _ids

#: A curriculum document is one node type with a kind, per the owner's answer 3.
CURRICULUM_KINDS = ("kyp", "handbook", "outline", "lesson_plan")


class ArithmeticWeekRefused(RuntimeError):
    """Raised when someone tries to derive a program week from a local one."""


class ProgramWeek(NamedTuple):
    value: int
    source_kind: str
    source_file: str


class WeekRange(NamedTuple):
    value: str
    recovered_from_date_coercion: bool


# --------------------------------------------------------------------------
# Sequence — what a `Week N` folder actually encodes
# --------------------------------------------------------------------------

_SEQ_RE = re.compile(r"^\s*Week\s*(\d+)\s*$", re.IGNORECASE)


def module_sequence_from_folder(folder_name: str) -> int | None:
    """`Week 3` -> 3, as a SEQUENCE within the domain. Never a week."""
    m = _SEQ_RE.match(folder_name)
    return int(m.group(1)) if m else None


def week_node_from_folder(folder_name: str) -> None:
    """Always None. A folder name is not evidence of a program week.

    Kept as a named function rather than an absent one so that a future caller
    reaching for "the week from the folder" finds a refusal with a reason,
    instead of writing the two-line regex themselves.
    """
    return None


# --------------------------------------------------------------------------
# Program week — only ever read from a curriculum document
# --------------------------------------------------------------------------

def program_week(value: int | None, source_kind: str | None,
                 source_file: str | None) -> ProgramWeek:
    """A program week that cannot exist without the document it came from."""
    if value is None:
        raise ValueError("a program week needs a value")
    if not source_kind or not source_file:
        raise ValueError(
            "a program week must carry the curriculum source it came from: "
            f"got kind={source_kind!r} file={source_file!r}. A module can sit "
            "at different program weeks in different programs, so a week with "
            "no source is a fact with nowhere to point.")
    if source_kind not in CURRICULUM_KINDS:
        raise ValueError(f"unknown curriculum kind {source_kind!r}; "
                         f"expected one of {CURRICULUM_KINDS}")
    return ProgramWeek(int(value), source_kind, source_file)


def program_week_from_local(local: int, offset: int) -> ProgramWeek:
    """Never returns. The owner's rule, given a name so it can be grepped."""
    raise ArithmeticWeekRefused(
        f"refusing to derive a program week from local={local} + offset={offset}. "
        "The offset of 8 between folder sequence and program week is EXPECTED "
        "(weeks 1-5 Algorithms, 6-8 Scalable System Design) and is not a "
        "licence to compute one from the other: a module sits at different "
        "program weeks in different programs. Read it from a curriculum "
        "document, or report a gap.")


def program_week_or_gap(week: ProgramWeek | None) -> tuple[ProgramWeek | None, str | None]:
    """(week, None) or (None, reason). SD3 has no week column anywhere today."""
    if week is None:
        return None, "no-curriculum-week"
    return week, None


# --------------------------------------------------------------------------
# Date coercion — Sheets turned the week RANGES into dates
# --------------------------------------------------------------------------
#
# `1-5` became 2023-01-05 and `6-8` became 2023-06-08 in both outlines. The SD2
# KYP PDF still carries them as text, so the PDF is preferred; this recovers the
# range only where no better source exists, and flags every recovery so
# validate.py can count them.

_COERCED_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T]00:00:00)?\s*$")


def recover_week_range(raw: str) -> WeekRange:
    """`2023-01-05 00:00:00` -> `1-5`, flagged. `9` -> `9`, unflagged."""
    text = str(raw).strip()
    m = _COERCED_RE.match(text)
    if not m:
        return WeekRange(text, False)
    _, month, day = m.groups()
    return WeekRange(f"{int(month)}-{int(day)}", True)


# --------------------------------------------------------------------------
# Module identity — (domain_slug, sequence). Labels never key anything.
# --------------------------------------------------------------------------

def module_key(domain_slug: str, sequence: int) -> str:
    """Deterministic, and deliberately not derived from the label.

    The existing graph holds 922 label-keyed `module` nodes. Row B will produce
    modules with the same labels that are not provably the same things, so a
    label key here would merge them silently on the first build.
    """
    # Minted by the SHARED function so the id matches the DB's id_shape
    # constraint. It used to be a bare sha256 hexdigest, which is why all
    # 5,811 content nodes were unprojectable — see pipeline/lib/ids.py.
    return _ids.compound("module", "rowB", domain_slug, int(sequence))


def normalise_for_join(label: str) -> str:
    """Whitespace, case and punctuation ONLY.

    It deliberately does NOT expand `JS` to `JavaScript` or `FE` to `Frontend`.
    Those expansions are what made four of four SD2 module names look like
    exact matches during Phase 0, and the owner's answer is that each one is a
    curated alias confirmed individually. An implicit expansion here would
    apply them all at once, invisibly, which is the `lib/resolve.py` failure in
    a different module.
    """
    s = unicodedata.normalize("NFKD", str(label)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def propose_alias(label: str, domain_slug: str, sequence: int,
                  candidate_id: str) -> dict:
    """A row for `config/module-aliases-review.yaml`. Never a join."""
    return {
        "label": label,
        "domain": domain_slug,
        "sequence": int(sequence),
        "module_key": module_key(domain_slug, sequence),
        "candidate": candidate_id,
        "confirmed": False,
        "note": "proposed by the row-B content crawl; confirm or delete. "
                "An unconfirmed row is never applied.",
    }


# --------------------------------------------------------------------------
# SD3's anomaly — the module comes from the module-named folder
# --------------------------------------------------------------------------
#
# All five Backend week folders sit under `Module-1: Database Design`, so a
# rule that takes the module from the top of the path files every Backend
# module under Database Design. The module-named folder NEAREST the file wins.

_MODULE_FOLDER_RES = (
    re.compile(r"^Module-\d+:\s*.+$"),               # SD3
    re.compile(r"^\d+\.\s*Module\s*-\s*.+-\s*Content$"),   # SD1
    re.compile(r"^\d+\s*[-:]\s*.+$"),                # SD1/2/3/4 under Week N
)


def module_folder_from_path(path: str) -> str | None:
    """The module-named folder closest to the file, never the parent path."""
    parts = [p for p in path.strip("/").split("/") if p]
    for part in reversed(parts):
        for rx in _MODULE_FOLDER_RES:
            if rx.match(part):
                return part
    return None
