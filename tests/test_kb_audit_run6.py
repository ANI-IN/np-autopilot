"""Run 6 (B5) audit fixes, docs/run6/AUDIT_FINDINGS.md: the database refuses
the AI assistant the admin-only powers (A1), a request cannot leave the
workspace without an admin (A2), and the curation endpoint answers a malformed
body with 400 (A9). Local DB only."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest

from kb_support import USERS, as_user, ensure_users, owner, requires_kb, reset

from lib.kb import service as svc
from lib.kb.errors import Forbidden

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()
    ensure_users()


def _archived_node() -> str:
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        nid = c.execute("insert into kb.nodes (type_id, name) values "
                        "((select id from kb.node_types where key = 'module'), 'Audit probe') returning id").fetchone()[0]
        c.execute("update kb.nodes set archived_at = now(), status = 'archived' where id = %s", (nid,))
    return str(nid)


@contextmanager
def _only_admin(user_id: str):
    """Make `user_id` the workspace's only admin for the duration (other admins'
    rows archived, then restored exactly)."""
    with owner() as c:
        others = [r[0] for r in c.execute("select user_id from kb.memberships where role = 'admin' "
                                          "and archived_at is null and user_id <> %s", (user_id,)).fetchall()]
        c.execute("update kb.memberships set archived_at = now(), status = 'archived' where user_id = any(%s)", (others,))
    try:
        yield
    finally:
        with owner() as c:
            c.execute("update kb.memberships set archived_at = null, status = 'active' where user_id = any(%s)", (others,))


def test_the_ai_assistant_cannot_grant_roles_even_for_an_admin():
    target = USERS["contributor"]
    with as_user(USERS["admin"], "ai") as conn:
        with pytest.raises(Forbidden, match="AI assistant"):
            svc.set_role(conn, svc.Actor(USERS["admin"], "ai"), target, "admin")
    with as_user(USERS["admin"]) as conn:                                # a person still can
        assert svc.set_role(conn, svc.Actor(USERS["admin"]), target, "editor")["role"] == "editor"


def test_the_ai_assistant_cannot_permanently_delete():
    nid = _archived_node()
    with as_user(USERS["admin"], "ai") as conn:
        with pytest.raises(Forbidden, match="AI assistant"):
            svc.hard_delete(conn, svc.Actor(USERS["admin"], "ai"), "nodes", nid)
    with as_user(USERS["admin"]) as conn:
        assert svc.hard_delete(conn, svc.Actor(USERS["admin"]), "nodes", nid) == {"deleted": nid}
        conn.commit()
    with owner() as c:
        assert c.execute("select count(*) from kb.nodes where id = %s", (nid,)).fetchone()[0] == 0


def test_the_ai_assistant_cannot_link_a_person_to_a_sign_in():
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        pid = c.execute("insert into kb.nodes (type_id, name) values "
                        "((select id from kb.node_types where key = 'instructor'), 'Audit person') returning id").fetchone()[0]
    with as_user(USERS["admin"], "ai") as conn:
        with pytest.raises(Forbidden):
            svc.set_person_account(conn, svc.Actor(USERS["admin"], "ai"), str(pid),
                                   {"email": f"audit-{uuid.uuid4().hex[:8]}@interviewkickstart.com"})


def test_the_last_admin_cannot_demote_themselves_but_can_once_there_is_another():
    me = USERS["admin"]
    with _only_admin(me):
        with as_user(me) as conn:
            with pytest.raises(Forbidden, match="last admin"):
                svc.set_role(conn, svc.Actor(me), me, "viewer")
        with as_user(me) as conn:
            svc.set_role(conn, svc.Actor(me), USERS["editor"], "admin")
            assert svc.set_role(conn, svc.Actor(me), me, "editor")["role"] == "editor"


def test_operator_connections_still_manage_memberships_directly():
    with owner() as c:                       # the tests' own fixtures, kb_admins.py, migrations
        c.execute("update kb.memberships set role = 'viewer' where user_id = %s", (USERS["admin"],))
        c.execute("update kb.memberships set role = 'admin' where user_id = %s", (USERS["admin"],))


@pytest.mark.parametrize("body", [[1, 2], {"table": 5, "key": "x", "changes": {"a": 1}, "expected_version": 1},
                                  {"table": "t", "key": ["x"], "changes": {"a": 1}, "expected_version": 1}])
def test_curation_answers_a_malformed_body_with_400(body):
    import curate
    status, payload = curate.handle(None, None, body)
    assert status == 400 and payload["error"] == "bad_request"
