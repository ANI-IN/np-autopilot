"""Pass 0 must leave a build-log record on EVERY terminal path.

Found during the first real B2 run. The empty-enumeration guard — the most
important check in the file, because a Shared Drive listed without the
all-drives flags returns an empty list with HTTP 200 — called `sys.exit()`
straight past `append_build_log`. So the one failure mode the guard exists to
catch was also the one failure that left no trace.

That is backwards for the pass most likely to run unattended: a nightly job that
fetched nothing looked exactly like a nightly job that never ran.

Seven terminal paths had the same shape (missing config, missing key, key inside
the repo, not a folder, trashed folder, missing dependency, empty enumeration).
All now route through `abort()`, which logs first.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FETCH = REPO / "pipeline" / "00_fetch_drive.py"


@pytest.fixture(scope="module")
def fetch_mod():
    spec = importlib.util.spec_from_file_location("np_fetch_drive", FETCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# static: abort() is the only exit
# --------------------------------------------------------------------------

def test_abort_is_the_only_caller_of_sys_exit():
    """A new `sys.exit` is a new silent failure. Route it through abort()."""
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "exit"
                    and getattr(inner.func.value, "id", None) == "sys"
                    and node.name != "abort"):
                offenders.append(f"{node.name}() at line {inner.lineno}")
    assert not offenders, (
        "sys.exit() outside abort() skips the build log:\n  " + "\n  ".join(offenders)
    )


def test_repo_imports_precede_third_party_imports():
    """A missing dependency must still be loggable.

    Ordered the other way, the failure most likely to hit a freshly provisioned
    scheduler is the one failure that cannot record itself.
    """
    src = FETCH.read_text(encoding="utf-8")
    assert src.index("from pipeline.lib.paths import") < src.index("import yaml"), (
        "third-party imports come before the build-log import, so an "
        "ImportError cannot be logged"
    )


def test_the_empty_enumeration_guard_logs_before_exiting():
    """The specific regression: the most important check left no trace."""
    src = FETCH.read_text(encoding="utf-8")
    guard = src.split("if not entries:", 1)[1].split("print(", 1)[0]
    assert "abort(" in guard, "the empty-enumeration guard no longer routes through abort()"
    assert "sys.exit" not in guard


def test_dry_run_records_that_it_ran():
    """A scheduled job silently switched to --dry-run must not look like silence."""
    src = FETCH.read_text(encoding="utf-8")
    tail = src.split("if args.dry_run:\n        # A dry run", 1)
    assert len(tail) == 2, "the dry-run exit no longer carries its logging block"
    assert "write_log(" in tail[1].split("return 0", 1)[0]


# --------------------------------------------------------------------------
# behavioural: the record actually lands
# --------------------------------------------------------------------------

def test_abort_writes_a_record_then_exits(fetch_mod, tmp_path, monkeypatch):
    log = tmp_path / "BUILD_LOG.md"
    monkeypatch.setenv("NP_BUILD_LOG", str(log))
    with pytest.raises(SystemExit):
        fetch_mod.abort("enumerated 0 files", account="sa@example.com",
                        folder_id="FOLDER123")
    text = log.read_text(encoding="utf-8")
    assert "00_fetch_drive (FAILED)" in text
    assert "enumerated 0 files" in text
    assert "FOLDER123" in text
    assert "sa@example.com" in text


def test_write_log_survives_an_unwritable_path(fetch_mod, tmp_path, monkeypatch, capsys):
    """A logging bug must not become the reason a real failure goes unreported."""
    monkeypatch.setenv("NP_BUILD_LOG", str(tmp_path / "nope" / "x" / "BUILD_LOG.md"))
    (tmp_path / "nope").write_text("I am a file, not a directory", encoding="utf-8")
    fetch_mod.write_log("FAILED", "something broke")       # must not raise
    assert "could not write the build log" in capsys.readouterr().err


def test_a_real_failing_invocation_leaves_a_record(tmp_path, isolate_build_log):
    """End to end: run the script with a key path that does not exist."""
    log = tmp_path / "BUILD_LOG.md"
    env = {**os.environ, "NP_BUILD_LOG": str(log),
           "NP_DRIVE_SA_KEY": str(tmp_path / "absent-key.json")}
    r = subprocess.run([sys.executable, "pipeline/00_fetch_drive.py", "--dry-run"],
                       cwd=REPO, capture_output=True, text=True, env=env)
    assert r.returncode != 0, "a missing key must not exit 0"
    assert log.exists(), "the run exited without recording anything"
    text = log.read_text(encoding="utf-8")
    assert "00_fetch_drive (FAILED)" in text
    assert "service-account key not found" in text


def test_the_log_never_contains_key_material(tmp_path, monkeypatch, fetch_mod):
    """Failure records name paths, never contents."""
    log = tmp_path / "BUILD_LOG.md"
    monkeypatch.setenv("NP_BUILD_LOG", str(log))
    with pytest.raises(SystemExit):
        fetch_mod.abort("service-account key not found at /tmp/some/key.json")
    text = log.read_text(encoding="utf-8")
    for marker in ("BEGIN PRIVATE KEY", "private_key", "client_secret"):
        assert marker not in text
