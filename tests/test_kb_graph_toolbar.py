"""The Graph page's load and toolbar, end to end in a real browser (2026-11-07).

Regression tests for the DEV report: on load "Could not load this. Cannot read
properties of undefined (reading 'forEach')", then Reset "Not reset: Cannot
read properties of null (reading 'edges')". The whole graph now loads in pages,
an unreadable or incomplete reply is reported as such, and the toolbar's
buttons say the graph has not loaded instead of failing on a missing canvas.

Covers: paged load, auto-layout (saves positions), reset (forgets them), save
view, connect, and the failure paths. SYNTHETIC records (kb_support resets the
kb tables around each test). One browser, one page at a time.
"""
from __future__ import annotations

import pytest

from kb_support import USERS, Client, requires_kb
from test_kb_e2e import CONTEXTS, _data, page_as, toast, eventually  # noqa: F401  (_data: the per-test reset)

pytest.importorskip("playwright.sync_api", reason="kb e2e: needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402

pytestmark = [requires_kb]


@pytest.fixture(scope="module")
def server():
    from kb_support import dev_server
    with dev_server() as base:
        yield base + "/kb/"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _records():
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Toolbar Course"})
    mods = [ed.post("/api/kb/nodes", {"type": "module", "name": f"Toolbar Module {i}", "parents": [course["id"]]})[1] for i in range(3)]
    _, topic = ed.post("/api/kb/nodes", {"type": "topic", "name": "Toolbar Topic"})
    return course, mods, topic


def _loaded(page):
    page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=30000)
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing")


def _positions(layout="default"):
    return Client(USERS["admin"]).get("/api/kb/graph/positions", f"layout={layout}")[1]["items"]


def test_whole_graph_loads_in_pages(server, browser):
    course, mods, topic = _records()
    page = page_as(browser, server, "admin")
    calls = []
    page.on("request", lambda r: "/api/kb/graph?" in r.url and calls.append(r.url))
    page.goto(server + "#/graph?limit=2")                    # 5 records, 2 per page: 3 pages
    _loaded(page)
    assert len(calls) >= 3, calls
    ids = page.evaluate("() => window.__kbGraph.cy.nodes().map((n) => n.id())")
    for rid in [course["id"], topic["id"], *(m["id"] for m in mods)]:
        assert rid in ids
    expect(page.locator(".error-box")).to_have_count(0)
    assert page.errors == []


def test_auto_layout_saves_and_reset_forgets(server, browser):
    _records()
    page = page_as(browser, server, "admin")
    page.goto(server + "#/graph")
    _loaded(page)
    page.get_by_test_id("graph-autolayout").click()
    expect(toast(page).filter(has_text="Arranged and saved")).to_be_visible()
    eventually(lambda: len(_positions()) >= 5, what="the saved positions")
    page.get_by_test_id("graph-reset").click()
    page.get_by_test_id("confirm-ok").click()
    expect(toast(page).filter(has_text="Layout reset")).to_be_visible()
    eventually(lambda: _positions() == [], what="positions forgotten")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing")
    assert page.errors == []


def test_save_view_keeps_positions(server, browser):
    _records()
    page = page_as(browser, server, "admin")
    page.goto(server + "#/graph")
    _loaded(page)
    page.get_by_test_id("graph-save-view").click()
    page.get_by_test_id("graph-view-name").fill("Toolbar view")
    page.get_by_test_id("graph-view-save").click()
    expect(toast(page).filter(has_text="Saved view")).to_be_visible()
    page.wait_for_function("() => location.hash.includes('view=')")
    view_id = page.evaluate("() => new URLSearchParams(location.hash.split('?')[1]).get('view')")
    assert len(_positions(view_id)) >= 5
    _loaded(page)
    expect(page.get_by_test_id("graph-layout")).to_contain_text("Toolbar view")
    assert page.errors == []


def test_connect_two_records(server, browser):
    course, mods, topic = _records()
    page = page_as(browser, server, "admin")       # the graph editor is admin-only
    page.goto(server + "#/graph")
    _loaded(page)
    page.get_by_test_id("graph-connect").click()
    pos = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy; cy.layout({{name:'grid', fit:true, padding:60}}).run();
        const r = document.getElementById('cy').getBoundingClientRect();
        const p = id => {{ const q = cy.getElementById(id).renderedPosition(); return [r.left + q.x, r.top + q.y]; }};
        return [p('{mods[0]['id']}'), p('{topic['id']}')]; }}""")
    page.mouse.click(*pos[0])
    page.mouse.click(*pos[1])
    page.get_by_test_id("graph-rel").click()
    page.get_by_test_id("graph-rel-option").first.click()
    page.get_by_test_id("connect-submit").click()
    expect(toast(page).filter(has_text="Connected")).to_be_visible()
    edges = Client(USERS["viewer"]).get("/api/kb/edges", f"node={topic['id']}")[1]["items"]
    assert len(edges) == 1
    assert page.errors == []


@pytest.mark.parametrize("body,message", [("<html>not json</html>", "could not be read"),
                                          ("{}", "incomplete")])
def test_a_bad_reply_is_reported_and_the_toolbar_stays_safe(server, browser, body, message):
    _records()
    page = page_as(browser, server, "admin")
    page.route("**/api/kb/graph?**", lambda route: route.fulfill(status=200, body=body, content_type="application/json"))
    page.goto(server + "#/graph")
    expect(page.locator(".error-box")).to_contain_text(message)
    for testid in ("graph-reset", "graph-autolayout", "graph-save-view", "graph-connect"):
        page.get_by_test_id(testid).click()
        expect(toast(page).filter(has_text="did not load").first).to_be_visible()
    expect(page.get_by_test_id("confirm-ok")).to_have_count(0)
    page.unroute("**/api/kb/graph?**")
    page.locator(".error-box").get_by_role("button").first.click()      # Try again
    _loaded(page)
    assert page.errors == []
