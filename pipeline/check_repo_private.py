"""Fail if the GitHub repository is public. R18 and R21, made mechanical.

The repository was public for eight days (R18), and the replacement created to
remediate it was itself created PUBLIC and stayed so for 13 days (R21) while
the project's state record said "private". Both times the record said one thing and nothing
checked the system that would show the other. This checks it.

Two ways to ask, and both are the real question:

  * Authenticated (GITHUB_TOKEN set — CI): the API's own `private` field.
  * Unauthenticated (no token — the pre-push hook): can an anonymous request
    read the repository at all? HTTP 200 means yes, which means public. 404 is
    what GitHub returns for a private repository to a stranger.

Anything else — rate limit, network error, an unexpected status — is a FAILURE,
not a pass. A check that goes green when it could not look is the A.7b shape.

    python3 pipeline/check_repo_private.py                 # repo from `origin`
    python3 pipeline/check_repo_private.py ANI-IN/np-autopilot

Used by .github/workflows/ci.yml (secrets job) and .githooks/pre-push.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/repos/{repo}"


def parse_repo(url: str) -> str:
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit(f"origin is not a GitHub repository: {url!r}")
    return m.group(1)


def repo_from_origin() -> str:
    return parse_repo(subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True).stdout.strip())


def fetch(repo: str, token: str | None) -> tuple[int, dict]:
    req = urllib.request.Request(API.format(repo=repo),
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "np-autopilot-visibility"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def verdict(status: int, body: dict, authenticated: bool) -> tuple[bool, str]:
    """(ok, reason). ok is True only on positive evidence of privacy."""
    if authenticated:
        if status == 200 and body.get("private") is True:
            return True, "private (authenticated API: private=true)"
        if status == 200 and body.get("private") is False:
            return False, "PUBLIC (authenticated API: private=false)"
        return False, f"could not determine visibility (authenticated API: HTTP {status})"
    if status == 404:
        return True, "private (anonymous request refused: HTTP 404)"
    if status == 200:
        return False, "PUBLIC (anonymous request succeeded: HTTP 200)"
    return False, f"could not determine visibility (anonymous API: HTTP {status})"


def main(argv: list[str]) -> int:
    repo = argv[1] if len(argv) > 1 else repo_from_origin()
    token = os.environ.get("GITHUB_TOKEN") or None
    try:
        status, body = fetch(repo, token)
    except OSError as exc:
        print(f"REFUSED: {repo}: could not reach the GitHub API ({exc}). "
              "A visibility check that cannot look does not pass.")
        return 1
    ok, reason = verdict(status, body, authenticated=bool(token))
    if ok:
        print(f"{repo}: {reason}")
        return 0
    print(f"REFUSED: {repo} is {reason}.\n"
          "  This repository must be private (docs/operations/risk-register.md R18, R21). Nothing "
          "should be pushed to it until it is.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
