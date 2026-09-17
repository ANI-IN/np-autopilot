"""F1 — curation writes: admin only, optimistically locked, audited.

The concurrency test is the point of the file. A lost curation update is the
`Ambiguous`-collapse failure with a database underneath it: two people resolve
the `ML` alias differently within the same minute, last-write-wins, and the
losing decision vanishes with nobody told. Three shipped bugs in this project had
that shape, which is why `lib/resolve.py` returns Ambiguous rather than picking.

So the second writer must fail LOUDLY, and the test asserts both halves — the
second write raises, AND the first writer's value is what survives.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

from pipeline.lib import db                                           # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

from lib import curation_service as cs                                # noqa: E402
from lib import data                                                  # noqa: E402

ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-00000000fe01")
MEMBER_ID = uuid.UUID("00000000-0000-4000-8000-00000000fe02")
ALIAS = "ZZ-SYNTHETIC alias"

ADMIN = cs.Actor(str(ADMIN_ID), "admin@interviewkickstart.com", "admin")
MEMBER = cs.Actor(str(MEMBER_ID), "member@interviewkickstart.com", "member")
SHARED = cs.Actor(str(ADMIN_ID), "b2c-courses-new-programs@interviewkickstart.com",
                  "admin", shared_account=True)


@pytest.fixture
def seeded():
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('np.writing_through_service','on',true)")
            cur.execute("delete from domain_aliases where alias = %s", (ALIAS,))
            cur.execute(
                "insert into domain_aliases(alias, domain, claims, sibling_test, "
                "confirmed) values (%s,'PM',12,'failed',false)", (ALIAS,))
            for uid, role in ((ADMIN_ID, "admin"), (MEMBER_ID, "member")):
                cur.execute(
                    "insert into profiles(user_id,email,email_domain,role) values "
                    "(%s,%s,'interviewkickstart.com',%s) on conflict (user_id) "
                    "do update set role = excluded.role",
                    (uid, f"{role}@interviewkickstart.com", role))
            conn.commit()
    yield
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('np.writing_through_service','on',true)")
            cur.execute("delete from domain_aliases where alias = %s", (ALIAS,))
            cur.execute("delete from curation_audit where row_key = %s", (ALIAS,))
            cur.execute("delete from profiles where user_id = any(%s)",
                        ([ADMIN_ID, MEMBER_ID],))
            conn.commit()


def _version(conn, alias=ALIAS) -> int:
    with conn.cursor() as cur:
        cur.execute("select version from domain_aliases where alias = %s", (alias,))
        return cur.fetchone()[0]


# --------------------------------------------------------------------------
# THE concurrency test
# --------------------------------------------------------------------------

def test_two_concurrent_edits_the_second_fails_loudly(seeded):
    """Both writers read version N. Both decide. Only one may win, audibly."""
    with db.connect(db.SESSION) as first, db.connect(db.SESSION) as second:
        seen_by_both = _version(first)

        cs.update_row(first, ADMIN, "domain_aliases", ALIAS,
                      {"domain": "PM", "confirmed": True,
                       "confirmed_by": "first writer",
                       "confirmed_at": "2026-09-17"},
                      expected_version=seen_by_both,
                      reason="sibling test passed; PM is the only plausible target")
        first.commit()

        with pytest.raises(cs.StaleVersion) as exc:
            cs.update_row(second, ADMIN, "domain_aliases", ALIAS,
                          {"domain": "GPM (Growth Product Management)"},
                          expected_version=seen_by_both,
                          reason="I think it is GPM")
        second.rollback()

    msg = str(exc.value)
    assert "YOUR WRITE DID NOT HAPPEN" in msg
    assert f"not {seen_by_both}" in msg

    # The first writer's decision is what survives — the losing write left no mark.
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select domain, confirmed, confirmed_by, version "
                    "from domain_aliases where alias = %s", (ALIAS,))
        domain, confirmed, by, version = cur.fetchone()
    assert domain == "PM" and confirmed is True and by == "first writer"
    assert version == seen_by_both + 1, "version did not advance exactly once"


def test_a_stale_writer_is_told_what_the_row_is_now(seeded):
    """"0 rows affected" says neither "gone" nor "changed". This must."""
    with db.connect(db.SESSION) as conn:
        v = _version(conn)
        cs.update_row(conn, ADMIN, "domain_aliases", ALIAS, {"claims": 99},
                      expected_version=v, reason="recount")
        conn.commit()
        with pytest.raises(cs.StaleVersion) as exc:
            cs.update_row(conn, ADMIN, "domain_aliases", ALIAS, {"claims": 1},
                          expected_version=v, reason="stale")
        conn.rollback()
    assert f"is at version {v + 1}" in str(exc.value)


# --------------------------------------------------------------------------
# who may write
# --------------------------------------------------------------------------

def test_a_member_cannot_curate(seeded):
    with db.connect(db.SESSION) as conn:
        with pytest.raises(cs.NotPermitted):
            cs.update_row(conn, MEMBER, "domain_aliases", ALIAS, {"claims": 1},
                          expected_version=_version(conn), reason="nope")


def test_a_shared_account_cannot_curate(seeded):
    """Even holding admin: a curation change must be attributable to a person."""
    with db.connect(db.SESSION) as conn:
        with pytest.raises(cs.NotPermitted) as exc:
            cs.update_row(conn, SHARED, "domain_aliases", ALIAS, {"claims": 1},
                          expected_version=_version(conn), reason="nope")
    assert "attributable to a person" in str(exc.value)


def test_a_write_with_no_reason_is_refused(seeded):
    """The alias decisions are one word of value and a paragraph of reason."""
    with db.connect(db.SESSION) as conn:
        for blank in ("", "   ", None):
            with pytest.raises(cs.NoReason):
                cs.update_row(conn, ADMIN, "domain_aliases", ALIAS, {"claims": 1},
                              expected_version=_version(conn), reason=blank)


def test_only_declared_columns_can_be_set(seeded):
    with db.connect(db.SESSION) as conn:
        with pytest.raises(cs.NotPermitted):
            cs.update_row(conn, ADMIN, "domain_aliases", ALIAS,
                          {"version": 99}, expected_version=_version(conn),
                          reason="trying to forge the lock")


# --------------------------------------------------------------------------
# a direct write is refused
# --------------------------------------------------------------------------

def test_a_direct_update_bypassing_the_service_is_refused(seeded):
    """"Just this once, directly" must not be available."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        with pytest.raises(Exception) as exc:
            cur.execute("update domain_aliases set claims = 1 where alias = %s",
                        (ALIAS,))
        conn.rollback()
    assert "service layer" in str(exc.value)


# --------------------------------------------------------------------------
# the audit trail
# --------------------------------------------------------------------------

def test_every_write_is_audited_with_before_after_and_reason(seeded):
    with db.connect(db.SESSION) as conn:
        cs.update_row(conn, ADMIN, "domain_aliases", ALIAS,
                      {"domain": "GPM (Growth Product Management)"},
                      expected_version=_version(conn),
                      reason="owner confirmed this is the growth track")
        conn.commit()
        rows = cs.history(conn, "domain_aliases", ALIAS)
    assert rows, "no audit row written"
    entry = rows[0]
    assert entry["action"] == "update"
    assert entry["actor_email"] == "admin@interviewkickstart.com"
    assert entry["reason"] == "owner confirmed this is the growth track"
    assert entry["before_value"]["domain"] == "PM"
    assert entry["after_value"]["domain"] == "GPM (Growth Product Management)"


def test_the_audit_log_is_unreachable_by_the_people_it_describes(seeded):
    """An audit log its subjects can read — or edit — is not an audit log."""
    with data.request_connection(str(ADMIN_ID)) as conn, conn.cursor() as cur:
        with pytest.raises(Exception) as exc:
            cur.execute("select count(*) from curation_audit")
    assert "permission denied" in str(exc.value).lower()


def test_curation_audit_has_rls_and_no_policy():
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select relrowsecurity from pg_class where relname='curation_audit'")
        assert cur.fetchone()[0] is True
        cur.execute("select count(*) from pg_policies where tablename='curation_audit'")
        assert cur.fetchone()[0] == 0, "curation_audit has a policy; it should have none"


# --------------------------------------------------------------------------
# F3 — the alias surface
# --------------------------------------------------------------------------

def test_the_ambiguous_alias_surface_does_not_recommend(seeded):
    """A UI that ranks candidates reintroduces the picking one layer up."""
    with db.connect(db.SESSION) as conn:
        rows = cs.ambiguous_aliases(conn)
    assert rows, "no unconfirmed aliases surfaced"
    for r in rows:
        assert "recommended" not in r
        assert "best" not in r
        assert r["confirmed"] is False


def test_a_delete_through_the_service_actually_deletes():
    """0008's trigger ended `return new`, and NEW is NULL on DELETE — which
    CANCELS the row operation. Every curation delete was silently discarded and
    reported rowcount 0, indistinguishable from "the row was not there".

    Found by a teardown that could not clean up. Fixed in 0009. This test exists
    so the guard cannot silently swallow writes again, which is exactly the class
    of failure the guard was written to prevent.
    """
    probe = "ZZ-SYNTHETIC delete probe"
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('np.writing_through_service','on',true)")
            cur.execute("insert into domain_aliases(alias, domain, confirmed) "
                        "values (%s,'PM',false)", (probe,))
            conn.commit()
        with conn.cursor() as cur:
            cur.execute("select set_config('np.writing_through_service','on',true)")
            cur.execute("delete from domain_aliases where alias = %s", (probe,))
            assert cur.rowcount == 1, (
                f"delete affected {cur.rowcount} rows — the trigger is cancelling "
                "deletes again")
            conn.commit()
        with conn.cursor() as cur:
            cur.execute("select count(*) from domain_aliases where alias = %s",
                        (probe,))
            assert cur.fetchone()[0] == 0, "the row survived a 'successful' delete"


def test_the_alias_surface_carries_evidence_but_no_ranking():
    """F3. Everything needed to decide, nothing that decides."""
    with db.connect(db.SESSION) as conn:
        rows = cs.ambiguous_aliases(conn)
    by_alias = {r["alias"]: r for r in rows}
    for expected in ("ML", "Agentic AI", "Product Management"):
        assert expected in by_alias, f"{expected} is not surfaced"
        row = by_alias[expected]
        assert row["domain"] is None, "an unresolved alias must have no target"
        assert row["confirmed"] is False
        assert row["claims"] and row["claims"] > 0
        assert row["note"], "no reasoning recorded for the ambiguity"
        assert row["candidates"], "no candidates to choose between"
        # candidate order is the corpus owner's, not a ranking
        recorded = (row["props"] or {}).get("candidates") or []
        assert [c["domain"] for c in row["candidates"]] == recorded
        for c in row["candidates"]:
            assert "recommended" not in c and "score" not in c and "best" not in c


def test_a_field_that_cannot_be_computed_says_so():
    """A figure that always reads 0 because the data is absent reads as
    "no corroboration exists" when it means "we did not look"."""
    with db.connect(db.SESSION) as conn:
        rows = cs.ambiguous_aliases(conn)
    cands = [c for r in rows for c in r["candidates"] if c.get("exists")]
    assert cands
    for c in cands:
        assert c["corroboration"]["available"] is False
        assert "not projected" in c["corroboration"]["why"]
        assert "corroborating_claimants" not in c, (
            "a zero-valued corroboration field is back; it is indistinguishable "
            "from a measured zero")


def test_an_alias_with_no_candidate_domain_says_it_is_a_taxonomy_question():
    with db.connect(db.SESSION) as conn:
        rows = cs.ambiguous_aliases(conn)
    orphans = [r for r in rows if not r["candidates"]]
    assert orphans, "Applied Gen AI / Advanced Gen AI should surface as orphans"
    for r in orphans:
        assert "TAXONOMY" in r["no_candidates_note"]


def test_the_three_target_aliases_remain_unresolved():
    """Do NOT resolve them. This test is the guard on that instruction."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select alias, domain, confirmed from domain_aliases "
                    "where alias in ('ML','Agentic AI','Product Management')")
        for alias, domain, confirmed in cur.fetchall():
            assert domain is None and confirmed is False, (
                f"{alias} has been resolved to {domain!r}. These need a program "
                "owner at IK, not a heuristic and not an agent."
            )
