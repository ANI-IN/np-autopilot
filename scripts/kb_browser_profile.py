#!/usr/bin/env python3
"""Browser-side profile of every screen on a LOCAL server (run 6, B5): time to
interactive, JavaScript bytes loaded, console errors / page errors, graph
expand timings and heap growth over a long graph session.

    python scripts/kb_browser_profile.py --base http://localhost:8775 \
        --email <local admin> --password <local password> [--repeat 50] [--json out.json]

"Interactive" = the screen's content is in place: no skeleton and nothing
aria-busy left, measured from a FULL page load (cold navigation) of the
screen's URL. JS bytes = decoded size of every script the page loaded
(Resource Timing), so the vendored graph library shows up only where it loads.
Heap = performance.memory.usedJSHeapSize after a forced GC (Chrome
--js-flags=--expose-gc). Prints counts, ids and timings only. One browser,
one page (the laptop's memory). Take the browser lock first (.run6/browser.lock).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

SCREENS = [
    ("dashboard", "#/"), ("records", "#/records"), ("programs", "#/programs"), ("courses", "#/courses"),
    ("resources", "#/resources"), ("outline", "#/outline"), ("graph start", "#/graph"),
    ("teaching", "#/teaching"), ("timeline", "#/timeline"), ("activity", "#/activity"),
    ("quality", "#/quality"), ("approvals", "#/approvals"), ("archived", "#/archived"), ("guide", "#/guide"),
    ("settings", "#/settings?tab=types"), ("settings-members", "#/settings?tab=members"),
    ("settings-sync", "#/settings?tab=sync"),
]
SETTLED = """() => !document.querySelector('.skeleton, [aria-busy="true"]')
                 && !!document.querySelector('#view > *') && document.readyState === 'complete'"""
JS_BYTES = """() => performance.getEntriesByType('resource').filter((r) => /\\.m?js(\\?|$)/.test(r.name))
                 .reduce((a, r) => a + (r.decodedBodySize || 0), 0)"""
HEAP = "() => { if (window.gc) window.gc(); return performance.memory ? performance.memory.usedJSHeapSize : null; }"


def _neighbours(db: str, rid: str) -> list[str]:
    """Live neighbours of the record (ids only), from the local kb_* clone."""
    import re
    import psycopg
    if not re.fullmatch(r"kb_[a-z0-9_]{1,40}", db):
        sys.exit("--db must name a local kb_* database")
    with psycopg.connect(f"postgresql://postgres:postgres@127.0.0.1:54322/{db}") as c:
        return [str(r[0]) for r in c.execute(
            """select case when source_id = %s then target_id else source_id end from kb.edges
               where archived_at is null and (source_id = %s or target_id = %s) order by id limit 50""",
            (rid, rid, rid)).fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--repeat", type=int, default=50)
    ap.add_argument("--record", default="", help="a record id with many relationships, for the graph")
    ap.add_argument("--db", default="", help="the server's local kb_* database, for the record's neighbours")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    out: dict = {"screens": [], "problems": {}}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--js-flags=--expose-gc"])
        ctx = b.new_context(viewport={"width": 1536, "height": 900})
        page = ctx.new_page()
        cur = {"name": "sign-in"}

        def problem(kind, text):
            out["problems"].setdefault(cur["name"], []).append(f"{kind}: {text[:200]}")
        page.on("console", lambda m: problem("console." + m.type, m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: problem("pageerror", str(e)))

        page.goto(a.base + "/local-login")
        page.fill("#email", a.email)
        page.fill("#password", a.password)
        page.click("#submit")
        page.wait_for_url("**/kb/**", timeout=60000)
        page.wait_for_function(SETTLED, timeout=60000)

        for name, route in SCREENS:
            cur["name"] = name
            page.goto("about:blank")
            t0 = time.perf_counter()
            page.goto(a.base + "/kb/" + route)
            try:
                page.wait_for_function(SETTLED, timeout=120000, polling=50)
                ms = (time.perf_counter() - t0) * 1000
            except Exception:                                          # noqa: BLE001
                ms = None
                problem("timeout", "not settled after 120 s")
            page.wait_for_load_state("networkidle")
            out["screens"].append({"screen": name, "interactive_ms": round(ms) if ms else None,
                                   "js_kb": round(page.evaluate(JS_BYTES) / 1024, 1)})
            print(f"  {name:<18} {out['screens'][-1]['interactive_ms']} ms  JS {out['screens'][-1]['js_kb']} KB",
                  file=sys.stderr)

        if a.record:
            cur["name"] = "graph"
            page.goto("about:blank")
            t0 = time.perf_counter()
            page.goto(a.base + f"/kb/#/graph/{a.record}?depth=1")
            page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=60000)
            page.wait_for_function(SETTLED, timeout=60000)
            out["graph_open_ms"] = round((time.perf_counter() - t0) * 1000)
            out["graph_js_kb"] = round(page.evaluate(JS_BYTES) / 1024, 1)
            # Expand: the record's neighbours, one after another (each = request + layout + draw).
            ids = _neighbours(a.db, a.record) if a.db else []
            times = []
            for i in range(min(a.repeat, 50)):
                rid = ids[i % len(ids)] if ids else a.record
                times.append(page.evaluate("""async (id) => { const t = performance.now(); await window.__kbGraph.expand(id);
                                                             return performance.now() - t; }""", rid))
            out["expand_ms"] = {"n": len(times), "p50": round(statistics.median(times)), "p95": round(sorted(times)[int(0.95 * (len(times) - 1))]),
                                "max": round(max(times))}
            # Long session: open and leave the graph `repeat` times; heap after GC.
            heap = [page.evaluate(HEAP)]
            for i in range(a.repeat):
                page.evaluate("(h) => { location.hash = h; }", f"#/graph/{a.record}?depth=1")
                page.wait_for_function("(n) => window.__kbGraph && window.__kbGraph.loadedAt > n", arg=0, timeout=60000)
                page.evaluate("() => { window.__kbGraph.loadedAt = 0; location.hash = '#/records'; }")
                page.wait_for_function(SETTLED, timeout=60000)
                if (i + 1) % 10 == 0:
                    heap.append(page.evaluate(HEAP))
            out["graph_heap_mb"] = [round(h / 1048576, 1) for h in heap if h]
            print(f"  graph open {out['graph_open_ms']} ms, expand {out['expand_ms']}, heap MB {out['graph_heap_mb']}",
                  file=sys.stderr)

        cur["name"] = "np-map"
        page.goto("about:blank")
        t0 = time.perf_counter()
        page.goto(a.base + "/")
        page.wait_for_load_state("networkidle", timeout=120000)
        out["map_networkidle_ms"] = round((time.perf_counter() - t0) * 1000)
        out["map_js_kb"] = round(page.evaluate(JS_BYTES) / 1024, 1)
        b.close()

    errors = sum(len(v) for v in out["problems"].values())
    print(f"\n| Screen | Interactive ms (cold load) | JS KB |\n|---|---|---|")
    for s in out["screens"]:
        print(f"| {s['screen']} | {s['interactive_ms']} | {s['js_kb']} |")
    for k in ("graph_open_ms", "graph_js_kb", "expand_ms", "graph_heap_mb", "map_networkidle_ms", "map_js_kb"):
        if k in out:
            print(f"{k}: {out[k]}")
    print(f"console errors / page errors / timeouts: {errors} {sorted(out['problems'])}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
