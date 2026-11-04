"""R23 — the prebuilt function may cite only files the upload will include.

Window step 4 (2026-09-30) failed on Vercel because the function map cited
files `.vercelignore` kept out of the upload. db/window/check_function_map.py
refuses such an artifact before any deploy; these tests hold it to that, on
synthetic artifacts, and hold the repository's `.vercelignore` to never
reaching into the build output.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_function_map", REPO / "db" / "window" / "check_function_map.py")
cfm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfm)

VENV = ".vercel/python/.venv/lib/python3.12/site-packages"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _artifact(tmp_path, cites, ignore=None):
    d = tmp_path / "artifact"
    (d / ".vercel/output/functions/python.func").mkdir(parents=True)
    fmap = {}
    for src in cites:
        (d / src).parent.mkdir(parents=True, exist_ok=True)
        (d / src).write_text("x", encoding="utf-8")
        fmap[src.replace(VENV, "_vendor")] = src
    (d / cfm.VC_CONFIG).write_text(json.dumps({"filePathMap": fmap}), encoding="utf-8")
    (d / ".vercelignore").write_text(
        ignore if ignore is not None else (REPO / ".vercelignore").read_text(encoding="utf-8"),
        encoding="utf-8")
    return d


GOOD = ["api/index.py", "web/lib/data.py", "pipeline/lib/taxonomy.py",
        "config/taxonomy.yaml", "README.md", f"{VENV}/psycopg/__init__.py"]


def test_a_clean_artifact_passes(tmp_path):
    assert cfm.check(_artifact(tmp_path, GOOD)) == []


@pytest.mark.parametrize("bad", ["01-corpus-inventory.md", "docs/HANDOFF.md",
                                 "tests/test_x.py", "pipeline/project_graph.py"])
def test_citing_an_uploaded_excluded_file_fails(tmp_path, bad):
    """The step-4 failure, reproduced: the function cites what is not uploaded."""
    problems = cfm.check(_artifact(tmp_path, GOOD + [bad]))
    assert problems and "EXCLUDED" in problems[0] and bad in problems[0]


def test_the_build_output_is_never_excluded_by_the_repo_ignore_file(tmp_path):
    """`commands/` and `*.md` used to match inside .vercel/python/.venv."""
    venv = [f"{VENV}/pip/_internal/commands/__init__.py",
            f"{VENV}/pip-26.2.1.dist-info/licenses/src/pip/_vendor/idna/LICENSE.md"]
    assert cfm.check(_artifact(tmp_path, GOOD + venv)) == []


def test_without_the_re_include_the_venv_case_fails(tmp_path):
    """Mutation: the repo's .vercelignore minus its `!.vercel/` lines."""
    ignore = "\n".join(l for l in (REPO / ".vercelignore").read_text(encoding="utf-8").splitlines()
                       if not l.startswith("!.vercel"))
    venv = [f"{VENV}/pip/_internal/commands/__init__.py"]
    assert cfm.check(_artifact(tmp_path, GOOD + venv, ignore=ignore))


def test_a_missing_cited_file_fails(tmp_path):
    d = _artifact(tmp_path, GOOD)
    (d / "web/lib/data.py").unlink()
    assert any("do not exist" in p for p in cfm.check(d))


def test_the_pulled_env_file_fails(tmp_path):
    d = _artifact(tmp_path, GOOD)
    (d / cfm.ENV_FILE).write_text("SECRET=x", encoding="utf-8")
    assert any("secrets" in p for p in cfm.check(d))


def test_the_build_script_prunes_before_building_and_checks_after():
    src = (REPO / "db" / "window" / "build_artifact.sh").read_text(encoding="utf-8")
    assert src.index("--exclude-from=.vercelignore") < src.index("vercel build --prod")
    assert src.rstrip().endswith('check_function_map.py" "$D"')
    assert "rm -f \"$D/.vercel/.env.production.local\"" in src


def test_the_runsheet_checks_the_map_before_deploying():
    rs = (REPO / "docs" / "operations" / "window-runsheet.md").read_text(encoding="utf-8")
    step4 = next(l for l in rs.splitlines() if l.startswith("| 4 |"))
    assert step4.index("check_function_map.py") < step4.index("--prod")
    assert "vercel deploy --prebuilt`" in step4 or "preview" in step4
