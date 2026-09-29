"""A reused connection that died while idle must not fail the next request.

`request_connection` keeps ONE connection per warm instance (B3 cold-start
fix). The pooler or the network can drop it while the instance sits idle, and
psycopg does not know until it next writes to the socket — `conn.closed` is
still False. Before this was handled, the next request's setup statement
raised, the caller got a 500, and only the request AFTER that reconnected.

Two ways a connection dies, both exercised:
  * the SERVER ends it — pg_terminate_backend, what an idle timeout does
    (direct connection, so the kill reaches the client's own backend);
  * the NETWORK drops it — the TCP socket is shut down underneath psycopg,
    through the real transaction pooler on 6543.

LOCAL STACK ONLY: these kill connections. They refuse a production DSN even
under NP_ALLOW_PROD_TESTS.
"""
from __future__ import annotations

import os
import socket
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

from pipeline.lib import db                                            # noqa: E402

pytestmark = [
    pytest.mark.skipif(not db.available(), reason="no database configured"),
    pytest.mark.skipif(any(db.production_reason(os.environ.get(v) or "")
                           for v in (db.SESSION, db.TRANSACTION)),
                       reason="kills connections — never against production"),
]

A = str(uuid.UUID("00000000-0000-0000-0000-0000000000aa"))
B = str(uuid.UUID("00000000-0000-0000-0000-0000000000bb"))


@pytest.fixture
def data(monkeypatch):
    from lib import data as _d
    monkeypatch.setattr(_d, "_WARM", None, raising=False)
    yield _d
    w = getattr(_d, "_WARM", None)
    if w is not None:
        try:
            w.close()
        except Exception:
            pass
    _d._WARM = None


@pytest.fixture
def direct(monkeypatch):
    """Route request connections straight to Postgres, so the backend the
    request holds is the one pg_terminate_backend kills."""
    monkeypatch.setenv(db.TRANSACTION, os.environ[db.SESSION])


def _pid(conn):
    with conn.cursor() as cur:
        cur.execute("select pg_backend_pid()")
        return cur.fetchone()[0]


def _uid(conn):
    with conn.cursor() as cur:
        cur.execute("select auth.uid()")
        return cur.fetchone()[0]


def _terminate(pid):
    with db.connect(db.SESSION, autocommit=True) as admin:
        admin.execute("select pg_terminate_backend(%s)", (pid,))


def _drop_socket(conn):
    s = socket.socket(fileno=os.dup(conn.fileno()))
    try:
        s.shutdown(socket.SHUT_RDWR)
    finally:
        s.close()


def test_a_server_side_kill_between_requests_is_survived(data, direct):
    with data.request_connection(A) as c:
        before = _pid(c)
    _terminate(before)
    with data.request_connection(B) as c:          # must NOT raise
        after = _pid(c)
        assert str(_uid(c)) == B, "the fresh connection lost the caller's identity"
    assert after != before, "the dead connection was reused"


def test_a_network_drop_between_requests_is_survived(data):
    """Through the real transaction pooler."""
    with data.request_connection(A) as c:
        warm = c
    _drop_socket(warm)
    with data.request_connection(B) as c:          # must NOT raise
        assert str(_uid(c)) == B
    assert data._WARM is not warm, "the dropped connection was kept"


def test_a_failure_inside_the_request_is_not_retried(data, direct):
    """Only SETUP is retried — before the endpoint has run anything. A failure
    after that surfaces; retrying it would run the endpoint's work twice."""
    calls = []
    with pytest.raises(Exception):
        with data.request_connection(A) as c:
            calls.append(1)
            _terminate(_pid(c))
            with c.cursor() as cur:
                cur.execute("select 1")
    assert calls == [1]
    with data.request_connection(B) as c:          # and the NEXT one recovers
        assert str(_uid(c)) == B


def test_a_database_that_stays_down_fails_once_and_does_not_loop(data, direct, monkeypatch):
    with data.request_connection(A) as c:
        pid = _pid(c)
    _terminate(pid)
    attempts = []

    def refuse(*a, **k):
        attempts.append(1)
        raise OSError("connection refused (simulated)")
    monkeypatch.setattr(data._db, "connect", refuse)
    with pytest.raises(OSError):
        with data.request_connection(B):
            pass
    assert len(attempts) == 1, f"reconnect was attempted {len(attempts)} times"


def test_a_genuine_sql_error_in_setup_is_not_mistaken_for_a_drop(data, monkeypatch):
    """The retry is for a BROKEN connection only; anything else propagates."""
    with data.request_connection(A):
        pass
    warm = data._WARM
    monkeypatch.setattr(data, "_SETUP_SQL",          # a server-side error
                        "select set_config('request.jwt.claims', %s, true), "
                        "np_no_such_function()")
    with pytest.raises(Exception) as exc:
        with data.request_connection(B):
            pass
    assert "does not exist" in str(exc.value)
    assert data._WARM is warm or data._WARM is None
