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
from urllib.parse import urlparse

#: Session pooler — migrations and the projection loader. Long-lived, DDL,
#: session state available.
SESSION = "SUPABASE_DB_URL_SESSION"
#: Transaction pooler, port 6543 — anything serverless. No prepared statements,
#: no session state. See DECISIONS §C.1.
TRANSACTION = "SUPABASE_DB_URL_TRANSACTION"


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


def url(var: str = SESSION) -> str:
    u = os.environ.get(var)
    if not u:
        raise RuntimeError(
            f"{var} is not set.\n"
            "  set -a && . ~/.config/np-autopilot/env && set +a"
        )
    assert_not_direct(u)
    return u


def connect(var: str = SESSION, **kw):
    """A psycopg connection. Import is local so the pipeline runs without it."""
    import psycopg
    kw.setdefault("connect_timeout", 30)
    if var == TRANSACTION:
        # Transaction-mode pooling cannot hold prepared statements across
        # statements. psycopg3 prepares after 5 executions by default, which
        # fails with "prepared statement already exists" under the pooler — the
        # single most common works-locally-fails-on-Vercel cause.
        kw.setdefault("prepare_threshold", None)
    return psycopg.connect(url(var), **kw)


def available() -> bool:
    """True when a connection could be attempted. Lets tests skip cleanly."""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get(SESSION))
