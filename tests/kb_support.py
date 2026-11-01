"""Shared fixtures for the KB tests (test_kb_*.py).

LOCAL OR DEV DATABASE ONLY. `reset()` truncates the kb content tables, so it
refuses any DSN that is not a loopback host; tests/conftest.py separately
refuses production before collection.

Users are SYNTHETIC: `kbtest-<role>@interviewkickstart.com`, the same
shape tests/test_role_boundary.py uses. No real identity appears here.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "web", REPO / "api"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from pipeline.lib import db                                           # noqa: E402

ROLES = ("viewer", "contributor", "editor", "admin")
#: A fixed, test-only HS256 secret. The local DB never verifies JWTs (claims
#: are set with set_config); only web/lib/auth.py does, and this is what it
#: verifies against in-process. Not the local stack's secret, not anyone's.
TEST_JWT_SECRET = "kb-tests-only-" + "x" * 40

USERS = {r: str(uuid.uuid5(uuid.NAMESPACE_URL, f"np-kb-test/{r}")) for r in ROLES}
OUTSIDER = str(uuid.uuid5(uuid.NAMESPACE_URL, "np-kb-test/no-profile"))

CONTENT_TABLES = ("node_tags", "node_resources", "edges", "nodes", "resources", "tags",
                  "proposals", "api_tokens", "audit_log")


def session_dsn() -> str | None:
    return os.environ.get(db.SESSION)


def _require_local(dsn: str) -> None:
    host = urlparse(dsn).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(f"KB tests reset data; refusing non-local host {host}")


def kb_available() -> bool:
    dsn = session_dsn()
    if not dsn:
        return False
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=3) as c:
            return c.execute("select to_regclass('kb.nodes') is not null").fetchone()[0]
    except Exception:                                                  # noqa: BLE001
        return False


requires_kb = pytest.mark.skipif(
    not kb_available(),
    reason="kb: needs the local database with the kb migrations (0022+) applied (db/local/setup.sh)")


def owner():
    import psycopg
    dsn = session_dsn()
    _require_local(dsn)
    return psycopg.connect(dsn, autocommit=True)


def ensure_users() -> None:
    with owner() as c:
        for r, uid in USERS.items():
            c.execute("insert into auth.users (id, email, created_at) values (%s, %s, now()) "
                      "on conflict (id) do nothing", (uid, f"kbtest-{r}@interviewkickstart.com"))
            c.execute("insert into profiles (user_id, email, email_domain, role) "
                      "values (%s, %s, 'interviewkickstart.com', 'member') on conflict (user_id) do nothing",
                      (uid, f"kbtest-{r}@interviewkickstart.com"))
            if r == "viewer":
                c.execute("delete from kb.memberships where user_id = %s", (uid,))
            else:
                c.execute("insert into kb.memberships (user_id, role) values (%s, %s) "
                          "on conflict (user_id) do update set role = excluded.role", (uid, r))


def reset() -> None:
    with owner() as c:
        c.execute("truncate " + ", ".join(f"kb.{t}" for t in CONTENT_TABLES) + " cascade")


@contextmanager
def as_user(user_id: str | None, actor_type: str = "human"):
    """A connection exactly like web/lib/data.request_connection gives a route."""
    import psycopg
    conn = psycopg.connect(session_dsn())
    claims = {"role": "authenticated", **({"sub": user_id} if user_id else {})}
    conn.execute("select set_config('request.jwt.claims', %s, true), set_config('role', 'authenticated', true), "
                 "set_config('kb.actor_type', %s, true)", (json.dumps(claims), actor_type))
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def type_id(key: str) -> str:
    with owner() as c:
        return str(c.execute("select id from kb.node_types where key = %s", (key,)).fetchone()[0])


def edge_type_id(key: str) -> str:
    with owner() as c:
        return str(c.execute("select id from kb.edge_types where key = %s", (key,)).fetchone()[0])


# ---------------------------------------------------------------------------
# HTTP: the real WSGI app, a real HS256 token, no stub identity.
# ---------------------------------------------------------------------------

def token_for(user_id: str, *, ttl: int = 600) -> str:
    import jwt
    now = int(time.time())
    return jwt.encode({"sub": user_id, "aud": "authenticated", "role": "authenticated",
                       "exp": now + ttl, "iat": now,
                       "email": f"kbtest-{user_id[:8]}@interviewkickstart.com"},
                      TEST_JWT_SECRET, algorithm="HS256")


class Client:
    def __init__(self, user_id: str | None):
        os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
        os.environ.setdefault(db.TRANSACTION, os.environ.get(db.SESSION, ""))
        import index
        self.app = index.app
        self.user_id = user_id

    def call(self, method: str, path: str, body=None, query: str = ""):
        raw = json.dumps(body).encode() if body is not None else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
        if self.user_id:
            env["HTTP_AUTHORIZATION"] = f"Bearer {token_for(self.user_id)}"
        out = {}

        def start_response(status, headers):
            out["status"] = int(status.split()[0])

        payload = b"".join(self.app(env, start_response))
        return out["status"], (json.loads(payload) if payload else None)

    def get(self, path, query=""):
        return self.call("GET", path, query=query)

    def post(self, path, body=None, query=""):
        return self.call("POST", path, body or {}, query)

    def patch(self, path, body, query=""):
        return self.call("PATCH", path, body, query)

    def delete(self, path):
        return self.call("DELETE", path)


# ---------------------------------------------------------------------------
# The local dev server (eval/kb_dev_server.py) for browser and MCP tests.
# ---------------------------------------------------------------------------

@contextmanager
def dev_server():
    """Start eval/kb_dev_server.py on a free port; yield its base URL."""
    import socket
    import subprocess
    import tempfile
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False)
    # stdout to a FILE: the server prints an audit line per request, and an
    # undrained pipe fills and blocks it mid-suite.
    proc = subprocess.Popen([sys.executable, str(REPO / "eval" / "kb_dev_server.py"), str(port)],
                            stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ))
    try:
        deadline = time.time() + 30
        while time.time() < deadline and "READY" not in Path(log.name).read_text(errors="replace"):
            time.sleep(0.2)
        if "READY" not in Path(log.name).read_text(errors="replace"):
            raise RuntimeError("kb_dev_server did not start: " + Path(log.name).read_text(errors="replace")[-500:])
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.kill()
        proc.wait(10)
