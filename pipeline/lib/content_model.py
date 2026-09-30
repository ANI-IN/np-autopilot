"""The row-B content model: how a cached file becomes nodes, edges and topics.

Pure functions, so the pass script is a thin caller and every rule here is
testable without a Drive or a cache — the same shape `lib/content_scope.py`
has for the crawl.

THE RULES THIS ENCODES, each an owner decision or a standing rule:

  module identity   (domain_slug, sequence). NEVER the label — `API Design`
                    exists in Backend and `API Design and Implementation` in
                    Full Stack, and the projection already holds 922
                    label-keyed modules that these must not silently join.
  program week      from a curriculum document, or from the owner's hand fact
                    for SD1 only. SD3 is null and reports a gap. Never
                    computed from a folder sequence — `curriculum.py` raises.
  attachment        live classes, assignments, reviews and decks hang off the
                    MODULE, not the week, because a week exists only where a
                    curriculum doc states one and SD3 has none.
  topics            must carry a locator (slide or page). A topic that cannot
                    cite where it came from is not evidence.
  D1                a deck never yields a person. Not ranked, not flagged.
  unavailable       a download-disabled file is still a node, marked, with no
                    content and no inferred content.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import NamedTuple

from pipeline.lib import curriculum as cur

# ---------------------------------------------------------------------------
# Module identity
# ---------------------------------------------------------------------------


class ModuleRef(NamedTuple):
    domain: str
    sequence: int
    label: str


#: Ordered: the most specific shape first. Each domain folder in row B uses a
#: different one, and two of them use more than one.
_MODULE_SHAPES = (
    re.compile(r"/Uplevel [Ss]hared/Week (?P<seq>\d+)/\d+\s*[-:]\s*(?P<label>[^/]+)"),
    re.compile(r"Content Repo/Week (?P<seq>\d+)/\d+\s*[-:]\s*(?P<label>[^/]+)"),
    re.compile(r"/(?P<seq2>\d+)\.\s*Module\s*-\s*(?P<label2>.+?)\s*-\s*Content(?:/|$)"),
    re.compile(r"/Module-(?P<seq3>\d+):\s*(?P<label3>[^/]+)"),
)


def parse_module(path: str) -> ModuleRef | None:
    """The module a path belongs to, or None.

    ORDER IS THE POINT. SD3 nests every week folder under
    `Module-1: Database Design`, so the `Module-N:` shape must be tried LAST —
    a path matching both is a week inside Module-1, and the week is the truth.
    """
    domain = path.strip("/").split("/")[0]
    for rx in _MODULE_SHAPES:
        m = rx.search(path)
        if not m:
            continue
        g = m.groupdict()
        seq = g.get("seq") or g.get("seq2") or g.get("seq3")
        label = g.get("label") or g.get("label2") or g.get("label3")
        return ModuleRef(domain, int(seq), label.strip())
    return None


def module_key(domain_slug: str, sequence: int) -> str:
    return cur.module_key(domain_slug, sequence)


# ---------------------------------------------------------------------------
# Curriculum documents
# ---------------------------------------------------------------------------

_KIND_PATTERNS = (
    ("kyp", re.compile(r"\bkyp\b", re.I)),
    ("handbook", re.compile(r"handbook", re.I)),
    ("lesson_plan", re.compile(r"lesson\s*plan", re.I)),
    ("outline", re.compile(r"course outline|curriculum outline|detailed course",
                           re.I)),
)


def curriculum_kind(name: str) -> str | None:
    """Which kind of curriculum document, or None for ordinary content.

    Measured 2026-09-29: exactly ONE `kyp` exists across 991 files in the four
    approved domains. `curriculum_doc` carries the kind rather than a `kyp`
    node type existing, so that SD1, SD3 and SD4 having no KYP reads as a
    CONTENT GAP instead of being hidden inside a node type.
    """
    for kind, rx in _KIND_PATTERNS:
        if rx.search(name):
            return kind
    return None


# ---------------------------------------------------------------------------
# Program week
# ---------------------------------------------------------------------------
#
# SD1 only, from `config/out-of-corpus-facts.yaml -> sd1-full-stack-program-
# weeks`: DSA occupies program weeks 1-5 and Scalable Systems Design 6-8, so
# the five Full Stack modules are weeks 9-13 in outline order.
#
# The +8 is NOT a rule and is not applied anywhere else. It is the content of
# one hand fact about one domain, and `cur.program_week_from_local` still
# refuses to compute a week from a sequence.

_FACTS_FILE = "config/out-of-corpus-facts.yaml"
_FACT_ID = "rowb-program-weeks"
_WEEKS_CACHE: dict | None = None


def _program_weeks() -> dict:
    """Per-module program weeks, READ FROM THE FACT FILE, never computed.

    A dict of explicit values, so adding a domain means adding its numbers
    rather than extending an arithmetic. `cur.program_week_from_local` still
    raises on any attempt to derive one from a folder sequence — the offset of
    8 is a fact about these four programmes, not a rule.
    """
    global _WEEKS_CACHE
    if _WEEKS_CACHE is None:
        import yaml
        from pipeline.lib.paths import REPO_ROOT
        data = yaml.safe_load((REPO_ROOT / _FACTS_FILE).read_text(encoding="utf-8"))
        fact = next(f for f in data["facts"] if f["id"] == _FACT_ID)
        _WEEKS_CACHE = {d: {int(k): int(v) for k, v in w.items()}
                        for d, w in fact["weeks"].items()}
    return _WEEKS_CACHE


_FACT_CITATION = (f"{_FACTS_FILE} -> {_FACT_ID} "
                  "(origin: hand, Animesh Kumar, 2026-09-29)")


def program_week_for(domain_slug: str, sequence: int) -> cur.ProgramWeek | None:
    """The program week, or None with a gap reported by the caller."""
    value = _program_weeks().get(domain_slug, {}).get(sequence)
    if value is None:
        return None
    return cur.ProgramWeek(value, "hand", _FACT_CITATION)


# ---------------------------------------------------------------------------
# Role of a file within its module
# ---------------------------------------------------------------------------

_ROLES = (
    ("review", re.compile(r"/Assignment Review(?:\s*-\s*[^/]+)?/", re.I)),
    ("class", re.compile(r"/(?:\d+\.\s*)?Live[ _]Class[^/]*/|/Slides?/", re.I)),
    ("task", re.compile(r"/(?:\d+\.\s*)?Assignments?[^/]*/|timed[ _-]?test", re.I)),
    ("practice", re.compile(r"/(?:\d+\.\s*)?Practice[^/]*/", re.I)),
    ("foundation", re.compile(r"/(?:\d+\.\s*)?Found\w*[^/]*/", re.I)),
)

_DECK_MIMES = {
    "application/vnd.google-apps.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
}

_ARCHIVE_MIMES = {"application/zip", "application/x-zip-compressed"}


def role_of(path: str) -> str | None:
    """Which part of the module a file plays, from the folder that names it.

    Returns a ROLE name (`review`, `class`, `task`, ...), deliberately NOT a
    taxonomy node type. An internal vocabulary that shadows the taxonomy's is
    a second source of truth for the same words, which is what
    `tests/test_taxonomy_single_source.py` refuses.

    Assignment review is checked FIRST: it lives inside an assignment folder,
    so a looser order files every review as an assignment.
    """
    for role, rx in _ROLES:
        if rx.search(path):
            return role
    return None


def is_deck(mime: str) -> bool:
    return mime in _DECK_MIMES


def is_repo(mime: str, name: str) -> bool:
    return mime in _ARCHIVE_MIMES or name.lower().endswith((".zip", ".tar.gz"))


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


class Topic(NamedTuple):
    label: str
    locator_kind: str      # "slide" | "page" | "tab" | "row"
    locator: int


_LOCATOR = re.compile(r"^\[(slide|page|tab)\s+([^\]]+)\]\s*$", re.I)

#: A topic line has to look like a heading, not a sentence. Measured against
#: the real decks: bullets and titles are short and carry few stop words;
#: prose runs long. This RANKS nothing and EXCLUDES nothing that is shaped
#: like a topic — it is a shape test, in the sense CLAUDE.md §4 permits:
#: a 300-character paragraph cannot be a topic label at all.
_MAX_TOPIC_CHARS = 90
_MIN_TOPIC_CHARS = 3


def topics_from_text(text: str, source: str) -> list[Topic]:
    """Topics with the slide, page or tab they came from.

    A TOPIC IS A TITLE, NOT EVERY LINE. Taking every 3-90 character line under
    a locator produced 17,392 topics across 20 modules on the first build —
    5,637 on Backend's API Design alone — including `Objectives`, `Agenda`,
    `Pause for Questions`, `Master API Development concepts.` and `<NAME>`,
    a template placeholder. "API Design covers Pause for Questions" is not a
    gap in the data; it is a confidently wrong answer.

    This is NOT `CLAUDE.md` §4's threshold hiding correct answers. It is D1's
    prior question in a new place: is a body bullet a TOPIC at all, or is it
    content ABOUT one? The title is the topic; the bullets are its body, and
    they stay in the cache with provenance either way.

    Two sources, in the order the owner specified:
      curriculum_doc  a `[tab ...]` block is a lesson plan or outline. Its
                      rows are `Topic | Flow | Learning Objectives`, so the
                      topic is the row's FIRST cell and the rest is what the
                      topic covers.
      deck / doc      the first non-empty line after each `[slide N]` or
                      `[page N]` marker.
    """
    out: list[Topic] = []
    kind, num, want_title = None, None, False
    header_seen = False
    for raw in text.splitlines():
        line = raw.strip()
        m = _LOCATOR.match(line)
        if m:
            kind = m.group(1).lower()
            digits = re.search(r"\d+", m.group(2))
            num = int(digits.group()) if digits else _tab_ordinal(m.group(2))
            want_title, header_seen = True, False
            continue
        if kind is None or num is None or not line:
            continue

        if kind == "tab":
            # ` | ` FIRST: extract_text._xlsx joins cells with it, and a cell
            # may legitimately contain a comma. Splitting on the comma first
            # returned the whole row, header included.
            cell = (line.split(" | ", 1)[0] if " | " in line
                    else line.split(",", 1)[0]).strip().strip('"')
            if not header_seen and cell.lower() in _TAB_HEADERS:
                header_seen = True          # the header row names the columns
                continue
            if _is_topic_label(cell):
                out.append(Topic(cell, kind, num))
            continue

        if want_title:
            want_title = False              # ONE title per slide or page
            if _is_topic_label(line):
                out.append(Topic(line, kind, num))
    return out


#: Column headers a lesson-plan tab uses for its first column. Skipped so the
#: word `Topic` does not become a topic.
_TAB_HEADERS = {"topic", "topics", "module", "week", "weeek", "concepts",
                "interview questions", "coursework", ""}

_TAB_ORDINALS: dict[str, int] = {}


def _tab_ordinal(name: str) -> int:
    """A tab has a name, not a number, and provenance needs something stable
    to cite. The ordinal is assigned in first-seen order per process."""
    return _TAB_ORDINALS.setdefault(name.strip(), len(_TAB_ORDINALS) + 1)


def _is_topic_label(s: str) -> bool:
    """Shape only. A 300-character paragraph cannot be a topic label at all —
    the same kind of test CLAUDE.md §4 permits for an `@` in a name."""
    if not (_MIN_TOPIC_CHARS <= len(s) <= _MAX_TOPIC_CHARS):
        return False
    return bool(re.search(r"[A-Za-z]", s))


def topic_key(domain_slug: str, sequence: int, label: str) -> str:
    """Scoped to the module. A global topic node merges Backend's `API Design`
    with Testing's `API Testing` on a name — the alias failure, a fourth time."""
    norm = re.sub(r"\s+", " ",
                  re.sub(r"[^a-z0-9]+", " ",
                         unicodedata.normalize("NFKD", label).lower())).strip()
    raw = f"topic|{domain_slug}|{int(sequence)}|{norm}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# D1
# ---------------------------------------------------------------------------

def people_from_text(text: str) -> list:
    """Always empty. D1, and the owner's deferral of instructors.

    A function rather than an absence, so that a future caller reaching for
    "the people in this deck" finds a refusal with a reason rather than
    writing the regex themselves. `REGISTRY-INVENTORY.md` §7 is the
    measurement: four instructor-shaped tuples on registry decks, two of them
    fabricated and structurally identical to the two real ones.
    """
    return []


# ---------------------------------------------------------------------------
# Unavailable content
# ---------------------------------------------------------------------------

_UNAVAILABLE_REASON = {
    "download-disabled-by-owner":
        "content unavailable: download disabled by owner",
    "no-text-extractor":
        "content unavailable: no text extractor for this file type",
    "no-media-download":
        "content not read: media and archives are recorded, never downloaded",
    "learner-content":
        "content not read: learner-authored material inside an assignment review",
}


def node_for_unavailable(row: dict) -> dict:
    """A node for a file whose content we do not hold. Marked, never dropped.

    It carries NO text and NO topics, and that absence is the point: a module
    that looks thin because its deck is on this list must say so rather than
    read as a gap in the curriculum.
    """
    return {
        "label": row["name"],
        "label_raw": row["name"],
        "path": row["path"],
        "mime": row["mime"],
        "content_available": False,
        "unavailable_rule": row["rule"],
        "unavailable_reason": _UNAVAILABLE_REASON.get(
            row["rule"], f"content unavailable: {row['rule']}"),
    }


# ---------------------------------------------------------------------------
# Revamp currency
# ---------------------------------------------------------------------------

_REVAMP = re.compile(r"/(Revamp[\s-]*20\d\d|Q\d\s*20\d\d:?\s*Revamp|"
                     r"New Material Aug 2023)(?:/|$)", re.I)

#: Left ambiguous by the owner, 2026-09-29: it sits INSIDE the base live-class
#: folder rather than beside the module's numbered units, so it has no sibling
#: base to point at. Recorded rather than forced into the rule that covers the
#: other seven.
_AMBIGUOUS = re.compile(r"/2\. Live Class Slides/Updated Content - Aug 2023(?:/|$)",
                        re.I)


def revision_of(path: str) -> str:
    """`base`, `revamp` or `ambiguous`."""
    if _AMBIGUOUS.search(path):
        return "ambiguous"
    return "revamp" if _REVAMP.search(path) else "base"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def provenance(row: dict, **extra) -> dict:
    """A source entry for one cached file. Never carries an address (D4)."""
    src = {
        "origin": "corpus",
        # RELATIVE, with no leading slash. `files.relative_path` carries
        # `check (relative_path !~ '^/')` and `node_sources.file` is a foreign
        # key into it, so an absolute path here means the citation either fails
        # the key or is silently normalised somewhere downstream — and the two
        # halves of the graph then disagree about what a path looks like.
        "file": (row["path"] or "").lstrip("/"),
        "owner_domain": row.get("owner_domain"),
        "mime": row.get("mime"),
    }
    src.update({k: v for k, v in extra.items() if v is not None})
    return {k: v for k, v in src.items() if v is not None}


# ---------------------------------------------------------------------------
# Joining curriculum documents to modules
# ---------------------------------------------------------------------------
#
# 19 of the 23 curriculum documents in row B sit at the DOMAIN root, not under
# a module folder, so a path-based join reaches none of them — and they are the
# structured topic source the owner named first. Two joins are available and
# they are not the same kind of thing:
#
#   BY ORDINAL   `Lesson Plan 2 - API Design and Implementation` is the second
#                module of its domain. That is the same structural fact the
#                module key already rests on, and the title after the number is
#                never compared to anything. Safe to apply.
#
#   BY TAB NAME  `Backend: Lesson plans` has one tab per module — `Concurrency
#                Lesson Plan`, `API development with Spring`. Matching those to
#                module labels is a name match with guaranteed misses: the
#                third occurrence of what `SCALE-PLAN.md` calls the alias
#                problem. It PROPOSES into a review file and never applies.

_LESSON_ORDINAL = re.compile(r"\bLesson\s*Plan\s*(\d+)\b", re.IGNORECASE)


def lesson_plan_sequence(name: str) -> int | None:
    """`Lesson Plan N - <anything>` -> N. No number, no join."""
    m = _LESSON_ORDINAL.search(name)
    return int(m.group(1)) if m else None


def propose_tab_join(tab: str, domain_slug: str,
                     modules: dict) -> dict | None:
    """A PROPOSAL for `config/content-topic-review.yaml`, never a join.

    `modules` maps module label -> sequence. Matching is substring on the
    normalised strings, and TWO matches are returned as ambiguous rather than
    ranked — `lib/resolve.py` returns Ambiguous by default because three
    shipped bugs came from picking with no signal to the caller.
    """
    norm_tab = cur.normalise_for_join(tab)
    hits = [(label, seq) for label, seq in modules.items()
            if cur.normalise_for_join(label) in norm_tab
            or norm_tab in cur.normalise_for_join(label)]
    if not hits:
        return None
    row = {"tab": tab, "domain": domain_slug, "confirmed": False}
    if len(hits) > 1:
        row.update(ambiguous=True, candidates=[h[0] for h in hits],
                   note="two or more modules match this tab name; a human "
                        "decides, and nothing is applied while unconfirmed")
    else:
        row.update(ambiguous=False, candidate=hits[0][0],
                   candidate_sequence=hits[0][1])
    return row


# ---------------------------------------------------------------------------
# Joining crawled files to mastersheet sessions
# ---------------------------------------------------------------------------
#
# The mastersheet is the STRUCTURAL layer (what exists, in what order, taught
# by whom); the crawl is the CONTENT layer (what is actually taught). A file
# always keeps its module edge, which the folder path makes reliable. A SESSION
# edge is added only where evidence allows, and the edge records which kind.
#
# Where neither kind of evidence applies the file stays module-level. That is
# the whole rule: an unplaced deck is a smaller answer, a guessed one is a
# wrong answer that looks the same.


class SessionMatch(NamedTuple):
    kind: str
    evidence: str          # "folder" | "name"
    detail: str


_FOLDER_EVIDENCE = (
    ("review", re.compile(r"/Assignment Review(?:\s*-\s*[^/]+)?/", re.I)),
    ("class", re.compile(r"/(?:\d+\.\s*)?Live[ _]Class[^/]*/|/Slides?/", re.I)),
    ("task", re.compile(r"/(?:\d+\.\s*)?Assignments?[^/]*/|/(?:\d+\.\s*)?Timed[ -]?Test", re.I)),
    ("post_class", re.compile(r"/(?:\d+\.\s*)?Practice[^/]*/", re.I)),
    ("pre_class", re.compile(r"/(?:\d+\.\s*)?Found\w*[^/]*/", re.I)),
)

_NAME_EVIDENCE = (
    ("alternate_review", re.compile(r"alternate.*assignment\s*review", re.I)),
    ("review", re.compile(r"assignment\s*review", re.I)),
    ("alternate_class", re.compile(r"alternate\s*class", re.I)),
    ("pre_class", re.compile(r"foundation material", re.I)),
    ("post_class", re.compile(r"practice problem", re.I)),
    ("class", re.compile(r"[–—-]\s*class\b", re.I)),
)


def session_for_file(path: str, name: str,
                     available_kinds) -> SessionMatch | None:
    """Which session a crawled file belongs to, or None.

    NAME evidence is tried FIRST: `API Design – Alternate Class` sitting in a
    `2. Live Class Slides` folder is an alternate class, and the folder alone
    would call it a class. The more specific evidence wins.

    A kind the module does not actually have is never invented — Test
    Engineering has no post_class sessions, so a `Practice Problems` folder
    there places nothing.
    """
    kinds = set(available_kinds or ())
    for kind, rx in _NAME_EVIDENCE:
        if rx.search(name) and kind in kinds:
            return SessionMatch(kind, "name", rx.pattern[:40])
    for kind, rx in _FOLDER_EVIDENCE:
        if rx.search(path) and kind in kinds:
            return SessionMatch(kind, "folder", rx.pattern[:40])
    return None


#: A deck filename often ends in a first name — `UI & DOM - Jakob.pptx`. With
#: the mastersheet giving per-module instructors, that can be PROPOSED. It is
#: never applied: D1 forbids people from slide CONTENT, and a filename is
#: weaker evidence than the sheet, not stronger.
#: Three shapes, all measured in the row-B cache. The extension is OPTIONAL —
#: native Google decks have none, which is why the first version proposed
#: nothing at all.
_NAME_SHAPES = (
    re.compile(r"\bby\s+([A-Z][A-Za-z.'`-]+(?:\s+[A-Z][A-Za-z.'`-]+)?)"
               r"$"),
    re.compile(r"[-–—]\s*([A-Z][A-Za-z.'`-]+(?:\s+[A-Z][A-Za-z.'`-]+)?)"
               r"\s*(?:\([^)]*\))?\s*$"),
    re.compile(r"^([A-Z][A-Za-z.'`-]+(?:\s+[A-Z][A-Za-z.'`-]+)?)\s*:"),
)


_EXT = re.compile(r"\.(pptx|pdf|docx|xlsx|key|ppt|doc|txt|md|zip)$", re.I)


def deck_name_token(filename: str) -> str | None:
    """The person-shaped token in a deck filename, or None.

    The extension is removed FIRST. Leaving it on let `Ashish.pdf` through as a
    name, because a surname legitimately contains a dot (`St. John`) and the
    character class has to allow one.
    """
    stem = _EXT.sub("", filename).strip()
    for rx in _NAME_SHAPES:
        m = rx.search(stem)
        if m:
            return m.group(1).strip(" .")
    return None


def propose_deck_instructor(filename: str, assignments: dict) -> dict | None:
    """A proposal linking a deck to one of its module's instructors, or None."""
    token = deck_name_token(filename)
    if not token:
        return None
    hits = [(person, role) for role, people in (assignments or {}).items()
            for person in (people if isinstance(people, list) else [])
            if _same_person_hint(token, person)]
    if not hits:
        return None
    row = {"deck": filename, "matched_token": token, "confirmed": False,
           "evidence": "deck filename first name"}
    if len(hits) > 1:
        row.update(ambiguous=True, candidates=[h[0] for h in hits],
                   note="the filename matches more than one instructor on this "
                        "module; a human decides, nothing is applied")
    else:
        row.update(ambiguous=False, candidate=hits[0][0],
                   instructor_role=hits[0][1])
    return row


def _same_person_hint(token: str, person: str) -> bool:
    """A first name matching a first name. A HINT, which is why it proposes."""
    t, p = token.lower().split(), person.lower().split()
    return bool(t and p and t[0] == p[0])


# ---------------------------------------------------------------------------
# Topic ranking
# ---------------------------------------------------------------------------
#
# Ranking ORDERS topics; it never drops one. CLAUDE.md §4 — a cutoff must not
# hide a correct answer, and nothing here is a cutoff.

_TOPIC_RANK = {
    "curriculum": 0,          # lesson plans and outlines come first
    "class": 1,
    "alternate_class": 2,
    "pre_class": 3,
    "task": 4,
    "review": 5,
    "alternate_review": 6,
    "post_class": 7,
}

_HISTORICAL = re.compile(r"/(Revamp[\s-]*20\d\d|Q\d\s*20\d\d:?\s*Revamp|"
                         r"New Material Aug 2023)(?:/|$)|^\s*\[?(old|deprecated|"
                         r"do ?not ?use)\b", re.I)


def topic_rank(source_kind: str | None) -> int:
    """Lower sorts first. An unknown source ranks last but is still kept."""
    return _TOPIC_RANK.get(source_kind or "", 99)


def is_historical(path: str, name: str) -> bool:
    """A superseded revamp subtree, or a deck whose own name says `Old`."""
    return bool(_HISTORICAL.search(path) or _HISTORICAL.search(name))


# ---------------------------------------------------------------------------
# Build / recording artefacts — DISPLAY ONLY (owner request, Animesh Kumar,
# 2026-09-30, checklist review part 1 §D)
# ---------------------------------------------------------------------------
# Test-run output and screen-recorder config sit in Drive beside real content:
# 55 recording.conf on sessions, 94 allure JSON, 26 .pyc. They are collapsed
# into one "Build/recording artefacts (N)" group in the checklist and the
# panel. Nothing is dropped from the graph, and every one stays linked.
# public/index.html carries ARTEFACT_NAME verbatim (tests/test_artefact_group.py).
ARTEFACT_NAME = (r"(\.pyc$|\.log$|^CACHEDIR\.TAG$|^(lastfailed|nodeids|stepwise)$"
                 r"|^recording\.conf$"
                 r"|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                 r"-(result|container|attachment)(\.\w+)?$)")
# a file under a generated directory, whatever it is called
ARTEFACT_DIR = r"(^|/)(__pycache__|\.pytest_cache|allure-results|allure-report)(/|$)"
_ARTEFACT_NAME = re.compile(ARTEFACT_NAME, re.I)
_ARTEFACT_DIR = re.compile(ARTEFACT_DIR, re.I)


def is_build_artefact(name: str, path: str = "") -> bool:
    base = str(name or "").rstrip("/").rsplit("/", 1)[-1]
    return bool(_ARTEFACT_NAME.search(base) or _ARTEFACT_DIR.search(str(path or ""))
                or _ARTEFACT_DIR.search(str(name or "")))


# ---------------------------------------------------------------------------
# Label hygiene — the DB constraint, applied where the label is minted
# ---------------------------------------------------------------------------

_LABEL_URL = re.compile(r"https?://\S+", re.I)
_LABEL_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def clean_label(label: str) -> tuple[str, bool]:
    """(label safe for `nodes.label`, whether anything was removed).

    `db/migrations/0018` narrowed `label_not_contact` to reject an ADDRESS and
    a URL SCHEME rather than the character `@` and the substring `http`. Ten
    content topics still fail it, because they really do carry a link.

    THE NODE IS NEVER DROPPED — CLAUDE.md §1, a failed join is visible and a
    deleted node is not. The link comes out of the display label and the
    original survives in `label_raw` and in the source record.

    FIVE OF THE TEN ARE NOTHING BUT A LINK, so stripping leaves an empty
    string and `label_nonempty` would reject them instead. Those are labelled
    by host: `link: css-tricks.com` says what the node is, carries no scheme,
    and does not pretend the URL was a topic title.
    """
    # ONLY touch labels that actually carry one. The first version stripped
    # trailing punctuation from every label it saw, changed 315 of them and
    # set `label_had_link` on all 315 — a flag that was false for 305.
    if not (_LABEL_URL.search(label or "") or _LABEL_EMAIL.search(label or "")):
        return label, False

    stripped = _LABEL_EMAIL.sub("", _LABEL_URL.sub("", label or ""))
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" :-,;|")
    if stripped:
        return stripped, stripped != (label or "").strip()
    m = _LABEL_URL.search(label or "")
    if m:
        host = re.sub(r"^https?://(www\.)?", "", m.group(0), flags=re.I).split("/")[0]
        return f"link: {host}", True
    return label, False
