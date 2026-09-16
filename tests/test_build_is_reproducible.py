"""The build embeds "today", so a historical build must be reproducible.

Found while verifying the AUDIT §6.1 fix: rebuilding produced a different
content hash even though the change touched only `meta`. Every node was
identical and the edge multiset was identical; exactly three fields on 44
`teaches` edges had moved:

    last_taught  2026-07-12 -> 2026-09-13
    sessions_past        4  -> 6
    sessions_scheduled   2  -> 0

Seven days had passed since the committed build. `teaches` splits recorded class
dates against the current date, so the graph is deterministic WITHIN a day and
not across days.

That is correct behaviour — the data ages — but it makes "rebuild and compare"
worthless as a verification tool, because calendar drift is indistinguishable
from a code or corpus change. NP_AS_OF pins the date so the difference that
remains is real.

This matters beyond the fix that found it: the Drive reconciliation gate is
"rebuild from .drive-cache and compare to the committed graph". Without a pinned
date that comparison can never come out clean, and the drift would have been
misattributed to Drive.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GRAPH = REPO / "knowledge" / "graph.json"
BUILDER = REPO / "pipeline" / "04_build_graph.py"

#: Edge fields computed against the build date. Anything added here is a new
#: source of calendar drift and must be pinned by NP_AS_OF too.
TIME_DERIVED_EDGE_FIELDS = {"last_taught", "sessions_past", "sessions_scheduled"}


@pytest.fixture(scope="module")
def builder():
    """Load 04_build_graph.py by path — the name starts with a digit."""
    spec = importlib.util.spec_from_file_location("np_build_graph", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_as_of_defaults_to_today(builder, monkeypatch):
    """Unset, behaviour is exactly what it was before the fix."""
    from datetime import datetime, timezone
    monkeypatch.delenv("NP_AS_OF", raising=False)
    assert builder.as_of_date() == datetime.now(timezone.utc).date().isoformat()


def test_as_of_is_pinnable(builder, monkeypatch):
    monkeypatch.setenv("NP_AS_OF", "2026-09-09")
    assert builder.as_of_date() == "2026-09-09"


def test_empty_as_of_falls_back_to_today(builder, monkeypatch):
    """An unset-but-exported env var must not pin the build to "" ."""
    from datetime import datetime, timezone
    monkeypatch.setenv("NP_AS_OF", "")
    assert builder.as_of_date() == datetime.now(timezone.utc).date().isoformat()


def test_builder_takes_its_date_only_from_as_of_date():
    """No second call to now() may decide what counts as past or future."""
    src = BUILDER.read_text(encoding="utf-8")
    body = src.split("def main(", 1)[1]
    assert "TODAY = as_of_date()" in body
    assert "datetime.now" not in body.split("TODAY")[0], (
        "main() reads the clock before setting TODAY — pin it through "
        "as_of_date() so a historical build is reproducible"
    )


def test_time_derived_fields_are_documented_and_unchanged():
    """A new calendar-dependent edge field must be added to the pinned set.

    Guards the reconciliation gate: if a future change adds, say, `days_since`,
    this fails and forces a decision about whether NP_AS_OF covers it.
    """
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    dated = set()
    for e in g["edges"]:
        for f in e:
            if f in TIME_DERIVED_EDGE_FIELDS:
                dated.add(f)
    assert dated == TIME_DERIVED_EDGE_FIELDS, (
        f"expected exactly {sorted(TIME_DERIVED_EDGE_FIELDS)} in the graph, "
        f"found {sorted(dated)}"
    )
    # first_taught is derived from the data alone, never from the clock, so it
    # must NOT be in the pinned set — if it drifts, that is a real change.
    assert "first_taught" not in TIME_DERIVED_EDGE_FIELDS
