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
    if node_type not in (T_PERSON, T_INSTRUCTOR):
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


def header_row(ws, wanted: str, limit: int = 4):
    """Find the row holding `wanted`. Headers are not always row 1."""
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=limit, values_only=True)):
        cells = [str(v).strip() if v is not None else "" for v in row]
        if wanted in cells:
            return i + 1, cells.index(wanted), cells
    return None, None, None


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
            hrow, hcol, _ = header_row(ws, column)
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
                    out.append({"type": node_type, "raw": raw, "norm": norm(raw),
                                "sources": [prov]})
    finally:
        wb.close()


def extract_workflows(root: Path, out: list, rejected: list) -> None:
    rel = "00-master/Team_Task___Workflow_Inventory"
    text = (root / rel).read_text(encoding="utf-8")
    theme = None
    for lineno, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            theme = (int(m.group(1)), m.group(2).strip())
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
    extract_domains(root, cands, rejected, blanks)
    # Domain labels are known only after extract_domains; the Slack grid uses
    # them as headers and they must not become people.
    DOMAIN_LABELS.update(c["raw"] for c in cands if c["type"] == T_DOMAIN)
    extract_slack_grid(root, cands, rejected)
    extract_people(root, cands, rejected, blanks)
    extract_programs(root, cands)
    for rel, sheet, col in SRC.INSTRUCTOR_SOURCES:
        scan_column(root, rel, sheet, col, T_INSTRUCTOR, cands, rejected, missing)
    for rel, sheet, col in SRC.MODULE_SOURCES:
        scan_column(root, rel, sheet, col, T_MODULE, cands, rejected, missing)

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
