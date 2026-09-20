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
            cur.execute("insert into auth.users (id, email) values (%s, %s)",
                        (uid, email))
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
