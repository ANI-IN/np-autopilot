"""Run 6, F4 — Settings -> Members: add a person by IK e-mail with a role
BEFORE their first sign-in, the role applied when they sign in (0035), change
it, withdraw it, remove a member; the last admin is never removed or demoted;
every change is in Activity and no address ever reaches the append-only log.

The "first sign-in" is what GoTrue does: a row in auth.users, whose sign-up
trigger (0015) creates the profile, whose trigger (0035) applies the role.
Synthetic `kbtest-invite-*@interviewkickstart.com` addresses only.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg
import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb


def _addr(tag: str) -> str:
    return f"kbtest-invite-{tag}-{uuid.uuid4().hex[:8]}@interviewkickstart.com"


def _clean():
    with owner() as c:
        ids = [r[0] for r in c.execute("select id from auth.users where email like 'kbtest-invite-%%'").fetchall()]
        c.execute("delete from kb.memberships where user_id = any(%s)", (ids,))
        c.execute("delete from profiles where email like 'kbtest-invite-%%'")
        c.execute("delete from auth.users where id = any(%s)", (ids,))
        c.execute("delete from kb.member_invites")


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    _clean()
    yield
    reset()
    _clean()
    ensure_users()                     # puts the viewer back to "no membership"


@pytest.fixture
def admin():
    return Client(USERS["admin"])


def _sign_in_for_the_first_time(email: str) -> str:
    uid = str(uuid.uuid4())
    with owner() as c:
        c.execute("insert into auth.users (id, email, created_at) values (%s, %s, now())", (uid, email))
        # 0015 creates the profile; this line only matters where that trigger is absent.
        c.execute("""insert into profiles (user_id, email, email_domain, role)
                     values (%s, %s, 'interviewkickstart.com', 'member') on conflict (user_id) do nothing""", (uid, email))
    return uid


@contextmanager
def _only_admin(user_id: str):
    with owner() as c:
        others = [r[0] for r in c.execute("select user_id from kb.memberships where role = 'admin' "
                                          "and archived_at is null and user_id <> %s", (user_id,)).fetchall()]
        c.execute("update kb.memberships set archived_at = now(), status = 'archived' where user_id = any(%s)", (others,))
    try:
        yield
    finally:
        with owner() as c:
            c.execute("update kb.memberships set archived_at = null, status = 'active' where user_id = any(%s)", (others,))


def test_a_person_added_before_their_first_sign_in_gets_the_role_when_they_sign_in(admin):
    email = _addr("before")
    s, inv = admin.post("/api/kb/members/invite", {"email": email.upper(), "role": "editor"})
    assert s == 201 and inv["status"] == "pending" and inv["email"] == email and inv["role"] == "editor", inv
    s, lst = admin.get("/api/kb/members")
    assert [i["email"] for i in lst["invites"]] == [email]
    assert email not in {m["email"] for m in lst["items"]}

    uid = _sign_in_for_the_first_time(email)
    with owner() as c:
        assert c.execute("select role from kb.memberships where user_id = %s and archived_at is null",
                         (uid,)).fetchone()[0] == "editor"
        assert c.execute("select status, user_id::text from kb.member_invites where id = %s",
                         (inv["id"],)).fetchone() == ("applied", uid)
    assert Client(uid).get("/api/kb/me")[1]["role"] == "editor"
    s, lst = admin.get("/api/kb/members")
    assert email in {m["email"] for m in lst["items"]} and lst["invites"] == []


def test_a_person_who_already_signed_in_gets_the_role_at_once(admin):
    email = "kbtest-viewer@interviewkickstart.com"          # ensure_users' viewer: a profile, no membership
    s, inv = admin.post("/api/kb/members/invite", {"email": email, "role": "contributor"})
    assert s == 201 and inv["status"] == "applied" and str(inv["user_id"]) == USERS["viewer"], inv
    assert Client(USERS["viewer"]).get("/api/kb/me")[1]["role"] == "contributor"


@pytest.mark.parametrize("bad", ["kbtest-x@example.com", "kbtest-x@interviewkickstart.com.example.com",
                                 "kbtest-x@notinterviewkickstart.com", "kbtest x@interviewkickstart.com",
                                 "@interviewkickstart.com", "kbtest-x", ""])
def test_only_an_ik_address_can_be_added_checked_by_the_server_and_the_database(admin, bad):
    s, out = admin.post("/api/kb/members/invite", {"email": bad, "role": "viewer"})
    assert s == 422 and out["field"] == "email", out
    if "@" in bad and " " not in bad and not bad.startswith("@"):
        with as_user(USERS["admin"]) as c:               # straight past the service: the CHECK refuses it
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("insert into kb.member_invites (email, role) values (%s, 'viewer')", (bad,))


def test_a_role_must_be_one_of_the_four(admin):
    s, out = admin.post("/api/kb/members/invite", {"email": _addr("role"), "role": "owner"})
    assert s == 422 and out["field"] == "role"


def test_change_and_withdraw_a_pending_invitation(admin):
    email = _addr("change")
    _, inv = admin.post("/api/kb/members/invite", {"email": email, "role": "viewer"})
    s, out = admin.post(f"/api/kb/members/invites/{inv['id']}", {"role": "admin"})
    assert s == 200 and out["role"] == "admin"
    # adding the same address again updates the one pending invitation
    s, again = admin.post("/api/kb/members/invite", {"email": email, "role": "contributor"})
    assert s == 201 and again["id"] == inv["id"] and again["role"] == "contributor"
    assert admin.post(f"/api/kb/members/invites/{inv['id']}/revoke")[0] == 200
    assert admin.post(f"/api/kb/members/invites/{inv['id']}/revoke")[0] == 404
    uid = _sign_in_for_the_first_time(email)
    assert Client(uid).get("/api/kb/me")[1]["role"] == "viewer", "a withdrawn invitation must grant nothing"


def test_only_admins_manage_members_and_never_the_ai_assistant(admin):
    for role in ("viewer", "contributor", "editor"):
        c = Client(USERS[role])
        assert c.post("/api/kb/members/invite", {"email": _addr("nope"), "role": "admin"})[0] == 403
        assert c.get("/api/kb/members")[0] == 403
    with as_user(USERS["admin"], "ai") as conn:          # the database refuses the AI too (refuse_ai)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("insert into kb.member_invites (email, role) values (%s, 'admin')", (_addr("ai"),))


def test_every_change_is_in_activity_and_no_address_enters_the_audit_log(admin):
    email = _addr("audit")
    _, inv = admin.post("/api/kb/members/invite", {"email": email, "role": "editor"})
    admin.post(f"/api/kb/members/invites/{inv['id']}", {"role": "contributor"})
    uid = _sign_in_for_the_first_time(email)
    admin.post(f"/api/kb/members/{uid}", {"role": "editor"})
    assert admin.post(f"/api/kb/members/{uid}/remove")[0] == 200
    with owner() as c:
        rows = c.execute("""select table_name, action, coalesce(before::text, '') || coalesce(after::text, '')
                            from kb.audit_log where table_name in ('member_invites', 'memberships')
                              and (row_id = %s or row_id = %s) order by id""", (inv["id"], uid)).fetchall()
        assert [r[:2] for r in rows if r[0] == "member_invites"][:2] == [("member_invites", "insert"), ("member_invites", "update")]
        assert any(r[0] == "memberships" and r[1] == "insert" for r in rows), "the applied role is audited"
        assert all("@" not in r[2] for r in rows), "an e-mail address reached the append-only audit log"
        changes = c.execute("select kind from kb.changes where row_id = %s", (inv["id"],)).fetchall()
        assert changes, "invitations appear in the change feed"
    s, act = admin.get("/api/kb/activity", "table=member_invites,memberships")
    assert s == 200
    labels = {(a["table_name"], a["label"]) for a in act["items"]}
    assert ("member_invites", "Role: editor (pending)") in labels
    assert any(t == "memberships" and lab and lab.startswith("Role: ") for t, lab in labels)


def test_the_last_admin_can_never_be_removed_or_demoted(admin):
    me = USERS["admin"]
    with _only_admin(me):
        s, out = admin.post(f"/api/kb/members/{me}", {"role": "editor"})
        assert s == 403 and "last admin" in out["message"], out
        # not by an invitation to their own address either
        s, out = admin.post("/api/kb/members/invite", {"email": "kbtest-admin@interviewkickstart.com", "role": "viewer"})
        assert s == 403 and "last admin" in out["message"], out
        with as_user(me) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("update kb.memberships set archived_at = now() where user_id = %s", (me,))
        assert Client(me).get("/api/kb/me")[1]["role"] == "admin"


def test_the_tab_gets_plain_descriptions_of_every_role(admin):
    s, out = admin.get("/api/kb/members")
    assert s == 200 and [r["role"] for r in out["roles"]] == ["viewer", "contributor", "editor", "admin"]
    assert all(len(r["can"]) > 40 for r in out["roles"])
    assert "last admin" in out["roles"][-1]["can"]


def test_an_invitation_written_by_an_operator_applies_on_sign_in_too():
    """pipeline scripts and migrations write as the table owner: the sign-in
    trigger applies their invitations the same way, and the sign-up succeeds."""
    email = _addr("operator")
    with owner() as c:
        c.execute("insert into kb.member_invites (email, role) values (%s, 'editor')", (email,))
    uid = _sign_in_for_the_first_time(email)
    with owner() as c:
        assert c.execute("select count(*) from profiles where user_id = %s", (uid,)).fetchone()[0] == 1
        assert c.execute("select role from kb.memberships where user_id = %s", (uid,)).fetchone()[0] == "editor"
