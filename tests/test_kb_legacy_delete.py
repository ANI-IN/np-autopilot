"""Run 6 resume, R3: the owner-approved permanent deletion of the legacy domains
and modules (web/lib/kb/legacy_delete.py), its export and restore, and the
sync's permanent exclusion (0037). Synthetic source (tests/test_kb_sync.py's
`kbsync_src`): no real data."""
from __future__ import annotations

import json

import psycopg
import pytest

from kb_support import Client, USERS, owner, requires_kb, session_dsn
from test_kb_sync import R, SRC, _setup, kb_count, rec, src, sync  # noqa: F401  (_setup: the synthetic source per test)

pytestmark = requires_kb
CURRENT = ("domain current",)


@pytest.fixture(autouse=True)
def _clean():
    yield
    with owner() as c:
        c.execute("delete from kb.sync_exclusions")


def _run(cmd, data=None):
    from lib.kb import legacy_delete as ld
    with psycopg.connect(session_dsn()) as conn:
        p = ld.plan(conn, CURRENT)
        if cmd == "plan":
            return p
        if cmd == "restore":
            out = ld.restore(conn, data)
            conn.commit()
            return out
        data = json.loads(json.dumps(ld.export(conn, p), default=ld._json_default))   # as the file holds it
        out = ld.delete(conn, p, data)
        conn.commit()
        return out, data


def _expertise():
    """A current instructor's declared expertise on the legacy domain."""
    a = Client(USERS["admin"])
    s, e = a.post("/api/kb/edges", {"type": "sme", "source_id": str(rec("ins_p")["id"]), "target_id": str(rec("dom_old")["id"])})
    assert s == 201, e
    return e


def test_delete_removes_legacy_domains_and_modules_and_nothing_else():
    sync()
    _expertise()
    top_b = rec("top_b")
    with owner() as c:
        assert c.execute("select scope_id from kb.nodes where id = %s", (top_b["id"],)).fetchone()[0] == rec("mod_old")["id"]
    out, data = _run("delete")
    assert out["domains"] == 1 and out["modules"] == 2 and out["expertise_links"] == 1
    for gone in ("dom_old", "mod_old", "mod_lost"):
        assert rec(gone) is None, gone
    for kept in ("dom_cur", "mod_cur", "ins_p", "ins_old", "prog", "top_a", "top_b", "ses"):
        assert rec(kept) is not None, kept
    with owner() as c:
        # the instructor lost only the expertise link; the topic is detached and flagged
        assert c.execute("select scope_id from kb.nodes where id = %s", (top_b["id"],)).fetchone()[0] is None
        assert c.execute("select count(*) from kb.flags where target_id = %s and status = 'open'", (top_b["id"],)).fetchone()[0] == 1
        assert c.execute("select count(*) from kb.edges where source_id = %s", (rec("ins_p")["id"],)).fetchone()[0] >= 1
        assert c.execute("select count(*) from kb.sync_exclusions where unit = 'rule'").fetchone()[0] == 1
    # the old tables are untouched
    with owner() as c:
        assert c.execute(f"select count(*) from {SRC}.nodes where id in ('dom_old', 'mod_old', 'mod_lost')").fetchone()[0] == 3


def test_the_sync_never_recreates_them_and_sees_no_conflict():
    sync()
    _run("delete")
    # a NEW legacy domain and module appear at the source: the rule keeps them out too
    src("insert into SRC.nodes (id, type, label, props) values ('dom_new_old', 'domain', 'Domain Newer Old', '{}'), "
        "('mod_new_old', 'module', 'Module Newer Old', '{}')")
    src(f"insert into SRC.edges (rel, source_id, target_id, props) values ('{R['domain_offers']}', 'dom_new_old', 'mod_new_old', '{{}}')")
    out = sync()
    assert out["status"] == "ok", out
    for gone in ("dom_old", "mod_old", "mod_lost", "dom_new_old", "mod_new_old"):
        assert rec(gone) is None, gone
    assert sum(dict(out["conflicts"]).values()) == 0 and kb_count("sync_map", "conflict_at is not null") == 0
    assert out["report"]["excluded"] == 5            # the three deleted + the two new legacy rows
    # a second run writes nothing
    again = sync()
    assert again["status"] == "ok"
    assert sum(dict(again["conflicts"]).values()) == 0
    assert sum(dict(again["created"]).values()) == 0 and sum(dict(again["updated"]).values()) == 0, (again["created"], again["updated"])


def test_restore_puts_every_row_back_with_the_same_ids():
    sync()
    e = _expertise()
    before = {k: rec(k)["id"] for k in ("dom_old", "mod_old", "mod_lost")}
    counts_before = {t: kb_count(t) for t in ("nodes", "edges", "node_resources", "node_tags", "sync_map")}
    top_b = rec("top_b")
    _, data = _run("delete")
    _run("restore", data)
    assert {k: rec(k)["id"] for k in before} == before
    assert {t: kb_count(t) for t in counts_before} == counts_before
    with owner() as c:
        assert c.execute("select scope_id from kb.nodes where id = %s", (top_b["id"],)).fetchone()[0] == before["mod_old"]
        assert c.execute("select count(*) from kb.edges where id = %s", (e["id"],)).fetchone()[0] == 1
        assert c.execute("select count(*) from kb.flags where reason like 'Its parent was permanently deleted%%'").fetchone()[0] == 0
        assert c.execute("select count(*) from kb.sync_exclusions").fetchone()[0] == 0
    out = sync()
    assert out["status"] == "ok" and kb_count("sync_map", "conflict_at is not null") == 0


def test_plan_refuses_when_the_current_domains_are_not_the_owners_list():
    sync()
    from lib.kb import legacy_delete as ld
    with psycopg.connect(session_dsn()) as conn:
        with pytest.raises(SystemExit, match="REFUSED"):
            ld.plan(conn, ("full stack", "backend", "frontend", "test engineering"))


def test_the_cli_refuses_production(monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    env = {"SUPABASE_DB_URL_SESSION": "postgresql://u:p@db.yqmzjgzhxhihnpbgqmeh.supabase.co:5432/postgres", "PATH": ""}
    r = subprocess.run([sys.executable, str(repo / "pipeline" / "kb_legacy_delete.py"), "plan"], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "REFUSED" in (r.stderr + r.stdout)
