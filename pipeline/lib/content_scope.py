"""What the content crawl may open, download, and extract people from.

Every rule here is a decision from `docs/PRE-CRAWL-DECISIONS.md` or from the
owner's Phase-0 answers, and each is DECLARED rather than inferred from size or
shape — `CLAUDE.md` §4: a threshold that silently excludes is the failure this
project keeps rediscovering. Every skip carries its rule name so the crawler can
count skips per rule instead of reporting a smaller number with no account of
the difference.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# --------------------------------------------------------------------------
# Scope. The REGISTRY declares it; readability never does.
# --------------------------------------------------------------------------
#
# `docs/REGISTRY-INVENTORY.md` §12: row C is shared `anyone`/reader, so for C
# "the account can read it" and "it is in scope" are connected by the public
# internet. The crawler must never use the first as a proxy for the second.
#
# Row B only, per the owner's scope decision. Rows A and C are out of scope for
# this phase and are NOT listed here, so adding them is a deliberate edit.
ROW_B_ID = "19MxiYsE8B3T-O0VqnOF7gtU_7oxlRFJo"

SCOPE_ROOTS = {"B": ROW_B_ID}

#: The four approved domain folders, verbatim. Trailing spaces in other row-B
#: folder names are load-bearing elsewhere (`CLAUDE.md` §1); these four have
#: none, and the names are the citation key.
IN_SCOPE_DOMAINS = {
    "SD1: Full Stack": "full-stack",
    "SD2: Frontend": "frontend",
    "SD3: Backend Engineering": "backend",
    "SD4: Test Engineering": "testing",
}


def in_scope(folder_id: str) -> bool:
    """True only for a root the registry declares. Not 'can we read it'."""
    return folder_id in SCOPE_ROOTS.values()


def domain_in_scope(folder_name: str) -> bool:
    return folder_name in IN_SCOPE_DOMAINS


def domain_slug(folder_name: str) -> str | None:
    return IN_SCOPE_DOMAINS.get(folder_name)


# --------------------------------------------------------------------------
# D1 — people never come from deck content, and (deferred) never from filenames
# --------------------------------------------------------------------------

_DECK_MIMES = {
    "application/vnd.google-apps.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/x-iwork-keynote-sffkey",
}


def may_extract_people(mime: str) -> bool:
    """D1. False for every deck shape, at any confidence, with any flag.

    `docs/REGISTRY-INVENTORY.md` §7 measured why: four `Name, Role, Company`
    tuples on registry decks, two fabricated, structurally identical to the two
    real ones — and one fabricated name is also a rated instructor elsewhere.
    The distinction an extractor would have to make is not in the artefact.
    """
    return mime not in _DECK_MIMES


def may_extract_people_from_filename(filename: str) -> bool:
    """Always False, for now, and the reason is scope rather than D1.

    D1 governs slide CONTENT and is silent on filenames. `Uplevel Shared` names
    two decks per module with different first names, which looks like
    primary/alternate instructor — exactly what the owner deferred. Deferred
    means the answer is False until that phase runs, not that it is settled.
    """
    return False


# --------------------------------------------------------------------------
# D4 — a file owner is a DOMAIN. Nothing downstream may carry an address.
# --------------------------------------------------------------------------

def owner_domain(address: str | None) -> str | None:
    """The part after the '@', lowercased. Never the local part."""
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[1].strip().lower()


def provenance_is_clean(row: dict) -> bool:
    """D4's enforceable form: no provenance field may contain '@'.

    DERIVED over the row's values rather than checking a list of field names
    somebody maintains, so a provenance column added next year is covered by
    default. That is `docs/A7B.md` instance 8's fix, applied before the bug.
    """
    return not any("@" in str(v) for v in row.values() if v is not None)


# --------------------------------------------------------------------------
# Declared skips: D5, D6, and the learner-content rule
# --------------------------------------------------------------------------

class Decision(NamedTuple):
    action: str            # "walk" | "export" | "metadata_only" | "skip"
    rule: str | None = None
    reason: str | None = None


#: D6. Drive generates these with a predictable suffix, which is why the skip
#: can be DECLARED. A size cap would also catch them and would drop a 17.66 MB
#: teaching deck at the same time.
_RESPONSES_RE = re.compile(r"\(File responses\)\s*$")

#: D5. A consent licence keys on the PURPOSE of the reader, and no control in
#: this system has that axis. Ingesting the names without the restriction is
#: the worst option available.
_CONSENT_RE = re.compile(r"^\s*SMEs consent\s*$", re.IGNORECASE)

#: Owner's Phase-0 answer 5. Learner-authored material inside an assignment
#: review: recorded as metadata, never opened.
_LEARNER_PATH_RE = re.compile(
    r"/Assignment Review(?:\s*-\s*[^/]+)?/", re.IGNORECASE)
_LEARNER_FILE_RE = re.compile(
    r"students?[ _-]*interactions?", re.IGNORECASE)

_MEDIA_PREFIXES = ("video/", "audio/", "image/")
_ARCHIVE_MIMES = {
    "application/zip", "application/x-zip-compressed", "application/x-tar",
    "application/gzip", "application/x-7z-compressed",
}


def classify_folder(path: str, name: str) -> Decision:
    """Walk it, or skip it by a named rule."""
    if _RESPONSES_RE.search(name):
        return Decision("skip", "D6",
                        "Drive-generated form-response folder: third-party "
                        "uploads, a learner name in every path, no curricular "
                        "content")
    if _CONSENT_RE.match(name):
        return Decision("skip", "D5",
                        "consent register: a per-purpose licence that no "
                        "property, node flag or origin can express")
    return Decision("walk")


def classify_file(path: str, name: str, mime: str) -> Decision:
    """Export its text, record it as metadata only, or skip it by name.

    Order is deliberate. The learner rule is checked BEFORE the media rule so a
    learner `.zip` is reported under `learner-content` rather than under
    `no-media-download` — two different reasons to hold the same file back, and
    collapsing them would lose the one that matters.
    """
    if _LEARNER_PATH_RE.search(path) or _LEARNER_FILE_RE.search(name):
        return Decision("metadata_only", "learner-content",
                        "learner-authored material inside an assignment "
                        "review; name and path recorded, text never exported")
    if mime.startswith(_MEDIA_PREFIXES) or mime in _ARCHIVE_MIMES:
        return Decision("metadata_only", "no-media-download",
                        "media or archive: 15.55 GiB of the 16.67 GiB measured "
                        "in scope, and none of it parses into curriculum")
    return Decision("export")
