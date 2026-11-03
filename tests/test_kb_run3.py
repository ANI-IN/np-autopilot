"""Run 3 — owner bugs A1/A2 and features B2 (custom relationship types), B4
(activity log) and B5 (admin-only link back to the original site), at the API
and database level. Browser coverage is in test_kb_e2e.py. Local DB only."""
from __future__ import annotations

import psycopg
import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

TEACHES = {"label": "mentors", "inverse_label": "mentored by", "rules": [{"source": "instructor", "target": "instructor"}]}


def _drop_custom():
    with owner() as c:
        c.execute("delete from kb.proposals where action in ('create', 'type_change')")
        c.execute("delete from kb.edge_types where not is_core")


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    _drop_custom()
    yield
    reset()
    _drop_custom()


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


def _node(client, type_="topic", name="Graphs", **kw):
    s, n = client.post("/api/kb/nodes", {"type": type_, "name": name, **kw})
    assert s == 201, n
    return n


# --- A1: one definition of "needs attention" ---------------------------------

def test_attention_tile_list_and_sidebar_agree(admin, editor):
    # Run 6: "No owner" counts types whose "owner expected" is ON (modules; topics are not counted).
    a = _node(editor, "module", name="No owner, no links", owner_id=None)       # no owner + not connected
    b = _node(editor, "module", name="Owned", owner_id=USERS["editor"])         # not connected
    s, r = editor.post("/api/kb/resources", {"url": "https://github.com/ik-demo/x", "title": "X", "kind": "repo"})
    assert s == 201, r
    with owner() as c:
        c.execute("insert into kb.link_checks (resource_id, status, http_status, checked_at) values (%s, 'broken', 404, now())", (r["id"],))
    s, d = admin.get("/api/kb/dashboard")
    att = d["attention"]
    s, counts = admin.get("/api/kb/counts")
    assert counts["attention"] == {"counts": att["counts"], "total": att["total"]}
    assert att["counts"]["no_owner"] == 1 and att["counts"]["orphans"] == 2 and att["counts"]["broken_links"] == 1
    # The total is the sum of every category the list shows, and each list agrees with its count.
    assert att["total"] == sum(att["counts"].values()) == 4
    for k in ("no_owner", "orphans", "broken_links", "flagged", "misfits"):
        assert len(att[k]) == att["counts"][k], k
    assert {a["id"], b["id"]} == {x["id"] for x in att["orphans"]}


# --- A2: named actors, append-only log ------------------------------------------

def test_every_activity_entry_names_its_actor(admin, editor):
    _node(editor, name="By a person")
    with owner() as c:                                      # a direct database change (fixture, migration)
        tid = c.execute("select id from kb.node_types where key = 'topic'").fetchone()[0]
        c.execute("insert into kb.nodes (type_id, name) values (%s, 'By the system')", (tid,))
    with as_user(USERS["editor"], actor_type="ai") as c:
        c.execute("insert into kb.nodes (type_id, name) values (%s, 'By the assistant')", (tid,))
        c.commit()
    s, d = admin.get("/api/kb/dashboard")
    labels = {x["label"]: x["actor_label"] for x in d["recent"]}
    assert labels["By the system"] == "System"
    assert labels["By the assistant"].startswith("AI assistant (for ")
    assert labels["By a person"] and labels["By a person"] not in ("Someone", "System")
    assert all(x["actor_label"] and x["actor_label"] != "Someone" for x in d["recent"])


def test_audit_rows_cannot_be_changed_or_deleted_by_any_api_role():
    n = None
    with as_user(USERS["admin"]) as c:
        tid = c.execute("select id from kb.node_types where key = 'topic'").fetchone()[0]
        n = c.execute("insert into kb.nodes (type_id, name) values (%s, 'Immutable') returning id", (tid,)).fetchone()[0]
        c.commit()
    for r in ("admin", "editor"):
        with as_user(USERS[r]) as c:
            # RLS hides nothing from an admin, so these reach the trigger (or the missing grant).
            with pytest.raises((psycopg.errors.InsufficientPrivilege,)):
                c.execute("update kb.audit_log set action = 'delete' where row_id = %s", (n,))
            c.rollback()
            with pytest.raises((psycopg.errors.InsufficientPrivilege,)):
                c.execute("delete from kb.audit_log where row_id = %s", (n,))
    # Even the table owner role, if it is not a superuser, is refused by the trigger.
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log where row_id = %s", (n,)).fetchone()[0] == 1


# --- B4: who sees the activity log ---------------------------------------------

def test_activity_visibility_is_enforced_by_the_database(admin, editor, viewer, contrib):
    mine = _node(admin, type_="course", name="Editor's course", owner_id=USERS["editor"])
    inside = _node(admin, type_="module", name="Module inside", parents=[mine["id"]])
    other = _node(admin, name="Someone else's topic")
    s, all_ = admin.get("/api/kb/activity")
    assert {mine["id"], inside["id"], other["id"]} <= {x["row_id"] for x in all_["items"]}
    s, ed = editor.get("/api/kb/activity")
    seen = {x["row_id"] for x in ed["items"]}
    assert mine["id"] in seen and inside["id"] in seen and other["id"] not in seen
    for c in (viewer, contrib):
        s, out = c.get("/api/kb/activity")
        assert s == 200 and out["items"] == []
        s, h = c.get(f"/api/kb/nodes/{other['id']}/history")             # a record's History still works
        assert s == 200 and h["items"][0]["action"] == "insert"
    with as_user(USERS["viewer"]) as c:
        assert c.execute("select count(*) from kb.audit_log").fetchone()[0] == 0
        assert c.execute("select count(*) from kb.changes").fetchone()[0] > 0   # live updates still flow


def test_activity_filters_diff_cursor_and_csv(admin, editor):
    n = _node(editor, name="Diffed", summary="before")
    s, cur = admin.get(f"/api/kb/nodes/{n['id']}")
    s, _ = editor.patch(f"/api/kb/nodes/{n['id']}", {"version": cur["version"], "summary": "after =1+1"})
    assert s == 200
    for i in range(5):
        _node(admin, name=f"Filler {i}")
    s, up = admin.get("/api/kb/activity", f"action=update&record={n['id']}")
    assert [x["action"] for x in up["items"]] == ["update"]
    assert {"field": "summary", "before": "before", "after": "after =1+1"} in up["items"][0]["changes"]
    s, byme = admin.get("/api/kb/activity", f"actor={USERS['editor']}&table=nodes")
    assert {x["actor_id"] for x in byme["items"]} == {USERS["editor"]}
    s, q = admin.get("/api/kb/activity", "q=Filler 3")
    assert [x["label"] for x in q["items"]] == ["Filler 3"]
    s, p1 = admin.get("/api/kb/activity", "limit=3&table=nodes")
    assert len(p1["items"]) == 3 and p1["next_cursor"]
    s, p2 = admin.get("/api/kb/activity", f"limit=3&table=nodes&cursor={p1['next_cursor']}")
    assert not {x["id"] for x in p1["items"]} & {x["id"] for x in p2["items"]}
    s, src = admin.get("/api/kb/activity", "source=ai")
    assert src["items"] == []
    s, csv = admin.get("/api/kb/activity", f"format=csv&record={n['id']}")
    lines = csv["csv"].strip().splitlines()
    assert lines[0].startswith("id,at,actor,source,action") and len(lines) == 3
    assert "'" not in lines[0] and "after =1+1" in csv["csv"]


# --- B2: custom relationship types ---------------------------------------------

def test_admin_creates_a_reviewed_relationship_type(admin):
    s, t = admin.post("/api/kb/types/edge", TEACHES)
    assert s == 201 and t["review_status"] == "reviewed"


def test_editor_type_is_usable_now_unreviewed_and_queued_for_an_admin(admin, editor):
    s, t = editor.post("/api/kb/types/edge", TEACHES)
    assert s == 201 and t["review_status"] == "unreviewed"
    a = _node(editor, type_="instructor", name="Asha")
    b = _node(editor, type_="instructor", name="Ben")
    s, e = editor.post("/api/kb/edges", {"type": "mentors", "source_id": a["id"], "target_id": b["id"]})
    assert s == 201, e
    s, props = admin.get("/api/kb/proposals")
    review = [p for p in props["items"] if (p["payload"] or {}).get("op") == "edge_review"]
    assert len(review) == 1
    # The admin confirms it and renames it on the way.
    s, out = admin.post(f"/api/kb/proposals/{review[0]['id']}/approve", {"label": "mentors (1:1)"})
    assert s == 200, out
    s, types = admin.get("/api/kb/types")
    m = next(x for x in types["edge_types"] if x["key"] == "mentors")
    assert m["review_status"] == "reviewed" and m["label"] == "mentors (1:1)"


def test_contributor_can_only_propose_a_relationship_type(admin, contrib):
    s, out = contrib.post("/api/kb/types/edge", TEACHES)
    assert s == 202 and out["proposal_id"]
    s, types = admin.get("/api/kb/types")
    assert not any(x["key"] == "mentors" for x in types["edge_types"])
    s, _ = admin.post(f"/api/kb/proposals/{out['proposal_id']}/approve")
    s, types = admin.get("/api/kb/types")
    assert next(x for x in types["edge_types"] if x["key"] == "mentors")["review_status"] == "reviewed"


def test_database_enforces_who_may_create_relationship_types():
    with as_user(USERS["editor"]) as c:                    # an editor cannot create a REVIEWED type
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into kb.edge_types (key, label) values ('x_one', 'x one')")
        c.rollback()
        c.execute("insert into kb.edge_types (key, label, review_status) values ('x_two', 'x two', 'unreviewed')")
    with as_user(USERS["contributor"]) as c:               # a contributor cannot create one at all
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into kb.edge_types (key, label, review_status) values ('x_three', 'x three', 'unreviewed')")


@pytest.mark.parametrize("label,inverse", [("Teaches", None), ("teach", None), ("taught  by", None), ("instructs", "Taught By"),
                                           ("TEACHES", "learns from")])
def test_near_duplicate_relationship_names_are_blocked_with_a_suggestion(admin, label, inverse):
    body = {"label": label, "rules": [{"source": "instructor", "target": "course"}]}
    if inverse:
        body["inverse_label"] = inverse
    s, out = admin.post("/api/kb/types/edge", body)
    assert s == 409 and out["existing"]["key"] == "teaches", out
    with owner() as c:                                     # and the database refuses it even without the service
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("insert into kb.edge_types (key, label, inverse_label) values ('dup', %s, %s)", (label, inverse))


def test_merge_moves_relationships_previews_counts_and_is_audited(admin, editor):
    s, _ = admin.post("/api/kb/types/edge", TEACHES)
    s, _ = admin.post("/api/kb/types/edge", {"label": "coaches", "inverse_label": "coached by",
                                             "rules": [{"source": "instructor", "target": "instructor"}]})
    a, b, c_ = (_node(editor, type_="instructor", name=n) for n in ("A", "B", "C"))
    for src, tgt, t in ((a, b, "mentors"), (a, c_, "mentors"), (a, b, "coaches")):
        s, e = editor.post("/api/kb/edges", {"type": t, "source_id": src["id"], "target_id": tgt["id"]})
        assert s == 201, e
    s, prev = admin.post("/api/kb/types/edge/coaches/merge", {"into": "mentors", "preview": True})
    assert prev["relationships"] == 1 and prev["duplicates"] == 1 and prev["moved"] == 0
    s, out = admin.post("/api/kb/types/edge/coaches/merge", {"into": "mentors"})
    assert s == 200, out
    with owner() as c:
        live = c.execute("""select et.key, count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                            where e.archived_at is null and et.key in ('mentors', 'coaches') group by et.key""").fetchall()
        assert dict(live) == {"mentors": 2}
        merged = c.execute("select archived_at is not null, merged_into is not null from kb.edge_types where key = 'coaches'").fetchone()
        assert merged == (True, True)
        assert c.execute("select count(*) from kb.audit_log where table_name = 'edge_types' and action = 'update' "
                         "and after ->> 'merged_into' is not null").fetchone()[0] == 1
    s, _ = editor.post("/api/kb/types/edge/mentors/merge", {"into": "teaches"})
    assert s == 403


# --- B5: admin-only link back to the original site -------------------------------

@pytest.mark.parametrize("r", ["editor", "contributor", "viewer"])
def test_only_admins_get_the_link_back_to_the_original_site(r):
    s, me = Client(USERS["admin"]).get("/api/kb/me")
    assert me["admin_links"] == [{"label": "Back to NP Autopilot", "href": "/", "testid": "back-to-site"}]
    s, me = Client(USERS[r]).get("/api/kb/me")
    assert s == 200 and "admin_links" not in me


# --- B2: the rest of the CRUD matrix ---------------------------------------------

def test_tags_rename_merge_archive_and_restore(admin, editor):
    n1, n2 = _node(editor, name="Tagged one"), _node(editor, name="Tagged two")
    for n, t in ((n1, "graphs"), (n2, "graph")):
        s, _ = editor.post(f"/api/kb/nodes/{n['id']}/tags", {"name": t})
        assert s in (200, 201)
    tags = {t["name"]: t for t in editor.get("/api/kb/tags")[1]["items"]}
    s, out = editor.patch(f"/api/kb/tags/{tags['graph']['id']}", {"version": tags["graph"]["version"], "name": "Graphs"})
    assert s == 422                                                     # already exists: merge instead
    s, out = editor.post(f"/api/kb/tags/{tags['graph']['id']}/merge", {"into": tags["graphs"]["id"]})
    assert s == 200 and out["records"] == 1
    tags = {t["name"]: t for t in editor.get("/api/kb/tags")[1]["items"]}
    assert list(tags) == ["graphs"] and tags["graphs"]["used_by"] == 2
    s, out = editor.post(f"/api/kb/tags/{tags['graphs']['id']}/archive")
    assert s == 200 and len(out["removed_from"]) == 2 and editor.get("/api/kb/tags")[1]["items"] == []
    s, _ = editor.post(f"/api/kb/tags/{tags['graphs']['id']}/restore", {"records": out["removed_from"]})
    assert editor.get("/api/kb/tags")[1]["items"][0]["used_by"] == 2


def test_member_removal_is_admin_only_audited_and_reversible(admin, editor):
    s, _ = editor.post(f"/api/kb/members/{USERS['contributor']}/remove")
    assert s == 403
    s, _ = admin.post(f"/api/kb/members/{USERS['admin']}/remove")
    assert s == 422                                                     # not yourself
    s, out = admin.post(f"/api/kb/members/{USERS['contributor']}/remove")
    assert s == 200
    assert USERS["contributor"] not in {m["user_id"] for m in admin.get("/api/kb/members")[1]["items"]}
    s, out = admin.post(f"/api/kb/members/{USERS['contributor']}", {"role": "contributor"})
    assert s == 200 and USERS["contributor"] in {m["user_id"] for m in admin.get("/api/kb/members")[1]["items"]}
    s, act = admin.get("/api/kb/activity", "table=memberships")
    assert {"update"} <= {x["action"] for x in act["items"]}


def test_template_rename_and_restore(admin, editor):
    c = _node(editor, type_="course", name="Template source")
    s, t = editor.post("/api/kb/templates", {"source_id": c["id"], "name": "Course shape"})
    assert s == 201, t
    s, out = editor.patch(f"/api/kb/templates/{t['id']}", {"name": "Course shape v2"})
    assert s == 200 and out["name"] == "Course shape v2"
    editor.post(f"/api/kb/templates/{t['id']}/archive")
    assert editor.get("/api/kb/templates")[1]["items"] == []
    editor.post(f"/api/kb/templates/{t['id']}/restore")
    assert [x["name"] for x in editor.get("/api/kb/templates")[1]["items"]] == ["Course shape v2"]


def test_relationship_type_can_be_changed_in_one_step(admin, editor):
    s, _ = admin.post("/api/kb/types/edge", {"label": "explains", "inverse_label": "explained by", "rules": [{"source": "module", "target": "topic"}]})
    assert s == 201
    m = _node(editor, type_="module", name="Retype module")
    t = _node(editor, name="Retype topic")
    s, e = editor.post("/api/kb/edges", {"type": "covers", "source_id": m["id"], "target_id": t["id"], "note": "keep me"})
    assert s == 201, e
    s, e2 = editor.post(f"/api/kb/edges/{e['id']}/retype", {"type": "explains"})
    assert s == 201 and e2["type"] == "explains" and e2["note"] == "keep me" and e2["source_id"] == m["id"]
    assert editor.get(f"/api/kb/edges/{e['id']}")[1]["archived_at"]                # the old one is kept, archived
    s, bad = editor.post(f"/api/kb/edges/{e2['id']}/retype", {"type": "teaches"})  # not allowed module -> topic
    assert s == 422 and not editor.get(f"/api/kb/edges/{e2['id']}")[1]["archived_at"]   # nothing changed


def test_dashboard_cache_is_invalidated_by_any_write(admin, editor):
    s, d1 = admin.get("/api/kb/dashboard")
    _node(editor, name="Fresh after cache")
    s, d2 = admin.get("/api/kb/dashboard")
    assert d2["totals"]["nodes"] == d1["totals"]["nodes"] + 1
    s, c2 = admin.get("/api/kb/counts")
    assert c2["totals"]["nodes"] == d2["totals"]["nodes"]
