"""pipeline/check_repo_private.py — passes only on positive evidence of privacy.

Offline: the verdict is tested against the responses GitHub gives, including
the ones that must NOT pass (rate limit, server error), because a visibility
check that goes green when it could not look is how R21 lasted 13 days.
"""
from __future__ import annotations

import importlib.util
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_repo_private", REPO / "pipeline" / "check_repo_private.py")
crp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crp)


@pytest.mark.parametrize("status, body, authenticated, ok", [
    (404, {}, False, True),                      # anonymous refused: private
    (200, {"private": False}, False, False),     # anonymous read it: PUBLIC
    (403, {}, False, False),                     # rate limited: could not look
    (500, {}, False, False),
    (200, {"private": True}, True, True),        # CI, with GITHUB_TOKEN
    (200, {"private": False}, True, False),
    (200, {}, True, False),                      # field missing: could not look
    (404, {}, True, False),                      # token cannot see it: could not look
])
def test_only_positive_evidence_of_privacy_passes(status, body, authenticated, ok):
    assert crp.verdict(status, body, authenticated)[0] is ok


def test_an_unreachable_api_fails(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(crp, "fetch", boom)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert crp.main(["x", "o/r"]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_a_public_repo_fails_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(crp, "fetch", lambda repo, token: (200, {"private": False}))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert crp.main(["x", "o/r"]) == 1
    assert "PUBLIC" in capsys.readouterr().out


def test_the_repo_is_read_from_origin_urls():
    for url in ("https://github.com/ANI-IN/np-autopilot.git",
                "git@github.com:ANI-IN/np-autopilot.git",
                "https://github.com/ANI-IN/np-autopilot"):
        assert crp.parse_repo(url) == "ANI-IN/np-autopilot", url


def test_ci_runs_the_check_with_a_token():
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pipeline/check_repo_private.py" in ci
    assert "GITHUB_TOKEN" in ci


def test_the_pre_push_hook_runs_the_check_and_is_executable():
    hook = REPO / ".githooks" / "pre-push"
    assert "check_repo_private.py" in hook.read_text(encoding="utf-8")
    assert hook.stat().st_mode & stat.S_IXUSR
