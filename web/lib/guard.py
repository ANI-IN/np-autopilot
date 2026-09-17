"""Layer 4 — route protection, and the shared request handler.

Last of the four layers, and deliberately so. DECISIONS §D: middleware is
defence in depth only, because its documented failure mode is a matcher that
silently stops matching. Doc 03 records the same shape in Claude Code plugins —
a path that escapes the plugin root fails silently and the plugin loads without
that component, so the symptom looks like missing data rather than a broken
configuration.

So this layer is built to be *unnecessary*. If a route forgets it, the request
reaches web/lib/data.py with no identity, `auth.uid()` is null, `np_role()`
returns 'none', and RLS returns zero rows. The route answers "nothing found"
rather than leaking. `test_a_route_that_forgets_the_guard_returns_nothing`
asserts exactly that.

What this layer adds is a clear 401 instead of a confusing empty result, and one
place where the audit record is written.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import data                                                   # noqa: E402
from lib.auth import AuthError, verify_google_token                    # noqa: E402


def bearer(headers) -> str | None:
    raw = headers.get("authorization") or headers.get("Authorization") or ""
    parts = raw.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def identify(headers):
    """Verified identity, or raise AuthError. Never trusts a header field."""
    token = bearer(headers)
    if not token:
        raise AuthError("no bearer token")
    return verify_google_token(token)


def audit(identity, endpoint: str, params: dict, rows: int,
          started: float) -> None:
    """One line per request. §E.4 wants the QUERY, not just that access happened.

    Written to stdout, which Vercel captures. It names an ACCOUNT, and
    docs/AUTH.md says plainly that an account is not necessarily a person —
    shared team mailboxes exist and this cannot tell them apart beyond a
    configured list.
    """
    print(json.dumps({
        "audit": True,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "subject": getattr(identity, "subject", None),
        "email": getattr(identity, "email", None),
        "shared_account": getattr(identity, "is_shared_account", False),
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "ms": round((time.time() - started) * 1000, 1),
    }, sort_keys=True))


def serve(endpoint: str, fn):
    """Build a Vercel Python handler around one read function.

    fn(conn, identity, params) -> (payload, row_count)
    """
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict):
            raw = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            # No caching of authorised data by a shared proxy.
            self.send_header("cache-control", "private, no-store")
            self.send_header("x-content-type-options", "nosniff")
            self.send_header("referrer-policy", "no-referrer")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):                                  # noqa: N802
            started = time.time()
            params = {k: (v[0] if len(v) == 1 else v)
                      for k, v in parse_qs(urlparse(self.path).query).items()}
            try:
                identity = identify(self.headers)
            except AuthError as exc:
                self._send(401, {"error": "unauthorised", "reason": str(exc)})
                return
            try:
                with data.request_connection(identity.subject) as conn:
                    payload, rows = fn(conn, identity, params)
            except data.DepthExceeded as exc:
                self._send(400, {"error": "depth_exceeded", "reason": str(exc)})
                return
            except Exception:                              # noqa: BLE001
                # Never return the exception text: it can carry row values.
                print(traceback.format_exc(), file=sys.stderr)
                self._send(500, {"error": "internal"})
                return
            audit(identity, endpoint, params, rows, started)
            self._send(200, payload)

        def log_message(self, *args):                      # noqa: D102
            pass                                           # audit() is the log

    return Handler
