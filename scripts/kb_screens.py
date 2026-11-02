"""Screenshot every KB screen at several widths and pixel densities, and report
layout problems found in the DOM (run 3, B1 and the A sweep). LOCAL ONLY:
drives the running demo server (eval/kb_demo_server.py) with system Chrome.

    python scripts/kb_screens.py                       # 1536 @1x, report only
    python scripts/kb_screens.py --widths 1280,1536,1920,2560,3840 --dpr 1,2 --out docs/redesign/run3

Each problem line names the screen, the width and the element: horizontal page
scroll, elements running past the viewport's right edge, text clipped without
a tooltip, and controls overlapping each other.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
SCREENS = [("dashboard", "#/"), ("records", "#/records"), ("courses", "#/courses"), ("record-panel", "#/records?open={course}"),
           ("record-page", "#/r/{course}"), ("outline", "#/outline"), ("graph", "#/graph/{course}"), ("resources", "#/resources"),
           ("quality", "#/quality"), ("approvals", "#/approvals"), ("activity", "#/activity"), ("archived", "#/archived"),
           ("settings", "#/settings"), ("settings-relationships", "#/settings?tab=relationships"), ("guide", "#/guide")]

PROBE = """() => {
  const out = [], vw = document.documentElement.clientWidth;
  const doc = document.scrollingElement;
  if (doc.scrollWidth > doc.clientWidth + 1) out.push('page scrolls horizontally: ' + doc.scrollWidth + ' > ' + doc.clientWidth);
  const view = document.querySelector('#view');
  if (view && view.scrollWidth > view.clientWidth + 1) out.push('#view scrolls horizontally: ' + view.scrollWidth + ' > ' + view.clientWidth);
  const name = (e) => (e.getAttribute('data-testid') || e.className || e.tagName).toString().slice(0, 40) + ' "' + (e.textContent || '').trim().slice(0, 30) + '"';
  for (const e of document.querySelectorAll('#app *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.opacity === '0') continue;
    if (r.right > vw + 1 && cs.position !== 'fixed' && !e.closest('.table-wrap, .tabs, #cy, .graph-canvas')) out.push('past right edge: ' + name(e));
    if (cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1 && !e.closest('[title]') && !e.title) out.push('clipped, no tooltip: ' + name(e));
  }
  const ctl = Array.from(document.querySelectorAll('#app button, #app a.btn, #app input, #app select')).filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.height && getComputedStyle(e).visibility !== 'hidden'; });
  for (let i = 0; i < ctl.length; i++) for (let j = i + 1; j < ctl.length; j++) {
    const a = ctl[i].getBoundingClientRect(), b = ctl[j].getBoundingClientRect();
    if (ctl[i].contains(ctl[j]) || ctl[j].contains(ctl[i])) continue;
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left), oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 4 && oy > 4) out.push('controls overlap: ' + name(ctl[i]) + ' / ' + name(ctl[j]));
  }
  return Array.from(new Set(out)).slice(0, 20);
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--widths", default="1536")
    ap.add_argument("--dpr", default="1")
    ap.add_argument("--height", type=int, default=0, help="viewport height (default: width * 9/16, min 800)")
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="comma-separated screen names")
    ap.add_argument("--email", default="demo-admin@interviewkickstart.com")
    ap.add_argument("--jpeg", action="store_true", help="save JPEG (quality 82) instead of PNG: large widths stay small")
    a = ap.parse_args()
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    problems = 0
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for dpr in [float(x) for x in a.dpr.split(",")]:
            for w in [int(x) for x in a.widths.split(",")]:
                h = a.height or max(800, w * 9 // 16)
                ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr)
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(BASE + "/local-login")
                page.fill("#email", a.email)
                page.fill("#password", "ik-demo-local")
                page.click("#submit")
                page.wait_for_url("**/kb/**")
                page.goto(BASE + "/kb/#/")
                page.wait_for_selector("[data-testid=dashboard] .grid-12")
                course = page.evaluate("""async () => { const s = JSON.parse(localStorage.getItem('np_session'));
                    const r = await fetch('/api/kb/nodes?type=course&limit=1&sort=name', { headers: { authorization: 'Bearer ' + s.access_token } });
                    return (await r.json()).items[0].id; }""")
                for name, route in SCREENS:
                    if only and name not in only:
                        continue
                    page.goto(BASE + "/kb/" + route.format(course=course))
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(700 if name.startswith("graph") else 300)
                    found = page.evaluate(PROBE) + [f"script error: {e}" for e in errors]
                    errors.clear()
                    for f in found:
                        print(f"{name} @ {w}x{dpr:g}: {f}")
                    problems += len(found)
                    if out:
                        ext = "jpg" if a.jpeg else "png"
                        page.screenshot(path=str(out / f"{w}{'@2x' if dpr == 2 else ''}-{name}.{ext}"), **({"quality": 82} if a.jpeg else {}))
                ctx.close()
        b.close()
    print(f"{problems} layout problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
