"""Run 6, B2: the Graph page's structure and navigation, end to end in a real
browser (Playwright, system Chrome) against eval/kb_dev_server.py.

Covers: the default hierarchical layout (Program > Course > Domain > Module >
Week > Session, satellites under their record, bundles), the legend as a
filter, focus mode and breadcrumbs, search that jumps into a bundle, the
minimap and fit, switching arrangements, the legacy toggle, grouping with
folding, the `?` shortcut sheet, live updates from the change feed, and that
no two visible labels overlap at normal zoom.

The records are SYNTHETIC (kb_support resets the kb tables of the test
database before and after each test). One browser, one page at a time.
"""
from __future__ import annotations

import pytest

from kb_support import USERS, Client, owner, requires_kb
from test_kb_e2e import CONTEXTS, _data, page_as, toast  # noqa: F401  (_data: the per-test reset)

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


def _tree(topics: int = 3) -> dict:
    """Program > Course > Domain > Module > Week > Session, plus topics on the module."""
    ed = Client(USERS["editor"])
    ids = {}
    _, ids["program"] = ed.post("/api/kb/programs", {"name": "Run6 Program"})
    _, ids["course"] = ed.post("/api/kb/nodes", {"type": "course", "name": "Run6 Course", "parents": [ids["program"]["id"]]})
    _, ids["domain"] = ed.post("/api/kb/nodes", {"type": "domain", "name": "Run6 Domain", "parents": [ids["course"]["id"]]})
    _, ids["module"] = ed.post("/api/kb/nodes", {"type": "module", "name": "Run6 Module", "parents": [ids["domain"]["id"]]})
    _, ids["week"] = ed.post("/api/kb/nodes", {"type": "week", "name": "Run6 Week", "parents": [ids["module"]["id"]]})
    _, ids["session"] = ed.post("/api/kb/nodes", {"type": "session", "name": "Run6 Session", "parents": [ids["week"]["id"]]})
    ids["topics"] = [ed.post("/api/kb/nodes", {"type": "topic", "name": f"Run6 Topic {i:02d}", "parents": [ids["module"]["id"]]})[1]
                     for i in range(topics)]
    for k in ("program", "course", "domain", "module", "week", "session"):
        assert "id" in ids[k], (k, ids[k])
    return ids


def _open(page, server, route="#/graph"):
    page.goto(server + route)
    page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing")


def _pos(page, rid):
    return page.evaluate(f"() => window.__kbGraph.cy.getElementById('{rid}').position()")


def _shown(page, rid):
    return page.evaluate(f"""() => {{ const n = window.__kbGraph.cy.getElementById('{rid}');
        return n.length > 0 && !n.hasClass('hidden') && !n.hasClass('bundled') && !n.hasClass('folded'); }}""")


OVERLAPS = """() => { const G = window.__kbGraph; G.declutter(); const bx = G.labelBoxes(); const out = [];
  for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) { const a = bx[i].b, c = bx[j].b;
    if (a.x1 < c.x2 && a.x2 > c.x1 && a.y1 < c.y2 && a.y2 > c.y1) out.push([bx[i].id, bx[j].id]); }
  return { shown: bx.length, overlaps: out }; }"""


def test_default_layout_is_the_hierarchy_with_satellites_and_bundles(server, browser):
    ids = _tree(topics=12)
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    _open(page, server)
    assert page.evaluate("() => window.__kbGraph.arrangement()") == "hierarchy"
    expect(page.get_by_test_id("graph-arrange")).to_have_value("hierarchy")
    ys = [_pos(page, ids[k]["id"])["y"] for k in ("program", "course", "domain", "module", "week", "session")]
    assert ys == sorted(ys) and len(set(ys)) == 6, ys                  # one row per level, top to bottom
    # 12 topics on one module: one bundle under the module, which opens on click
    bundle = page.evaluate("() => window.__kbGraph.cy.nodes('.bundle').map((b) => [b.id(), b.data('label'), b.position()])")
    assert len(bundle) == 1 and bundle[0][1] == "12 topics", bundle
    assert bundle[0][2]["y"] > _pos(page, ids["module"]["id"])["y"]
    expect(page.get_by_test_id("graph-info")).to_contain_text("12 more in 1 bundle")
    page.evaluate(f"() => window.__kbGraph.cy.getElementById('{bundle[0][0]}').emit('tap')")
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{ids['topics'][0]['id']}').length === 1")
    m = _pos(page, ids["module"]["id"])
    for t in ids["topics"]:
        p = _pos(page, t["id"])
        assert p["y"] > m["y"], "a satellite sits under its record"
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 18 record(s)")
    assert page.errors == []


def test_legend_is_a_filter(server, browser):
    ids = _tree(topics=3)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 9 record(s)")
    page.get_by_test_id("graph-filter-topic").uncheck()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 6 record(s)")
    assert not _shown(page, ids["topics"][0]["id"])
    page.get_by_test_id("graph-filter-topic").check()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 9 record(s)")
    # "Only": just that type; again: everything back
    page.get_by_test_id("graph-filter-module").hover()
    page.get_by_test_id("graph-only-module").click()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 1 record(s)")
    page.get_by_test_id("graph-filter-module").hover()
    page.get_by_test_id("graph-only-module").click()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 9 record(s)")
    # relationship types filter too, and the legend shows each one's line style
    expect(page.get_by_test_id("graph-legend").locator(".legend-edge").first).to_be_visible()
    page.get_by_test_id("graph-edge-filter-contains").uncheck()
    assert page.evaluate("() => window.__kbGraph.cy.edges('[type = \"contains\"]').every((e) => e.hasClass('hidden'))")
    assert page.errors == []


def test_focus_mode_and_breadcrumbs(server, browser):
    ids = _tree(topics=2)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    page.evaluate(f"() => {{ const cy = window.__kbGraph.cy; cy.$(':selected').unselect(); cy.getElementById('{ids['session']['id']}').select(); }}")
    crumbs = page.get_by_test_id("graph-breadcrumbs")
    expect(crumbs).to_be_visible()
    expect(crumbs.get_by_test_id("graph-crumb")).to_have_text(["Run6 Program", "Run6 Course", "Run6 Domain", "Run6 Module", "Run6 Week", "Run6 Session"])
    # a crumb jumps to that record
    crumbs.get_by_test_id("graph-crumb").filter(has_text="Run6 Domain").click()
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{ids['domain']['id']}').selected()")
    expect(crumbs.get_by_test_id("graph-crumb").last).to_have_text("Run6 Domain")
    # focus mode, 1 step: the domain and its neighbours stay, the rest dims
    page.get_by_test_id("graph-focus").select_option("1")
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{ids['session']['id']}').hasClass('dim')")
    assert not page.evaluate(f"() => window.__kbGraph.cy.getElementById('{ids['module']['id']}').hasClass('dim')")
    assert not page.evaluate(f"() => window.__kbGraph.cy.getElementById('{ids['course']['id']}').hasClass('dim')")
    assert "focus=1" in page.url
    page.get_by_test_id("graph-focus").select_option("2")
    page.wait_for_function(f"() => !window.__kbGraph.cy.getElementById('{ids['week']['id']}').hasClass('dim')")
    page.get_by_test_id("graph-focus").select_option("0")
    page.wait_for_function("() => window.__kbGraph.cy.nodes('.dim').length === 0")
    assert page.errors == []


def test_search_jumps_into_a_bundle(server, browser):
    ids = _tree(topics=10)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    target = ids["topics"][7]
    assert page.evaluate(f"() => window.__kbGraph.cy.getElementById('{target['id']}').length") == 0   # inside the bundle
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("/")
    expect(page.get_by_test_id("graph-search")).to_be_focused()
    page.keyboard.type("Run6 Topic 07")
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => {{ const n = window.__kbGraph.cy.getElementById('{target['id']}'); return n.length && n.selected() && n.hasClass('found'); }}")
    page.wait_for_timeout(400)                                         # the jump animates
    inside = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy, p = cy.getElementById('{target['id']}').renderedPosition();
        return p.x > 0 && p.y > 0 && p.x < cy.width() && p.y < cy.height(); }}""")
    assert inside
    assert page.errors == []


def test_minimap_and_fit(server, browser):
    _tree(topics=3)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    mini = page.get_by_test_id("minimap")
    expect(mini).to_be_visible()
    page.evaluate("() => { const cy = window.__kbGraph.cy; cy.zoom(2.5); cy.pan({ x: -3000, y: -3000 }); }")
    box = mini.bounding_box()
    before = page.evaluate("() => window.__kbGraph.cy.pan()")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    after = page.evaluate("() => window.__kbGraph.cy.pan()")
    assert before != after
    page.get_by_test_id("graph-fit").click()
    allin = page.evaluate("""() => { const cy = window.__kbGraph.cy, w = cy.width(), h = cy.height();
        return cy.nodes().filter((n) => !n.hasClass('hidden') && !n.id().startsWith('__')).every((n) => { const b = n.renderedBoundingBox({ includeLabels: false });
          return b.x1 >= -1 && b.y1 >= -1 && b.x2 <= w + 1 && b.y2 <= h + 1; }); }""")
    assert allin
    page.get_by_test_id("graph-minimap-toggle").click()
    expect(mini).to_be_hidden()
    page.get_by_test_id("graph-minimap-toggle").click()
    expect(mini).to_be_visible()
    assert page.errors == []


def test_switching_layouts(server, browser):
    ids = _tree(topics=3)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    page.evaluate(f"() => {{ const cy = window.__kbGraph.cy; cy.getElementById('{ids['module']['id']}').select(); }}")
    page.get_by_test_id("graph-arrange").select_option("radial")
    page.wait_for_function("() => window.__kbGraph.arrangement() === 'radial'")
    assert "arrange=radial" in page.url
    # radial: the selected record in the middle, its neighbours on the first ring
    m = _pos(page, ids["module"]["id"])
    assert abs(m["x"]) < 1 and abs(m["y"]) < 1, m
    d = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy, c = cy.getElementById('{ids['module']['id']}');
        return c.neighborhood('node').map((n) => Math.round(Math.hypot(n.position('x'), n.position('y')))); }}""")
    assert len(set(d)) == 1 and d[0] > 0, d
    page.get_by_test_id("graph-arrange").select_option("force")
    page.wait_for_function("() => window.__kbGraph.arrangement() === 'force'")
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("1")                                           # back to the hierarchy
    page.wait_for_function("() => window.__kbGraph.arrangement() === 'hierarchy'")
    ys = [_pos(page, ids[k]["id"])["y"] for k in ("program", "course", "domain", "module")]
    assert ys == sorted(ys)
    assert page.errors == []


def test_legacy_records_are_hidden_until_asked(server, browser):
    ids = _tree(topics=1)
    ed = Client(USERS["editor"])
    _, old = ed.post("/api/kb/nodes", {"type": "module", "name": "Old Module", "parents": [ids["domain"]["id"]]})
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        c.execute("update kb.nodes set is_legacy = true where id = %s", (old["id"],))
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    assert page.evaluate(f"() => window.__kbGraph.cy.getElementById('{old['id']}').length") == 0
    page.get_by_test_id("graph-legacy").check()
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{old['id']}').length === 1")
    assert "legacy=all" in page.url
    assert page.evaluate(f"() => window.__kbGraph.cy.getElementById('{old['id']}').hasClass('legacy')")
    page.get_by_test_id("graph-legacy").uncheck()
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{old['id']}').length === 0")
    assert page.errors == []


def test_group_by_type_folds_and_unfolds(server, browser):
    ids = _tree(topics=3)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    page.get_by_test_id("graph-group").select_option("type")
    page.wait_for_function("() => window.__kbGraph.cy.nodes('.gbox').length > 0")
    head = "__head:topic"
    page.evaluate(f"() => window.__kbGraph.cy.getElementById('{head}').emit('tap')")
    page.wait_for_function("() => window.__kbGraph.cy.getElementById('__g:topic').length === 1")
    assert not _shown(page, ids["topics"][0]["id"])
    expect(page.get_by_test_id("graph-info")).to_contain_text("3 in 1 folded group")
    page.evaluate("() => window.__kbGraph.cy.getElementById('__g:topic').emit('tap')")
    page.wait_for_function("() => window.__kbGraph.cy.getElementById('__g:topic').length === 0")
    assert _shown(page, ids["topics"][0]["id"])
    assert page.errors == []


def test_shortcut_sheet_hints_and_empty_state(server, browser):
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    _open(page, server)
    expect(page.get_by_test_id("graph-empty")).to_contain_text("Nothing to show yet")
    expect(page.get_by_test_id("graph-empty-new")).to_be_visible()
    expect(page.get_by_test_id("graph-hint")).to_contain_text("handles")
    page.get_by_test_id("graph-hint-dismiss").click()
    expect(page.get_by_test_id("graph-hint")).to_be_hidden()
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("?")
    sheet = page.get_by_test_id("graph-shortcuts")
    expect(sheet).to_be_visible()
    for k in ("/", "F", "N", "Delete", "1 · 2 · 3 · 4", "O"):
        expect(sheet.locator("kbd", has_text=k).first).to_be_visible()
    page.keyboard.press("Escape")
    expect(sheet).to_be_hidden()
    # a record added elsewhere arrives live; hovering it shows its handles
    _, n = Client(USERS["admin"]).post("/api/kb/nodes", {"type": "topic", "name": "Hover me"})   # someone else
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{n['id']}').length === 1", timeout=20000)
    expect(page.get_by_test_id("graph-empty")).to_be_hidden()
    page.evaluate(f"() => window.__kbGraph.cy.center(window.__kbGraph.cy.getElementById('{n['id']}'))")
    page.mouse.move(*page.evaluate(f"window.__kbGraph.renderedPosition('{n['id']}')"))
    expect(page.get_by_test_id("graph-handles")).to_be_visible()
    expect(page.get_by_test_id("graph-handle")).to_be_visible()
    assert page.errors == []


def test_live_change_arrives_through_apply_changes(server, browser):
    ids = _tree(topics=1)
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server)
    _, new = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "week", "name": "Arrives live", "parents": [ids["module"]["id"]]})
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{new['id']}').length === 1", timeout=20000)
    Client(USERS["editor"]).post(f"/api/kb/nodes/{new['id']}/archive", {})
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{new['id']}').length === 0", timeout=20000)
    assert page.errors == []


def test_labels_never_overlap_at_normal_zoom(server, browser):
    _tree(topics=8)
    ed = Client(USERS["editor"])
    _, d2 = ed.post("/api/kb/nodes", {"type": "domain", "name": "A second domain with a rather long name for labels"})
    for i in range(6):
        ed.post("/api/kb/nodes", {"type": "module", "name": f"Module with a long descriptive title number {i}", "parents": [d2["id"]]})
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    _open(page, server, "#/graph?expand=all")
    page.evaluate("() => { const cy = window.__kbGraph.cy; cy.zoom(1); cy.center(); }")
    page.wait_for_timeout(300)
    r = page.evaluate(OVERLAPS)
    assert r["shown"] >= 8 and r["overlaps"] == [], r
    # also in the other arrangements, at normal zoom
    for how in ("radial", "force"):
        page.get_by_test_id("graph-arrange").select_option(how)
        page.wait_for_function(f"() => window.__kbGraph.arrangement() === '{how}'")
        page.evaluate("() => { const cy = window.__kbGraph.cy; cy.zoom(1); cy.center(); }")
        page.wait_for_timeout(300)
        r = page.evaluate(OVERLAPS)
        assert r["overlaps"] == [], (how, r)
    assert page.errors == []
