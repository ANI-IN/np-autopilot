#!/usr/bin/env python3
"""Serve the real app over the LOCAL Supabase stack, for measurement.

TEST HARNESS, NOT SHIPPED CODE — the same seam as eval/screenshot_views.py and
nothing more: `guard.identify` returns a fixed local identity instead of
verifying a Supabase token. The route table, handlers, queries, connection
reuse and RLS (request_connection sets the `authenticated` role) are the real
ones. Static files come from public/ as Vercel would serve them.

REFUSES a production DSN (db.production_reason), because it writes a profile
row for the harness identity.

    python3 eval/local_server.py [port]        # prints "READY <port>" when up
"""
from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api")]

from pipeline.lib import db                                           # noqa: E402

PUBLIC = REPO / "public"
LOCAL_SESSION = db.LOCAL_TEST_DSN
LOCAL_TRANSACTION = db.LOCAL_TEST_DSN_TRANSACTION


class _Identity:
    subject = "00000000-0000-0000-0000-0000000000b3"
    email = "b3-measure-harness@interviewkickstart.com"   # synthetic, IK domain
    role = "member"

    def __getattr__(self, _):
        return None


def _environment():
    os.environ.setdefault(db.SESSION, LOCAL_SESSION)
    os.environ.setdefault(db.TRANSACTION, LOCAL_TRANSACTION)
    for var in (db.SESSION, db.TRANSACTION):
        reason = db.production_reason(os.environ[var])
        if reason:
            sys.exit(f"REFUSED: {var} is production ({reason}); this harness "
                     "writes a profile row and stubs authentication.")
    # Placeholders so the page takes the signed-in path; nothing verifies them.
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1/local-harness")
    os.environ.setdefault("SUPABASE_ANON_KEY", "local-harness-not-a-key")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "local-harness.apps.local")


def _ensure_profile():
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("""insert into profiles(user_id,email,email_domain,role)
                       values (%s,%s,'interviewkickstart.com','member')
                       on conflict (user_id) do update set role='member'""",
                    (_Identity.subject, _Identity.email))


def application_factory():
    from lib import guard
    guard.identify = lambda headers: _Identity()
    import index as api_app                                    # api/index.py

    def application(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if path.startswith("/api/"):
            return api_app.app(environ, start_response)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = PUBLIC / rel
        if not f.is_file():
            start_response("404 NOT FOUND", [("content-type", "text/plain")])
            return [b"not found"]
        body = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        start_response("200 OK", [("content-type", ctype),
                                  ("content-length", str(len(body)))])
        return [body]
    return application


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def main() -> int:
    _environment()
    _ensure_profile()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    srv = make_server("127.0.0.1", port, application_factory(),
                      server_class=WSGIServer, handler_class=_Quiet)
    print(f"READY {srv.server_address[1]}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
