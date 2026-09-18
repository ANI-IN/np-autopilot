"""The hd corroboration must be read from where GoTrue actually writes it.

THE DEFECT, found by a real account being refused:

    grant_access.py refused animesh.kumar@interviewkickstart.com with
    "provider hd=None, not 'interviewkickstart.com'"

The account had signed in successfully, which means `/api/session` verified the
`hd` claim before GoTrue was contacted, and the migration-0007 hook accepted it
at user creation. The claim was present and correct. The script simply read the
wrong place:

    identity_data ->> 'hd'                      <- where it looked  (NULL)
    identity_data -> 'custom_claims' ->> 'hd'   <- where GoTrue puts it

GoTrue nests non-standard OIDC claims under `custom_claims`. So the guard
refused because it found nothing, where "nothing" meant "never recorded in the
shape I read" rather than "not true" — and it would have refused EVERY
legitimate account.

WHY NO TEST CAUGHT IT. Every existing auth test builds its own tokens and its
own rows. Not one of them had ever seen a row GoTrue wrote. The shape was an
assumption, and an assumption shared by the code and its tests is not tested at
all — §A.7a's "two checks sharing one source of truth", where the source is a
belief about someone else's schema.

So these tests read the REAL `auth.users` / `auth.identities` rows. They skip
when none exist, and that skip is the known blind spot: it is stated here so a
green CI run is not mistaken for coverage of this.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline import grant_access                                      # noqa: E402
from pipeline.lib import db                                            # noqa: E402

needs_db = pytest.mark.skipif(not db.available(),
                              reason="needs the Supabase connection")


def _real_users(cur):
    cur.execute("""
        select u.id, u.email
        from auth.users u
        join auth.identities i on i.user_id = u.id and i.provider = 'google'
    """)
    return cur.fetchall()


@needs_db
def test_hd_is_readable_from_every_real_google_identity():
    """THE TEST THAT WOULD HAVE CAUGHT IT.

    For every account GoTrue actually created, `_lookup` must return the hosted
    domain. A None here is the exact production failure.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        users = _real_users(cur)
        if not users:
            pytest.skip("no GoTrue-created accounts yet — THIS is the blind "
                        "spot that let the shape assumption through")
        missing = []
        for _uid, email in users:
            row = grant_access._lookup(cur, email)
            assert row is not None, f"_lookup found nothing for {email}"
            hd = row[2]
            if hd is None:
                missing.append(email)
            else:
                assert hd.lower() == grant_access.ALLOWED_HD, \
                    f"{email} carries hd={hd!r}"
        assert not missing, (
            f"no hd found for {missing}. These accounts exist, which means they "
            "already passed the domain check twice (/api/session before GoTrue, "
            "and the 0007 hook) — so this is GoTrue's storage shape having "
            "moved, not an identity problem. Inspect "
            "auth.identities.identity_data and add the path to HD_PATHS.")


@needs_db
def test_the_old_top_level_read_really_was_empty():
    """The negative control, against production data rather than a fixture.

    Proves the fix changed the answer: the path the first version used returns
    NULL for real rows, while the path it uses now returns the domain. Without
    this, `test_hd_is_readable...` could pass on a row that happened to carry
    both, and the regression would be invisible.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        if not _real_users(cur):
            pytest.skip("no GoTrue-created accounts yet")
        cur.execute("""
            select count(*) filter (where identity_data ->> 'hd' is not null),
                   count(*) filter (where identity_data -> 'custom_claims' ->> 'hd'
                                          is not null),
                   count(*)
            from auth.identities where provider = 'google'
        """)
        top_level, nested, total = cur.fetchone()
        assert total > 0
        assert nested == total, (
            f"only {nested} of {total} identities carry custom_claims.hd")
        assert top_level == 0, (
            "a top-level 'hd' has appeared in identity_data. That is not a "
            "failure, but HD_PATHS order and this test's premise should be "
            "re-checked against the new shape.")


@needs_db
def test_every_configured_hd_path_is_valid_sql():
    """HD_PATHS is a list of SQL fragments; a typo would read as NULL.

    A malformed path does not raise — `identity_data -> 'typo' ->> 'hd'` is
    perfectly legal SQL that returns NULL. So a broken entry degrades silently
    into the very failure this file exists for.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        for sql, name in grant_access.HD_PATHS:
            cur.execute(
                f"select {sql} from auth.identities where provider='google' limit 1")
            cur.fetchall()          # raises only on genuinely invalid SQL
        # And at least one path must actually produce a value somewhere.
        cur.execute("select count(*) from auth.identities where provider='google'")
        if cur.fetchone()[0] == 0:
            pytest.skip("no identities to resolve against")
        expr = "coalesce(" + ", ".join(s for s, _ in grant_access.HD_PATHS) + ")"
        cur.execute(f"select count(*) from auth.identities "
                    f"where provider='google' and {expr} is not null")
        assert cur.fetchone()[0] > 0, (
            "no configured path resolves an hd for any real identity; every "
            "entry in HD_PATHS is reading somewhere empty")


@needs_db
def test_a_granted_profile_carries_the_verified_domain():
    """The domain written into `profiles` is the CHECKed constant, not a guess."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select email, email_domain, role from profiles")
        for email, domain, role in cur.fetchall():
            assert domain == grant_access.ALLOWED_HD, \
                f"{email} has email_domain={domain!r}"
            assert role in grant_access.ROLES


# ---------------------------------------------------------------------------
# The shared-account rule, against the real shared account
# ---------------------------------------------------------------------------

SHARED = "b2c-courses-new-programs@interviewkickstart.com"


@needs_db
def test_the_shared_account_flag_is_derived_not_supplied(monkeypatch):
    """A CHECK keyed on a value the caller supplies is not a constraint.

    THE FAILURE THIS EXISTS FOR, found by running the guard against a real
    account: `grant --role recruiting` on the shared team mailbox SUCCEEDED.
    Both layers were inert.

      * The script consulted NP_SHARED_ACCOUNTS, which was set in Vercel and
        never in the environment the script runs in. An empty list means no
        account is shared, so there was nothing to refuse.
      * Migration 0008's CHECK is keyed on `is_shared_account`. The script had
        just written `false`. The constraint held perfectly, over a value that
        was already wrong.

    An unset variable made "no shared accounts exist" indistinguishable from "I
    was never told which accounts are shared" — A.7b, in a security control.

    Migration 0014 derives the flag with a trigger, so this asserts the
    derivation happens with the variable explicitly UNSET: the condition that
    produced the failure.
    """
    monkeypatch.delenv("NP_SHARED_ACCOUNTS", raising=False)
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from shared_accounts")
        assert cur.fetchone()[0] > 0, "the shared_accounts table is empty"

        cur.execute("select id from auth.users where lower(email) = %s", (SHARED,))
        row = cur.fetchone()
        if not row:
            pytest.skip("the shared account has not signed in")
        uid = row[0]

        # The flag must be derived even when the caller claims otherwise.
        for claimed in (False, True):
            cur.execute("""
                insert into profiles (user_id, email, email_domain, role,
                                      is_shared_account)
                values (%s, %s, 'interviewkickstart.com', 'member', %s)
                on conflict (user_id) do update set is_shared_account = excluded.is_shared_account
                returning is_shared_account
            """, (uid, SHARED, claimed))
            assert cur.fetchone()[0] is True, (
                f"caller claimed is_shared_account={claimed} and the database "
                "accepted it; the 0014 trigger is not deriving the flag")
        conn.rollback()


@needs_db
def test_a_shared_account_cannot_be_granted_recruiting_or_admin(monkeypatch):
    """The end-to-end refusal, with the variable unset."""
    monkeypatch.delenv("NP_SHARED_ACCOUNTS", raising=False)
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select id from auth.users where lower(email) = %s", (SHARED,))
        row = cur.fetchone()
        if not row:
            pytest.skip("the shared account has not signed in")
        uid = row[0]
        for role in ("recruiting", "admin"):
            with pytest.raises(Exception) as exc:
                cur.execute("""
                    insert into profiles (user_id, email, email_domain, role,
                                          is_shared_account)
                    values (%s, %s, 'interviewkickstart.com', %s, false)
                """, (uid, SHARED, role))
            assert "shared_accounts_stay_member" in str(exc.value), (
                f"a shared account was granted {role!r}: {exc.value}")
            conn.rollback()


@needs_db
def test_a_normal_account_is_not_flagged(monkeypatch):
    """The positive control: the rule must not catch everyone.

    Without this, a trigger that flagged every account would pass the two tests
    above while making `recruiting` ungrantable to anyone.
    """
    monkeypatch.delenv("NP_SHARED_ACCOUNTS", raising=False)
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""select email, is_shared_account from profiles
                       where lower(email) <> %s""", (SHARED,))
        rows = cur.fetchall()
        if not rows:
            pytest.skip("no non-shared profiles to check")
        for email, flagged in rows:
            assert flagged is False, f"{email} was wrongly flagged as shared"
