#!/usr/bin/env python3
"""Run 5 browser check on the LOCAL real-data copy (:8766): the new screens
render with real data and without script errors. Prints counts only.

  Who teaches what (matrix, P/B1-B3 badges, filters, export), Programme
  timeline, Settings -> Sync (run log, Sync now), Data quality (sync sections),
  All records (legacy hidden by default; "Legacy only"), a current module's
  panel (owner by role P, backups B1..).
"""
from __future__ import annotations

import sys

import psycopg
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8766"
DB = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"


def main() -> int:
    c = psycopg.connect(DB)
    mod = c.execute("""select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
                       where t.key = 'module' and not n.is_legacy and cardinality(n.co_owner_record_ids) >= 2 order by n.id limit 1""").fetchone()[0]
    res, errs = {}, []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        page.goto(BASE + "/local-login")
        page.fill("#password", "ik-realdata-local")
        page.click("#submit")
        page.wait_for_url("**/kb/**")
        page.wait_for_selector("[data-testid=dash-grid]")

        page.goto(BASE + "/kb/#/teaching")
        page.wait_for_selector("[data-testid=teaching-matrix]", timeout=60000)
        res["teaching rows"] = page.locator("[data-testid=teaching-row]").count()
        res["teaching cells P"] = page.locator("[data-testid=teaching-cell].r-primary").count()
        res["teaching cells B1-B3"] = sum(page.locator(f"[data-testid=teaching-cell].r-backup_{i}").count() for i in (1, 2, 3))
        with page.expect_download() as dl:
            page.click("[data-testid=teaching-export]")
        res["teaching export rows"] = dl.value.path().read_text(encoding="utf-8-sig").count("\n") + 1
        page.select_option("[data-testid=teaching-role]", "primary")
        page.wait_for_function("() => document.querySelectorAll('[data-testid=teaching-cell]').length > 0 && "
                               "[...document.querySelectorAll('[data-testid=teaching-cell]')].every(x => x.textContent === 'P')")
        res["teaching role=primary cells"] = page.locator("[data-testid=teaching-cell]").count()
        page.select_option("[data-testid=teaching-role]", "")
        page.wait_for_function("() => document.querySelectorAll('[data-testid=teaching-row]').length === 25")
        page.check("[data-testid=teaching-legacy]")
        page.wait_for_function("() => document.querySelectorAll('[data-testid=teaching-row]').length > 25", timeout=60000)
        res["teaching rows incl. legacy"] = page.locator("[data-testid=teaching-row]").count()

        page.goto(BASE + "/kb/#/timeline")
        page.wait_for_selector("[data-testid=timeline-programme]", timeout=60000)
        res["timeline programmes"] = page.locator("[data-testid=timeline-programme]").count()
        res["timeline weeks"] = page.locator("[data-testid=timeline-week]").count()

        page.goto(BASE + "/kb/#/settings?tab=sync")
        page.wait_for_selector("[data-testid=sync-runs]", timeout=60000)
        res["sync runs listed"] = page.locator("[data-testid=sync-run]").count()
        before = res["sync runs listed"]
        page.click("[data-testid=sync-now]")
        page.wait_for_function(f"() => document.querySelectorAll('[data-testid=sync-run]').length > {before}", timeout=120000)
        res["sync runs after Sync now"] = page.locator("[data-testid=sync-run]").count()

        page.goto(BASE + "/kb/#/quality")
        page.wait_for_selector("[data-testid=q-sync-conflicts]", timeout=60000)
        res["quality: sync stats shown"] = page.locator("[data-testid=q-sync-conflicts], [data-testid=q-removed-at-source]").count()

        page.goto(BASE + "/kb/#/records")
        page.wait_for_selector("[data-testid=result-count]:not(:empty)", timeout=60000)
        res["records (default)"] = page.get_by_test_id("result-count").inner_text()
        page.goto(BASE + "/kb/#/records?legacy=only")
        page.wait_for_function("() => (document.querySelector('[data-testid=result-count]')||{}).textContent", timeout=60000)
        page.wait_for_selector("[data-testid=chip-legacy]")
        page.wait_for_timeout(800)
        res["records (legacy only)"] = page.get_by_test_id("result-count").inner_text()

        page.goto(BASE + f"/kb/#/records?open={mod}")
        page.wait_for_selector("[data-testid=panel-owner-record]", timeout=60000)
        res["panel: owner by role shown"] = page.locator("[data-testid=panel-owner-record] .role-badge").count()
        res["panel: backups shown"] = page.locator("[data-testid=panel-co-owner-records] .role-badge").count()
        page.click("[role=tab]:has-text('Relationships')")
        page.wait_for_selector("[data-testid=panel-relationships]")
        res["panel: role badges on relationships"] = page.locator("[data-testid=rel-role]").count()
        page.screenshot(path=sys.argv[1] if len(sys.argv) > 1 else "run5_panel.png")
        b.close()
    for k, v in res.items():
        print(f"{k}: {v}")
    print("page errors:", len(errs), errs[:3])
    ok = (not errs and res["teaching rows"] == 25 and res["teaching cells P"] == 23 and res["teaching cells B1-B3"] == 34
          and res["timeline programmes"] > 0 and res["sync runs after Sync now"] == res["sync runs listed"] + 1 and res["quality: sync stats shown"] == 2
          and res["panel: owner by role shown"] == 1 and res["panel: backups shown"] >= 2 and res["panel: role badges on relationships"] >= 3)
    print("UI CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
