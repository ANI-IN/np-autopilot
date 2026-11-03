"""Input validation for KB writes. Hand-written rather than pydantic/zod: the
Vercel bundle is at its size limit (pyproject.toml header), and these rules are
few enough to read in one sitting.

Every validator returns the CLEANED value or raises Invalid naming the field.
The database re-checks the structural rules (constraints in 0022); this layer
exists to give a person a readable message before the database gives a code.
"""
from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from .errors import Invalid

NAME_MAX = 300
SUMMARY_MAX = 2000
BODY_MAX = 100_000
NOTE_MAX = 2000
URL_MAX = 2048
RESOURCE_KINDS = ("link", "doc", "sheet", "slides", "video", "pdf", "folder", "other",
                  "recording", "assignment", "solution", "repo")      # 0026 widened the CHECK  # taxonomy-literal-ok: a KB resource kind (migration 0026 CHECK), not the corpus-graph taxonomy
LINK_STATUSES = ("ok", "needs_auth", "forbidden", "broken", "timeout", "unreachable")
NODE_STATUSES = ("draft", "active")
PAGE_DEFAULT, PAGE_MAX = 50, 200


def text(body: dict, field: str, *, required: bool = False, max_len: int,
         allow_empty: bool = True) -> str | None:
    if field not in body or body[field] is None:
        if required:
            raise Invalid(f"{field} is required", field=field)
        return None
    v = body[field]
    if not isinstance(v, str):
        raise Invalid(f"{field} must be text", field=field)
    v = v.strip()
    if not v and (required or not allow_empty):
        raise Invalid(f"{field} cannot be empty", field=field)
    if len(v) > max_len:
        raise Invalid(f"{field} is {len(v)} characters; the limit is {max_len}", field=field)
    return v or None


def name_problem(value, field: str = "name") -> str | None:
    """THE record-name rule, or None when the name is acceptable. One rule for
    every writer (run 6, F4 "one service layer"): name() below, so the API, the
    MCP tools and the Sheets import, AND the sync from the original site's
    tables (sync.desired_state), which used to carry its own copy of it.
    A name is text; not empty once trimmed; at most NAME_MAX characters; and
    never an e-mail address or a URL (CLAUDE.md: an `@` in a name cannot be a
    name)."""
    if not isinstance(value, str):
        return f"{field} must be text"
    s = value.strip()
    if not s:
        return f"{field} cannot be empty"
    if len(s) > NAME_MAX:
        return f"{field} is {len(s)} characters; the limit is {NAME_MAX}"
    if "@" in s or re.search(r"https?://", s, re.I):
        return f"{field} cannot contain an email address or a URL; put links in resources"
    return None


def name(body: dict, field: str = "name", *, required: bool = True) -> str | None:
    if field not in body or body[field] is None:
        if required:
            raise Invalid(f"{field} is required", field=field)
        return None
    problem = name_problem(body[field], field)
    if problem:
        raise Invalid(problem, field=field)
    return re.sub(r"\s+", " ", body[field].strip())


def uid(value, field: str, *, required: bool = True) -> str | None:
    if value in (None, ""):
        if required:
            raise Invalid(f"{field} is required", field=field)
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        raise Invalid(f"{field} is not a valid id", field=field) from None


def version(body: dict) -> int:
    v = body.get("version")
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise Invalid("version is required: send the version you loaded, so a change "
                      "made since then is detected rather than overwritten", field="version")
    return v


def url(body: dict, field: str = "url") -> str:
    v = text(body, field, required=True, max_len=URL_MAX, allow_empty=False)
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc or " " in v or "." not in p.netloc:
        raise Invalid(f"{field} must be a full http(s) URL", field=field)
    return v


def choice(body: dict, field: str, options, default=None):
    v = body.get(field, default)
    if v is None:
        return None
    if v not in options:
        raise Invalid(f"{field} must be one of {', '.join(options)}", field=field)
    return v


def props(body: dict) -> dict | None:
    v = body.get("props")
    if v is None:
        return None
    if not isinstance(v, dict):
        raise Invalid("props must be an object", field="props")
    if len(str(v)) > 20_000:
        raise Invalid("props is too large", field="props")
    return v


def limit(params: dict) -> int:
    raw = params.get("limit", PAGE_DEFAULT)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise Invalid("limit must be a number", field="limit") from None
    if n < 1:
        raise Invalid("limit must be at least 1", field="limit")
    return min(n, PAGE_MAX)


def only(body: dict, allowed: set[str]) -> None:
    unknown = set(body) - allowed
    if unknown:
        raise Invalid(f"unknown field(s): {', '.join(sorted(unknown))}", fields=sorted(unknown))
