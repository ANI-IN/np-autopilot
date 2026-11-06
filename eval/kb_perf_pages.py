#!/usr/bin/env python3
"""Page-level performance of the workspace and the map, the way a person meets it:
cold and warm page loads, navigation between views, every API call (duration and
size), LCP and CLS, palette search latency, the Graph's load and group-by-type,
and the map's time to interactive. Counts and timings only, never record content.

LOCAL servers (sign in through /local-login), or the DEV preview with a KB API
token (`--token`, an ikkb_ token the owner minted; the workspace accepts it on
/api/kb/*; the map needs a real Google session and is skipped).

    python eval/kb_perf_pages.py --base http://localhost:8766 \
        --email realdata-admin@interviewkickstart.com --password ... --label before
    python eval/kb_perf_pages.py --base https://np-autopilot-kb-dev.vercel.app --token "$DEV_PERF_TOKEN" \
        --bypass "$VERCEL_BYPASS" --label preview-before

Writes .measure/perf/<label>.json (gitignored) and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = [("dashboard", ""), ("records", "records"), ("quality", "quality"), ("activity", "activity"),
         ("outline", "outline"), ("resources", "resources"), ("teaching", "teaching")]
OBSERVE = """
window.__perf = {lcp: 0, cls: 0};
try {
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__perf.lcp = Math.max(window.__perf.lcp, e.startTime); })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__perf.cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""
READY = """() => { const v = document.getElementById('view'); if (!v) return false;
  return !v.querySelector('.skeleton') && v.textContent.trim().length > 40 && !document.querySelector('.error-box'); }"""


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email"); ap.add_argument("--password"); ap.add_argument("--token"); ap.add_argument("--bypass")
    ap.add_argument("--label", default="run"); ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--skip-graph", action="store_true"); ap.add_argument("--skip-map", action="store_true")
    a = ap.parse_args()
    out = {"base": a.base, "label": a.label, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "views": {}, "api": [], "nav": {}}
    api = out["api"]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1536, "height": 900},
                            extra_http_headers={"x-vercel-protection-bypass": a.bypass} if a.bypass else None)
        ctx.add_init_script(OBSERVE)
        if a.token:
            sess = json.dumps({"access_token": a.token, "expires_at": int(time.time()) + 3600, "user": {"email": "perf"}})
            ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:120]))

        def on_done(r):
            if "/api/" not in r.url:
                return
            try:
                t = r.timing
                body = r.response().body() if r.response() else b""
                api.append({"path": r.url.split("/api/")[1].split("?")[0][:40], "ms": round(t["responseEnd"] - t["requestStart"], 1),
                            "bytes": len(body), "status": r.response().status if r.response() else 0, "view": out.get("_view")})
            except Exception:
                pass
        pg.on("requestfinished", on_done)
        if not a.token:
            pg.goto(a.base + "/local-login")
            pg.fill("#email", a.email); pg.fill("#password", a.password); pg.click("#submit")
            pg.wait_for_url("**/kb/**", timeout=60000)
        pg.goto(a.base + "/kb/"); pg.wait_for_function(READY, timeout=60000)

        # page loads: each view opened as a fresh page load, cold (first) and warm (repeats)
        for name, path in VIEWS:
            runs = []
            for i in range(a.repeat):
                out["_view"] = name
                t0 = time.monotonic()
                pg.goto(a.base + "/kb/#/" + path)
                pg.reload()
                try:
                    pg.wait_for_function(READY, timeout=60000)
                    ms = round((time.monotonic() - t0) * 1000)
                except Exception:
                    ms = None
                perf = pg.evaluate("() => window.__perf || {}")
                runs.append({"ms": ms, "lcp": round(perf.get("lcp", 0)), "cls": round(perf.get("cls", 0), 3)})
            out["views"][name] = runs
        # navigation between views (sidebar clicks, app already loaded)
        pg.goto(a.base + "/kb/"); pg.wait_for_function(READY, timeout=60000)
        for name, path in VIEWS[1:] + VIEWS[:1]:
            out["_view"] = "nav:" + name
            t0 = time.monotonic()
            pg.click(f"[data-nav='{path or 'dashboard'}']")
            try:
                pg.wait_for_function(READY, timeout=60000)
                out["nav"][name] = round((time.monotonic() - t0) * 1000)
            except Exception:
                out["nav"][name] = None
        # palette search: Ctrl+K, type, time to results
        out["_view"] = "search"
        lat = []
        for q in ("system design", "kafka", "interview", "graph", "python"):
            pg.keyboard.press("Control+k"); pg.wait_for_selector("[data-testid=palette-input]")
            t0 = time.monotonic()
            pg.fill("[data-testid=palette-input]", q)
            try:
                pg.wait_for_function("() => document.querySelectorAll('[data-testid=palette-node]').length > 0", timeout=15000)
                lat.append(round((time.monotonic() - t0) * 1000))
            except Exception:
                lat.append(None)
            pg.keyboard.press("Escape")
        out["search_ms"] = lat
        # the Graph: load, then group by type
        if not a.skip_graph:
            out["_view"] = "graph"
            t0 = time.monotonic()
            pg.goto(a.base + "/kb/#/graph"); pg.reload()
            pg.wait_for_function("() => !!(window.__kbGraph && window.__kbGraph.cy && window.__kbGraph.loadedAt)", timeout=120000)
            out["graph_load_ms"] = round((time.monotonic() - t0) * 1000)
            out["graph_nodes"] = pg.evaluate("() => window.__kbGraph.cy.nodes().length")
            t0 = time.monotonic()
            pg.select_option("[data-testid=graph-group]", "type", timeout=120000)
            pg.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
            pg.wait_for_timeout(200)
            pg.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
            out["group_by_type_ms"] = round((time.monotonic() - t0) * 1000)
        # the map: time to interactive
        if not a.skip_map and not a.token:
            out["_view"] = "map"
            t0 = time.monotonic()
            pg.goto(a.base + "/"); pg.reload()
            pg.wait_for_function("() => window.__NP && window.__NP_LOADS >= 1 && window.__NP.data && window.__NP.data.nodes.length > 100", timeout=120000)
            out["map_ready_ms"] = round((time.monotonic() - t0) * 1000)
        b.close()
    out.pop("_view", None)
    out["errors"] = errors
    ok = [x["ms"] for x in api if x["status"] < 400]
    out["api_summary"] = {"n": len(api), "p50": pct(ok, 50), "p95": pct(ok, 95), "max": max(ok) if ok else None,
                          "largest": sorted(({"path": x["path"], "kb": round(x["bytes"] / 1024, 1)} for x in api), key=lambda x: -x["kb"])[:5]}
    dest = Path(__file__).resolve().parent.parent / ".measure" / "perf"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{a.label}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"== {a.label} on {a.base}")
    for name, runs in out["views"].items():
        ms = [r["ms"] for r in runs if r["ms"] is not None]
        print(f"  load {name:10} cold {runs[0]['ms']} ms, warm median {statistics.median(ms[1:]) if len(ms) > 1 else '-'} ms, "
              f"LCP {runs[-1]['lcp']} ms, CLS {runs[-1]['cls']}")
    print("  navigation ms:", out["nav"])
    print("  search ms:", out["search_ms"])
    print("  API:", out["api_summary"])
    for k in ("graph_load_ms", "graph_nodes", "group_by_type_ms", "map_ready_ms"):
        if k in out:
            print(f"  {k}: {out[k]}")
    print("  page errors:", len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
