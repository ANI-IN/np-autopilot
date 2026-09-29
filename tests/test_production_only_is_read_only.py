"""A `production_only` test cannot write — proved against the local stack.

The tests marked `production_only` run against production (HANDOFF.md §D.7),
so "they are read-only" has to be a property of the connection, not of how
they happen to be written. These canaries attempt the writes a careless test
could make and assert each is refused by the server.

Never run against production: if the enforcement were broken, the canary's
write would land there. So they skip whenever the target is production, and
run against the local Supabase stack.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

import db_guard                                                        # noqa: E402

pytestmark = [
    pytest.mark.skipif(not db.available(), reason="no database to test against"),
    pytest.mark.skipif(bool(os.environ.get(db.SESSION))
                       and bool(db.production_reason(os.environ[db.SESSION])),
                       reason="never canary a write against production"),
]

WRITE = "insert into auth_hook_refusals (reason) values ('read-only canary')"
#: The seven tests that assert on production's own rows (the owner's list, 2026-09-29).
EXPECTED_PRODUCTION_ONLY = 7


@pytest.fixture(autouse=True)
def _clean_up_if_the_guard_failed():
    yield
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from auth_hook_refusals where reason = 'read-only canary'")
        conn.commit()


def _refused(exc: BaseException) -> bool:
    return "read-only transaction" in str(exc)


@pytest.mark.parametrize("var", [db.SESSION, db.TRANSACTION])
def test_a_write_is_refused_on_either_connection(var):
    with db_guard.read_only_database():
        with pytest.raises(Exception) as exc:
            with db.connect(var) as conn, conn.cursor() as cur:
                cur.execute(WRITE)
                conn.commit()
    assert _refused(exc.value), exc.value


def test_a_write_is_refused_in_autocommit():
    """psycopg's own read_only flag does not cover autocommit; the server
    setting does. This is why the enforcement is PGOPTIONS."""
    with db_guard.read_only_database():
        with pytest.raises(Exception) as exc:
            with db.connect(db.SESSION, autocommit=True) as conn:
                conn.execute(WRITE)
    assert _refused(exc.value), exc.value


def test_a_write_from_a_subprocess_is_refused():
    code = ("import sys; sys.path.insert(0, '.'); from pipeline.lib import db\n"
            "with db.connect(db.SESSION) as c:\n"
            f"    c.execute({WRITE!r}); c.commit()\n")
    with db_guard.read_only_database():
        r = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                           capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "read-only transaction" in r.stderr, r.stderr


def test_reads_still_work():
    """The positive control: a guard that refused everything would pass above."""
    with db_guard.read_only_database():
        with db.connect(db.SESSION) as conn, conn.cursor() as cur:
            cur.execute("select count(*) from nodes")
            assert cur.fetchone()[0] >= 0


def test_a_target_that_ignores_the_option_is_refused_not_trusted(monkeypatch):
    """If the server does not come up read-only, the test must not run."""
    monkeypatch.setattr(db_guard, "READ_ONLY_OPTION",
                        "-c default_transaction_read_only=off")
    with pytest.raises(RuntimeError, match="refusing to run it unguarded"):
        with db_guard.read_only_database():
            pass


def test_the_environment_is_restored_afterwards():
    before = {k: os.environ.get(k) for k in ("PGOPTIONS", db.TRANSACTION)}
    with db_guard.read_only_database():
        pass
    assert {k: os.environ.get(k) for k in before} == before


class _Node:
    def __init__(self, marked: bool):
        self._marked = marked

    def get_closest_marker(self, name):
        return object() if (self._marked and name == "production_only") else None


def test_a_marked_test_runs_under_the_guard():
    with db_guard.guard_for(_Node(marked=True)):
        assert db_guard.READ_ONLY_OPTION in os.environ.get("PGOPTIONS", "")
        with pytest.raises(Exception) as exc:
            with db.connect(db.SESSION) as conn, conn.cursor() as cur:
                cur.execute(WRITE)
                conn.commit()
    assert _refused(exc.value), exc.value


def test_an_unmarked_test_is_left_alone():
    before = os.environ.get("PGOPTIONS")
    with db_guard.guard_for(_Node(marked=False)):
        assert os.environ.get("PGOPTIONS") == before


def test_every_production_only_test_gets_the_guard(request):
    marked = [i for i in request.session.items
              if i.get_closest_marker("production_only")]
    if request.config.option.keyword or request.config.option.markexpr:
        pytest.skip("a filtered run does not collect the whole suite")
    if not any("test_landing_stats.py" in i.nodeid for i in request.session.items):
        pytest.skip("run as part of the whole suite")
    assert len(marked) == EXPECTED_PRODUCTION_ONLY, [i.nodeid for i in marked]
    unguarded = [i.nodeid for i in marked
                 if "_production_only_is_read_only" not in i.fixturenames]
    assert not unguarded, unguarded
