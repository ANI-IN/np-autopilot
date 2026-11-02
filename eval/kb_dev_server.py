#!/usr/bin/env python3
"""Serve the KB workspace locally: public/ as static files, /api/* through the
REAL api/index.py WSGI app. TEST HARNESS, not shipped (eval/ is excluded from
every deploy by .vercelignore).

Unlike eval/local_server.py there is NO identity stub: requests carry real
HS256 tokens, verified by web/lib/auth.py against SUPABASE_JWT_SECRET, which
this harness sets to a TEST-ONLY value (tests/kb_support.TEST_JWT_SECRET). The
Playwright suite mints tokens with the same value. The database never sees the
token; RLS runs on the claims exactly as in production.

ONE REQUEST AT A TIME, through a lock: web/lib/data.py keeps ONE warm
connection per process (Vercel runs one request per instance). The server is
still threaded so that an idle socket a browser preconnects cannot block accept.

Refuses a production DSN, binds 127.0.0.1, answers only Host 127.0.0.1/localhost.

    python eval/kb_dev_server.py [port]      # prints "READY <port>" when up
"""
from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]

from pipeline.lib import db                                           # noqa: E402

PUBLIC = REPO / "public"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _production_headers() -> list[tuple[str, str]]:
    """vercel.json's headers for every path (CSP, HSTS, frame options …), so the
    browser tests run under the SAME policy production serves. A page that needs
    eval or an off-origin fetch fails here, not after a deploy."""
    import json
    cfg = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    out = []
    for rule in cfg.get("headers", []):
        if rule.get("source") == "/(.*)":
            out += [(h["key"], h["value"]) for h in rule["headers"] if h["key"] != "strict-transport-security"]
    return out


PROD_HEADERS = _production_headers()


def _configure() -> None:
    os.environ.setdefault(db.SESSION, db.LOCAL_TEST_DSN)
    os.environ.setdefault(db.TRANSACTION, db.LOCAL_TEST_DSN_TRANSACTION)
    for var in (db.SESSION, db.TRANSACTION):
        reason = db.production_reason(os.environ[var])
        if reason:
            sys.exit(f"REFUSED: {var} points at production ({reason}); this harness is local only")
    from kb_support import TEST_JWT_SECRET
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ.pop("SUPABASE_URL", None)       # no issuer check / JWKS for local tokens


def make_app(configure=None, extra=None):
    """`configure` replaces the test configuration (eval/kb_demo_server.py uses
    the local stack's own auth instead). `extra(environ, start_response, lock)`
    may answer a request first by returning a body, or decline with None."""
    (configure or _configure)()
    import index
    api = index.app
    lock = threading.Lock()

    def app(environ, start_response):
        host = (environ.get("HTTP_HOST") or "").split(":")[0]
        if host not in LOCAL_HOSTS:
            start_response("403 Forbidden", [("content-type", "text/plain")])
            return [b"local only"]
        path = environ.get("PATH_INFO", "/")
        if extra is not None:
            answered = extra(environ, start_response, lock)
            if answered is not None:
                return answered
        if path.startswith("/api/"):
            with lock:
                return list(api(environ, start_response))
        if path in ("/kb", "/kb/"):
            path = "/kb/index.html"
        if path == "/":
            path = "/index.html"
        target = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC not in target.parents or not target.is_file():
            start_response("404 Not Found", [("content-type", "text/plain")])
            return [b"not found"]
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        start_response("200 OK", [("content-type", ctype), ("cache-control", "no-store")] + PROD_HEADERS)
        return [target.read_bytes()]
    return app


class _Threaded(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def serve(app, port: int) -> int:
    server = make_server("127.0.0.1", port, app, server_class=_Threaded, handler_class=_Quiet)
    print(f"READY {port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    return serve(make_app(), int(sys.argv[1]) if len(sys.argv) > 1 else 8765)


if __name__ == "__main__":
    sys.exit(main())
