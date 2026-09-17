"""E1 — prove the member / recruiting boundary against SYNTHETIC sensitive rows.

Counter-intuitive ordering, and the point of the whole file: D3 projected ZERO
sensitive nodes, so a policy failure right now costs nothing. Once the real 277
hiring rejections land, testing a deny policy means risking exposure of the rows
the policy exists to hide — you would be proving the lock works by putting the
valuables behind it first.

So the rows here are fabricated. Structurally identical to the real ones — type
instructor, sensitive true, a pipeline_status of rejected or in_pipeline, their
own provenance and edges — and named so that a leak is unmistakable rather than
plausible.

Every test asserts the synthetic set is gone afterwards. Asserted, not assumed:
a cleanup that silently failed would leave fabricated people in a graph whose
whole value is that its records are traceable to a source.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db, taxonomy                                  # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

#: Unmistakably fabricated. If one of these ever appears in a real answer, the
#: leak is obvious rather than arguable.
SYNTH = [
    ("ins_ffffffffff000001", "ZZ-SYNTHETIC Rejected Candidate One", "rejected"),
    ("ins_ffffffffff000002", "ZZ-SYNTHETIC Rejected Candidate Two", "rejected"),
    ("ins_ffffffffff000003", "ZZ-SYNTHETIC Pipeline Candidate", "in_pipeline"),
]
SYNTH_IDS = [s[0] for s in SYNTH]
SYNTH_FILE = "03-instructors/ZZ-SYNTHETIC.xlsx"

MEMBER = uuid.UUID("00000000-0000-4000-8000-00000000fa01")
RECRUITER = uuid.UUID("00000000-0000-4000-8000-00000000fa02")
STRANGER = uuid.UUID("00000000-0000-4000-8000-00000000fa03")


def _as(conn, user_id, fn):
    """Run fn(cur) impersonating an authenticated user, then roll back.

    Sets request.jwt.claims the way Supabase's auth.uid() reads it, so the
    policies are exercised through exactly the mechanism production uses rather
    than through a test-only shortcut.
    """
    with conn.cursor() as cur:
        cur.execute("select set_config('request.jwt.claims', %s, true)",
                    (json.dumps({"sub": str(user_id), "role": "authenticated"}),))
        cur.execute('set local role "authenticated"')
        try:
            return fn(cur)
        finally:
            conn.rollback()


@pytest.fixture
def synthetic():
    """Insert the fabricated sensitive set and the two profiles; remove both."""
    inst = "instructor"
    prov = taxonomy.edge_for_role("provenance")
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into files(relative_path, parsed) values (%s, true) "
                        "on conflict do nothing", (SYNTH_FILE,))
            for nid, label, status in SYNTH:
                cur.execute(
                    "insert into nodes(id,type,label,label_raw,sensitive,props) "
                    "values (%s,%s,%s,%s,true,%s)",
                    (nid, inst, label, label,
                     json.dumps({"pipeline_status": status, "renderable": False})))
                cur.execute(
                    "insert into node_sources(id,node_id,origin,file,sheet,row_num,"
                    "ordinal) values (%s,%s,'corpus',%s,'Synthetic',1,0)",
                    (f"{'f'*32}{nid[-16:]}{'0'*16}"[:64], nid, SYNTH_FILE))
                cur.execute(
                    "insert into edges(rel,source_id,target_id) "
                    "select %s, %s, id from nodes where type='file' limit 1",
                    (prov, nid))
            for uid, role in ((MEMBER, "member"), (RECRUITER, "recruiting")):
                cur.execute(
                    "insert into profiles(user_id,email,email_domain,role) "
                    "values (%s,%s,'interviewkickstart.com',%s) "
                    "on conflict (user_id) do update set role = excluded.role",
                    (uid, f"synthetic-{role}@interviewkickstart.com", role))
            conn.commit()
    yield
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from nodes where id = any(%s)", (SYNTH_IDS,))
            cur.execute("delete from files where relative_path = %s", (SYNTH_FILE,))
            cur.execute("delete from profiles where user_id = any(%s)",
                        ([MEMBER, RECRUITER, STRANGER],))
            conn.commit()


def test_the_synthetic_rows_actually_exist_first(synthetic):
    """Without this, every deny below could be passing for the wrong reason."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from nodes where id = any(%s)", (SYNTH_IDS,))
        assert cur.fetchone()[0] == len(SYNTH)
        cur.execute("select count(*) from nodes where sensitive")
        assert cur.fetchone()[0] == len(SYNTH), (
            "the only sensitive rows must be the synthetic ones — a real "
            "sensitive row in the database would mean D3's scope was violated"
        )


def test_member_sees_zero_sensitive_rows(synthetic):
    with db.connect(db.SESSION) as conn:
        seen = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where sensitive"),
            cur.fetchone()[0])[1])
        assert seen == 0, f"member can see {seen} sensitive rows"
        by_id = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where id = any(%s)", (SYNTH_IDS,)),
            cur.fetchone()[0])[1])
        assert by_id == 0, "member can fetch a sensitive node by id"


def test_member_still_sees_the_public_graph(synthetic):
    """A deny that denies everything is not a boundary, it is an outage."""
    with db.connect(db.SESSION) as conn:
        n = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where not sensitive"),
            cur.fetchone()[0])[1])
        assert n > 3000, f"member sees only {n} public nodes"


def test_recruiting_sees_exactly_the_sensitive_rows(synthetic):
    with db.connect(db.SESSION) as conn:
        ids = _as(conn, RECRUITER, lambda cur: (
            cur.execute("select id from nodes where sensitive order by id"),
            [r[0] for r in cur.fetchall()])[1])
        assert ids == sorted(SYNTH_IDS), f"recruiting sees {ids}"
        total = _as(conn, RECRUITER, lambda cur: (
            cur.execute("select count(*) from nodes"), cur.fetchone()[0])[1])
        public = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes"), cur.fetchone()[0])[1])
        assert total == public + len(SYNTH), (
            "recruiting should see the public graph PLUS the sensitive rows"
        )


def test_an_identity_with_no_profile_sees_nothing(synthetic):
    """np_role() returns 'none' by default, so an unknown identity gets nothing
    rather than falling through to a permissive branch."""
    with db.connect(db.SESSION) as conn:
        n = _as(conn, STRANGER, lambda cur: (
            cur.execute("select count(*) from nodes"), cur.fetchone()[0])[1])
        assert n == 0, f"an identity with no profile sees {n} nodes"


def test_a_role_change_takes_effect_without_a_re_projection(synthetic):
    """The boundary is a policy, not a property of the data as loaded.

    If promoting someone required rebuilding the projection, every access change
    would be a data migration — and the temptation would be to project
    everything and filter in the app, which is the failure §D exists to prevent.
    """
    with db.connect(db.SESSION) as conn:
        before = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where sensitive"),
            cur.fetchone()[0])[1])
        assert before == 0
        with conn.cursor() as cur:
            cur.execute("update profiles set role='recruiting' where user_id=%s",
                        (MEMBER,))
            conn.commit()
        after = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where sensitive"),
            cur.fetchone()[0])[1])
        assert after == len(SYNTH), "promotion did not take effect immediately"
        with conn.cursor() as cur:
            cur.execute("update profiles set role='member' where user_id=%s", (MEMBER,))
            conn.commit()
        revoked = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from nodes where sensitive"),
            cur.fetchone()[0])[1])
        assert revoked == 0, "demotion did not take effect immediately"


def test_edges_and_provenance_follow_the_node(synthetic):
    """An edge to a hidden node leaks its existence and its id."""
    with db.connect(db.SESSION) as conn:
        e = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from edges where source_id = any(%s) "
                        "or target_id = any(%s)", (SYNTH_IDS, SYNTH_IDS)),
            cur.fetchone()[0])[1])
        assert e == 0, f"member can see {e} edges touching a sensitive node"
        s = _as(conn, MEMBER, lambda cur: (
            cur.execute("select count(*) from node_sources where node_id = any(%s)",
                        (SYNTH_IDS,)),
            cur.fetchone()[0])[1])
        assert s == 0, f"member can see {s} provenance rows for sensitive nodes"
        r = _as(conn, RECRUITER, lambda cur: (
            cur.execute("select count(*) from node_sources where node_id = any(%s)",
                        (SYNTH_IDS,)),
            cur.fetchone()[0])[1])
        assert r == len(SYNTH), "recruiting cannot see sensitive provenance"


def test_a_member_cannot_write_anything(synthetic):
    """SELECT-only policies. No INSERT/UPDATE/DELETE policy exists at all.

    Each statement gets its own transaction: once one fails the transaction is
    aborted, and reusing it would make later statements "fail" for the wrong
    reason — which would read as coverage.
    """
    attempts = [
        ("insert into nodes(id,type,label,sensitive) values "
         "('ins_ffffffffff0000ff','instructor','x',false)", None),
        ("update nodes set label='x' where id = any(%s)", (SYNTH_IDS,)),
        ("delete from nodes where id = any(%s)", (SYNTH_IDS,)),
    ]
    with db.connect(db.SESSION) as conn:
        for sql, args in attempts:
            with conn.cursor() as cur:
                cur.execute("select set_config('request.jwt.claims', %s, true)",
                            (json.dumps({"sub": str(MEMBER),
                                         "role": "authenticated"}),))
                cur.execute('set local role "authenticated"')
                with pytest.raises(Exception):
                    cur.execute(sql, args)
            conn.rollback()
        # and the rows are untouched
        with conn.cursor() as cur:
            cur.execute("select count(*) from nodes where id = any(%s)", (SYNTH_IDS,))
            assert cur.fetchone()[0] == len(SYNTH), "a write got through"


def test_the_synthetic_set_is_removed_afterwards():
    """Runs without the fixture, AFTER the tests above have torn it down.

    Asserted rather than assumed: a cleanup that silently failed would leave
    fabricated people in a graph whose whole value is traceable records.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from nodes where id = any(%s)", (SYNTH_IDS,))
        assert cur.fetchone()[0] == 0, "synthetic nodes survived"
        cur.execute("select count(*) from nodes where label like 'ZZ-SYNTHETIC%'")
        assert cur.fetchone()[0] == 0, "a synthetic label survived"
        cur.execute("select count(*) from nodes where sensitive")
        assert cur.fetchone()[0] == 0, "sensitive rows remain in the database"
        cur.execute("select count(*) from files where relative_path = %s", (SYNTH_FILE,))
        assert cur.fetchone()[0] == 0, "the synthetic file node survived"
        cur.execute("select count(*) from profiles where email like 'synthetic-%'")
        assert cur.fetchone()[0] == 0, "synthetic profiles survived"


def test_anon_holds_no_grants_at_all():
    """Supabase grants ALL to anon and authenticated by default in `public`.

    Found by testing: a member's UPDATE returned "NO ERROR, rowcount=0" — RLS
    held, but silently, because the grant was there and only the absence of a
    policy stopped it. Migration 0006 revokes the defaults and sets them for
    future tables, so a new table in a later migration cannot re-inherit them.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select table_name, grantee, privilege_type
            from information_schema.role_table_grants
            where table_schema = 'public' and grantee = 'anon'""")
        anon = cur.fetchall()
        assert not anon, f"anon holds grants it should not: {anon[:5]}"

        cur.execute("""
            select table_name, string_agg(distinct privilege_type, ',')
            from information_schema.role_table_grants
            where table_schema = 'public' and grantee = 'authenticated'
            group by table_name order by table_name""")
        for table, privs in cur.fetchall():
            assert privs == "SELECT", (
                f"authenticated holds {privs} on {table}; read-only means SELECT"
            )


def test_a_newly_created_table_grants_nothing_to_anon_or_authenticated():
    """Behavioural, not ACL-reading, and the distinction mattered.

    Reading pg_default_acl naively fails: there are TWO sets in `public`, one
    owned by `postgres` and one by `supabase_admin`. 0006 revoked the postgres
    one — which is the role migrations run as — and cannot alter the
    supabase_admin one without being that role. So the ACL text still mentions
    anon, while a table created by a migration grants it nothing.

    Creating a real table and inspecting its grants answers the question that
    actually matters: does the next `create table` in a migration reopen the
    hole? Reading the ACL answers a different one.
    """
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("create table np_grant_probe (id int primary key)")
            cur.execute("""
                select grantee, privilege_type
                from information_schema.role_table_grants
                where table_name = 'np_grant_probe'
                  and grantee in ('anon', 'authenticated')""")
            leaked = cur.fetchall()
            cur.execute("drop table np_grant_probe")
            conn.commit()
    assert not leaked, (
        f"a newly created table granted {leaked} — the next migration's tables "
        "inherit Supabase's permissive defaults and the hole reopens silently"
    )


def test_migrations_run_as_the_role_whose_defaults_were_revoked():
    """0006 is only effective for tables created by this role. Pin that."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select current_user")
        who = cur.fetchone()[0]
        cur.execute("""
            select d.defaclacl::text
            from pg_default_acl d
            join pg_namespace n on n.oid = d.defaclnamespace
            where n.nspname = 'public' and d.defaclobjtype = 'r'
              and pg_get_userbyid(d.defaclrole) = %s""", (who,))
        row = cur.fetchone()
    assert row, f"no default ACL owned by {who}; 0006 may not have applied"
    acl = row[0]
    for role in ("anon=", "authenticated="):
        assert role not in acl, (
            f"default privileges for {who} still grant to {role.rstrip('=')}: {acl}"
        )
