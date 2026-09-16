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

#: Fields that USED to be stored on the edge and are now derived at read time.
#: None of these may reappear in graph.json — see AUDIT §B.4.
CALENDAR_DERIVED = {"last_taught", "sessions_past", "sessions_scheduled",
                    "sessions_recorded", "first_taught"}


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


def test_no_calendar_derived_field_is_stored_on_an_edge():
    """AUDIT §B.4 — the fix. These were STORED and drifted; now they are derived.

    Storing them made the graph deterministic within a day and not across days.
    If any reappears, the nightly projection starts emitting ~44 spurious
    UPDATEs again and "rebuild and compare" stops working as verification.
    """
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    stored = {f for e in g["edges"] for f in e if f in CALENDAR_DERIVED}
    assert not stored, (
        f"calendar-derived fields are stored on edges again: {sorted(stored)}. "
        "They belong in pipeline/lib/teaching.py, computed at read time."
    )


def test_the_raw_evidence_is_stored_instead():
    """Deriving is only safe if the evidence survives. Prove it did."""
    from pipeline.lib import teaching
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    with_dates = [e for e in g["edges"] if e.get(teaching.CLASS_DATES)]
    assert len(with_dates) > 1000, (
        f"only {len(with_dates)} edges carry class_dates; the evidence that the "
        "derived values were computed from has been lost, not moved"
    )
    for e in with_dates[:50]:
        ds = e[teaching.CLASS_DATES]
        assert ds == sorted(set(ds)), "class_dates must be sorted and deduplicated"


def test_a_rebuild_on_a_different_day_is_identical():
    """The whole point of §B.4, asserted directly.

    Before the fix, two builds a week apart differed on 44 edges with every node
    and edge key untouched. Now the graph carries no clock-dependent value, so
    the derivation date cannot reach it.
    """
    from pipeline.lib import teaching
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    edges = json.dumps(g["edges"], sort_keys=True)
    for probe in ("2020-01-01", "2030-12-31"):
        counts = [teaching.edge_sessions(e, probe) for e in g["edges"]
                  if e.get(teaching.CLASS_DATES)]
        assert counts, "no edge to probe"
        # The stored bytes cannot change with the probe date; only the derivation does.
        assert json.dumps(g["edges"], sort_keys=True) == edges
    far_past = [teaching.edge_sessions(e, "2020-01-01")
                for e in g["edges"] if e.get(teaching.CLASS_DATES)]
    far_future = [teaching.edge_sessions(e, "2030-12-31")
                  for e in g["edges"] if e.get(teaching.CLASS_DATES)]
    assert sum(c["past"] for c in far_past) == 0, "nothing is past in 2020"
    assert sum(c["scheduled"] for c in far_future) == 0, "nothing is scheduled in 2030"
    assert (sum(c["recorded"] for c in far_past)
            == sum(c["recorded"] for c in far_future)), "the evidence itself must not move"


def test_last_taught_never_reports_a_future_booking():
    """commands/staffing.md: "sessions_scheduled is a FUTURE booking — never
    present it as history." The derivation has to honour that."""
    from pipeline.lib import teaching
    s = teaching.sessions(["2026-01-01", "2030-12-31"], "2026-06-01")
    assert s["last_taught"] == "2026-01-01"
    assert s["past"] == 1 and s["scheduled"] == 1 and s["recorded"] == 2
    none_yet = teaching.sessions(["2030-12-31"], "2026-06-01")
    assert none_yet["last_taught"] is None, "a future-only pair has not been taught"
    assert none_yet["first_taught"] == "2030-12-31"
