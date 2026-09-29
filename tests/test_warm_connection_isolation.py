"""A reused connection must not carry one caller's identity into the next.

`request_connection` now keeps ONE connection per warm function instance
instead of opening a new one per request, because opening one measured 1.3 s
from a laptop to ap-northeast-2 and was being paid on every single request.

CACHING IS NOT WHAT MAKES THAT SAFE. The rollback is. Both pieces of
per-request state — `set_config('request.jwt.claims', ..., true)` and
`SET LOCAL ROLE` — are transaction-local, so the rollback in the `finally:`
block is the only thing standing between one caller and the next. These tests
exist so that if someone ever changes it to a commit, or adds an early return
that skips it, the failure is a red test and not a stranger reading another
user's rows.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

from pipeline.lib import db                                            # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(), reason="no database configured")

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


def _uid(conn):
    with conn.cursor() as cur:
        cur.execute("select auth.uid()")
        return cur.fetchone()[0]


def _claims(conn):
    with conn.cursor() as cur:
        cur.execute("select current_setting('request.jwt.claims', true)")
        return cur.fetchone()[0]


def test_the_connection_is_actually_reused(data):
    """Otherwise every assertion below is about a fresh connection and proves
    nothing about the thing that changed."""
    with data.request_connection(A) as c1:
        first = id(c1)
    with data.request_connection(B) as c2:
        assert id(c2) == first, "a new connection was opened; nothing is reused"


def test_a_second_request_does_not_inherit_the_first_identity(data):
    with data.request_connection(A) as c:
        assert str(_uid(c)) == A
    with data.request_connection(B) as c:
        got = str(_uid(c))
        assert got == B, f"the second request saw {got}, expected {B}"
        assert got != A


def test_identity_is_cleared_between_requests_not_merely_overwritten(data):
    """An anonymous request after an identified one must see NOTHING.

    Overwriting would pass the test above and still leak here: a caller with
    no subject would inherit whoever ran last.
    """
    with data.request_connection(A) as c:
        assert str(_uid(c)) == A
    with data.request_connection(None) as c:
        assert _uid(c) is None, "an unidentified request inherited a subject"


def test_the_claims_setting_does_not_survive_the_transaction(data):
    with data.request_connection(A) as c:
        assert A in (_claims(c) or "")
    # Outside any request, on the same cached connection.
    conn = data._WARM
    assert conn is not None
    assert not (_claims(conn) or ""), "jwt claims outlived the request"


def test_the_role_does_not_survive_the_transaction(data):
    with data.request_connection(A) as c:
        with c.cursor() as cur:
            cur.execute("select current_user")
            assert cur.fetchone()[0] == "authenticated"
    conn = data._WARM
    with conn.cursor() as cur:
        cur.execute("select current_user")
        assert cur.fetchone()[0] != "authenticated", (
            "SET LOCAL ROLE outlived the request")


def test_an_exception_inside_the_request_still_clears_identity(data):
    """The finally: block is the control, so it must run on the error path."""
    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with data.request_connection(A):
            raise Boom
    with data.request_connection(None) as c:
        assert _uid(c) is None, "identity survived an exception"


def test_a_broken_connection_is_dropped_rather_than_reused(data):
    """If the reset itself fails, nobody should inherit that connection."""
    with data.request_connection(A) as c:
        pass
    data._WARM.close()                      # simulate a dead connection
    with data.request_connection(B) as c2:
        assert str(_uid(c2)) == B
        assert not getattr(c2, "closed", False)


def test_the_reset_is_a_rollback_and_not_a_commit():
    """Asserted in the source: a commit would make the identity permanent."""
    src = (REPO / "web" / "lib" / "data.py").read_text(encoding="utf-8")
    body = src[src.index("def request_connection"):]
    body = body[:body.index("\ndef ")]
    assert "conn.rollback()" in body
    assert "conn.commit()" not in body, (
        "the per-request reset became a commit; identity would persist")
