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
    """The real numbers from 2026-09-29, verbatim.

    Checked in the PRE phase, the more permissive one: even there the 401s are
    rejected, because the relaxation is scoped to the unshipped endpoint.
    """
    m = _mod()
    results = {
        "/api/overview":     {"status": 401, "bytes": 54, "times": [219]},
        "/api/search?q=api": {"status": 401, "bytes": 54, "times": [216]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [217]},
    }
    bad = m["invalid_measurements"](results, None, "pre")
    assert bad, "the 401 baseline would still pass"
    joined = " ".join(bad)
    assert "/api/overview" in joined and "/api/search" in joined
    assert "/api/node" in joined, "a missing node id must invalidate the run too"


def test_a_200_that_is_too_small_is_still_rejected():
    """An error body wearing a 200 is the next version of the same bug."""
    m = _mod()
    bad = m["invalid_measurements"](
        {"/api/structure": {"status": 200, "bytes": 61, "times": [10]}}, "x",
        "post")
    assert bad and "too small" in bad[0]


def test_config_is_allowed_to_be_small():
    """It is four settings. A blanket size floor would flag it forever."""
    m = _mod()
    assert not m["invalid_measurements"](
        {"/api/config": {"status": 200, "bytes": 429, "times": [10]}}, "x",
        "pre")


def test_a_real_looking_run_passes():
    m = _mod()
    assert not m["invalid_measurements"]({
        "/api/structure":    {"status": 200, "bytes": 900000, "times": [400]},
        "/api/search?q=api": {"status": 200, "bytes": 4200, "times": [120]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [90]},
        "/api/node?id=x":    {"status": 200, "bytes": 2100, "times": [110]},
    }, "x", "post")


def test_the_timed_requests_send_an_authorization_header():
    """The fix itself, asserted in the source: a bare fetch is what broke it."""
    src = SCRIPT.read_text(encoding="utf-8")
    loop = src[src.index("results = page2.evaluate"):]
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


# ---------------------------------------------------------------------------
# PHASE is stated, never inferred
# ---------------------------------------------------------------------------

def test_pre_deploy_does_not_fail_on_the_unshipped_endpoint():
    m = _mod()
    results = {
        "/api/structure":    {"status": 404, "bytes": 9, "times": [30]},
        "/api/overview":     {"status": 200, "bytes": 51000, "times": [210]},
        "/api/search?q=api": {"status": 200, "bytes": 4200, "times": [180]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [190]},
    }
    assert not m["invalid_measurements"](results, "nid", "pre")


def test_post_deploy_requires_the_new_endpoint():
    m = _mod()
    results = {
        "/api/overview":     {"status": 200, "bytes": 51000, "times": [210]},
        "/api/search?q=api": {"status": 200, "bytes": 4200, "times": [180]},
        "/api/config":       {"status": 200, "bytes": 429, "times": [190]},
    }
    bad = m["invalid_measurements"](results, "nid", "post")
    assert bad and "/api/structure" in bad[0]


def test_post_deploy_rejects_a_broken_new_endpoint():
    m = _mod()
    results = {"/api/structure": {"status": 404, "bytes": 9, "times": [30]}}
    assert m["invalid_measurements"](results, "nid", "post")


def test_pre_deploy_keeps_every_other_endpoint_strict():
    """The relaxation is scoped to the unshipped endpoint and nothing else."""
    m = _mod()
    results = {
        "/api/structure": {"status": 404, "bytes": 9, "times": [30]},
        "/api/overview":  {"status": 401, "bytes": 54, "times": [219]},
    }
    bad = m["invalid_measurements"](results, "nid", "pre")
    assert bad and "/api/overview" in bad[0]
    assert not any("/api/structure" in b for b in bad)


def test_a_missing_node_id_fails_in_both_phases():
    m = _mod()
    for phase in ("pre", "post"):
        bad = m["invalid_measurements"](
            {"/api/config": {"status": 200, "bytes": 429, "times": [1]}},
            None, phase)
        assert any("/api/node" in b for b in bad), phase


def test_the_phase_must_be_stated():
    """No default, no inference. A guard that infers 'pre' from a 404 switches
    itself off exactly when the endpoint it guards has broken."""
    import pytest
    m = _mod()
    with pytest.raises(ValueError):
        m["invalid_measurements"]({}, "nid", "guess")
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'required=True' in src and '"pre", "post"' in src.replace("'", '"')


# ---------------------------------------------------------------------------
# WHERE THE APP KEEPS ITS SESSION
# ---------------------------------------------------------------------------

def test_the_token_check_reads_the_bare_name_not_window():
    """`let SESSION = null` at the top level of a classic script lives in the
    global LEXICAL environment, NOT on `window`.

    Verified against the real production page, signed out:
        typeof window.SESSION -> "undefined"
        bare SESSION          -> null (declared)

    So a check written as `window.SESSION && ...` is false whether or not
    anyone is signed in. It reported "no access token in the page" on a page
    that had signed in automatically in about two seconds.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    # Comments may NAME the broken form — that is how the reason survives.
    # What must not happen is evaluating it.
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith(("#", "#:")))
    assert "window.SESSION" not in code, (
        "the token check reads window.SESSION, which is always undefined: "
        "the app declares `let SESSION` in the global lexical scope")
    assert "_HAS_TOKEN" in code and "SESSION && SESSION.access_token" in code


def test_the_page_declares_session_the_way_the_script_expects():
    """The other half of the pair: if the PAGE changes how it holds the
    session, this fails here rather than as a mysterious timeout."""
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    assert "let SESSION=null;" in html or "let SESSION = null;" in html, (
        "public/index.html no longer declares `let SESSION` at top level; "
        "eval/measure_signed_in.py reads that name and must change with it")
    assert "window.SESSION" not in html, (
        "the page now puts SESSION on window; the script could read either, "
        "but they must agree")


def test_cold_load_is_sampled_not_guessed():
    """Two runs against an unchanged site reported TTFB 207 ms and 1,230 ms."""
    m = _mod()
    assert m["COLD_LOADS"] >= 5
    med, lo, hi = m["_stat"]([207, 1230, 300, 280, 310])
    assert med == 300 and lo == 207 and hi == 1230
    assert m["_stat"]([None, None]) == (None, None, None)


def test_it_waits_for_the_apps_own_authenticated_request():
    """A scope bug was the cause this time; a race is the other way it goes
    wrong. Waiting on the app's own first data call covers both."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "getEntriesByType('resource')" in src
    assert "overview|structure" in src


def test_there_is_a_wait_for_enter_escape_hatch():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "--wait-for-enter" in src or "wait_for_enter" in src
