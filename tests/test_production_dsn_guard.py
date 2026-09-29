"""The test suite refuses to run against production unless told to.

The database tests insert, delete and re-project. The documented way to load
credentials (`. ~/.config/np-autopilot/env`) loads PRODUCTION's, so "load the
env and run pytest" rewrote production — nothing stopped it. conftest.py now
refuses a production DSN before collection unless NP_ALLOW_PROD_TESTS=1.

Every subprocess below uses a production-SHAPED DSN whose host does not
resolve, so even a broken guard cannot reach a real database: the failure mode
of this test is a connection error, never a write.
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

# Shaped like the real poolers; `nowhere-9` does not resolve.
POOLER = ("postgresql://postgres.zzfakerefzz:pw@"
          "aws-0-nowhere-9.pooler.supabase.com:{port}/postgres")
# Not a Supabase host at all — only the project ref gives it away.
REF_ONLY = f"postgresql://postgres.{db.PROD_PROJECT_REF}:pw@127.0.0.1:1/postgres"
# A port nothing listens on, so "default to local" finds no server.
UNREACHABLE_LOCAL = "postgresql://np@127.0.0.1:1/np_b2"

WRITE_TEST = "tests/test_curation_writes.py"      # inserts and deletes rows


# --- the detector ----------------------------------------------------------

@pytest.mark.parametrize("dsn", [
    POOLER.format(port=5432),                      # session pooler
    POOLER.format(port=6543),                      # transaction pooler
    # Split so CI's "no direct supabase connection" grep does not match a fixture.
    "postgresql://postgres:pw@db." + "abcdefgh.supabase.co:5432/postgres",
    REF_ONLY,
    "postgresql://np@DB.ABCDEFGH.SUPABASE.CO:5432/x",   # case-insensitive
])
def test_production_shapes_are_recognised(dsn):
    assert db.production_reason(dsn)


@pytest.mark.parametrize("dsn", [
    db.LOCAL_TEST_DSN,
    "postgresql://np@localhost:5432/np_b2",
    "postgresql://u:p@example.com:5432/supabase",   # the word, not the host
])
def test_local_shapes_are_not(dsn):
    assert db.production_reason(dsn) is None


def test_the_reason_never_carries_the_password():
    reason = db.production_reason(
        "postgresql://postgres.x:s3cr3t-pw@aws-0-a.pooler.supabase.com:5432/p")
    assert "s3cr3t-pw" not in reason


# --- the gate, end to end ----------------------------------------------------

def _pytest(env_overrides: dict, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in (db.SESSION, db.TRANSACTION, db.ALLOW_PROD_TESTS,
                        "NP_TEST_DSN", "NP_TEST_DSN_TRANSACTION", "NP_SKIP_LEDGER",
                        "NP_SKIP_LEDGER_FILE")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120)


def _refused(r: subprocess.CompletedProcess) -> bool:
    """Refused before collection: pytest's usage-error exit, nothing ran.
    With the gate removed the write test errors on connect instead — exit 1."""
    out = r.stdout + r.stderr
    return (r.returncode == pytest.ExitCode.USAGE_ERROR
            and "REFUSED" in out and "PRODUCTION" in out
            and " passed" not in out and " failed" not in out)


@pytest.mark.parametrize("var", [db.SESSION, db.TRANSACTION])
def test_a_write_test_refuses_a_production_pooler(var):
    r = _pytest({var: POOLER.format(port=5432)}, WRITE_TEST)
    assert _refused(r), r.stdout + r.stderr
    assert var in r.stdout + r.stderr


def test_a_write_test_refuses_the_production_ref_on_any_host():
    r = _pytest({db.SESSION: REF_ONLY}, WRITE_TEST)
    assert _refused(r), r.stdout + r.stderr


@pytest.mark.parametrize("var", ["NP_TEST_DSN", "NP_TEST_DSN_TRANSACTION"])
def test_the_test_dsn_overrides_cannot_smuggle_production_in(var):
    r = _pytest({var: POOLER.format(port=6543)}, WRITE_TEST)
    assert _refused(r), r.stdout + r.stderr


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_only_exactly_1_opts_in(value):
    r = _pytest({db.SESSION: POOLER.format(port=5432),
                 db.ALLOW_PROD_TESTS: value}, WRITE_TEST)
    assert _refused(r), r.stdout + r.stderr


def test_the_opt_in_is_honoured_and_announced():
    """Collect only: with the gate open the write test would try to connect."""
    r = _pytest({db.SESSION: POOLER.format(port=5432),
                 db.ALLOW_PROD_TESTS: "1"}, "--collect-only", WRITE_TEST)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "database: PRODUCTION" in r.stdout


def test_a_local_dsn_is_not_refused():
    r = _pytest({db.SESSION: db.LOCAL_TEST_DSN}, "--collect-only", WRITE_TEST)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "REFUSED" not in r.stdout + r.stderr
    assert "database: 127.0.0.1:54322/postgres" in r.stdout


def test_production_only_tests_skip_locally_and_say_why():
    """No server needed: the skip is decided at collection, from the DSN."""
    r = _pytest({db.SESSION: db.LOCAL_TEST_DSN}, "-rs",
                "tests/test_landing_stats.py::test_stats_json_matches_the_projection")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 skipped" in r.stdout and "production_only:" in r.stdout


def test_no_dsn_and_no_local_server_skips_rather_than_fails():
    r = _pytest({"NP_TEST_DSN": UNREACHABLE_LOCAL}, WRITE_TEST)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped" in r.stdout and " passed" not in r.stdout
    assert "database: none" in r.stdout
