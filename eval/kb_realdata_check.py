#!/usr/bin/env python3
"""Browser check of the LOCAL real-data copy on http://localhost:8766 (step 9).
Prints record ids and counts only, never names or values.

For the 5 programs with the most modules it compares, against the projection
(public.*) the records came from:
  - All records filtered "in this program"   vs the program's modules + sessions + weeks
  - Outline: the program's direct children    vs its contains edges
  - Record panel: Relationships tab count      vs the KB's relationships of that record
  - Graph (2 steps): records drawn, load time, frames per second while panning
plus the dashboard's numbers vs the import report.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psycopg
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8766"
DB = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    c = psycopg.connect(DB)
    progs = c.execute("""select n.id, n.external_id,
                            (select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                             where e.source_id = n.id and e.archived_at is null) as children,
                            (select count(*) from public.edges pe where pe.source_id = substr(n.external_id, 4) and pe.rel = 'contains') as proj_children,
                            (select count(*) from kb.edges e where (e.source_id = n.id or e.target_id = n.id) and e.archived_at is null) as rels
                         from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'program'
                         order by 3 desc, 1 limit 5""").fetchall()
    rep = json.loads((REPO / "backups" / "import-apply.json").read_text(encoding="utf-8"))
    problems = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1536, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:120]))
        page.goto(BASE + "/local-login")
        page.fill("#password", "ik-realdata-local")
        page.click("#submit")
        page.wait_for_url("**/kb/**")
        page.wait_for_selector("[data-testid=dash-grid]")
        recs = page.locator("[data-testid=dash-grid] .tile .v").all_inner_texts()
        print(f"dashboard tiles: {recs} | import report totals: {rep['kb_totals']}")
        if int(recs[0].replace(",", "")) != rep["kb_totals"]["records"] or int(recs[1].replace(",", "")) != rep["kb_totals"]["relationships"] \
                or int(recs[2].replace(",", "")) != rep["kb_totals"]["links"]:
            problems.append("dashboard totals differ from the import report")
        for pid, ext, children, proj_children, rels in progs:
            # All records, filtered to the program
            page.goto(BASE + f"/kb/#/records?parent={pid}")
            page.wait_for_selector("[data-testid=result-count]:not(:empty)")
            listed = page.get_by_test_id("result-count").inner_text()
            # Outline rooted at the program
            page.goto(BASE + f"/kb/#/outline?root={pid}")
            page.wait_for_timeout(800)
            # Record panel: relationships tab
            page.goto(BASE + f"/kb/#/records?open={pid}")
            page.get_by_test_id("tab-relationships").click()
            page.wait_for_timeout(500)
            shown_rels = page.get_by_test_id("rel").count()
            links_tab = page.get_by_test_id("tab-links").inner_text()
            # Graph, two steps out
            t0 = time.perf_counter()
            page.goto(BASE + f"/kb/#/graph/{pid}?depth=2")
            page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=60000)
            load_ms = (time.perf_counter() - t0) * 1000
            drawn = page.evaluate("() => window.__kbGraph.cy.nodes(':not(.cluster)').length")
            fps = page.evaluate("""async () => { const cy = window.__kbGraph.cy; let f = 0; const t0 = performance.now();
                await new Promise((d) => { const s = (t) => { f++; cy.panBy({ x: 3, y: 2 }); if (t - t0 < 2000) requestAnimationFrame(s); else d(); }; requestAnimationFrame(s); });
                return f / ((performance.now() - t0) / 1000); }""")
            ok = children == proj_children and shown_rels == rels
            print(f"program {pid} ({ext}): contains {children} (projection {proj_children}) | All records in it: {listed} | "
                  f"panel relationships {shown_rels}/{rels} | links tab '{links_tab}' | graph {drawn} records, {load_ms:.0f} ms, {fps:.0f} fps"
                  + ("" if ok else "  <-- MISMATCH"))
            if not ok:
                problems.append(f"program {pid}")
        b.close()
    if errs:
        problems.append(f"{len(errs)} script errors")
        print("script errors:", errs[:3])
    print("CHECK:", "PASS" if not problems else "PROBLEMS: " + "; ".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
