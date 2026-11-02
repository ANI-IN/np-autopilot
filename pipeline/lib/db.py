"""Database access. The one place a connection is opened.

Same rule as `paths.corpus_root()` and `paths.build_log()`: one resolver, so the
connection string cannot be decided in two places and drift.

NEVER the direct `db.<ref>.supabase.co:5432` connection. It is IPv6-only on this
project, so it works on a laptop and fails on Vercel — the worst possible failure
distribution, and a shape that only shows up in production. `assert_not_direct()`
refuses it rather than letting it work locally.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

#: Session pooler — migrations and the projection loader. Long-lived, DDL,
#: session state available.
SESSION = "SUPABASE_DB_URL_SESSION"
#: Transaction pooler, port 6543 — anything serverless. No prepared statements,
#: no session state. See DECISIONS §C.1.
TRANSACTION = "SUPABASE_DB_URL_TRANSACTION"

#: The production Supabase project (STATE.md §2). Named so that a test run can
#: recognise it and refuse — see `production_reason()`.
PROD_PROJECT_REF = "yqmzjgzhxhihnpbgqmeh"
#: Every Supabase-managed host: the poolers (`*.pooler.supabase.com`) and the
#: direct connection (`db.<ref>.supabase.co`). None of them is a test database.
_SUPABASE_HOST_SUFFIXES = (".supabase.com", ".supabase.co")
#: Where the database tests go by default: the Supabase CLI local stack
#: (`db/local/`, HANDOFF.md §I) — Supabase's own Postgres image, auth schema,
#: roles and RLS, so a pass here says something true about production. The
#: password is the stack's fixed local default, not a secret. Override with
#: NP_TEST_DSN.
LOCAL_TEST_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
#: The same stack through its Supavisor transaction pooler on 6543 — the shape
#: production's web requests use. Override with NP_TEST_DSN_TRANSACTION.
LOCAL_TEST_DSN_TRANSACTION = ("postgresql://postgres.pooler-dev:postgres@"
                              "127.0.0.1:6543/postgres")
#: The one way to point the test suite at production. Exactly "1".
ALLOW_PROD_TESTS = "NP_ALLOW_PROD_TESTS"


def assert_not_direct(url: str) -> None:
    host = (urlparse(url).hostname or "")
    if host.startswith("db.") and host.endswith(".supabase.co"):
        raise RuntimeError(
            f"refusing the direct connection ({host}). It is IPv6-only on this "
            "project: it works here and fails on Vercel. Reaching for it is also "
            "a signal that the code assumes a persistent connection it will not "
            "have — use the session pooler for migrations, the transaction "
            "pooler for anything request-scoped."
        )


def production_reason(u: str) -> str | None:
    """Why this DSN is production, or None if it is not.

    Derived from the DSN itself — the host and the project ref — never from a
    flag somebody sets, so a test run cannot be told it is local while pointed
    at Supabase. The reason names the host, never the password.
    """
    p = urlparse(u)
    host = (p.hostname or "").lower()
    user = unquote(p.username or "")
    if host.endswith(_SUPABASE_HOST_SUFFIXES):
        return f"host {host} is Supabase-managed"
    if PROD_PROJECT_REF in host or PROD_PROJECT_REF in user:
        return f"it names the production project ref {PROD_PROJECT_REF}"
    return None


def url(var: str = SESSION) -> str:
    u = os.environ.get(var)
    if not u:
        raise RuntimeError(
            f"{var} is not set.\n"
            "  set -a && . ~/.config/np-autopilot/env && set +a"
        )
    assert_not_direct(u)
    return u


def params(var: str = SESSION) -> dict:
    """Split the URL into connection PARAMETERS, once, here.

    WHY NOT JUST PASS THE URL. The password is percent-encoded — it contains a
    literal `@`, correctly written as `%40`. Local psycopg decodes that once and
    connects. The psycopg vendored into the Vercel bundle decodes the netloc and
    then re-splits it, so `...%402026@aws-0-...` becomes `...@2026@aws-0-...`,
    it takes the FIRST `@`, and the host comes out as

        2026@aws-0-ap-northeast-2.pooler.supabase.com

    which does not resolve. Every authenticated request 500s, and only on
    Vercel — the exact works-on-my-laptop-fails-in-production shape §C warns
    about for the direct connection, arriving by a different route.

    Passing host, port, user, password and dbname as separate keywords removes
    the ambiguity rather than working around it: there is no string left for a
    parser to disagree about.
    """
    u = urlparse(url(var))
    out = {
        "host": u.hostname,
        "port": u.port,
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "dbname": (u.path or "/postgres").lstrip("/") or "postgres",
    }
    if not out["host"]:
        raise RuntimeError(f"{var} has no host: {u.netloc!r}")
    # Belt and braces. `urlparse` splits at the LAST '@' per RFC 3986, so it
    # cannot currently produce a host containing one — this guards a future
    # parser change, not a reachable state today. Said plainly so nobody reads
    # a passing suite as evidence that this branch was exercised.
    if "@" in out["host"]:
        raise RuntimeError(
            f"{var} parsed a host containing '@' ({out['host']!r}). The "
            "credentials and the host have run together — percent-encode the "
            "password, or check for a stray '@'.")
    return out


#: Set by tests/db_guard.py for `production_only` tests (and inherited by any
#: subprocess they spawn). Every connection then goes read-only AFTER it is
#: open, and proves it, because the pooler in front of production does not
#: forward libpq's startup options — PGOPTIONS alone reached the server as
#: `default_transaction_read_only=off` (window step 6, 2026-09-30).
READ_ONLY_ENV = "NP_DB_READ_ONLY"
#: Supabase's transaction pooler. A session setting does not persist there —
#: the next transaction may run on another backend — so read-only mode refuses it.
TRANSACTION_POOLER_PORT = 6543


def _enforce_read_only(conn, var: str, port) -> None:
    if port == TRANSACTION_POOLER_PORT:
        conn.close()
        raise RuntimeError(
            f"read-only mode refuses {var}: port {port} is the TRANSACTION pooler, "
            "where a session setting does not persist between transactions")
    # Committed, not merely executed: a session SET made inside a transaction
    # that is then rolled back is undone with it.
    conn.execute("set default_transaction_read_only = on")
    conn.commit()
    state = conn.execute("show default_transaction_read_only").fetchone()[0]
    conn.rollback()
    if state != "on":
        conn.close()
        raise RuntimeError(f"read-only mode could not be set on {var} "
                           f"(default_transaction_read_only={state})")


def assert_transaction_pooler(url: str) -> None:
    """Request-scoped code must reach a Supabase project through the
    TRANSACTION pooler (port 6543). The session pooler (5432) holds one server
    connection per client for the client's whole life, so many serverless
    instances, each keeping its warm connection, exhaust the project's pool and
    every later request fails. Local stacks (127.0.0.1) are not checked."""
    u = urlparse(url)
    host = u.hostname or ""
    if host.endswith(".pooler.supabase.com") and u.port != TRANSACTION_POOLER_PORT:
        raise RuntimeError(
            f"{TRANSACTION} must use the transaction pooler (port {TRANSACTION_POOLER_PORT}); "
            f"it points at port {u.port}. On Vercel the session pooler is exhausted by "
            "instances holding their warm connection. See docs/DEPLOYMENT.md.")
    assert_not_direct(url)


def connect(var: str = SESSION, **kw):
    """A psycopg connection. Import is local so the pipeline runs without it."""
    import psycopg
    kw.setdefault("connect_timeout", 30)
    if var == TRANSACTION:
        assert_transaction_pooler(os.environ.get(TRANSACTION, ""))
        # Transaction-mode pooling cannot hold prepared statements across
        # statements. psycopg3 prepares after 5 executions by default, which
        # fails with "prepared statement already exists" under the pooler — the
        # single most common works-locally-fails-on-Vercel cause.
        kw.setdefault("prepare_threshold", None)
    p = params(var)
    conn = psycopg.connect(**p, **kw)
    if os.environ.get(READ_ONLY_ENV) == "1":
        _enforce_read_only(conn, var, p["port"])
    return conn


def available() -> bool:
    """True when a connection could be attempted. Lets tests skip cleanly."""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get(SESSION))
