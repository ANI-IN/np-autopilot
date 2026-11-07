"""Run 6 (F3): Activity reads as plain sentences.

Every entry is ONE sentence built on the server (web/lib/kb/activity.py):
WHO did WHAT to WHICH entity, old -> new where relevant. This file asserts the
exact sentence for EVERY operation of the change-propagation matrix
(tests/test_kb_propagation.py, performed the same way through the API), plus
the grouping of a bulk edit, the "deleted" mark, the filters and the search,
and that no e-mail address ever appears. Local DB only; synthetic data
(kbtest-*@interviewkickstart.com accounts read as "Kbtest Admin" and so on).
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urlencode

import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

A = "Kbtest Admin"          # kbtest-admin@… read as a name, never as the address
E = "Kbtest Editor"


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    _drop_custom()
    yield
    reset()
    _drop_custom()


def _drop_custom():
    with owner() as c:
        c.execute("truncate kb.flags, kb.templates, kb.saved_views, kb.graph_positions, kb.person_accounts")
        c.execute("delete from kb.proposals where action = 'type_change'")
        c.execute("delete from kb.node_types where not is_core")
        c.execute("delete from kb.edge_types where not is_core")
        c.execute("""update kb.node_types set owner_expected = key in ('program', 'course', 'domain', 'module', 'session', 'week')
                     where is_core""")


@pytest.fixture
def admin():
    return Client(USERS["admin"])


@pytest.fixture
def editor():
    return Client(USERS["editor"])


# ---------------------------------------------------------------------------- helpers
def _node(c, type_="topic", name="Graphs", **kw):
    s, n = c.post("/api/kb/nodes", {"type": type_, "name": name, **kw})
    assert s == 201, n
    return n


def _edge(c, type_, a, b, **kw):
    s, e = c.post("/api/kb/edges", {"type": type_, "source_id": a["id"], "target_id": b["id"], **kw})
    assert s == 201, e
    return e


def _cursor(c):
    return c.get("/api/kb/changes")[1]["cursor"]


def _activity(c, **params):
    s, out = c.get("/api/kb/activity", urlencode({"limit": 200, **params}))
    assert s == 200, out
    return out


def _since(c, cur, **params):
    return [x for x in _activity(c, **params)["items"] if x["id"] > cur]


def _said(c, cur, kind, *, table=None, row=None):
    """The sentences (newest first) of the entries after `cur` with this kind."""
    out = [x for x in _since(c, cur) if x["kind"] == kind and (table is None or x["table_name"] == table)
           and (row is None or str(x["row_id"]) == str(row) or str(row) in x["node_ids"])]
    assert out, f"no {kind} entry after {cur}: {[(x['kind'], x['sentence']) for x in _since(c, cur)]}"
    for x in out:
        assert x["sentence"] == _text(x["parts"]), x                    # the parts say the same thing
    return [x["sentence"] for x in out]


def _text(parts):
    out = []
    for p in parts:
        if p["t"] == "entity":
            out.append(f"'{p['text']}'" + (" (deleted)" if p.get("deleted") and p.get("badge", True) else ""))
        elif p["t"] == "value" and p.get("quote"):
            out.append(f"'{p['text']}'")
        else:
            out.append(p["text"])
    return "".join(out)


def _one(c, cur, kind, **kw):
    return _said(c, cur, kind, **kw)[0]


# ---------------------------------------------------------------------------- records
def test_record_sentences_and_the_deleted_mark(admin):
    cur = _cursor(admin)
    n = _node(admin, "module", "Propagation Module")
    assert _one(admin, cur, "record.create", row=n["id"]) == f"{A} created module 'Propagation Module'"
    created_id = [x for x in _since(admin, cur) if x["kind"] == "record.create"][0]["id"]

    cur = _cursor(admin)
    s, n = admin.patch(f"/api/kb/nodes/{n['id']}", {"version": n["version"], "name": "Renamed Module"})
    assert s == 200
    assert _one(admin, cur, "record.update", row=n["id"]) == f"{A} renamed module 'Propagation Module' to 'Renamed Module'"

    cur = _cursor(admin)
    assert admin.post(f"/api/kb/nodes/{n['id']}/archive")[0] == 200
    assert _one(admin, cur, "record.archive", row=n["id"]) == f"{A} archived module 'Renamed Module'"

    cur = _cursor(admin)
    assert admin.post(f"/api/kb/nodes/{n['id']}/restore")[0] == 200
    assert _one(admin, cur, "record.restore", row=n["id"]) == f"{A} restored module 'Renamed Module'"

    admin.post(f"/api/kb/nodes/{n['id']}/archive")
    cur = _cursor(admin)
    assert admin.delete(f"/api/kb/nodes/{n['id']}")[0] == 200
    assert _one(admin, cur, "record.delete", row=n["id"]) == f"{A} permanently deleted module 'Renamed Module'"

    # The record no longer exists: every older entry about it says so, and
    # links nowhere (the UI shows a "deleted" badge instead of a link).
    old = [x for x in _activity(admin, record=n["id"])["items"] if x["id"] == created_id][0]
    assert old["sentence"] == f"{A} created module 'Propagation Module' (deleted)"
    ent = [p for p in old["parts"] if p["t"] == "entity"][0]
    assert ent["deleted"] is True and ent["kind"] == "record" and old["exists_now"] is False


# ---------------------------------------------------------------------------- relationships
def test_relationship_sentences_use_the_type_labels(admin):
    # run C: "teaches" links an instructor to a course (a module's teaching is an SME assignment with a role)
    mod, ins = _node(admin, "course", "Teaching Module"), _node(admin, "instructor", "Ada Teacher")
    rel = "'Teaching Module' taught by instructor 'Ada Teacher'"
    cur = _cursor(admin)
    e = _edge(admin, "teaches", ins, mod)
    assert _one(admin, cur, "relationship.create", row=e["id"]) == f"{A} linked 'Teaching Module' to instructor 'Ada Teacher' as taught by"
    # From the source record's side (its History), the same change reads with the label.
    s, h = admin.get(f"/api/kb/nodes/{ins['id']}/history")
    assert f"{A} linked 'Ada Teacher' to course 'Teaching Module' as teaches" in [x["sentence"] for x in h["items"]]

    cur = _cursor(admin)
    s, e = admin.patch(f"/api/kb/edges/{e['id']}", {"version": e["version"], "props": {"role": "backup_1"}})
    assert s == 200, e
    assert _one(admin, cur, "relationship.update", row=e["id"]) == f"{A} set the role of the relationship {rel} to backup 1"

    cur = _cursor(admin)
    assert admin.post(f"/api/kb/edges/{e['id']}/archive")[0] == 200
    assert _one(admin, cur, "relationship.archive", row=e["id"]) == f"{A} archived the relationship {rel}"

    cur = _cursor(admin)
    assert admin.delete(f"/api/kb/edges/{e['id']}")[0] == 200
    assert _one(admin, cur, "relationship.delete", row=e["id"]) == f"{A} permanently deleted the relationship {rel}"


# ---------------------------------------------------------------------------- custom relationship types
def test_custom_relationship_type_sentences(admin):
    a, b, c = (_node(admin, "instructor", n) for n in ("Mentor A", "Mentor B", "Mentor C"))
    cur = _cursor(admin)
    s, t = admin.post("/api/kb/types/edge", {"label": "mentors", "inverse_label": "mentored by",
                                             "rules": [{"source": "instructor", "target": "instructor"}]})
    assert s == 201, t
    assert _one(admin, cur, "reltype.create", table="edge_types") == f"{A} created the relationship type 'mentors' (inverse 'mentored by')"
    assert _one(admin, cur, "reltype.update", table="edge_type_rules") == \
        f"{A} allowed the relationship type 'mentors' from instructor to instructor"
    _edge(admin, "mentors", a, b)

    cur = _cursor(admin)
    et = {x["key"]: x for x in admin.get("/api/kb/types")[1]["edge_types"]}["mentors"]
    s, out = admin.patch("/api/kb/types/edge/mentors", {"version": et["version"], "label": "coaches"})
    assert s == 200, out
    assert _one(admin, cur, "reltype.update", table="edge_types") == f"{A} renamed the relationship type 'mentors' to 'coaches'"

    s, t2 = admin.post("/api/kb/types/edge", {"label": "guides", "inverse_label": "guided by",
                                              "rules": [{"source": "instructor", "target": "instructor"}]})
    assert s == 201, t2
    _edge(admin, "guides", a, c)
    cur = _cursor(admin)
    s, out = admin.post("/api/kb/types/edge/guides/merge", {"into": "mentors"})
    assert s == 200, out
    items = _since(admin, cur)
    said = [x["sentence"] for x in items]
    assert f"{A} merged the relationship type 'guides' into 'coaches'" in said, said
    assert any(re.fullmatch(rf"{A} (changed the relationship between 'Mentor C' and instructor 'Mentor A' from guided by to "
                            rf"mentored by|linked 'Mentor C' to instructor 'Mentor A' as mentored by)", x) for x in said), said

    for x in admin.get("/api/kb/graph", "legacy=all")[1]["edges"]:
        admin.post(f"/api/kb/edges/{x['id']}/archive")
    cur = _cursor(admin)
    assert admin.post("/api/kb/types/edge/mentors/archive")[0] == 200
    assert _one(admin, cur, "reltype.archive", table="edge_types") == f"{A} archived the relationship type 'coaches'"


# ---------------------------------------------------------------------------- record types
def test_record_type_sentences(admin):
    cur = _cursor(admin)
    s, t = admin.post("/api/kb/types/node", {"label": "Workshop", "fields": [{"key": "venue", "label": "Venue", "kind": "short_text"}]})
    assert s == 201, t
    assert _one(admin, cur, "type.create") == f"{A} created the record type 'Workshop'"

    cur = _cursor(admin)
    t = {x["key"]: x for x in admin.get("/api/kb/types")[1]["node_types"]}["workshop"]
    s, out = admin.patch("/api/kb/types/node/workshop", {"version": t["version"],
                                                         "fields": t["fields"] + [{"key": "seats", "label": "Seats", "kind": "number"}]})
    assert s == 200, out
    assert re.fullmatch(rf"{A} (added the field 'Seats' to the record type 'Workshop'|changed the fields of the record type "
                        rf"'Workshop' \(added 'Seats'.*\))", _one(admin, cur, "type.update"))

    cur = _cursor(admin)
    tt = {x["key"]: x for x in admin.get("/api/kb/types")[1]["node_types"]}["topic"]
    s, out = admin.patch("/api/kb/types/node/topic", {"version": tt["version"], "owner_expected": True})
    assert s == 200, out
    assert _one(admin, cur, "type.update") == f"{A} turned on owner expected for the record type 'Topic'"


# ---------------------------------------------------------------------------- tags, owners, bulk, graph
def test_tag_owner_bulk_and_layout_sentences(admin):
    mod = _node(admin, "module", "Owned Module", owner_id=None)
    ins = _node(admin, "team_member", "Owner Person")      # run C: owners are NP team members
    cur = _cursor(admin)
    s, _ = admin.post(f"/api/kb/nodes/{mod['id']}/tags", {"name": "flagship"})
    assert s in (200, 201)
    assert _one(admin, cur, "tag.create") == f"{A} created the tag 'flagship'"
    assert _one(admin, cur, "tag.attach", row=mod["id"]) == f"{A} tagged module 'Owned Module' with 'flagship'"

    tag = admin.get("/api/kb/tags")[1]["items"][0]
    cur = _cursor(admin)
    assert admin.patch(f"/api/kb/tags/{tag['id']}", {"version": tag["version"], "name": "flagships"})[0] == 200
    assert _one(admin, cur, "tag.update") == f"{A} renamed the tag 'flagship' to 'flagships'"

    cur = _cursor(admin)
    assert admin.delete(f"/api/kb/nodes/{mod['id']}/tags/{tag['id']}")[0] == 200
    assert _one(admin, cur, "tag.detach", row=mod["id"]) == f"{A} removed the tag 'flagships' from module 'Owned Module'"

    cur = _cursor(admin)
    s, m2 = admin.patch(f"/api/kb/nodes/{mod['id']}", {"version": admin.get(f"/api/kb/nodes/{mod['id']}")[1]["version"],
                                                       "owner_record_id": ins["id"]})
    assert s == 200, m2
    assert _one(admin, cur, "record.owner", row=mod["id"]) == \
        f"{A} set the owner by role of module 'Owned Module' to team member 'Owner Person'"

    cur = _cursor(admin)
    s, out = admin.post("/api/kb/graph/positions", {"positions": [{"node_id": mod["id"], "x": 400.0, "y": -800.0}]})
    assert s == 200, out
    assert _one(admin, cur, "layout.update", row=mod["id"]) == f"{A} moved module 'Owned Module' on the graph"
    moved = [x for x in _since(admin, cur) if x["kind"] == "layout.update"][0]
    assert moved["source"] == "graph"
    assert [x["id"] for x in _since(admin, cur, source="graph")] == [moved["id"]]

    # bulk edit: each record has its own sentence, and the request reads as one entry
    ids = [_node(admin, "topic", f"Bulk {i}")["id"] for i in range(3)]
    cur = _cursor(admin)
    s, out = admin.post("/api/kb/nodes/bulk", {"ids": ids, "set": {"status": "draft"}})
    assert s == 200 and out["updated"] == 3
    for sentence in _said(admin, cur, "record.update"):
        assert re.fullmatch(rf"{A} changed the status of topic 'Bulk [012]' from \w+ to draft", sentence), sentence
    page = _activity(admin, group=1)
    rows = [x for x in page["items"] if x["id"] > cur]
    assert len(rows) == 3 and len({x["group"] for x in rows}) == 1 and rows[0]["group"]
    g = [x for x in page["groups"] if x["key"] == rows[0]["group"]][0]
    assert g["count"] == 3 and set(g["ids"]) == {x["id"] for x in rows}
    assert g["sentence"] == f"{A} updated 3 topics"
    # the three creates before it are a group of their own
    creates = [x for x in page["items"] if x["kind"] == "record.create" and x.get("label", "").startswith("Bulk ")]
    gc = [x for x in page["groups"] if x["key"] == creates[0]["group"]][0]
    assert gc["sentence"] == f"{A} created 3 topics"
    # a page boundary never splits a group when the page asks for whole groups
    small = _activity(admin, limit=2, group=1)
    assert len(small["items"]) == 3 and small["next_cursor"]
    assert len(_activity(admin, limit=2)["items"]) == 2                  # without group=1, the limit is exact


# ---------------------------------------------------------------------------- links, templates
def test_link_and_template_sentences(admin):
    mod = _node(admin, "module", "Linked Module")
    cur = _cursor(admin)
    s, r = admin.post("/api/kb/resources", {"url": "https://docs.google.com/presentation/d/f3-activity", "title": "Deck One", "kind": "slides"})
    assert s == 201, r
    assert _one(admin, cur, "link.create") == f"{A} added the link 'Deck One'"
    cur = _cursor(admin)
    s, att = admin.post(f"/api/kb/nodes/{mod['id']}/resources", {"resource_id": r["id"]})
    assert s == 201, att
    assert _one(admin, cur, "link.attach", row=mod["id"]) == f"{A} attached the link 'Deck One' to module 'Linked Module'"

    cur = _cursor(admin)
    s, r2 = admin.patch(f"/api/kb/resources/{r['id']}", {"version": r["version"], "title": "Deck One v2"})
    assert s == 200
    assert _one(admin, cur, "link.update") == f"{A} renamed the link 'Deck One' to 'Deck One v2'"

    aid = att.get("attachment_id") or att.get("id") or admin.get(f"/api/kb/nodes/{mod['id']}")[1]["resources"][0]["attachment_id"]
    cur = _cursor(admin)
    assert admin.post(f"/api/kb/attachments/{aid}/detach")[0] == 200
    assert _one(admin, cur, "link.detach", row=mod["id"]) == f"{A} detached the link 'Deck One v2' from module 'Linked Module'"

    c = _node(admin, "course", "Template Course")
    _node(admin, "module", "Template Course: One", parents=[c["id"]])
    cur = _cursor(admin)
    s, t = admin.post("/api/kb/templates", {"source_id": c["id"], "name": "Course shape"})
    assert s == 201, t
    assert _one(admin, cur, "templates.insert") == f"{A} saved the template 'Course shape' from course 'Template Course'"
    cur = _cursor(admin)
    s, out = admin.post(f"/api/kb/templates/{t['id']}/instantiate", {"name": "Copied Course"})
    assert s == 201 and out["created"] == 2
    said = _said(admin, cur, "record.create")
    assert f"{A} created course 'Copied Course'" in said
    assert f"{A} created module 'Copied Course: One' in course 'Copied Course'" in said
    assert f"{A} linked 'Copied Course: One' to course 'Copied Course' as part of" in _said(admin, cur, "relationship.create")


# ---------------------------------------------------------------------------- import, sync
def test_import_and_sync_sentences(admin):
    from lib.kb import service as svc
    cur = _cursor(admin)
    with as_user(USERS["admin"], actor_type="import") as c:
        n = svc.create_node(c, svc.Actor(USERS["admin"], "import"), {"type": "module", "name": "Imported Module"})
        c.commit()
    assert _one(admin, cur, "record.create", row=n["id"]) == f"Import (run by {A}) created module 'Imported Module'"
    imported = _since(admin, cur, source="import")
    assert imported and {x["source"] for x in imported} == {"import"} and {x["actor_type"] for x in imported} == {"import"}

    import psycopg
    from kb_support import session_dsn
    from lib.kb import sync as engine
    M = engine.load_mapping()
    src = "kbact_src"
    with owner() as c:
        c.execute(f"drop schema if exists {src} cascade")
        c.execute(f"create schema {src}")
        c.execute(f"""create table {src}.nodes (id text primary key, type text, label text, props jsonb, sensitive boolean default false);
            create table {src}.edges (id serial primary key, rel text, source_id text, target_id text, props jsonb);
            create table {src}.node_sources (node_id text, file text);
            create table {src}.node_layout (node_id text, x float8, y float8);
            create table {src}.people (canonical text, team text, title text, seniority text);
            create table {src}.people_aliases (alias text, canonical text);
            create table {src}.domain_aliases (alias text, domain text);
            create table {src}.workflow_owners (workflow_id text, suggestion text);
            create table {src}.curation_notes (id serial, scope text, row_key text, note text, position int)""")
        c.execute(f"insert into {src}.nodes (id, type, label, props) values ('ins_sync', %s, 'Synced Instructor', '{{}}')",
                  (M["roles"]["instructor"],))
    try:
        mapping = dict(M, type_fields={}, placement={}, new_record_types=[], new_relationship_types=[], relationships=[])
        cur = _cursor(admin)
        with psycopg.connect(session_dsn()) as conn:
            out = engine.run(conn, trigger="cli", actor_id=USERS["admin"], apply=True, source=src, mapping=mapping)
        assert out["status"] == "ok", out
        made = _one(admin, cur, "record.create")
        assert re.fullmatch(rf"Sync \(NP Autopilot, started by {A}\) created [a-z ]+ 'Synced Instructor'", made), made
        ran = _one(admin, cur, "sync.run")
        assert re.fullmatch(rf"Sync \(NP Autopilot, started by {A}\) finished a sync run: created 1 record\b.*", ran), ran
        assert {x["source"] for x in _since(admin, cur)} == {"sync"}
        assert {x["kind"] for x in _since(admin, cur, source="sync")} >= {"record.create", "sync.run"}
    finally:
        with owner() as c:
            c.execute(f"drop schema if exists {src} cascade")
            c.execute("truncate kb.sync_map, kb.sync_runs, kb.legacy_archive")


# ---------------------------------------------------------------------------- people: never an address
def test_person_account_sentence_never_shows_the_address(admin):
    p = _node(admin, "instructor", "Linked Person")
    cur = _cursor(admin)
    s, out = admin.post(f"/api/kb/nodes/{p['id']}/account", {"email": "kbact-person@interviewkickstart.com"})
    assert s == 200, out
    assert _one(admin, cur, "owner.account", row=p["id"]) == f"{A} linked instructor 'Linked Person' to a sign-in account"
    s, h = admin.get(f"/api/kb/nodes/{p['id']}/history")
    assert f"{A} linked instructor 'Linked Person' to a sign-in account" in [x["sentence"] for x in h["items"]]
    s, unlinked = admin.post(f"/api/kb/nodes/{p['id']}/account", {"email": None})
    assert s == 200, unlinked
    everything = json.dumps([_activity(admin), _activity(admin, q="Linked Person"), h,
                             admin.get("/api/kb/activity", "format=csv")[1]], default=str)
    assert "@" not in everything and "kbact-person" not in everything and "interviewkickstart" not in everything
    assert "actor_email" not in everything
    assert f"{A} unlinked the sign-in account from instructor 'Linked Person'" in [x["sentence"] for x in _activity(admin)["items"]]


# ---------------------------------------------------------------------------- filters and search
def test_filters_search_and_the_csv_sentence(admin, editor):
    t0 = _cursor(admin)
    mine = _node(editor, "module", "Editor Module")
    _node(admin, "topic", "Admin Topic")
    s, _ = admin.post(f"/api/kb/nodes/{mine['id']}/tags", {"name": "zebra"})
    assert s in (200, 201)
    admin.post(f"/api/kb/nodes/{mine['id']}/archive")

    # who
    by = _since(admin, t0, actor=USERS["editor"])
    assert by and {x["actor_id"] for x in by} == {USERS["editor"]}
    assert [x["sentence"] for x in by] == [f"{E} created module 'Editor Module'"]
    # what happened (op) and the old action param, still accepted
    assert {x["kind"] for x in _since(admin, t0, op="archive")} == {"record.archive"}
    assert {x["kind"] for x in _since(admin, t0, op="attach")} == {"tag.attach"}
    assert {x["action"] for x in _since(admin, t0, action="insert")} == {"insert"}
    assert {x["kind"] for x in _since(admin, t0, op="create,archive")} == {"record.create", "tag.create", "record.archive"}
    # which entity type, and which record type
    assert {x["table_name"] for x in _since(admin, t0, table="node_tags")} == {"node_tags"}
    assert {x["label"] for x in _since(admin, t0, type="module")} == {"Editor Module"}
    # source
    assert {x["source"] for x in _since(admin, t0, source="app")} == {"app"}
    assert _since(admin, t0, source="ai") == []
    # date range
    assert _activity(admin, **{"from": "2999-01-01"})["items"] == []
    assert _activity(admin, to="2000-01-01T00:00:00")["items"] == []
    # search: the entity names in the sentence (a tag, the record it is on), and the person
    zebra = [x["sentence"] for x in _since(admin, t0, q="zebra")]
    assert set(zebra) == {f"{A} created the tag 'zebra'", f"{A} tagged module 'Editor Module' with 'zebra'"}, zebra
    named = [x["sentence"] for x in _since(admin, t0, q="Editor Module")]
    assert f"{A} tagged module 'Editor Module' with 'zebra'" in named and f"{A} archived module 'Editor Module'" in named
    assert "Admin Topic" not in json.dumps(named)
    people = _since(admin, t0, q=E)
    assert people and all(x["actor_id"] == USERS["editor"] for x in people)
    # bad values are refused, with the field named
    for k, val in (("op", "explode"), ("source", "telepathy"), ("table", "secrets")):
        s, err = admin.get("/api/kb/activity", f"{k}={quote(val)}")
        assert s == 422 and err.get("field") == k, err
    # the CSV says the same sentence
    s, out = admin.get("/api/kb/activity", f"format=csv&record={mine['id']}")
    assert s == 200
    lines = out["csv"].strip().splitlines()
    assert lines[0].startswith("id,at,actor,source,action,kind,sentence")
    assert any(f"{E} created module 'Editor Module'" in line for line in lines[1:])
