#!/usr/bin/env python3
"""Run 6 (F1): does the dashboard fit in one screen, with no scrolling? Signs in
on a LOCAL server and reports, per viewport, the page's scroll height against
the window, the view's own overflow, and the number of API requests the
dashboard made. Counts only.

  python eval/kb_fit_check.py --base http://localhost:8766 --email realdata-admin@interviewkickstart.com --password ik-realdata-local
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

SIZES = ((1536, 730), (1920, 1080))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--shot", default="")
    a = ap.parse_args()
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for w, h in SIZES:
            ctx = b.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            errs, calls = [], []
            page.on("pageerror", lambda e: errs.append(str(e)[:120]))
            page.on("request", lambda r: calls.append(r.url) if "/api/kb/" in r.url else None)
            page.goto(a.base + "/local-login")
            page.fill("#email", a.email)
            page.fill("#password", a.password)
            page.click("#submit")
            page.wait_for_url("**/kb/**", timeout=60000)
            page.wait_for_selector("[data-testid=dash-grid]", timeout=60000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)
            m = page.evaluate("""() => { const v = document.querySelector('#view'); const d = document.scrollingElement;
                return { winH: innerHeight, docH: d.scrollHeight, viewH: v.clientHeight, viewScroll: v.scrollHeight,
                         gridBottom: Math.round(document.querySelector('[data-testid=dash-grid]').getBoundingClientRect().bottom) }; }""")
            dash = [c for c in calls if "/dashboard" in c or "/counts" in c or "/me" in c or "/types" in c]
            fits = m["docH"] <= m["winH"] and m["viewScroll"] <= m["viewH"] + 1
            ok = ok and fits and not errs
            print(f"{w}x{h}: fits={fits} doc {m['docH']}/{m['winH']} view {m['viewScroll']}/{m['viewH']} grid bottom {m['gridBottom']} "
                  f"api calls {len(calls)} ({len(dash)} dashboard/counts/me/types) errors {len(errs)}")
            if a.shot:
                page.screenshot(path=f"{a.shot}-{w}x{h}.png")
            ctx.close()
        b.close()
    print("FIT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
