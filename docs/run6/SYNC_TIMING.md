# Sync timing — resumable batches (run 6, B1)

Measured 2026-11-03 on the laptop's local Postgres (Docker, 127.0.0.1:54322) with
`scripts/kb_sync_timing.py`, budget `KB_SYNC_BUDGET_SECONDS=10` (the default).
Each batch is one call of the engine the cron route runs (`web/lib/kb/sync.py`
`run(..., budget_seconds=10)`), on a fresh connection; the next batch continues
from the place the last one saved (`kb.sync_runs.resume`, migration 0033).
Counts and seconds only. **The lead re-measures on dev** (the dev pooler is far
away: every round trip there is ~175 ms, D45).

| Scenario | Database | Batches | Seconds per batch | Total | Writes |
|---|---|---|---|---|---|
| No change since the last run | kb_b1 | 1 | 2.3 | 2.3 s | 0 |
| 100 changed source rows (record labels) | kb_b1_timing (throw-away clone of kb_b1) | 1 | 4.8 | 4.8 s | 286 |
| Full first import into an empty KB | kb_b1_timing, kb content tables emptied | 5 | 10.2 · 10.4 · 10.2 · 10.1 · 2.3 | 43.2 s | 25,226 |

Where the batches stopped (the saved place): records → relationships →
attachments → attachments → done. No batch went past 10.4 s: the engine checks
the budget after each write batch, flushes what it has queued, commits, saves
its place and stops.

What every batch pays before any write: reading the old tables and building the
desired state (~2 s here; the "no change" row is almost all of it). On dev that
part grows with the distance to the database, which is why the function limit
has headroom (below).

## The function limit (vercel.json)

`functions."api/**".maxDuration` = **60** (was 15). The cron route runs inside
the one Python function (`api/index.py`), so the limit is the function's.
60 s is the largest value every Vercel plan accepts without Fluid compute
(Hobby: max 60 s; Pro: max 300 s; with Fluid compute both allow more), so the
deployment never fails on it, and it leaves ~5x headroom over a 10 s budget
plus the desired-state read on a distant pooler. A batch never uses it: the
budget stops the work at ~10 s. Lower `KB_SYNC_BUDGET_SECONDS` if dev's
measurement shows the reads alone above ~40 s.

## How resuming works

- Phases in order: records, owners by role, links, relationships, links on
  records, removed at source; then the short finish (layout, legacy rules),
  which is never cut off.
- A batch that reaches the budget writes what it has queued, commits, and saves
  `{"phase", "after"}` (the last unit it finished) on its run row.
- The next batch reads the last finished run's place and skips every unit up to
  it (it rebuilds its id maps for them without writing). A run that completes
  saves nothing, so the run after it starts a new pass from the beginning.
- A failed run keeps the place it started from (its committed batches stay).
- A source row changed in a part an interrupted pass already finished is picked
  up by the next full pass (at most one schedule interval later).
- Test: `tests/test_kb_sync.py::test_a_stopped_run_saves_its_place_and_the_next_one_continues_there`
  (every run stopped after one write: each continues exactly where the previous
  one stopped, never goes back a phase, and ends equal to one uninterrupted run).
