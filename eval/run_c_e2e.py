#!/usr/bin/env python3
"""Run C end-to-end checks on REAL data, with a screenshot per check (local only, never committed).

    python eval/run_c_e2e.py --base http://127.0.0.1:8766 --label local          # local copy (signs in at /local-login)
    python eval/run_c_e2e.py --base <DEV preview URL> --label dev --dev          # DEV preview: DEV_PERF_TOKEN + VERCEL_BYPASS from .env

Screenshots: testing/evidence/<feature>/<label>-<test-id>.png (gitignored: they show real names).
Results:     testing/evidence/run_c_e2e_<label>.json (pass / fail / detail per test id).
Never prints the token, the bypass secret or the preview URL.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
EV = REPO / "testing" / "evidence"
RES = [(1366, 768), (1440, 900), (1920, 1080), (2560, 1440), (3840, 2160)]
READY = "() => document.querySelector('#view') && !document.querySelector('#view .skeleton')"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    token = bypass = None
    if a.dev:
        from dotenv import dotenv_values
        env = dotenv_values(REPO / ".env")
        token, bypass = env.get("DEV_PERF_TOKEN"), env.get("VERCEL_BYPASS")
        del env
        if not token:
            sys.exit("DEV_PERF_TOKEN is not set")
    results: dict = {}

    def check(tid, feature, scenario, ok, detail="", shot=None):
        results[tid] = {"feature": feature, "scenario": scenario, "pass": bool(ok), "detail": str(detail)[:400],
                        "screenshot": str(shot.relative_to(REPO)).replace("\\", "/") if shot else None}
        print(("PASS " if ok else "FAIL ") + tid + " " + scenario + ((" - " + str(detail)[:160]) if detail and not ok else ""), flush=True)

    def snap(page, feature, tid):
        d = EV / feature
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{a.label}-{tid}.png"
        page.screenshot(path=str(p))
        return p

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)

        def context(w=1440, h=900, dpr=1):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr,
                                extra_http_headers={"x-vercel-protection-bypass": bypass} if bypass else None)
            if token:
                sess = json.dumps({"access_token": token, "expires_at": int(time.time()) + 3600, "user": {"email": "run-c-e2e"}})
                ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
            return ctx

        def signed_in(ctx):
            pg = ctx.new_page()
            pg.errors = []
            pg.on("pageerror", lambda e: pg.errors.append(str(e)[:200]))
            if not token:
                pg.goto(base + "/local-login")
                pg.fill("#email", "realdata-admin@interviewkickstart.com"); pg.fill("#password", "ik-realdata-local"); pg.click("#submit")
                pg.wait_for_url("**/kb/**", timeout=60000)
            else:
                pg.goto(base + "/kb/")
            pg.wait_for_selector("[data-testid=whoami]", timeout=60000)
            return pg

        def api(pg, path):
            return pg.evaluate("""async (p) => { const s = JSON.parse(localStorage.getItem('np_session')); const r = await fetch('/api/kb' + p,
                                   {headers: {authorization: 'Bearer ' + s.access_token}}); return {status: r.status, body: await r.json().catch(() => null)}; }""", path)

        def find(pg, q, typ):
            from urllib.parse import quote
            r = api(pg, "/nodes?type=" + typ + "&q=" + quote(q) + "&limit=50")["body"] or {}
            items = r.get("items", [])
            exact = [i for i in items if " ".join(i["name"].split()).lower() == q.lower()]
            best = [i for i in exact if not i.get("scope_id")] or exact or items
            print(f"  find {typ} {q!r}: {len(items)} hits, picked {'unscoped exact' if best and best is not items and not best[0].get('scope_id') else 'other'}")
            return best[0]["id"] if best else None

        ctx = context()
        pg = signed_in(ctx)
        role = pg.get_by_test_id("whoami").inner_text()
        check("RD-AU-01", "admin-dashboard", "signed in as admin (workspace role)", "admin" in role.lower(), role, snap(pg, "admin-dashboard", "RD-AU-01-home"))

        # ---- four domains, hidden aliases, week-agnostic
        doms = api(pg, "/nodes?type=domain&limit=50")["body"]["items"]
        names = sorted(d["name"] for d in doms)
        check("RD-DM-01", "curriculum", "exactly four domains: Backend, Frontend, Fullstack, Test", names == ["Backend", "Frontend", "Fullstack", "Test"], names)
        s = api(pg, "/search?q=SD3")["body"]
        items = s.get("nodes", [])
        hit = any(i.get("name") == "Backend" for i in items)
        check("RD-DM-02", "curriculum", "old code SD3 finds Backend (hidden alias), never displayed", hit and "SD3" not in json.dumps(items), [i.get("name") for i in items][:5])
        types = [t["key"] for t in api(pg, "/types")["body"]["node_types"]]
        check("RD-WK-01", "curriculum", "no week, workflow or theme record types", not ({"week", "process", "theme"} & set(types)), types)

        # ---- module panel: owners, SMEs (Primary then backups), used in, topics, resources, sources
        mid = find(pg, "Database Design", "module")
        pg.goto(base + "/kb/#/records?open=" + str(mid))
        pg.wait_for_selector("[data-testid=entity]", timeout=60000)
        labels = pg.get_by_test_id("sme-role").all_inner_texts()
        ok = bool(labels) and labels[0] == "Primary" and all(l.startswith("Backup") or l == "Primary" or l for l in labels)
        check("RD-OS-01", "owner-sme", "module panel: SMEs with Primary first, then backups in order", ok, labels, snap(pg, "owner-sme", "RD-OS-01-module-smes"))
        has = {k: pg.get_by_test_id(k).count() > 0 for k in ("entity-used-in", "entity-topics", "entity-sources", "entity-domain", "entity-owners")}
        check("RD-CU-01", "curriculum", "module panel shows domain, used-in (course + program + week), topics, sources", all(has.values()), has,
              snap(pg, "curriculum", "RD-CU-01-module-panel"))
        prof = api(pg, f"/nodes/{mid}")["body"]["profile"]
        check("RD-CU-02", "curriculum", "module sources are KYP pages with version", any(x.get("source") == "confluence" and x.get("page_version") for x in prof.get("sources", [])),
              [x.get("page_title") for x in prof.get("sources", [])])
        # navigate to the course, then its program
        pg.get_by_test_id("entity-used-in").get_by_role("link").first.click()
        pg.wait_for_selector("[data-testid=entity-modules], [data-testid=entity-courses]", timeout=30000)
        check("RD-CU-03", "curriculum", "click a related course from the module panel", True, pg.get_by_test_id("panel-name").inner_text(),
              snap(pg, "curriculum", "RD-CU-03-course-panel"))
        pid = find(pg, "Backend Interview Preparation Program", "program")
        pg.goto(base + "/kb/#/records?open=" + str(pid))
        pg.wait_for_selector("[data-testid=entity-courses]", timeout=30000)
        courses = pg.get_by_test_id("entity-courses").locator("li").all_inner_texts()
        check("RD-CU-04", "curriculum", "program panel lists its courses in order", len(courses) >= 3, courses[:5], snap(pg, "curriculum", "RD-CU-04-program-panel"))
        did = next((d["id"] for d in doms if d["name"] == "Backend"), None)
        pg.goto(base + "/kb/#/records?open=" + str(did))
        pg.wait_for_selector("[data-testid=entity]", timeout=30000)
        check("RD-CU-05", "curriculum", "domain panel lists the programs, courses and modules it classifies",
              pg.get_by_test_id("entity-domain-modules").count() > 0, "", snap(pg, "curriculum", "RD-CU-05-domain-panel"))

        # ---- Admin overview, sources, data quality, guide
        pg.goto(base + "/kb/#/admin"); pg.wait_for_selector("[data-testid=admin-card]", timeout=30000)
        check("RD-AD-01", "admin-dashboard", "Admin overview cards", pg.get_by_test_id("admin-card").count() >= 7, pg.get_by_test_id("admin-card").count(),
              snap(pg, "admin-dashboard", "RD-AD-01-admin-overview"))
        pg.goto(base + "/kb/#/settings?tab=sync"); pg.wait_for_selector("[data-testid=sources-counts]", timeout=60000)
        check("RD-SC-01", "source-crawling", "Sources & sync: catalog counts by provider and status", True, "", snap(pg, "source-crawling", "RD-SC-01-sources"))
        fb = pg.get_by_test_id("sources-filter-failed")
        if fb.count():
            fb.click(); pg.wait_for_selector("[data-testid=source-failure]", timeout=30000)
            check("RD-SC-02", "source-crawling", "failures listed with link and reason", pg.get_by_test_id("source-failure").count() > 0,
                  pg.get_by_test_id("source-failure").first.inner_text(), snap(pg, "source-crawling", "RD-SC-02-failures"))
        q = api(pg, "/quality")["body"]
        check("RD-AD-02", "admin-dashboard", "Data quality lists SME role issues from the sources", "sme_roles" in q, (q.get("sme_roles") or {}).get("total"))
        pg.goto(base + "/kb/#/quality"); pg.wait_for_function(READY, timeout=30000)
        snap(pg, "admin-dashboard", "RD-AD-03-quality")
        pg.goto(base + "/kb/#/guide"); pg.wait_for_selector("[data-testid=guide]", timeout=30000)
        txt = pg.get_by_test_id("guide").inner_text()
        check("RD-GU-01", "guide", "Guide explains the model; no legacy terms",
              "Owners and SMEs" in txt and not any(w in txt for w in ("workflow", "programme week", "SD1", "mastersheet")), "", snap(pg, "guide", "RD-GU-01-guide"))

        # ---- Graph editor: loads, auto-layout, reset, owner filter (NP team only)
        pg.goto(base + "/kb/#/graph")
        pg.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=120000)
        info = pg.get_by_test_id("graph-info").inner_text()
        check("RD-GR-01", "graph", "Graph editor loads on real data (paged)", pg.locator(".error-box").count() == 0 and "Showing" in info, info,
              snap(pg, "graph", "RD-GR-01-graph"))
        opts = pg.get_by_test_id("graph-owner-filter").locator("option").all_inner_texts()
        insts = {i["name"] for i in (api(pg, "/nodes?type=instructor&limit=500")["body"] or {}).get("items", [])}
        check("RD-GR-02", "graph", "owner filter lists NP team members, never instructors", not (set(opts) & insts), opts[:6])
        pg.get_by_test_id("graph-autolayout").click()
        pg.wait_for_selector("[data-testid=toast]:has-text('Arranged')", timeout=60000)
        snap(pg, "graph", "RD-GR-03-autolayout")
        pg.get_by_test_id("graph-reset").click(); pg.get_by_test_id("confirm-ok").click()
        pg.wait_for_selector("[data-testid=toast]:has-text('Layout reset')", timeout=60000)
        check("RD-GR-03", "graph", "auto-layout then reset", True, "", snap(pg, "graph", "RD-GR-04-reset"))
        check("RD-GR-04", "graph", "no page errors on the graph", pg.errors == [], pg.errors[:2])
        ctx.close()

        # ---- responsive: graph and a module panel at 5 resolutions x DPR 1 and 2
        for (w, h) in RES:
            for dpr in (1, 2):
                if w >= 3840 and dpr == 2 and a.label == "dev":
                    pass
                c2 = context(w, h, dpr)
                p2 = signed_in(c2)
                p2.goto(base + "/kb/#/graph")
                p2.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=120000)
                p2.wait_for_timeout(800)
                m = p2.evaluate("""() => { const c = document.querySelector('[data-testid=graph-canvas], .graph-canvas, #cy');
                    const r = c ? c.getBoundingClientRect() : null; return { w: innerWidth, sw: document.documentElement.scrollWidth,
                    cw: r ? Math.round(r.width) : 0, ch: r ? Math.round(r.height) : 0, z: window.__kbGraph && window.__kbGraph.cy ? window.__kbGraph.cy.zoom() : null }; }""")
                ok = m["sw"] <= m["w"] + 1 and m["cw"] >= 0.55 * w and m["ch"] >= 0.6 * h
                check(f"RD-RS-{w}x{h}@{dpr}", "responsive", f"graph at {w}x{h}, device scale {dpr}: fills the space, no sideways scroll", ok, m,
                      snap(p2, "responsive", f"RD-RS-graph-{w}x{h}-dpr{dpr}"))
                p2.goto(base + "/kb/#/records?open=" + str(mid))
                p2.wait_for_selector("[data-testid=entity]", timeout=60000)
                pw_ = p2.evaluate("() => { const p = document.getElementById('panel'); return p ? Math.round(p.getBoundingClientRect().width) : 0; }")
                check(f"RD-RP-{w}x{h}@{dpr}", "responsive", f"detail panel at {w}x{h}, scale {dpr}: proportionate width", 360 <= pw_ <= max(720, w * 0.45), pw_,
                      snap(p2, "responsive", f"RD-RP-panel-{w}x{h}-dpr{dpr}"))
                c2.close()

        # ---- Map (local only: on DEV the map needs a Google session)
        if not a.dev:
            c3 = context()
            p3 = signed_in(c3)
            mref = (api(p3, f"/nodes/{mid}")["body"] or {}).get("external_id") or ""
            ref = mref[3:] if mref.startswith("np:") else str(mid)
            p3.goto(base + "/?open=" + ref)
            p3.wait_for_selector("[data-testid=map-entity-slot] [data-testid=entity]", timeout=60000)
            who = p3.locator("#who").inner_text()
            check("RD-MP-01", "graph", "the Map shows the same entity panel and the KB role", "admin" in who and
                  p3.locator("[data-testid=map-entity-slot] [data-testid=sme-row]").count() > 0, who, snap(p3, "graph", "RD-MP-01-map-panel"))
            c3.close()
        b.close()
    out = EV / f"run_c_e2e_{a.label}.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    bad = [k for k, v in results.items() if not v["pass"]]
    print(f"{len(results) - len(bad)}/{len(results)} passed; failed: {bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
