#!/usr/bin/env python3
"""Run 6: screenshot every screen and record every browser console error and
warning, on a LOCAL server (the real-data copy or the demo). Used for the
before (A1) and after (B3, Phase C) sets. Prints counts only; real data stays
in the screenshots, which go to the gitignored .measure/screens by default
(local servers only; never commit them).

  python eval/kb_screens.py --base http://localhost:8766 --password ik-realdata-local \
      --email realdata-admin@interviewkickstart.com [--out .measure/screens/realdata] [--width 1536] [--dark]

Writes <out>/<NN>-<screen>.png and <out>/console.json; exit 1 on a page error.
One browser, one page, sequential (the laptop's memory).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

SCREENS = [
    ("dashboard", "#/"), ("records", "#/records"), ("programs", "#/programs"), ("courses", "#/courses"),
    ("resources", "#/resources"), ("outline", "#/outline"), ("graph", "#/graph"), ("teaching", "#/teaching"),
    ("timeline", "#/timeline"), ("activity", "#/activity"), ("quality", "#/quality"), ("approvals", "#/approvals"),
    ("archived", "#/archived"), ("guide", "#/guide"),
    ("settings-types", "#/settings?tab=types"), ("settings-relationships", "#/settings?tab=relationships"),
    ("settings-links", "#/settings?tab=links"), ("settings-tags", "#/settings?tab=tags"),
    ("settings-members", "#/settings?tab=members"), ("settings-tokens", "#/settings?tab=tokens"),
    ("settings-templates", "#/settings?tab=templates"), ("settings-sync", "#/settings?tab=sync"),
    ("settings-people", "#/settings?tab=people"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default=".measure/screens")
    ap.add_argument("--width", type=int, default=1536)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--dark", action="store_true")
    a = ap.parse_args()
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log: dict[str, list] = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": a.width, "height": a.height}, color_scheme="dark" if a.dark else "light")
        page = ctx.new_page()
        current = {"name": "sign-in"}

        def note(kind, text):
            log.setdefault(current["name"], []).append({"kind": kind, "text": text[:300]})
        page.on("console", lambda m: note(m.type, m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: note("pageerror", str(e)))

        page.goto(a.base + "/local-login")
        page.screenshot(path=str(out / "00-sign-in.png"))
        page.fill("#email", a.email)
        page.fill("#password", a.password)
        page.click("#submit")
        page.wait_for_url("**/kb/**", timeout=60000)
        page.wait_for_selector("[data-testid=dash-grid]", timeout=60000)

        for i, (name, route) in enumerate(SCREENS, 1):
            current["name"] = name
            page.goto(a.base + "/kb/" + route)
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:                                          # noqa: BLE001
                note("timeout", "network not idle after 30 s")
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / f"{i:02d}-{name}.png"))

        # A record: the panel, then the full page; and the New record sheet.
        current["name"] = "record-panel"
        page.goto(a.base + "/kb/#/records")
        page.wait_for_selector("[data-testid=result-count]:not(:empty)", timeout=60000)
        first = page.locator("table tbody tr").first
        if first.count():
            first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out / "30-record-panel.png"))
            href = page.evaluate("() => location.hash")
            rid = href.split("open=")[-1].split("&")[0] if "open=" in href else None
            if rid:
                current["name"] = "record-page"
                page.goto(a.base + "/kb/#/r/" + rid)
                page.wait_for_timeout(2000)
                page.screenshot(path=str(out / "31-record-page.png"))
        current["name"] = "new-record"
        page.goto(a.base + "/kb/#/records")
        page.wait_for_timeout(1000)
        page.click("[data-testid=new-record]")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out / "32-new-record.png"))
        page.keyboard.press("Escape")

        # The NP Autopilot map at "/".
        current["name"] = "np-map"
        page.goto(a.base + "/")
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:                                              # noqa: BLE001
            note("timeout", "network not idle after 60 s")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(out / "40-np-map.png"))
        b.close()

    (out / "console.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    errors = sum(1 for v in log.values() for x in v if x["kind"] in ("error", "pageerror"))
    warnings = sum(1 for v in log.values() for x in v if x["kind"] == "warning")
    print(f"screens: {len(SCREENS) + 5}; console errors: {errors}; warnings: {warnings}; "
          f"screens with any: {sorted(k for k, v in log.items() if v)}")
    return 1 if any(x["kind"] == "pageerror" for v in log.values() for x in v) else 0


if __name__ == "__main__":
    sys.exit(main())
