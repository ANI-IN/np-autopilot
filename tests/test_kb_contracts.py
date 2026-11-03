"""Run 6 contracts (docs/CONTRACTS.md): the graph read API, the change feed's
kind / node_ids, and the type styles. Local DB only."""
from __future__ import annotations

import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()
    with owner() as c:
        c.execute("delete from kb.proposals where action = 'type_change'")
        c.execute("delete from kb.edge_types where not is_core")


@pytest.fixture
def admin():
    return Client(USERS["admin"])


@pytest.fixture
def viewer():
    return Client(USERS["viewer"])


def _node(client, type_="topic", name="Graphs", **kw):
    s, n = client.post("/api/kb/nodes", {"type": type_, "name": name, **kw})
    assert s == 201, n
    return n


def _edge(client, type_, a, b):
    s, e = client.post("/api/kb/edges", {"type": type_, "source_id": a["id"], "target_id": b["id"]})
    assert s == 201, e
    return e


def _head(client):
    s, out = client.get("/api/kb/changes")
    assert s == 200
    return out["cursor"]


def _since(client, cursor):
    s, out = client.get("/api/kb/changes", f"since={cursor}")
    assert s == 200
    return out["changes"]


# --- 1. graph read API -------------------------------------------------------

def test_graph_pages_return_every_record_and_relationship_exactly_once(admin, viewer):
    topics = [_node(admin, name=f"Topic {i:02d}") for i in range(7)]
    for a, b in zip(topics, topics[1:]):
        _edge(admin, "related", a, b)
    seen_n, seen_e, cursor = [], [], None
    while True:
        s, page = viewer.get("/api/kb/graph", "limit=3" + (f"&cursor={cursor}" if cursor else ""))
        assert s == 200, page
        seen_n += [n["id"] for n in page["nodes"]]
        seen_e += [e["id"] for e in page["edges"]]
        assert page["total_nodes"] == 7
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen_n) == sorted(t["id"] for t in topics)
    assert len(seen_e) == len(set(seen_e)) == 6
    assert page["head"] == _head(viewer)
    assert all(isinstance(n["version"], int) for n in page["nodes"])
    s, g = viewer.get("/api/kb/graph")
    assert all(isinstance(e["version"], int) and "note" in e for e in g["edges"])


def test_graph_filters_legacy_archived_focus_and_scope(admin, viewer):
    course = _node(admin, "course", "Graph course")
    a, b, c = (_node(admin, name=n) for n in ("Alpha", "Beta", "Gamma"))
    _edge(admin, "related", a, b)
    _edge(admin, "related", b, c)
    with owner() as db:
        db.execute("update kb.nodes set is_legacy = true where id = %s", (c["id"],))
    s, g = viewer.get("/api/kb/graph", "types=topic")
    assert {n["name"] for n in g["nodes"]} == {"Alpha", "Beta"} and len(g["edges"]) == 1
    s, g = viewer.get("/api/kb/graph", "types=topic&legacy=only")
    assert [n["name"] for n in g["nodes"]] == ["Gamma"] and g["nodes"][0]["is_legacy"]
    s, g = viewer.get("/api/kb/graph", "types=topic&legacy=all")
    assert len(g["nodes"]) == 3 and {e["is_legacy"] for e in g["edges"]} == {False, True}
    s, _ = admin.post(f"/api/kb/nodes/{b['id']}/archive", {"version": admin.get(f"/api/kb/nodes/{b['id']}")[1]["version"]})
    assert s == 200
    s, g = viewer.get("/api/kb/graph", "types=topic&legacy=all")
    assert {n["name"] for n in g["nodes"]} == {"Alpha", "Gamma"} and g["edges"] == []
    s, g = viewer.get("/api/kb/graph", "types=topic&legacy=all&archived=1")
    assert {n["name"]: n["archived"] for n in g["nodes"]}["Beta"] is True
    s, g = viewer.get("/api/kb/graph", f"focus={a['id']}&depth=2&legacy=all&archived=1")
    assert {n["name"] for n in g["nodes"]} == {"Alpha", "Beta", "Gamma"}
    s, g = viewer.get("/api/kb/graph", f"scope={course['id']}")
    assert [n["id"] for n in g["nodes"]] == [course["id"]]


@pytest.mark.parametrize("query, field", [("legacy=old", "legacy"), ("limit=0", "limit"), ("limit=5001", "limit"),
                                          ("depth=3&focus=00000000-0000-4000-8000-000000000000", "depth"),
                                          ("types=a;b", "types"), ("focus=nope", "focus")])
def test_graph_rejects_bad_parameters_with_422(viewer, query, field):
    s, out = viewer.get("/api/kb/graph", query)
    assert s == 422 and out.get("field") == field, out


def test_graph_unknown_focus_is_404_and_needs_a_member(viewer):
    s, _ = viewer.get("/api/kb/graph", "focus=00000000-0000-4000-8000-000000000000")
    assert s == 404
    s, _ = Client(None).get("/api/kb/graph")
    assert s == 401


# --- 2. change feed kinds ----------------------------------------------------

def test_change_feed_names_the_kind_and_the_records(admin):
    cur = _head(admin)
    a, b = _node(admin, name="One"), _node(admin, name="Two")
    e = _edge(admin, "related", a, b)
    s, a2 = admin.patch(f"/api/kb/nodes/{a['id']}", {"name": "One renamed", "version": a["version"]})
    assert s == 200, a2
    s, _ = admin.post(f"/api/kb/edges/{e['id']}/archive", {})
    assert s == 200
    s, _ = admin.post(f"/api/kb/nodes/{b['id']}/archive", {"version": b["version"]})
    assert s == 200
    rows = _since(admin, cur)
    kinds = [r["kind"] for r in rows]
    for k in ("record.create", "relationship.create", "record.update", "relationship.archive", "record.archive"):
        assert k in kinds, (k, kinds)
    rel = next(r for r in rows if r["kind"] == "relationship.create")
    assert set(rel["node_ids"]) == {a["id"], b["id"]}
    assert all(r["kind"] for r in rows)


def test_owner_change_is_its_own_kind(admin):
    rec = _node(admin, "module", "Owned module")
    person = _node(admin, "instructor", "Some Instructor")
    cur = _head(admin)
    s, out = admin.patch(f"/api/kb/nodes/{rec['id']}", {"owner_record_id": person["id"], "version": rec["version"]})
    assert s == 200, out
    assert [r["kind"] for r in _since(admin, cur) if r["table_name"] == "nodes"] == ["record.owner"]


def test_layout_saves_emit_one_change_without_an_audit_row(admin):
    a, b = _node(admin, name="Placed A"), _node(admin, name="Placed B")
    cur = _head(admin)
    with owner() as c:
        audit_before = c.execute("select count(*) from kb.audit_log").fetchone()[0]
    s, out = admin.post("/api/kb/graph/positions",
                        {"layout": "default", "positions": [{"node_id": a["id"], "x": 1, "y": 2}, {"node_id": b["id"], "x": 3, "y": 4}]})
    assert s == 200, out
    rows = [r for r in _since(admin, cur) if r["kind"] == "layout.update"]
    assert len(rows) == 1 and set(rows[0]["node_ids"]) == {a["id"], b["id"]}
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log").fetchone()[0] == audit_before


# --- 3. type styles ----------------------------------------------------------

def test_types_carry_shape_owner_expected_and_relationship_styles(viewer, admin):
    s, t = viewer.get("/api/kb/types")
    assert s == 200
    nts = {x["key"]: x for x in t["node_types"]}
    assert nts["module"]["owner_expected"] and not nts["topic"]["owner_expected"]
    assert all(x["shape"] for x in t["node_types"])
    assert all(x["color"] and x["line_style"] in ("solid", "dashed", "dotted") for x in t["edge_types"])
    styles = set()
    for label, inv in (("mentors", "mentored by"), ("reviews", "reviewed by"), ("pairs with", "paired with")):
        s, e = admin.post("/api/kb/types/edge", {"label": label, "inverse_label": inv,
                                                  "rules": [{"source": "instructor", "target": "instructor"}]})
        assert s == 201, e
    s, t = viewer.get("/api/kb/types")
    custom = [x for x in t["edge_types"] if not x["is_core"]]
    assert len(custom) == 3
    styles = {(x["color"], x["line_style"]) for x in custom}
    assert len(styles) == 3, "every custom relationship type gets its own look"


# --- run 6 audit fixes in the lead's files (A9b, A11) -------------------------

def test_a_negative_content_length_is_refused(admin):
    import io

    from kb_support import token_for
    env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/kb/nodes", "QUERY_STRING": "",
           "CONTENT_LENGTH": "-1", "wsgi.input": io.BytesIO(b'{"type": "topic", "name": "x"}'),
           "HTTP_AUTHORIZATION": f"Bearer {token_for(USERS['admin'])}"}
    out = {}
    b"".join(admin.app(env, lambda status, headers: out.setdefault("status", status)))
    assert out["status"].startswith("413"), out
    with owner() as c:
        assert c.execute("select count(*) from kb.nodes where name = 'x'").fetchone()[0] == 0
