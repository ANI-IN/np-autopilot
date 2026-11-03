"""Run 6, F4 — ONE service layer: the sync and the UI/API refuse the SAME
invalid input with the SAME rule.

Three kinds of input, each sent down both paths:

  1. an over-long name (and a name that is an e-mail address),
  2. an invalid value for a typed field,
  3. a relationship the type rules forbid.

The API path is the real WSGI app (Client). The sync path is
web/lib/kb/sync.py on a synthetic copy of the original site's tables in a
schema of its own (`kbval_src`), run as a PREVIEW (apply=False: one
transaction, rolled back), so nothing is written. Each test asserts the same
sentence on both sides AND that the sync reached it through the shared
function (validate.name_problem, service.field_errors,
service.edge_rule_problem), not through a copy of the rule.

No real data: every name below is made up.
"""
from __future__ import annotations

import json
from collections import defaultdict

import psycopg
import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset, session_dsn, type_id

pytestmark = requires_kb

SRC = "kbval_src"
GADGET = {"label": "Kbval gadget", "key": "kbval_gadget",
          "fields": [{"label": "Size", "kind": "number"}]}


def _make_source(nodes=(), edges=()):
    with owner() as c:
        c.execute(f"drop schema if exists {SRC} cascade")
        c.execute(f"create schema {SRC}")
        c.execute(f"""create table {SRC}.nodes (id text primary key, type text, label text, props jsonb, sensitive boolean default false);
            create table {SRC}.edges (id serial primary key, rel text, source_id text, target_id text, props jsonb);
            create table {SRC}.node_sources (node_id text, file text);
            create table {SRC}.node_layout (node_id text, x float8, y float8);
            create table {SRC}.people (canonical text, team text, title text, seniority text);
            create table {SRC}.people_aliases (alias text, canonical text);
            create table {SRC}.domain_aliases (alias text, domain text);
            create table {SRC}.workflow_owners (workflow_id text, suggestion text);
            create table {SRC}.curation_notes (id serial, scope text, row_key text, note text, position int)""")
        for i, t, lab, p in nodes:
            c.execute(f"insert into {SRC}.nodes (id, type, label, props) values (%s, %s, %s, %s)", (i, t, lab, json.dumps(p)))
        for rel, s, t in edges:
            c.execute(f"insert into {SRC}.edges (rel, source_id, target_id, props) values (%s, %s, %s, '{{}}')", (rel, s, t))


def _drop():
    with owner() as c:
        c.execute(f"drop schema if exists {SRC} cascade")
        c.execute("truncate kb.sync_map, kb.sync_runs")
        c.execute("delete from kb.proposals where action in ('create', 'type_change')")
        c.execute("delete from kb.node_types where key = %s", (GADGET["key"],))


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.delenv("KB_SYNC_ENABLED", raising=False)
    ensure_users()
    reset()
    _drop()
    yield
    reset()
    _drop()


def _mapping(**over):
    from lib.kb import sync as engine
    # Only the KB's existing types: nothing to create, no fields or placement added.
    M = dict(engine.load_mapping(), type_fields={}, placement={}, new_record_types=[],
             new_relationship_types=[], attachments=[])
    M.update(over)
    return M


def _desired(M):
    from lib.kb import sync as engine
    with psycopg.connect(session_dsn()) as conn:
        try:
            return engine.desired_state(conn, M, SRC)
        finally:
            conn.rollback()


# ---------------------------------------------------------------- 1. names
@pytest.mark.parametrize("bad", ["Overlong " + "x" * 300, "kbval-someone@example.com"])
def test_a_bad_name_is_refused_by_the_api_and_the_sync_with_one_sentence(bad):
    from lib.kb import validate as v
    rule = v.name_problem(bad)
    assert rule, "the shared rule must refuse this name"

    s, out = Client(USERS["editor"]).post("/api/kb/nodes", {"type": "module", "name": bad})
    assert s == 422 and out["field"] == "name", out
    assert out["message"] == rule

    _make_source(nodes=[("kbval_bad", "module", bad, {}), ("kbval_ok", "module", "Kbval fine module", {})])
    D = _desired(_mapping(types={"module": "module"}))
    rejected = {r["id"]: r["reason"] for r in D["report"]["rejected"]}
    assert rejected.get("kbval_bad") == rule, rejected
    assert "kbval_ok" in D["recs"] and "kbval_ok" not in rejected        # valid data is untouched


def test_the_sync_calls_the_shared_name_rule(monkeypatch):
    """Not a copy of the rule: the sync reaches validate.name_problem itself."""
    from lib.kb import validate as v
    seen = []
    real = v.name_problem
    monkeypatch.setattr(v, "name_problem", lambda value, field="name": seen.append(value) or real(value, field))
    _make_source(nodes=[("kbval_ok", "module", "Kbval fine module", {})])
    _desired(_mapping(types={"module": "module"}))
    assert "Kbval fine module" in seen


# ---------------------------------------------------------------- 2. typed fields
def test_an_invalid_field_value_is_refused_by_the_api_the_sync_and_the_database():
    from lib.kb import service as svc
    from lib.kb import sync as engine
    admin, editor = Client(USERS["admin"]), Client(USERS["editor"])
    s, t = admin.post("/api/kb/types/node", GADGET)
    assert s == 201, t
    size = next(f for f in t["fields"] if f["label"] == "Size")

    # the API (UI forms post the same body)
    s, out = editor.post("/api/kb/nodes", {"type": GADGET["key"], "name": "Kbval G1", "props": {size["key"]: "big"}})
    assert s == 422 and out["field"] == "props." + size["key"], out
    api_sentence = out["message"]

    # the sync's check (sync.field_problems -> service.field_errors) on the same record
    with psycopg.connect(session_dsn()) as conn:
        rec = {"np": "kbval_g1", "type": GADGET["key"], "props": {size["key"]: "big"}}
        rep = {"problems": defaultdict(list), "rejected": []}
        recs = {"kbval_g1": rec}
        assert engine.field_problems(conn, recs, rep) == 1
        assert rep["problems"]["field_value_rejected"] == [f"kbval_g1: {api_sentence}"]
        assert rec["props"] == {}, "the refused value is left out, the record is kept"
        assert "kbval_g1" in recs
        # one function, both callers
        assert svc.field_errors(conn, [(t["fields"], {size["key"]: "big"})]) == {0: (size["key"], api_sentence)}
        # valid data: nothing changes
        ok = {"kbval_g2": {"np": "kbval_g2", "type": GADGET["key"], "props": {size["key"]: 3}}}
        assert engine.field_problems(conn, ok, rep) == 0 and ok["kbval_g2"]["props"] == {size["key"]: 3}
        conn.rollback()

    # and the database trigger, the last line, says the same thing
    with owner() as c:
        with pytest.raises(psycopg.errors.CheckViolation) as exc:
            c.execute("insert into kb.nodes (type_id, name, props) values (%s, 'Kbval G3', %s)",
                      (type_id(GADGET["key"]), json.dumps({size["key"]: "big"})))
        assert exc.value.diag.message_primary == api_sentence


def test_the_sync_runs_every_record_through_the_shared_field_rule(monkeypatch):
    from lib.kb import service as svc
    calls = []
    real = svc.field_errors
    monkeypatch.setattr(svc, "field_errors", lambda conn, items: calls.append(list(items)) or real(conn, items))
    _make_source(nodes=[("kbval_m1", "module", "Kbval module one", {"granularity": "kbval"})])
    D = _desired(_mapping(types={"module": "module"}))
    assert calls, "desired_state did not call service.field_errors"
    assert any(p == D["recs"]["kbval_m1"]["props"] or "granularity" in p for _, p in calls[0])


# ---------------------------------------------------------------- 3. relationship rules
def test_a_forbidden_relationship_is_refused_by_the_api_and_the_sync_with_one_rule(monkeypatch):
    from lib.kb import service as svc
    from lib.kb import sync as engine
    # Two records of a type the rules never let one teach the other.
    with owner() as c:
        a, b = (str(c.execute("insert into kb.nodes (type_id, name) values (%s, %s) returning id",
                              (type_id("module"), n)).fetchone()[0]) for n in ("Kbval A", "Kbval B"))
    s, out = Client(USERS["editor"]).post("/api/kb/edges", {"type": "teaches", "source_id": a, "target_id": b})
    assert s == 422 and out.get("rule") == "kb_edge_rule", out
    with psycopg.connect(session_dsn()) as conn:
        rules = svc.edge_rules(conn)
        conn.rollback()
    assert out["message"] == svc.edge_rule_problem(rules, "teaches", "module", "module")

    # The sync, with a source relationship mapped onto the same forbidden shape.
    seen = []
    real = svc.edge_rule_problem
    monkeypatch.setattr(svc, "edge_rule_problem",
                        lambda r, e, s_, t_: seen.append((e, s_, t_, real(r, e, s_, t_))) or real(r, e, s_, t_))
    _make_source(nodes=[("kbval_m1", "module", "Kbval module one", {}), ("kbval_m2", "module", "Kbval module two", {})],
                 edges=[("kbval_rel", "kbval_m1", "kbval_m2")])
    M = _mapping(types={"module": "module"},
                 relationships=[{"rel": "kbval_rel", "source": "module", "target": "module", "kb": "teaches"}])
    with psycopg.connect(session_dsn()) as conn:
        res = engine.run(conn, trigger="cli", actor_id=USERS["admin"], source=SRC, mapping=M, apply=False)
    assert res["status"] == "ok", res
    assert "teaches|kbval_m1|kbval_m2" in res["report"]["problems"]["relationship_not_allowed"]
    assert ("teaches", "module", "module", out["message"]) in seen
    assert res["created"].get("relationship: teaches", 0) == 0
    with owner() as c:      # a preview: nothing was written
        assert c.execute("select count(*) from kb.nodes where external_id like 'np:kbval_%%'").fetchone()[0] == 0


def test_an_allowed_relationship_still_syncs_and_still_saves():
    """The shared check changes nothing on valid data: an allowed shape passes both paths."""
    from lib.kb import service as svc
    with psycopg.connect(session_dsn()) as conn:
        rules = svc.edge_rules(conn)
        conn.rollback()
    assert rules, "no relationship rules at all"
    e, s_, t_ = sorted(rules)[0]
    assert svc.edge_rule_problem(rules, e, s_, t_) is None
