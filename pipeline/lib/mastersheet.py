"""Parse `Resource Collection Mastersheet (Software + System).xlsx`.

WHY THIS SOURCE IS DIFFERENT FROM EVERYTHING PASS 7 READS. It is STRUCTURED —
module rows, session rows, a per-module instructor block, an instructor table —
so instructor attribution here is a row in a file with columns, which is the
evidence shape `node_sources` was built to cite. D1 is untouched: nothing in
this module reads a slide, and the deck-derived path still yields no people.

THREE SECTIONS PER TAB, AND THEY ARE NOT SEPARATED BY ANYTHING RELIABLE:

    r0   Module Name | Module - Uplevel Link | Resource Name | Type | ...
    ...  Week 1 - Database Design | https://... | ... Foundation Material | Pre Class
    r42  Drive Folder      | SD3: Backend Engineering
    r45  Topic             | Primary Instructor | Backup 1 | Backup 2 | Backup 3
    r46  Week 1/5 - Database Design | Konstantinos | Robert Kreznarich | ...
    r53  Name of the Instructor | Contact # | Email id | ... | Linkedin

The instructor block reuses `Week N` for its own rows — with `/5` in Backend
and WITHOUT it in Frontend and Testing — so a regex over the whole tab counts
Frontend's four modules as eight and Testing's six as twelve. Sections are
found by their HEADERS. That is the same lesson as `parse_module`'s ordering:
the shape that looks general is the one that double-counts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

#: The workbook this module parses. It was written out in five places;
#: `validate.py` needed a sixth to check instructor provenance, which is
#: the point at which a repeated literal becomes a second source of truth.
SHEET_FILE = "Resource Collection Mastersheet (Software + System).xlsx"

DOMAIN_TABS = ("Full Stack Engineering", "Frontend Engineering",
               "Backend Engineering", "Test Engineering")

#: The tab -> row-B folder join, stated by the sheet's own `Drive Folder` row
#: rather than inferred. Read from the file; this is only the expected shape.
FOLDER_ROW = "drive folder"

#: Columns of the instructor table that are CONTACT DATA. They are separated
#: here, at parse time, so no later caller has to remember to do it.
SENSITIVE_FIELDS = ("contact_phone", "contact_email", "linkedin_url")

PUBLIC_FIELDS = ("name", "years_experience", "current_company",
                 "current_designation", "past_companies")


class Session(NamedTuple):
    name: str
    kind: str
    resource_type: str
    uplevel_link: str
    row: int


class Module(NamedTuple):
    sequence: int
    name: str
    raw: str
    uplevel_link: str
    row: int
    sessions: list


class Tab(NamedTuple):
    tab: str
    drive_folder: str
    modules: list
    assignments_by_sequence: dict
    instructors: list
    drive_folder_url: str = ""


_MODULE_RE = re.compile(r"^Week\s*(\d+)(?:\s*/\s*\d+)?\s*[-–]\s*(.+)$", re.I)

#: Session kind comes from the resource NAME first, because the `Type` column
#: collapses four live-class variants into one value. Order matters: `Alternate
#: Assignment Review` must be tested before `Assignment Review`, and that
#: before `Assignment`.
_KIND_RULES = (
    ("alternate_review", re.compile(r"alternate.*assignment\s*review", re.I)),
    ("review", re.compile(r"assignment\s*review", re.I)),
    ("alternate_class", re.compile(r"alternate\s*class", re.I)),
    ("pre_class", re.compile(r"foundation material|pre[ -]class", re.I)),
    ("post_class", re.compile(r"practice problem|post[ -]class", re.I)),
    # The SHEET's own word is "Assignment"; `task` is our kind name, chosen
    # so the internal vocabulary does not shadow the `assignment` node type.
    ("task", re.compile(r"assignment", re.I)),  # taxonomy-literal-ok: this is the SHEET's word in a resource name, not the node type
    ("class", re.compile(r"[–-]\s*class\b|\bclass\b", re.I)),
)

#: Fallback, when the name says nothing the rules recognise.
_TYPE_FALLBACK = {"pre class": "pre_class", "post class": "post_class",
                  # taxonomy-literal-ok: the key is the sheet's own `Type`
                  # column value, which we read; the VALUE is our kind name.
                  "assignment": "task", "live class": "class"}


def _cell(rows, r, c) -> str:
    if r >= len(rows):
        return ""
    row = rows[r]
    if c >= len(row) or row[c] is None:
        return ""
    return str(row[c]).strip()


def session_kind(name: str, type_col: str) -> str:
    for kind, rx in _KIND_RULES:
        if rx.search(name):
            return kind
    return _TYPE_FALLBACK.get(type_col.strip().lower(), "other")


def split_people(cell: str) -> list[str]:
    """`Bill Ogden/Sindhu Singh Dua` is TWO people.

    Splitting on `/` is applied to instructor cells ONLY, exactly as
    `CLAUDE.md` restricts it to owner columns: the domain `Agentic AI - TPM/Pm`
    is one label and is one row away from `Kunal/Abhishek`, which is two
    people. An empty token is dropped rather than becoming a blank instructor.
    """
    if not cell:
        return []
    return [p.strip() for p in re.split(r"\s*[/,]\s*", cell) if p.strip()]


def needs_people_review(name: str) -> bool:
    """True for a short first-name-only form like `Shelby` or `Bharath`.

    It PROPOSES; nothing merges. The instructor table has `Shelby Cohen`, and
    joining those two automatically is the picking-with-no-signal failure
    `lib/resolve.py` exists to refuse.
    """
    return len(name.split()) == 1


def split_instructor_row(row: dict) -> tuple[dict, dict]:
    """(public fields, contact fields). Separated here so no caller forgets.

    Contact data was DECLINED for all three populations in
    `docs/CONTACT-DATA.md` and that decision was reversed by the corpus owner
    on 2026-09-29 for this structured source only, under conditions recorded
    in that file's approval block. The conditions are enforced elsewhere —
    `property_scopes` refuses a sensitive property on a public row, and the
    contact fields live on a `sensitive: true` node that never enters git.
    This function only guarantees the two never travel together by accident.
    """
    public = {k: v for k, v in row.items() if k in PUBLIC_FIELDS and v}
    private = {k: v for k, v in row.items() if k in SENSITIVE_FIELDS and v}

    # A PUBLIC COLUMN CAN STILL HOLD CONTACT DATA. Test Engineering row 69 has
    # an email and a LinkedIn URL pasted into the NAME column and no name at
    # all. Dropping the row silently is CLAUDE.md §4; publishing it is the
    # thing this whole separation exists to prevent. So the tokens MOVE and the
    # row is flagged — the column map says where a field should be, and this
    # says what the cell actually contains.
    moved = []
    for key, value in list(public.items()):
        cleaned, hits = _scrub(str(value))
        if hits:
            moved.extend(hits)
            public[key] = cleaned
    if moved:
        private["scrubbed_from_public"] = moved
    return public, private


_CONTACT_TOKEN = re.compile(
    r"[\w.+-]+@[\w.-]+\.\w+"
    r"|(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/[\w\-/%.]+",
    re.IGNORECASE)


def _scrub(value: str) -> tuple[str, list[str]]:
    hits = _CONTACT_TOKEN.findall(value)
    return (_CONTACT_TOKEN.sub("", value).strip(" ,;|") if hits else value), hits


def is_unusable(public: dict) -> bool:
    """True when scrubbing left no name — the row is reported, not ingested."""
    return not (public.get("name") or "").strip()


def parse_tab(path: Path, tab: str) -> Tab:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb[tab].iter_rows(values_only=True))
    wb.close()

    # THE REAL HYPERLINK TARGETS. A read_only workbook has no hyperlink model,
    # so a cell whose URL lives in the target rather than the value read as no
    # URL at all — and the session filter below drops a row with no link.
    links = cell_links(path, tab)

    n = len(rows)
    drive_row = next((i for i in range(n)
                      if _cell(rows, i, 0).lower().startswith(FOLDER_ROW)), None)
    topic_row = next((i for i in range(n)
                      if _cell(rows, i, 0).strip().lower() == "topic"
                      and "instructor" in _cell(rows, i, 1).lower()), None)
    table_row = next((i for i in range(n)
                      if "name of the instructor" in _cell(rows, i, 0).lower()),
                     None)

    # -- section 1: modules and their sessions -----------------------------
    end = drive_row if drive_row is not None else (topic_row or n)
    modules: list[Module] = []
    for i in range(1, end):
        m = _MODULE_RE.match(_cell(rows, i, 0))
        if m:
            modules.append(Module(int(m.group(1)), m.group(2).strip(),
                                  _cell(rows, i, 0),
                                  best_link(_cell(rows, i, 1), links.get((i, 1))),
                                  i, []))
    for idx, mod in enumerate(modules):
        stop = modules[idx + 1].row if idx + 1 < len(modules) else end
        for i in range(mod.row, stop):
            name, type_col = _cell(rows, i, 2), _cell(rows, i, 3)
            link = best_link(_cell(rows, i, 5), links.get((i, 5)))
            if not name or not link:
                continue
            mod.sessions.append(Session(name, session_kind(name, type_col),
                                        _cell(rows, i, 4), link, i))

    # -- section 2: per-module instructors ---------------------------------
    by_seq: dict[int, dict] = {}
    if topic_row is not None:
        stop = table_row if table_row is not None else n
        for i in range(topic_row + 1, stop):
            m = _MODULE_RE.match(_cell(rows, i, 0))
            if not m:
                continue
            by_seq[int(m.group(1))] = {
                "raw": _cell(rows, i, 0),
                "row": i,
                "primary": split_people(_cell(rows, i, 1)),
                "backup_1": split_people(_cell(rows, i, 2)),
                "backup_2": split_people(_cell(rows, i, 3)),
                "backup_3": split_people(_cell(rows, i, 4)),
            }

    # -- section 3: the instructor table -----------------------------------
    people: list[dict] = []
    if table_row is not None:
        header = [_cell(rows, table_row, c).lower() for c in range(12)]

        def col(*needles, default=None):
            for c, h in enumerate(header):
                if h and any(nd in h for nd in needles):
                    return c
            return default

        cmap = {
            "name": col("name of the instructor", default=0),
            "contact_phone": col("contact"),
            "contact_email": col("email"),
            "years_experience": col("years experience", "# years"),
            "current_company": col("current company"),
            "current_designation": col("current designation"),
            "past_companies": col("past tier", "past companies"),
            "linkedin_url": col("linkedin"),
        }
        for i in range(table_row + 1, n):
            name = _cell(rows, i, cmap["name"] or 0)
            if not name or _MODULE_RE.match(name):
                continue
            rec = {"row": i}
            for field, c in cmap.items():
                rec[field] = _cell(rows, i, c) if c is not None else ""
            people.append(rec)

    # The `Drive Folder` row's LABEL is the folder name and its TARGET is the
    # folder URL — the case that made hyperlink reading necessary at all.
    drive_url = links.get((drive_row, 1), "") if drive_row is not None else ""
    return Tab(tab, _cell(rows, drive_row, 1) if drive_row is not None else "",
               modules, by_seq, people, drive_url)


# ---------------------------------------------------------------------------
# Hyperlink targets — the LINK, not the label
# ---------------------------------------------------------------------------

#: Only these schemes ever become a link in the UI. `mailto:` is the reason
#: this is an allow-list rather than a deny-list: eight cells in the Backend tab
#: carry a real hyperlink whose target differs from its display text, and two of
#: them are `mailto:` targets holding an instructor's personal address. A
#: value-only read never saw them. Reading hyperlinks is what exposes them, so
#: the read is filtered at the point it happens.
_LINK_OK = re.compile(r"^https?://", re.I)


class LinkCell(NamedTuple):
    row: int
    col: int
    display: str
    target: str
    differs: bool


def _col_to_index(ref: str) -> tuple[int, int]:
    """`B43` -> (row 42, col 1), both 0-based to match `parse_tab`."""
    letters = "".join(ch for ch in ref if ch.isalpha())
    digits = "".join(ch for ch in ref if ch.isdigit())
    col = 0
    for ch in letters.upper():
        col = col * 26 + (ord(ch) - 64)
    return int(digits) - 1, col - 1


def _raw_links(path: Path, tab: str) -> dict:
    """{(row, col): (target, is_http)} read straight out of the .xlsx ZIP.

    NOT openpyxl. `load_workbook(read_only=True)` carries no hyperlink model at
    all, and `read_only=False` opens the workbook WRITABLE — which
    `tests/test_documented_constraints_are_enforced.py` refuses, because
    CLAUDE.md §1 says a corpus file is never written and the guard does not
    take promises. An .xlsx is a zip of XML, and `zipfile` in read mode cannot
    write to it, so the constraint is satisfied by construction rather than by
    intent.

    Hyperlinks live in two places: `<hyperlink ref="B43" r:id="rId1"/>` in the
    sheet, and the URL behind that rId in the sheet's `.rels` part.
    """
    import re as _re
    import xml.etree.ElementTree as ET
    import zipfile

    NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
    out: dict = {}
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_part = {r.get("Id"): r.get("Target")
                       for r in rels.findall("pr:Relationship", NS)}
        part = None
        for sh in wb.findall("m:sheets/m:sheet", NS):
            if sh.get("name") == tab:
                target = rid_to_part.get(sh.get(f"{{{NS['r']}}}id"), "")
                part = "xl/" + target.lstrip("/").replace("xl/", "", 1)
                break
        if part is None or part not in z.namelist():
            return out
        sheet = ET.fromstring(z.read(part))
        name = part.rsplit("/", 1)[-1]
        rels_part = part.rsplit("/", 1)[0] + "/_rels/" + name + ".rels"
        link_rels = {}
        if rels_part in z.namelist():
            lr = ET.fromstring(z.read(rels_part))
            link_rels = {r.get("Id"): (r.get("Target") or "")
                         for r in lr.findall("pr:Relationship", NS)}
        for h in sheet.findall("m:hyperlinks/m:hyperlink", NS):
            ref = (h.get("ref") or "").split(":")[0]
            if not ref:
                continue
            tgt = link_rels.get(h.get(f"{{{NS['r']}}}id"), "") or ""
            if not tgt:
                # An internal link has no rId; it points inside the workbook
                # and is never a source link.
                continue
            out[_col_to_index(ref)] = (tgt.strip(),
                                       bool(_LINK_OK.match(tgt.strip())))
    return out


def cell_links(path: Path, tab: str) -> dict:
    """{(row, col): target} for every http(s) hyperlink on the tab.

    `parse_tab` reads values only, so a cell whose URL lives in the hyperlink
    TARGET rather than in the cell value produced no link at all — the case
    that made this necessary: the `Drive Folder` row displays the folder NAME
    and links the folder.
    """
    return {k: v[0] for k, v in _raw_links(path, tab).items() if v[1]}


def link_mismatches(path: Path, tab: str, rows: list | None = None) -> list:
    """Cells whose display text is not their link target.

    REPORTED, NOT SILENTLY PREFERRED. The owner asked for the real target to be
    used and for any disagreement surfaced: a label that reads like one resource
    and points at another is a defect in the sheet, and the graph should not be
    the only thing that knows.

    A non-http target is reported with the TARGET WITHHELD. Two of them are
    `mailto:` links carrying an instructor's personal address, and a report
    about contact data does not need the contact data to make its point.
    """
    if rows is None:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = list(wb[tab].iter_rows(values_only=True))
        wb.close()
    out = []
    for (r, c), (tgt, is_http) in sorted(_raw_links(path, tab).items()):
        disp = _cell(rows, r, c)
        if not is_http:
            out.append(LinkCell(r, c, disp, "<non-http target withheld>", True))
        elif disp != tgt:
            out.append(LinkCell(r, c, disp, tgt, True))
    return out


def best_link(value: str, target: str | None) -> str:
    """The link for a cell: its hyperlink TARGET, else its value if that is a URL.

    Never the display text when a target exists, and never a non-http scheme.
    """
    if target and _LINK_OK.match(target):
        return target.strip()
    v = (value or "").strip()
    return v if _LINK_OK.match(v) else ""


# ---------------------------------------------------------------------------
# Red-highlighted cells, and the owner's word on what they mean
# ---------------------------------------------------------------------------
#
# The sheet's authors mark a no-longer-valid instructor cell RED rather than
# clearing it (owner, 2026-09-30). A values-only read cannot see that, so the
# cell is read here — read_only, like every other read — and the MEANING comes
# from config/mastersheet-owner-facts.yaml, never from the colour.

OWNER_FACTS = Path(__file__).resolve().parents[2] / "config" / "mastersheet-owner-facts.yaml"
ROLE_COLUMNS = {1: "primary", 2: "backup_1", 3: "backup_2", 4: "backup_3"}


def _is_red(hexrgb) -> bool:
    if not isinstance(hexrgb, str) or len(hexrgb) < 6:
        return False
    h = hexrgb[-6:]
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
    return r >= 180 and g <= 120 and b <= 120


def red_cells(path: Path, tab: str) -> dict:
    """{(row0, col0): value} for every non-empty cell filled or written red."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    try:
        for row in wb[tab].iter_rows():
            for c in row:
                if c.value in (None, ""):
                    continue
                fill = getattr(getattr(c.fill, "fgColor", None), "rgb", None) \
                    if c.fill is not None and c.fill.fill_type else None
                font = getattr(getattr(c.font, "color", None), "rgb", None) \
                    if c.font is not None and c.font.color is not None else None
                if _is_red(fill) or _is_red(font):
                    out[(c.row - 1, c.column - 1)] = str(c.value)
    finally:
        wb.close()
    return out


def withdrawn_roles() -> dict:
    """{(domain, sequence, role, person): fact} from the owner-facts file."""
    import yaml
    if not OWNER_FACTS.exists():
        return {}
    data = yaml.safe_load(OWNER_FACTS.read_text(encoding="utf-8")) or {}
    out = {}
    for f in data.get("withdrawn_roles") or []:
        assert f.get("origin") == "hand" and f.get("asserted_by") and f.get("fact"), f
        out[(f["domain"], int(f["sequence"]), f["role"], f["person"])] = f
    return out

