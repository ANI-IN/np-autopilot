"""0016 — the before-user-created hook must find `hd` where GoTrue put it.

THE BUG THIS LOCKS DOWN, AND WHY IT IS THE SECOND TIME.

`pipeline/grant_access.py` carries a comment established by reading a real
GoTrue row:

    identity_data -> 'custom_claims' ->> 'hd'   <-- where it IS
    identity_data ->> 'hd'                      <-- where the script looked

GoTrue nests NON-STANDARD OIDC claims under `custom_claims`, and `hd` is
non-standard. That script's first version read only the unnested path, found
NULL for everyone, and refused every legitimate user while reporting "this
account is not a Workspace identity". `docs/A7B.md` lists it as instance 6.

Migration 0007's hook made the same mistake in the same repository. It read
`{claims,hd}` and `{user_metadata,hd}` — both unnested — and nothing caught it
because the hook was a database function that GoTrue had never been configured
to call. It was registered on 2026-09-21 and Google sign-in stopped working
within the hour.

So these tests do the thing that was missing: run the hook against every
container shape GoTrue plausibly sends, rather than the one its author assumed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

IK = "interviewkickstart.com"


def _hook(event: dict):
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select auth_before_user_created(%s::jsonb)",
                    (json.dumps(event),))
        out = cur.fetchone()[0]
        conn.commit()
    return (out or {}).get("error")


#: Every container GoTrue might use, with `hd` nested under custom_claims where
#: this project has already proved it lands. Each one is a REAL Workspace
#: identity and must be allowed: refusing any of them locks a colleague out.
ALLOW_SHAPES = {
    "claims.hd (0007's assumption)":
        {"claims": {"email": f"a@{IK}", "hd": IK}},
    "claims.custom_claims.hd":
        {"claims": {"email": f"a@{IK}", "custom_claims": {"hd": IK}}},
    "user.raw_user_meta_data.custom_claims.hd":
        {"user": {"raw_user_meta_data": {"email": f"a@{IK}",
                                         "custom_claims": {"hd": IK}}}},
    "user.user_metadata.custom_claims.hd":
        {"user": {"user_metadata": {"email": f"a@{IK}",
                                    "custom_claims": {"hd": IK}}}},
    "user.identity_data.custom_claims.hd":
        {"user": {"identity_data": {"email": f"a@{IK}",
                                    "custom_claims": {"hd": IK}}}},
    "metadata.custom_claims.hd":
        {"metadata": {"custom_claims": {"hd": IK}}, "user": {"email": f"a@{IK}"}},
    "hd present, email nowhere known":
        {"claims": {"custom_claims": {"hd": IK}}},
}


@pytest.mark.parametrize("label", sorted(ALLOW_SHAPES))
def test_a_real_workspace_identity_is_allowed_whatever_shape_it_arrives_in(label):
    """THE REGRESSION TEST. Any of these refusing is a locked-out colleague.

    The last case matters on its own: `hd` is the check and `email` is
    corroboration, so a payload carrying hd in a known place but email in an
    unknown one must NOT be refused. 0007 refused it — `email = ''` failed its
    `not like` test — which is the same class of bug one field over.
    """
    err = _hook(ALLOW_SHAPES[label])
    assert err is None, (
        f"a valid Workspace identity shaped as {label!r} was REFUSED: "
        f"{(err or {}).get('message')!r}")


REFUSE_SHAPES = {
    "no hd anywhere": {"user": {"email": f"a@{IK}"}},
    "wrong hd, nested": {"claims": {"custom_claims": {"hd": "evil.com"},
                                    "email": "a@evil.com"}},
    "hd ok but email disagrees": {"claims": {"custom_claims": {"hd": IK},
                                             # contact-ok: synthetic. A consumer-provider domain is the POINT —
                                             # migration 0007's rule is that a Workspace `hd` claim cannot be
                                             # trusted when the address is outside that domain, and the
                                             # assertion is that this shape is REFUSED.
                                             "email": "a@gmail.com"}},
    "empty payload": {},
}


@pytest.mark.parametrize("label", sorted(REFUSE_SHAPES))
def test_everything_else_is_still_refused(label):
    """POSITIVE CONTROL. Widening where the hook LOOKS must not widen what it
    ACCEPTS — otherwise the fix for a lockout is a hole."""
    err = _hook(REFUSE_SHAPES[label])
    assert err is not None, f"{label!r} was allowed through the hook"
    assert err.get("http_code") == 403


def test_an_ik_email_without_hd_is_refused():
    """The case `endsWith()` accepts and this project does not.

    An address in the domain is not membership of the Workspace. This is the
    whole reason the hook exists, so it gets its own test rather than living
    inside the parametrised list.
    """
    err = _hook({"user": {"email": f"someone@{IK}"},
                 "claims": {"email": f"someone@{IK}"}})
    assert err is not None, (
        "an IK email address with no hd claim was accepted — that is exactly "
        "the identity docs/architecture/auth.md says we refuse")
    assert "hosted-domain" in err["message"]


def test_a_refusal_records_the_payload_shape_and_never_a_value():
    """A refusal that cannot say why it refused is how this bug survived.

    The diagnostic records key NAMES so a failed sign-in is debuggable, and
    must never record a value — a control that copies the identity it refused
    would leak contact data at the moment it was being careful.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from auth_hook_refusals")
        conn.commit()

    secret = f"nobody-real@{IK}"
    _hook({"user": {"email": secret, "sub": "xyz"}})

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select reason, top_keys, nested_keys from auth_hook_refusals")
        rows = cur.fetchall()
        cur.execute("delete from auth_hook_refusals")
        conn.commit()

    assert rows, "a refusal recorded nothing — the next failure is a mystery"
    reason, top, nested = rows[0]
    assert top == ["user"], f"top-level keys not captured: {top}"
    assert nested is not None and "email" in nested
    blob = f"{reason}{top}{nested}"
    assert secret not in blob, (
        "the diagnostic recorded the address it refused; key names only")
    assert "nobody-real" not in blob


def test_the_hook_is_callable_by_the_role_gotrue_uses():
    """If supabase_auth_admin cannot execute it, the hook RAISES instead of
    refusing and GoTrue turns that into a failed sign-in with no explanation —
    indistinguishable from the bug this migration fixes."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""select
            has_function_privilege('supabase_auth_admin',
                'public.auth_before_user_created(jsonb)', 'EXECUTE'),
            has_function_privilege('supabase_auth_admin',
                'public._hook_pick(jsonb, text)', 'EXECUTE'),
            has_table_privilege('supabase_auth_admin',
                'public.auth_hook_refusals', 'INSERT'),
            has_function_privilege('anon',
                'public.auth_before_user_created(jsonb)', 'EXECUTE')""")
        can_exec, can_pick, can_insert, anon_exec = cur.fetchone()
    assert can_exec, "supabase_auth_admin cannot execute the hook"
    assert can_pick, "supabase_auth_admin cannot execute the claim reader"
    assert can_insert, "supabase_auth_admin cannot write the diagnostic row"
    assert not anon_exec, "anon can execute the hook — it should not"


# ---------------------------------------------------------------------------
# 0020 — run it as GoTrue does, and as nobody else can
# ---------------------------------------------------------------------------
#
# Everything above calls the hook as the table owner, and the privilege test
# only ASKS whether supabase_auth_admin may execute it. With RLS now on the
# refusals table, the question that matters is whether a sign-in still works
# end to end as the role GoTrue actually connects with. The local Supabase
# stack lets that role log in (its fixed local password); production's is not
# known here, so these run against the local stack only.

GOTRUE_LOCAL = "postgresql://supabase_auth_admin:postgres@127.0.0.1:54322/postgres"
_ON_LOCAL_STACK = db.available() and db.params(db.SESSION)["port"] == 54322
needs_local_stack = pytest.mark.skipif(
    not _ON_LOCAL_STACK,
    reason="needs the local Supabase stack's supabase_auth_admin login")


def _as_gotrue(event: dict):
    import psycopg
    with psycopg.connect(GOTRUE_LOCAL, connect_timeout=10) as conn, \
            conn.cursor() as cur:
        cur.execute("select current_user")
        assert cur.fetchone()[0] == "supabase_auth_admin"
        # Schema-qualified, as GoTrue calls it (pg-functions://postgres/public/
        # auth_before_user_created): this role's search_path is `auth`.
        cur.execute("select public.auth_before_user_created(%s::jsonb)",
                    (json.dumps(event),))
        out = cur.fetchone()[0]
        conn.commit()
    return (out or {}).get("error")


@needs_local_stack
def test_gotrue_allows_a_workspace_identity_under_rls():
    assert _as_gotrue(ALLOW_SHAPES["claims.custom_claims.hd"]) is None


@needs_local_stack
def test_gotrue_refuses_and_the_refusal_is_recorded_under_rls():
    """The diagnostic insert is the part RLS could have broken silently: the
    hook would still refuse, and nobody would learn why."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from auth_hook_refusals")
        conn.commit()
    err = _as_gotrue(REFUSE_SHAPES["no hd anywhere"])
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from auth_hook_refusals")
        recorded = cur.fetchone()[0]
        cur.execute("delete from auth_hook_refusals")
        conn.commit()
    assert err is not None and err.get("http_code") == 403
    assert recorded == 1, "the refusal was not recorded when GoTrue ran the hook"


@pytest.mark.parametrize("role", ["anon", "authenticated", "service_role"])
def test_no_other_role_can_run_the_hook(role):
    """0007 revoked anon and authenticated and forgot PUBLIC. Asserted by
    CALLING it, not only by reading the ACL."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute(f"set local role {role}")
        with pytest.raises(Exception, match="permission denied for function"):
            cur.execute("select auth_before_user_created('{}'::jsonb)")
        conn.rollback()


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_the_refusals_table_is_invisible_to_client_roles(role):
    """RLS plus no grant: a row that exists cannot be read by a client role."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("insert into auth_hook_refusals (reason) values ('rls probe')")
        cur.execute(f"set local role {role}")
        try:
            cur.execute("select count(*) from auth_hook_refusals")
            seen = cur.fetchone()[0]
        except Exception as exc:
            assert "permission denied" in str(exc)
            seen = 0
        conn.rollback()
    assert seen == 0, f"{role} can read auth_hook_refusals"
