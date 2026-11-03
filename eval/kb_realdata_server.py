#!/usr/bin/env python3
"""Serve the KB workspace over the LOCAL copy of production data (database
`kb_realdata`, built by eval/kb_realdata_db.py) on its own port, next to the
fictional demo (eval/kb_demo_server.py, 8765), which it never touches.
NOT SHIPPED: eval/ is excluded from every deploy (.vercelignore).

  - Database: kb_realdata in the local Supabase Postgres (127.0.0.1:54322),
    direct (the local pooler serves only the demo's database). Refuses any
    non-loopback database.
  - Sign-in: /local-login, the demo's page and pattern, for the ONE local admin
    (eval/kb_realdata_db.py admin). The password is checked against
    kb_realdata's own auth.users (bcrypt, pgcrypto); the server then mints a
    session token with a secret generated at start-up and held only in this
    process, and the app verifies it through the production HS256 path. Real
    users' accounts are not needed and none exist.
  - Binds 127.0.0.1 and answers only Host: localhost / 127.0.0.1.

    python eval/kb_realdata_server.py [port]      # default 8766; prints "READY <port>"
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kb_dev_server as base                                          # noqa: E402

DEMO = HERE / "demo"
# KB_LOCAL_DB (run 6): a run-6 workstream serves its own clone (kb_<stream>) of
# kb_realdata on its own port. Only a local database named kb_* is accepted.
_DB_NAME = os.environ.get("KB_LOCAL_DB", "kb_realdata")
if not re.fullmatch(r"kb_[a-z0-9_]{1,40}", _DB_NAME):
    sys.exit("REFUSED: KB_LOCAL_DB must name a local kb_* database")
DB_URL = f"postgresql://postgres:postgres@127.0.0.1:54322/{_DB_NAME}"
TOKEN_TTL = 8 * 3600
MAX_BODY = 16 * 1024
SECRET = secrets.token_urlsafe(48)          # this process only; restarting signs everyone out
RIBBON = "Local copy · REAL internal data · not connected to production"


def _configure() -> None:
    from pipeline.lib import db
    os.environ[db.SESSION] = DB_URL
    os.environ[db.TRANSACTION] = DB_URL
    for var in (db.SESSION, db.TRANSACTION):
        reason = db.production_reason(os.environ[var])
        if reason or "127.0.0.1" not in os.environ[var]:
            sys.exit(f"REFUSED: {var} is not the local kb_realdata database; this server is local only")
    os.environ["SUPABASE_JWT_SECRET"] = SECRET
    os.environ.pop("SUPABASE_URL", None)     # local HS256 tokens: no issuer / JWKS
    os.environ.pop("KB_REALTIME_ORIGIN", None)


def _json(start_response, code: str, body: dict):
    raw = json.dumps(body, default=str).encode()
    start_response(code, [("content-type", "application/json"), ("cache-control", "no-store")] + base.PROD_HEADERS)
    return [raw]


def _sign_in(environ, start_response, lock):
    import jwt
    import psycopg
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
        payload = json.loads(environ["wsgi.input"].read(min(size, MAX_BODY)) or b"{}")
        email = str(payload.get("email") or "").strip().lower()
        password = str(payload.get("password") or "")
    except (ValueError, TypeError):
        return _json(start_response, "400 Bad Request", {"reason": "send JSON with email and password"})
    if not email or not password:
        return _json(start_response, "400 Bad Request", {"reason": "email and password are required"})
    with lock, psycopg.connect(DB_URL, connect_timeout=5) as c:
        row = c.execute("""select id from auth.users where lower(email) = %s and encrypted_password is not null
                           and encrypted_password = extensions.crypt(%s, encrypted_password)""", (email, password)).fetchone()
    if not row:
        time.sleep(0.5)
        return _json(start_response, "401 Unauthorized", {"reason": "Wrong email or password."})
    now = int(time.time())
    token = jwt.encode({"sub": str(row[0]), "aud": "authenticated", "role": "authenticated", "email": email,
                        "iat": now, "exp": now + TOKEN_TTL}, SECRET, algorithm="HS256")
    return _json(start_response, "200 OK", {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL,
                                            "expires_at": now + TOKEN_TTL, "user": {"id": str(row[0]), "email": email}})


def extra(environ, start_response, lock):
    path, method = environ.get("PATH_INFO", "/"), environ.get("REQUEST_METHOD", "GET")
    if path == "/local-login/session" and method == "POST":
        return _sign_in(environ, start_response, lock)
    if path == "/local-login" and method == "GET":
        html = (DEMO / "local-login.html").read_text(encoding="utf-8")
        html = html.replace("Local demo · fictional data · not connected to production", RIBBON)
        html = html.replace("<title>Local Demo Sign-in</title>", "<title>Local Real-Data Sign-in</title>")
        html = html.replace("Local demo sign-in. Production uses Google sign-in only; this page exists only on the local demo server.",
                            "Local sign-in for the copy of production data on this machine. Production uses Google sign-in only.")
        html = html.replace('value="demo-admin@interviewkickstart.com"', 'value="realdata-admin@interviewkickstart.com"')
        start_response("200 OK", [("content-type", "text/html; charset=utf-8"), ("cache-control", "no-store")] + base.PROD_HEADERS)
        return [html.encode()]
    if path in ("/local-login.js", "/local-demo.css") and method == "GET":
        ctype = "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8"
        start_response("200 OK", [("content-type", ctype), ("cache-control", "no-store")] + base.PROD_HEADERS)
        return [(DEMO / path.lstrip("/")).read_bytes()]
    if path in ("/kb", "/kb/", "/kb/index.html") and method == "GET":
        html = (base.PUBLIC / "kb" / "index.html").read_text(encoding="utf-8")
        html = html.replace('<a class="btn primary" href="/">Sign in</a>', '<a class="btn primary" href="/local-login">Sign in</a>', 1)
        html = html.replace('<link rel="stylesheet" href="/kb/kb.css">',
                            '<link rel="stylesheet" href="/kb/kb.css">\n<link rel="stylesheet" href="/local-demo.css">', 1)
        html = html.replace("<body>", '<body>\n<div class="demo-ribbon" id="demo-badge-slot" data-testid="demo-badge">'
                                      'Local copy · real data</div>', 1)
        start_response("200 OK", [("content-type", "text/html; charset=utf-8"), ("cache-control", "no-store")] + base.PROD_HEADERS)
        return [html.encode()]
    return None


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    return base.serve(base.make_app(configure=_configure, extra=extra), port)


if __name__ == "__main__":
    sys.exit(main())
