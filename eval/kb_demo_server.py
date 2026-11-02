#!/usr/bin/env python3
"""Serve the KB workspace for a LOCAL DEMO, signed in through the local stack's
own Supabase Auth. NOT SHIPPED: eval/ is excluded from every deploy
(.vercelignore), and nothing here changes how production signs anyone in.

What differs from eval/kb_dev_server.py (the test harness):

  - Tokens are real local-GoTrue sessions, verified by web/lib/auth.py exactly
    as in production (signing keys fetched from the local stack, issuer
    checked), instead of tokens minted with a test-only secret.
  - /local-login is a sign-in page for the demo users that eval/kb_demo_seed.py
    creates (email + password, local GoTrue's password grant). It exists only
    in this process. The production app has no such route and no password login.
  - The KB page's "Sign in" button points at /local-login, and a small ribbon
    says the data is fictional. Done by rewriting the served HTML in this
    process; public/kb/index.html is unchanged.

Refuses a non-loopback database or auth URL; binds 127.0.0.1.

    python eval/kb_demo_server.py [port]      # default 8765; prints "READY <port>"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kb_dev_server as base                                          # noqa: E402
import kb_local_stack as stack                                        # noqa: E402

DEMO = HERE / "demo"
STATIC = {"/local-login": ("local-login.html", "text/html; charset=utf-8"),
          "/local-login.js": ("local-login.js", "text/javascript; charset=utf-8"),
          "/local-demo.css": ("local-demo.css", "text/css; charset=utf-8")}
MAX_BODY = 16 * 1024


def _configure() -> None:
    st = stack.status()
    stack.configure_env(st)
    # Live updates over Supabase Realtime (D2): the origin comes from the local
    # stack's own status, never a literal. The page's connect-src gets exactly
    # that origin (http + ws), as docs/DEPLOYMENT.md describes for production.
    origin = st["API_URL"].rstrip("/")
    os.environ["KB_REALTIME_ORIGIN"] = origin
    ws = "ws" + origin[len("http"):]
    base.PROD_HEADERS[:] = [(k, v.replace("connect-src 'self'", f"connect-src 'self' {origin} {ws}"))
                            if k.lower() == "content-security-policy" else (k, v) for k, v in base.PROD_HEADERS]
    from pipeline.lib import db
    for var in (db.SESSION, db.TRANSACTION):
        reason = db.production_reason(os.environ[var])
        if reason:
            sys.exit(f"REFUSED: {var} points at production ({reason}); the demo is local only")


def _json(start_response, code: str, body: dict):
    raw = json.dumps(body, default=str).encode()
    start_response(code, [("content-type", "application/json"), ("cache-control", "no-store")] + base.PROD_HEADERS)
    return [raw]


def _sign_in(environ, start_response, lock):
    from lib import gotrue
    import session
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
        payload = json.loads(environ["wsgi.input"].read(min(size, MAX_BODY)) or b"{}")
        email = str(payload.get("email") or "").strip().lower()
        password = str(payload.get("password") or "")
    except (ValueError, TypeError):
        return _json(start_response, "400 Bad Request", {"reason": "send JSON with email and password"})
    if not email or not password:
        return _json(start_response, "400 Bad Request", {"reason": "email and password are required"})
    try:
        with lock:
            grant = gotrue._post("token?grant_type=password", {"email": email, "password": password})
            out = session._session_payload(grant)
    except gotrue.GoTrueError as exc:
        return _json(start_response, "401 Unauthorized",
                     {"reason": "Wrong email or password." if exc.status in (400, 401) else str(exc)})
    return _json(start_response, "200 OK", out)


def extra(environ, start_response, lock):
    path, method = environ.get("PATH_INFO", "/"), environ.get("REQUEST_METHOD", "GET")
    if path == "/local-login/session" and method == "POST":
        return _sign_in(environ, start_response, lock)
    if path in STATIC and method == "GET":
        name, ctype = STATIC[path]
        start_response("200 OK", [("content-type", ctype), ("cache-control", "no-store")] + base.PROD_HEADERS)
        return [(DEMO / name).read_bytes()]
    if path in ("/kb", "/kb/", "/kb/index.html") and method == "GET":
        html = (base.PUBLIC / "kb" / "index.html").read_text(encoding="utf-8")
        html = html.replace('<a class="btn primary" href="/">Sign in</a>',
                            '<a class="btn primary" href="/local-login">Sign in</a>', 1)
        html = html.replace('<link rel="stylesheet" href="/kb/kb.css">',
                            '<link rel="stylesheet" href="/kb/kb.css">\n<link rel="stylesheet" href="/local-demo.css">', 1)
        html = html.replace("<body>", '<body>\n<div class="demo-ribbon">Local demo · fictional data</div>', 1)
        start_response("200 OK", [("content-type", "text/html; charset=utf-8"), ("cache-control", "no-store")] + base.PROD_HEADERS)
        return [html.encode()]
    return None


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    return base.serve(base.make_app(configure=_configure, extra=extra), port)


if __name__ == "__main__":
    sys.exit(main())
