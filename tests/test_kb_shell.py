"""The Direction A shell (owner decision 2026-11-07, docs/design/phase1/DECISION.md),
end to end in a real browser: navigation by role, the Admin group (hidden for
viewers, enforced on the server), the theme toggle (system by default), Home's
search-first top, the search results page, and WCAG AA contrast of chips and
badges in light and dark mode.

SYNTHETIC records (kb_support resets the kb tables around each test).
"""
from __future__ import annotations

import pytest

from kb_support import USERS, Client, requires_kb
from test_kb_e2e import CONTEXTS, _data, page_as, eventually  # noqa: F401  (_data: the per-test reset)

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


def _records(n_topics=7):
    ed = Client(USERS["editor"])
    _, prog = ed.post("/api/kb/programs", {"name": "Shell Program"})
    _, course = ed.post("/api/kb/courses", {"name": "Shell Course"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Shell Hashing Module", "parents": [course["id"]]})
    topics = [ed.post("/api/kb/nodes", {"type": "topic", "name": f"Hashing topic {i}", "parents": [mod["id"]]})[1] for i in range(n_topics)]
    return prog, course, mod, topics


@pytest.mark.parametrize("role,admin_items", [
    ("viewer", []),
    ("contributor", ["Overview", "Approvals", "Data quality"]),
    ("editor", ["Overview", "Approvals", "Data quality", "Activity", "Archived"]),
    ("admin", ["Overview", "Graph editor", "Approvals", "Data quality", "Activity", "Archived", "Members", "Sources & sync"]),
])
def test_navigation_by_role(server, browser, role, admin_items):
    page = page_as(browser, server, role)
    browse = page.locator("#nav .nav-group").nth(1)
    expect(browse.locator(".nav-group-label")).to_have_text("Browse")
    for label in ("Programs", "Courses", "Resources", "Who teaches what", "All records", "Outline", "Map"):
        expect(browse.get_by_role("link", name=label, exact=True)).to_be_visible()
    expect(page.locator("#nav").get_by_role("link", name="Graph", exact=True)).to_have_count(0)    # no "Graph" in Browse
    expect(page.get_by_test_id("nav-map")).to_have_attribute("href", "/")
    expect(page.get_by_test_id("nav-home")).to_be_visible()
    admin = page.get_by_test_id("nav-admin-group")
    if not admin_items:
        expect(admin).to_have_count(0)
    else:
        expect(admin.locator("a")).to_have_text(admin_items)
        # the Admin group sits below Browse, at the bottom of the sidebar
        assert admin.bounding_box()["y"] > browse.bounding_box()["y"] + browse.bounding_box()["height"] - 1
    assert page.errors == []


@pytest.mark.parametrize("role", ["viewer", "contributor", "editor"])
def test_graph_editor_is_admin_only_in_the_page_and_on_the_server(server, browser, role):
    _, course, mod, _t = _records(1)
    page = page_as(browser, server, role)
    page.goto(server + "#/graph")
    expect(page.get_by_test_id("admins-only")).to_be_visible()
    expect(page.get_by_test_id("graph-canvas")).to_have_count(0)
    page.goto(server + f"#/records?open={mod['id']}")
    expect(page.locator("#panel")).to_be_visible()
    expect(page.locator("#panel")).to_contain_text("Shell Hashing Module")
    expect(page.get_by_test_id("open-graph")).to_have_count(0)
    # enforced on the server: the editor's writes are refused for anyone but an admin
    c = Client(USERS[role])
    s, _ = c.post("/api/kb/graph/positions", {"positions": [{"node_id": mod["id"], "x": 1.0, "y": 2.0}]})
    assert s == 403, s
    s, _ = c.call("DELETE", "/api/kb/graph/positions", query="layout=default")
    assert s == 403, s
    s, _ = Client(USERS["admin"]).post("/api/kb/graph/positions", {"positions": [{"node_id": mod["id"], "x": 1.0, "y": 2.0}]})
    assert s == 200, s
    assert page.errors == []


def test_members_and_sync_stay_admin_only_on_the_server(server, browser):
    for role in ("viewer", "contributor", "editor"):
        s, _ = Client(USERS[role]).get("/api/kb/sync")
        assert s == 403, (role, s)
    assert Client(USERS["admin"]).get("/api/kb/sync")[0] == 200


def test_admin_overview_lists_the_tools_of_the_role(server, browser):
    page = page_as(browser, server, "admin")
    page.goto(server + "#/admin")
    expect(page.get_by_test_id("admin-card")).to_have_count(7)
    expect(page.get_by_test_id("admin-overview")).to_contain_text("Graph editor")
    page = page_as(browser, server, "contributor")
    page.goto(server + "#/admin")
    expect(page.get_by_test_id("admin-card")).to_have_count(2)
    expect(page.get_by_test_id("admin-overview")).not_to_contain_text("Graph editor")


def _bg(page):
    return page.evaluate("() => getComputedStyle(document.body).backgroundColor")


def test_theme_toggle_cycles_and_persists_and_follows_the_system(server, browser):
    page = page_as(browser, server, "viewer")
    btn = lambda: page.get_by_test_id("theme-toggle")                    # noqa: E731
    expect(btn()).to_have_attribute("data-theme-choice", "system")
    page.emulate_media(color_scheme="dark")
    assert _bg(page) == "rgb(11, 18, 32)"                             # B's navy, from the system setting
    page.emulate_media(color_scheme="light")
    assert _bg(page) == "rgb(255, 255, 255)"
    btn().click()
    expect(btn()).to_have_attribute("data-theme-choice", "light")
    page.emulate_media(color_scheme="dark")
    assert _bg(page) == "rgb(255, 255, 255)"                          # an explicit choice beats the system
    btn().click()
    expect(btn()).to_have_attribute("data-theme-choice", "dark")
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    page.reload()
    expect(page.get_by_test_id("whoami")).to_be_visible()
    expect(btn()).to_have_attribute("data-theme-choice", "dark")
    assert _bg(page) == "rgb(11, 18, 32)"
    btn().click()
    expect(btn()).to_have_attribute("data-theme-choice", "system")
    assert page.evaluate("() => document.documentElement.dataset.theme || null") is None
    assert page.errors == []


def test_home_search_first_then_cards(server, browser):
    prog, course, mod, topics = _records(7)
    page = page_as(browser, server, "viewer")
    expect(page.get_by_test_id("home-hero")).to_be_visible()
    expect(page.get_by_test_id("home-search-input")).to_be_focused()
    expect(page.get_by_test_id("home-type-program")).to_be_visible()
    expect(page.get_by_test_id("home-programs")).to_contain_text("Shell Program")
    expect(page.get_by_test_id("dash-attention")).to_have_count(0)        # viewers cannot fix it
    hero = page.get_by_test_id("home-hero").bounding_box()
    cards = page.get_by_test_id("dashboard").bounding_box()
    assert hero["y"] < cards["y"]
    page.get_by_test_id("home-search-input").fill("hashing")
    page.get_by_test_id("home-search-input").press("Enter")
    page.wait_for_function("() => location.hash.startsWith('#/search?q=hashing')")
    groups = page.get_by_test_id("search-group")
    expect(groups.first).to_be_visible()
    topic_group = page.locator("[data-testid=search-group][data-type=topic]")
    expect(topic_group.get_by_test_id("search-hit")).to_have_count(5)    # 5 per group, then "See all"
    topic_group.get_by_test_id("search-see-all").click()
    page.wait_for_function("() => location.hash.includes('type=topic')")
    expect(page.locator("[data-testid=search-group][data-type=topic]").get_by_test_id("search-hit")).to_have_count(7)
    expect(page.locator("[data-testid=search-group][data-type=module]")).to_have_count(0)
    page.locator("[data-testid=search-hit]").first.click()
    page.wait_for_function("() => location.hash.includes('open=')")
    assert "#/search" in page.url                                       # the record opens beside the results
    # the recent search becomes a suggestion on Home
    page.goto(server + "#/")
    expect(page.get_by_test_id("home-recent").first).to_have_text("hashing")
    page.goto(server + "#/search?q=zzzznothing")
    expect(page.get_by_test_id("search-results")).to_contain_text("Nothing matches")
    assert page.errors == []


CONTRAST = """() => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/) || c.match(/color\\(srgb ([^)]+)\\)/); if (!m) return null;
    const p = m[1].replace(/\\//, ' ').split(/[ ,]+/).filter(Boolean).map(Number);
    const srgb = c.startsWith('color('); return { r: srgb ? p[0] * 255 : p[0], g: srgb ? p[1] * 255 : p[1], b: srgb ? p[2] * 255 : p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = (el) => { const stack = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } }
    let out = { r: 255, g: 255, b: 255 }; for (const c of stack.reverse()) out = { r: c.r * c.a + out.r * (1 - c.a), g: c.g * c.a + out.g * (1 - c.a), b: c.b * c.a + out.b * (1 - c.a) }; return out; };
  const bad = [];
  document.querySelectorAll('.chip, .filter-chip, .badge, .count, .nav-group-label, .chip .count, .filter-chip.on').forEach((el) => {
    if (!el.offsetParent || !el.textContent.trim()) return;
    const fg = parse(getComputedStyle(el).color), bg = bgOf(el); if (!fg) return;
    const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    if (ratio < 4.5) bad.push({ cls: el.className, text: el.textContent.trim().slice(0, 20), ratio: Math.round(ratio * 100) / 100 });
  });
  return bad; }"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_chips_and_badges_meet_aa_contrast(server, browser, theme):
    _records(6)
    page = page_as(browser, server, "admin")
    page.evaluate(f"() => {{ localStorage.setItem('kb_theme', '{theme}'); }}")
    for route in ("#/", "#/search?q=hashing", "#/records", "#/admin"):
        page.goto(server + route)
        page.reload()
        expect(page.get_by_test_id("whoami")).to_be_visible()
        page.wait_for_timeout(600)
        assert page.evaluate("() => document.documentElement.dataset.theme") == theme
        bad = page.evaluate(CONTRAST)
        assert bad == [], (theme, route, bad)
    assert page.errors == []
