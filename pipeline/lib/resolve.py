"""One name-resolution rule for the whole pipeline.

Three separate bugs had the same shape — several plausible targets, one chosen
with no signal to the caller:

  * `Agentic AI` matched four domains; caught before it shipped.
  * `ML` matched five; caught by the owner's sibling-domain challenge.
  * `Data Science` silently became `AI Data Science Switch-up (DS 2.0)`; caught
    while smoke-testing the staffing command.

So ambiguity is now the DEFAULT RETURN, not an error path. A caller that wants a
single answer must either get exactly one candidate or handle `Ambiguous`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s).lower()).strip()


def strip_paren(s: str) -> str:
    return norm(re.sub(r"\(.*?\)", " ", str(s)))


@dataclass(frozen=True)
class Ambiguous:
    """More than one candidate. NEVER collapse this to candidates[0]."""
    query: str
    candidates: tuple
    stage: str

    def as_dict(self):
        return {"ambiguous": list(self.candidates), "query": self.query,
                "matched_at": self.stage,
                "message": f"{self.query!r} matches {len(self.candidates)} candidates. "
                           "Ask which one; do not pick."}


def resolve(query: str, labels, *, allow_substring: bool = True):
    """Return one label, an Ambiguous, or None.

    Stages run most-specific first and STOP at the first stage that yields any
    candidate. A later, looser stage never rescues an ambiguous earlier one —
    that would be picking.
    """
    q = norm(query)
    if not q:
        return None
    labels = list(labels)

    stages = [
        ("exact", [l for l in labels if norm(l) == q]),
        ("paren-stripped", [l for l in labels if strip_paren(l) == q]),
    ]
    # A SINGLE-TOKEN query is tested on token boundaries before any prefix or
    # substring stage. "ML" is a prefix of "ML Switch-up (Adv ML)" purely by
    # coincidence, while appearing as a whole token in five domain names — the
    # prefix stage would have resolved it to one of them with no signal.
    if len(q.split()) == 1:
        tok = [l for l in labels if q in norm(l).split()]
        if tok:
            stages.append(("token", tok))
    stages.append(("prefix", [l for l in labels if norm(l).startswith(q)]))
    if allow_substring:
        stages.append(("substring", [l for l in labels if q in norm(l)]))

    for stage, hits in stages:
        uniq = sorted(set(hits))
        if not uniq:
            continue
        if len(uniq) == 1:
            return uniq[0]
        return Ambiguous(query=query, candidates=tuple(uniq), stage=stage)
    return None


def siblings(alias: str, labels):
    """Domains an alias could plausibly mean — word-boundary token sets only.

    Never substrings: norm("Product Management") CONTAINS "em", which once
    matched the domain EM through the letters in "managEMent".
    """
    at = set(norm(alias).split())
    out = []
    for l in labels:
        dt = set(norm(l).split())
        if at and dt and (at == dt or at <= dt or dt <= at):
            out.append(l)
    return sorted(set(out))
