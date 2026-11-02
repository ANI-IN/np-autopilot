"""M2 — KB roles enforced by RLS, tested DIRECTLY against the database as
`authenticated` with each synthetic user's claims: no service, no route. This is
the "viewer calls the write API directly" case — it must fail here."""
from __future__ import annotations

import psycopg
import pytest

from kb_support import OUTSIDER, USERS, as_user, edge_type_id, ensure_users, owner, requires_kb, reset, type_id

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()


def _insert_topic(conn, name="RLS topic"):
    return conn.execute("insert into kb.nodes (type_id, name) values (%s, %s) returning id",
                        (type_id("topic"), name)).fetchone()[0]


def _seed_topic(name="Seed"):
    with owner() as c:
        return c.execute("insert into kb.nodes (type_id, name) values (%s, %s) returning id",
                         (type_id("topic"), name)).fetchone()[0]


def test_role_function_resolves_each_synthetic_user():
    for r, uid in USERS.items():
        with as_user(uid) as c:
            assert c.execute("select kb.role()").fetchone()[0] == r
    with as_user(OUTSIDER) as c:
        assert c.execute("select kb.role()").fetchone()[0] == "none"


def test_no_profile_sees_nothing():
    _seed_topic()
    with as_user(OUTSIDER) as c:
        assert c.execute("select count(*) from kb.nodes").fetchone()[0] == 0
    with as_user(None) as c:
        assert c.execute("select count(*) from kb.nodes").fetchone()[0] == 0


def test_viewer_reads_but_cannot_write():
    n = _seed_topic()
    with as_user(USERS["viewer"]) as c:
        assert c.execute("select count(*) from kb.nodes").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _insert_topic(c)
    with as_user(USERS["viewer"]) as c:
        cur = c.execute("update kb.nodes set summary = 'x' where id = %s", (n,))
        assert cur.rowcount == 0, "a viewer's UPDATE must match no rows under RLS"


def test_contributor_edits_but_cannot_create_archive_or_delete():
    # 0027: a contributor's create is a proposal, so the database refuses a
    # direct insert from them; editing an existing record is still allowed.
    with as_user(USERS["contributor"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _insert_topic(c)
    n = _seed_topic("Editable")
    with as_user(USERS["contributor"]) as c:
        c.execute("update kb.nodes set summary = 'edited' where id = %s", (n,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="editor"):
            c.execute("update kb.nodes set archived_at = now(), status = 'archived' where id = %s", (n,))
    n2 = _seed_topic("To delete")
    with owner() as o:
        o.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (n2,))
    with as_user(USERS["contributor"]) as c:
        assert c.execute("delete from kb.nodes where id = %s", (n2,)).rowcount == 0


def test_editor_archives_and_restores_and_the_cascade_runs_as_editor():
    a, b = _seed_topic("A"), _seed_topic("B")
    with owner() as o:
        o.execute("insert into kb.edges (edge_type_id, source_id, target_id) values (%s,%s,%s)",
                  (edge_type_id("related"), a, b))
    with as_user(USERS["editor"]) as c:
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (a,))
        assert c.execute("select count(*) from kb.edges where archived_at is null").fetchone()[0] == 0
        c.execute("update kb.nodes set archived_at = null, status='active' where id = %s", (a,))
        assert c.execute("select count(*) from kb.edges where archived_at is null").fetchone()[0] == 1
        # editor cannot hard delete
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (b,))
        assert c.execute("delete from kb.nodes where id = %s", (b,)).rowcount == 0


def test_admin_hard_deletes_only_archived_rows():
    live, archived = _seed_topic("Live"), _seed_topic("Gone")
    with owner() as o:
        o.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (archived,))
    with as_user(USERS["admin"]) as c:
        assert c.execute("delete from kb.nodes where id = %s", (live,)).rowcount == 0
        assert c.execute("delete from kb.nodes where id = %s", (archived,)).rowcount == 1


def test_only_admin_configures_types():
    for r in ("viewer", "contributor", "editor"):
        with as_user(USERS[r]) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("insert into kb.node_types (key, label) values ('quiz', 'Quiz')")
    with as_user(USERS["admin"]) as c:
        c.execute("insert into kb.node_types (key, label) values ('quiz', 'Quiz')")
        c.rollback()


def test_nobody_writes_the_audit_log_directly():
    for r in ("contributor", "admin"):
        with as_user(USERS[r]) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("insert into kb.audit_log (actor_type, table_name, action) "
                          "values ('human', 'nodes', 'insert')")


def test_audit_attributes_the_verified_user_and_actor_type():
    with as_user(USERS["editor"], actor_type="ai") as c:
        n = _insert_topic(c, "AI made")
        row = c.execute("select actor_id, actor_type from kb.audit_log where row_id = %s", (n,)).fetchone()
        assert str(row[0]) == USERS["editor"] and row[1] == "ai"


def test_memberships_are_admin_managed_and_not_self_grantable():
    with as_user(USERS["contributor"]) as c:
        cur = c.execute("update kb.memberships set role = 'admin' where user_id = %s", (USERS["contributor"],))
        assert cur.rowcount == 0
    with as_user(USERS["viewer"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into kb.memberships (user_id, role) values (%s, 'admin')", (USERS["viewer"],))


def test_tokens_are_private_to_their_owner():
    with as_user(USERS["editor"]) as c:
        c.execute("insert into kb.api_tokens (user_id, name, token_hash, prefix) values (%s,'t',%s,'ikkb_x')",
                  (USERS["editor"], "a" * 64))
        c.commit()
    with as_user(USERS["admin"]) as c:
        assert c.execute("select count(*) from kb.api_tokens").fetchone()[0] == 0
    with as_user(USERS["contributor"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into kb.api_tokens (user_id, name, token_hash, prefix) values (%s,'t',%s,'p')",
                      (USERS["editor"], "b" * 64))
