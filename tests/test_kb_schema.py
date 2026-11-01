"""M1 — the kb schema's constraints, triggers and audit, tested in the database
itself (as the table owner, so these prove the STRUCTURE holds without any
service or policy in front of it)."""
from __future__ import annotations

import psycopg
import pytest

from kb_support import edge_type_id, owner, requires_kb, reset, session_dsn, type_id

pytestmark = requires_kb


@pytest.fixture(autouse=True)
def _clean():
    reset()
    yield
    reset()


def _node(c, type_key, name, scope=None):
    return c.execute("insert into kb.nodes (type_id, name, scope_id) values (%s,%s,%s) returning id",
                     (type_id(type_key), name, scope)).fetchone()[0]


def _edge(c, etype, s, t):
    return c.execute("insert into kb.edges (edge_type_id, source_id, target_id) values (%s,%s,%s) returning id",
                     (edge_type_id(etype), s, t)).fetchone()[0]


def test_rls_is_enabled_on_every_kb_table():
    with owner() as c:
        rows = c.execute("select c.relname, c.relrowsecurity from pg_class c join pg_namespace n "
                         "on n.oid = c.relnamespace where n.nspname = 'kb' and c.relkind = 'r'").fetchall()
    assert rows, "no kb tables found — the scan is looking in the wrong place"
    assert [r for r, sec in rows if not sec] == []
    assert len(rows) >= 13


def test_every_mutable_table_carries_the_standard_columns():
    want = {"id", "created_by", "updated_by", "created_at", "updated_at", "version", "status", "archived_at"}
    with owner() as c:
        for t in ("node_types", "edge_types", "nodes", "edges", "resources", "node_resources", "tags",
                  "api_tokens", "proposals"):
            cols = {r[0] for r in c.execute("select column_name from information_schema.columns "
                                            "where table_schema='kb' and table_name=%s", (t,))}
            assert want <= cols, f"kb.{t} is missing {want - cols}"


def test_duplicate_name_is_rejected_across_case_and_whitespace():
    with owner() as c:
        _node(c, "topic", "Dynamic Programming")
        for variant in ("dynamic programming", "  Dynamic   Programming ", "DYNAMIC PROGRAMMING"):
            with pytest.raises(psycopg.errors.UniqueViolation):
                _node(c, "topic", variant)


def test_same_name_is_allowed_in_another_type_or_scope():
    with owner() as c:
        a = _node(c, "course", "Course A")
        b = _node(c, "course", "Course B")
        _node(c, "module", "Week 1", a)
        _node(c, "module", "Week 1", b)            # different scope: fine
        _node(c, "topic", "Week 1")                # different type: fine


def test_archiving_frees_the_name_and_restore_into_a_taken_name_fails():
    with owner() as c:
        n = _node(c, "topic", "Graphs")
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (n,))
        _node(c, "topic", "graphs")
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("update kb.nodes set archived_at = null, status='active' where id = %s", (n,))


def test_unicode_and_emoji_names_are_kept():
    with owner() as c:
        n = _node(c, "topic", "Grafos — teoría 📈")
        assert c.execute("select name from kb.nodes where id=%s", (n,)).fetchone()[0] == "Grafos — teoría 📈"


def test_a_name_cannot_carry_an_address_or_url():
    with owner() as c:
        for bad in ("someone@example.com", "see https://example.com"):
            with pytest.raises(psycopg.errors.CheckViolation):
                _node(c, "topic", bad)


def test_duplicate_edge_rejected():
    with owner() as c:
        a, b = _node(c, "topic", "A"), _node(c, "topic", "B")
        _edge(c, "related", a, b)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _edge(c, "related", a, b)


def test_edge_type_not_allowed_between_those_types_is_rejected():
    with owner() as c:
        topic, course = _node(c, "topic", "T"), _node(c, "course", "C")
        with pytest.raises(psycopg.errors.CheckViolation, match="not allowed from topic to course"):
            _edge(c, "teaches", topic, course)


def test_self_edge_rejected_unless_type_allows_it():
    with owner() as c:
        a = _node(c, "topic", "Self")
        with pytest.raises(psycopg.errors.CheckViolation, match="itself"):
            _edge(c, "related", a, a)
        c.execute("update kb.edge_types set allow_self = true where key = 'related'")
        try:
            _edge(c, "related", a, a)
        finally:
            c.execute("update kb.edge_types set allow_self = false where key = 'related'")


def test_archive_cascades_to_edges_and_restore_brings_back_only_those():
    with owner() as c:
        a, b, d = _node(c, "topic", "A"), _node(c, "topic", "B"), _node(c, "topic", "D")
        e1 = _edge(c, "related", a, b)
        e2 = _edge(c, "related", b, d)
        # e2 archived deliberately BEFORE b is archived: restore must not revive it.
        c.execute("update kb.edges set archived_at = now(), status='archived' where id = %s", (e2,))
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (b,))
        assert c.execute("select archived_with from kb.edges where id=%s", (e1,)).fetchone()[0] == b
        c.execute("update kb.nodes set archived_at = null, status='active' where id = %s", (b,))
        live = {r[0] for r in c.execute("select id from kb.edges where archived_at is null")}
        assert live == {e1}


def test_edge_to_an_archived_node_is_rejected():
    with owner() as c:
        a, b = _node(c, "topic", "A"), _node(c, "topic", "B")
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (b,))
        with pytest.raises(psycopg.errors.CheckViolation, match="archived"):
            _edge(c, "related", a, b)


def test_concurrent_archive_and_edge_create_never_leave_an_orphan():
    """★ An edge created while its endpoint is being archived: the insert blocks
    on the endpoint's row lock, then sees the archive and is refused."""
    import threading
    with owner() as c:
        a, b = _node(c, "topic", "A"), _node(c, "topic", "B")
    arch = psycopg.connect(session_dsn())
    arch.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (b,))
    result = {}

    def create():
        try:
            with psycopg.connect(session_dsn(), autocommit=True) as c2:
                _edge(c2, "related", a, b)
            result["ok"] = True
        except psycopg.errors.CheckViolation as exc:
            result["err"] = str(exc)

    t = threading.Thread(target=create)
    t.start()
    t.join(1.0)
    assert t.is_alive(), "the edge insert should be waiting on the archive's lock"
    arch.commit()
    arch.close()
    t.join(10)
    assert "err" in result and "archived" in result["err"]
    with owner() as c:
        orphans = c.execute("""select count(*) from kb.edges e join kb.nodes n
                               on n.id in (e.source_id, e.target_id)
                               where e.archived_at is null and n.archived_at is not null""").fetchone()[0]
    assert orphans == 0


def test_version_is_bumped_by_the_database_not_the_caller():
    with owner() as c:
        n = _node(c, "topic", "V")
        c.execute("update kb.nodes set summary = 'x', version = 99 where id = %s", (n,))
        assert c.execute("select version from kb.nodes where id=%s", (n,)).fetchone()[0] == 2


def test_audit_log_records_before_and_after_for_every_operation():
    with owner() as c:
        n = _node(c, "topic", "Audited")
        c.execute("update kb.nodes set summary = 'changed' where id = %s", (n,))
        c.execute("update kb.nodes set archived_at = now(), status='archived' where id = %s", (n,))
        c.execute("delete from kb.nodes where id = %s", (n,))
        rows = c.execute("select action, before ->> 'summary', after ->> 'summary' from kb.audit_log "
                         "where row_id = %s and table_name='nodes' order by id", (n,)).fetchall()
    assert [r[0] for r in rows] == ["insert", "update", "update", "delete"]
    assert rows[1][1] is None and rows[1][2] == "changed"


def test_resource_url_must_be_http_and_is_unique_when_normalised():
    with owner() as c:
        c.execute("insert into kb.resources (url, title) values ('https://example.com/a/', 'A')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("insert into kb.resources (url, title) values ('HTTPS://EXAMPLE.COM/a', 'A2')")
        for bad in ("ftp://example.com", "not a url", "javascript:alert(1)"):
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("insert into kb.resources (url, title) values (%s, 'x')", (bad,))
