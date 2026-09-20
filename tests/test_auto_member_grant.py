"""0015 — a verified IK Workspace identity becomes a `member` automatically.

This reverses part of Q3's default: until now a profile was created only by an
administrator running pipeline/grant_access.py. The reversal is recorded in
docs/AUTH.md, because it changes what "a profile grants access" means.

WHAT THESE TESTS ARE FOR. The auto path must be incapable of three things, and
each has its own test rather than being argued from the SQL:

  * granting anything but `member`,
  * granting anything at all to a non-IK identity,
  * demoting somebody who already has a role.

The third matters most in the least obvious way: `on conflict do nothing` and
`on conflict do update` are one word apart, and the wrong one silently demotes
an admin to member on a replayed insert. A test that only checked "a new user
gets member" passes either way.
"""
from __future__ import annotations

import re as _re
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

IK = "interviewkickstart.com"
#: Synthetic identities. Local parts are unmistakably not people.
IDS = {
    "ik":       uuid.UUID("00000000-0000-4000-8000-00000000ac01"),
    "outside":  uuid.UUID("00000000-0000-4000-8000-00000000ac02"),
    "existing": uuid.UUID("00000000-0000-4000-8000-00000000ac03"),
    "shared":   uuid.UUID("00000000-0000-4000-8000-00000000ac04"),
}


def _cleanup(cur):
    cur.execute("delete from profiles where user_id = any(%s)", (list(IDS.values()),))
    cur.execute("delete from auth.users where id = any(%s)", (list(IDS.values()),))


@pytest.fixture
def signup():
    """Creates auth.users rows the way GoTrue does, and removes them after.

    Inserting into auth.users is what fires the trigger; nothing else does. A
    test that wrote to `profiles` directly would exercise the constraints and
    never the grant.
    """
    made: list[uuid.UUID] = []

    def _make(key: str, email: str, preset_role: str | None = None):
        uid = IDS[key]
        with db.connect(db.SESSION) as conn, conn.cursor() as cur:
            if preset_role:
                cur.execute(
                    "insert into profiles (user_id, email, email_domain, role) "
                    "values (%s, %s, %s, %s)", (uid, email, IK, preset_role))
            # created_at as GoTrue sets it. The column is nullable, and a row
            # without it cannot be placed either side of the migration — see
            # the undatable case in grant_access._unprovisioned.
            cur.execute("insert into auth.users (id, email, created_at) "
                        "values (%s, %s, now())", (uid, email))
            conn.commit()
        made.append(uid)
        return uid

    yield _make

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        _cleanup(cur)
        conn.commit()


def _profile(uid):
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select role, email_domain, is_shared_account "
                    "from profiles where user_id = %s", (uid,))
        return cur.fetchone()


def test_an_ik_workspace_identity_gets_member_automatically(signup):
    uid = signup("ik", f"np-test-autogrant@{IK}")
    row = _profile(uid)
    assert row is not None, (
        "an IK Workspace identity signed up and got no profile — the whole "
        "point of 0015")
    role, domain, _shared = row
    assert role == "member"
    assert domain == IK


def test_a_non_ik_identity_still_gets_nothing(signup):
    """The mandatory condition. Layer 3 refuses these before they become a row
    at all; this proves that if one ever did, it would still get no profile."""
    # contact-ok: synthetic outsider identity; belongs to nobody, and the
    # assertion is that it is granted nothing.
    uid = signup("outside", "np-test-outsider@gmail.com")
    assert _profile(uid) is None, (
        "a non-IK identity was granted a profile by the auto path")


def test_the_auto_path_grants_member_and_only_member(signup):
    """`recruiting` and `admin` stay manual.

    Behavioural, not a grep of the SQL: the role that actually lands in the row
    is asserted, so an edit that made the role an expression would have to keep
    producing 'member' to pass.
    """
    uid = signup("ik", f"np-test-autogrant@{IK}")
    role, _, _ = _profile(uid)
    assert role == "member", f"the auto path granted {role!r}"


def test_an_existing_profile_is_never_demoted(signup):
    """`on conflict do nothing`, not `do update`.

    One word apart, and the wrong one quietly demotes an administrator to
    member. "A new user gets member" passes either way, so this is the only
    test that can tell them apart.
    """
    uid = signup("existing", f"np-test-existing@{IK}", preset_role="admin")
    role, _, _ = _profile(uid)
    assert role == "admin", (
        f"signup overwrote an existing profile, demoting admin -> {role!r}")


def test_a_shared_mailbox_is_auto_granted_but_still_capped(signup):
    """0014's derivation and 0008's CHECK must still hold on this path.

    A shared mailbox may hold `member` — that is exactly what the auto path
    grants — so the two agree by construction. What must remain true is that
    the flag is still DERIVED on a row this trigger wrote, because the cap that
    depends on it is inert if it is merely defaulted.

    Registers its OWN synthetic shared account: the real one already exists in
    auth.users, and reusing it would collide on the email unique index.
    """
    local = "np-test-shared-mailbox"
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("insert into shared_accounts (local_part, note) values "
                    "(%s, %s) on conflict (local_part) do nothing",
                    (local, "synthetic, created by tests/test_auto_member_grant.py"))
        conn.commit()
    try:
        uid = signup("shared", f"{local}@{IK}")
        profile = _profile(uid)
        assert profile is not None, "a shared IK mailbox got no profile"
        role, _, shared = profile
        assert role == "member"
        assert shared is True, (
            "is_shared_account was not derived on the auto-granted row — "
            "0014's trigger did not fire, so the cap that depends on it is "
            "inert on everything this migration creates")
    finally:
        with db.connect(db.SESSION) as conn, conn.cursor() as cur:
            cur.execute("delete from shared_accounts where local_part = %s", (local,))
            conn.commit()


# ---------------------------------------------------------------------------
# Does anything NOTICE when the auto-grant stops working?
#
# Before 0015, an IK account with no profile was the correct resting state and
# grant_access.py said so in those words. The auto-grant changed what the same
# observation means and the wording outlived its condition: it is now a FAULT.
#
# A teammate in that state sees "you can read nothing", assumes it is normal,
# and nobody finds out the trigger stopped firing. These tests are for the
# thing that notices.
# ---------------------------------------------------------------------------

from pipeline import grant_access as ga                              # noqa: E402


def test_an_ik_account_with_no_profile_is_reported_as_an_anomaly(signup):
    """THE NEGATIVE CONTROL. A check that has never fired is indistinguishable
    from one that cannot fire, so this breaks the thing and asserts it is seen.

    The profile is deleted AFTER the trigger created it, which is exactly the
    shape of both failure modes: a trigger that did not fire, and a revocation.
    """
    uid = signup("ik", f"np-test-noprofile@{IK}")
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from profiles where user_id = %s", (uid,))
        conn.commit()

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        applied, rows = ga._unprovisioned(cur)

    assert applied is not None, "0015 is not applied; the split cannot be made"
    mine = [r for r in rows if r["email"] == f"np-test-noprofile@{IK}"]
    assert mine, "an IK account with no profile was not reported at all"
    assert mine[0]["anomalous"], (
        "an IK account created after 0015 with no profile was not flagged as "
        "anomalous — the check cannot tell a broken auto-grant from a queue")
    assert mine[0]["age"].total_seconds() >= 0


def test_the_check_command_fails_when_an_ik_account_has_no_profile(signup, capsys):
    """Exit code is the interface — this is meant to run unattended."""
    assert ga.cmd_check(None) == 0, "expected a clean database to start from"

    uid = signup("ik", f"np-test-noprofile@{IK}")
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from profiles where user_id = %s", (uid,))
        conn.commit()

    rc = ga.cmd_check(None)
    out = capsys.readouterr().out
    assert rc == 1, "the check passed while an IK account had no profile"
    assert "np-test-noprofile" in out, "the account was counted but not named"
    assert "REVOKED" in out or "revoke" in out.lower(), (
        "the report must say that a revocation and a broken trigger look "
        "identical here — otherwise it implies a precision it does not have")


def test_a_non_ik_account_with_no_profile_is_not_an_anomaly(signup):
    """POSITIVE CONTROL. Without it, "flag everything" would pass the test above.

    A non-IK identity having no profile is the system working correctly, and
    reporting it as a fault would train people to ignore the output.
    """
    outsider = "np-test-outsider2@gmail.com"  # contact-ok: synthetic, and the
    # assertion is that it is NOT flagged. Bound once so the literal appears on
    # exactly one line — the marker covers its own line and the next code line,
    # which a repeated literal further down would escape.
    signup("outside", outsider)
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        _applied, rows = ga._unprovisioned(cur)
    mine = [r for r in rows if r["email"] == outsider]
    assert mine, "the non-IK account was not listed at all"
    assert not mine[0]["anomalous"], (
        "a non-IK account with no profile was flagged as a fault; it is the "
        "correct outcome and flagging it makes the report noise")


def test_the_cutoff_is_derived_from_the_migration_table_not_hardcoded():
    """Instance 8: a date typed into the script is a second source of truth
    about when the auto-grant started, and it rots in the passing direction."""
    src = (REPO / "pipeline" / "grant_access.py").read_text()
    assert "np_schema_migrations" in src

    # USES, not MENTIONS. The module docstring legitimately says when the scope
    # changed; what must not exist is a date CONSTANT the code compares against.
    import ast as _ast
    tree = _ast.parse(src)
    docstrings = {id(_ast.get_docstring(n, clean=False))
                  for n in _ast.walk(tree)
                  if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.ClassDef))}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            if id(node.value) in docstrings:
                continue
            assert not _re.match(r"^\s*20\d\d-\d\d-\d\d", node.value), (
                f"date literal {node.value!r} in code — derive the cutoff from "
                "np_schema_migrations instead")
