#!/usr/bin/env python3
"""Measure the LIVE explorer while signed in. Read-only against production.

WHY THIS IS INTERACTIVE. Every data endpoint is 401 without a session, so the
numbers that matter — payload per API call, time to a settled layout, p50/p95
on the real query path — cannot be collected unauthenticated. There is no way
to get them without a human signing in once, and no credential is typed to,
stored by, or visible to the agent that wrote this.

THE SESSION IS TREATED AS A SECRET.
  * written only to .measure/ , which is gitignored
  * deleted in a finally: block, so an exception still removes it
  * never printed, never logged, never included in the report

Run:  python3 eval/measure_signed_in.py
      A browser opens. Sign in. The run continues by itself.
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = "https://np-autopilot.vercel.app"
SESSION_DIR = REPO / ".measure"
SESSION = SESSION_DIR / "session.json"

ENDPOINTS = ["/api/overview", "/api/search?q=api", "/api/config"]
SAMPLES = 20


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(q * len(vals)))]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed:  python3 -m pip install playwright"
                 "  &&  python3 -m playwright install chromium")

    SESSION_DIR.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context()
            page = ctx.new_page()

            print(f"\n  Opening {SITE} — sign in, then leave the window alone.")
            page.goto(SITE, wait_until="domcontentloaded")
            print("  Waiting for /api/me to return 200 (up to 5 minutes)...")
            try:
                page.wait_for_function(
                    """() => fetch('/api/me').then(r => r.status === 200)
                             .catch(() => false)""",
                    timeout=300_000)
            except Exception:
                sys.exit("  timed out waiting for sign-in.")
            ctx.storage_state(path=str(SESSION))
            print("  signed in. session stored to a gitignored path.\n")

            # ---- cold load, signed in -----------------------------------
            ctx2 = browser.new_context(storage_state=str(SESSION))
            page2 = ctx2.new_page()
            sizes: dict[str, int] = {}
            page2.on("response", lambda r: sizes.__setitem__(
                r.url.replace(SITE, ""),
                len(r.body()) if r.request.resource_type != "image" else 0)
                if "/api/" in r.url or r.url.endswith((".json", "/")) else None)

            t0 = time.time()
            page2.goto(SITE, wait_until="domcontentloaded")
            dom = time.time() - t0
            page2.wait_for_load_state("networkidle")
            settled = time.time() - t0

            nav = page2.evaluate("""() => {
                const n = performance.getEntriesByType('navigation')[0] || {};
                const paint = performance.getEntriesByType('paint');
                return {ttfb: n.responseStart, domContentLoaded: n.domContentLoadedEventEnd,
                        load: n.loadEventEnd,
                        fp: (paint.find(x=>x.name==='first-paint')||{}).startTime ?? null,
                        fcp: (paint.find(x=>x.name==='first-contentful-paint')||{}).startTime ?? null,
                        transfer: n.transferSize, decoded: n.decodedBodySize};
            }""")

            print("  COLD LOAD, SIGNED IN")
            print(f"    TTFB                    {nav['ttfb']:8.0f} ms")
            print(f"    first contentful paint  {(nav['fcp'] or 0):8.0f} ms")
            print(f"    DOMContentLoaded        {nav['domContentLoaded']:8.0f} ms")
            print(f"    load event              {nav['load']:8.0f} ms")
            print(f"    settled (networkidle)   {settled*1000:8.0f} ms")
            print(f"    document transfer       {nav['transfer']:8} bytes"
                  f"  ({nav['decoded']} decoded)")

            print("\n  PAYLOAD PER CALL")
            for u, n in sorted(sizes.items(), key=lambda kv: -(kv[1] or 0))[:12]:
                if n:
                    print(f"    {u[:52]:52} {n:8} bytes")

            # ---- p50/p95 on the real query path -------------------------
            print(f"\n  LATENCY, SIGNED IN ({SAMPLES} samples)")
            print(f"    {'endpoint':26} {'p50':>8} {'p95':>8} {'bytes':>8}")
            for ep in ENDPOINTS:
                times, nbytes = [], 0
                for _ in range(SAMPLES):
                    r = page2.evaluate("""async (ep) => {
                        const t = performance.now();
                        const res = await fetch(ep);
                        const body = await res.text();
                        return [performance.now() - t, body.length, res.status];
                    }""", ep)
                    times.append(r[0]); nbytes = r[1]
                print(f"    {ep:26} {pct(times,.5):7.0f}ms {pct(times,.95):7.0f}ms"
                      f" {nbytes:8}")

            # one node detail, using an id the overview actually returned
            nid = page2.evaluate("""async () => {
                const r = await fetch('/api/overview'); const j = await r.json();
                const n = (j.nodes || j.graph?.nodes || [])[0];
                return n && (n.id || n.i) || null;
            }""")
            if nid:
                times = []
                for _ in range(SAMPLES):
                    times.append(page2.evaluate("""async (id) => {
                        const t = performance.now();
                        await (await fetch('/api/node?id=' + encodeURIComponent(id))).text();
                        return performance.now() - t;
                    }""", nid))
                print(f"    {'/api/node':26} {pct(times,.5):7.0f}ms "
                      f"{pct(times,.95):7.0f}ms")
            else:
                print("    /api/node                  (no id returned by overview)")

            browser.close()
    finally:
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
        print("\n  session deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
