#!/usr/bin/env python3
"""Pre-fill the one-time OWNER sheet for the NP team to confirm (owner decision 2026-11-07, run C).

    python scripts/owner_sheet_prefill.py --db local|dev

Writes .measure/private/owner-sheet-run-c-<db>.xlsx (gitignored, local: it holds real names). Nothing is
written to the database. No owner is invented: a "suggested" cell holds only what a source says, with the
evidence next to it; everything else is blank for the NP team to fill in.

Tabs:
  Owners    one row per in-scope program, course and module (KYP-imported), with any owner the knowledge
            base already has, the suggestions the sources contain (KYP "owned by" notes, by program), and
            blank "Confirmed owners" / "Notes" columns.
  SME evidence   SME information found in registry files that is NOT in the knowledge base (older trackers):
            for the team to confirm or discard. Current SME assignments are in the knowledge base.
  Team members   the NP team member records owners must be chosen from.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402
from pipeline.lib import taxonomy as _tax                            # noqa: E402

OWNED_BY = _tax.edge_for_role("domain_primary")

LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
TRACKERS = re.compile(r"Content Tracker|Tracker$", re.I)


def db_url(which):
    if which == "local":
        return LOCAL
    from dotenv import dotenv_values
    u = dotenv_values(REPO / ".env").get("DEV_SUPABASE_DB_URL") or ""
    if which != "dev" or not u:
        sys.exit("use --db local or --db dev")
    return u


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    url = db_url(a.db)
    if PRODUCTION_REF in url:
        print("refused: that is the production database"); return 2
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    cur = json.loads((REPO / ".measure/kyp-c/curriculum.json").read_text(encoding="utf-8"))
    notes_by_prog = {}
    for n in cur["owner_notes"]:
        notes_by_prog.setdefault(n["program"], []).append(n)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Owners"
    hdr = ["Type", "Name", "Domain", "Programs (for courses / modules)", "Owners already in the knowledge base",
           "Suggested by the sources", "Evidence", "Confirmed owners (NP team members)", "Notes"]
    ws.append(hdr)
    with psycopg.connect(url, connect_timeout=30) as c:
        rows = c.execute(f"""
            select t.key, n.name, n.props->>'kyp_key',
                   (select string_agg(d.name, ', ') from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'in_domain'
                      join kb.nodes d on d.id = e.target_id where e.source_id = n.id and e.archived_at is null),
                   (select string_agg(o.name, ', ') from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = '{OWNED_BY}'
                      join kb.nodes o on o.id = e.target_id where e.source_id = n.id and e.archived_at is null),
                   (select string_agg(distinct p.name, ', ') from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                      join kb.nodes p on p.id = e.source_id join kb.node_types pt on pt.id = p.type_id
                      where e.target_id = n.id and e.archived_at is null and pt.key in ('program', 'course'))
            from kb.nodes n join kb.node_types t on t.id = n.type_id
            where n.archived_at is null and t.key in ('program', 'course', 'module') and n.props ? 'kyp_key'
            order by array_position(array['program','course','module'], t.key::text), n.name_norm""").fetchall()
        team = c.execute("""select n.name, n.props->>'team', n.props->>'title' from kb.nodes n join kb.node_types t on t.id = n.type_id
                            where t.key = 'team_member' and n.archived_at is null order by n.name_norm""").fetchall()
    for typ, name, kk, dom, have, parents in rows:
        sug, ev = "", ""
        if typ == "program" and kk in notes_by_prog:
            ns = notes_by_prog[kk]
            sug = ", ".join(sorted({x["name"] for x in ns}))
            ev = "; ".join(f"KYP note in section '{x['section']}': \"{x['note'][:80]}\"" for x in ns)
            ev += " (an owner of that KYP section, not necessarily of the program: please confirm)"
        ws.append([typ.capitalize(), name, dom or "", parents or "", have or "", sug, ev, "", ""])
    sm = wb.create_sheet("SME evidence")
    sm.append(["Source file (registry)", "Live link", "Row", "Note"])
    cat = json.loads((REPO / ".measure/sources/catalog.json").read_text(encoding="utf-8"))
    for it in cat["items"]:
        pv = " > ".join(it.get("provenance") or [])
        if not (re.search(r"SD[1-4]:", pv) and it.get("title") and TRACKERS.search(it["title"]) and it["mime"].endswith("spreadsheet")):
            continue
        t = REPO / ".measure/sources/text" / (it["resource_id"] + ".txt")
        if not t.exists():
            continue
        for line in t.read_text(encoding="utf-8", errors="replace").splitlines()[:80]:
            if line.count("|") >= 2 and not line.startswith("##"):
                sm.append([it["title"], it["url"], line[:400], "Older tracker; confirm before using as SME roles"])
    tw = wb.create_sheet("Team members")
    tw.append(["NP team member record", "Team", "Title"])
    for r in team:
        tw.append(list(r))
    for w in wb.worksheets:
        for cell in w[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DDEBF7")
        w.freeze_panes = "A2"
        for col in w.columns:
            w.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(x.value or "")) for x in col[:200]) + 2))
    out = REPO / ".measure" / "private" / f"owner-sheet-run-c-{a.db}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"owner sheet: {out.relative_to(REPO)} ({len(rows)} records, {sum(1 for r in rows if r[4])} with an owner already, "
          f"{sum(1 for r in rows if r[0] == 'program' and r[2] in notes_by_prog)} programs with a source suggestion, {len(team)} team members)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
