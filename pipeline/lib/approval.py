"""Read D2a's approval block, and refuse while it is blank.

`pipeline/project_graph.py` refuses `--scope full` and points at
`docs/INGEST-SCOPE-REVERSAL.md`, whose approval block is deliberately empty.
This is the same mechanism for the row-B content crawl, and it exists because
`docs/PRE-CRAWL-DECISIONS.md` itself records the failure it prevents:

    | D1 | no people from slides | — | recorded only |
    | D2 | fork A                | — | recorded only |
    | D4 | owner domain          | — | recorded only |
    | D6 | (File responses)      | — | recorded only |

    "Five of six are prose, and prose is what instance 9 is about."

DERIVED, NOT ASSERTED. The block is parsed on every run rather than a flag
being set once, so blanking it stops the crawler again — the property
`project_graph.py` gained when its hardcoded refusal was replaced by a query.
A gate that can only be opened is not a gate.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from pipeline.lib.paths import REPO_ROOT

DECISIONS_FILE = REPO_ROOT / "docs" / "PRE-CRAWL-DECISIONS.md"

#: The four domain labels exactly as the approval block writes them, mapped to
#: the row-B folder names. Written here rather than derived from
#: content_scope.IN_SCOPE_DOMAINS on purpose: the approval block is a human
#: artefact, and a rename in code must not silently re-interpret a signature
#: somebody already gave.
_DOMAIN_LINES = {
    "SD1 Full Stack": "SD1: Full Stack",
    "SD2 Frontend": "SD2: Frontend",
    "SD3 Backend Engineering": "SD3: Backend Engineering",
    "SD4 Test Engineering": "SD4: Test Engineering",
}


class NotApproved(RuntimeError):
    """The block is blank, incomplete, or names no domain."""


class Approval(NamedTuple):
    approved_by: str
    date: str
    domains: list[str]
    source: str


_BY_RE = re.compile(r"^\s*Approved by:\s*(.+?)\s*$", re.MULTILINE)
_DATE_RE = re.compile(r"^\s*Date:\s*(.+?)\s*$", re.MULTILINE)
#: A blank field is a run of underscores. Anything else is a value.
_BLANK_RE = re.compile(r"^_+$")


def _value(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text)
    if not m:
        return None
    v = m.group(1).strip()
    return None if not v or _BLANK_RE.match(v) else v


def read_d2a(path: Path | None = None) -> Approval | None:
    """The approval, or None when the block is not filled in."""
    p = Path(path) if path else DECISIONS_FILE
    text = p.read_text(encoding="utf-8")
    by, date = _value(_BY_RE, text), _value(_DATE_RE, text)
    if not by or not date:
        return None
    domains = [folder for line, folder in _DOMAIN_LINES.items()
               if re.search(r"\[\s*[xX]\s*\]\s*" + re.escape(line), text)]
    return Approval(by, date, domains, str(p))


def require_d2a(path: Path | None = None) -> Approval:
    """The approval, or raise NotApproved naming the file to fill in."""
    p = Path(path) if path else DECISIONS_FILE
    got = read_d2a(p)
    if got is None:
        raise NotApproved(
            f"D2a is not approved. The approval block in {p} is blank.\n"
            "\nThis crawl reads curriculum documents and slide text from other\n"
            "people's Drive folders. D2a is the record that the scope was\n"
            "decided rather than assumed — fill in 'Approved by' and 'Date',\n"
            "tick the domains, and run again. A proposal is not a control.")
    if not got.domains:
        raise NotApproved(
            f"D2a is signed in {p} but no domain is ticked, so the approved\n"
            "scope is empty. Tick the domains that are approved rather than\n"
            "leaving the crawler to infer that a signature means all of them.")
    return got
