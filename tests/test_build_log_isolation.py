"""AUDIT §6.4 — running a pass must not dirty the working tree under test.

Characterization: the append to the build log is CORRECT behaviour and must
survive. What must not survive is the append landing on the repo's tracked
BUILD_LOG.md during a test run. So every test here asserts both halves — the
tracked file is untouched, AND the record was still written.

A test that only asserted "BUILD_LOG.md unchanged" would pass if someone deleted
the logging entirely. That is the failure mode this file exists to prevent.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import paths                                        # noqa: E402

REPO = Path(__file__).resolve().parent.parent
TRACKED_LOG = REPO / "BUILD_LOG.md"


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "(absent)"


# --------------------------------------------------------------------------
# the resolver: one place decides the path, and it is injectable
# --------------------------------------------------------------------------

def test_default_build_log_is_the_repo_file(monkeypatch):
    """With no override, behaviour is exactly what it was before this fix."""
    monkeypatch.delenv("NP_BUILD_LOG", raising=False)
    assert paths.build_log() == paths.DEFAULT_BUILD_LOG == TRACKED_LOG


def test_env_var_redirects_the_build_log(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere.md"
    monkeypatch.setenv("NP_BUILD_LOG", str(target))
    assert paths.build_log() == target


def test_conftest_has_redirected_this_session(isolate_build_log):
    """The session fixture is active, so a pass run now cannot touch the repo."""
    assert paths.build_log() == isolate_build_log
    assert paths.build_log() != TRACKED_LOG


# --------------------------------------------------------------------------
# the passes: append still happens, just not to the tracked file
# --------------------------------------------------------------------------

def test_resolve_pass_appends_to_the_injected_log_and_not_the_tracked_one(
        isolate_build_log):
    """03_resolve.py is the pass the test suite shells out to (B5 determinism).

    This is the exact path that used to dirty the tree.
    """
    before_tracked = _digest(TRACKED_LOG)
    before_injected = isolate_build_log.stat().st_size if isolate_build_log.exists() else 0

    r = subprocess.run([sys.executable, "pipeline/03_resolve.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]

    assert _digest(TRACKED_LOG) == before_tracked, (
        "03_resolve.py wrote to the tracked BUILD_LOG.md despite NP_BUILD_LOG "
        "being set. The pass is not resolving the log through paths.build_log()."
    )
    assert isolate_build_log.exists(), (
        "no build-log record was written anywhere. The append is correct "
        "behaviour and must be redirected, never suppressed."
    )
    assert isolate_build_log.stat().st_size > before_injected, (
        "the injected log did not grow — the run recorded nothing."
    )
    assert "03_resolve" in isolate_build_log.read_text(encoding="utf-8")


def test_every_pass_resolves_the_log_through_paths():
    """No module may re-derive the build-log path for itself.

    00_fetch_drive.py used to define `BUILD_LOG = ROOT / "BUILD_LOG.md"` of its
    own, which is a second place a repo path is decided — the same rule that
    keeps the corpus root inside paths.corpus_root().
    """
    # A path DERIVATION joins the name onto a directory: `ROOT / "BUILD_LOG.md"`.
    # Naming the file in a set of strings is not a derivation — 01_walk_corpus
    # lists "BUILD_LOG.md" in OWN_DOCS so the walker skips its own log, which is
    # correct and must not trip this check.
    derivation = re.compile(r"/\s*[\"']BUILD_LOG\.md[\"']")
    offenders = []
    for py in sorted((REPO / "pipeline").rglob("*.py")):
        if py.resolve() == (REPO / "pipeline" / "lib" / "paths.py").resolve():
            continue
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if derivation.search(stripped):
                offenders.append(f"{py.relative_to(REPO)}:{lineno}: {stripped}")
    assert not offenders, (
        "these modules derive the build-log path themselves instead of calling "
        "paths.build_log():\n  " + "\n  ".join(offenders)
    )


def test_no_module_imports_a_build_log_constant():
    """The constant is gone on purpose: a constant cannot be injected.

    Keeping both a BUILD_LOG constant and a build_log() function would let a
    module bind the path at import time and silently escape the override.
    """
    bad = []
    for py in sorted((REPO / "pipeline").rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        if "import" in text and "paths import" in text:
            for lineno, line in enumerate(text.splitlines(), 1):
                if "paths import" in line and "BUILD_LOG" in line:
                    bad.append(f"{py.relative_to(REPO)}:{lineno}")
    assert not bad, (
        "importing a BUILD_LOG constant binds the path at import time and "
        "escapes NP_BUILD_LOG: " + ", ".join(bad)
    )
