"""C3/C4/D1/D3–D6 at the API: one-step create (nested inline placement,
relationships, links incl. reuse, people, tags), rollback, contributor
proposals, duplicate-name check, bulk edit/archive, Archived → permanent
delete, outline + reorder, flags, templates, saved views, completeness."""
from __future__ import annotations

import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    with owner() as c:
        c.execute("truncate kb.flags, kb.templates, kb.saved_views")
    yield
    reset()


@pytest.fixture
def ed():
    return Client(USERS["editor"])


@pytest.fixture
def contrib():
    return Client(USERS["contributor"])


@pytest.fixture
def admin():
    return Client(USERS["admin"])


def test_one_save_creates_everything_with_nested_inline_placement(ed):
    _, mentor = ed.post("/api/kb/nodes", {"type": "instructor", "name": "Ada Example"})
    _, reused = ed.post("/api/kb/resources", {"url": "https://github.com/ik-demo/shared", "title": "Shared repo"})
    s, n = ed.post("/api/kb/nodes", {
        "type": "session", "name": "Designing a rate limiter", "summary": "Token bucket vs sliding window",
        "parents": [{"new": {"type": "module", "name": "Scalability",
                     "parent": {"new": {"type": "course", "name": "System Design II"}}}}],     # run C: no weeks
        "edges": [{"type": "covers", "direction": "out", "node": {"new": {"type": "topic", "name": "Rate limiting"}}},
                  {"type": "teaches", "direction": "in", "node": mentor["id"]}],
        "resources": [{"url": "https://drive.google.com/file/d/abc/view", "title": "Deck", "note": "Shown in class"},
                      {"url": "https://uplevel.interviewkickstart.com/update_video/9/", "title": "Recording",
                       "kind": "recording"},
                      {"resource_id": reused["id"], "note": "Starter code"}],
        "tags": ["new-2026"]})
    assert s == 201, n
    assert [b["name"] for b in n["breadcrumb"]] == ["System Design II", "Scalability"]
    assert n["scope_name"] == "System Design II"
    assert {r["link_kind"] for r in n["resources"]} == {"drive_file", "uplevel", "github"}
    assert {e["label"] for e in n["incoming"]} >= {"taught by", "part of"}
    assert {c["name"] for c in n["created_inline"]} == {"System Design II", "Scalability", "Rate limiting"}
    assert [t["name"] for t in n["tags"]] == ["new-2026"]
    assert n["owner_id"] == USERS["editor"]


def test_a_failed_save_rolls_back_everything_and_names_the_field(ed):
    s, out = ed.post("/api/kb/nodes", {
        "type": "module", "name": "Doomed", "parents": [{"new": {"type": "course", "name": "Doomed course"}}],
        "resources": [{"url": "https://example.com/ok", "title": "ok"}],
        "edges": [{"type": "covers", "node": {"new": {"type": "topic", "name": "T"}}},
                  {"type": "teaches", "direction": "out", "node": {"new": {"type": "topic", "name": "T2"}}}]})
    assert s == 422 and out["field"] == "edges.1" and "not allowed" in out["message"]
    assert ed.get("/api/kb/nodes", "status=all")[1]["items"] == []
    assert ed.get("/api/kb/resources")[1]["items"] == []


def test_contributor_create_is_a_proposal_an_editor_approves(contrib, ed):
    s, out = contrib.post("/api/kb/nodes", {"type": "topic", "name": "Proposed topic"})
    assert s == 202 and "sent for approval" in out["message"]
    assert ed.get("/api/kb/nodes")[1]["items"] == []
    p = [x for x in ed.get("/api/kb/proposals")[1]["items"] if x["action"] == "create"][0]
    assert p["target_label"] == "Proposed topic"
    s, d = ed.post(f"/api/kb/proposals/{p['id']}/approve")
    assert s == 200 and d["result"]["name"] == "Proposed topic"
    s, out = contrib.post("/api/kb/nodes", {"type": "topic", "name": "Proposed topic"})
    assert s == 409 and out["existing"]["name"] == "Proposed topic"           # validated before proposing


def test_duplicate_name_check_while_typing(ed):
    ed.post("/api/kb/nodes", {"type": "topic", "name": "Dynamic Programming"})
    s, out = ed.get("/api/kb/nodes/check-name", "type=topic&name=dynamic%20programming")
    assert s == 200 and out["exact"]["name"] == "Dynamic Programming"
    s, out = ed.get("/api/kb/nodes/check-name", "type=topic&name=Dynamic%20Programing")
    assert out["exact"] is None and out["similar"][0]["name"] == "Dynamic Programming"


def test_bulk_edit_and_bulk_archive(ed, contrib):
    ids = [ed.post("/api/kb/nodes", {"type": "topic", "name": f"B{i}"})[1]["id"] for i in range(3)]
    # Run 6: a contributor's field changes become one proposal per record (0033); tags stay direct.
    s, out = contrib.post("/api/kb/nodes/bulk", {"ids": ids, "set": {"owner_id": USERS["contributor"], "status": "draft"},
                                                 "add_tags": ["batch"]})
    assert s == 202 and out["count"] == 3
    assert ed.get("/api/kb/nodes", "status=draft")[1]["items"] == []
    s, out = ed.post("/api/kb/nodes/bulk", {"ids": ids, "set": {"owner_id": USERS["contributor"], "status": "draft"}})
    assert s == 200 and out["updated"] == 3
    items = ed.get("/api/kb/nodes", "status=draft")[1]["items"]
    assert {i["owner_id"] for i in items} == {USERS["contributor"]}
    assert contrib.post("/api/kb/nodes/bulk-archive", {"ids": ids})[0] == 202   # proposals
    s, out = ed.post("/api/kb/nodes/bulk-archive", {"ids": ids[:2]})
    assert s == 200 and out["archived"] == 2


def test_archived_then_permanent_delete_with_impact(ed, admin):
    _, a = ed.post("/api/kb/nodes", {"type": "topic", "name": "Gone soon",
                                     "resources": [{"url": "https://example.com/g", "title": "g"}]})
    ed.post(f"/api/kb/nodes/{a['id']}/archive")
    arch = ed.get("/api/kb/archived", "kind=records")[1]["items"]
    assert [x["name"] for x in arch] == ["Gone soon"]
    assert ed.get(f"/api/kb/nodes/{a['id']}/delete-impact")[1]["links"] == 1
    assert ed.delete(f"/api/kb/nodes/{a['id']}")[0] == 403
    assert admin.delete(f"/api/kb/nodes/{a['id']}")[0] == 200
    assert ed.get("/api/kb/archived")[1]["items"] == []


def test_outline_tree_and_reorder(ed):
    _, c = ed.post("/api/kb/courses", {"name": "Outline course"})
    a = ed.post("/api/kb/nodes", {"type": "module", "name": "Alpha", "parents": [c["id"]]})[1]
    b = ed.post("/api/kb/nodes", {"type": "module", "name": "Beta", "parents": [c["id"]]})[1]
    tree = ed.get("/api/kb/outline")[1]["roots"]
    assert [x["name"] for x in tree[0]["children"]] == ["Alpha", "Beta"]
    ed.post("/api/kb/outline/reorder", {"parent_id": c["id"], "child_ids": [b["id"], a["id"]]})
    assert [x["name"] for x in ed.get("/api/kb/outline")[1]["roots"][0]["children"]] == ["Beta", "Alpha"]


def test_flag_assigned_to_owner_and_resolved(ed, contrib):
    _, n = ed.post("/api/kb/nodes", {"type": "topic", "name": "Questionable"})
    viewer = Client(USERS["viewer"])
    s, f = viewer.post("/api/kb/flags", {"target_table": "nodes", "target_id": n["id"], "reason": "Wrong date"})
    assert s == 201 and f["assigned_to"] == USERS["editor"]
    assert [x["name"] for x in ed.get("/api/kb/nodes", "flagged=1")[1]["items"]] == ["Questionable"]
    assert contrib.post(f"/api/kb/flags/{f['id']}/resolve", {})[0] == 403
    s, r = ed.post(f"/api/kb/flags/{f['id']}/resolve", {"resolution": "Fixed the date"})
    assert s == 200 and r["status"] == "resolved"


def test_template_saves_structure_and_instantiates_with_name_substitution(ed):
    _, c = ed.post("/api/kb/courses", {"name": "Python Basics", "resources": [{"url": "https://example.com/py", "title": "x"}]})
    m = ed.post("/api/kb/nodes", {"type": "module", "name": "Python Basics: Syntax", "parents": [c["id"]]})[1]
    ed.post("/api/kb/nodes", {"type": "topic", "name": "Python Basics: Variables", "parents": [m["id"]]})
    s, t = ed.post("/api/kb/templates", {"source_id": c["id"], "name": "Intro course"})
    assert s == 201
    s, out = ed.post(f"/api/kb/templates/{t['id']}/instantiate", {"name": "Go Basics"})
    assert s == 201 and out["created"] == 3
    names = {n["name"] for n in ed.get("/api/kb/nodes", "limit=50")[1]["items"]}
    assert {"Go Basics", "Go Basics: Syntax"} <= names
    new_course = ed.get(f"/api/kb/nodes/{out['root']['id']}")[1]
    assert new_course["resources"] == []                                    # structure, not content links


def test_saved_views_personal_and_shared(ed, contrib):
    s, v1 = ed.post("/api/kb/views", {"name": "My drafts", "config": {"status": "draft"}})
    s, v2 = ed.post("/api/kb/views", {"name": "Team: no owner", "shared": True, "config": {"no_owner": 1}})
    assert {v["name"] for v in contrib.get("/api/kb/views")[1]["items"]} == {"Team: no owner"}
    assert contrib.call("DELETE", f"/api/kb/views/{v2['id']}")[0] == 403
    assert ed.call("DELETE", f"/api/kb/views/{v1['id']}")[0] == 200


def test_completeness_names_what_is_missing(ed):
    _, c = ed.post("/api/kb/courses", {"name": "Scored", "summary": "s"})
    m = ed.post("/api/kb/nodes", {"type": "module", "name": "Bare", "parents": [c["id"]], "owner_id": None})[1]
    sc = ed.get(f"/api/kb/nodes/{m['id']}/completeness")[1]
    assert set(sc["missing"]) == {"Has an owner", "Has a summary", "Has at least one link"}
    cs = ed.get(f"/api/kb/nodes/{c['id']}/completeness")[1]
    assert cs["tree_size"] == 2 and cs["weakest"][0]["name"] == "Bare"
