"""Retake the Guide's screenshots (public/kb/guide/*.png) from the running local
demo (eval/kb_demo_server.py + eval/kb_demo_seed.py), each CROPPED to the part
of the screen the Guide is talking about (run 3, A6). LOCAL ONLY.

    python scripts/kb_guide_shots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
OUT = Path(__file__).resolve().parent.parent / "public" / "kb" / "guide"


def shot(page, name, locator=None, clip=None, pad=12):
    if locator is not None:
        b = locator.bounding_box()
        clip = {"x": max(0, b["x"] - pad), "y": max(0, b["y"] - pad), "width": b["width"] + 2 * pad, "height": b["height"] + 2 * pad}
    page.screenshot(path=str(OUT / f"{name}.png"), clip=clip)
    print("wrote", name)


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(BASE + "/local-login")
        page.fill("#email", "demo-admin@interviewkickstart.com")
        page.fill("#password", "ik-demo-local")
        page.click("#submit")
        page.wait_for_url("**/kb/**")
        page.wait_for_selector("[data-testid=dashboard] .grid-12")
        ids = page.evaluate("""async () => { const s = JSON.parse(localStorage.getItem('np_session'));
            const get = async (q) => (await (await fetch('/api/kb/nodes?' + q, { headers: { authorization: 'Bearer ' + s.access_token } })).json()).items;
            return { course: (await get('type=course&limit=1&sort=name'))[0].id, module: (await get('type=module&limit=1&sort=name'))[0].id }; }""")
        # record: the detail panel only
        page.goto(BASE + f"/kb/#/records?open={ids['module']}")
        page.wait_for_selector("[data-testid=panel-name]")
        page.wait_for_timeout(500)
        shot(page, "record", page.locator("#panel"), pad=0)
        # outline: the tree, expanded
        page.goto(BASE + "/kb/#/outline")
        page.get_by_test_id("outline-expand").click()
        page.wait_for_timeout(400)
        tree = page.locator(".tree").first
        bb = tree.bounding_box()
        shot(page, "outline", clip={"x": bb["x"] - 12, "y": bb["y"] - 12, "width": min(bb["width"], 900) + 24, "height": min(bb["height"], 520) + 24})
        # new record: the sheet with an inline new course under Placement
        page.goto(BASE + "/kb/#/records")
        page.get_by_test_id("new-record").click()
        page.get_by_test_id("create-type").fill("Module")
        page.get_by_test_id("create-type-option").filter(has=page.get_by_text("Module", exact=True)).first.click()
        page.get_by_test_id("create-name").fill("Rate limiting")
        page.get_by_test_id("placement-picker").fill("System Design III")
        page.get_by_test_id("placement-picker-create").filter(has_text="course").click()
        page.wait_for_timeout(300)
        shot(page, "new-record", page.get_by_test_id("record-sheet"), pad=0)
        # relationship: the sentence picker, open, grouped by direction
        page.get_by_test_id("section-relationships").locator("summary").click()
        page.get_by_test_id("add-relationship").click()
        page.get_by_test_id("rel-type").last.click()
        page.get_by_test_id("rel-type-option").first.wait_for()
        row = page.get_by_test_id("rel-row").last.bounding_box()
        menu = page.get_by_test_id("rel-type-menu").bounding_box()
        # the list may open above or below the row: take both
        x0, y0 = min(row["x"], menu["x"]) - 12, min(row["y"], menu["y"]) - 12
        x1, y1 = max(row["x"] + row["width"], menu["x"] + menu["width"]) + 12, max(row["y"] + row["height"], menu["y"] + menu["height"]) + 12
        shot(page, "relationship", clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
        page.goto(BASE + "/kb/#/settings")
        page.reload()                                   # drops the open form (its draft stays on this device)
        page.wait_for_selector("[data-testid=type-row]")
        # types: the record type editor with its live preview
        page.get_by_test_id("type-row").filter(has_text="Live session").first.get_by_role("button", name="Edit").click()
        page.wait_for_timeout(400)
        sheet = page.locator(".sheet").last
        shot(page, "types", sheet, pad=0)
        page.keyboard.press("Escape")
        # graph: a record's handles, the legend and filters
        page.goto(BASE + f"/kb/#/graph/{ids['course']}")
        page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt")
        page.wait_for_timeout(500)
        pos = page.evaluate(f"window.__kbGraph.renderedPosition('{ids['course']}')")
        page.mouse.move(*pos)
        page.wait_for_timeout(300)
        shot(page, "graph", page.locator(".graph-wrap"), pad=0)
        # activity: updates, with before and after
        page.goto(BASE + "/kb/#/activity")
        page.get_by_test_id("activity-entry").first.wait_for()
        bb = page.locator("#view").bounding_box()
        shot(page, "activity", clip={"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": min(bb["height"], 640)})
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
