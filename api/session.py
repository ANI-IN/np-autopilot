"""POST /api/session — the ONLY place a Google identity becomes a session.

Three actions on one endpoint:

    {"action": "signin",  "id_token": "<google id token>"}
    {"action": "refresh", "refresh_token": "..."}
    {"action": "signout", "access_token": "..."}

`signin` is the only unauthenticated entry point in the application, and it
reaches no project data: it verifies a token, asks GoTrue for a session, and
reads the caller's OWN profile row. It cannot read the graph, because it holds
no privilege the caller does not already have.

WHAT A SUCCESSFUL SIGN-IN DOES NOT GRANT. A session is not access. `np_role()`
returns 'none' without a `profiles` row, every policy is default-deny, and so a
brand-new IK employee who signs in successfully sees zero nodes and is told so
in those words. Provisioning stays a deliberate act by an operator
(`pipeline/grant_access.py`), exactly as docs/AUTH.md already claimed:
*"layer 3 permits an account to exist; a profile is what gives it data."*
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

from lib import data, gotrue                                          # noqa: E402
from lib.auth import AuthError, Identity, verify_google_token         # noqa: E402
from lib.auth import verify_supabase_token                            # noqa: E402

MAX_BODY = 16 * 1024


def _profile(subject: str) -> dict | None:
    """The caller's own profile, read AS the caller.

    Read through `profiles_self_select`, which permits exactly one row: your
    own. A service-role read here would work and would also mean this endpoint
    could enumerate every user, which is a capability it has no reason to hold.
    """
    with data.request_connection(subject) as conn, conn.cursor() as cur:
        cur.execute("select role, email, is_shared_account from profiles "
                    "where user_id = %s", (subject,))
        row = cur.fetchone()
    if not row:
        return None
    return {"role": row[0], "email": row[1], "shared_account": row[2]}


def _session_payload(session: dict) -> dict:
    """What the browser gets back. Tokens included; nothing else about them."""
    user = session.get("user") or {}
    subject = user.get("id") or ""
    profile = _profile(subject) if subject else None
    return {
        "access_token": session.get("access_token"),
        "refresh_token": session.get("refresh_token"),
        "expires_in": session.get("expires_in"),
        "expires_at": session.get("expires_at"),
        "user": {"id": subject, "email": (user.get("email") or "").lower()},
        "profile": profile,
        # Said explicitly, because "signed in but sees nothing" is otherwise
        # indistinguishable from "the explorer is broken" — and this project
        # has a standing rule about states that look like absence.
        "note": None if profile else (
            "Signed in successfully, but this account has no profile, so it can "
            "read nothing. A session proves who you are; a profile is what "
            "grants access. Ask an administrator to run "
            "`pipeline/grant_access.py grant <email>`."),
    }


def _audit(event: str, email: str, ok: bool, reason: str, started: float,
           subject: str = "") -> None:
    """One line per attempt, success or refusal. NEVER a token, not even a prefix."""
    print(json.dumps({
        "audit": True, "endpoint": "session", "event": event,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "email": email or None, "subject": subject or None,
        "ok": ok, "reason": reason or None,
        "ms": round((time.time() - started) * 1000, 1),
    }, sort_keys=True))


def handle(action: str, payload: dict) -> tuple[int, dict]:
    """One of three actions. Returns (status, body); the HTTP shell is index.py.

    `signin` is the only unauthenticated entry point in the application and it
    reaches no project data — it verifies a token, asks GoTrue for a session,
    and reads the caller's OWN profile row through profiles_self_select.
    """
    started = time.time()
    try:
        if action == "signin":
            token = (payload.get("id_token") or "").strip()
            if not token:
                return 400, {"error": "bad_request", "reason": "no id_token"}
            # STEP 1, FIRST ON PURPOSE. Our own verification, `hd` included. An
            # @interviewkickstart.com address on a consumer Google account
            # completes the whole OAuth dance and is refused right here, before
            # GoTrue is contacted and before any user row could exist.
            try:
                identity: Identity = verify_google_token(token)
            except AuthError as exc:
                _audit("signin", "", False, str(exc), started)
                return 401, {"error": "unauthorised", "reason": str(exc)}
            # STEP 2. GoTrue verifies it again, independently, and creating the
            # user invokes auth_before_user_created (migration 0007).
            session = gotrue.exchange_google_id_token(token)
            out = _session_payload(session)
            _audit("signin", identity.email, True,
                   "no profile" if out["profile"] is None
                   else f"role={out['profile']['role']}",
                   started, subject=out["user"]["id"])
            return 200, out

        if action == "refresh":
            rt = (payload.get("refresh_token") or "").strip()
            if not rt:
                return 400, {"error": "bad_request", "reason": "no refresh_token"}
            out = _session_payload(gotrue.refresh(rt))
            _audit("refresh", out["user"]["email"], True, "", started,
                   subject=out["user"]["id"])
            return 200, out

        if action == "signout":
            at = (payload.get("access_token") or "").strip()
            if not at:
                return 400, {"error": "bad_request", "reason": "no access_token"}
            # Verified first so the audit line names who signed out. A bad token
            # still reaches GoTrue below — signing out is not a privileged act
            # and refusing it would leave a session alive to protect a log line.
            email, subject = "", ""
            try:
                ident = verify_supabase_token(at)
                email, subject = ident.email, ident.subject
            except AuthError:
                pass
            gotrue.sign_out(at)
            _audit("signout", email, True, "revoked globally", started,
                   subject=subject)
            return 200, {"signed_out": True,
                         "note": "Refresh tokens revoked server-side. The "
                                 "current access token stays valid until it "
                                 "expires."}

        return 400, {"error": "bad_request", "reason": f"unknown action {action!r}"}

    except gotrue.GoTrueError as exc:
        _audit(action, "", False, str(exc), started)
        # 4xx from GoTrue is the user's to see — the 0007 hook's message lives
        # here. 5xx is ours and says nothing specific.
        passthrough = 400 <= exc.status < 500
        return (exc.status if passthrough else 502), {
            "error": "auth_refused" if passthrough else "upstream",
            "reason": str(exc)}
