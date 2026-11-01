"""M5/M6/M7 — end-to-end through a real browser (Playwright, system Chrome),
against eval/kb_dev_server.py: the real WSGI app, real token verification, RLS.

Covers the wrapper's acceptance paths: create → edit → connect → archive →
restore for a node, a course created INLINE, a resource and an edge; the graph
(open, expand, details, filter by type); search and filters; the 409 conflict
dialog with two sessions; and role restrictions per role.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from kb_support import USERS, Client, dev_server, ensure_users, requires_kb, reset, token_for

pytest.importorskip("playwright.sync_api", reason="kb e2e: needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402

pytestmark = [requires_kb]
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server():
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


@pytest.fixture(autouse=True)
def _data():
    ensure_users()
    reset()
    yield
    reset()


def page_as(browser, base, role, viewport=(1400, 900)):
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)})")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base)
    expect(page.get_by_test_id("whoami")).to_contain_text(role)
    page.errors = errors
    return page


def open_record(page, base, node_id):
    page.goto(base + f"#/records?open={node_id}")
    try:
        expect(page.get_by_test_id("panel-name")).to_be_visible()
    except AssertionError:
        page.screenshot(path=str(REPO.parent / "np-logs" / "e2e-fail.png"))
        print("URL", page.url, "ERRORS", page.errors)
        raise


# ---------------------------------------------------------------------------

def test_node_and_inline_course_lifecycle(server, browser):
    page = page_as(browser, server, "editor")
    # CREATE a module, creating its course INLINE from the picker
    page.get_by_test_id("new-record").click()
    page.get_by_test_id("create-type").select_option("module")
    page.get_by_test_id("create-name").fill("Week 1: Foundations")
    page.get_by_test_id("scope-picker").fill("Distributed Systems")
    page.get_by_test_id("picker-create-course").click()
    expect(page.get_by_test_id("scope-picker-picked")).to_contain_text("Distributed Systems")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Week 1: Foundations")
    expect(page.get_by_test_id("panel-scope")).to_contain_text("Distributed Systems (course)")
    # EDIT inline: summary, then name
    page.get_by_test_id("panel-summary").click()
    page.get_by_test_id("edit-summary").fill("Consensus, replication, clocks")
    page.get_by_test_id("panel-name").click()       # blur saves the summary
    expect(page.get_by_test_id("panel-summary")).to_have_text("Consensus, replication, clocks")
    expect(page.get_by_test_id("panel-version")).to_have_text("v2")
    # The course exists as a first-class record with its own page
    page.goto(server + "#/courses")
    expect(page.get_by_test_id("row")).to_have_count(1)
    page.get_by_test_id("row").first.click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Distributed Systems")
    # CONNECT: course contains module (searchable picker)
    page.get_by_test_id("connect").click()
    options = page.get_by_test_id("connect-type").locator("option").all_text_contents()
    page.get_by_test_id("connect-type").select_option(index=[i for i, o in enumerate(options) if o.startswith("contains")][0])
    page.get_by_test_id("connect-picker").fill("Week 1")
    page.get_by_test_id("picker-option").first.click()
    page.get_by_test_id("connect-submit").click()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    expect(page.get_by_test_id("panel-relationships")).to_contain_text("Week 1: Foundations")
    # ARCHIVE the course: the dialog shows the impact first
    page.get_by_test_id("archive").click()
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 relationship(s)")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 record(s) belong to it")
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("restore")).to_be_visible()
    # RESTORE brings the relationship back
    page.get_by_test_id("restore").click()
    expect(page.get_by_test_id("archive")).to_be_visible()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    assert page.errors == []


def test_resource_lifecycle_and_reuse(server, browser):
    api = Client(USERS["editor"])
    _, a = api.post("/api/kb/nodes", {"type": "topic", "name": "Caching"})
    _, b = api.post("/api/kb/nodes", {"type": "topic", "name": "CDNs"})
    page = page_as(browser, server, "editor")
    # CREATE a resource by attaching a new URL to a record
    open_record(page, server, a["id"])
    page.get_by_test_id("attach").click()
    page.get_by_test_id("attach-search").fill("https://example.com/caching-guide")
    page.get_by_test_id("attach-title").fill("Caching guide")
    page.get_by_test_id("attach-add-url").click()
    page.get_by_test_id("attach-submit").click()
    expect(page.get_by_test_id("panel-resources")).to_contain_text("Caching guide")
    # REUSE: the same URL on another record links the existing resource
    open_record(page, server, b["id"])
    page.get_by_test_id("attach").click()
    page.get_by_test_id("attach-search").fill("caching")
    page.get_by_test_id("attach-option").first.click()
    page.get_by_test_id("attach-submit").click()
    expect(page.get_by_test_id("panel-resources")).to_contain_text("Caching guide")
    # EDIT the resource from its own panel
    page.goto(server + "#/resources")
    page.get_by_test_id("res-row").first.click()
    expect(page.get_by_test_id("res-used-by")).to_contain_text("Caching")
    expect(page.get_by_test_id("res-used-by")).to_contain_text("CDNs")
    page.get_by_test_id("res-edit").click()
    page.get_by_test_id("res-edit-title").fill("Caching guide (2026)")
    page.get_by_test_id("res-edit-save").click()
    expect(page.get_by_test_id("res-panel")).to_contain_text("Caching guide (2026)")
    # A duplicate URL through "New resource" is refused with a link to the existing one
    page.get_by_test_id("new-resource").click()
    page.get_by_test_id("res-url").fill("https://EXAMPLE.com/caching-guide/")
    page.get_by_test_id("res-title").fill("dupe")
    page.get_by_test_id("res-submit").click()
    expect(page.locator("#modal-box")).to_contain_text("already in the library")
    page.keyboard.press("Escape")
    # ARCHIVE → detached everywhere; RESTORE → re-attached
    page.get_by_test_id("res-archive").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("res-restore")).to_be_visible()
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{a['id']}")[1]["resources"] == []
    page.get_by_test_id("res-restore").click()
    expect(page.get_by_test_id("res-archive")).to_be_visible()
    assert len(Client(USERS["viewer"]).get(f"/api/kb/nodes/{b['id']}")[1]["resources"]) == 1
    assert page.errors == []


def test_edge_lifecycle_from_the_graph(server, browser):
    api = Client(USERS["editor"])
    _, course = api.post("/api/kb/courses", {"name": "Graph Course"})
    _, mod = api.post("/api/kb/nodes", {"type": "module", "name": "Graph Module"})
    _, topic = api.post("/api/kb/nodes", {"type": "topic", "name": "Graph Topic"})
    api.post("/api/kb/edges", {"type": "contains", "source_id": course["id"], "target_id": mod["id"]})
    page = page_as(browser, server, "editor")
    page.goto(server + f"#/graph/{course['id']}")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 2 record(s)")
    # EXPAND by script hook (canvas double-click coordinates are layout-dependent)
    page.evaluate(f"window.__kbGraph.expand('{mod['id']}')")
    # CONNECT in the graph: connect mode, click source then target
    page.get_by_test_id("graph-connect").click()
    pos = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy; cy.add({{group:'nodes', data:{{id:'{topic['id']}', label:'Graph Topic', type:'topic', color:'#059669', degree:0, shape:'ellipse'}}}});
        cy.layout({{name:'grid', fit:true, padding:40}}).run();
        const r = document.getElementById('cy').getBoundingClientRect();
        const p = id => {{ const q = cy.getElementById(id).renderedPosition(); return [r.left + q.x, r.top + q.y]; }};
        return [p('{mod['id']}'), p('{topic['id']}')]; }}""")
    page.mouse.click(*pos[0])
    page.mouse.click(*pos[1])
    expect(page.get_by_test_id("connect-submit")).to_be_visible()
    page.get_by_test_id("connect-submit").click()
    expect(page.locator("[data-testid=toast]").last).to_contain_text("Connected")
    edges = Client(USERS["viewer"]).get("/api/kb/edges", f"node={topic['id']}")[1]["items"]
    assert len(edges) == 1 and edges[0]["source_id"] == mod["id"]
    # ARCHIVE the edge in the UI, RESTORE it, and see it come back
    open_record(page, server, mod["id"])
    expect(page.get_by_test_id("rel")).to_have_count(2)
    page.get_by_test_id("rel").filter(has_text="Graph Topic").get_by_role("button", name="Remove relationship").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    eid = edges[0]["id"]
    assert Client(USERS["editor"]).post(f"/api/kb/edges/{eid}/restore")[0] == 200
    page.reload()
    expect(page.get_by_test_id("rel")).to_have_count(2)
    assert page.errors == []


def test_graph_expand_details_and_type_filter(server, browser):
    api = Client(USERS["admin"])
    _, c = api.post("/api/kb/courses", {"name": "Hub Course"})
    mods = []
    for i in range(3):
        _, m = api.post("/api/kb/nodes", {"type": "module", "name": f"M{i}"})
        api.post("/api/kb/edges", {"type": "contains", "source_id": c["id"], "target_id": m["id"]})
        mods.append(m)
    _, t = api.post("/api/kb/nodes", {"type": "topic", "name": "Deep Topic"})
    api.post("/api/kb/edges", {"type": "contains", "source_id": mods[0]["id"], "target_id": t["id"]})
    page = page_as(browser, server, "viewer")
    page.goto(server + f"#/graph/{c['id']}")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 4 record(s)")
    page.evaluate(f"window.__kbGraph.expand('{mods[0]['id']}')")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 5 record(s)")
    # click a node → details panel opens without leaving the graph
    pos = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy, r = document.getElementById('cy').getBoundingClientRect();
        const q = cy.getElementById('{t['id']}').renderedPosition(); return [r.left + q.x, r.top + q.y]; }}""")
    page.mouse.click(*pos)
    expect(page.get_by_test_id("panel-name")).to_have_text("Deep Topic")
    assert "#/graph/" in page.url
    # filter by type hides modules
    page.get_by_test_id("graph-filter-module").uncheck()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 2 record(s)")
    page.get_by_test_id("graph-filter-module").check()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 5 record(s)")
    # viewer: no connect mode offered
    expect(page.get_by_test_id("graph-connect")).to_have_count(0)
    assert page.errors == []


def test_search_palette_and_list_filters(server, browser):
    api = Client(USERS["contributor"])
    _, c = api.post("/api/kb/courses", {"name": "Algorithms"})
    api.post("/api/kb/nodes", {"type": "topic", "name": "Dynamic Programming", "summary": "tabulation"})
    api.post("/api/kb/nodes", {"type": "module", "name": "Sorting week", "scope": c["id"]})
    page = page_as(browser, server, "contributor")
    page.keyboard.press("Control+k")
    page.get_by_test_id("palette-input").fill("tabulation")
    expect(page.get_by_test_id("palette-node")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("panel-name")).to_have_text("Dynamic Programming")
    # palette quick-create
    page.keyboard.press("Control+k")
    page.get_by_test_id("palette-input").fill("Greedy Algorithms")
    page.get_by_test_id("palette-create-topic").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Greedy Algorithms")
    # list filters
    page.goto(server + "#/records")
    expect(page.get_by_test_id("row")).to_have_count(4)
    page.get_by_test_id("filter-type").select_option("topic")
    expect(page.get_by_test_id("row")).to_have_count(2)
    page.get_by_test_id("filter-type").select_option("")
    page.get_by_test_id("filter-scope").select_option(label="Algorithms (course)")
    expect(page.get_by_test_id("row")).to_have_count(1)
    expect(page.get_by_test_id("row")).to_contain_text("Sorting week")
    page.get_by_test_id("filter-scope").select_option("")
    page.get_by_test_id("filter-q").fill("dynamic")
    expect(page.get_by_test_id("row")).to_have_count(1)
    page.get_by_test_id("filter-q").fill("zzz-nothing")
    expect(page.get_by_test_id("empty")).to_contain_text("Nothing matches")
    # duplicate name through the create form links to the existing record
    page.get_by_test_id("new-record").click()
    page.get_by_test_id("create-type").select_option("topic")
    page.get_by_test_id("create-name").fill("  dynamic   programming ")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("open-existing")).to_be_visible()
    assert page.errors == []


def test_two_sessions_conflict_dialog(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Contested"})
    a = page_as(browser, server, "contributor")
    b = page_as(browser, server, "editor")
    open_record(a, server, n["id"])
    open_record(b, server, n["id"])
    # B saves first
    b.get_by_test_id("panel-summary").click()
    b.get_by_test_id("edit-summary").fill("Editor's version")
    b.get_by_test_id("panel-name").click()
    expect(b.get_by_test_id("panel-version")).to_have_text("v2")
    # A (still on v1) saves: conflict dialog, NOT a silent overwrite
    a.get_by_test_id("panel-summary").click()
    a.get_by_test_id("edit-summary").fill("Contributor's version")
    a.get_by_test_id("panel-name").click()
    expect(a.get_by_test_id("conflict-dialog")).to_be_visible()
    expect(a.get_by_test_id("conflict-diff")).to_contain_text("Contributor's version")
    expect(a.get_by_test_id("conflict-diff")).to_contain_text("Editor's version")
    expect(a.get_by_test_id("conflict-overwrite")).to_have_count(0)       # contributors cannot overwrite
    a.get_by_test_id("conflict-reload").click()
    expect(a.get_by_test_id("panel-summary")).to_have_text("Editor's version")
    # an editor CAN overwrite
    _, cur = Client(USERS["admin"]).get(f"/api/kb/nodes/{n['id']}")
    Client(USERS["admin"]).patch(f"/api/kb/nodes/{n['id']}", {"version": cur["version"], "summary": "Admin's version"})
    b.get_by_test_id("panel-summary").click()
    b.get_by_test_id("edit-summary").fill("Editor wins")
    b.get_by_test_id("panel-name").click()
    expect(b.get_by_test_id("conflict-overwrite")).to_be_visible()
    b.get_by_test_id("conflict-overwrite").click()
    expect(b.get_by_test_id("panel-version")).to_have_text("v4")
    expect(b.get_by_test_id("panel-summary")).to_have_text("Editor wins")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{n['id']}")[1]["summary"] == "Editor wins"
    assert a.errors == [] and b.errors == []


def test_live_update_reaches_an_open_record(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Live"})
    page = page_as(browser, server, "viewer")
    open_record(page, server, n["id"])
    Client(USERS["editor"]).patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "changed elsewhere"})
    expect(page.get_by_test_id("panel-summary")).to_have_text("changed elsewhere", timeout=15000)
    expect(page.get_by_test_id("live-banner")).to_be_visible()


@pytest.mark.parametrize("role", ["viewer", "contributor", "editor", "admin"])
def test_role_restrictions_in_the_ui(server, browser, role):
    _, n = Client(USERS["admin"]).post("/api/kb/nodes", {"type": "topic", "name": "Roles"})
    page = page_as(browser, server, role)
    open_record(page, server, n["id"])
    if role == "viewer":
        expect(page.get_by_test_id("archive")).to_have_count(0)
        expect(page.get_by_test_id("connect")).to_have_count(0)
        expect(page.get_by_test_id("attach")).to_have_count(0)
        assert page.get_by_test_id("panel-name").get_attribute("contenteditable") is None
    elif role == "contributor":
        expect(page.get_by_test_id("archive")).to_have_text("Propose archive")
        page.get_by_test_id("archive").click()
        page.get_by_test_id("archive-reason").fill("superseded")
        page.get_by_test_id("confirm-ok").click()
        expect(page.locator("[data-testid=toast]").last).to_contain_text("Sent for approval")
        page.goto(server + "#/proposals")
        expect(page.get_by_test_id("proposal")).to_have_count(1)
        expect(page.get_by_test_id("approve")).to_have_count(0)
    else:
        expect(page.get_by_test_id("archive")).to_have_text("Archive")
        page.goto(server + "#/settings")
        expect(page.get_by_test_id("tokens")).to_be_visible()
        expect(page.get_by_test_id("members")).to_have_count(1 if role == "admin" else 0)
    page.goto(server + "#/records")
    expect(page.get_by_test_id("new-record")).to_have_count(0 if role == "viewer" else 1)
    assert page.errors == []


def test_approving_a_proposal_in_the_ui(server, browser):
    _, n = Client(USERS["contributor"]).post("/api/kb/nodes", {"type": "topic", "name": "Obsolete"})
    Client(USERS["contributor"]).post(f"/api/kb/nodes/{n['id']}/archive", {"reason": "old"})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/proposals")
    page.get_by_test_id("approve").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("empty")).to_contain_text("Nothing waiting")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{n['id']}")[1]["archived_at"]


def test_tablet_width_layout_and_tokens(server, browser):
    page = page_as(browser, server, "viewer", viewport=(820, 1100))
    page.goto(server + "#/settings")
    page.get_by_test_id("token-name").fill("tablet")
    page.get_by_test_id("token-create").click()
    expect(page.get_by_test_id("token-value")).to_have_value(__import__("re").compile(r"^ikkb_"))
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("token-row")).to_have_count(1)
    page.get_by_test_id("token-revoke").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("token-row")).to_contain_text("revoked")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
