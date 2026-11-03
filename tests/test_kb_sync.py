"""Run 5: the sync from the original site's tables (web/lib/kb/sync.py), the
legacy step (web/lib/kb/legacy.py), owners by role and person accounts.

The source is a SYNTHETIC copy of the old tables in a schema of its own
(`kbsync_src`), so every rule is exercised on a few rows:
  NP Autopilot's categories (legacy module / domain / instructor / programme),
  P/B1-B3 only from the mastersheet, owners from roles, no merging by name,
  idempotent re-run, a source change applies, an app edit is never overwritten
  (conflict), a removed row is flagged (never deleted), KB-created records are
  never touched, one run at a time, the kill switch, the cron secret, the time
  budget, the legacy archive (re-runnable, one-command restore), the actor
  "Sync", person accounts now and on a future sign-in, and "no owner".
No real data: every name below is made up."""
from __future__ import annotations

import json
import uuid

import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

SRC = "kbsync_src"
# Projection type and relationship names come from the mapping (the taxonomy is
# the single source; config/kb-projection-mapping.yaml is checked against it).
from lib.kb import sync as _engine                                      # noqa: E402
R = _engine.load_mapping()["roles"]
ADMIN = USERS["admin"]

NODES = [
    # id, type, label, props
    ("dom_cur", "domain", "Domain Current", {}),
    ("dom_old", "domain", "Domain Old", {}),
    ("mod_cur", "module", "Module Current", {"domain_slug": "dc"}),
    ("mod_old", "module", "Module Old", {}),
    ("mod_lost", "module", "Module Unlinked", {}),
    ("ins_p", "instructor", "Ada Example", {}),
    ("ins_b1", "instructor", "Ben Example", {}),
    ("ins_old", "instructor", "Cy Example", {}),
    ("prog", "program", "Programme Old", {}),
    ("ses", R["session"], "Session One", {}),
    ("top_a", R["topic"], "Introduction", {}),
    ("top_b", R["topic"], "Introduction", {}),
    ("deck", R["deck"], "Deck One", {"drive_url": "https://docs.google.com/presentation/d/kbsync-test-deck"}),
    ("pers", "person", "Dee Example", {}),
]
EDGES = [
    # rel, source, target, props
    (R["domain_offers"], "dom_cur", "mod_cur", {}),
    (R["domain_offers"], "dom_old", "mod_old", {}),
    ("covers", "prog", "dom_old", {}),
    ("contains", "prog", "mod_old", {}),
    (R["teaching_reversed"], "mod_cur", "ins_p", {"tier": "mastersheet", "instructor_role": "primary"}),
    (R["teaching_reversed"], "mod_cur", "ins_b1", {"tier": "mastersheet", "instructor_role": "backup_1"}),
    # the older sheets say ins_b1 is "primary": must NOT become P
    ("teaches", "ins_b1", "mod_cur", {"tier": "legacy", "role": "primary"}),
    ("teaches", "ins_old", "mod_old", {"tier": "legacy", "role": "primary"}),
    (R["session_link"], "mod_cur", "ses", {}),
    (R["topic_link"], "mod_cur", "top_a", {}),
    (R["topic_link"], "mod_old", "top_b", {}),
    (R["deck_link"], "mod_cur", "deck", {}),
    (R["owner_link"], "dom_cur", "pers", {}),
]


def _make_source():
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
        for i, t, lab, p in NODES:
            c.execute(f"insert into {SRC}.nodes (id, type, label, props) values (%s, %s, %s, %s)", (i, t, lab, json.dumps(p)))
        for rel, s, t, p in EDGES:
            c.execute(f"insert into {SRC}.edges (rel, source_id, target_id, props) values (%s, %s, %s, %s)", (rel, s, t, json.dumps(p)))


CORE_SNAPSHOT = {}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.delenv("KB_SYNC_ENABLED", raising=False)
    ensure_users()
    reset()
    with owner() as c:
        c.execute("truncate kb.sync_map, kb.sync_runs, kb.legacy_archive, kb.person_accounts")
        CORE_SNAPSHOT["types"] = c.execute("select key, allowed_parents from kb.node_types where is_core").fetchall()
    _make_source()
    yield
    reset()
    with owner() as c:
        c.execute("truncate kb.sync_map, kb.sync_runs, kb.legacy_archive, kb.person_accounts")
        c.execute(f"drop schema if exists {SRC} cascade")
        c.execute("delete from kb.node_types where not is_core")
        c.execute("delete from kb.edge_types where not is_core")
        for key, parents in CORE_SNAPSHOT["types"]:
            c.execute("update kb.node_types set allowed_parents = %s where key = %s and allowed_parents <> %s", (parents, key, parents))
        assert c.execute("select count(*) from kb.node_types where is_core and fields::text like '%%family%%' and not fields::text like '%%archived%%'").fetchone()[0] == 0
        c.execute("delete from auth.users where email like 'kbsync-later-%%'")


def call_app(method, path, headers=None):
    """The WSGI app with no user session (the cron caller)."""
    import io
    c = Client(None)
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(b"")}
    for k, v in (headers or {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v
    out = {}
    payload = b"".join(c.app(env, lambda st, h: out.update(status=int(st.split()[0]))))
    return out["status"], (json.loads(payload) if payload else None)


def sync(**kw):
    import psycopg
    from kb_support import session_dsn
    from lib.kb import sync as engine
    # The shared test database's CORE types are left alone (fields can never be
    # removed again, rightly): no added fields or placement; the two new
    # record types are created and dropped per test.
    M = dict(engine.load_mapping(), type_fields={}, placement={})
    with psycopg.connect(session_dsn()) as conn:
        return engine.run(conn, trigger="cli", actor_id=ADMIN, source=SRC, mapping=M, **kw)


def legacy(cmd):
    import psycopg
    from kb_support import session_dsn
    from lib.kb import legacy as lg
    with psycopg.connect(session_dsn()) as conn:
        out = getattr(lg, cmd)(conn)
        conn.commit()
        return out


def rec(np_id):
    with owner() as c:
        r = c.execute("""select n.id, n.name, n.is_legacy, n.owner_record_id, n.co_owner_record_ids, n.archived_at,
                                n.review_status, n.version, n.owner_id from kb.nodes n where n.external_id = %s""", ("np:" + np_id,)).fetchone()
    return None if r is None else dict(zip(("id", "name", "legacy", "owner_rec", "co", "archived", "review", "version", "owner_id"), r))


def src(sql, p=()):
    with owner() as c:
        c.execute(sql.replace("SRC.", SRC + "."), p)


def kb_count(table, where="true"):
    with owner() as c:
        return c.execute(f"select count(*) from kb.{table} where {where}").fetchone()[0]


# ---------------------------------------------------------------- categories, roles, owners
def test_first_run_follows_np_autopilot():
    out = sync()
    assert out["status"] == "ok"
    assert rec("dom_cur")["legacy"] is False and rec("dom_old")["legacy"] is True
    assert rec("mod_cur")["legacy"] is False and rec("mod_old")["legacy"] is True
    assert rec("ins_p")["legacy"] is False and rec("ins_b1")["legacy"] is False and rec("ins_old")["legacy"] is True
    assert rec("prog")["legacy"] is True
    # legacy is tagged
    with owner() as c:
        assert c.execute("""select count(*) from kb.node_tags nt join kb.tags g on g.id = nt.tag_id
                            where g.name = 'legacy'""").fetchone()[0] == 5


def test_roles_only_from_the_mastersheet_and_owners_from_roles():
    sync()
    with owner() as c:
        roles = dict(c.execute("""select n.external_id, e.props->>'role' from kb.edges e join kb.nodes n on n.id = e.source_id
                                  join kb.edge_types et on et.id = e.edge_type_id and et.key = 'teaches'""").fetchall())
    assert roles["np:ins_p"] == "primary"
    assert roles["np:ins_b1"] == "backup_1"          # the older sheets' "primary" does not override it
    assert roles["np:ins_old"] is None               # older sheets only: no P/B role
    m = rec("mod_cur")
    assert str(m["owner_rec"]) == str(rec("ins_p")["id"])
    assert [str(x) for x in m["co"]] == [str(rec("ins_b1")["id"])]
    assert str(rec("dom_cur")["owner_rec"]) == str(rec("pers")["id"])


def test_same_names_are_not_merged():
    sync()
    a, b = rec("top_a"), rec("top_b")
    assert a and b and a["id"] != b["id"]
    assert a["name"] == b["name"] == "Introduction"        # scoped to different modules


def test_rerun_writes_nothing():
    sync()
    v = rec("mod_cur")["version"]
    out = sync()
    assert out["created"] == {} and out["updated"] == {} and out["conflicts"] == {}
    assert rec("mod_cur")["version"] == v


# ---------------------------------------------------------------- incremental, conflicts, removals
def test_source_change_applies_to_an_unedited_record():
    sync()
    src("update SRC.nodes set label = 'Session Renamed' where id = 'ses'")
    out = sync()
    assert out["updated"].get("record") == 1
    assert rec("ses")["name"] == "Session Renamed"


def test_added_source_row_is_created():
    sync()
    src("insert into SRC.nodes (id, type, label, props) values ('ses2', %s, 'Session Two', '{}')", (R["session"],))
    src("insert into SRC.edges (rel, source_id, target_id, props) values (%s, 'mod_cur', 'ses2', '{}')", (R["session_link"],))
    out = sync()
    assert out["created"].get("record: session") == 1
    assert rec("ses2") is not None


def test_app_edit_is_never_overwritten_and_becomes_a_conflict():
    sync()
    admin = Client(ADMIN)
    r = rec("ses")
    s, _ = admin.patch(f"/api/kb/nodes/{r['id']}", {"version": r["version"], "name": "Edited In The App"})
    assert s == 200
    src("update SRC.nodes set label = 'Changed At Source' where id = 'ses'")
    out = sync()
    assert out["conflicts"].get("record") == 1
    assert rec("ses")["name"] == "Edited In The App"
    s, counts = admin.get("/api/kb/counts")
    assert counts["attention"]["counts"]["sync_conflicts"] == 1
    s, issues = admin.get("/api/kb/quality/sync")
    assert [str(x["id"]) for x in issues["conflicts"]] == [str(r["id"])]
    s, node = admin.get(f"/api/kb/nodes/{r['id']}")
    assert node["sync"]["conflict_at"]


def test_removed_source_row_is_flagged_never_deleted():
    sync()
    src("delete from SRC.edges where target_id = 'ses'")
    src("delete from SRC.nodes where id = 'ses'")
    out = sync()
    assert out["removed_at_source"].get("record") == 1
    r = rec("ses")
    assert r is not None and r["archived"] is None and r["review"] == "needs_review"
    # its relationship is archived (reversible), not deleted
    assert kb_count("edges", f"(source_id = '{r['id']}' or target_id = '{r['id']}') and archived_at is not null") == 1
    assert Client(ADMIN).get("/api/kb/counts")[1]["attention"]["counts"]["removed_at_source"] == 1
    # back at the source: un-flagged, relationship restored
    src("insert into SRC.nodes (id, type, label, props) values ('ses', %s, 'Session One', '{}')", (R["session"],))
    src("insert into SRC.edges (rel, source_id, target_id, props) values (%s, 'mod_cur', 'ses', '{}')", (R["session_link"],))
    sync()
    assert kb_count("edges", f"(source_id = '{r['id']}' or target_id = '{r['id']}') and archived_at is null") == 1
    assert kb_count("sync_map", "removed_at is not null") == 0


def test_kb_created_records_are_never_touched():
    sync()
    admin = Client(ADMIN)
    s, made = admin.post("/api/kb/nodes", {"type": "topic", "name": "Made In The KB"})
    assert s == 201, made
    sync()
    with owner() as c:
        name, version = c.execute("select name, version from kb.nodes where id = %s", (made["id"],)).fetchone()
        assert (name, version) == ("Made In The KB", made["version"])
        assert c.execute("select count(*) from kb.sync_map where kb_id = %s", (made["id"],)).fetchone()[0] == 0


# ---------------------------------------------------------------- one at a time, switches, budget
def test_one_run_at_a_time():
    with owner() as c:
        c.execute("insert into kb.sync_runs (trigger) values ('cron')")             # a run in progress
    out = sync()
    assert out["status"] == "skipped"
    with owner() as c:
        assert c.execute("select count(*) from kb.sync_runs where status = 'skipped'").fetchone()[0] == 1
        # a run older than the stale limit no longer blocks
        c.execute("update kb.sync_runs set started_at = now() - interval '1 hour' where status = 'running'")
    assert sync()["status"] == "ok"


def test_kill_switch(monkeypatch):
    from lib.kb import sync as engine, sync_api
    monkeypatch.setenv("KB_SYNC_ENABLED", "false")
    with pytest.raises(engine.SyncDisabled):
        sync()
    assert sync_api.run_now("cron", None)["status"] == "disabled"
    assert kb_count("nodes") == 0


def test_cron_route_needs_the_secret(monkeypatch):
    monkeypatch.setenv("KB_SYNC_SECRET", "s" * 32)
    monkeypatch.setenv("KB_SYNC_ENABLED", "false")                                   # never actually runs here
    assert call_app("POST", "/api/cron/kb-sync")[0] == 401
    assert call_app("POST", "/api/cron/kb-sync", headers={"authorization": "Bearer wrong"})[0] == 401
    status, body = call_app("POST", "/api/cron/kb-sync", headers={"authorization": "Bearer " + "s" * 32})
    assert status == 200 and body["status"] == "disabled"
    monkeypatch.setenv("KB_SYNC_SECRET", "short")                                   # a weak secret opens nothing
    assert call_app("POST", "/api/cron/kb-sync", headers={"authorization": "Bearer short"})[0] == 401


def test_sync_routes_are_admin_only():
    assert Client(USERS["editor"]).get("/api/kb/sync")[0] == 403
    assert Client(USERS["editor"]).post("/api/kb/sync/run", {})[0] == 403
    assert Client(ADMIN).get("/api/kb/sync")[0] == 200


def test_time_budget_stops_and_the_next_run_continues():
    out = sync(budget_seconds=0.0001, batch=1)
    assert out["status"] == "ok" and out["partial"] is True
    done = kb_count("nodes")
    out = sync()
    assert out["partial"] is False and kb_count("nodes") > done
    assert sync()["created"] == {}


def test_writes_are_attributed_to_sync():
    sync()
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log where actor_type = 'sync'").fetchone()[0] > 0
        assert c.execute("select count(*) from kb.audit_log where actor_type <> 'sync' and table_name = 'nodes'").fetchone()[0] == 0
    s, act = Client(ADMIN).get("/api/kb/activity", "source=sync")
    assert s == 200 and act["items"] and all(x["actor_label"].startswith("Sync") for x in act["items"])


# ---------------------------------------------------------------- legacy
def test_legacy_hidden_by_default_and_filterable():
    sync()
    admin = Client(ADMIN)
    cur = admin.get("/api/kb/nodes", "limit=200")[1]["items"]
    assert all(not x["is_legacy"] for x in cur)
    only = admin.get("/api/kb/nodes", "limit=200&legacy=only")[1]["items"]
    assert only and all(x["is_legacy"] for x in only)
    assert admin.get("/api/kb/nodes", "legacy=bogus")[0] == 422


def test_legacy_archive_is_rerunnable_and_restores_exactly():
    sync()
    before = (kb_count("nodes", "archived_at is null"), kb_count("edges", "archived_at is null"),
              kb_count("node_resources", "archived_at is null"))
    out = legacy("archive")
    assert out["archived_now"] == {"domains": 1, "modules": 1, "instructors": 1}
    assert rec("dom_old")["archived"] and rec("mod_old")["archived"] and rec("ins_old")["archived"]
    assert rec("mod_lost")["archived"] is None             # no domain at all: left as it is
    assert rec("mod_cur")["archived"] is None and rec("ins_b1")["archived"] is None
    assert legacy("archive")["archived_now"] == {"domains": 0, "modules": 0, "instructors": 0}
    # the sync keeps it applied, with no false conflicts
    out = sync()
    assert out["conflicts"] == {} and out["updated"] == {}
    legacy("restore")
    after = (kb_count("nodes", "archived_at is null"), kb_count("edges", "archived_at is null"),
             kb_count("node_resources", "archived_at is null"))
    assert after == before


def test_legacy_never_archives_what_a_current_item_uses():
    src("insert into SRC.edges (rel, source_id, target_id, props) values (%s, 'ins_p', 'dom_old', '{}')", (R["expertise"],))
    sync()
    out = legacy("archive")
    assert out["archived_now"]["domains"] == 0
    assert out["domains_with_current_connections"] == [str(rec("dom_old")["id"])]


# ---------------------------------------------------------------- person accounts, no owner
def test_person_account_now_and_on_a_future_sign_in():
    sync()
    admin = Client(ADMIN)
    ins = rec("ins_p")
    # an existing sign-in: resolves at once, and they own what the record owns by role
    s, acc = admin.post(f"/api/kb/nodes/{ins['id']}/account", {"email": "KBTEST-editor@interviewkickstart.com"})
    assert s == 200 and str(acc["user_id"]) == USERS["editor"]
    assert str(rec("mod_cur")["owner_id"]) == USERS["editor"]
    # a person who has not signed in yet: linked on their first sign-in
    b1 = rec("ins_b1")
    later = "kbsync-later-" + uuid.uuid4().hex[:8] + "@interviewkickstart.com"
    s, acc = admin.post(f"/api/kb/nodes/{b1['id']}/account", {"email": later})
    assert s == 200 and acc["user_id"] is None
    uid = str(uuid.uuid4())
    with owner() as c:
        # their first sign-in: the auth user (its profile is created by the sign-up trigger)
        c.execute("insert into auth.users (id, email, created_at) values (%s, %s, now())", (uid, later))
        c.execute("""insert into profiles (user_id, email, email_domain, role) values (%s, %s, 'interviewkickstart.com', 'member')
                     on conflict (user_id) do nothing""", (uid, later))
        assert str(c.execute("select user_id from kb.person_accounts where node_id = %s", (b1["id"],)).fetchone()[0]) == uid
        co = c.execute("select co_owners from kb.nodes where id = %s", (rec("mod_cur")["id"],)).fetchone()[0]
        assert uid in [str(x) for x in co]
    # only admins link accounts
    assert Client(USERS["editor"]).post(f"/api/kb/nodes/{ins['id']}/account", {"email": "x@interviewkickstart.com"})[0] == 403


def test_no_owner_counts_only_records_without_any_owner():
    sync()
    with owner() as c:
        want = c.execute("""select count(*) from kb.nodes where archived_at is null and not is_legacy
                            and owner_id is null and owner_record_id is null""").fetchone()[0]
        with_role = c.execute("select count(*) from kb.nodes where not is_legacy and owner_record_id is not null").fetchone()[0]
    assert with_role == 2                                    # mod_cur (P) and dom_cur (owned_by)
    assert Client(ADMIN).get("/api/kb/counts")[1]["attention"]["counts"]["no_owner"] == want


def test_owner_record_must_be_a_person():
    sync()
    admin = Client(ADMIN)
    m = rec("mod_cur")
    s, body = admin.patch(f"/api/kb/nodes/{m['id']}", {"version": m["version"], "owner_record_id": str(rec("ses")["id"])})
    assert s == 422
    s, body = admin.patch(f"/api/kb/nodes/{m['id']}", {"version": m["version"], "co_owner_record_ids": [str(rec("ins_b1")["id"]), str(rec("ins_p")["id"])]})
    assert s == 200, body


# ---------------------------------------------------------------- operator mode (first import on a new database)
def test_operator_mode_is_only_for_the_table_owner():
    import psycopg
    from kb_support import as_user, session_dsn
    from lib.kb import service as svc
    with as_user(USERS["viewer"]) as conn:                      # a request connection asking for it
        conn.execute("select set_config('kb.operator', 'on', true)")
        assert svc.role(conn) == "viewer"
    with as_user(None) as conn:
        conn.execute("select set_config('kb.operator', 'on', true)")
        assert svc.role(conn) == "none"
    with psycopg.connect(session_dsn()) as conn:                # the owner without asking: no admin
        assert svc.role(conn) == "none"
        conn.execute("select set_config('kb.operator', 'on', true)")
        assert svc.role(conn) == "admin"


def test_first_import_as_operator_without_any_admin():
    import psycopg
    from kb_support import session_dsn
    from lib.kb import sync as engine
    M = dict(engine.load_mapping(), type_fields={}, placement={})
    with psycopg.connect(session_dsn()) as conn:
        with pytest.raises(RuntimeError):                        # no admin, no operator: refuses
            engine.run(conn, trigger="cron", actor_id=None, source=SRC, mapping=M)
    with psycopg.connect(session_dsn()) as conn:
        out = engine.run(conn, trigger="cli", actor_id=None, source=SRC, mapping=M, operator=True)
    assert out["status"] == "ok" and rec("mod_cur") is not None


def test_a_failure_is_in_the_run_log_and_raises_the_admin_banner(monkeypatch):
    from lib.kb import sync as engine

    def broken():
        raise RuntimeError("mapping names what the taxonomy does not define")
    monkeypatch.setattr(engine, "load_mapping", broken)
    import psycopg
    from kb_support import session_dsn
    with psycopg.connect(session_dsn()) as conn, pytest.raises(RuntimeError):
        engine.run(conn, trigger="cron", actor_id=None, source=SRC)
    s, st = Client(ADMIN).get("/api/kb/sync")
    assert s == 200 and st["failing"] is True and st["last"]["status"] == "error"
    assert "mapping" in st["last"]["errors"][0]
