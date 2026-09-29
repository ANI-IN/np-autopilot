"""The skip ledger fails when a skip is not listed — proved, not assumed.

tests/ci-skips.yaml lists every skip CI's `test` job may report. These run
pytest on ONE test with a known skip, against a temporary ledger, so the real
ledger is never edited to prove the mechanism.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
TARGET = ("tests/test_exclusion_is_deny_by_default.py::"
          "test_the_deployed_response_carries_every_security_header")
REASON = "set NP_VERIFY_URL to check the live deployment"


def _run(tmp_path: Path, skips: dict, enforce: bool = True):
    ledger = tmp_path / "ledger.yaml"
    ledger.write_text(yaml.safe_dump({"skips": skips}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("NP_SKIP_LEDGER", "NP_SKIP_LEDGER_FILE", "NP_VERIFY_URL")}
    env["NP_SKIP_LEDGER_FILE"] = str(ledger)
    if enforce:
        env["NP_SKIP_LEDGER"] = "enforce"
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
                           "-q", TARGET], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)


def test_a_listed_skip_passes_and_is_printed(tmp_path):
    r = _run(tmp_path, {REASON: 1})
    assert r.returncode == 0, r.stdout
    assert "skips by reason (1)" in r.stdout and REASON in r.stdout
    assert "skip ledger: matches" in r.stdout


def test_an_unlisted_skip_fails(tmp_path):
    r = _run(tmp_path, {})
    assert r.returncode == 1, r.stdout
    assert "SKIP LEDGER MISMATCH" in r.stdout and REASON in r.stdout


def test_a_stale_allowance_fails_too(tmp_path):
    """Exact, both ways: a count that shrank would otherwise absorb a new skip."""
    r = _run(tmp_path, {REASON: 1, "a skip that no longer happens": 3})
    assert r.returncode == 1, r.stdout


def test_a_grown_count_fails(tmp_path):
    r = _run(tmp_path, {REASON: 0})
    assert r.returncode == 1, r.stdout


def test_without_enforce_it_only_prints(tmp_path):
    r = _run(tmp_path, {}, enforce=False)
    assert r.returncode == 0, r.stdout
    assert "skips by reason (1)" in r.stdout


def test_ci_enforces_it():
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = ci["jobs"]["test"]["steps"]
    assert any("pytest" in str(s.get("run", "")) and
               (s.get("env") or {}).get("NP_SKIP_LEDGER") == "enforce" for s in steps)
