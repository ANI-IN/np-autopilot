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

import argparse
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

#: Timed and STRICTLY validated in both phases. These exist in production
#: today, so a 401 or a too-small body is a broken measurement either way.
BASE_ENDPOINTS = ["/api/overview", "/api/search?q=api", "/api/config"]

#: Added by B3. Absent from production until the deploy, so `--phase pre` only
#: PROBES it and reports what it found; `--phase post` times it and requires it.
NEW_ENDPOINTS = ["/api/structure"]

#: Endpoints whose small body is CORRECT. /api/config is four settings; the
#: size floor would flag it forever. Everything else returning under ~200
#: bytes is an error body, not data.
SMALL_BY_DESIGN = {"/api/config"}
SAMPLES = 20

#: Cold loads per run. One sample is noise: two runs against an unchanged
#: production site reported TTFB 207 ms and 1,230 ms.
COLD_LOADS = 5


def invalid_measurements(results: dict, node_id, phase: str) -> list:
    """Why a latency table is not a measurement. Empty means it is.

    THE CHECK THAT WAS MISSING. The first run reported a clean-looking table —
    /api/overview p50 219 ms — built entirely from 401 responses, because the
    timed requests carried no Authorization header. Every body was 54 bytes,
    the size of `{"error":"unauthorised",...}`, and nothing said so.

    PHASE IS PASSED IN, NEVER INFERRED. Deciding "this looks like a pre-deploy
    run because /api/structure 404s" would make the script relax its own
    checks whenever the endpoint broke — a guard that switches itself off
    exactly when the thing it guards has failed. The caller states which run
    this is.
    """
    if phase not in ("pre", "post"):
        raise ValueError(f"phase must be 'pre' or 'post', not {phase!r}")
    bad = []
    for ep, r in results.items():
        if phase == "pre" and ep.split("?")[0] in NEW_ENDPOINTS:
            continue                      # probed and reported, not required
        if r.get("status") != 200:
            bad.append(f"{ep}: HTTP {r.get('status')}")
        elif ep.split("?")[0] not in SMALL_BY_DESIGN and r.get("bytes", 0) < 200:
            bad.append(f"{ep}: {r.get('bytes')} bytes — too small to be data")
    if phase == "post":
        for ep in NEW_ENDPOINTS:
            if ep not in results:
                bad.append(f"{ep}: not measured, and required after deploy")
    if node_id is None:
        bad.append("/api/node: no node id could be fetched to time it")
    return bad


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(q * len(vals)))]


def _args(argv):
    """`--phase` is REQUIRED. There is no default and no inference.

    A default would be a guess about which side of the deploy this is, and the
    wrong guess in the safe-looking direction — `pre` — silently drops the
    strictness the owner asked to keep.
    """
    ap = argparse.ArgumentParser(
        description="Measure the live explorer while signed in.")
    ap.add_argument("--phase", required=True, choices=("pre", "post"),
                    help="pre: before the B3 deploy. /api/structure is probed "
                         "and reported, never required; every other endpoint "
                         "stays strict. post: after the deploy. /api/structure "
                         "is timed and REQUIRED.")
    ap.add_argument("--wait-for-enter", action="store_true",
                    help="pause after opening the page and wait for Enter, "
                         "for when signing in takes a while")
    ap.add_argument("--headless", action="store_true",
                    help="no visible browser; only useful when already "
                         "signed in or for a signed-out smoke test")
    ap.add_argument("outdir", nargs="?", default=None,
                    help="unused; kept so an old invocation does not silently "
                         "become a phase")
    return ap.parse_args(argv)


def _nav_timings(page):
    return page.evaluate("""() => {
        const n = performance.getEntriesByType('navigation')[0] || {};
        const paint = performance.getEntriesByType('paint');
        return {ttfb: n.responseStart, dcl: n.domContentLoadedEventEnd,
                load: n.loadEventEnd,
                fcp: (paint.find(x=>x.name==='first-contentful-paint')||{}).startTime ?? null,
                transfer: n.transferSize, decoded: n.decodedBodySize};
    }""")


def _stat(vals):
    """(median, min, max) — a single sample is not a measurement.

    Two runs against an unchanged production site reported TTFB 207 ms and
    1,230 ms. One of those numbers was going to become "the baseline" and the
    other would have looked like a regression or a win depending on which got
    written down first.
    """
    v = sorted(x for x in vals if x is not None)
    if not v:
        return (None, None, None)
    return (statistics.median(v), v[0], v[-1])


def _fmt(triple, unit="ms"):
    med, lo, hi = triple
    if med is None:
        return "—"
    return f"{med:.0f}{unit}  ({lo:.0f}–{hi:.0f})"


#: How the page ACTUALLY holds its session. `let SESSION = null` at the top
#: level of a classic script lives in the global LEXICAL environment, not on
#: `window` — so `window.SESSION` is undefined while the bare name resolves.
#: The first token check asked for `window.SESSION`, found nothing, and
#: reported "no access token in the page" on a page that was correctly signed
#: in. The app itself reads the bare name; so does this.
_HAS_TOKEN = """() => {
    try { return !!(SESSION && SESSION.access_token); }
    catch (e) { return false; }
}"""


def main(argv=None) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed:  python3 -m pip install playwright"
                 "  &&  python3 -m playwright install chromium")

    args = _args(argv)
    phase = args.phase
    endpoints = (BASE_ENDPOINTS if phase == "pre"
                 else NEW_ENDPOINTS + BASE_ENDPOINTS)
    print(f"\n  PHASE: {phase}-deploy"
          + ("  (/api/structure probed, not required)" if phase == "pre"
             else "  (/api/structure required)"))
    SESSION_DIR.mkdir(exist_ok=True)
    local = "127.0.0.1" in SITE or "localhost" in SITE
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless or local)
            ctx = browser.new_context()
            page = ctx.new_page()

            print(f"\n  Opening {SITE}" +
                  ("  (local smoke test)" if local
                   else " — sign in if prompted."))
            page.goto(SITE, wait_until="domcontentloaded")

            if args.wait_for_enter:
                input("\n  Sign in, then press Enter here to start measuring... ")

            if not local:
                print("  Waiting for the app to finish signing in...")
            try:
                page.wait_for_function(_HAS_TOKEN, timeout=300_000)
            except Exception:
                sys.exit(
                    "  timed out waiting for a session. The app never stored "
                    "an access token.\n"
                    "  Re-run with --wait-for-enter if you need longer to "
                    "sign in.")
            ctx.storage_state(path=str(SESSION))
            print("  signed in.\n")

            # ---- COLD LOADS: five, reported as median and range ----------
            # A single cold sample is noise. Each one gets a FRESH CONTEXT so
            # it is genuinely cold rather than warmed by the previous load.
            print(f"  COLD LOAD, SIGNED IN ({COLD_LOADS} loads)")
            ttfb, fcp, dcl, load, settled, transfer, decoded = ([] for _ in range(7))
            sizes: dict[str, int] = {}
            page2 = None
            for i in range(COLD_LOADS):
                c = browser.new_context(storage_state=str(SESSION))
                pg = c.new_page()
                # GUARDED. `r.body()` is a round trip to the browser, and a
                # response can still be in flight when the context closes —
                # which raises TargetClosedError from inside an asyncio
                # callback, long after the numbers were collected and printed.
                # A missing size is not a failed measurement; a stack trace
                # under a valid table is just noise that makes it look failed.
                def _record(r, _sizes=sizes):
                    try:
                        if not ("/api/" in r.url
                                or r.url.endswith((".json", "/"))):
                            return
                        if r.request.resource_type == "image":
                            return
                        _sizes[r.url.replace(SITE, "")] = len(r.body())
                    except Exception:
                        pass
                pg.on("response", _record)
                t0 = time.time()
                pg.goto(SITE, wait_until="domcontentloaded")
                pg.wait_for_load_state("networkidle")
                settled.append((time.time() - t0) * 1000)
                nav = _nav_timings(pg)
                ttfb.append(nav["ttfb"]); fcp.append(nav["fcp"])
                dcl.append(nav["dcl"]); load.append(nav["load"])
                transfer.append(nav["transfer"]); decoded.append(nav["decoded"])
                if i == COLD_LOADS - 1:
                    page2 = pg                       # keep the last one warm
                else:
                    c.close()

            print(f"    {'TTFB':24} {_fmt(_stat(ttfb))}")
            print(f"    {'first contentful paint':24} {_fmt(_stat(fcp))}")
            print(f"    {'DOMContentLoaded':24} {_fmt(_stat(dcl))}")
            print(f"    {'load event':24} {_fmt(_stat(load))}")
            print(f"    {'settled (networkidle)':24} {_fmt(_stat(settled))}")
            print(f"    {'document transfer':24} "
                  f"{_fmt(_stat(transfer), ' bytes')} "
                  f"({_stat(decoded)[0]:.0f} decoded)")

            print("\n  PAYLOAD PER CALL")
            for u, n in sorted(sizes.items(), key=lambda kv: -(kv[1] or 0))[:12]:
                if n:
                    print(f"    {u[:52]:52} {n:8} bytes")

            # ---- WAIT FOR THE APP'S OWN AUTHENTICATED REQUEST ------------
            # Not just for a token to exist: for the app to have USED it. The
            # previous failure was a scope bug, but a race is the other way
            # this goes wrong, and waiting on the app's own first data call
            # covers both without guessing a delay.
            try:
                page2.wait_for_function(
                    """() => (performance.getEntriesByType('resource') || [])
                             .some(r => /\\/api\\/(overview|structure|coverage)/
                                        .test(r.name))""",
                    timeout=60_000)
            except Exception:
                print("  (the app made no data request of its own; continuing)")
            if not page2.evaluate(_HAS_TOKEN):
                raise SystemExit(
                    "  no access token in the page after load. The app keeps "
                    "its session in the global lexical scope as `SESSION`; if "
                    "that changed, this script must change with it.")

            # ---- p50/p95 on the real query path -------------------------
            print(f"\n  LATENCY, SIGNED IN ({SAMPLES} samples)")
            node_id = page2.evaluate("""async () => {
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

            eps = list(endpoints)
            if node_id:
                eps.append("/api/node?id=" + node_id)

            results = page2.evaluate("""async ([eps, n]) => {
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

            if phase == "pre":
                for ep in NEW_ENDPOINTS:
                    st = page2.evaluate("""async (ep) => {
                        const h = {authorization: 'Bearer ' + SESSION.access_token};
                        try { const r = await fetch(ep, {headers: h});
                              return r.status; }
                        catch (e) { return 0; }
                    }""", ep)
                    note = ("not served (new endpoint)" if st in (404, 0)
                            else f"ALREADY SERVED (HTTP {st}) — is this really "
                                 f"a pre-deploy run?")
                    print(f"    {ep[:26]:26} {'—':>8} {'—':>8} {'—':>9} "
                          f"{st:7}   {note}")

            bad = invalid_measurements(results, node_id, phase)
            if bad:
                print("\n  MEASUREMENT INVALID:")
                for b in bad:
                    print(f"    {b}")
                raise SystemExit(
                    "  the timed requests did not return data. A latency table "
                    "built from 401s is worse than no table.")
            # Detach first: a listener firing during teardown is the whole
            # reason the last run printed two tracebacks under a good table.
            try:
                page2.remove_listener("response", _record)
            except Exception:
                pass
            browser.close()
    finally:
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
        print("\n  session deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
