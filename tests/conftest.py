"""Test-session isolation for the build log.

Every pass APPENDS its run record to BUILD_LOG.md, and that is correct
behaviour — the log is how a corpus delta gets explained months later. But
tests/test_deterministic_ids.py shells out to 03_resolve.py twice, so a plain
`pytest` run used to leave BUILD_LOG.md modified in the working tree. That makes
`git status` an unreliable signal and would make any CI check on tracked files
flap.

The fix is isolation, not suppression: NP_BUILD_LOG redirects the append to a
temp file for the whole session, so the code under test writes exactly what it
writes in production. `tests/test_build_log_isolation.py` asserts BOTH halves —
the repo file is untouched AND the append still happened.

Set via os.environ (not monkeypatch) because subprocesses inherit os.environ,
and the passes under test are subprocesses.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

from db_guard import guard_for                                       # noqa: E402

#: Which database this run uses, for the report header. Set in pytest_configure.
_DATABASE = "none — database tests skip"
#: True only when the run targets production AND was opted in to it.
_TARGET_IS_PRODUCTION = False

PRODUCTION_ONLY_SKIP = (
    "production_only: asserts on production's own rows (real identities, the "
    "live projection) — run read-only with NP_ALLOW_PROD_TESTS=1 against "
    "production, HANDOFF.md §D.7")


def pytest_configure(config):
    """The database tests write: they insert and delete rows, and
    test_db_migration_verification re-projects the graph. Pointed at
    production, a plain `pytest` rewrites production.

    That nearly happened: the working instruction was to load
    ~/.config/np-autopilot/env and run the suite, and that env IS production.
    So a production DSN is refused here, before collection, unless
    NP_ALLOW_PROD_TESTS=1 — derived from the DSN (db.production_reason), not
    from a flag that says "this is local".

    With no DSN set, the tests default to the Supabase CLI local stack
    (db.LOCAL_TEST_DSN / LOCAL_TEST_DSN_TRANSACTION, or NP_TEST_DSN /
    NP_TEST_DSN_TRANSACTION) when it is listening, and skip when it is not.
    HANDOFF.md §I is the procedure.
    """
    global _DATABASE, _TARGET_IS_PRODUCTION
    config.addinivalue_line(
        "markers", "production_only: asserts on production's own rows; "
        "skipped unless the run targets production, and always read-only")
    allowed = os.environ.get(db.ALLOW_PROD_TESTS) == "1"
    candidates = [(v, os.environ[v]) for v in (db.SESSION, db.TRANSACTION)
                  if os.environ.get(v)]
    defaulted = not candidates
    if defaulted:
        session = os.environ.get("NP_TEST_DSN") or db.LOCAL_TEST_DSN
        transaction = (os.environ.get("NP_TEST_DSN_TRANSACTION")
                       or os.environ.get("NP_TEST_DSN")
                       or db.LOCAL_TEST_DSN_TRANSACTION)
        candidates = [
            ("NP_TEST_DSN" if os.environ.get("NP_TEST_DSN")
             else "the local default", session),
            ("NP_TEST_DSN_TRANSACTION" if os.environ.get("NP_TEST_DSN_TRANSACTION")
             else "the local default (transaction)", transaction)]
    for var, dsn in candidates:
        reason = db.production_reason(dsn)
        if reason and not allowed:
            raise pytest.UsageError(
                f"REFUSED: {var} points at PRODUCTION ({reason}).\n"
                "  The database tests insert, delete and re-project; run "
                "against production they rewrite it.\n"
                "  Run them against the local PostgreSQL instead "
                "(HANDOFF.md §I), or unset the variable to skip them.\n"
                f"  To run against production deliberately: "
                f"{db.ALLOW_PROD_TESTS}=1")
        if reason:
            _TARGET_IS_PRODUCTION = True
            _DATABASE = f"PRODUCTION ({reason}) — {db.ALLOW_PROD_TESTS}=1"
    if not defaulted:
        if not _TARGET_IS_PRODUCTION:
            _DATABASE = _where(candidates[0][1])
        return
    session, transaction = candidates[0][1], candidates[1][1]
    if _listening(session):
        os.environ[db.SESSION] = session
        os.environ[db.TRANSACTION] = transaction
        _DATABASE = _where(session) + " (default)"


def pytest_report_header(config):
    return f"database: {_DATABASE}"


def pytest_collection_modifyitems(config, items):
    if _TARGET_IS_PRODUCTION:
        return
    skip = pytest.mark.skip(reason=PRODUCTION_ONLY_SKIP)
    for item in items:
        if item.get_closest_marker("production_only"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _production_only_is_read_only(request):
    """Every production_only test runs read-only, enforced by the server and
    verified first (tests/db_guard.py). A write fails the test."""
    with guard_for(request.node):
        yield


def _where(dsn: str) -> str:
    p = urlparse(dsn)
    return f"{p.hostname}:{p.port}{p.path}"


def _listening(dsn: str) -> bool:
    p = urlparse(dsn)
    try:
        with socket.create_connection((p.hostname, p.port or 5432), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def isolate_landing_stats():
    """Same isolation as the build log, for the same reason.

    tests/test_db_migration_verification.py re-projects against the real
    database, and project_graph.py regenerates public/stats.json on a
    successful public projection. Without this, running the suite rewrites a
    tracked file — a test that dirties the tree it is testing.
    """
    tmpdir = tempfile.mkdtemp(prefix="np-landing-stats-")
    out = Path(tmpdir) / "stats.json"
    previous = os.environ.get("NP_LANDING_STATS")
    os.environ["NP_LANDING_STATS"] = str(out)
    try:
        yield out
    finally:
        if previous is None:
            os.environ.pop("NP_LANDING_STATS", None)
        else:
            os.environ["NP_LANDING_STATS"] = previous


@pytest.fixture(scope="session", autouse=True)
def isolate_build_log():
    tmpdir = tempfile.mkdtemp(prefix="np-build-log-")
    log = Path(tmpdir) / "BUILD_LOG.md"
    previous = os.environ.get("NP_BUILD_LOG")
    os.environ["NP_BUILD_LOG"] = str(log)
    try:
        yield log
    finally:
        if previous is None:
            os.environ.pop("NP_BUILD_LOG", None)
        else:
            os.environ["NP_BUILD_LOG"] = previous
