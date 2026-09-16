"""refresh.py must decide the version bump from the LOCK, not the working tree.

Found while landing AUDIT §A.5. I ran 04_build_graph.py by hand — which
pipeline/README documents as normal, "any pass can be re-run without repeating
the one before" — and then ran refresh.py. Refresh captured its "before"
snapshot from the working-tree graph.json, which already contained the change.
It compared new against new, printed:

    IDENTICAL — nodes and edges byte-identical to the previous build
    version unchanged at 0.1.4 (graph did not change)

then rewrote .version-lock.json with the NEW hash. That last step disarmed
validate.py as well, which compares the graph to the lock — so a content change
shipped under an unchanged version and the report said 0 FAIL.

The graph really had changed: a53462823ca26466 -> 961d6beb4b740a44.

This is the precise failure the version lock exists to prevent, reached through
the front door. README calls the bump "automatic AND enforced"; it was enforced
only for anyone who had not run a pass by hand first.

The lock records what was last RELEASED, so it is the only honest baseline.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

REFRESH = REPO / "pipeline" / "refresh.py"

RELEASED = "a53462823ca26466fc5e6b3bf18615ec51bb96ed003249a866f7a29f4dc567e8"
REBUILT = "961d6beb4b740a44990a8c978332f9f5d943254f42131dce553ef00e901abf9a"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("np_refresh", REFRESH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unchanged_content_does_not_bump(refresh):
    assert refresh.needs_bump({"content_hash": RELEASED}, RELEASED) is False


def test_changed_content_bumps(refresh):
    assert refresh.needs_bump({"content_hash": RELEASED}, REBUILT) is True


def test_the_regression_itself(refresh):
    """The exact scenario: a pass was run by hand, so the tree already matched.

    A tree-based comparison sees no delta here. A lock-based one sees the change.
    """
    tree_hash_before_refresh = REBUILT      # hand-run already wrote it
    lock = {"content_hash": RELEASED, "plugin_version": "0.1.4"}
    assert tree_hash_before_refresh == REBUILT      # tree-based: "IDENTICAL"
    assert refresh.needs_bump(lock, REBUILT) is True, (
        "refresh would skip the bump and then overwrite the lock, disarming "
        "validate.py's enforcement too"
    )


def test_missing_lock_bumps(refresh):
    """No lock means nothing is known to be released. Bump rather than assume."""
    assert refresh.needs_bump(None, REBUILT) is True
    assert refresh.needs_bump({}, REBUILT) is True
    assert refresh.needs_bump({"content_hash": ""}, REBUILT) is True


def test_refresh_no_longer_baselines_on_the_working_tree():
    """Static guard: the decision must not come from the pre-run snapshot."""
    src = REFRESH.read_text(encoding="utf-8")
    assert 'changed = before is None or before["hash"] != after["hash"]' not in src, (
        "the bump decision is back on the working-tree snapshot"
    )
    assert "changed = needs_bump(" in src


def test_a_hand_run_divergence_is_announced():
    """Silence is how this stayed invisible. The disagreement must be printed."""
    src = REFRESH.read_text(encoding="utf-8")
    assert "a pass was run by hand" in src


def test_no_bump_does_not_release_the_hash():
    """--no-bump printed "validate will hard-fail" and then wrote the lock.

    Writing the lock is what RELEASES a content hash — validate.py compares the
    graph against it. So the dry-run flag silently made the warning untrue, the
    same defeat-your-own-guard shape as the tree-vs-lock bug above.
    """
    src = REFRESH.read_text(encoding="utf-8")
    body = src.split("def main(", 1)[1]
    assert "if changed and args.no_bump:" in body, (
        "--no-bump writes the version lock unconditionally again"
    )
    lock_write = body.split("LOCK.write_text", 1)[0]
    assert "version lock NOT updated" in lock_write
