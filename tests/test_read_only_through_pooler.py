"""production_only tests must be unable to write — THROUGH THE POOLER.

Window step 6 (2026-09-30): production's connections go through Supabase's
pooler, which drops libpq's PGOPTIONS, so `default_transaction_read_only=on`
never reached the server and the guard refused to run the tests. db.connect now
sets read-only after connecting (NP_DB_READ_ONLY) and refuses the transaction
pooler. Proven here by BEHAVIOUR: write canaries (tests/read_only_canaries.py)
through a real session pooler.

Two layers:
- unit tests on a fake driver — run everywhere, CI included;
- behaviour tests through a real pooler — run when NP_TEST_SESSION_POOLER_DSN
  (and NP_TEST_TRANSACTION_POOLER_DSN) point at one; the local Supabase stack
  has both (docs/operations/testing.md §4).
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from pipeline.lib import db                                              # noqa: E402

SESSION_POOLER = os.environ.get("NP_TEST_SESSION_POOLER_DSN")
TRANSACTION_POOLER = os.environ.get("NP_TEST_TRANSACTION_POOLER_DSN")


# --------------------------------------------------------------------------
# unit: the mechanism, on a fake driver
# --------------------------------------------------------------------------

class FakeConn:
    def __init__(self, honours_set=True):
        self.sql, self.closed, self.committed = [], False, 0
        self.state, self.honours_set = "off", honours_set

    def execute(self, q):
        self.sql.append(q)
        if q.startswith("set default_transaction_read_only") and self.honours_set:
            self.state = "on"
        return types.SimpleNamespace(fetchone=lambda: (self.state,))

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def fake(monkeypatch):
    box = {}

    def connect(**kw):
        box["conn"] = FakeConn(box.get("honours", True))
        return box["conn"]
    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    monkeypatch.setenv(db.SESSION, "postgresql://u:p@pooler.example.test:5432/postgres")
    return box


def test_read_only_mode_sets_and_commits_and_verifies(fake, monkeypatch):
    monkeypatch.setenv(db.READ_ONLY_ENV, "1")
    c = db.connect(db.SESSION)
    assert c.sql[0] == "set default_transaction_read_only = on"
    assert c.committed >= 1, "an uncommitted session SET is undone by a rollback"
    assert "show default_transaction_read_only" in c.sql


def test_a_setting_that_does_not_take_refuses_the_connection(fake, monkeypatch):
    monkeypatch.setenv(db.READ_ONLY_ENV, "1")
    fake["honours"] = False
    with pytest.raises(RuntimeError, match="could not be set"):
        db.connect(db.SESSION)
    assert fake["conn"].closed


def test_the_transaction_pooler_is_refused_in_read_only_mode(fake, monkeypatch):
    monkeypatch.setenv(db.READ_ONLY_ENV, "1")
    monkeypatch.setenv(db.SESSION, "postgresql://u:p@pooler.example.test:6543/postgres")
    with pytest.raises(RuntimeError, match="TRANSACTION pooler"):
        db.connect(db.SESSION)


def test_without_the_flag_nothing_changes(fake, monkeypatch):
    monkeypatch.delenv(db.READ_ONLY_ENV, raising=False)
    assert db.connect(db.SESSION).sql == []


def test_the_guard_turns_the_flag_on_and_restores_it(monkeypatch):
    import db_guard
    monkeypatch.delenv(db.READ_ONLY_ENV, raising=False)
    seen = {}

    class C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return self
        def execute(self, q): seen["flag"] = os.environ.get(db.READ_ONLY_ENV)
        def fetchone(self): return ("on",)
    monkeypatch.setattr(db, "connect", lambda *a, **k: C())
    monkeypatch.setenv(db.SESSION, "postgresql://u:p@x:5432/postgres")
    with db_guard.read_only_database():
        assert os.environ[db.READ_ONLY_ENV] == "1"
    assert seen["flag"] == "1"
    assert db.READ_ONLY_ENV not in os.environ


# --------------------------------------------------------------------------
# behaviour: write canaries through a REAL pooler
# --------------------------------------------------------------------------

needs_pooler = pytest.mark.skipif(
    not SESSION_POOLER,
    reason="set NP_TEST_SESSION_POOLER_DSN to a session pooler to run the write canaries")


@pytest.fixture
def through_session_pooler(monkeypatch):
    import db_guard
    monkeypatch.setenv(db.SESSION, SESSION_POOLER)
    monkeypatch.delenv("PGOPTIONS", raising=False)
    with db_guard.read_only_database():
        yield


@needs_pooler
@pytest.mark.parametrize("canary", ["INSERT", "UPDATE", "DELETE", "TRUNCATE"])
def test_every_write_is_refused_through_the_session_pooler(through_session_pooler, canary):
    import read_only_canaries as rc
    res = {n: (ok, msg) for n, ok, msg in rc.canaries(lambda: db.connect(db.SESSION))}
    assert res[canary][0], f"{canary} was NOT refused through the pooler: {res[canary][1]}"


@needs_pooler
@pytest.mark.xfail(strict=True, reason=(
    "KNOWN GAP, pinned: a session setting is a default, so an explicit "
    "SET TRANSACTION READ WRITE can still write. Refusing it needs a database "
    "role without write privileges (docs/operations/testing.md §4). strict: this "
    "test fails the day the gap closes, so the pin cannot go stale."))
def test_set_transaction_read_write_then_a_write_is_refused(through_session_pooler):
    import read_only_canaries as rc
    res = {n: ok for n, ok, _ in rc.canaries(lambda: db.connect(db.SESSION))}
    assert res["SET TRANSACTION READ WRITE, then INSERT"]


@pytest.mark.skipif(not TRANSACTION_POOLER,
                    reason="set NP_TEST_TRANSACTION_POOLER_DSN to a transaction pooler")
def test_the_guard_refuses_to_run_through_the_transaction_pooler(monkeypatch):
    import db_guard
    monkeypatch.setenv(db.SESSION, TRANSACTION_POOLER)
    with pytest.raises(RuntimeError, match="TRANSACTION pooler"):
        with db_guard.read_only_database():
            pass


def test_the_production_form_can_never_run_canary_5():
    import read_only_canaries as rc
    assert "SET TRANSACTION READ WRITE, then INSERT" not in rc.PRODUCTION_SAFE
    seen = []

    class Conn:
        autocommit = False
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, q): seen.append(q)
        def rollback(self): pass
        def close(self): pass
    rc.canaries(lambda: Conn(), only=rc.PRODUCTION_SAFE)
    assert not any("read write" in q for q in seen)
    src = (REPO / "tests" / "read_only_canaries.py").read_text(encoding="utf-8")
    assert "only=PRODUCTION_SAFE" in src.split('if __name__ == "__main__":', 1)[1]
