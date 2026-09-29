#!/usr/bin/env python3
"""Accuracy item 3 — re-derive the mastersheet facts and diff against the graph.

INDEPENDENT ON PURPOSE. This does NOT import `pipeline/lib/mastersheet.py`. It
opens the workbook with openpyxl and reads the cells itself, because a diff
that runs the pipeline's own parser against the pipeline's own output tests
that the code is self-consistent, not that it is right. Two readings of the
same spreadsheet that disagree is the signal worth having.

WHAT IS RE-DERIVED
  module      every `Week N - <name>` row in the first section of a domain tab
  sessions    every resource row under a module that carries a name and a link
  instructors the per-module block, primary and backups, by role
  task        the graded exercise session, kept distinct from the review
              session, which the sheet names separately

PROGRAM WEEK IS NOT IN THE SPREADSHEET. `Week N` in the sheet is a SEQUENCE
inside the domain, not a calendar week — the owner said so before the crawl
(docs/PRE-CRAWL-DECISIONS.md) and `curriculum.program_week_from_local` raises
rather than derive one arithmetically. The programme weeks are an owner fact in
`config/out-of-corpus-facts.yaml`. So the re-derivation checks the RULE: week ==
domain's first programme week + (sequence - 1), read from that file, and any
mismatch is a real difference.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl                                                      # noqa: E402
import yaml                                                          # noqa: E402

from pipeline.lib import taxonomy as tax                             # noqa: E402
from pipeline.lib import freshness                                  # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR, REPO_ROOT   # noqa: E402

OWNER_FACTS = REPO_ROOT / "config" / "mastersheet-owner-facts.yaml"
SHEET = (REPO_ROOT / ".drive-cache" / "02-curriculum" /
         "Resource Collection Mastersheet (Software + System).xlsx")

TABS = {"Full Stack Engineering": "full-stack", "Frontend Engineering": "frontend",
        "Backend Engineering": "backend", "Test Engineering": "testing"}

MODULE_RE = re.compile(r"^Week\s*(\d+)(?:\s*/\s*\d+)?\s*[-–]\s*(.+)$", re.I)


def cell(rows, r, c):
    if r >= len(rows):
        return ""
    row = rows[r]
    return "" if c >= len(row) or row[c] is None else str(row[c]).strip()


def reread(path: Path) -> dict:
    """The spreadsheet, read from scratch."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for tab, slug in TABS.items():
        rows = list(wb[tab].iter_rows(values_only=True))
        n = len(rows)
        folder_row = next((i for i in range(n)
                           if cell(rows, i, 0).lower().startswith("drive folder")), n)
        topic_row = next((i for i in range(n)
                          if cell(rows, i, 0).strip().lower() == "topic"
                          and "instructor" in cell(rows, i, 1).lower()), None)
        table_row = next((i for i in range(n)
                          if "name of the instructor" in cell(rows, i, 0).lower()), n)

        mods = [(i, int(m.group(1)), m.group(2).strip())
                for i in range(1, folder_row)
                for m in [MODULE_RE.match(cell(rows, i, 0))] if m]
        for idx, (row_i, seq, name) in enumerate(mods):
            stop = mods[idx + 1][0] if idx + 1 < len(mods) else folder_row
            sessions = []
            for i in range(row_i, stop):
                nm, link = cell(rows, i, 2), cell(rows, i, 5)
                if nm and link.startswith("http"):
                    sessions.append(nm)
            out[(slug, seq)] = {"name": name, "sessions": sessions,
                                "primary": [], "backups": []}

        if topic_row is not None:
            for i in range(topic_row + 1, table_row):
                m = MODULE_RE.match(cell(rows, i, 0))
                if not m:
                    continue
                key = (slug, int(m.group(1)))
                if key not in out:
                    continue
                split = lambda s: [p.strip() for p in re.split(r"\s*[/,]\s*", s)
                                   if p.strip()]
                out[key]["primary"] = split(cell(rows, i, 1))
                out[key]["backups"] = sum((split(cell(rows, i, c))
                                           for c in (2, 3, 4)), [])
    wb.close()
    return out


def from_graph() -> dict:
    g = json.loads((KNOWLEDGE_DIR / "content_graph.json").read_text(encoding="utf-8"))
    N = {n["id"]: n for n in g["nodes"]}
    OUT = collections.defaultdict(list)
    for e in g["edges"]:
        OUT[e["source"]].append(e)
    R = {r: tax.edge_for_role(r) for r in
         ("module_session", "module_instructor", "module_week")}
    out = {}
    for m in g["nodes"]:
        if m["type"] != "module":
            continue
        sessions, prim, back, week = [], [], [], None
        for e in OUT[m["id"]]:
            if e["rel"] == R["module_session"] and not e.get("attached_file"):
                sessions.append(N[e["target"]]["label"])
            elif e["rel"] == R["module_instructor"]:
                (prim if e.get("instructor_role") == "primary" else back).append(
                    N[e["target"]]["label"])
            elif e["rel"] == R["module_week"]:
                week = N[e["target"]].get("number")
        out[(m.get("domain_slug"), m.get("sequence"))] = {
            "name": m["label"], "sessions": sessions,
            "primary": prim, "backups": back, "week": week}
    return out


def expected_weeks() -> dict:
    """{(slug, sequence): week} from the owner fact.

    The fact records an EXPLICIT per-module mapping, not a first-week plus an
    offset. The first version of this function assumed the offset rule and
    reported 11 false differences — the graph was right and the re-derivation
    was wrong, which is the failure mode a diff is most likely to have.
    """
    facts = yaml.safe_load((CONFIG_DIR / "out-of-corpus-facts.yaml")
                           .read_text(encoding="utf-8"))
    for f in facts.get("facts") or []:
        if isinstance(f, dict) and f.get("id") == "rowb-program-weeks":
            return {(slug, int(seq)): int(wk)
                    for slug, per in (f.get("weeks") or {}).items()
                    for seq, wk in per.items()}
    return {}


def main() -> int:
    if not SHEET.exists():
        print(f"  the corpus cache is absent: {SHEET}")
        return 0
    # never re-derive from a copy older than Drive (owner request 2026-09-30)
    freshness.require_fresh("mastersheet_rederive")
    sheet, graph = reread(SHEET), from_graph()
    expected = expected_weeks()
    # A role the OWNER withdrew (config/mastersheet-owner-facts.yaml, origin:
    # hand) is still in the sheet and deliberately not in the graph. Taken off
    # the sheet side here and LISTED, so it is an explained difference, never
    # a silent one — and a fact naming a person the sheet no longer lists is
    # itself a difference.
    explained, stale = [], []
    # Read straight from the YAML: this check must not import the parser it
    # is checking (tests/test_mastersheet_rederivation.py).
    facts = yaml.safe_load(OWNER_FACTS.read_text(encoding="utf-8")) or {}
    for fact in facts.get("withdrawn_roles") or []:
        assert fact.get("origin") == "hand" and fact.get("asserted_by"), fact
        dom, seq, role, person = (fact["domain"], int(fact["sequence"]),
                                  fact["role"], fact["person"])
        s = sheet.get((dom, seq))
        field = "primary" if role == "primary" else "backups"
        if s and person in s[field]:
            s[field] = [x for x in s[field] if x != person]
            explained.append(f"{dom}/{seq} {role} {person} — {fact['fact']} "
                             f"({fact['asserted_by']}, {fact['asserted_at']})")
        else:
            stale.append(((dom, seq), "stale owner fact", f"{role} {person} is not in "
                          "the sheet", "config/mastersheet-owner-facts.yaml"))

    keys = sorted(set(sheet) | set(graph))
    print("=" * 96)
    print("ACCURACY ITEM 3 — mastersheet re-derived independently, diffed")
    print("=" * 96)
    print(f"\n  {'module':26} {'sessions':>16} {'primary':>14} {'backups':>14} "
          f"{'week':>10}")
    print("  " + "-" * 92)
    diffs = []
    for k in keys:
        s, gph = sheet.get(k), graph.get(k)
        if s is None:
            diffs.append((k, "in the graph, not in the sheet", "", "")); continue
        if gph is None:
            diffs.append((k, "in the sheet, not in the graph", "", "")); continue
        cells = []
        for field in ("sessions", "primary", "backups"):
            a, b = sorted(s[field]), sorted(gph[field])
            same = a == b
            cells.append(f"{len(a)}=={len(b)}" if same else f"{len(a)}!={len(b)}")
            if not same:
                diffs.append((k, field, a, b))
        exp, wk = expected.get(k), gph.get("week")
        if exp is not None:
            cells.append(f"{wk}" if wk == exp else f"{wk} != {exp}")
            if wk != exp:
                diffs.append((k, "program week", exp, wk))
        else:
            cells.append(f"{wk} (no owner fact)")
        label = f"{k[0]}/{k[1]} {s['name']}"[:26]
        print(f"  {label:26} {cells[0]:>16} "
              f"{cells[1]:>14} {cells[2]:>14} {cells[3]:>10}")

    print("\n" + "=" * 96)
    diffs += stale
    for x in explained:
        print(f"  explained by an owner fact: {x}")
    if diffs:
        print(f"  {len(diffs)} DIFFERENCE(S)")
        for k, field, a, b in diffs:
            print(f"    {k[0]}/{k[1]:<2} {field}")
            print(f"      sheet: {a}")
            print(f"      graph: {b}")
    else:
        print("  0 unexplained differences across "
              f"{len(keys)} modules — sessions, instructors by role, and "
              "programme week all re-derive identically.")
    print("=" * 96)
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
