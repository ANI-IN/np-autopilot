# Run 6 baseline (A1), 2026-11-03, before any run-6 workstream

Commit `9a739f9` (Run 5), plus the Phase A contracts (0032, GET /api/kb/graph).

## Tests
`scripts/verify_all.sh` on 9a739f9: **1,264 passed, 13 failed, 52 skipped** (19 min).
The 13 failures are all in `docs/baseline-failures.txt` (main's 43; 30 of them now pass). 0 KB failures.
Phase A additions: tests/test_kb_contracts.py 13 passed; the API-level KB, sync,
schema, RLS, migration-verification and MCP files re-run: 156 passed.

## Browser console, every screen at 1536 px (eval/kb_screens.py)
| Server | Screens | Console errors | Warnings | Page errors |
|---|---|---|---|---|
| :8766 real data | 28 | 0 | 0 | 0 |
| :8765 demo | 28 | 0 | 0 | 0 |

Screens: sign-in, dashboard, all records, programs, courses, resources, outline, graph,
who teaches what, programme timeline, activity, data quality, approvals, archived, guide,
every Settings tab, a record panel, a record page, New record, and the "/" map.

## Screenshots
- Demo (:8765), 1536 px light: `docs/run6/before/demo/` (committed).
- Real data (:8766): `docs/run6/before/realdata/`, **kept local, never committed** (real names).
  The "/" map screenshots (`*np-map*.png`) are local-only on both servers, because the map shows
  the pipeline's real instructor names even in the demo.
