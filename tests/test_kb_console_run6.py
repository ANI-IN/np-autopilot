"""Run 6 (B5): zero console errors and zero unhandled promise rejections on
every screen and the main flows, in a real browser against eval/kb_dev_server.py
(the real WSGI app, token verification, RLS, the production CSP).

A page error, a console error (CSP violations included) or an unhandled
promise rejection anywhere fails the test, with the screen it happened on.
One browser, one page at a time. Take the browser lock first
(.run6/browser.lock) when other agents share the machine.
"""
from __future__ import annotations

import json
import time

import pytest

from kb_support import USERS, Client, dev_server, ensure_users, requires_kb, reset, token_for

pytest.importorskip("playwright.sync_api", reason="kb console: needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402

pytestmark = [requires_kb]

SCREENS = ["#/", "#/records", "#/programs", "#/courses", "#/resources", "#/outline", "#/graph", "#/teaching",
           "#/activity", "#/quality", "#/approvals", "#/archived", "#/guide",
           "#/settings?tab=types", "#/settings?tab=relationships", "#/settings?tab=links", "#/settings?tab=tags",
           "#/settings?tab=members", "#/settings?tab=tokens", "#/settings?tab=templates", "#/settings?tab=sync",
           "#/settings?tab=people"]

# Reported to the console as an error, so the console listener sees it.
REJECTIONS = """window.addEventListener('unhandledrejection', (e) => {
  const r = e.reason; console.error('unhandledrejection: ' + (r && (r.stack || r.message) || String(r)));
});"""


@pytest.fixture(scope="module")
def server():
    with dev_server() as base:
        yield base


@pytest.fixture(scope="module")
def data():
    ensure_users()
    reset()
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Console Course", "summary": "A course for the console pass"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Console Module", "parents": [course["id"]],
                                       "resources": [{"url": "https://example.com/console", "title": "Console link"}]})
    ed.post("/api/kb/nodes", {"type": "module", "name": "Console Module Two", "parents": [course["id"]]})
    yield {"course": course["id"], "module": mod["id"]}
    reset()


def _page(browser, base, role, log):
    ctx = browser.new_context(viewport={"width": 1536, "height": 900})
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});" + REJECTIONS)
    page = ctx.new_page()
    where = {"at": "load"}
    page.on("console", lambda m: m.type == "error" and log.append(f"{where['at']}: console.error: {m.text[:300]}"))
    page.on("pageerror", lambda e: log.append(f"{where['at']}: pageerror: {str(e)[:300]}"))
    page.where = where
    return ctx, page


def _settle(page):
    page.wait_for_function("() => !!document.querySelector('#view > *') && "
                           "!document.querySelector('.skeleton, [aria-busy=\"true\"]')", timeout=30000)
    page.wait_for_load_state("networkidle")


@pytest.mark.parametrize("role", ["admin", "viewer"])
def test_every_screen_and_flow_without_console_errors(server, data, role):
    log: list[str] = []
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = pw.chromium.launch(headless=True)
        ctx, page = _page(b, server + "/kb/", role, log)
        page.goto(server + "/kb/")
        expect(page.get_by_test_id("whoami")).to_contain_text(role)
        for route in SCREENS:
            page.where["at"] = route
            page.goto(server + "/kb/" + route)
            _settle(page)
        # a record: the panel, the full page, the graph around it (open + expand)
        page.where["at"] = "record panel"
        page.goto(server + f"/kb/#/records?open={data['course']}")
        expect(page.get_by_test_id("panel-name")).to_have_text("Console Course")
        _settle(page)
        page.where["at"] = "record page"
        page.goto(server + f"/kb/#/r/{data['module']}")
        _settle(page)
        page.where["at"] = "graph"
        page.goto(server + f"/kb/#/graph/{data['course']}?depth=1")
        if role == "admin":                  # the graph editor is admin-only (2026-11-07); others see "Admins only"
            page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=30000)
            page.evaluate(f"() => window.__kbGraph.expand('{data['module']}')")
        else:
            expect(page.get_by_test_id("admins-only")).to_be_visible()
        _settle(page)
        if role == "admin":
            page.where["at"] = "new record sheet"
            page.goto(server + "/kb/#/records")
            _settle(page)
            page.get_by_test_id("new-record").click()
            expect(page.get_by_test_id("create-name")).to_be_visible()
            page.keyboard.press("Escape")
        page.where["at"] = "search"
        page.goto(server + "/kb/#/records")
        _settle(page)
        page.keyboard.press("Control+k")
        page.keyboard.type("Console")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("Escape")
        page.where["at"] = "the NP Autopilot map at /"
        page.goto(server + "/")
        page.wait_for_load_state("networkidle", timeout=60000)
        ctx.close()
        b.close()
    assert log == [], "\n".join(log)
