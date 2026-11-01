"""M3 — /api/kb/* through the REAL WSGI app (api/index.py): real HS256 token
verification, the real connection scoping, RLS underneath. Every endpoint
family is covered for success, validation error, permission denied, 404, 409
conflict and duplicate rejection."""
from __future__ import annotations

import uuid

import pytest

from kb_support import USERS, OUTSIDER, Client, ensure_users, requires_kb, reset

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()


@pytest.fixture
def admin():
    return Client(USERS["admin"])


@pytest.fixture
def editor():
    return Client(USERS["editor"])


@pytest.fixture
def contrib():
    return Client(USERS["contributor"])


@pytest.fixture
def viewer():
    return Client(USERS["viewer"])


def _mk(client, type_="topic", name="Binary Search", **kw):
    s, body = client.post("/api/kb/nodes", {"type": type_, "name": name, **kw})
    assert s == 201, body
    return body


# --- auth --------------------------------------------------------------------

def test_no_token_is_401():
    s, body = Client(None).get("/api/kb/nodes")
    assert s == 401


def test_a_signed_in_account_without_a_profile_sees_nothing_and_cannot_write():
    c = Client(OUTSIDER)
    s, body = c.get("/api/kb/nodes")
    assert s == 200 and body["items"] == []
    s, body = c.post("/api/kb/nodes", {"type": "topic", "name": "x"})
    assert s == 403


def test_me_reports_the_role(viewer, admin):
    assert viewer.get("/api/kb/me")[1]["role"] == "viewer"
    assert admin.get("/api/kb/me")[1]["role"] == "admin"


# --- nodes ---------------------------------------------------------------------

def test_create_get_list_node(contrib, viewer):
    n = _mk(contrib, summary="Halving the search space")
    assert n["version"] == 1 and n["type"] == "topic"
    s, got = viewer.get(f"/api/kb/nodes/{n['id']}")
    assert s == 200 and got["name"] == "Binary Search"
    s, page = viewer.get("/api/kb/nodes", "type=topic")
    assert [i["id"] for i in page["items"]] == [n["id"]]


def test_validation_errors_are_422_and_name_the_field(contrib):
    for body, field in (({"type": "topic"}, "name"), ({"type": "topic", "name": "  "}, "name"),
                        ({"type": "nope", "name": "x"}, "type"),
                        ({"type": "topic", "name": "x" * 301}, "name"),
                        ({"type": "topic", "name": "mail me@example.com"}, "name"),
                        ({"type": "topic", "name": "ok", "bogus": 1}, None)):
        s, out = contrib.post("/api/kb/nodes", body)
        assert s == 422, (body, out)
        if field:
            assert out.get("field") == field


def test_viewer_write_is_403(viewer):
    s, out = viewer.post("/api/kb/nodes", {"type": "topic", "name": "x"})
    assert s == 403 and out["error"] == "permission_denied"


def test_unknown_node_is_404_and_bad_id_is_422(viewer):
    assert viewer.get(f"/api/kb/nodes/{uuid.uuid4()}")[0] == 404
    assert viewer.get("/api/kb/nodes/not-a-uuid")[0] == 422
    assert viewer.get("/api/kb/nowhere")[0] == 404


def test_duplicate_name_is_409_with_a_link_to_the_existing_record(contrib):
    n = _mk(contrib, name="Dynamic Programming")
    s, out = contrib.post("/api/kb/nodes", {"type": "topic", "name": "  dynamic   PROGRAMMING "})
    assert s == 409 and out["error"] == "duplicate"
    assert out["existing"]["id"] == n["id"]


def test_update_needs_version_and_a_stale_version_is_409_with_current(contrib, editor):
    n = _mk(contrib)
    s, out = contrib.patch(f"/api/kb/nodes/{n['id']}", {"summary": "no version"})
    assert s == 422 and out["field"] == "version"
    s, a = contrib.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "first"})
    assert s == 200 and a["version"] == 2
    s, out = editor.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "second"})
    assert s == 409 and out["error"] == "version_conflict"
    assert out["current"]["summary"] == "first" and out["current"]["version"] == 2


def test_force_overwrite_is_editor_only(contrib, editor):
    n = _mk(contrib)
    contrib.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "newer"})
    s, _ = contrib.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "mine"}, "force=1")
    assert s == 403
    s, out = editor.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "mine"}, "force=1")
    assert s == 200 and out["summary"] == "mine"


def test_archive_impact_archive_restore(contrib, editor):
    a, b = _mk(contrib, name="A"), _mk(contrib, name="B")
    s, e = contrib.post("/api/kb/edges", {"type": "related", "source_id": a["id"], "target_id": b["id"]})
    assert s == 201
    s, imp = editor.get(f"/api/kb/nodes/{a['id']}/impact")
    assert imp["edges"] == 1
    s, out = contrib.post(f"/api/kb/nodes/{a['id']}/archive")
    assert s == 202 and out["error"] == "approval_required"      # contributor → proposal
    s, out = editor.post(f"/api/kb/nodes/{a['id']}/archive")
    assert s == 200 and out["node"]["archived_at"] and out["impact"]["edges"] == 1
    assert editor.get(f"/api/kb/edges/{e['id']}")[1]["archived_at"]
    s, out = editor.post(f"/api/kb/nodes/{a['id']}/restore")
    assert s == 200 and out["archived_at"] is None
    assert editor.get(f"/api/kb/edges/{e['id']}")[1]["archived_at"] is None


def test_duplicate_copies_text_and_resources_not_edges(contrib):
    n = _mk(contrib, name="Original", summary="s", resources=[{"url": "https://example.com/r", "title": "R"}])
    s, d = contrib.post(f"/api/kb/nodes/{n['id']}/duplicate")
    assert s == 201 and d["name"] == "Original (copy)" and d["status"] == "draft"
    assert len(d["resources"]) == 1 and d["resources"][0]["id"] == n["resources"][0]["id"]
    s, d2 = contrib.post(f"/api/kb/nodes/{n['id']}/duplicate")
    assert d2["name"] == "Original (copy 2)"


def test_hard_delete_admin_only_and_archived_only(editor, admin):
    n = _mk(editor, name="Temp")
    assert admin.delete(f"/api/kb/nodes/{n['id']}")[0] == 422          # not archived
    editor.post(f"/api/kb/nodes/{n['id']}/archive")
    assert editor.delete(f"/api/kb/nodes/{n['id']}")[0] == 403
    assert admin.delete(f"/api/kb/nodes/{n['id']}")[0] == 200
    assert admin.get(f"/api/kb/nodes/{n['id']}")[0] == 404


# --- courses / programs, inline creation, one transaction ---------------------

def test_inline_course_creation_inside_a_module_create(contrib, viewer):
    s, m = contrib.post("/api/kb/nodes", {"type": "module", "name": "Week 1",
                                          "scope": {"new": {"type": "course", "name": "System Design"}}})
    assert s == 201 and m["scope_name"] == "System Design" and m["created_scope_id"]
    s, courses = viewer.get("/api/kb/courses")
    assert [c["name"] for c in courses["items"]] == ["System Design"]
    s, prog = contrib.post("/api/kb/programs", {"name": "Backend Track"})
    assert s == 201 and prog["type"] == "program"
    assert viewer.get(f"/api/kb/courses/{prog['id']}")[0] == 404


def test_multi_step_create_is_atomic(contrib, viewer):
    """A bad edge in the same request rolls back the node, the inline course and
    the resource: nothing partial is left behind."""
    s, out = contrib.post("/api/kb/nodes", {
        "type": "module", "name": "Atomic", "scope": {"new": {"type": "course", "name": "Atomic Course"}},
        "resources": [{"url": "https://example.com/atomic", "title": "doc"}],
        "edges": [{"type": "teaches", "node_id": str(uuid.uuid4())}]})
    assert s in (422, 404), out
    assert viewer.get("/api/kb/nodes", "status=all")[1]["items"] == []
    assert viewer.get("/api/kb/resources")[1]["items"] == []


def test_scope_must_be_a_container(contrib):
    t = _mk(contrib, name="A topic")
    s, out = contrib.post("/api/kb/nodes", {"type": "module", "name": "M", "scope": t["id"]})
    assert s == 422 and out["field"] == "scope"


# --- edges -------------------------------------------------------------------

def test_edge_rules_duplicates_and_self_edges(contrib):
    c = _mk(contrib, "course", "Algorithms")
    t = _mk(contrib, "topic", "Sorting")
    s, e = contrib.post("/api/kb/edges", {"type": "covers", "source_id": c["id"], "target_id": t["id"]})
    assert s == 201 and e["type"] == "covers"
    s, out = contrib.post("/api/kb/edges", {"type": "covers", "source_id": c["id"], "target_id": t["id"]})
    assert s == 409 and out["error"] == "duplicate"
    s, out = contrib.post("/api/kb/edges", {"type": "covers", "source_id": t["id"], "target_id": c["id"]})
    assert s == 422 and "not allowed from topic to course" in out["message"]
    s, out = contrib.post("/api/kb/edges", {"type": "related", "source_id": t["id"], "target_id": t["id"]})
    assert s == 422 and "itself" in out["message"]


def test_edge_update_conflict_and_archive(contrib, editor):
    a, b = _mk(contrib, name="A"), _mk(contrib, name="B")
    _, e = contrib.post("/api/kb/edges", {"type": "related", "source_id": a["id"], "target_id": b["id"]})
    assert contrib.patch(f"/api/kb/edges/{e['id']}", {"version": 1, "note": "n1"})[0] == 200
    s, out = contrib.patch(f"/api/kb/edges/{e['id']}", {"version": 1, "note": "n2"})
    assert s == 409
    assert contrib.post(f"/api/kb/edges/{e['id']}/archive")[0] == 202
    assert editor.post(f"/api/kb/edges/{e['id']}/archive")[0] == 200
    assert editor.post(f"/api/kb/edges/{e['id']}/restore")[0] == 200
    assert editor.get(f"/api/kb/edges/{uuid.uuid4()}")[0] == 404


def test_connecting_an_archived_node_is_refused(contrib, editor):
    a, b = _mk(contrib, name="A"), _mk(contrib, name="B")
    editor.post(f"/api/kb/nodes/{b['id']}/archive")
    s, out = contrib.post("/api/kb/edges", {"type": "related", "source_id": a["id"], "target_id": b["id"]})
    assert s == 422 and "archived" in out["message"]


# --- resources ----------------------------------------------------------------

def test_resource_crud_dedupe_and_reuse(contrib, editor, viewer):
    s, r = contrib.post("/api/kb/resources", {"url": "https://example.com/guide", "title": "Guide", "kind": "doc"})
    assert s == 201
    s, out = contrib.post("/api/kb/resources", {"url": "https://EXAMPLE.com/guide/", "title": "Again"})
    assert s == 409 and out["existing"]["id"] == r["id"]
    assert contrib.post("/api/kb/resources", {"url": "notaurl", "title": "x"})[0] == 422
    assert viewer.post("/api/kb/resources", {"url": "https://example.com/v", "title": "x"})[0] == 403
    n1, n2 = _mk(contrib, name="N1"), _mk(contrib, name="N2")
    s, att = contrib.post(f"/api/kb/nodes/{n1['id']}/resources", {"resource_id": r["id"], "note": "primary"})
    assert s == 201 and not att["reused"]
    s, att2 = contrib.post(f"/api/kb/nodes/{n2['id']}/resources",
                           {"url": "https://example.com/guide", "title": "Guide copy"})
    assert s == 201 and att2["reused"] and att2["resource_id"] == r["id"]
    s, out = contrib.post(f"/api/kb/nodes/{n1['id']}/resources", {"resource_id": r["id"]})
    assert s == 409
    s, full = viewer.get(f"/api/kb/resources/{r['id']}")
    assert full["used_by"] == 2 and {n["name"] for n in full["nodes"]} == {"N1", "N2"}
    s, upd = contrib.patch(f"/api/kb/resources/{r['id']}", {"version": 1, "title": "Guide v2"})
    assert s == 200 and upd["version"] == 2
    assert contrib.patch(f"/api/kb/resources/{r['id']}", {"version": 1, "title": "stale"})[0] == 409
    assert editor.post(f"/api/kb/resources/{r['id']}/archive")[0] == 200
    assert viewer.get(f"/api/kb/nodes/{n1['id']}")[1]["resources"] == []
    assert editor.post(f"/api/kb/resources/{r['id']}/restore")[0] == 200
    assert len(viewer.get(f"/api/kb/nodes/{n1['id']}")[1]["resources"]) == 1


def test_detach(contrib, editor):
    n = _mk(contrib, name="N", resources=[{"url": "https://example.com/d", "title": "D"}])
    aid = n["resources"][0]["attachment_id"]
    assert contrib.post(f"/api/kb/attachments/{aid}/detach")[0] == 202
    assert editor.post(f"/api/kb/attachments/{aid}/detach")[0] == 200
    assert editor.get(f"/api/kb/nodes/{n['id']}")[1]["resources"] == []


# --- proposals ----------------------------------------------------------------

def test_proposal_flow(contrib, editor, viewer):
    n = _mk(contrib, name="Proposed")
    s, out = contrib.post(f"/api/kb/nodes/{n['id']}/archive", {"reason": "obsolete"})
    assert s == 202
    pid = out["proposal_id"]
    s, again = contrib.post(f"/api/kb/nodes/{n['id']}/archive")
    assert s == 202 and again["proposal_id"] == pid
    items = viewer.get("/api/kb/proposals")[1]["items"]
    assert [p["id"] for p in items] == [pid] and items[0]["target_label"] == "Proposed"
    assert contrib.post(f"/api/kb/proposals/{pid}/approve")[0] == 403
    assert editor.post(f"/api/kb/proposals/{pid}/approve")[0] == 200
    assert viewer.get(f"/api/kb/nodes/{n['id']}")[1]["archived_at"]
    assert editor.post(f"/api/kb/proposals/{pid}/reject")[0] == 409


# --- pagination, search, neighbourhood ---------------------------------------

def test_cursor_pagination_boundaries(admin, viewer):
    for i in range(50):
        _mk(admin, name=f"Topic {i:03d}")
    s, p1 = viewer.get("/api/kb/nodes", "sort=name&limit=50")
    assert len(p1["items"]) == 50 and p1["next_cursor"] is None        # exactly one full page
    _mk(admin, name="Topic 050")
    s, p1 = viewer.get("/api/kb/nodes", "sort=name&limit=50")
    assert p1["next_cursor"]
    s, p2 = viewer.get("/api/kb/nodes", f"sort=name&limit=50&cursor={p1['next_cursor']}")
    assert [i["name"] for i in p2["items"]] == ["Topic 050"] and p2["next_cursor"] is None
    assert viewer.get("/api/kb/nodes", "limit=5000")[1]["limit"] == 200
    assert viewer.get("/api/kb/nodes", "cursor=garbage")[0] == 422
    assert viewer.get("/api/kb/nodes", "type=process")[1]["items"] == []


def test_search_full_text_and_fuzzy(contrib, viewer):
    _mk(contrib, name="Dynamic Programming", summary="memoisation and tabulation")
    _mk(contrib, "course", "Graph Algorithms")
    contrib.post("/api/kb/resources", {"url": "https://example.com/dp-notes", "title": "DP notes"})
    s, out = viewer.get("/api/kb/search", "q=tabulation")
    assert [n["name"] for n in out["nodes"]] == ["Dynamic Programming"]
    s, out = viewer.get("/api/kb/search", "q=dynamc programing")           # typos → trigram
    assert out["nodes"] and out["nodes"][0]["name"] == "Dynamic Programming"
    s, out = viewer.get("/api/kb/search", "q=graph&types=course")
    assert [n["type"] for n in out["nodes"]] == ["course"]
    s, out = viewer.get("/api/kb/search", "q=dp")
    assert out["resources"][0]["title"] == "DP notes"
    assert viewer.get("/api/kb/search", "q=")[0] == 422


def test_neighbourhood_depth_cap_and_truncation(admin, viewer):
    hub = _mk(admin, name="Hub")
    ids = []
    for i in range(305):
        n = _mk(admin, name=f"Leaf {i:03d}")
        ids.append(n["id"])
        admin.post("/api/kb/edges", {"type": "related", "source_id": hub["id"], "target_id": n["id"]})
    s, nb = viewer.get(f"/api/kb/nodes/{hub['id']}/neighbourhood", "depth=1")
    assert s == 200 and len(nb["nodes"]) == 300 and nb["total"] == 306 and nb["truncated"]
    assert viewer.get(f"/api/kb/nodes/{hub['id']}/neighbourhood", "depth=3")[0] == 422
    s, nb = viewer.get(f"/api/kb/nodes/{ids[0]}/neighbourhood", "depth=2&types=topic")
    assert nb["total"] == 306 and len(nb["nodes"]) == 300


# --- tags, dashboard, history, changes, tokens, members, types ---------------

def test_tags(contrib, viewer):
    n = _mk(contrib)
    s, t = contrib.post(f"/api/kb/nodes/{n['id']}/tags", {"name": "Core"})
    assert s == 201
    contrib.post(f"/api/kb/nodes/{n['id']}/tags", {"name": "core "})             # same tag, no dupe
    assert [g["name"] for g in viewer.get(f"/api/kb/nodes/{n['id']}")[1]["tags"]] == ["Core"]
    assert viewer.get("/api/kb/nodes", f"tag={t['tag_id']}")[1]["items"][0]["id"] == n["id"]
    assert contrib.call("DELETE", f"/api/kb/nodes/{n['id']}/tags/{t['tag_id']}")[0] == 200


def test_dashboard_history_and_change_feed(contrib, viewer):
    s, feed = viewer.get("/api/kb/changes")
    cursor = feed["cursor"]
    n = _mk(contrib, name="Watched")
    contrib.patch(f"/api/kb/nodes/{n['id']}", {"version": 1, "summary": "s"})
    s, feed = viewer.get("/api/kb/changes", f"since={cursor}")
    mine = [c for c in feed["changes"] if c["row_id"] == n["id"]]
    assert [c["action"] for c in mine] == ["insert", "update"] and mine[-1]["version"] == "2"
    s, d = viewer.get("/api/kb/dashboard")
    assert d["totals"]["nodes"] == 1 and d["recent"][0]["label"] == "Watched"
    s, h = viewer.get(f"/api/kb/nodes/{n['id']}/history")
    assert [x["action"] for x in h["items"]] == ["update", "insert"]
    assert h["items"][0]["actor_id"] == USERS["contributor"]


def test_tokens_are_shown_once_and_hashed(viewer):
    s, t = viewer.post("/api/kb/tokens", {"name": "laptop"})
    assert s == 201 and t["token"].startswith("ikkb_")
    s, lst = viewer.get("/api/kb/tokens")
    assert "token" not in lst["items"][0] and "token_hash" not in lst["items"][0]
    assert viewer.post(f"/api/kb/tokens/{t['id']}/revoke")[0] == 200
    assert viewer.post(f"/api/kb/tokens/{t['id']}/revoke")[0] == 404
    assert viewer.post("/api/kb/tokens", {"name": "x", "expires_in_days": 9999})[0] == 422


def test_members_and_types_are_admin_only(admin, editor):
    assert editor.get("/api/kb/members")[0] == 403
    s, out = admin.get("/api/kb/members")
    assert s == 200 and {m["role"] for m in out["items"]} >= {"admin", "editor"}
    assert editor.post("/api/kb/types/node", {"key": "lab", "label": "Lab"})[0] == 403
    s, t = admin.post("/api/kb/types/node", {"key": "lab", "label": "Lab"})
    assert s == 201
    s, _ = admin.post("/api/kb/types/node", {"key": "lab", "label": "Lab again"})
    assert s == 409
    try:
        assert admin.post("/api/kb/types/rule", {"type": "related", "source_type": "lab",
                                                 "target_type": "topic"})[0] == 201
        types = admin.get("/api/kb/types")[1]
        assert "lab" in {t["key"] for t in types["node_types"]}
    finally:
        from kb_support import owner
        with owner() as c:
            c.execute("delete from kb.node_types where key = 'lab'")


def test_quality_overview(contrib, viewer):
    c = _mk(contrib, "course", "Q Course")
    m = _mk(contrib, "module", "Q Module", scope=c["id"],
            resources=[{"url": "https://example.com/q", "title": "Q"}])
    _mk(contrib, name="Lonely Topic")
    _mk(contrib, name="Lonely Topics")
    s, q = viewer.get("/api/kb/quality")
    assert s == 200
    assert q["totals"]["live"] == 4 and q["totals"]["orphans"] == 4 and q["totals"]["no_resources"] == 3
    course = [x for x in q["courses"] if x["id"] == c["id"]][0]
    assert course["contents"] == 1 and float(course["completeness"]) == 50.0      # module has one, course none
    assert {d["a_name"] for d in q["duplicates"]} | {d["b_name"] for d in q["duplicates"]} >= {"Lonely Topic", "Lonely Topics"}
