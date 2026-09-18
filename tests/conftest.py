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
import tempfile
from pathlib import Path

import pytest


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
