"""The Supabase Auth (GoTrue) side of the login flow.

WHY GOTRUE IS IN THE LOOP AT ALL, given that web/lib/auth.py already verifies a
Google token: `auth.uid()` casts `sub` to uuid, so the database can only resolve
a session whose subject is a uuid. A Google subject is a decimal string. GoTrue
is what mints a uuid-subject token — and, as it does, it invokes the
before-user-created hook from migration 0007, which has been installed and never
called since it was written.

ORDER: we verify the Google token OURSELVES FIRST, and only then hand it to
GoTrue. The reverse order would work too, because the 0007 hook enforces the
same `hd` rule — but it would make the guarantee depend on a dashboard setting
that no test in this repo can assert. Verifying first means the refusal holds
even if the hook is never wired up, and the hook then becomes what it was always
described as: defence in depth, not the thing keeping data safe.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
#: Publishable by design — it is the key a browser would hold. It grants
#: nothing on its own: every table is default-deny and `np_role()` returns
#: 'none' without a profile.
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

TIMEOUT = 15


class GoTrueError(Exception):
    """GoTrue refused. Carries the HTTP status so a route can pass it through."""

    def __init__(self, message: str, status: int = 502, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


def _require_config() -> None:
    missing = [n for n, v in (("SUPABASE_URL", SUPABASE_URL),
                              ("SUPABASE_ANON_KEY", ANON_KEY)) if not v]
    if missing:
        raise GoTrueError(
            f"{', '.join(missing)} not set — the login flow cannot reach "
            "Supabase Auth. These are deployment configuration, not secrets: "
            "the anon key is the key a browser holds and grants nothing "
            "without a profile.", status=500)


def _post(path: str, body: dict | None, bearer: str | None = None,
          opener=None) -> dict:
    """POST to GoTrue. `opener` is injected by tests; nothing else fakes it."""
    _require_config()
    url = f"{SUPABASE_URL}/auth/v1/{path.lstrip('/')}"
    raw = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=raw, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("apikey", ANON_KEY)
    req.add_header("authorization", f"Bearer {bearer or ANON_KEY}")
    try:
        if opener is not None:
            return opener(req)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read() or b"{}")
        except Exception:                                      # noqa: BLE001
            detail = {}
        # The 0007 hook returns 403 with its own message. Pass that through
        # rather than flattening it to "login failed": it is the only place a
        # user learns that their account is not a Workspace identity.
        raise GoTrueError(
            detail.get("msg") or detail.get("error_description")
            or detail.get("message") or f"GoTrue returned {exc.code}",
            status=exc.code, body=detail) from exc
    except urllib.error.URLError as exc:
        raise GoTrueError(f"cannot reach Supabase Auth: {exc.reason}",
                          status=502) from exc


def exchange_google_id_token(id_token: str, *, opener=None) -> dict:
    """Google ID token -> Supabase session. Fires the migration-0007 hook.

    GoTrue independently verifies the token with Google, so this is a second
    verification, not a substitute for ours.
    """
    return _post("token?grant_type=id_token",
                 {"provider": "google", "id_token": id_token}, opener=opener)


def refresh(refresh_token: str, *, opener=None) -> dict:
    """A new access token WITHOUT another trip through Google.

    This is the whole reason refresh tokens exist here: an access token lives
    about an hour, and re-running the OAuth dance every hour would train people
    to click through consent screens without reading them.
    """
    return _post("token?grant_type=refresh_token",
                 {"refresh_token": refresh_token}, opener=opener)


def sign_out(access_token: str, *, opener=None) -> None:
    """REVOKE, not forget.

    scope=global revokes every refresh token for the user server-side, so a
    stolen refresh token stops working. Clearing browser storage — which is what
    "log out" usually means in a single-page app — leaves the refresh token
    valid for anyone who copied it. The access token itself stays valid until it
    expires; that is a property of stateless JWTs and is stated in docs/AUTH.md
    rather than papered over.
    """
    _post("logout?scope=global", {}, bearer=access_token, opener=opener)
