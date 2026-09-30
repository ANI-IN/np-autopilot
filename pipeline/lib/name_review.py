"""Instructor labels that are not one person's name — REPORTED, never changed.

Owner review 2026-09-30 (origin: hand, Animesh Kumar): put the obviously
malformed legacy entries ("2- Prateek", "Agentic IP Instructors", "Amrita Ray,
Hemanth Pugaliya", and similar) in REVIEW-QUEUE for later; don't change them now.

WHAT IS NOT MALFORMED (CLAUDE.md §4). A credential ("Joseph Babcock, PhD"), a
nickname in brackets ("Chetan (Chet) Kunar"), initials ("A. Sindhuja",
"J.L.Bismarck Fuentes") and long multi-part names are real names. The six
retired name filters excluded 84 people for a PhD/Dr/MD and 28 for a middle
initial; these rules are written so that none of those shapes matches, and
tests/test_name_review.py holds that.

Each rule is a SHAPE that cannot be one person's name:
  enumerated   a list number in front of the name     "2- Prateek"
  collective   a group, a role or a hiring bucket      "Agentic IP Instructors"
  several      two or more people in one cell          "Amrita Ray, Hemanth Pugaliya"
  annotated    a multi-word note in brackets           "Nazeer Ahmed (yet to be trained)"
"""
from __future__ import annotations

import re

_CREDENTIAL = re.compile(
    r"^(ph\.?\s?d\.?|md|m\.d\.|dr\.?|mba|ms|msc|rhce|oscp|cissp|pmp|jr\.?|sr\.?|ii|iii)$", re.I)
_ENUMERATED = re.compile(r"^\s*\d+\s*[-.)]\s*\S")
_COLLECTIVE = re.compile(
    r"\b(instructors?|team|panel|smes?|tbd|tba|hiring|candidates?|trainers?|faculty|"
    r"pms|tpms)\b", re.I)
_BRACKET = re.compile(r"\(([^)]*)\)")


def _several(label: str) -> bool:
    """Two or more people: a separator whose parts are not credentials."""
    parts = [p.strip() for p in re.split(r"\s*(?:[,;/&+]|\band\b)\s*", label)]
    if len(parts) < 2:
        return False
    names = [p for p in parts if p and not _CREDENTIAL.match(p)]
    # "Robert/Shelby/" — the empty token after a separator is itself the tell
    return len(names) >= 2 or (len(names) == 1 and "" in parts[1:] and "/" in label)


def reasons(label: str) -> list[str]:
    label = label or ""
    out = []
    if _ENUMERATED.match(label):
        out.append("enumerated")
    if _COLLECTIVE.search(label):
        out.append("collective")
    if _several(label):
        out.append("several")
    for inner in _BRACKET.findall(label):
        if len(inner.split()) >= 2:
            out.append("annotated")
            break
    return out


RECOMMEND = {
    "enumerated": "strip the list number; keep label_raw",
    "collective": "not a person: take it out of the instructor type",
    "several": "split into one instructor per name; keep label_raw",
    "annotated": "move the note out of the name; keep label_raw",
}
