#!/usr/bin/env python3
"""Run 6, Section 7: end-to-end workflows on the LOCAL real-data copy (:8766),
as the local admin, with the Graph page and the "/" map open in a second and
third tab. Every step is checked in the API, the database, the Graph page, the
"/" map and Activity (the sentence). Synthetic records only ("S7 ..."), which
the script deletes at the end. Prints counts, ids and PASS/FAIL per step.

  python eval/kb_workflow_check.py --base http://localhost:8766 \
      --email realdata-admin@interviewkickstart.com --password ik-realdata-local

Steps: create a module inside a current domain -> it appears on the Graph page
and the "/" map -> rename + summary + a relationship to an instructor -> both
reflect it -> Activity has a sentence for each step -> archive, then delete
permanently -> both drop it, Activity records it. Errors: an invalid name (422
naming the field), a stale version (409 with the current record), the network
dropped (the page says so and recovers). API vs database after each step.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.parse import urlparse

import psycopg
from playwright.sync_api import sync_playwright

DB = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
RESULTS: list[tuple[str, bool, str]] = []


def check(step, ok, note=""):
    RESULTS.append((step, bool(ok), note))
    print(f"{'PASS' if ok else 'FAIL'}  {step}" + (f"  ({note})" if note else ""))


def wait(page, js, timeout=8.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if page.evaluate(js):
                return round(time.monotonic() - t0, 2)
        except Exception:                                              # noqa: BLE001
            pass
        time.sleep(0.25)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    a = ap.parse_args()
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    db = psycopg.connect(DB, autocommit=True)
    dom = db.execute("""select n.id, n.name from kb.nodes n join kb.node_types t on t.id = n.type_id
                        where t.key = 'domain' and n.archived_at is null and not n.is_legacy order by n.name limit 1""").fetchone()
    ins = db.execute("""select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
                        where t.key = 'instructor' and n.archived_at is null and not n.is_legacy order by n.name limit 1""").fetchone()[0]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1536, "height": 900})
        app = ctx.new_page()
        errors = []
        for pg in (app,):
            pg.on("pageerror", lambda e: errors.append(str(e)[:160]))
        app.goto(a.base + "/local-login")
        app.fill("#email", a.email)
        app.fill("#password", a.password)
        app.click("#submit")
        app.wait_for_url("**/kb/**", timeout=60000)
        app.wait_for_selector("[data-testid=dash-grid]", timeout=60000)

        def api(method, path, body=None):
            return app.evaluate("""async ([m, p, b]) => {
                const s = JSON.parse(localStorage.getItem('np_session') || 'null');
                const r = await fetch('/api/kb' + p, { method: m, headers: { 'content-type': 'application/json',
                    authorization: 'Bearer ' + (s && s.access_token) }, body: b ? JSON.stringify(b) : undefined });
                let j = null; try { j = await r.json(); } catch (e) { /* empty */ }
                return [r.status, j]; }""", [method, path, body])

        graph = ctx.new_page(); graph.on("pageerror", lambda e: errors.append("graph: " + str(e)[:160]))
        graph.goto(a.base + f"/kb/#/graph/{dom[0]}?depth=1")
        npmap = ctx.new_page(); npmap.on("pageerror", lambda e: errors.append("map: " + str(e)[:160]))
        npmap.goto(a.base + "/")
        check("Graph page loaded (a current domain, 1 step)", wait(graph, "!!(window.__kbGraph && window.__kbGraph.cy && window.__kbGraph.loadedAt)", 60) is not None)
        check('"/" map loaded and following the change feed', wait(npmap, "!!(window.__NP_LIVE && window.__NP_LIVE.cursor !== null)", 60) is not None)

        # 1. create
        s, rec = api("POST", "/nodes", {"type": "module", "name": "S7 Workflow Module", "parents": [str(dom[0])]})
        check("admin creates a module (API 201)", s == 201, f"status {s}")
        rid = rec["id"]
        inside = db.execute("""select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                               where et.key = 'contains' and e.source_id = %s and e.target_id = %s and e.archived_at is null""", (dom[0], rid)).fetchone()[0]
        check("database has it, inside the domain (contains)", inside == 1)
        t = wait(graph, f"!!window.__kbGraph.cy.getElementById('{rid}').length", 10)
        check("Graph page shows it without a reload", t is not None, f"{t} s")
        t = wait(npmap, f"window.__NP.data.nodes.some((n) => n.id === '{rid}')", 10)
        check('"/" map shows it without a reload', t is not None, f"{t} s")
        # 2. update properties and a relationship
        s, rec2 = api("PATCH", f"/nodes/{rid}", {"version": rec["version"], "name": "S7 Workflow Module renamed", "summary": "Section 7 check"})
        check("rename + summary (API 200)", s == 200, f"status {s}")
        s, e = api("POST", "/edges", {"type": "teaches", "source_id": str(ins), "target_id": rid})
        check("relationship to an instructor (API 201)", s == 201, f"status {s}")
        row = db.execute("select name, summary, version from kb.nodes where id = %s", (rid,)).fetchone()
        s, got = api("GET", f"/nodes/{rid}")
        check("API and database agree after the edit", got["name"] == row[0] and got["summary"] == row[1] and got["version"] == row[2])
        t = wait(graph, f"window.__kbGraph.cy.getElementById('{rid}').data('label') === 'S7 Workflow Module renamed' && !!window.__kbGraph.cy.getElementById('{e['id']}').length", 10)
        check("Graph page shows the new name and the relationship", t is not None, f"{t} s")
        t = wait(npmap, f"window.__NP.data.nodes.some((n) => n.id === '{rid}' && n.l === 'S7 Workflow Module renamed') && "
                        f"window.__NP.data.edges.some((x) => (x.s === '{rid}' || x.t === '{rid}'))", 10)
        check('"/" map shows the new name and the relationship', t is not None, f"{t} s")
        # 3. errors
        s, out = api("POST", "/nodes", {"type": "module", "name": "   "})
        check("invalid input: 422 naming the field", s == 422 and (out or {}).get("field") == "name", f"{s} {(out or {}).get('field')}")
        s, out = api("PATCH", f"/nodes/{rid}", {"version": rec["version"], "summary": "stale"})
        check("stale version: 409 with the current record", s == 409 and (out or {}).get("current", {}).get("id") == rid, f"status {s}")
        app.goto(a.base + "/kb/#/records")
        app.wait_for_selector("[data-testid=result-count]:not(:empty)", timeout=60000)
        ctx.set_offline(True)
        app.evaluate("() => { location.hash = '#/quality'; }")
        t = wait(app, "document.body.innerText.match(/offline|network|connection|could not|try again/i) !== null", 12)
        check("network dropped: the page says so", t is not None)
        ctx.set_offline(False)
        app.evaluate("() => { location.hash = '#/'; }")
        t = wait(app, "!!document.querySelector('[data-testid=dash-grid]')", 20)
        check("network back: the page recovers", t is not None)
        # 4. archive, then delete permanently
        s, cur = api("GET", f"/nodes/{rid}")
        s, _ = api("POST", f"/nodes/{rid}/archive", {"version": cur["version"]})
        check("archive (API 200)", s == 200, f"status {s}")
        t = wait(graph, f"!window.__kbGraph.cy.getElementById('{rid}').length", 10)
        check("Graph page drops it", t is not None, f"{t} s")
        t = wait(npmap, f"!window.__NP.data.nodes.some((n) => n.id === '{rid}')", 10)
        check('"/" map drops it', t is not None, f"{t} s")
        s, _ = api("DELETE", f"/nodes/{rid}")
        check("permanent delete (API 200)", s == 200, f"status {s}")
        check("database: gone, with its relationship",
              db.execute("select count(*) from kb.nodes where id = %s", (rid,)).fetchone()[0] == 0
              and db.execute("select count(*) from kb.edges where id = %s", (e["id"],)).fetchone()[0] == 0)
        # 5. Activity: a sentence for each step
        s, act = api("GET", f"/activity?record={rid}&limit=50")
        sentences = [x.get("sentence", "") for x in (act or {}).get("items", [])]
        for x in sentences:
            print("   activity:", x[:160])
        want = {"created": "created module 'S7 Workflow Module'", "renamed": "to 'S7 Workflow Module renamed' and updated its summary",
                "linked": "linked", "archived": "archived module", "deleted": "permanently deleted module"}
        for k, needle in want.items():
            check(f"Activity sentence: {k}", any(needle in x for x in sentences), next((x for x in sentences if needle in x), "missing")[:120])
        check("no page errors in the three tabs", not errors, "; ".join(errors[:2]))
        b.close()
    fails = [r for r in RESULTS if not r[1]]
    print(f"\nWORKFLOWS: {'PASS' if not fails else 'FAIL'} ({len(RESULTS) - len(fails)}/{len(RESULTS)})")
    print(json.dumps([r[0] for r in fails]))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
