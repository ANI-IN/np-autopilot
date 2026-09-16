"""Session counts derived from recorded class dates, at READ time.

AUDIT §B.4. `teaches` edges used to STORE last_taught, sessions_past and
sessions_scheduled, computed by partitioning recorded dates against "today" at
build time. That made the graph deterministic within a day and not across days:
rebuilding the 2026-09-09 graph on 2026-09-16 moved 44 edges across the
boundary, every node and every edge key untouched.

Three costs, only the first of which is obvious:

  * A nightly rebuild emits ~44 spurious UPDATEs against an unchanged corpus,
    for ever. Under a diffed projection that buries the one signal worth having.
  * The plugin ships a snapshot, so a laptop reports `sessions_scheduled` as of
    whenever it was built. A class taught in July still reads as "scheduled".
  * "Rebuild and compare" stops working as verification, because calendar drift
    is indistinguishable from a code or corpus change.

Storing the raw dates and deriving the rest here fixes all three. The derived
values are always current, they vanish from the diff, and NP_AS_OF narrows to
its real job — reproducing a historical build for verification.

ONE implementation, imported by query.py and by the eval harness, so the two
cannot drift. They previously read the same stored fields; now they must share
the same derivation instead.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

#: Edge property holding the raw evidence: every recorded class date, sorted.
CLASS_DATES = "class_dates"


def as_of() -> str:
    """The date "past" and "scheduled" are judged against, ISO.

    Honours NP_AS_OF so a historical build — or an eval run against one — can be
    reproduced exactly. Defaults to today, which is what a live query wants.
    """
    return os.environ.get("NP_AS_OF") or datetime.now(timezone.utc).date().isoformat()


def sessions(dates, today: str | None = None) -> dict:
    """Derive session counts from recorded class dates.

    Returns first_taught / last_taught / recorded / past / scheduled.
    `last_taught` is the latest date NOT in the future — an instructor booked for
    next month has not taught it yet, and presenting a future booking as history
    is the failure commands/staffing.md calls out by name.
    """
    ds = sorted(d for d in (dates or []) if d)
    if not ds:
        return {"first_taught": None, "last_taught": None,
                "recorded": 0, "past": 0, "scheduled": 0}
    now = today or as_of()
    past = [d for d in ds if d <= now]
    future = [d for d in ds if d > now]
    return {
        "first_taught": ds[0],
        "last_taught": past[-1] if past else None,
        "recorded": len(ds),
        "past": len(past),
        "scheduled": len(future),
    }


def edge_sessions(edge, today: str | None = None) -> dict:
    """sessions() for one teaches edge. Empty-safe for edges with no dates."""
    return sessions(edge.get(CLASS_DATES), today)
