"""A latency table built from 401s is worse than no table.

The first production baseline reported /api/overview at p50 219 ms. Every one
of those requests was a 401: the timed loop issued a bare `fetch(ep)` from
`page.evaluate`, and this app keeps the Supabase access token in PAGE MEMORY
and sends it as an Authorization header rather than a cookie. Saved storage
state authenticates nothing. The table measured the auth rejection path and
looked entirely plausible doing it.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SCRIPT = REPO / "eval" / "measure_signed_in.py"


def _mod():
    return runpy.run_path(str(SCRIPT))


def test_the_exact_run_that_slipped_through_is_now_rejected():
    """The real numbers from 2026-09-29, verbatim."""
    m = _mod()
    results = {
        "/api/overview":     {"status": 401, "bytes": 54, "times": [219]},
        "/api/search?q=api": {"status": 401, "bytes": 54, "times": [216]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [217]},
    }
    bad = m["invalid_measurements"](results, None)
    assert bad, "the 401 baseline would still pass"
    joined = " ".join(bad)
    assert "/api/overview" in joined and "/api/search" in joined
    assert "/api/node" in joined, "a missing node id must invalidate the run too"


def test_a_200_that_is_too_small_is_still_rejected():
    """An error body wearing a 200 is the next version of the same bug."""
    m = _mod()
    bad = m["invalid_measurements"](
        {"/api/structure": {"status": 200, "bytes": 61, "times": [10]}}, "x")
    assert bad and "too small" in bad[0]


def test_config_is_allowed_to_be_small():
    """It is four settings. A blanket size floor would flag it forever."""
    m = _mod()
    assert not m["invalid_measurements"](
        {"/api/config": {"status": 200, "bytes": 429, "times": [10]}}, "x")


def test_a_real_looking_run_passes():
    m = _mod()
    assert not m["invalid_measurements"]({
        "/api/structure":    {"status": 200, "bytes": 900000, "times": [400]},
        "/api/search?q=api": {"status": 200, "bytes": 4200, "times": [120]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [90]},
        "/api/node?id=x":    {"status": 200, "bytes": 2100, "times": [110]},
    }, "x")


def test_the_timed_requests_send_an_authorization_header():
    """The fix itself, asserted in the source: a bare fetch is what broke it."""
    src = SCRIPT.read_text(encoding="utf-8")
    loop = src[src.index("results = page.evaluate"):]
    assert "authorization" in loop.lower(), (
        "the timing loop issues requests without an Authorization header")
    assert "SESSION.access_token" in loop


def test_the_token_never_leaves_the_page():
    """The token VALUE never reaches this process.

    The first version of this test asserted that the STRING "access_token" did
    not appear before `def main`, and flagged a comment that merely named the
    field. Naming it is fine; extracting it is not. So the check is about what
    the code DOES: the token may be read inside a page.evaluate, and must never
    be bound to a Python name, printed, or written.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        if "access_token" not in line:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("#:"):
            continue                      # a comment naming the field
        assert "print" not in line, f"line {i}: the token is printed"
        assert "write" not in line, f"line {i}: the token is written out"
        # A Python-side binding would look like `tok = page.evaluate(...)`.
        assert not any(line.lstrip().startswith(p) for p in
                       ("token =", "tok =", "access =")), \
            f"line {i}: the token is bound to a Python name"

    # And the one evaluate that reads it must not RETURN it.
    assert "return SESSION.access_token" not in src
    assert "=> SESSION.access_token" not in src
