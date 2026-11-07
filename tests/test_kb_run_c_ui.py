"""Run C in a real browser (owner decisions 2026-11-07): the one entity component with owners and SMEs
(navigate, edit, persist), the Graph editor's owner filter, the Map's panel and KB role, the source
catalog page, the New record form's people, and the Guide. Screenshots: testing/evidence/ (gitignored).

SYNTHETIC records (kb_support resets the kb tables around each test).
"""
from __future__ import annotations

import json
import time

import pytest

from kb_support import USERS, Client, owner, requires_kb, token_for
from test_kb_e2e import CONTEXTS, _data, page_as  # noqa: F401  (_data: the per-test reset)
from test_kb_run_c import _curriculum, shot

from pipeline.lib import taxonomy  # noqa: E402

OWNED_BY = taxonomy.edge_for_role("domain_primary")
pytestmark = [requires_kb]

pytest.importorskip("playwright.sync_api", reason="kb e2e: needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402


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


def test_ui_detail_panel_owners_smes_navigate_edit_persist(server, browser):
    d = _curriculum()
    ad = Client(USERS["admin"])
    ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][1]["id"], "target_id": d["mod"]["id"], "props": {"role": "backup", "rank": 1}})
    ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": d["mod"]["id"], "props": {"role": "primary"}})
    _, res = ad.post(f"/api/kb/nodes/{d['mod']['id']}/resources", {"url": "https://docs.google.com/document/d/runc-live-doc", "title": "RunC lesson plan"})
    page = page_as(browser, server, "editor")
    page.goto(server + "#/records?open=" + d["mod"]["id"])
    ent = page.get_by_test_id("entity")
    expect(ent).to_be_visible()
    expect(page.get_by_test_id("entity-domain")).to_have_text("Backend")
    rows = page.get_by_test_id("sme-row")
    expect(rows).to_have_count(2)
    expect(rows.nth(0).get_by_test_id("sme-role")).to_have_text("Primary")
    expect(rows.nth(1).get_by_test_id("sme-role")).to_have_text("Backup 1")
    expect(page.get_by_test_id("entity-used-in")).to_contain_text("RunC Course")
    expect(page.get_by_test_id("entity-resource")).to_have_attribute("href", "https://docs.google.com/document/d/runc-live-doc")
    shot(page, "owner-sme", "UI-OS-01-module-panel")
    # add an owner (NP team member; the picker offers team members only)
    page.get_by_test_id("add-owner").click()
    page.get_by_test_id("owner-picker").fill("RunC")
    opts = page.locator("[role=option]")
    expect(opts.first).to_be_visible()
    assert not any("Instructor" in t for t in opts.all_inner_texts())
    shot(page, "owner-sme", "UI-OS-02-owner-picker-team-only")
    opts.filter(has_text="RunC Owner 2").first.click()
    expect(page.get_by_test_id("entity-owners")).to_contain_text("RunC Owner 2")
    # add an SME with role Backup 2
    page.get_by_test_id("add-sme").click()
    page.get_by_test_id("sme-picker").fill("RunC Instructor 3")
    page.locator("[role=option]").filter(has_text="RunC Instructor 3").first.click()
    page.get_by_test_id("sme-role-select").select_option("backup:2")
    shot(page, "owner-sme", "UI-OS-03-sme-role-dialog")
    page.get_by_test_id("sme-role-save").click()
    expect(page.get_by_test_id("sme-row")).to_have_count(3)
    expect(page.get_by_test_id("sme-row").nth(2).get_by_test_id("sme-role")).to_have_text("Backup 2")
    shot(page, "owner-sme", "UI-OS-04-sme-added")
    # change a role
    page.get_by_test_id("sme-row").nth(2).get_by_test_id("change-sme-role").click()
    page.get_by_test_id("sme-role-select").select_option("backup:3")
    page.get_by_test_id("sme-role-save").click()
    expect(page.get_by_test_id("sme-row").nth(2).get_by_test_id("sme-role")).to_have_text("Backup 3")
    # the change is in the database and everywhere else
    prof = Client(USERS["viewer"]).get(f"/api/kb/nodes/{d['mod']['id']}")[1]["profile"]
    assert [s["label"] for s in prof["smes"]] == ["Primary", "Backup 1", "Backup 3"]
    assert [o["name"] for o in prof["owners"]] == ["RunC Owner 2"]
    # navigate to a related record (the course), then back; close and reopen: the data persists
    page.get_by_test_id("entity-used-in").get_by_role("link", name="RunC Course").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("RunC Course")
    expect(page.get_by_test_id("entity-modules")).to_contain_text("RunC Database Design")
    shot(page, "curriculum", "UI-CU-01-course-panel")
    page.get_by_test_id("close-panel").click()
    page.goto(server + "#/records?open=" + d["mod"]["id"])
    expect(page.get_by_test_id("sme-row")).to_have_count(3)
    expect(page.get_by_test_id("entity-owners")).to_contain_text("RunC Owner 2")
    shot(page, "owner-sme", "UI-OS-05-reopened-persisted")
    assert page.errors == []


def test_ui_viewer_sees_people_but_cannot_edit(server, browser):
    d = _curriculum()
    Client(USERS["admin"]).post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["mod"]["id"], "target_id": d["tm"][0]["id"]})
    page = page_as(browser, server, "viewer")
    page.goto(server + "#/records?open=" + d["mod"]["id"])
    expect(page.get_by_test_id("entity-owners")).to_contain_text("RunC Owner 1")
    expect(page.get_by_test_id("add-owner")).to_have_count(0)
    expect(page.get_by_test_id("add-sme")).to_have_count(0)
    shot(page, "owner-sme", "UI-OS-06-viewer-read-only")
    # and the server refuses the write anyway
    s, _ = Client(USERS["viewer"]).post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["mod"]["id"], "target_id": d["tm"][1]["id"]})
    assert s == 403


def test_ui_graph_owner_filter_lists_team_members_not_instructors(server, browser):
    d = _curriculum()
    ad = Client(USERS["admin"])
    ad.post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["mod"]["id"], "target_id": d["tm"][0]["id"]})
    ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": d["mod"]["id"], "props": {"role": "primary"}})
    page = page_as(browser, server, "admin")
    page.goto(server + "#/graph")
    page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=30000)
    opts = page.get_by_test_id("graph-owner-filter").locator("option").all_inner_texts()
    assert "RunC Owner 1" in opts and not any("Instructor" in o for o in opts), opts
    page.get_by_test_id("graph-owner-filter").select_option(label="RunC Owner 1")
    shot(page, "graph", "UI-GR-01-owner-filter-team-members")
    assert page.errors == []


def test_ui_map_uses_the_same_entity_component_and_kb_role(server, browser):
    d = _curriculum()
    Client(USERS["admin"]).post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": d["mod"]["id"], "props": {"role": "primary"}})
    base = server[:-len("/kb/")]
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    CONTEXTS.append(ctx)
    sess = json.dumps({"access_token": token_for(USERS["admin"], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": "kbtest-admin@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/?open=" + d["mod"]["id"])
    expect(page.locator("#who")).to_contain_text("admin", timeout=30000)        # the KB role, not the site role
    slot = page.get_by_test_id("map-entity-slot")
    expect(slot.get_by_test_id("entity")).to_be_visible(timeout=30000)
    expect(slot.get_by_test_id("sme-row").first.get_by_test_id("sme-role")).to_have_text("Primary")
    expect(slot.get_by_test_id("entity-used-in")).to_contain_text("RunC Course")
    expect(slot.get_by_test_id("add-owner")).to_have_count(0)                 # the Map is read-only
    with owner() as c:
        c.execute("update kb.nodes set search_aliases = 'SD3' where id = %s", (d["dom"]["id"],))
    assert "SD3" not in page.locator("#right").inner_text()                  # domain codes are never displayed
    shot(page, "graph", "UI-MP-01-map-entity-panel")
    assert errors == []


def test_ui_sources_page_for_admins(server, browser):
    with owner() as c:
        c.execute("""insert into kb.sources (provider, resource_id, kind, title, url, status, failure_reason, provenance, version)
                     values ('drive', 'runc-ui-1', 'presentation', 'RunC slides', 'https://docs.google.com/presentation/d/runc-ui-1', 'extracted', null, '{registry,SD3: Backend Engineering}', '12'),
                            ('drive', 'runc-ui-2', 'document', null, 'https://docs.google.com/document/d/runc-ui-2', 'failed',
                             'not found or not shared with the service account (Drive answers 404 for both)', '{registry,Sheet1!B4}', null),
                            ('confluence', 'runc-ui-3', 'page', 'RunC [Do not Use] page', 'https://example.invalid/p', 'do_not_use', null, '{KYPs}', '3')
                     on conflict do nothing""")
    try:
        page = page_as(browser, server, "admin")
        page.goto(server + "#/settings?tab=sync")
        expect(page.get_by_test_id("sources-counts")).to_be_visible()
        expect(page.get_by_test_id("source-row")).to_have_count(3)
        shot(page, "source-crawling", "UI-SC-01-sources-page")
        page.get_by_test_id("sources-filter-failed").click()
        expect(page.get_by_test_id("source-row")).to_have_count(1)
        expect(page.get_by_test_id("source-failure")).to_contain_text("not shared")
        shot(page, "source-crawling", "UI-SC-02-failures-with-reason")
        page.get_by_test_id("sources-filter-all").click()
        expect(page.get_by_test_id("source-row")).to_have_count(3)
        page.get_by_test_id("sources-search").fill("slides")
        expect(page.get_by_test_id("source-link")).to_have_text(["RunC slides"])
        expect(page.get_by_test_id("source-link")).to_have_attribute("href", "https://docs.google.com/presentation/d/runc-ui-1")
        assert page.errors == []
        # viewers do not get the page's data
        assert Client(USERS["viewer"]).get("/api/kb/sources")[0] == 403
    finally:
        with owner() as c:
            c.execute("delete from kb.sources where resource_id like 'runc-ui-%%'")


def test_ui_new_record_form_sets_owners_and_sme_roles(server, browser):
    _curriculum()
    page = page_as(browser, server, "editor")
    page.get_by_test_id("new-record").click()
    from test_kb_e2e import choose_type
    choose_type(page, "Module")
    page.get_by_test_id("create-name").fill("RunC Form Module")
    page.get_by_test_id("section-people").locator("summary").click()
    for tid, name in (("np-owners", "RunC Owner 1"), ("sme-primary", "RunC Instructor 1"), ("sme-backups", "RunC Instructor 2"), ("sme-backups", "RunC Instructor 3")):
        page.get_by_test_id(tid).fill(name)
        page.locator("[role=option]").filter(has_text=name).first.click()
    shot(page, "owner-sme", "UI-OS-07-new-record-people")
    page.get_by_test_id("create-submit").click()
    expect(page.get_by_test_id("panel-name")).to_have_text("RunC Form Module")
    expect(page.get_by_test_id("sme-row")).to_have_count(3)
    nid = page.url.split("open=")[-1].split("&")[0]
    prof = Client(USERS["viewer"]).get(f"/api/kb/nodes/{nid}")[1]["profile"]
    assert [s["label"] for s in prof["smes"]] == ["Primary", "Backup 1", "Backup 2"]
    assert [o["name"] for o in prof["owners"]] == ["RunC Owner 1"]
    assert page.errors == []


def test_ui_guide_matches_the_model(server, browser):
    page = page_as(browser, server, "viewer")
    page.goto(server + "#/guide")
    g = page.get_by_test_id("guide")
    expect(g).to_contain_text("Owners and SMEs")
    for must in ("Fullstack", "Backend", "Frontend", "Test", "registry sheet", "Primary", "Backup 1", "Re-crawling", "Graph editor"):
        expect(g).to_contain_text(must)
    text = g.inner_text()
    for gone in ("workflow", "Workflow", "theme", "programme week", "Programme week", "SD1", "SD4", "mastersheet"):
        assert gone not in text, gone
    shot(page, "guide", "UI-GU-01-guide")
