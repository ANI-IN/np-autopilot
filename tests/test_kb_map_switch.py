"""Round 1 of the owner's DEV preview test (2026-11-07):

- Admins switch between the map (/) and the workspace from a button at the TOP of
  each page; nobody else sees either button. Hiding is convenience only: the
  workspace's routes still check the role on the server (tests/test_kb_api.py).
- The map is 2D only. The 3D view, its toggle and its bundle are gone, and an old
  ?dim=3d (or ?dim=2d) link opens the 2D map and is rewritten without it.

Runs the map and the workspace through the KB dev server, one browser, as each role.
"""
from __future__ import annotations

import json
import time

import pytest

from kb_support import USERS, ensure_users, requires_kb, token_for

pytest.importorskip("playwright.sync_api", reason="needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402

pytestmark = [requires_kb]
CONTEXTS: list = []


@pytest.fixture(scope="module")
def base():
    from kb_support import dev_server
    ensure_users()
    with dev_server() as b:
        yield b


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(autouse=True)
def _close_pages():
    yield
    while CONTEXTS:
        CONTEXTS.pop().close()


def _open(browser, url, role):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    CONTEXTS.append(ctx)
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
    page = ctx.new_page()
    page.errors, page.requests = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))
    page.on("request", lambda r: page.requests.append(r.url))
    page.goto(url)
    return page


def _map_ready(page):
    page.wait_for_function("() => window.__NP && window.__NP.data && window.__NP.data.nodes.length >= 0"
                           " && document.getElementById('who').textContent.trim().length > 1", timeout=30000)


@pytest.mark.parametrize("role", ["admin", "editor", "viewer"])
def test_the_map_offers_the_workspace_graph_to_admins_only(base, browser, role):
    page = _open(browser, base + "/", role)
    _map_ready(page)
    btn = page.get_by_test_id("open-workspace-graph")
    if role == "admin":
        expect(btn).to_be_visible(timeout=15000)
        expect(btn).to_have_attribute("href", "/kb/#/admin")   # the Admin area (owner, 2026-11-07)
        expect(btn).to_contain_text("Admin")
        box = btn.bounding_box()
        assert box and box["y"] < 80, f"the button must sit at the top of the map, got y={box and box['y']}"
    else:
        page.wait_for_timeout(1500)                 # the role check has answered
        expect(btn).to_be_hidden()
    assert page.errors == []


@pytest.mark.parametrize("role", ["admin", "editor", "contributor", "viewer"])
def test_the_workspace_offers_the_map_at_the_top_to_admins_only(base, browser, role):
    page = _open(browser, base + "/kb/", role)
    expect(page.get_by_test_id("whoami")).to_contain_text(role, timeout=20000)
    link = page.get_by_test_id("back-to-site-nav")
    if role == "admin":
        expect(link).to_be_visible()
        expect(link).to_have_attribute("href", "/")
        box = link.bounding_box()
        assert box and box["y"] < 60, f"the map button must sit in the top row, got y={box and box['y']}"
    else:
        expect(link).to_have_count(0)
    assert page.errors == []


def test_the_map_has_no_3d_toggle_and_never_loads_the_3d_bundle(base, browser):
    page = _open(browser, base + "/", "admin")
    _map_ready(page)
    assert page.locator("#dimtog").count() == 0, "the 2D/3D toggle is still on the page"
    page.wait_for_timeout(1000)
    assert not [u for u in page.requests if "np3d" in u], "the 3D bundle was requested"
    assert page.errors == []


@pytest.mark.parametrize("dim", ["3d", "2d"])
def test_an_old_dim_link_opens_the_2d_map_and_drops_the_parameter(base, browser, dim):
    page = _open(browser, base + f"/?dim={dim}", "viewer")
    _map_ready(page)
    page.wait_for_function("() => !location.search.includes('dim=')", timeout=10000)
    assert page.locator("canvas#c").is_visible(), "the 2D map is not showing"
    assert not [u for u in page.requests if "np3d" in u]
    assert page.errors == []


def test_the_map_asks_for_its_structure_without_waiting_for_me(base, browser):
    """Sign-in timing (2026-11-07): /api/structure and /api/me start together,
    so the map pays one round trip before it can draw, not two."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    CONTEXTS.append(ctx)
    sess = json.dumps({"access_token": token_for(USERS["viewer"], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": "kbtest-viewer@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
    page = ctx.new_page()
    seen = []
    page.on("request", lambda r: r.url.split("?")[0].endswith(("/api/structure", "/api/me")) and seen.append(("start", r.url.split("?")[0].rsplit("/", 1)[1])))
    page.on("requestfinished", lambda r: r.url.split("?")[0].endswith("/api/me") and seen.append(("done", "me")))
    page.goto(base + "/")
    _map_ready(page)
    order = [e for e in seen]
    assert ("start", "structure") in order and ("done", "me") in order, order
    assert order.index(("start", "structure")) < order.index(("done", "me")), f"structure waited for /me: {order}"


@pytest.mark.parametrize("q", ["week=10", "week=10&domain=x", "view=timeline", "types=program_week,workflow,theme,module"])
def test_retired_weeks_workflows_and_themes_are_gone_from_the_map(base, browser, q):
    """Owner, 2026-11-07: the programme-week filter, ?week= links, the timeline view and the
    week/workflow/theme types are gone. An old link opens with no week filter (the
    address is rewritten without it) and the map still works."""
    page = _open(browser, base + "/?" + q, "viewer")
    _map_ready(page)
    page.wait_for_function("() => !location.search.includes('week=')", timeout=10000)
    expect(page.locator("#fwk")).to_have_count(0)
    expect(page.locator('#vbar [data-view="timeline"]')).to_have_count(0)
    assert page.evaluate("() => location.search.includes('timeline')") is False
    html = page.content()
    for gone in ("Programme week", "Programme weeks", "Programme timeline"):
        assert gone not in page.locator("body").inner_text(), gone
    assert "Workflows" not in page.locator("#legend, .legend, #chips").all_inner_texts().__str__()
    assert html
