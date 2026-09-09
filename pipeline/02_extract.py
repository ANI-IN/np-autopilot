#!/usr/bin/env python3
"""Pass 2 — extract candidates. Closed vocabulary, every rejection logged.

Reads knowledge/files.json. Does NOT resolve identities — pass 3 does that. The
extract/resolve split is the structural defence against the failure that put 27
slide bullets into the reference implementation's instructor list: their passes
were fused, so nothing could say "that is not a person".

Every candidate carries provenance. A candidate without it is a build failure.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl                                                       # noqa: E402

from pipeline.lib import sources as SRC                                # noqa: E402
from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import BUILD_LOG, KNOWLEDGE_DIR, corpus_root   # noqa: E402

CANDIDATES = KNOWLEDGE_DIR / "candidates.json"
REJECTIONS = KNOWLEDGE_DIR / "rejections.json"

T_WORKFLOW, T_THEME = "workflow", "theme"
T_PERSON, T_DOMAIN = "person", "domain"
T_PROGRAM, T_MODULE, T_INSTRUCTOR = "program", "module", "instructor"

#: Domain labels from Sheet1, populated at run time. The For Slack grid uses
#: them as column headers and they must not become people.
DOMAIN_LABELS: set = set()

STOPWORDS = re.compile(
    r"\b(the|and|not|you|your|they|we|but|is|are|was|were|it|to|of|for|with|"
    r"that|this|can|will|our|from|has|have)\b")
TOPIC_WORDS = re.compile(
    r"\b(design|system|systems|architecture|infrastructure|cloud|frontend|"
    r"backend|full ?stack|database|networking|security|devops|analytics|"
    r"pipeline|framework|fundamentals|crash course)\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = re.sub(r"[^\w\s]", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def reject_reason(raw: str, node_type: str) -> str | None:
    """Junk heuristics. Scoped to person and instructor labels ONLY.

    As global rules these reject the taxonomy's own vocabulary — theme 15 is 46
    characters and 27 of 92 workflow labels contain / & or an arrow.
    """
    s = str(raw).strip()
    if not s:
        return "empty"
    if "@" in s or "http" in s.lower():
        return "contains @ or http"
    if node_type == T_MODULE:
        # Module labels get almost no heuristic, which let 7 pure numbers
        # ("1.0".."7.0") and 2 PHONE NUMBERS become module nodes. These are the
        # only shapes a module label can never legitimately take.
        if re.fullmatch(r"[\d.\s]+", s):
            return "numeric only — not a module name"
        if re.fullmatch(r"\+?\d[\d\s().-]{7,}", s):
            return "phone-number shaped"
        if len(s) < 3:
            return "shorter than 3 characters"
        low = s.strip().lower().rstrip(".")
        # Status / filler values. "done" had become a module with 18 teaches
        # edges before this rule existed.
        if low in {"done", "na", "n/a", "tbd", "yes", "no", "wip", "pending",
                   "complete", "completed", "nil", "none", "ok", "default",
                   "-", "--", "n.a"}:
            return "status or filler value, not a module"
        # Column headers that leaked into the data region.
        if low in {"topic", "topics", "week no", "week", "module", "module name",
                   "name", "resource name", "pathways", "course", "instructor"}:
            return "column header, not a module"
        return None
    if node_type != T_PERSON and node_type != T_INSTRUCTOR:
        return None
    n = norm(s)
    if not n:
        return "no alphanumeric content"
    if len(s) > 40:
        return "longer than 40 characters"
    if re.search(r"[.!?,;:]", s.rstrip(".")):
        return "sentence punctuation"
    if len(n.split()) > 4:
        return "more than 4 tokens"
    if STOPWORDS.search(f" {n} "):
        return "contains a stopword"
    if re.search(r"\d", s):
        return "contains a digit"
    if TOPIC_WORDS.search(s):
        return "matches the topic vocabulary, not a person"
    if len(n.split()) == 1:
        return "single-token name — review, not accepted silently"
    return None


def header_row(ws, wanted: str, limit: int = 5):
    """Find the row holding `wanted`. Headers are not always row 1."""
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=limit, values_only=True)):
        cells = [str(v).strip() if v is not None else "" for v in row]
        if wanted in cells:
            return i + 1, cells.index(wanted), cells
    return None, None, None


def _status_for(rel: str, sn: str, row, hdr_cells) -> str:
    """Roster presence vs hiring-funnel outcome. Never conflate the two."""
    key = (rel, sn)
    if key in SRC.FUNNEL_OUTCOMES:
        col, mapping = SRC.FUNNEL_OUTCOMES[key]
        if col in hdr_cells:
            i = hdr_cells.index(col)
            v = str(row[i]).strip().lower() if i < len(row) and row[i] is not None else ""
            for needle, status in mapping.items():
                if v.startswith(needle):
                    return status
            return "in_pipeline"          # named candidate, outcome not recorded
        return "in_pipeline"
    if key in SRC.ROSTER_SHEETS:
        return "roster"
    return "unknown"


def scan_column(root: Path, rel: str, sheet: str, column: str, node_type: str,
                out: list, rejected: list, missing: list) -> None:
    path = root / rel
    if not path.exists():
        missing.append({"file": rel, "sheet": sheet, "reason": "file not present"})
        return
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = [sheet] if sheet else wb.sheetnames
        for sn in sheets:
            if sn not in wb.sheetnames:
                missing.append({"file": rel, "sheet": sn, "reason": "sheet not found"})
                continue
            ws = wb[sn]
            hrow, hcol, hdr_cells = header_row(ws, column)
            if hrow is None:
                missing.append({"file": rel, "sheet": sn,
                                "reason": f"column {column!r} not found in first 4 rows"})
                continue
            for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                         start=hrow + 1):
                if hcol >= len(row):
                    continue
                v = row[hcol]
                if v is None or not str(v).strip():
                    continue
                raw = str(v).strip()
                prov = {"origin": "corpus", "file": rel, "sheet": sn,
                        "row": rownum, "column": column}
                why = reject_reason(raw, node_type)
                if why:
                    rejected.append({"type": node_type, "raw": raw,
                                     "reason": why, "source": prov})
                else:
                    rec = {"type": node_type, "raw": raw, "norm": norm(raw),
                           "sources": [prov]}
                    if node_type == T_INSTRUCTOR:
                        rec["pipeline_status"] = _status_for(rel, sn, row, hdr_cells or [])
                    if node_type == T_MODULE:
                        rec["sheet"] = sn
                        rec["domain"] = SRC.SHEET_DOMAIN.get(sn)
                        rec["granularity"] = "module"   # declared Module Name column
                    out.append(rec)
    finally:
        wb.close()


def extract_workflows(root: Path, out: list, rejected: list) -> None:
    rel = "00-master/Team_Task___Workflow_Inventory"
    text = (root / rel).read_text(encoding="utf-8")
    theme = None
    current_wf = None
    for lineno, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            theme = (int(m.group(1)), m.group(2).strip())
            current_wf = None
            out.append({"type": T_THEME, "raw": m.group(2).strip(),
                        "norm": norm(m.group(2)), "theme_id": theme[0],
                        "sources": [{"origin": "corpus", "file": rel, "row": lineno}]})
            continue
        m = re.match(r"^###\s+(\d+)\.(\d+)\s+(.+?)\s*$", line)
        if m and theme:
            out.append({"type": T_WORKFLOW, "raw": m.group(3).strip(),
                        "norm": norm(m.group(3)),
                        "workflow_id": f"{m.group(1)}.{m.group(2)}",
                        "theme_id": theme[0],
                        "sources": [{"origin": "corpus", "file": rel, "row": lineno}]})
            current_wf = out[-1]
            continue
        # Workflow BODY properties. The first build extracted only id/name/theme
        # and every Component A eval question failed as a result — 8 of 22.
        if current_wf is None:
            continue
        m = re.match(r"^-\s*Workflow:\s*(.+)$", line)
        if m:
            current_wf["steps"] = [s.strip() for s in
                                   re.split(r"\u2192|->", m.group(1)) if s.strip()]
            continue
        m = re.match(r"^-\s*Effort:\s*(.+)$", line)
        if m:
            current_wf["effort"] = m.group(1).strip()
            continue
        m = re.match(r"^-\s*Alerts?:\s*(.+)$", line)
        if m:
            current_wf["alerts"] = [s.strip().rstrip(".") for s in
                                    re.split(r"\u2192|->", m.group(1)) if s.strip()]
            continue


def attach_tools(root: Path, out: list) -> None:
    """workflow.tools from the closed vocabulary — the Tool demotion's product."""
    rel = "00-master/Team_Task___Workflow_Inventory"
    text = (root / rel).read_text(encoding="utf-8")
    blocks = re.split(r"^### ", text, flags=re.M)[1:]
    body = {}
    for b in blocks:
        head = b.split("\n", 1)[0]
        m = re.match(r"(\d+\.\d+)\s", head)
        if m:
            body[m.group(1)] = b.lower()
    vocab = taxonomy.tools()
    for c in out:
        if c["type"] != T_WORKFLOW:
            continue
        blk = body.get(c.get("workflow_id"), "")
        c["tools"] = [t for t in vocab if t.lower() in blk]


def extract_domains(root: Path, out: list, rejected: list, blanks: list) -> None:
    rel = "00-master/Domains_Courses Owners.xlsx"
    wb = openpyxl.load_workbook(root / rel, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    for rownum, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        def cell(i):
            return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
        dom = cell(0)
        if not dom:
            continue
        prov = {"origin": "corpus", "file": rel, "sheet": "Sheet1", "row": rownum}
        out.append({"type": T_DOMAIN, "raw": dom, "norm": norm(dom),
                    "cadence": cell(4), "stage": cell(5), "sources": [prov]})
        # Owner columns: split on , and / — owner columns ONLY, never the domain
        # label ("Agentic AI - TPM/Pm" is one domain, one row from "Kunal/Abhishek").
        for role, col1 in taxonomy.owner_sheet_edges():
            idx = col1 - 1
            v = cell(idx)
            if not v:
                continue
            tokens = [t.strip() for t in v.replace("/", ",").split(",")]
            if any(t == "" for t in tokens):
                blanks.append({"file": rel, "sheet": "Sheet1", "row": rownum,
                               "column": idx + 1, "role": role, "raw": v,
                               "tokens": tokens,
                               "note": "empty token from multi-value split — RETAINED"})
            for t in [t for t in tokens if t]:
                why = reject_reason(t, T_PERSON)
                rec = {"type": T_PERSON, "raw": t, "norm": norm(t), "role": role,
                       "domain": dom, "sources": [dict(prov, column=idx + 1)]}
                if why and why != "single-token name — review, not accepted silently":
                    rejected.append({"type": T_PERSON, "raw": t, "reason": why,
                                     "source": rec["sources"][0]})
                else:
                    if why:
                        rec["review"] = why
                    out.append(rec)
    wb.close()


def extract_slack_grid(root: Path, out: list, rejected: list) -> None:
    """The `For Slack` sheet is a person GRID, not a table with a name column.

    Domain names run across one header row and the people responsible are listed
    beneath each. Missing it lost `Abhinav Rawat` entirely — his single cell in
    the whole 75-file corpus lives here.
    """
    rel = "00-master/Domains_Courses Owners.xlsx"
    wb = openpyxl.load_workbook(root / rel, read_only=True, data_only=True)
    ws = wb["For Slack"]
    # Header and status rows are detected STRUCTURALLY, with no hardcoded
    # vocabulary. Two signatures, both specific to this grid's layout:
    #   header — the first row of a block, i.e. row 1 or a row after a blank
    #   status — one value repeated across most of the row ("Created" x9)
    rows = list(ws.iter_rows(values_only=True))
    skip = set()
    prev_blank = True
    for rownum, row in enumerate(rows, start=1):
        vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
        if not vals:
            prev_blank = True
            continue
        if prev_blank:
            skip.add(rownum)                       # block header
        elif len(vals) >= 5 and len(set(vals)) == 1:
            skip.add(rownum)                       # status row
        prev_blank = False
    for rownum, row in enumerate(rows, start=1):
        if rownum in skip:
            continue
        for col, v in enumerate(row, start=1):
            if v is None or not str(v).strip():
                continue
            raw = str(v).strip()
            if raw.strip() in DOMAIN_LABELS:
                continue
            prov = {"origin": "corpus", "file": rel, "sheet": "For Slack",
                    "row": rownum, "column": col}
            why = reject_reason(raw, T_PERSON)
            if why and why != "single-token name — review, not accepted silently":
                rejected.append({"type": T_PERSON, "raw": raw, "reason": why, "source": prov})
                continue
            rec = {"type": T_PERSON, "raw": raw, "norm": norm(raw), "sources": [prov]}
            if why:
                rec["review"] = why
            out.append(rec)
    wb.close()


def extract_people(root: Path, out: list, rejected: list, blanks: list) -> None:
    rel = "00-master/IAims Setting Audit _ New Programs.xlsx"
    wb = openpyxl.load_workbook(root / rel, read_only=True, data_only=True)
    qmap = {q["sheet"]: q for q in taxonomy._raw()["quarter_vocabulary"]}
    for sn in wb.sheetnames:
        ws = wb[sn]
        hrow, hcol, hdr = header_row(ws, "Employee Name")
        if hrow is None:
            continue
        eno = hdr.index("ENo") if "ENo" in hdr else None
        q = qmap.get(sn)
        for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                     start=hrow + 1):
            if hcol >= len(row) or row[hcol] is None or not str(row[hcol]).strip():
                continue
            raw = str(row[hcol]).strip()
            ident = str(row[eno]).strip() if eno is not None and eno < len(row) and row[eno] else ""
            prov = {"origin": "corpus", "file": rel, "sheet": sn, "row": rownum}
            if not ident:
                # RETAINED, never dropped. Normal HR lag for a recent joiner.
                blanks.append({"file": rel, "sheet": sn, "row": rownum,
                               "name": raw, "note": "blank employee id — RETAINED"})
            why = reject_reason(raw, T_PERSON)
            rec = {"type": T_PERSON, "raw": raw, "norm": norm(raw),
                   "employee_id": ident, "quarter": q["quarter"] if q else None,
                   "quarter_order": q["order"] if q else None,
                   "sheet": sn, "sources": [prov]}
            if why and why != "single-token name — review, not accepted silently":
                rejected.append({"type": T_PERSON, "raw": raw, "reason": why, "source": prov})
            else:
                if why:
                    rec["review"] = why
                out.append(rec)
    wb.close()


def extract_pairings(root: Path, out: list, rejected: list, pairs: list) -> None:
    """module <-> instructor pairings, and modules from the UpLevel schedules.

    Both feed relations that pass 4 turns into edges. Modules found here are
    added as module candidates with their domain, because a module named only in
    a pairing sheet is still a module.
    """
    # --- grids: module in one column, ranked instructors across others ---
    for rel, sheet, hrow, mcol, icols, dom in SRC.TEACHES_GRIDS:
        path = root / rel
        if not path.exists():
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if sheet not in wb.sheetnames:
            wb.close()
            continue
        ws = wb[sheet]
        current = None
        for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                     start=hrow + 1):
            def c(i):
                return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
            if c(mcol):
                current = c(mcol)
            if not current or reject_reason(current, T_MODULE):
                continue
            prov = {"origin": "corpus", "file": rel, "sheet": sheet, "row": rownum}
            out.append({"type": T_MODULE, "raw": current, "norm": norm(current),
                        "sheet": sheet, "domain": dom,
                        "granularity": "module",   # Module<>SME grids name modules
                        "sources": [prov]})
            for rank, ic in enumerate(icols):
                name = c(ic)
                if not name:
                    continue
                # cells like "Robert/Shelby/" or "Ashish Kaila / JD Kelby"
                for piece in [x.strip() for x in name.split("/") if x.strip()]:
                    why = reject_reason(piece, T_INSTRUCTOR)
                    if why:
                        rejected.append({"type": T_INSTRUCTOR, "raw": piece,
                                         "reason": why, "source": prov})
                        continue
                    out.append({"type": T_INSTRUCTOR, "raw": piece, "norm": norm(piece),
                                "pipeline_status": "roster", "sources": [prov]})
                    pair = {"module": norm(current), "instructor": norm(piece),
                            "rank": rank, "domain": dom, "source": prov}
                    rc = SRC.TEACHES_RATINGS.get((rel, sheet, mcol))
                    if rc:
                        if c(rc[0]):
                            pair["avg_rating"] = c(rc[0])
                        if c(rc[1]):
                            pair["classes"] = c(rc[1])
                    pairs.append(pair)
        wb.close()

    # --- lists: one instructor, several modules in a delimited cell ---
    for rel, sheet, namecol, modcol, sep in SRC.TEACHES_LISTS:
        path = root / rel
        if not path.exists():
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if sheet not in wb.sheetnames:
            wb.close()
            continue
        ws = wb[sheet]
        hrow, _, hdr = header_row(ws, namecol)
        if hrow is None or modcol not in (hdr or []):
            wb.close()
            continue
        ni, mi = hdr.index(namecol), hdr.index(modcol)
        for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                     start=hrow + 1):
            def c(i):
                return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
            name, mods = c(ni), c(mi)
            if not name or not mods or reject_reason(name, T_INSTRUCTOR):
                continue
            prov = {"origin": "corpus", "file": rel, "sheet": sheet, "row": rownum}
            for m in [x.strip() for x in mods.replace("\n", sep).split(sep) if x.strip()]:
                if reject_reason(m, T_MODULE):
                    continue
                out.append({"type": T_MODULE, "raw": m, "norm": norm(m),
                            "sheet": sheet, "domain": None,
                            "granularity": "expertise",  # self-declared topic
                                                         # expertise, coarsest
                            "sources": [prov]})
                pairs.append({"module": norm(m), "instructor": norm(name),
                              "rank": 0, "domain": None, "source": prov})

        wb.close()

    # --- UpLevel per-domain cohort schedules: Topic (For) is the module ---
    path = root / "01-workflows/UpLevel Schedule Structure.xlsx"
    if path.exists():
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for sheet, dom in SRC.UPLEVEL_DOMAIN_SHEETS.items():
            if not dom or sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            hrow, hcol, hdr = header_row(ws, SRC.UPLEVEL_TOPIC_COLUMN)
            if hrow is None:
                continue
            ri = hdr.index("Resource Type") if hdr and "Resource Type" in hdr else None
            for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                         start=hrow + 1):
                v = row[hcol] if hcol < len(row) else None
                if v is None or not str(v).strip():
                    continue
                raw = str(v).strip()
                if reject_reason(raw, T_MODULE):
                    continue
                # "Topic (For)" is BROADER than a module: it labels what an
                # activity is for, and the activities include feedback forms,
                # onboarding videos and tests. Only teaching-shaped rows yield a
                # module; the rest are activity labels and are skipped.
                rtype = (str(row[ri]).strip().lower()
                         if ri is not None and ri < len(row) and row[ri] else "")
                if rtype and not any(k in rtype for k in ("class", "resourcecollection",
                                                          "resource collection")):
                    continue
                out.append({"type": T_MODULE, "raw": raw, "norm": norm(raw),
                            "sheet": sheet, "domain": dom,
                            "granularity": "topic",   # coarser than a declared
                                                      # Module Name; see below
                            "resource_type": rtype,
                            "sources": [{"origin": "corpus",
                                         "file": "01-workflows/UpLevel Schedule Structure.xlsx",
                                         "sheet": sheet, "row": rownum}]})
        wb.close()


def extract_expertise(root: Path, out: list, rejected: list, claims: list) -> None:
    """instructor -> declared domain. Not teaching evidence — see taxonomy note."""
    for rel, sheet, namecol, subjcol, basis, sep in SRC.EXPERT_IN_SOURCES:
        path = root / rel
        if not path.exists():
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if sheet not in wb.sheetnames:
            wb.close()
            continue
        ws = wb[sheet]
        hrow, _, hdr = header_row(ws, namecol)
        if hrow is None or subjcol not in (hdr or []):
            wb.close()
            continue
        ni, si = hdr.index(namecol), hdr.index(subjcol)
        for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                     start=hrow + 1):
            def c(i):
                return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
            name, subj = c(ni), c(si)
            if not name or not subj or reject_reason(name, T_INSTRUCTOR):
                continue
            prov = {"origin": "corpus", "file": rel, "sheet": sheet, "row": rownum}
            for piece in [x.strip() for x in subj.split(sep) if x.strip()]:
                raw = piece
                stripped = re.sub(SRC.ROLE_SUFFIX_RE, "", piece, flags=re.I).strip(" -")
                recovered = stripped != piece
                if not stripped or stripped.lower() in SRC.ROLE_ONLY_VALUES:
                    rejected.append({"type": taxonomy.edge_for_role("instructor_domain"),
                                     "raw": raw,
                                     "reason": "role, not a domain", "source": prov})
                    continue
                claims.append({"instructor": norm(name), "subject_raw": raw,
                               "subject": stripped, "norm": norm(stripped),
                               "basis": basis, "role_suffix_stripped": recovered,
                               "source": prov})
        wb.close()


def extract_schedule(root: Path, out: list, rejected: list, pairs: list) -> list:
    """Who actually taught what, from the per-domain class schedules."""
    path = root / SRC.SCHEDULE_FILE
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    dom_labels = {norm(c["raw"]): c["raw"] for c in out if c["type"] == T_DOMAIN}
    seen_sheets = []
    for sheet in wb.sheetnames:
        if sheet in SRC.SCHEDULE_NON_DOMAIN and sheet != "Combined Schedule Mastersheet":
            continue
        ws = wb[sheet]
        hrow, icol, hdr = header_row(ws, SRC.SCHEDULE_INSTRUCTOR_COL, limit=5)
        if hrow is None or SRC.SCHEDULE_TOPIC_COL not in (hdr or []):
            continue
        tcol = hdr.index(SRC.SCHEDULE_TOPIC_COL)
        dcol = hdr.index(SRC.SCHEDULE_DATE_COL) if SRC.SCHEDULE_DATE_COL in hdr else None
        # sheet name -> domain. "Backend DTC" and "Backend" are both Backend.
        base = re.sub(r"\s*(DTC|SSD|\(NS\)|New Students)\s*$", "", sheet).strip()
        dom = dom_labels.get(norm(base))
        seen_sheets.append((sheet, dom))
        for rownum, row in enumerate(ws.iter_rows(min_row=hrow + 1, values_only=True),
                                     start=hrow + 1):
            def c(i):
                return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
            name, topic = c(icol), c(tcol)
            if not name or not topic:
                continue
            prov = {"origin": "corpus", "file": SRC.SCHEDULE_FILE,
                    "sheet": sheet, "row": rownum}
            if reject_reason(name, T_INSTRUCTOR):
                continue
            module = re.sub(SRC.CLASS_SUFFIX_RE, "", topic, flags=re.I).strip(" -")
            if not module or reject_reason(module, T_MODULE):
                continue
            out.append({"type": T_MODULE, "raw": module, "norm": norm(module),
                        "sheet": sheet, "domain": dom, "granularity": "module",
                        "sources": [prov]})
            out.append({"type": T_INSTRUCTOR, "raw": name, "norm": norm(name),
                        "pipeline_status": "roster", "sources": [prov]})
            when = None
            if dcol is not None and dcol < len(row) and isinstance(row[dcol], datetime):
                when = row[dcol].date().isoformat()
            pairs.append({"module": norm(module), "instructor": norm(name),
                          "rank": 0, "domain": dom, "delivered": True,
                          "date": when, "source": prov})
    wb.close()
    return seen_sheets


def extract_programs(root: Path, out: list) -> None:
    for pdf in sorted((root / "04-programs").glob("*.pdf")):
        rel = f"04-programs/{pdf.name}"
        n = re.sub(r"^CUR-", "", pdf.name)
        n = re.sub(r"-\d{6}-\d{6}\.pdf$", "", n)
        n = re.sub(r"\.pdf$", "", n).strip()
        kyp, curriculum = taxonomy.doctypes()
        doctype = kyp if re.search(rf"\b{re.escape(kyp)}\b", n, re.I) else curriculum
        edgeup, interview_prep, standalone = taxonomy.families()
        if re.search(re.escape(edgeup), n, re.I):
            fam = edgeup
        elif re.search(r"Interview Preparation Program", n, re.I):
            fam = interview_prep
        else:
            fam = standalone
        out.append({"type": T_PROGRAM, "raw": n, "norm": norm(n),
                    "doctype": doctype, "family": fam,
                    "sources": [{"origin": "corpus", "file": rel}]})


def main() -> int:
    root = corpus_root()
    manifest = json.loads((KNOWLEDGE_DIR / "files.json").read_text(encoding="utf-8"))
    print("=" * 78)
    print("PASS 2 — extract candidates")
    print("=" * 78)
    print(f"source     : {manifest['source']}")
    print(f"files.json : {len(manifest['files'])} parsed files")
    print()

    cands: list = []
    rejected: list = []
    missing: list = []
    blanks: list = []

    extract_workflows(root, cands, rejected)
    attach_tools(root, cands)
    extract_domains(root, cands, rejected, blanks)
    # Domain labels are known only after extract_domains; the Slack grid uses
    # them as headers and they must not become people.
    DOMAIN_LABELS.update(c["raw"] for c in cands if c["type"] == T_DOMAIN)
    extract_slack_grid(root, cands, rejected)
    extract_people(root, cands, rejected, blanks)
    extract_programs(root, cands)
    pairs: list = []
    extract_pairings(root, cands, rejected, pairs)
    claims: list = []
    extract_expertise(root, cands, rejected, claims)
    sched = extract_schedule(root, cands, rejected, pairs)
    for rel, sheet, col in SRC.INSTRUCTOR_SOURCES:
        scan_column(root, rel, sheet, col, T_INSTRUCTOR, cands, rejected, missing)
    for rel, sheet, col in SRC.MODULE_SOURCES:
        scan_column(root, rel, sheet, col, T_MODULE, cands, rejected, missing)

    # Cross-type collision. A label that is both a module and an instructor is
    # a person's name leaking into a Module Name column — 42 of them, mostly in
    # Resource Collection Mastersheet!Full Stack Engineering. The instructor
    # reading is the trustworthy one, so the module is dropped and logged.
    # A collision does NOT always mean the module is wrong. "UI & DOM" is a real
    # module that also leaked into an instructor name column; "Cathy Ma" is a
    # real person that leaked into a module column. Decide per label by SHAPE,
    # and log which way it went.
    def looks_like_person(s):
        toks = s.split()
        return (1 < len(toks) <= 4
                and all(re.fullmatch(r"[(\"']?[A-Za-z][A-Za-z.'\-]*[)\"']?", w) for w in toks)
                and not TOPIC_WORDS.search(s))

    inst_by_norm = {c["norm"]: c for c in cands if c["type"] == T_INSTRUCTOR}
    mod_by_norm = {c["norm"]: c for c in cands if c["type"] == T_MODULE}
    drop_mod, drop_inst = set(), set()
    for nz in set(inst_by_norm) & set(mod_by_norm):
        raw = mod_by_norm[nz]["raw"]
        if looks_like_person(raw):
            drop_mod.add(nz)
            rejected.append({"type": T_MODULE, "raw": raw,
                             "reason": "person name leaked into a module column",
                             "source": mod_by_norm[nz]["sources"][0]})
        else:
            drop_inst.add(nz)
            rejected.append({"type": T_INSTRUCTOR, "raw": inst_by_norm[nz]["raw"],
                             "reason": "module/topic string leaked into a name column",
                             "source": inst_by_norm[nz]["sources"][0]})
    collided = [mod_by_norm[n] for n in drop_mod] + [inst_by_norm[n] for n in drop_inst]
    dropped_norms = drop_mod
    cands = [c for c in cands
             if not (c["type"] == T_MODULE and c["norm"] in drop_mod)
             and not (c["type"] == T_INSTRUCTOR and c["norm"] in drop_inst)]
    pairs = [pr for pr in pairs
             if pr["module"] not in drop_mod and pr["instructor"] not in drop_inst]

    print("-" * 78)
    print("CROSS-TYPE COLLISIONS (module label that is also an instructor)")
    print("-" * 78)
    print(f"  {len(drop_mod)} dropped from MODULE (person leaked into a module column)")
    for n in sorted(drop_mod)[:5]:
        print(f"      {mod_by_norm[n]['raw']!r}  <- {mod_by_norm[n]['sources'][0].get('sheet')}")
    print(f"  {len(drop_inst)} dropped from INSTRUCTOR (module/topic leaked into a name column)")
    for n in sorted(drop_inst)[:5]:
        print(f"      {inst_by_norm[n]['raw']!r}  <- {inst_by_norm[n]['sources'][0].get('sheet')}")
    print()

    print("-" * 78)
    print("CANDIDATES BY TYPE  (raw rows -> distinct normalised)")
    print("-" * 78)
    by_type = defaultdict(list)
    for c in cands:
        by_type[c["type"]].append(c)
    print(f"  {'type':<12} {'raw':>7} {'distinct':>9}")
    for t in sorted(by_type):
        d = len({c["norm"] for c in by_type[t]})
        print(f"  {t:<12} {len(by_type[t]):>7} {d:>9}")
    print(f"  {'TOTAL':<12} {len(cands):>7}")
    print()

    print("-" * 78)
    print("INSTRUCTOR PIPELINE STATUS  (roster presence vs hiring-funnel outcome)")
    print("-" * 78)
    st = defaultdict(set)
    for c in by_type[T_INSTRUCTOR]:
        st[c.get("pipeline_status", "unknown")].add(c["norm"])
    allnames = {c["norm"] for c in by_type[T_INSTRUCTOR]}
    roster = st.get("roster", set())
    hired = st.get("hired", set())
    deliverable = roster | hired
    for k in sorted(st, key=lambda x: -len(st[x])):
        print(f"  {k:<14} {len(st[k]):>6} distinct")
    print(f"  {'-'*30}")
    print(f"  {'DELIVERABLE':<14} {len(deliverable):>6}  (roster or explicitly hired)")
    print(f"  {'candidates':<14} {len(allnames - deliverable):>6}  (in pipeline / rejected / lapsed only)")
    print(f"  {'TOTAL':<14} {len(allnames):>6}")
    print()
    print("  A person appearing in BOTH a roster and the funnel counts as deliverable.")
    print("  Counting the funnel as its outcome is how the reference implementation")
    print("  published 773 instructors against a real 351.")
    print()

    print("-" * 78)
    print("REJECTION LOG")
    print("-" * 78)
    print(f"  {len(rejected)} rejected")
    reasons = Counter(r["reason"] for r in rejected)
    for reason, n in reasons.most_common():
        print(f"    {n:>5}  {reason}")
    print()
    print("  sample (first 3 per reason):")
    seen = Counter()
    for r in rejected:
        if seen[r["reason"]] < 3:
            seen[r["reason"]] += 1
            s = r["source"]
            print(f"    [{r['type']}] {r['raw'][:50]!r}")
            print(f"        {r['reason']}  <- {s.get('file','?').split('/')[-1]}"
                  f"!{s.get('sheet','')} r{s.get('row','?')}")
    print()

    print("-" * 78)
    print("CLASS DELIVERY LOG — New Combined Schedule.xlsx")
    print("-" * 78)
    print(f"  {len(sched)} per-domain schedule sheets read "
          f"({sum(1 for _, d in sched if d)} mapped to a domain)")
    dp = [pr for pr in pairs if pr.get("delivered")]
    print(f"  {len(dp)} delivery rows -> "
          f"{len({(x['module'], x['instructor']) for x in dp})} distinct pairs")
    print()

    print("-" * 78)
    print("MODULE <-> INSTRUCTOR PAIRINGS EXTRACTED")
    print("-" * 78)
    ps = defaultdict(int)
    for pr in pairs:
        ps[f"{pr['source']['file'].split('/')[-1][:34]}!{pr['source']['sheet']}"] += 1
    for k in sorted(ps, key=lambda x: -ps[x]):
        print(f"  {ps[k]:>5}  {k}")
    print(f"  {len(pairs):>5}  TOTAL raw pairs "
          f"({len({(p['module'], p['instructor']) for p in pairs})} distinct)")
    print()

    print("-" * 78)
    print("EXPERTISE CLAIMS (expert_in) — declared subject, NOT teaching evidence")
    print("-" * 78)
    cb = defaultdict(int)
    for cl in claims:
        cb[cl["basis"]] += 1
    for k in sorted(cb):
        print(f"  {k:<16} {cb[k]:>6} claims")
    rec = sum(1 for cl in claims if cl["role_suffix_stripped"])
    print(f"  {'TOTAL':<16} {len(claims):>6} claims, "
          f"{len({cl['instructor'] for cl in claims})} distinct instructors")
    print(f"  role suffix stripped on {rec} claims (e.g. 'ML - Instructor' -> 'ML')")
    print()

    print("-" * 78)
    print("PROVENANCE COVERAGE")
    print("-" * 78)
    with_prov = sum(1 for c in cands if c.get("sources"))
    nonempty = sum(1 for c in cands if c.get("sources") and len(c["sources"]) >= 1)
    print(f"  candidates with a non-empty sources list : {nonempty}/{len(cands)} "
          f"({100*nonempty/max(1,len(cands)):.1f}%)")
    print(f"  candidates with NO provenance            : {len(cands)-with_prov}")
    print("  (reference implementation shipped 280 of 351 instructors with an empty")
    print("   source list — 3% real provenance. min_length: 1 is a HARD rule here.)")
    print()

    print("-" * 78)
    print("BLANK IDENTIFIERS AND EMPTY TOKENS — REPORTED AND RETAINED")
    print("-" * 78)
    print(f"  {len(blanks)} rows")
    for b in blanks[:14]:
        if "name" in b:
            print(f"    blank ENo   {b['name']:<24} {b['sheet']}!r{b['row']}")
        else:
            print(f"    empty token {b['raw']!r} -> {b['tokens']}  r{b['row']} c{b['column']} ({b['role']})")
    if len(blanks) > 14:
        print(f"    ... {len(blanks)-14} more")
    print()

    if missing:
        print("-" * 78)
        print("SOURCES DECLARED BUT NOT FOUND")
        print("-" * 78)
        for m in missing:
            print(f"    {m['file'].split('/')[-1]}!{m['sheet']} — {m['reason']}")
        print()

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES.write_text(json.dumps(
        {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "source": manifest["source"], "candidates": cands,
         "teaches_pairs": pairs,
         "expertise_claims": claims,
         "blank_identifiers": blanks}, indent=1), encoding="utf-8")
    REJECTIONS.write_text(json.dumps(
        {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "count": len(rejected), "rejections": rejected}, indent=1), encoding="utf-8")
    print(f"wrote {CANDIDATES.name} ({len(cands)} candidates)")
    print(f"wrote {REJECTIONS.name} ({len(rejected)} rejections)")

    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 02_extract\n\n")
        fh.write(f"- Candidates {len(cands)} | rejected {len(rejected)} | "
                 f"blank identifiers retained {len(blanks)}\n")
        for t in sorted(by_type):
            fh.write(f"    - {t}: {len(by_type[t])} raw, "
                     f"{len({c['norm'] for c in by_type[t]})} distinct\n")

    if not rejected:
        print("\nHARD FAIL — empty rejection log. The checks are not working.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
