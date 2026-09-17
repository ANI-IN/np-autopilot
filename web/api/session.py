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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


class handler(BaseHTTPRequestHandler):                         # noqa: N801
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        # A session response carries refresh tokens. It must never sit in a
        # shared cache, and never in the back/forward cache either.
        self.send_header("cache-control", "no-store, private")
        self.send_header("pragma", "no-cache")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("referrer-policy", "no-referrer")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:                                 # noqa: N802
        started = time.time()
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": "bad_request", "reason": "missing or oversized body"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:                                      # noqa: BLE001
            self._send(400, {"error": "bad_request", "reason": "body is not JSON"})
            return

        action = (body.get("action") or "signin").strip().lower()
        try:
            if action == "signin":
                self._signin(body, started)
            elif action == "refresh":
                self._refresh(body, started)
            elif action == "signout":
                self._signout(body, started)
            else:
                self._send(400, {"error": "bad_request",
                                 "reason": f"unknown action {action!r}"})
        except gotrue.GoTrueError as exc:
            _audit(action, "", False, str(exc), started)
            # 4xx from GoTrue is the user's problem to see (the 0007 hook's
            # message lives here); 5xx is ours and says nothing specific.
            passthrough = 400 <= exc.status < 500
            self._send(exc.status if passthrough else 502,
                       {"error": "auth_refused" if passthrough else "upstream",
                        "reason": str(exc)})
        except Exception:                                      # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            _audit(action, "", False, "internal", started)
            self._send(500, {"error": "internal"})

    # -- actions ----------------------------------------------------------
    def _signin(self, body: dict, started: float) -> None:
        token = (body.get("id_token") or "").strip()
        if not token:
            self._send(400, {"error": "bad_request", "reason": "no id_token"})
            return

        # STEP 1, AND IT IS FIRST ON PURPOSE. Our own verification, with the
        # `hd` check. An @interviewkickstart.com address on a consumer Google
        # account completes the entire OAuth dance and is refused right here,
        # before GoTrue is contacted and before any user row could exist.
        try:
            identity: Identity = verify_google_token(token)
        except AuthError as exc:
            _audit("signin", "", False, str(exc), started)
            self._send(401, {"error": "unauthorised", "reason": str(exc)})
            return

        # STEP 2. GoTrue verifies it again, independently, and creating the user
        # invokes auth_before_user_created (migration 0007).
        session = gotrue.exchange_google_id_token(token)
        payload = _session_payload(session)
        _audit("signin", identity.email, True,
               "no profile" if payload["profile"] is None else
               f"role={payload['profile']['role']}",
               started, subject=payload["user"]["id"])
        self._send(200, payload)

    def _refresh(self, body: dict, started: float) -> None:
        rt = (body.get("refresh_token") or "").strip()
        if not rt:
            self._send(400, {"error": "bad_request", "reason": "no refresh_token"})
            return
        session = gotrue.refresh(rt)
        payload = _session_payload(session)
        _audit("refresh", payload["user"]["email"], True, "",
               started, subject=payload["user"]["id"])
        self._send(200, payload)

    def _signout(self, body: dict, started: float) -> None:
        at = (body.get("access_token") or "").strip()
        if not at:
            self._send(400, {"error": "bad_request", "reason": "no access_token"})
            return
        # Verified first so the audit line names who signed out. A bad token
        # still reaches GoTrue below — signing out is not a privileged act and
        # refusing it would leave a session alive to protect a log line.
        email, subject = "", ""
        try:
            ident = verify_supabase_token(at)
            email, subject = ident.email, ident.subject
        except AuthError:
            pass
        gotrue.sign_out(at)
        _audit("signout", email, True, "revoked globally", started, subject=subject)
        self._send(200, {"signed_out": True,
                         "note": "Refresh tokens revoked server-side. The current "
                                 "access token stays valid until it expires."})

    def do_GET(self) -> None:                                  # noqa: N802
        self._send(405, {"error": "method_not_allowed",
                         "reason": "POST an action to /api/session"})

    def log_message(self, *args):                              # noqa: D102
        pass
