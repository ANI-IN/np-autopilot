"""End-to-end through a real browser (Playwright, system Chrome) against
eval/kb_dev_server.py: the real WSGI app, real token verification, RLS, and the
production security headers (CSP: any violation fails the test that caused it).

Run 1 acceptance paths, updated for the redesigned UI (run 2), plus the run-2
paths: a custom type end to end; the one-step New record with nested inline
placement, relationships and links (one reused); rollback on a failed save; the
duplicate-name warning; disallowed relationships; contributor proposals;
archive → permanent delete; a conflict between two users; keyboard-only flows;
no horizontal scrolling at 1024px.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from kb_support import USERS, Client, dev_server, ensure_users, owner, requires_kb, reset, token_for

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


CONTEXTS: list = []


@pytest.fixture(autouse=True)
def _data():
    ensure_users()
    reset()
    _drop_custom()
    yield
    # Close this test's pages FIRST: an open page keeps polling the change feed,
    # and its queries would deadlock against the reset's TRUNCATE.
    while CONTEXTS:
        CONTEXTS.pop().close()
    reset()
    _drop_custom()


def _drop_custom():
    with owner() as c:
        c.execute("truncate kb.flags, kb.templates, kb.saved_views, kb.graph_positions")
        c.execute("delete from kb.proposals where action = 'type_change'")
        c.execute("delete from kb.node_types where not is_core")
        c.execute("delete from kb.edge_types where not is_core")


def page_as(browser, base, role, viewport=(1440, 900)):
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, accept_downloads=True)
    CONTEXTS.append(ctx)
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)}); if (!sessionStorage.getItem('kbt')) {{ localStorage.removeItem('kb_draft_new_record'); sessionStorage.setItem('kbt', '1'); }}")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and "Content Security Policy" in m.text and errors.append(m.text))
    page.goto(base)
    expect(page.get_by_test_id("whoami")).to_contain_text(role)
    page.errors = errors
    return page


def eventually(check, timeout: float = 10.0, what: str = "condition"):
    """Poll `check` until it is true (run 6, B5: replaces fixed sleeps, which
    raced the server and the re-render on a loaded machine)."""
    deadline = time.monotonic() + timeout
    while True:
        if check():
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"{what} did not become true within {timeout} s")
        time.sleep(0.1)


def settled(page, timeout: float = 15000):
    """The screen has finished loading: no skeleton and nothing aria-busy is
    left (run 6, B5: replaces fixed waits before layout and a11y checks)."""
    expect(page.locator(".skeleton, [aria-busy='true']")).to_have_count(0, timeout=timeout)


def open_record(page, base, node_id):
    page.goto(base + f"#/records?open={node_id}")
    expect(page.get_by_test_id("panel-name")).to_be_visible()


def more(page, item):
    page.get_by_test_id("more-actions").click()
    page.get_by_test_id(item).click()


def pick(page, testid, text, option_testid=None):
    page.get_by_test_id(testid).last.fill(text)
    opt = page.get_by_test_id(option_testid or f"{testid}-option").filter(has_text=text).first
    opt.click()


def choose_type(page, label):
    """Pick a record type in the New record form by its exact label."""
    page.get_by_test_id("create-type").fill(label)
    page.get_by_test_id("create-type-option").filter(has=page.get_by_text(label, exact=True)).first.click()


def select_matching(locator, pattern):
    """Select the first <option> whose text matches `pattern` (a regex string)."""
    opts = locator.locator("option").all_text_contents()
    match = next(o for o in opts if re.search(pattern, o))
    locator.select_option(label=match)


def choose_rel(page, pattern):
    """Pick a relationship in the searchable relationship picker (A7) by a regex
    on its sentence, e.g. "^This module covers a topic$"."""
    page.get_by_test_id("rel-type").last.click()
    page.get_by_test_id("rel-type-option").filter(has_text=re.compile(pattern)).first.click()


def rel_options(page):
    page.get_by_test_id("rel-type").last.click()
    page.get_by_test_id("rel-type-option").first.wait_for()
    return page.get_by_test_id("rel-type-option").all_text_contents()


def toast(page):
    return page.locator("[data-testid=toast]").last


# --- run 1 paths, redesigned ---------------------------------------------------

def test_node_and_inline_course_lifecycle(server, browser):
    page = page_as(browser, server, "editor")
    page.get_by_test_id("new-record").click()
    choose_type(page, "Module")
    page.get_by_test_id("create-name").fill("Week 1: Foundations")
    page.get_by_test_id("placement-picker").fill("Distributed Systems")
    page.get_by_test_id("placement-picker-create").filter(has_text="course").click()
    expect(page.get_by_test_id("placement-picker-picked")).to_contain_text("Distributed Systems")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Week 1: Foundations")
    expect(page.get_by_test_id("breadcrumb")).to_contain_text("Distributed Systems")
    page.get_by_test_id("panel-summary").click()
    page.get_by_test_id("edit-summary").fill("Consensus, replication, clocks")
    page.get_by_test_id("panel-name").click()
    expect(page.get_by_test_id("panel-summary")).to_have_text("Consensus, replication, clocks")
    expect(page.get_by_test_id("panel-version")).to_have_text("v2")
    page.goto(server + "#/courses")
    expect(page.get_by_test_id("row")).to_have_count(1)
    page.get_by_test_id("row").first.click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Distributed Systems")
    page.get_by_test_id("tab-relationships").click()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    expect(page.get_by_test_id("panel-relationships")).to_contain_text("Week 1: Foundations")
    more(page, "archive")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 relationship will be archived")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 record belong")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("delete it permanently later from Archived")
    page.get_by_test_id("confirm-ok").click()
    expect(toast(page)).to_contain_text("delete permanently later from Archived")
    more(page, "restore")
    expect(page.get_by_test_id("more-actions")).to_be_visible()
    page.get_by_test_id("tab-relationships").click()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    assert page.errors == []


def test_resource_lifecycle_and_reuse(server, browser):
    api = Client(USERS["editor"])
    _, a = api.post("/api/kb/nodes", {"type": "topic", "name": "Caching"})
    _, b = api.post("/api/kb/nodes", {"type": "topic", "name": "CDNs"})
    page = page_as(browser, server, "editor")
    open_record(page, server, a["id"])
    page.get_by_test_id("tab-links").click()
    page.get_by_test_id("attach").click()
    page.get_by_test_id("link-url").fill("https://example.com/caching-guide")
    page.get_by_test_id("link-title").fill("Caching guide")
    page.get_by_test_id("attach-submit").click()
    expect(page.get_by_test_id("panel-resources")).to_contain_text("Caching guide")
    open_record(page, server, b["id"])
    page.get_by_test_id("tab-links").click()
    page.get_by_test_id("attach").click()
    page.get_by_test_id("link-url").fill("https://example.com/caching-guide/")
    page.get_by_test_id("use-existing").click()
    page.get_by_test_id("attach-submit").click()
    expect(page.get_by_test_id("panel-resources")).to_contain_text("Caching guide")
    page.goto(server + "#/resources")
    page.get_by_test_id("res-row").first.click()
    expect(page.get_by_test_id("res-used-by")).to_contain_text("Caching")
    expect(page.get_by_test_id("res-used-by")).to_contain_text("CDNs")
    page.get_by_test_id("res-edit").click()
    page.get_by_test_id("res-edit-title").fill("Caching guide (2026)")
    page.get_by_test_id("res-edit-save").click()
    expect(page.get_by_test_id("res-title")).to_have_text("Caching guide (2026)")
    page.get_by_test_id("new-resource").click()
    page.get_by_test_id("res-url").fill("https://EXAMPLE.com/caching-guide/")
    page.get_by_test_id("res-title").last.fill("dupe")
    page.get_by_test_id("res-submit").click()
    expect(page.locator("[role=dialog]").last).to_contain_text("already in the library")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="More actions").click()
    page.get_by_test_id("res-archive").click()
    page.get_by_test_id("confirm-ok").click()
    expect(toast(page)).to_contain_text("Archived")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{a['id']}")[1]["resources"] == []
    page.get_by_role("button", name="More actions").click()
    page.get_by_test_id("res-restore").click()
    expect(page.get_by_text("Archived ", exact=False).first).to_be_visible()
    eventually(lambda: len(Client(USERS["viewer"]).get(f"/api/kb/nodes/{b['id']}")[1]["resources"]) == 1,
               what="the restored link")
    assert page.errors == []


def test_edge_lifecycle_from_the_graph(server, browser):
    api = Client(USERS["editor"])
    _, course = api.post("/api/kb/courses", {"name": "Graph Course"})
    _, mod = api.post("/api/kb/nodes", {"type": "module", "name": "Graph Module", "parents": [course["id"]]})
    _, topic = api.post("/api/kb/nodes", {"type": "topic", "name": "Graph Topic"})
    page = page_as(browser, server, "editor")
    page.goto(server + f"#/graph/{course['id']}")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 2 record(s)")
    page.evaluate(f"window.__kbGraph.expand('{mod['id']}')")
    page.get_by_test_id("graph-connect").click()
    pos = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy; cy.add({{group:'nodes', data:{{id:'{topic['id']}', label:'Graph Topic', type:'topic', color:'#4d7c0f', degree:0, shape:'ellipse'}}}});
        cy.layout({{name:'grid', fit:true, padding:40}}).run();
        const r = document.getElementById('cy').getBoundingClientRect();
        const p = id => {{ const q = cy.getElementById(id).renderedPosition(); return [r.left + q.x, r.top + q.y]; }};
        return [p('{mod['id']}'), p('{topic['id']}')]; }}""")
    page.mouse.click(*pos[0])
    page.mouse.click(*pos[1])
    page.get_by_test_id("graph-rel").click()
    page.get_by_test_id("graph-rel-option").filter(has_text="covers").first.click()
    page.get_by_test_id("connect-submit").click()
    expect(toast(page)).to_contain_text("Connected")
    edges = Client(USERS["viewer"]).get("/api/kb/edges", f"node={topic['id']}")[1]["items"]
    assert len(edges) == 1 and edges[0]["source_id"] == mod["id"]
    open_record(page, server, mod["id"])
    page.get_by_test_id("tab-relationships").click()
    expect(page.get_by_test_id("rel")).to_have_count(2)
    page.get_by_test_id("rel").filter(has_text="Graph Topic").get_by_role("button", name="Remove relationship").click()
    expect(page.get_by_test_id("rel")).to_have_count(1)
    toast(page).get_by_test_id("toast-undo").click()                  # undo restores it
    page.get_by_test_id("tab-relationships").click()
    expect(page.get_by_test_id("rel")).to_have_count(2)
    assert page.errors == []


def test_graph_expand_details_and_type_filter(server, browser):
    api = Client(USERS["admin"])
    _, c = api.post("/api/kb/courses", {"name": "Hub Course"})
    mods = [api.post("/api/kb/nodes", {"type": "module", "name": f"M{i}", "parents": [c["id"]]})[1] for i in range(3)]
    _, t = api.post("/api/kb/nodes", {"type": "topic", "name": "Deep Topic", "parents": [mods[0]["id"]]})
    page = page_as(browser, server, "viewer")
    page.goto(server + f"#/graph/{c['id']}")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 4 record(s)")
    expect(page.get_by_test_id("minimap")).to_be_visible()
    page.evaluate(f"window.__kbGraph.expand('{mods[0]['id']}')")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 5 record(s)")
    # centre the node first so the minimap (bottom-right) cannot be on top of it
    pos = page.evaluate(f"""() => {{ const cy = window.__kbGraph.cy, r = document.getElementById('cy').getBoundingClientRect();
        cy.center(cy.getElementById('{t['id']}'));
        const q = cy.getElementById('{t['id']}').renderedPosition(); return [r.left + q.x, r.top + q.y]; }}""")
    page.mouse.click(*pos)
    expect(page.get_by_test_id("panel-name")).to_have_text("Deep Topic")
    assert "#/graph/" in page.url
    page.get_by_test_id("graph-filter-module").uncheck()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 2 record(s)")
    page.get_by_test_id("graph-filter-module").check()
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 5 record(s)")
    expect(page.get_by_test_id("graph-connect")).to_have_count(0)
    assert page.errors == []


def test_search_palette_and_list_filters(server, browser):
    api = Client(USERS["editor"])
    _, c = api.post("/api/kb/courses", {"name": "Algorithms"})
    api.post("/api/kb/nodes", {"type": "topic", "name": "Dynamic Programming", "summary": "tabulation"})
    api.post("/api/kb/nodes", {"type": "module", "name": "Sorting week", "parents": [c["id"]]})
    page = page_as(browser, server, "editor")
    page.keyboard.press("Control+k")
    page.get_by_test_id("palette-input").fill("tabulation")
    expect(page.get_by_test_id("palette-node")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("panel-name")).to_have_text("Dynamic Programming")
    page.keyboard.press("Escape")
    page.keyboard.press("Control+k")
    page.get_by_test_id("palette-input").fill("Greedy Algorithms")
    page.get_by_test_id("palette-create-topic").click()
    expect(page.get_by_test_id("create-name")).to_have_value("Greedy Algorithms")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Greedy Algorithms")
    page.goto(server + "#/records")
    expect(page.get_by_test_id("row")).to_have_count(4)
    page.get_by_test_id("filter-button").click()
    page.get_by_test_id("filter-type-topic").click()
    expect(page.get_by_test_id("row")).to_have_count(2)
    expect(page.get_by_test_id("chip-type")).to_contain_text("Topic")
    page.get_by_test_id("chip-type").get_by_role("button").click()
    expect(page.get_by_test_id("row")).to_have_count(4)
    page.goto(server + f"#/records?parent={c['id']}")
    expect(page.get_by_test_id("row")).to_have_count(1)
    expect(page.get_by_test_id("row")).to_contain_text("Sorting week")
    page.goto(server + "#/records")
    page.get_by_test_id("filter-q").fill("dynamic")
    expect(page.get_by_test_id("row")).to_have_count(1)
    page.get_by_test_id("filter-q").fill("zzz-nothing")
    expect(page.get_by_test_id("empty")).to_contain_text("Nothing matches")
    assert page.errors == []


def test_two_sessions_conflict_dialog(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Contested"})
    # Run 6 (B1): a contributor's field edit is a proposal (0033), never a conflict;
    # the two writers are an admin and an editor (tests/test_kb_propagation.py covers the contributor).
    a = page_as(browser, server, "admin")
    b = page_as(browser, server, "editor")
    open_record(a, server, n["id"])
    open_record(b, server, n["id"])
    a.get_by_test_id("panel-summary").click()                       # A starts editing first
    b.get_by_test_id("panel-summary").click()
    b.get_by_test_id("edit-summary").fill("Editor's version")
    b.get_by_test_id("panel-name").click()
    expect(b.get_by_test_id("panel-version")).to_have_text("v2")
    a.get_by_test_id("edit-summary").fill("Admin's first version")
    a.get_by_test_id("panel-name").click()
    expect(a.get_by_test_id("conflict-dialog")).to_be_visible()
    expect(a.get_by_test_id("conflict-diff")).to_contain_text("Admin's first version")
    expect(a.get_by_test_id("conflict-diff")).to_contain_text("Editor's version")
    expect(a.get_by_test_id("conflict-overwrite")).to_be_visible()          # editors and admins may overwrite
    a.get_by_test_id("conflict-reload").click()
    expect(a.get_by_test_id("panel-summary")).to_have_text("Editor's version")
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
    page.get_by_test_id("more-actions").click()
    if role == "viewer":
        expect(page.get_by_test_id("archive")).to_have_count(0)
        expect(page.get_by_test_id("flag")).to_be_visible()                 # viewers can still flag
        page.keyboard.press("Escape")
        expect(page.get_by_test_id("edit-record")).to_have_count(0)
        page.get_by_test_id("tab-relationships").click()
        expect(page.get_by_test_id("connect")).to_have_count(0)
        assert page.get_by_test_id("panel-name").get_attribute("contenteditable") is None
    elif role == "contributor":
        expect(page.get_by_test_id("archive")).to_have_text("Propose archive")
        page.get_by_test_id("archive").click()
        page.get_by_test_id("confirm-reason").fill("superseded")
        page.get_by_test_id("confirm-ok").click()
        expect(toast(page)).to_contain_text("Sent for approval")
        page.goto(server + "#/approvals")
        expect(page.get_by_test_id("proposal")).to_have_count(1)
        expect(page.get_by_test_id("approve")).to_have_count(0)
    else:
        expect(page.get_by_test_id("archive")).to_have_text("Archive")
        page.keyboard.press("Escape")
        page.goto(server + "#/settings?tab=tokens")
        expect(page.get_by_test_id("tokens")).to_be_visible()
        expect(page.get_by_test_id("settings-tab-members")).to_have_count(1 if role == "admin" else 0)
    page.goto(server + "#/records")
    expect(page.get_by_test_id("new-record")).to_have_count(0 if role == "viewer" else 1)
    assert page.errors == []


def test_approving_a_proposal_in_the_ui(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Obsolete"})
    Client(USERS["contributor"]).post(f"/api/kb/nodes/{n['id']}/archive", {"reason": "old"})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/approvals")
    page.get_by_test_id("approve").click()
    expect(page.get_by_test_id("empty")).to_contain_text("Nothing waiting")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{n['id']}")[1]["archived_at"]


def test_tablet_width_layout_and_tokens(server, browser):
    page = page_as(browser, server, "viewer", viewport=(820, 1100))
    page.goto(server + "#/settings?tab=tokens")
    page.get_by_test_id("token-name").fill("tablet")
    page.get_by_test_id("token-create").click()
    expect(page.get_by_test_id("token-value")).to_have_value(re.compile(r"^ikkb_"))
    expect(page.get_by_test_id("token-row")).to_have_count(1)
    page.get_by_test_id("token-revoke").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("token-row")).to_contain_text("revoked")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_quality_dashboard_and_csv_export(server, browser):
    api = Client(USERS["editor"])
    _, c = api.post("/api/kb/courses", {"name": "Quality, \"Course\""})
    api.post("/api/kb/nodes", {"type": "module", "name": "Unresourced", "parents": [c["id"]], "owner_id": None})
    api.post("/api/kb/nodes", {"type": "topic", "name": "=HYPERLINK(\"x\")"})
    page = page_as(browser, server, "viewer")
    page.goto(server + "#/quality")
    expect(page.get_by_test_id("q-unowned")).to_contain_text("Unresourced")
    expect(page.get_by_test_id("q-course")).to_contain_text("Quality")
    page.goto(server + "#/")
    expect(page.get_by_test_id("dash-attention")).to_contain_text("Unresourced")
    page.goto(server + "#/records")
    with page.expect_download() as d:
        page.get_by_test_id("export-csv").click()
    text = Path(d.value.path()).read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith('"id","type","name"')
    assert '"Quality, ""Course"""' in text and "Unresourced" in text
    assert "\"'=HYPERLINK" in text                                  # formulas neutralised
    assert page.errors == []


# --- run 2 paths -----------------------------------------------------------------

def test_custom_type_case_study_end_to_end(server, browser):
    page = page_as(browser, server, "admin")
    page.goto(server + "#/settings?tab=types")
    page.get_by_test_id("new-type").click()
    page.get_by_test_id("type-label").fill("Case Study")
    page.get_by_test_id("add-field").click()
    page.get_by_test_id("field-label").last.fill("Difficulty")
    page.get_by_test_id("field-kind").last.select_option("single_select")
    page.get_by_test_id("field-options").last.fill("Easy, Medium, Hard")
    page.get_by_test_id("field-required").last.check()
    page.get_by_test_id("add-field").click()
    page.get_by_test_id("field-label").last.fill("Minutes")
    page.get_by_test_id("field-kind").last.select_option("number")
    expect(page.get_by_test_id("type-preview")).to_contain_text("Difficulty")
    page.get_by_test_id("type-parents").get_by_label("Module", exact=True).check()
    page.get_by_test_id("type-save").click()
    expect(toast(page)).to_contain_text("Case Study")
    expect(page.get_by_test_id("types")).to_contain_text("Case Study")
    _, mod = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "module", "name": "Pricing"})
    # create one through the form, placed in the module, with its fields
    page.get_by_test_id("new-record").click()
    choose_type(page, "Case Study")
    page.get_by_test_id("create-name").fill("Surge pricing")
    page.get_by_test_id("field-input-difficulty").select_option("hard")
    pick(page, "placement-picker", "Pricing")
    page.get_by_test_id("section-fields").locator("summary").click()
    page.get_by_test_id("field-input-minutes").fill("45")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Surge pricing")
    expect(page.get_by_test_id("field-difficulty")).to_be_visible()
    # table filter + column, palette, graph, CSV
    page.goto(server + "#/records")
    page.get_by_test_id("filter-button").click()
    page.get_by_test_id("filter-type-case_study").click()
    expect(page.get_by_test_id("row")).to_have_count(1)
    page.keyboard.press("Control+k")
    page.get_by_test_id("palette-input").fill("Surge")
    expect(page.get_by_test_id("palette-node")).to_contain_text("Case Study")
    page.keyboard.press("Escape")
    with page.expect_download() as d:
        page.get_by_test_id("export-csv").click()
    text = Path(d.value.path()).read_text(encoding="utf-8-sig")
    assert '"field:difficulty"' in text.splitlines()[0] and '"hard"' in text and '"45"' in text
    node = [n for n in Client(USERS["viewer"]).get("/api/kb/nodes", "type=case_study")[1]["items"]][0]
    page.goto(server + f"#/graph/{node['id']}")
    expect(page.get_by_test_id("graph-legend")).to_contain_text("Case")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing 2 record(s)")
    assert page.errors == []


def test_one_save_with_nested_inline_course_relationships_and_links(server, browser):
    api = Client(USERS["editor"])
    _, prog = api.post("/api/kb/programs", {"name": "Backend Track"})
    _, mentor = api.post("/api/kb/nodes", {"type": "instructor", "name": "Ada Example"})
    _, lib = api.post("/api/kb/resources", {"url": "https://github.com/ik-demo/rate-limiter", "title": "Rate limiter repo"})
    page = page_as(browser, server, "editor")
    page.get_by_test_id("new-record").click()
    choose_type(page, "Module")
    page.get_by_test_id("create-name").fill("Scalability")
    # placement: a NEW course, itself placed in the existing program
    page.get_by_test_id("placement-picker").fill("System Design II")
    page.get_by_test_id("placement-picker-create").filter(has_text="course").click()
    pick(page, "placement-nested-picker", "Backend Track")
    # two relationships: covers a NEW topic, taught by an existing instructor
    page.get_by_test_id("section-relationships").locator("summary").click()
    page.get_by_test_id("add-relationship").click()
    choose_rel(page, "^This module covers a topic")
    page.get_by_test_id("rel-target").last.fill("Rate limiting")
    page.get_by_test_id("rel-target-create").last.click()
    expect(page.get_by_test_id("rel-sentence").last).to_contain_text("“Scalability” covers “Rate limiting”")
    page.get_by_test_id("add-relationship").click()
    choose_rel(page, "^An instructor teaches this module")
    pick(page, "rel-target", "Ada Example")
    # three links: Drive, UpLevel, GitHub (reused from the library)
    for url, title in (("https://drive.google.com/file/d/abc123/view", "Deck"),
                       ("https://uplevel.interviewkickstart.com/update_video/75226/", "Recording")):
        page.get_by_test_id("add-link").click()
        page.get_by_test_id("link-url").last.fill(url)
        page.get_by_test_id("link-title").last.fill(title)
    page.get_by_test_id("add-link").click()
    page.get_by_test_id("link-url").last.fill("https://github.com/ik-demo/rate-limiter")
    page.get_by_test_id("use-existing").click()
    page.get_by_test_id("link-purpose").last.fill("Starter code")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Scalability")
    expect(page.get_by_test_id("breadcrumb")).to_contain_text("Backend Track")
    expect(page.get_by_test_id("breadcrumb")).to_contain_text("System Design II")
    expect(toast(page)).to_contain_text("new record")
    n = Client(USERS["viewer"]).get("/api/kb/nodes", "q=Scalability")[1]["items"][0]
    full = Client(USERS["viewer"]).get(f"/api/kb/nodes/{n['id']}")[1]
    assert {r["link_kind"] for r in full["resources"]} == {"drive_file", "uplevel", "github"}
    assert [r for r in full["resources"] if r["id"] == lib["id"]][0]["note"] == "Starter code"
    assert {e["node_name"] for e in full["outgoing"]} == {"Rate limiting"}
    assert {e["node_name"] for e in full["incoming"]} >= {"Ada Example", "System Design II"}
    assert len(Client(USERS["viewer"]).get("/api/kb/resources", "q=rate-limiter")[1]["items"]) == 1   # reused, not duplicated
    assert page.errors == []


def test_failed_save_rolls_back_and_highlights_the_field(server, browser):
    Client(USERS["admin"]).post("/api/kb/types/node", {"label": "Case Study", "fields": [
        {"label": "Difficulty", "kind": "single_select", "required": True, "options": ["easy", "hard"]}]})
    page = page_as(browser, server, "editor")
    page.get_by_test_id("new-record").click()
    choose_type(page, "Case Study")
    page.get_by_test_id("create-name").fill("Incomplete case")
    page.get_by_test_id("add-link").click()
    page.get_by_test_id("link-url").last.fill("https://example.com/brief")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("form-error")).to_contain_text("Difficulty is required")
    expect(page.locator("[data-field='props.difficulty'].invalid")).to_be_visible()
    assert Client(USERS["viewer"]).get("/api/kb/nodes", "status=all")[1]["items"] == []
    assert Client(USERS["viewer"]).get("/api/kb/resources")[1]["items"] == []           # nothing partial
    page.get_by_test_id("field-input-difficulty").select_option("easy")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Incomplete case")
    assert page.errors == []


def test_duplicate_name_warning_while_typing(server, browser):
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Dynamic Programming"})
    page = page_as(browser, server, "editor")
    page.get_by_test_id("new-record").click()
    choose_type(page, "Topic")
    page.get_by_test_id("create-name").fill("dynamic   programming")
    expect(page.get_by_test_id("dup-warning")).to_contain_text("already exists")
    page.get_by_test_id("open-existing").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Dynamic Programming")
    assert page.errors == []


def test_disallowed_relationships_are_not_offered_and_duplicates_blocked(server, browser):
    api = Client(USERS["editor"])
    _, t1 = api.post("/api/kb/nodes", {"type": "topic", "name": "Heaps"})
    _, t2 = api.post("/api/kb/nodes", {"type": "topic", "name": "Priority queues"})
    page = page_as(browser, server, "editor")
    open_record(page, server, t1["id"])
    page.get_by_test_id("tab-relationships").click()
    page.get_by_test_id("connect").click()
    options = rel_options(page)
    assert options and not any("This topic teaches" in o for o in options)   # a topic cannot teach
    assert not any("←" in o or "→" in o for o in options)                    # plain sentences (A7)
    page.keyboard.press("Escape")
    choose_rel(page, "^This topic is related to a topic")
    pick(page, "rel-target", "Priority queues")
    page.get_by_test_id("connect-submit").click()
    expect(toast(page)).to_contain_text("Connected")
    page.get_by_test_id("connect").click()
    choose_rel(page, "^This topic is related to a topic")
    pick(page, "rel-target", "Priority queues")
    page.get_by_test_id("connect-submit").click()
    expect(page.get_by_test_id("connect-error")).to_contain_text("already connected")
    assert page.errors == []


def test_contributor_create_is_a_proposal_an_editor_approves(server, browser):
    page = page_as(browser, server, "contributor")
    page.get_by_test_id("new-record").click()
    expect(page.get_by_test_id("proposal-note")).to_contain_text("sent to an editor for approval")
    choose_type(page, "Topic")
    page.get_by_test_id("create-name").fill("Bloom filters")
    expect(page.get_by_test_id("create-submit")).to_contain_text("Send for approval")
    page.get_by_test_id("create-submit").click()
    expect(toast(page)).to_contain_text("sent for approval")
    assert Client(USERS["viewer"]).get("/api/kb/nodes")[1]["items"] == []
    ed = page_as(browser, server, "editor")
    ed.goto(server + "#/approvals")
    expect(ed.get_by_test_id("proposal")).to_contain_text("Bloom filters")
    ed.get_by_test_id("approve").click()
    expect(ed.get_by_test_id("empty")).to_contain_text("Nothing waiting")
    assert [n["name"] for n in Client(USERS["viewer"]).get("/api/kb/nodes")[1]["items"]] == ["Bloom filters"]
    assert page.errors == [] and ed.errors == []


def test_archive_then_permanent_delete_from_archived(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Short-lived",
                                                           "resources": [{"url": "https://example.com/s", "title": "s"}]})
    page = page_as(browser, server, "admin")
    open_record(page, server, n["id"])
    more(page, "archive")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 link will be archived")
    page.get_by_test_id("confirm-ok").click()
    page.goto(server + "#/archived")
    expect(page.get_by_test_id("archived-row")).to_contain_text("Short-lived")
    page.get_by_test_id("archived-delete").click()
    expect(page.get_by_test_id("confirm-ok")).to_be_disabled()
    page.get_by_test_id("confirm-type").fill("Short-lived")
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("empty")).to_contain_text("Nothing archived")
    assert Client(USERS["admin"]).get(f"/api/kb/nodes/{n['id']}")[0] == 404
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log where row_id = %s and action = 'delete'", (n["id"],)).fetchone()[0] == 1
    assert page.errors == []


def test_keyboard_only_main_flows(server, browser):
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Tries"})
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Graphs"})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/records")
    expect(page.get_by_test_id("row")).to_have_count(2)
    page.locator("body").click(position={"x": 700, "y": 600})
    page.keyboard.press("j")
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("panel-name")).to_be_visible()
    page.keyboard.press("Escape")
    page.keyboard.press("c")                                             # new record from the keyboard
    expect(page.get_by_test_id("create-name")).to_be_focused()
    page.keyboard.type("Suffix arrays")
    page.keyboard.press("Control+Enter")
    expect(page.get_by_test_id("panel-name")).to_have_text("Suffix arrays")
    page.keyboard.press("Control+k")
    page.keyboard.type("Tries")
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("panel-name")).to_have_text("Tries")
    assert page.errors == []


@pytest.mark.parametrize("route", ["#/", "#/records", "#/outline", "#/graph", "#/quality", "#/approvals", "#/activity", "#/archived", "#/settings", "#/guide", "#/resources"])
def test_no_horizontal_scroll_at_1024(server, browser, route):
    Client(USERS["editor"]).post("/api/kb/courses", {"name": "A course with a rather long name for layout testing"})
    page = page_as(browser, server, "admin", viewport=(1024, 768))
    page.goto(server + route)
    settled(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
    assert page.errors == []


# --- phase D screens -------------------------------------------------------------

def test_outline_quick_add_reorder_and_copy(server, browser):
    api = Client(USERS["editor"])
    _, prog = api.post("/api/kb/programs", {"name": "Outline Program"})
    _, c = api.post("/api/kb/nodes", {"type": "course", "name": "Outline Course", "parents": [prog["id"]]})
    api.post("/api/kb/nodes", {"type": "module", "name": "Alpha", "parents": [c["id"]]})
    api.post("/api/kb/nodes", {"type": "module", "name": "Beta", "parents": [c["id"]]})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/outline")
    expect(page.get_by_test_id("outline-row").first).to_be_visible()
    page.get_by_test_id("outline-expand").click()
    rows = page.get_by_test_id("outline-row")
    expect(rows.filter(has_text="Alpha")).to_be_visible()
    names = lambda: [t.strip() for t in page.locator("[data-testid=outline-row] a.name").all_text_contents()]  # noqa: E731
    assert names().index("Alpha") < names().index("Beta")
    rows.filter(has_text="Beta").drag_to(rows.filter(has_text="Alpha"), target_position={"x": 40, "y": 4})
    expect(toast(page)).to_contain_text("Order saved")
    eventually(lambda: names().index("Beta") < names().index("Alpha"), what="the saved order")
    rows.filter(has_text="Outline Course").hover()
    rows.filter(has_text="Outline Course").get_by_test_id("outline-add").click()
    page.get_by_test_id("outline-add-module").click()
    expect(page.get_by_test_id("placement-picker-picked")).to_contain_text("Outline Course")
    page.get_by_test_id("create-name").fill("Gamma")
    page.get_by_test_id("create-submit").click()
    expect(rows.filter(has_text="Gamma")).to_be_visible()
    assert page.errors == []


def test_flag_as_incorrect_reaches_the_owner_in_reviews(server, browser):
    _, n = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Questionable"})
    viewer = page_as(browser, server, "viewer")
    open_record(viewer, server, n["id"])
    more(viewer, "flag")
    viewer.get_by_test_id("flag-reason").fill("The recording link is from the 2024 cohort")
    viewer.get_by_test_id("flag-submit").click()
    expect(viewer.get_by_test_id("flag-banner")).to_contain_text("2024 cohort")
    owner_page = page_as(browser, server, "editor")
    owner_page.goto(server + "#/records?flagged=1")
    expect(owner_page.get_by_test_id("row")).to_have_count(1)
    owner_page.goto(server + "#/approvals?tab=reviews")
    expect(owner_page.get_by_test_id("review")).to_contain_text("Assigned to you")
    owner_page.get_by_test_id("flag-resolve").click()
    owner_page.get_by_test_id("flag-resolution").fill("Replaced with the 2026 recording")
    owner_page.get_by_test_id("flag-close").click()
    expect(owner_page.get_by_test_id("empty")).to_contain_text("No open reviews")
    assert viewer.errors == [] and owner_page.errors == []


def test_save_course_as_template_and_create_from_it(server, browser):
    api = Client(USERS["editor"])
    _, c = api.post("/api/kb/courses", {"name": "Python Basics"})
    m = api.post("/api/kb/nodes", {"type": "module", "name": "Python Basics: Syntax", "parents": [c["id"]]})[1]
    api.post("/api/kb/nodes", {"type": "week", "name": "Week 1", "parents": [m["id"]]})
    page = page_as(browser, server, "editor")
    open_record(page, server, c["id"])
    more(page, "save-template")
    page.get_by_test_id("template-save").click()
    expect(toast(page)).to_contain_text("Template saved")
    page.get_by_test_id("new-record").click()
    choose_type(page, "Course")
    page.get_by_test_id("create-name").fill("Go Basics")
    page.get_by_test_id("template-select").select_option(label="Python Basics template (course)")
    page.get_by_test_id("create-submit").click()
    expect(toast(page)).to_contain_text("from the template (3 records)")
    names = {n["name"] for n in Client(USERS["viewer"]).get("/api/kb/nodes", "limit=50")[1]["items"]}
    assert {"Go Basics", "Go Basics: Syntax"} <= names
    assert page.errors == []


def test_saved_view_shared_with_the_team_and_bulk_owner(server, browser):
    api = Client(USERS["editor"])
    for i in range(3):
        api.post("/api/kb/nodes", {"type": "topic", "name": f"Bulk {i}", "owner_id": None})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/records?owner=none")
    expect(page.get_by_test_id("row")).to_have_count(3)
    page.get_by_test_id("save-view").click()
    page.get_by_test_id("view-name").fill("Needs an owner")
    page.get_by_test_id("view-shared").check()
    page.get_by_test_id("view-save").click()
    expect(page.get_by_test_id("view-tab")).to_contain_text("Needs an owner")
    page.get_by_test_id("select-all").check()
    expect(page.get_by_test_id("bulk-bar")).to_contain_text("3 records selected")
    page.get_by_test_id("bulk-owner").click()
    page.get_by_test_id("bulk-owner-option").first.click()
    expect(toast(page)).to_contain_text("Updated 3 records")
    expect(page.get_by_test_id("empty")).to_be_visible()
    other = page_as(browser, server, "contributor")
    other.goto(server + "#/records")
    expect(other.get_by_test_id("view-tab")).to_contain_text("Needs an owner")    # shared
    assert page.errors == [] and other.errors == []


def test_guide_promises_undo_after_create_draft_restore_and_theme(server, browser):
    page = page_as(browser, server, "editor")
    # Undo straight after creating archives the new record
    page.get_by_test_id("new-record").click()
    choose_type(page, "Topic")
    page.get_by_test_id("create-name").fill("Undo me")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("Undo me")
    page.get_by_test_id("toast-undo").click()
    expect(toast(page)).to_contain_text("Undone")
    assert Client(USERS["viewer"]).get("/api/kb/nodes", "q=Undo")[1]["items"] == []
    # closing a dirty form asks first; the draft is offered next time
    page.keyboard.press("Escape")
    page.get_by_test_id("new-record").click()
    page.get_by_test_id("create-name").fill("Half-written idea")
    # the draft autosave is debounced: wait for the draft itself, not for a guess at the delay
    page.wait_for_function("() => (JSON.parse(localStorage.getItem('kb_draft_new_record') || 'null') || {}).name"
                           " === 'Half-written idea'")
    page.get_by_test_id("sheet-close").click()
    expect(page.get_by_test_id("confirm-dialog")).to_contain_text("Discard this draft?")
    page.get_by_test_id("confirm-ok").click()
    page.get_by_test_id("new-record").click()
    expect(page.get_by_test_id("draft-restore")).to_be_visible()
    page.get_by_test_id("draft-restore").get_by_role("button", name="Restore").click()
    expect(page.get_by_test_id("create-name")).to_have_value("Half-written idea")
    page.get_by_test_id("sheet-close").click()
    page.get_by_test_id("confirm-ok").click()
    # theme toggle
    page.get_by_test_id("whoami").click()
    page.get_by_test_id("theme-dark").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.errors == []


def test_new_record_prefills_from_the_open_record_and_shows_custom_columns(server, browser):
    _, c = Client(USERS["editor"]).post("/api/kb/courses", {"name": "Context Course"})
    page = page_as(browser, server, "editor")
    open_record(page, server, c["id"])
    page.locator("body").click(position={"x": 700, "y": 700})
    page.keyboard.press("c")
    expect(page.get_by_test_id("placement-picker-picked")).to_contain_text("Context Course")
    page.get_by_test_id("create-name").fill("From context")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("breadcrumb")).to_contain_text("Context Course")
    # a list of one custom type shows its fields as columns
    Client(USERS["admin"]).post("/api/kb/types/node", {"label": "Case Study", "fields": [
        {"label": "Difficulty", "kind": "single_select", "options": ["easy", "hard"]}]})
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "case_study", "name": "Columned", "props": {"difficulty": "hard"}})
    page.goto(server + "#/records?type=case_study")
    page.reload()
    expect(page.get_by_test_id("th-field-difficulty")).to_be_visible()
    expect(page.get_by_test_id("row")).to_contain_text("hard")
    assert page.errors == []


A11Y_SCRIPT = """() => {
  const name = (e) => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || e.value || '').trim()
    || (e.id && document.querySelector('label[for="' + e.id + '"]') ? 'label' : '') || (e.closest('label') ? 'label' : '')
    || (e.getAttribute('placeholder') || '').trim();
  const bad = [];
  document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=tab]').forEach((e) => {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) return;
    if (!name(e)) bad.push(e.tagName + '.' + (e.className || '') + ' ' + (e.getAttribute('data-testid') || ''));
  });
  return bad;
}"""


@pytest.mark.parametrize("route", ["#/", "#/records", "#/outline", "#/quality", "#/approvals", "#/activity", "#/archived", "#/settings", "#/resources", "#/graph"])
def test_every_control_has_an_accessible_name(server, browser, route):
    api = Client(USERS["editor"])
    _, c = api.post("/api/kb/courses", {"name": "A11y Course"})
    api.post("/api/kb/nodes", {"type": "module", "name": "A11y Module", "parents": [c["id"]],
                               "resources": [{"url": "https://example.com/a11y", "title": "A11y link"}]})
    page = page_as(browser, server, "admin")
    page.goto(server + route + ("" if "?" in route else f"?open={c['id']}"))
    settled(page)
    assert page.evaluate(A11Y_SCRIPT) == [], route
    page.get_by_test_id("new-record").click()
    expect(page.get_by_test_id("create-name")).to_be_visible()
    settled(page)
    assert page.evaluate(A11Y_SCRIPT) == [], route + " + New record sheet"


# --- run 3: owner bugs (phase A) -------------------------------------------------

def _records_with_issues():
    ed = Client(USERS["editor"])
    # Run 6: "No owner" counts types whose "owner expected" is ON (modules), not topics.
    _, a = ed.post("/api/kb/nodes", {"type": "module", "name": "Unowned module", "owner_id": None})
    _, b = ed.post("/api/kb/nodes", {"type": "topic", "name": "Lonely topic"})
    _, r = ed.post("/api/kb/resources", {"url": "https://github.com/ik-demo/broken", "title": "Broken repo", "kind": "repo"})
    with owner() as c:
        c.execute("insert into kb.link_checks (resource_id, status, http_status, checked_at) values (%s, 'broken', 404, now())", (r["id"],))
    return a, b


def test_a1_attention_tile_list_and_sidebar_agree(server, browser):
    _records_with_issues()
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    tile = page.get_by_test_id("dash-attention-total").locator(".v")
    expect(tile).to_have_text("4")                             # no owner 1 + broken 1 + not connected 2
    counts = [int(x) for x in page.get_by_test_id("attention-count").all_text_contents()]
    assert sum(counts) == 4
    expect(page.locator("[data-count=attention]")).to_have_text("4")
    page.get_by_role("link", name="Data quality").click()
    expect(page.get_by_test_id("q-total").locator(".v")).to_have_text("4")
    assert page.errors == []


def test_a2_activity_names_every_actor(server, browser):
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "By a person"})
    with owner() as c:
        tid = c.execute("select id from kb.node_types where key = 'topic'").fetchone()[0]
        c.execute("insert into kb.nodes (type_id, name) values (%s, 'By the system')", (tid,))
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    actors = page.get_by_test_id("activity").get_by_test_id("activity-actor")
    expect(actors.first).to_be_visible()
    names = actors.all_text_contents()
    assert "System" in names and all(n and n != "Someone" for n in names), names
    assert page.errors == []


def test_a3_demo_badge_has_its_own_sidebar_slot(server, browser):
    # The demo server injects the badge with the slot id the app looks for ...
    import urllib.request
    with dev_server("kb_demo_server.py") as base:
        html = urllib.request.urlopen(base + "/kb/", timeout=10).read().decode()
        css = urllib.request.urlopen(base + "/local-demo.css", timeout=10).read().decode()
    assert 'id="demo-badge-slot"' in html and ".sidebar-slot .demo-ribbon" in css
    # ... and the app moves it into its own slot above the user menu, clear of the links.
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    page.add_init_script("document.addEventListener('readystatechange', () => document.readyState === 'interactive' && document.body.insertAdjacentHTML('afterbegin', "
                         "'<div class=\"demo-ribbon\" id=\"demo-badge-slot\" data-testid=\"demo-badge\">Local demo · fictional data</div>'))")
    page.reload()
    badge = page.locator("#sidebar-slot [data-testid=demo-badge]")
    expect(badge).to_be_visible()
    b, user = badge.bounding_box(), page.get_by_test_id("whoami").bounding_box()
    last = page.locator(".sidebar-foot > a").last.bounding_box()
    assert last["y"] + last["height"] <= b["y"] and b["y"] + b["height"] <= user["y"]     # between the links and the user menu
    assert page.errors == []


def test_a4_view_popover_stays_in_the_viewport_with_labelled_controls(server, browser):
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Columns"})
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    page.goto(server + "#/records")
    page.get_by_test_id("view-options").click()
    pop = page.get_by_test_id("view-popover")
    expect(pop).to_be_visible()
    box = pop.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 1536 and box["y"] + box["height"] <= 900
    expect(page.get_by_role("radiogroup", name="Row density")).to_be_visible()
    lab = page.get_by_test_id("col-row-owner").locator("label")
    gap = page.evaluate("(l) => { const c = l.querySelector('input').getBoundingClientRect(), t = l.querySelector('span').getBoundingClientRect(); return t.left - c.right; }", lab.element_handle())
    assert gap >= 8                                                     # the ✓ is not glued to the label
    page.get_by_test_id("col-owner").uncheck()
    expect(page.get_by_test_id("th-owner")).to_have_count(0)
    page.get_by_role("button", name="Move Updated up").click()
    heads = page.locator("[data-testid=records-table] th").all_text_contents()
    assert heads.index("Updated") < heads.index("Links")
    page.get_by_test_id("density-compact").click()
    expect(page.locator(".table-wrap.compact")).to_have_count(1)
    assert page.evaluate("[...document.querySelectorAll('.tabs')].every((t) => t.scrollHeight <= t.clientHeight + 1)")   # no stray scrollbar
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert page.errors == []


def test_a5_full_text_on_hover_two_line_description_and_resizable_columns(server, browser):
    long = "A very long description that keeps going well past the width of the column so that it would be cut off " * 3
    Client(USERS["editor"]).post("/api/kb/nodes", {"type": "topic", "name": "Long one", "summary": long.strip()})
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    page.goto(server + "#/records")
    cell = page.get_by_test_id("cell-name").first
    assert long.strip() in cell.get_attribute("title")
    clamp = page.evaluate("getComputedStyle(document.querySelector('[data-testid=cell-desc]')).webkitLineClamp")
    assert clamp == "2"
    th = page.get_by_test_id("th-scope")
    w0 = th.bounding_box()["width"]
    h = page.get_by_test_id("col-resize-scope").bounding_box()
    page.mouse.move(h["x"] + 3, h["y"] + h["height"] / 2)
    page.mouse.down(); page.mouse.move(h["x"] + 83, h["y"] + h["height"] / 2, steps=5); page.mouse.up()
    assert th.bounding_box()["width"] > w0 + 60
    page.reload()
    assert page.get_by_test_id("th-scope").bounding_box()["width"] > w0 + 60    # remembered
    assert page.errors == []


def test_a6_guide_is_centred_and_screenshots_enlarge(server, browser):
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    page.goto(server + "#/guide")
    doc, toc = page.get_by_test_id("guide").bounding_box(), page.locator(".guide-toc").bounding_box()
    view = page.locator("#view").bounding_box()
    left, right = doc["x"] - view["x"], view["x"] + view["width"] - (toc["x"] + toc["width"])
    assert abs(left - right) < 40, (left, right)                      # one centred unit
    assert 700 <= doc["width"] <= 800 and 180 <= toc["width"] <= 260
    page.get_by_test_id("guide-figure").first.click()
    expect(page.get_by_test_id("guide-lightbox")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("guide-lightbox")).to_have_count(0)
    assert page.errors == []


def test_a7_relationship_picker_reads_as_sentences_and_does_not_hide_the_record_input(server, browser):
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    page.get_by_test_id("new-record").click()
    choose_type(page, "Module")
    page.get_by_test_id("create-name").fill("Sentences")
    page.get_by_test_id("section-relationships").locator("summary").click()
    page.get_by_test_id("add-relationship").click()
    options = rel_options(page)
    assert options and not any(("←" in o or "→" in o) for o in options), options
    assert any(o.startswith("This module ") for o in options) and any(o.endswith(" this module") for o in options)
    labels = page.get_by_test_id("rel-type-menu").locator(".menu-label").all_text_contents()
    assert "This module …" in labels and "… this module" in labels
    menu, target = page.get_by_test_id("rel-type-menu").bounding_box(), page.get_by_test_id("rel-target-placeholder").bounding_box()
    assert menu["y"] >= target["y"] + target["height"] - 1             # the list opens below, never over the record input
    page.get_by_test_id("rel-type-option").filter(has_text="This module covers a topic").first.click()
    expect(page.get_by_test_id("rel-target")).to_be_visible()
    assert page.errors == []


# --- run 3: custom relationship types (B2) ------------------------------------------

def _connect_dialog(page, server, node_id):
    open_record(page, server, node_id)
    page.get_by_test_id("tab-relationships").click()
    page.get_by_test_id("connect").click()


@pytest.mark.parametrize("role", ["admin", "editor", "contributor"])
def test_b2_inline_relationship_creation_by_role(server, browser, role):
    _, inst = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "instructor", "name": "Asha Rao"})
    page = page_as(browser, server, role, viewport=(1536, 900))
    _connect_dialog(page, server, inst["id"])
    page.get_by_test_id("rel-type").last.fill("mentors")
    page.get_by_test_id("rel-type-create").click()
    expect(page.get_by_test_id("newrel-dialog")).to_be_visible()
    expect(page.get_by_test_id("newrel-inverse")).to_have_value("mentored by")      # suggested
    page.get_by_test_id("newrel-target").select_option("instructor")
    page.get_by_test_id("newrel-save").click()
    expect(page.get_by_test_id("newrel-dialog")).to_have_count(0)
    types = {t["key"]: t for t in Client(USERS["admin"]).get("/api/kb/types")[1]["edge_types"]}
    if role == "contributor":
        expect(toast(page)).to_contain_text("Proposed")
        assert "mentors" not in types
        props = Client(USERS["admin"]).get("/api/kb/proposals")[1]["items"]
        assert any((p["payload"] or {}).get("op") == "edge_create" for p in props)
    else:
        expect(toast(page)).to_contain_text("Created")
        expect(page.get_by_test_id("rel-type-picked").last).to_contain_text("mentors")
        assert types["mentors"]["review_status"] == ("reviewed" if role == "admin" else "unreviewed")
    if role == "editor":                                               # the admin confirms it in Approvals
        admin = page_as(browser, server, "admin", viewport=(1536, 900))
        admin.goto(server + "#/approvals")
        row = admin.get_by_test_id("proposal").filter(has_text="Review relationship type")
        expect(row).to_have_count(1)
        row.get_by_test_id("approve").click()
        expect(toast(admin)).to_contain_text("Approved")
        assert {t["key"]: t for t in Client(USERS["admin"]).get("/api/kb/types")[1]["edge_types"]}["mentors"]["review_status"] == "reviewed"
    assert page.errors == []


def test_b2_duplicate_relationship_type_is_blocked_with_the_existing_one_offered(server, browser):
    _, inst = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "instructor", "name": "Ben Ode"})
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    _connect_dialog(page, server, inst["id"])
    page.get_by_test_id("rel-type").last.fill("Taught by")
    page.get_by_test_id("rel-type-create").click()
    expect(page.get_by_test_id("newrel-duplicate")).to_contain_text("teaches")
    expect(page.get_by_test_id("newrel-save")).to_be_disabled()
    page.get_by_test_id("newrel-use-existing").click()
    assert not [t for t in Client(USERS["admin"]).get("/api/kb/types")[1]["edge_types"] if t["key"] not in
                ("contains", "covers", "teaches", "prerequisite", "sme", "related")]
    assert page.errors == []


def test_b2_merge_relationship_types_from_settings(server, browser):
    admin = Client(USERS["admin"])
    admin.post("/api/kb/types/edge", {"label": "coaches", "inverse_label": "coached by", "rules": [{"source": "instructor", "target": "course"}]})
    _, i = admin.post("/api/kb/nodes", {"type": "instructor", "name": "Cleo"})
    _, c = admin.post("/api/kb/courses", {"name": "Merge Course"})
    admin.post("/api/kb/edges", {"type": "coaches", "source_id": i["id"], "target_id": c["id"]})
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    page.goto(server + "#/settings?tab=relationships")
    row = page.locator("[data-testid=edge-type-row][data-key=coaches]")
    row.get_by_test_id("edge-archive").click()
    expect(page.get_by_test_id("edge-archive-impact")).to_contain_text("1 live relationship")
    page.get_by_role("button", name="Merge into another type…").click()
    page.get_by_test_id("merge-into").select_option("teaches")
    expect(page.get_by_test_id("merge-preview")).to_contain_text("1 relationship will move")
    page.get_by_test_id("merge-confirm").click()
    expect(toast(page)).to_contain_text("Merged")
    edges = Client(USERS["viewer"]).get("/api/kb/edges", f"node={c['id']}")[1]["items"]
    assert [e["type"] for e in edges] == ["teaches"]
    assert page.errors == []


# --- run 3: graph editing (B3) --------------------------------------------------------

def _graph(page, server, center):
    page.goto(server + f"#/graph/{center}")
    expect(page.get_by_test_id("graph-info")).to_contain_text("Showing")
    page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt")


def test_b3_graph_create_connect_rename_delete_undo(server, browser):
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Canvas Course"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Canvas Module", "parents": [course["id"]]})
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    _graph(page, server, course["id"])
    # create: double-click empty canvas (pan the records out of the way first)
    page.evaluate("() => { const cy = window.__kbGraph.cy; cy.zoom(1); cy.pan({ x: -4000, y: -4000 }); }")
    box = page.get_by_test_id("graph-canvas").bounding_box()
    page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.get_by_test_id("graph-new-type").select_option("topic")
    page.get_by_test_id("graph-new-name").fill("Drawn topic")
    page.get_by_test_id("graph-new-create").click()
    expect(toast(page)).to_contain_text("Created “Drawn topic”")
    topic = next(n for n in Client(USERS["viewer"]).get("/api/kb/nodes", "q=Drawn topic")[1]["items"])
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{topic['id']}').length === 1")
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("f")                                            # fit: everything back in view
    # connect: drag the module's handle onto the new topic
    page.mouse.move(*page.evaluate(f"window.__kbGraph.renderedPosition('{mod['id']}')"))
    h = page.get_by_test_id("graph-handle").bounding_box()
    page.mouse.move(h["x"] + 12, h["y"] + 12)
    page.mouse.down()
    tx, ty = page.evaluate(f"window.__kbGraph.renderedPosition('{topic['id']}')")
    page.mouse.move(tx, ty, steps=8)
    page.mouse.up()
    page.get_by_test_id("graph-rel").click()
    page.get_by_test_id("graph-rel-option").filter(has_text="This module covers a topic").first.click()
    expect(page.get_by_test_id("graph-rel-sentence")).to_contain_text("“Canvas Module” covers “Drawn topic”")
    page.get_by_test_id("connect-submit").click()
    expect(toast(page)).to_contain_text("Connected")
    assert len(Client(USERS["viewer"]).get("/api/kb/edges", f"node={topic['id']}")[1]["items"]) == 1
    # rename in place: double-click the node (centred, clear of the minimap and the toolbar)
    page.evaluate(f"() => window.__kbGraph.cy.center(window.__kbGraph.cy.getElementById('{topic['id']}'))")
    page.mouse.dblclick(*page.evaluate(f"window.__kbGraph.renderedPosition('{topic['id']}')"))
    page.get_by_test_id("graph-rename-input").fill("Renamed topic")
    page.keyboard.press("Enter")
    expect(toast(page)).to_contain_text("Renamed")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{topic['id']}")[1]["name"] == "Renamed topic"
    # delete: select and press Delete -> impact -> archive; Undo restores
    page.evaluate(f"(() => {{ const cy = window.__kbGraph.cy; cy.$(':selected').unselect(); cy.getElementById('{topic['id']}').select(); }})()")
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("Delete")
    expect(page.get_by_test_id("archive-impact")).to_contain_text("1 relationship will be archived")
    page.get_by_test_id("confirm-ok").click()
    expect(toast(page)).to_contain_text("Archived 1 record")
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{topic['id']}")[1]["archived_at"]
    toast(page).get_by_test_id("toast-undo").click()
    page.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{topic['id']}').length === 1")
    assert not Client(USERS["viewer"]).get(f"/api/kb/nodes/{topic['id']}")[1]["archived_at"]
    # move: positions are saved to the shared layout and never touch the record
    v0 = Client(USERS["viewer"]).get(f"/api/kb/nodes/{mod['id']}")[1]["version"]
    page.evaluate(f"() => window.__kbGraph.cy.center(window.__kbGraph.cy.getElementById('{mod['id']}'))")
    n0 = page.evaluate("() => window.__kbGraph.savedPositions || 0")
    mx, my = page.evaluate(f"window.__kbGraph.renderedPosition('{mod['id']}')")
    page.mouse.move(mx, my); page.mouse.down(); page.mouse.move(mx - 120, my + 90, steps=6); page.mouse.up()
    page.wait_for_function(f"() => (window.__kbGraph.savedPositions || 0) > {n0}")
    pos = Client(USERS["viewer"]).get("/api/kb/graph/positions", "layout=default")[1]["items"]
    assert any(p["node_id"] == mod["id"] for p in pos)
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{mod['id']}")[1]["version"] == v0
    assert page.errors == []


def test_b3_graph_rejects_an_invalid_connection_with_a_reason(server, browser):
    types = Client(USERS["admin"]).get("/api/kb/types")[1]
    pairs = {(r["source"], r["target"]) for t in types["edge_types"] for r in t["rules"]}
    a, b = next((x["key"], y["key"]) for x in types["node_types"] for y in types["node_types"]
                if (x["key"], y["key"]) not in pairs and (y["key"], x["key"]) not in pairs and x["key"] != y["key"])
    ed = Client(USERS["editor"])
    _, na = ed.post("/api/kb/nodes", {"type": a, "name": "Left one"})
    _, nb = ed.post("/api/kb/nodes", {"type": b, "name": "Right one"})
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    _graph(page, server, na["id"])
    page.evaluate(f"""(() => {{ const cy = window.__kbGraph.cy; cy.add({{group:'nodes', data:{{id:'{nb['id']}', label:'Right one', type:'{b}', color:'#475569', degree:0, shape:'ellipse'}}, position: {{x: cy.getElementById('{na['id']}').position('x') + 220, y: cy.getElementById('{na['id']}').position('y')}}}}); cy.center(); }})()""")
    page.mouse.move(*page.evaluate(f"window.__kbGraph.renderedPosition('{na['id']}')"))
    h = page.get_by_test_id("graph-handle").bounding_box()
    page.mouse.move(h["x"] + 12, h["y"] + 12)
    page.mouse.down()
    page.mouse.move(*page.evaluate(f"window.__kbGraph.renderedPosition('{nb['id']}')"), steps=8)
    page.mouse.up()
    expect(page.get_by_test_id("graph-connect-reason")).to_contain_text("No relationship type allows")
    assert page.evaluate("window.__kbGraph.cy.$('#__ghost, #__ghost_edge').length") == 0          # the line snapped back
    assert Client(USERS["viewer"]).get("/api/kb/edges", f"node={na['id']}")[1]["items"] == []
    assert page.errors == []


def test_b3_two_people_edit_the_graph_at_once(server, browser):
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Shared Canvas"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Shared Module", "parents": [course["id"]]})
    a = page_as(browser, server, "editor", viewport=(1536, 900))
    b = page_as(browser, server, "admin", viewport=(1536, 900))
    _graph(a, server, course["id"])
    _graph(b, server, course["id"])
    # A adds a record and connects it; B sees both arrive without reloading
    _, extra = ed.post("/api/kb/nodes", {"type": "module", "name": "Arrives live", "parents": [course["id"]]})
    b.wait_for_function(f"() => window.__kbGraph.cy.getElementById('{extra['id']}').length === 1", timeout=20000)
    # both rename the same record: the second save gets the conflict dialog
    a.mouse.dblclick(*a.evaluate(f"window.__kbGraph.renderedPosition('{mod['id']}')"))
    a.get_by_test_id("graph-rename-input").fill("Name from A")
    a.keyboard.press("Enter")
    expect(toast(a)).to_contain_text("Renamed")
    b.mouse.dblclick(*b.evaluate(f"window.__kbGraph.renderedPosition('{mod['id']}')"))
    b.evaluate("window.__kbGraph.cy.nodes().forEach((n) => n.data('version', Math.min(n.data('version') || 1, 1)))")   # B still holds v1
    b.get_by_test_id("graph-rename-input").fill("Name from B")
    b.keyboard.press("Enter")
    expect(b.get_by_test_id("conflict-dialog")).to_contain_text("Name from A")
    b.get_by_test_id("conflict-reload").click()
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/{mod['id']}")[1]["name"] == "Name from A"
    assert a.errors == [] and b.errors == []


# --- run 3: activity (B4) and the admin-only link (B5) --------------------------------

def test_b4_activity_filters_and_diff(server, browser):
    ed = Client(USERS["editor"])
    _, n = ed.post("/api/kb/nodes", {"type": "topic", "name": "Diff me", "summary": "old text"})
    ed.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "new text"})
    Client(USERS["admin"]).post("/api/kb/nodes", {"type": "topic", "name": "Admin made"})
    page = page_as(browser, server, "admin", viewport=(1536, 900))
    page.goto(server + "#/activity")
    expect(page.get_by_test_id("activity-entry").first).to_be_visible()
    page.get_by_test_id("activity-action").select_option("update")
    expect(page.get_by_test_id("activity-entry")).to_have_count(1)
    entry = page.get_by_test_id("activity-entry").first
    expect(entry.get_by_test_id("history-diff")).to_contain_text("old text")
    expect(entry.get_by_test_id("history-diff")).to_contain_text("new text")
    expect(entry.locator("time")).to_have_attribute("title", re.compile(r"\d"))
    page.get_by_test_id("activity-clear").click()
    page.get_by_test_id("activity-search").fill("Admin made")
    expect(page.get_by_test_id("activity-entry")).to_have_count(1)
    with page.expect_download() as dl:
        page.get_by_test_id("activity-csv").click()
    text = Path(dl.value.path()).read_text(encoding="utf-8")
    assert text.startswith("id,at,actor,source,action") and "Admin made" in text
    # the record's History tab uses the same entries
    open_record(page, server, n["id"])
    page.get_by_test_id("tab-history").click()
    expect(page.get_by_test_id("history-list").get_by_test_id("activity-entry")).to_have_count(2)
    assert page.errors == []


def test_b4_activity_is_not_offered_to_viewers(server, browser):
    page = page_as(browser, server, "viewer", viewport=(1536, 900))
    expect(page.locator("[data-nav=activity]")).to_have_count(0)
    page.goto(server + "#/activity")
    expect(page.get_by_test_id("empty")).to_contain_text("Activity is for editors and admins")


@pytest.mark.parametrize("role", ["admin", "editor", "contributor", "viewer"])
def test_b5_link_back_to_the_original_site_is_admin_only(server, browser, role):
    page = page_as(browser, server, role, viewport=(1536, 900))
    link = page.get_by_test_id("back-to-site-nav")
    page.get_by_test_id("whoami").click()
    if role == "admin":
        expect(link).to_have_attribute("href", "/")
        expect(page.get_by_test_id("back-to-site")).to_be_visible()
    else:
        expect(link).to_have_count(0)
        expect(page.get_by_test_id("back-to-site")).to_have_count(0)
    assert page.errors == []


def test_b3_graph_keyboard_only(server, browser):
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Keyboard Canvas"})
    ed.post("/api/kb/nodes", {"type": "module", "name": "Keyed module", "parents": [course["id"]]})
    page = page_as(browser, server, "editor", viewport=(1536, 900))
    _graph(page, server, course["id"])
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("n")                                           # N: new record at the centre
    expect(page.get_by_test_id("graph-new-name")).to_be_focused()
    page.keyboard.type("Typed topic")
    page.keyboard.press("Enter")
    expect(toast(page)).to_contain_text("Created “Typed topic”")
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("f")                                           # F: fit
    page.keyboard.press("/")                                           # /: find
    expect(page.get_by_test_id("graph-search")).to_be_focused()
    page.keyboard.type("Keyed")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__kbGraph.cy.$('node:selected').length === 1")
    assert page.evaluate("() => window.__kbGraph.cy.$('node:selected').data('label')") == "Keyed module"
    page.get_by_test_id("graph-canvas").focus()
    page.keyboard.press("Escape")                                      # Esc: clear the selection
    assert page.evaluate("() => window.__kbGraph.cy.$(':selected').length") == 0
    assert page.errors == []
