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
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: Overridable so the in-page timing loop can be smoke-tested against the
#: local harness before spending a real sign-in. It does NOT prove the
#: Authorization header is required — the local server stubs identify() — but
#: it does prove `SESSION.access_token` resolves and the loop returns bodies,
#: which is the mistake that wasted the first baseline.
SITE = os.environ.get("NP_MEASURE_BASE", "https://np-autopilot.vercel.app")
SESSION_DIR = REPO / ".measure"
SESSION = SESSION_DIR / "session.json"

ENDPOINTS = ["/api/structure", "/api/overview", "/api/search?q=api",
             "/api/config"]

#: Endpoints whose small body is CORRECT. /api/config is four settings; the
#: size floor below would flag it forever. Everything else returning under
#: ~200 bytes is an error body, not data.
SMALL_BY_DESIGN = {"/api/config"}
SAMPLES = 20


def invalid_measurements(results: dict, node_id) -> list:
    """Why a latency table is not a measurement. Empty means it is.

    THE CHECK THAT WAS MISSING. The first run reported a clean-looking table —
    /api/overview p50 219 ms — built entirely from 401 responses, because the
    timed requests carried no Authorization header. Every body was 54 bytes,
    the size of `{"error":"unauthorised",...}`, and nothing said so.
    """
    bad = []
    for ep, r in results.items():
        if r.get("status") != 200:
            bad.append(f"{ep}: HTTP {r.get('status')}")
        elif ep.split("?")[0] not in SMALL_BY_DESIGN and r.get("bytes", 0) < 200:
            bad.append(f"{ep}: {r.get('bytes')} bytes — too small to be data")
    if node_id is None:
        bad.append("/api/node: no node id could be fetched to time it")
    return bad


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
            browser = p.chromium.launch(
            headless=bool(os.environ.get('NP_MEASURE_BASE')))
            ctx = browser.new_context()
            page = ctx.new_page()

            local = "127.0.0.1" in SITE or "localhost" in SITE
            print(f"\n  Opening {SITE}" +
                  ("  (local smoke test — no sign-in needed)" if local
                   else " — sign in, then leave the window alone."))
            page.goto(SITE, wait_until="domcontentloaded")
            if not local:
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
            # AUTHENTICATED, WHICH THE FIRST VERSION WAS NOT. It issued a bare
            # `fetch(ep)` from page.evaluate. This app keeps the Supabase access
            # token in PAGE MEMORY and sends it as an Authorization header —
            # it is not a cookie — so a bare fetch carried no credential and
            # every timed request was a 401. The table looked plausible
            # (219 ms p50) and was measuring the auth rejection path.
            #
            # The token is read INSIDE the page and never crosses into this
            # process: the whole timing loop runs in one page.evaluate, so
            # nothing here can print or store it.
            print(f"\n  LATENCY, SIGNED IN ({SAMPLES} samples)")

            # THE TOKEN MUST EXIST BEFORE ANYTHING IS TIMED. Without this the
            # loop throws `Cannot read properties of null` deep inside
            # page.evaluate, which reads as a harness bug rather than as "this
            # page is not actually authenticated". Found by smoke-testing
            # against the local server, where SESSION is genuinely null because
            # that server stubs identity and never needs a token.
            has_token = page.evaluate(
                "() => !!(window.SESSION && SESSION.access_token)")
            if not has_token:
                raise SystemExit(
                    "  no access token in the page. The measurement cannot run "
                    "authenticated, and an unauthenticated table is what "
                    "invalidated the first baseline.\n"
                    "  If you signed in and still see this, the app changed "
                    "where it keeps the session.")

            node_id = page.evaluate("""async () => {
                const h = {authorization: 'Bearer ' + SESSION.access_token};
                for (const ep of ['/api/structure', '/api/overview']) {
                    try {
                        const r = await fetch(ep, {headers: h});
                        if (!r.ok) continue;
                        const j = await r.json();
                        const ns = j.nodes || (j.graph && j.graph.nodes) || [];
                        if (ns.length) return ns[0].id || ns[0].i || null;
                    } catch (e) { /* endpoint may not exist yet */ }
                }
                return null;
            }""")

            eps = list(ENDPOINTS)
            if node_id:
                eps.append("/api/node?id=" + node_id)

            results = page.evaluate("""async ([eps, n]) => {
                const h = {authorization: 'Bearer ' + SESSION.access_token};
                const out = {};
                for (const ep of eps) {
                    const times = [];
                    let bytes = 0, status = 0;
                    for (let i = 0; i < n; i++) {
                        const t = performance.now();
                        const res = await fetch(ep, {headers: h});
                        const body = await res.text();
                        times.push(performance.now() - t);
                        bytes = body.length; status = res.status;
                    }
                    out[ep] = {times, bytes, status};
                }
                return out;
            }""", [eps, SAMPLES])

            print(f"    {'endpoint':26} {'p50':>8} {'p95':>8} {'bytes':>9} "
                  f"{'status':>7}")
            for ep, r in results.items():
                print(f"    {ep[:26]:26} {pct(r['times'],.5):7.0f}ms "
                      f"{pct(r['times'],.95):7.0f}ms {r['bytes']:9} "
                      f"{r['status']:7}")
            bad = invalid_measurements(results, node_id)
            if bad:
                print("\n  MEASUREMENT INVALID:")
                for b in bad:
                    print(f"    {b}")
                raise SystemExit(
                    "  the timed requests did not return data. A latency table "
                    "built from 401s is worse than no table.")

            browser.close()
    finally:
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
        print("\n  session deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
