"""Run 6 (B1): every admin change appears everywhere — the API half of the
CHANGE-PROPAGATION MATRIX (the browser half is test_kb_propagation_e2e.py).

For EVERY write path in the brief, performed as an admin (the sync and the
import as themselves), this asserts:
  1. the change feed (GET /api/kb/changes, what every open page polls) carries
     the expected `kind` with the records to refresh in `node_ids`
     (docs/architecture/contracts.md §2);
  2. GET /api/kb/graph (the Graph page) returns the new state;
  3. the NP Autopilot map's routes ("/": /api/structure, /api/node, /api/search)
     return it too, read from kb (web/lib/kb/npmap.py), and the structure's
     ETag moved so a cached copy is revalidated.
Also the decisions: contributors attach links and relationships directly while
their field edits wait in Approvals (0033), and NP_MAP_SOURCE=old rolls the map
back to the old tables. Local DB only; synthetic data.
"""
from __future__ import annotations

import base64
import json
import struct

import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

ROWS: list[dict] = []            # the matrix, printed at the end

from lib.kb import sync as _engine                                      # noqa: E402
ROLES = _engine.load_mapping()["roles"]


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
def viewer():
    return Client(USERS["viewer"])


@pytest.fixture
def contrib():
    return Client(USERS["contributor"])


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


def _feed(c, since):
    s, out = c.get("/api/kb/changes", f"since={since}&limit=500")
    assert s == 200
    return out["changes"]


def _graph(c, q="legacy=all"):
    s, g = c.get("/api/kb/graph", q)
    assert s == 200, g
    return g


def _types(c):
    return c.get("/api/kb/types")[1]


def decode(o: dict) -> dict:
    """The map's columnar structure, decoded as public/index.html decodeStructure() does."""
    ev = base64.b64decode(o["e"])
    tri = struct.unpack(f"<{len(ev) // 2}H", ev) if ev else ()
    nodes = {o["ids"][i]: {"type": o["types"][o["t"][i]], "label": o["labels"][i], "props": o["np"].get(str(i), {})}
             for i in range(o["n"])}
    edges = [(o["ids"][tri[3 * j]], o["ids"][tri[3 * j + 1]], o["rels"][tri[3 * j + 2]]) for j in range(o["m"])]
    return {"nodes": nodes, "edges": edges}


def _map(c):
    """GET /api/structure as the map does, with its ETag."""
    import io
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/structure", "QUERY_STRING": "", "CONTENT_LENGTH": "0",
           "wsgi.input": io.BytesIO(b""), "HTTP_AUTHORIZATION": _auth(c)}
    out = {}

    def sr(status, headers):
        out["status"] = int(status.split()[0])
        out["etag"] = dict(headers).get("etag")
    body = b"".join(c.app(env, sr))
    assert out["status"] == 200
    return decode(json.loads(body)), out["etag"]


def _auth(c):
    from kb_support import token_for
    return f"Bearer {token_for(c.user_id)}"


def _row(op, kind, api, graph, npmap):
    ROWS.append({"op": op, "kind": kind, "api": api, "graph": graph, "map": npmap})


def _kinds(changes):
    return [c["kind"] for c in changes]


def _with(changes, kind, *ids):
    hit = [c for c in changes if c["kind"] == kind and all(str(i) in [str(x) for x in c["node_ids"]] for i in ids)]
    assert hit, f"no {kind} change naming {ids} in {_kinds(changes)}"
    return hit


# ---------------------------------------------------------------------------- records
def test_records_create_update_archive_restore_delete(admin, viewer):
    m0, tag0 = _map(viewer)
    cur = _cursor(viewer)
    n = _node(admin, "module", "Propagation Module")
    ch = _feed(viewer, cur)
    _with(ch, "record.create", n["id"])
    assert n["id"] in {x["id"] for x in _graph(viewer)["nodes"]}
    m, tag = _map(viewer)
    assert m["nodes"][n["id"]]["label"] == "Propagation Module" and tag != tag0
    _row("record create", "record.create", True, True, True)

    cur = _cursor(viewer)
    s, n = admin.patch(f"/api/kb/nodes/{n['id']}", {"version": n["version"], "name": "Renamed Module"})
    assert s == 200
    _with(_feed(viewer, cur), "record.update", n["id"])
    assert {x["id"]: x["name"] for x in _graph(viewer)["nodes"]}[n["id"]] == "Renamed Module"
    assert _map(viewer)[0]["nodes"][n["id"]]["label"] == "Renamed Module"
    s, hits = viewer.get("/api/search", "q=Renamed%20Mod")
    assert s == 200 and [h["id"] for h in hits["results"]] == [n["id"]]
    _row("record update (rename)", "record.update", True, True, True)

    cur = _cursor(viewer)
    s, out = admin.post(f"/api/kb/nodes/{n['id']}/archive")
    assert s == 200
    _with(_feed(viewer, cur), "record.archive", n["id"])
    assert n["id"] not in {x["id"] for x in _graph(viewer)["nodes"]}
    assert n["id"] not in _map(viewer)[0]["nodes"]
    assert viewer.get("/api/node", f"id={n['id']}")[1] == {"error": "not_found"}
    _row("record archive", "record.archive", True, True, True)

    cur = _cursor(viewer)
    assert admin.post(f"/api/kb/nodes/{n['id']}/restore")[0] == 200
    _with(_feed(viewer, cur), "record.restore", n["id"])
    assert n["id"] in {x["id"] for x in _graph(viewer)["nodes"]}
    assert n["id"] in _map(viewer)[0]["nodes"]
    _row("record restore", "record.restore", True, True, True)

    admin.post(f"/api/kb/nodes/{n['id']}/archive")
    cur = _cursor(viewer)
    s, out = admin.delete(f"/api/kb/nodes/{n['id']}")
    assert s == 200, out
    _with(_feed(viewer, cur), "record.delete", n["id"])
    assert n["id"] not in {x["id"] for x in _graph(viewer, "legacy=all&archived=1")["nodes"]}
    assert n["id"] not in _map(viewer)[0]["nodes"]
    _row("record permanent delete", "record.delete", True, True, True)


# ---------------------------------------------------------------------------- relationships
def test_relationships_create_update_archive_delete(admin, viewer):
    mod, ins = _node(admin, "module", "Teaching Module"), _node(admin, "instructor", "Ada Teacher")
    cur = _cursor(viewer)
    e = _edge(admin, "teaches", ins, mod)
    _with(_feed(viewer, cur), "relationship.create", ins["id"], mod["id"])
    assert e["id"] in {x["id"] for x in _graph(viewer)["edges"]}
    assert (ins["id"], mod["id"], "teaches") in _map(viewer)[0]["edges"]
    _row("relationship create", "relationship.create", True, True, True)

    cur = _cursor(viewer)
    s, e = admin.patch(f"/api/kb/edges/{e['id']}", {"version": e["version"], "props": {"role": "backup_1"}})
    assert s == 200, e
    _with(_feed(viewer, cur), "relationship.update", ins["id"], mod["id"])
    assert {x["id"]: x["role"] for x in _graph(viewer)["edges"]}[e["id"]] == "backup_1"
    edges = _map(viewer)[0]["edges"]
    assert (mod["id"], ins["id"], ROLES["teaching_reversed"]) in edges     # the map's current-mastersheet relation
    s, det = viewer.get("/api/node", f"id={mod['id']}&detail=1")
    assert any(x["props"].get("instructor_role") == "backup_1" for x in det["edges"])
    _row("relationship update (role)", "relationship.update", True, True, True)

    cur = _cursor(viewer)
    assert admin.post(f"/api/kb/edges/{e['id']}/archive")[0] == 200
    _with(_feed(viewer, cur), "relationship.archive", ins["id"], mod["id"])
    assert e["id"] not in {x["id"] for x in _graph(viewer)["edges"]}
    assert not [x for x in _map(viewer)[0]["edges"] if {x[0], x[1]} == {mod["id"], ins["id"]}]
    _row("relationship archive", "relationship.archive", True, True, True)

    cur = _cursor(viewer)
    assert admin.delete(f"/api/kb/edges/{e['id']}")[0] == 200
    _with(_feed(viewer, cur), "relationship.delete", ins["id"], mod["id"])
    assert e["id"] not in {x["id"] for x in _graph(viewer, "legacy=all&archived=1")["edges"]}
    _row("relationship permanent delete", "relationship.delete", True, True, True)


# ---------------------------------------------------------------------------- custom relationship types
def test_custom_relationship_types_create_rename_merge_archive(admin, viewer):
    a, b, c = (_node(admin, "instructor", n) for n in ("Mentor A", "Mentor B", "Mentor C"))
    cur = _cursor(viewer)
    s, t = admin.post("/api/kb/types/edge", {"label": "mentors", "inverse_label": "mentored by",
                                             "rules": [{"source": "instructor", "target": "instructor"}]})
    assert s == 201, t
    ch = _feed(viewer, cur)
    assert "reltype.create" in _kinds(ch)
    et = {x["key"]: x for x in _types(viewer)["edge_types"]}["mentors"]
    core = [x for x in _types(viewer)["edge_types"] if x["is_core"]]
    assert et["color"] and et["line_style"] in ("solid", "dashed", "dotted")
    assert (et["color"], et["line_style"]) not in {(x["color"], x["line_style"]) for x in core}   # its own style
    e1 = _edge(admin, "mentors", a, b)
    assert {x["id"]: x["type"] for x in _graph(viewer)["edges"]}[e1["id"]] == "mentors"
    assert (a["id"], b["id"], "mentors") in _map(viewer)[0]["edges"]
    _row("custom relationship type create (+ its first relationship)", "reltype.create", True, True, True)

    cur = _cursor(viewer)
    s, out = admin.patch("/api/kb/types/edge/mentors", {"version": et["version"], "label": "coaches"})
    assert s == 200, out
    assert "reltype.update" in _kinds(_feed(viewer, cur))
    assert {x["key"]: x["label"] for x in _types(viewer)["edge_types"]}["mentors"] == "coaches"
    _row("custom relationship type rename", "reltype.update", True, True, True)

    s, t2 = admin.post("/api/kb/types/edge", {"label": "guides", "inverse_label": "guided by",
                                              "rules": [{"source": "instructor", "target": "instructor"}]})
    _edge(admin, "guides", a, c)
    cur = _cursor(viewer)
    s, out = admin.post("/api/kb/types/edge/guides/merge", {"into": "mentors"})
    assert s == 200, out
    kinds = _kinds(_feed(viewer, cur))
    assert "reltype.update" in kinds and ("relationship.update" in kinds or "relationship.create" in kinds)
    types_now = {x["type"] for x in _graph(viewer)["edges"]}
    assert types_now == {"mentors"}
    assert {x[2] for x in _map(viewer)[0]["edges"]} == {"mentors"}
    _row("custom relationship type merge", "reltype.update", True, True, True)

    admin.post(f"/api/kb/edges/{e1['id']}/archive")
    for x in _graph(viewer)["edges"]:
        admin.post(f"/api/kb/edges/{x['id']}/archive")
    cur = _cursor(viewer)
    s, out = admin.post("/api/kb/types/edge/mentors/archive")
    assert s == 200, out
    assert "reltype.archive" in _kinds(_feed(viewer, cur))
    assert "mentors" not in {x["key"] for x in _types(viewer)["edge_types"]}
    assert not _map(viewer)[0]["edges"]
    _row("custom relationship type archive", "reltype.archive", True, True, True)


# ---------------------------------------------------------------------------- record types and fields
def test_record_type_and_field_changes(admin, viewer):
    cur = _cursor(viewer)
    s, t = admin.post("/api/kb/types/node", {"label": "Workshop", "fields": [{"key": "venue", "label": "Venue", "kind": "short_text"}]})
    assert s == 201, t
    assert "type.create" in _kinds(_feed(viewer, cur))
    w = _node(admin, "workshop", "Graph Workshop", props={"venue": "Room 1"})
    assert {x["id"]: x["type"] for x in _graph(viewer)["nodes"]}[w["id"]] == "workshop"
    _map(viewer)
    s, nd = viewer.get("/api/node", f"id={w['id']}")
    assert nd["node"]["type"] == "workshop" and nd["node"]["props"]["venue"] == "Room 1"
    _row("record type create (+ a record of it)", "type.create", True, True, True)

    cur = _cursor(viewer)
    t = {x["key"]: x for x in _types(admin)["node_types"]}["workshop"]
    s, t2 = admin.patch("/api/kb/types/node/workshop", {"version": t["version"],
                                                        "fields": t["fields"] + [{"key": "seats", "label": "Seats", "kind": "number"}]})
    assert s == 200, t2
    assert "type.update" in _kinds(_feed(viewer, cur))
    assert "seats" in {f["key"] for f in {x["key"]: x for x in _types(viewer)["node_types"]}["workshop"]["fields"]}
    _row("record type field change", "type.update", True, True, True)

    # owner expected (decision): editable by admins; "No owner" follows it
    _node(admin, "topic", "Ownerless Topic", owner_id=None)
    assert viewer.get("/api/kb/quality/no-owner")[1]["total"] == 0
    cur = _cursor(viewer)
    tt = {x["key"]: x for x in _types(admin)["node_types"]}["topic"]
    s, out = admin.patch("/api/kb/types/node/topic", {"version": tt["version"], "owner_expected": True})
    assert s == 200 and out.get("owner_expected", True)
    assert "type.update" in _kinds(_feed(viewer, cur))
    assert {x["key"]: x for x in _types(viewer)["node_types"]}["topic"]["owner_expected"] is True
    assert viewer.get("/api/kb/quality/no-owner")[1]["total"] == 1
    assert admin.get("/api/kb/counts")[1]["attention"]["counts"]["no_owner"] == 1
    _row("owner expected (type setting)", "type.update", True, True, True)


# ---------------------------------------------------------------------------- tags, owners, bulk, graph edits
def test_tags_owners_bulk_and_graph_edits(admin, viewer):
    mod = _node(admin, "module", "Owned Module", owner_id=None)
    ins = _node(admin, "instructor", "Owner Person")
    cur = _cursor(viewer)
    s, _ = admin.post(f"/api/kb/nodes/{mod['id']}/tags", {"name": "flagship"})
    assert s in (200, 201)
    _with(_feed(viewer, cur), "tag.attach", mod["id"])
    _row("tag attach", "tag.attach", True, True, True)
    tag = viewer.get("/api/kb/tags")[1]["items"][0]
    cur = _cursor(viewer)
    assert admin.patch(f"/api/kb/tags/{tag['id']}", {"version": tag["version"], "name": "flagships"})[0] == 200
    assert "tag.update" in _kinds(_feed(viewer, cur))
    _row("tag rename", "tag.update", True, True, True)
    cur = _cursor(viewer)
    assert admin.delete(f"/api/kb/nodes/{mod['id']}/tags/{tag['id']}")[0] == 200
    _with(_feed(viewer, cur), "tag.detach", mod["id"])
    _row("tag detach", "tag.detach", True, True, True)

    cur = _cursor(viewer)
    s, m2 = admin.patch(f"/api/kb/nodes/{mod['id']}", {"version": admin.get(f"/api/kb/nodes/{mod['id']}")[1]["version"],
                                                       "owner_record_id": ins["id"]})
    assert s == 200, m2
    _with(_feed(viewer, cur), "record.owner", mod["id"])
    assert {x["id"]: x["owner_record_id"] for x in _graph(viewer)["nodes"]}[mod["id"]] == ins["id"]
    _row("owner (by role)", "record.owner", True, True, True)

    ids = [_node(admin, "topic", f"Bulk {i}")["id"] for i in range(3)]
    cur = _cursor(viewer)
    s, out = admin.post("/api/kb/nodes/bulk", {"ids": ids, "set": {"status": "draft"}})
    assert s == 200 and out["updated"] == 3
    ch = _feed(viewer, cur)
    for i in ids:
        _with(ch, "record.update", i)
    assert {x["id"]: x["status"] for x in _graph(viewer)["nodes"] if x["id"] in ids} == {i: "draft" for i in ids}
    _row("bulk edit (3 records)", "record.update x3", True, True, True)

    _, etag0 = _map(viewer)
    cur = _cursor(viewer)
    s, out = admin.post("/api/kb/graph/positions", {"positions": [{"node_id": mod["id"], "x": 400.0, "y": -800.0}]})
    assert s == 200, out
    _with(_feed(viewer, cur), "layout.update", mod["id"])
    s, pos = viewer.get("/api/kb/graph/positions", f"ids={mod['id']}")
    assert pos["items"][0]["x"] == 400.0
    m, etag = _map(viewer)
    assert etag != etag0
    _row("graph edit (position)", "layout.update", True, True, True)


# ---------------------------------------------------------------------------- links, templates
def test_links_and_template_creates(admin, viewer):
    mod = _node(admin, "module", "Linked Module")
    s, r = admin.post("/api/kb/resources", {"url": "https://docs.google.com/presentation/d/b1-propagation", "title": "Deck One", "kind": "slides"})
    assert s == 201, r
    cur = _cursor(viewer)
    s, att = admin.post(f"/api/kb/nodes/{mod['id']}/resources", {"resource_id": r["id"]})
    assert s == 201, att
    _with(_feed(viewer, cur), "link.attach", mod["id"])
    m = _map(viewer)[0]
    deck = "link:" + r["id"]
    assert m["nodes"][deck]["label"] == "Deck One" and (mod["id"], deck) in {(x[0], x[1]) for x in m["edges"]}
    _row("link attach (a deck on a module)", "link.attach", True, True, True)

    cur = _cursor(viewer)
    s, r2 = admin.patch(f"/api/kb/resources/{r['id']}", {"version": r["version"], "title": "Deck One v2"})
    assert s == 200
    assert "link.update" in _kinds(_feed(viewer, cur))
    assert _map(viewer)[0]["nodes"][deck]["label"] == "Deck One v2"
    _row("link update (title)", "link.update", True, True, True)

    aid = att.get("attachment_id") or att.get("id")
    if not aid:
        aid = admin.get(f"/api/kb/nodes/{mod['id']}")[1]["resources"][0]["attachment_id"]
    cur = _cursor(viewer)
    assert admin.post(f"/api/kb/attachments/{aid}/detach")[0] == 200
    _with(_feed(viewer, cur), "link.detach", mod["id"])
    assert deck not in _map(viewer)[0]["nodes"]
    _row("link detach", "link.detach", True, True, True)

    c = _node(admin, "course", "Template Course")
    _node(admin, "module", "Template Course: One", parents=[c["id"]])
    s, t = admin.post("/api/kb/templates", {"source_id": c["id"], "name": "Course shape"})
    assert s == 201, t
    cur = _cursor(viewer)
    s, out = admin.post(f"/api/kb/templates/{t['id']}/instantiate", {"name": "Copied Course"})
    assert s == 201 and out["created"] == 2
    ch = _feed(viewer, cur)
    assert _kinds(ch).count("record.create") == 2 and "relationship.create" in _kinds(ch)
    names = {x["name"] for x in _graph(viewer)["nodes"]}
    assert {"Copied Course", "Copied Course: One"} <= names
    assert {"Copied Course", "Copied Course: One"} <= {x["label"] for x in _map(viewer)[0]["nodes"].values()}
    _row("template create (instantiate)", "record.create x2", True, True, True)


# ---------------------------------------------------------------------------- import and sync
def test_import_and_sync_changes_flow_the_same_way(admin, viewer):
    from lib.kb import service as svc
    cur = _cursor(viewer)
    with as_user(USERS["admin"], actor_type="import") as c:
        n = svc.create_node(c, svc.Actor(USERS["admin"], "import"), {"type": "module", "name": "Imported Module"})
        c.commit()
    n = {"id": str(n["id"])}
    ch = [x for x in _feed(viewer, cur) if x["kind"] == "record.create"]
    assert ch and ch[0]["actor_type"] == "import"
    assert n["id"] in {x["id"] for x in _graph(viewer)["nodes"]} and n["id"] in _map(viewer)[0]["nodes"]
    _row("import (Sheets importer, as import)", "record.create", True, True, True)

    # A sync run over a tiny synthetic source (tests/test_kb_sync.py does the rules).
    import psycopg
    from kb_support import session_dsn
    from lib.kb import sync as engine
    M = engine.load_mapping()
    src = "kbprop_src"
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
        cur = _cursor(viewer)
        with psycopg.connect(session_dsn()) as conn:
            out = engine.run(conn, trigger="cli", actor_id=USERS["admin"], apply=True, source=src, mapping=mapping)
        assert out["status"] == "ok", out
        ch = _feed(viewer, cur)
        assert "sync.run" in _kinds(ch) and "record.create" in _kinds(ch)
        assert all(x["actor_type"] == "sync" for x in ch if x["kind"] == "record.create")
        assert "Synced Instructor" in {x["name"] for x in _graph(viewer)["nodes"]}
        assert "ins_sync" in _map(viewer)[0]["nodes"]                    # the map keeps the projection id
        _row("sync run (scheduled / Sync now)", "sync.run + record.create", True, True, True)
    finally:
        with owner() as c:
            c.execute(f"drop schema if exists {src} cascade")
            c.execute("truncate kb.sync_map, kb.sync_runs, kb.legacy_archive")


# ---------------------------------------------------------------------------- people
def test_person_account_link_is_a_change_only_event(admin, viewer):
    p = _node(admin, "instructor", "Linked Person")
    cur = _cursor(viewer)
    s, out = admin.post(f"/api/kb/nodes/{p['id']}/account", {"email": "kbprop-person@interviewkickstart.com"})
    assert s == 200, out
    ch = _with(_feed(viewer, cur), "owner.account", p["id"])
    assert "kbprop-person" not in json.dumps(ch)                       # no address in the feed
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log where (before::text || after::text) like '%%kbprop-person%%'").fetchone()[0] == 0
    _row("person account (e-mail link)", "owner.account", True, True, True)


# ---------------------------------------------------------------------------- decisions
def test_contributors_attach_links_and_relationships_directly_but_edits_wait_for_approval(admin, contrib, viewer):
    mod, ins = _node(admin, "module", "Contrib Module"), _node(admin, "instructor", "Contrib Teacher")
    s, r = contrib.post("/api/kb/resources", {"url": "https://example.com/b1-contrib", "title": "Notes", "kind": "doc"})
    assert s == 201, r
    s, att = contrib.post(f"/api/kb/nodes/{mod['id']}/resources", {"resource_id": r["id"]})
    assert s == 201, att                                                # direct
    assert contrib.post("/api/kb/edges", {"type": "teaches", "source_id": ins["id"], "target_id": mod["id"]})[0] == 201
    s, out = contrib.patch(f"/api/kb/nodes/{mod['id']}", {"version": mod["version"], "name": "Changed by a contributor"})
    assert s == 202 and out["proposal_id"]                              # waits
    assert admin.get(f"/api/kb/nodes/{mod['id']}")[1]["name"] == "Contrib Module"
    assert contrib.post(f"/api/kb/nodes/{mod['id']}/archive")[0] == 202
    # the database refuses the direct write, whatever the client
    import psycopg
    with as_user(USERS["contributor"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update kb.nodes set name = 'direct' where id = %s", (mod["id"],))
    with as_user(USERS["contributor"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update kb.node_resources set archived_at = now(), status = 'archived' where node_id = %s", (mod["id"],))
    cur = _cursor(viewer)
    s, d = admin.post(f"/api/kb/proposals/{out['proposal_id']}/approve")
    assert s == 200, d
    assert admin.get(f"/api/kb/nodes/{mod['id']}")[1]["name"] == "Changed by a contributor"
    _with(_feed(viewer, cur), "record.update", mod["id"])
    assert _map(viewer)[0]["nodes"][mod["id"]]["label"] == "Changed by a contributor"


def test_the_map_can_roll_back_to_the_old_tables(viewer, monkeypatch):
    _node(Client(USERS["admin"]), "module", "Only In The KB")
    s, out = viewer.get("/api/structure")
    assert s == 200 and out.get("source") == "kb"
    monkeypatch.setenv("NP_MAP_SOURCE", "old")
    s, out = viewer.get("/api/structure")
    assert s == 200 and out.get("source") is None and "Only In The KB" not in out["labels"]
    assert viewer.get("/api/stats")[0] == 404                           # the page falls back to stats.json


def test_landing_numbers_come_from_kb_and_need_no_session(admin):
    _node(admin, "module", "Counted Module")
    s, st = Client(None).get("/api/stats")
    assert s == 200 and st["source"] == "kb" and st["nodes"] == 1 and st["by_type"] == {"module": 1}
    assert set(st) >= {"nodes", "edges", "files", "built_as_of"}
    assert "labels" not in st and "ids" not in st                       # counts only


def test_zz_print_matrix():
    """The API matrix (test order: this runs last in the file)."""
    if ROWS:
        print("\nCHANGE-PROPAGATION MATRIX (API): operation | kind | feed | /api/kb/graph | '/' routes")
        for r in ROWS:
            print(f"  {r['op']:<58} {r['kind']:<26} {'ok' if r['api'] else 'FAIL'}  "
                  f"{'ok' if r['graph'] else 'FAIL'}  {'ok' if r['map'] else 'FAIL'}")
