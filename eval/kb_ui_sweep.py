#!/usr/bin/env python3
"""Run 6 (B3): sweep every KB screen at several widths and both themes and
report layout and accessibility problems that a screenshot can hide:

  - horizontal scroll (the document or the page container wider than the view)
  - text cut off ("…" or a line clamp) with no tooltip carrying the full text
  - controls with no accessible name
  - console errors and page errors

LOCAL servers only. Prints counts and selectors, never record content, so it is
safe on the real-data copy. One browser, one page, sequential (memory).

  python eval/kb_ui_sweep.py --base http://localhost:8773 --email ... --password ... \
      [--widths 1024,1280,1536,1920,2560] [--themes light,dark] [--shots DIR] [--only records,quality]
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

CHECKS = r"""() => {
  const out = {hscroll: false, truncated: [], unnamed: []};
  const view = document.getElementById('view');
  const de = document.documentElement;
  out.hscroll = de.scrollWidth > window.innerWidth + 1 || (view && view.scrollWidth > view.clientWidth + 1);
  const sel = (e) => e.tagName.toLowerCase() + (e.getAttribute('data-testid') ? '[' + e.getAttribute('data-testid') + ']' : '')
    + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).join('.') : '');
  const visible = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight; };
  for (const e of document.querySelectorAll('body *')) {
    if (!visible(e) || !e.textContent.trim()) continue;
    const cs = getComputedStyle(e);
    const ell = cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1;
    const clamp = cs.webkitLineClamp && cs.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1;
    if ((ell || clamp) && !e.closest('[title]')) out.truncated.push(sel(e));
  }
  const name = (e) => (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.getAttribute('title') || e.textContent || e.value || '').trim()
    || (e.id && document.querySelector('label[for="' + e.id + '"]') ? 'label' : '') || (e.closest('label') ? 'label' : '')
    || (e.getAttribute('placeholder') || '').trim();
  document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=tab], [tabindex]:not([tabindex="-1"])').forEach((e) => {
    if (!visible(e)) return;
    if (!name(e)) out.unnamed.push(sel(e));
  });
  out.truncated = [...new Set(out.truncated)].slice(0, 12);
  out.unnamed = [...new Set(out.unnamed)].slice(0, 12);
  return out;
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--widths", default="1024,1280,1536,1920,2560")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--shots", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--layers", action="store_true", help="also open the read-only panels, sheets, dialogs and menus")
    a = ap.parse_args()
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    only = set(filter(None, a.only.split(",")))
    screens = [s for s in SCREENS if not only or s[0] in only]
    report: dict = {}
    problems = 0
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for theme in a.themes.split(","):
            ctx = b.new_context(viewport={"width": 1536, "height": a.height}, color_scheme=theme)
            page = ctx.new_page()
            current = {"k": "sign-in"}
            page.on("console", lambda m: m.type == "error" and report.setdefault(current["k"], {}).setdefault("console", []).append(m.text[:200]))
            page.on("pageerror", lambda e: report.setdefault(current["k"], {}).setdefault("console", []).append("pageerror: " + str(e)[:200]))
            page.goto(a.base + "/local-login")
            page.fill("#email", a.email)
            page.fill("#password", a.password)
            page.click("#submit")
            page.wait_for_url("**/kb/**", timeout=60000)
            page.wait_for_selector("[data-testid=dash-grid]", timeout=60000)
            for w in [int(x) for x in a.widths.split(",")]:
                page.set_viewport_size({"width": w, "height": a.height})
                def settle():
                    try:
                        page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:                                  # noqa: BLE001
                        pass
                    try:   # wait for the content, not the skeleton (real data can be slow)
                        page.wait_for_function("() => !document.querySelector('#view [aria-busy=true], #panel [aria-busy=true]')", timeout=45000)
                    except Exception:                                  # noqa: BLE001
                        report.setdefault(current["k"], {})["slow"] = "still loading after 45 s"
                    page.wait_for_timeout(700)

                def check(name):
                    res = page.evaluate(CHECKS)
                    entry = report.setdefault(current["k"], {})
                    for k in ("hscroll", "truncated", "unnamed"):
                        if res[k]:
                            entry[k] = res[k]
                    if a.shots:
                        d = Path(a.shots) / f"{theme}-{w}"
                        d.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(d / f"{name}.png"))

                for name, route in screens:
                    current["k"] = f"{theme}/{w}/{name}"
                    page.goto(a.base + "/kb/" + route)
                    settle()
                    check(name)
                if not a.layers:
                    continue
                # Read-only layers: the record panel and page, the New record sheet,
                # the palette, menus, the type editor and a relationship type dialog.
                # Each is opened and closed with Escape; nothing is saved.
                page.goto(a.base + "/kb/#/records")
                settle()
                rid = page.evaluate("() => { const r = document.querySelector('tr[data-id]'); return r && r.dataset.id; }")
                layers = []
                if rid:
                    layers += [("record-panel", "#/records?open=" + rid, None), ("record-page", "#/r/" + rid, None),
                               ("record-more-menu", "#/records?open=" + rid, "[data-testid=more-actions]"),
                               ("record-tab-links", "#/records?open=" + rid, "[data-testid=tab-links]"),
                               ("record-tab-relationships", "#/records?open=" + rid, "[data-testid=tab-relationships]"),
                               ("record-tab-history", "#/records?open=" + rid, "[data-testid=tab-history]")]
                layers += [("new-record", "#/records", "[data-testid=new-record]"), ("palette", "#/", "[data-testid=open-palette]"),
                           ("user-menu", "#/", "[data-testid=whoami]"), ("records-view-popover", "#/records", "[data-testid=view-options]"),
                           ("type-editor", "#/settings?tab=types", "[data-testid=edit-type-module]"),
                           ("edge-type-dialog", "#/settings?tab=relationships", "[data-testid=new-edge-type]")]
                for name, route, click in layers:
                    current["k"] = f"{theme}/{w}/{name}"
                    page.goto(a.base + "/kb/" + route)
                    settle()
                    if click:
                        loc = page.locator(click).first
                        if not loc.count():
                            report.setdefault(current["k"], {})["missing"] = click
                            continue
                        loc.click()
                        page.wait_for_timeout(900)
                    check(name)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
            ctx.close()
        b.close()
    report = {k: v for k, v in report.items() if v}
    for k, v in sorted(report.items()):
        problems += 1
        print(k, json.dumps(v)[:600])
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"screens with a problem: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
