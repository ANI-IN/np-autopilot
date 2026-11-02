# Test results — 2026-11-02 (run 3 first, then run 2, then run 1) (local Supabase stack, Windows 11, Python 3.12, Chrome)

## Run 3 (polish, graph editing, custom relationships, activity), 2026-11-02

Local Supabase stack (Docker), Windows 11 laptop, Python 3.12, system Chrome
headless (software rendering: no GPU in headless mode). Every number below was
measured on this machine in this run; nothing is estimated.

### Final verification

`bash scripts/verify_all.sh --fresh-clone --reset-db`: **VERIFY: ALL PASS**.

- Fresh clone of the branch, clean `uv` install, byte-compile, all KB ES modules parse: PASS.
- `supabase db reset`, every migration 0001-0029, KB rolled back to 0021 and re-applied: PASS
  (the projection step fails exactly as on `main`; pre-existing, docs/AUDIT.md).
- Lint (now including the run-3 scripts), plugin in sync and valid, no server keys in `public/`,
  `.env` untracked, no secret-shaped strings in history, RLS on every kb table, deploy guard: PASS.
- Full suite: **1203 passed, 22 failed, 21 errors, 53 skipped**; all 43 failures/errors are the
  `main` baseline by name (docs/baseline-failures.txt); **0 new**; every KB test passes.
- The Realtime test skips after the reset (no demo users); after reseeding: **1 passed**
  (presence and a live update over the new `kb.changes` feed in under 3 s).
- The first final run failed one step: a typo in `verify_all.sh`'s own lint file list (a
  literal `
`). Fixed and re-run from the start; the result above is the re-run.
- The Realtime test's cleanup used to delete its probe's audit rows; with the log append-only
  that is refused (as it should be), so the test now removes only the probe record and the
  re-seed clears the history.

### New tests

- `tests/test_kb_run3.py` (23, API and database): one attention definition
  (tile = list = sidebar = Data quality); named actors (system, AI assistant
  for a person, a person; never "Someone"); audit rows cannot be updated or
  deleted by admin or editor; activity visibility enforced in the database
  (admin all, editor own + scope, viewer and contributor none, History still
  works, live feed still flows); activity filters, field diff, cursor, CSV with
  formula-safe cells; relationship types: admin reviewed, editor unreviewed +
  review queue + rename on confirm, contributor proposal only, the database
  refusing editor/contributor writes directly, five near-duplicate spellings
  refused by the service and the trigger, merge with preview and audit; the
  admin-only link (4 roles); tags rename/merge/archive/restore; member removal;
  template rename/restore; relationship change of type; the dashboard cache
  invalidated by a write.
- `tests/test_kb_e2e.py`, 22 new browser tests: every Phase A fix (A1 counts
  agree, A2 named actors, A3 badge slot, A4 popover in the viewport with
  labelled controls and reorder, A5 tooltip + 2-line description + resizable
  columns remembered, A6 Guide centred as one unit + lightbox, A7 sentence
  options grouped by direction that never cover the record input); inline
  relationship creation as admin, editor (then confirmed by an admin in
  Approvals) and contributor (proposal); duplicate relationship type blocked
  with the existing one offered; merge from Settings; graph create → connect
  (handle drag) → rename (double-click) → archive (Delete, impact shown) → Undo
  → move (position saved, record version unchanged); an invalid connection
  rejected with its reason and the line snapped back; two people on one graph
  (a record added by one appears for the other; a stale rename gets the
  conflict dialog); graph keyboard only (N, F, /, Esc); Activity filters, diff,
  search and CSV, and the History tab using the same entries; Activity not
  offered to viewers; the admin-only link (4 roles). Activity added to the
  1024px no-horizontal-scroll and accessible-name sweeps.

### Concurrency: 25 simulated people for 2 minutes (`scripts/kb_load.py`)

5 editors, 15 contributors and 5 viewers, each modelled as its own serverless
instance (its own warm connection, one request at a time, as on Vercel), all
through the real WSGI app (token verification, RLS, triggers). Same-record
conflicts on three "hot" records, parallel graph edits in the shared layout,
and a race to create the same nine relationships.

**LOAD: PASS.** 19,754 requests in 120 s (164/s), **0 server errors (5xx)**.

| Check | Result |
|---|---|
| Duplicate relationships | 0 (the race created exactly the 9 possible; 1,186 attempts got 409 duplicate) |
| Duplicate records | 0 |
| Live relationships pointing at an archived record | 0 |
| Same-record saves | 318 saved, 1,455 refused with **409** (every refusal a 409) |
| Audit rows vs successful writes | record updates 318 = 318; record creates 345 = 345; relationships 9 = 9; proposals 1,198 = 1,198 |

Latency under that load (25 concurrent clients sharing one laptop, one local
Postgres in Docker and one Python interpreter, so it includes queueing):

| Endpoint | Requests | p50 ms | p95 ms | Statuses |
|---|---|---|---|---|
| GET /nodes (list) | 5,400 | 93.8 | 134.8 | 200 |
| GET /search | 1,959 | 84.1 | 119.9 | 200 |
| GET /nodes/{id}/neighbourhood (depth 2) | 1,994 | 117.7 | 159.8 | 200 |
| GET /nodes/{id} | 1,537 | 242.6 | 307.0 | 200 |
| GET /dashboard | 1,152 | 331.0 | 414.4 | 200 |
| GET /counts | 1,209 | 137.8 | 189.4 | 200 |
| GET /activity | 758 | 74.5 | 137.3 | 200 |
| PATCH /nodes/{id} | 1,773 | 314.7 | 423.4 | 200 ×318, 409 ×1,455 |
| POST /edges | 1,195 | 85.8 | 123.2 | 201 ×9, 409 ×1,186 |
| POST /nodes | 1,543 | 136.6 | 326.5 | 201 ×345, 202 ×1,198 (contributor proposals) |
| POST /graph/positions | 1,234 | 106.4 | 152.7 | 200 |

The dashboard is cached per person until the next change; in this test a write
lands every few milliseconds, so it is recomputed almost every time (the worst
case).

Finding on the way (not a production defect, recorded so nobody trips on it):
`web/lib/data.py` keeps ONE warm connection per process, correct on Vercel
(one request at a time per instance) and in the dev servers (they serialise API
calls with a lock). The first load run shared that connection between 25
threads and produced aborted transactions and cross-user identity on the
shared connection; the load script now gives each simulated person its own
connection, as production does. Never run `api/index.py` under a threaded
server without that lock.

### Query plans at 5,000 records / 15,000 relationships (`scripts/kb_explain.py`)

Every SELECT behind each endpoint, EXPLAIN ANALYZE, run as each role under RLS.
Database time per request (sum of its statements):

| Endpoint | Viewer ms | Editor ms | Admin ms | Statements |
|---|---|---|---|---|
| List records | 21.3 | 18.1 | 14.1 | 2 |
| List records, type + name order | 15.3 | 11.6 | 8.9 | 2 |
| Search | 21.9 | 16.4 | 14.8 | 2 |
| Neighbourhood, depth 2 | 20.0 | 15.3 | 12.5 | 4 |
| Dashboard (uncached) | 230.7 | 359.3 | 180.0 | 15 |
| Sidebar counts (uncached) | 87.0 | 88.8 | 67.9 | 3 |
| Activity, newest 50 | 8.3 (sees none) | 154.5 | 3.7 | 1 |
| Activity, filtered | 13.0 | 119.4 | 6.1 | 1 |
| A record's History | 1.6 | 1.2 | 1.3 | 1 |
| Change feed | 0.7 | 0.4 | 0.3 | 1 |

Fixed: the dashboard's completeness by course was one `completeness()` call per
course or program (~5 queries each, ~1,000 statements at this seed): now 3
queries whatever the number of courses. Indexes added in 0029 for the activity
filters (actor, table, and the record ids inside before/after). Sequential
scans that remain are whole-table counts the dashboard and counts must make
(nodes 5,000, edges 15,000, changes 20,000 rows), now behind the cache. The
editor's Activity is the slowest uncached read (155 ms at 20,000 audit rows):
the policy filters by the editor's scope row by row; it grows with the size
of the log and is the first thing to revisit at 10x.

### Latency at 5,000 / 15,000, one client (`scripts/kb_perf.py --runs 30`)

| Request | p50 ms | p95 ms | max ms | runs |
|---|---|---|---|---|
| list: first page (updated) | 23.5 | 25.6 | 28.7 | 30 |
| list: type=topic sorted by name | 21.0 | 24.1 | 27.5 | 30 |
| list: text filter q=caching | 20.1 | 26.6 | 30.1 | 30 |
| search: full text 'consensus' | 26.0 | 34.8 | 39.2 | 30 |
| search: fuzzy 'perf topik 12' | 43.0 | 54.3 | 58.1 | 30 |
| neighbourhood: depth 1, random topic | 18.9 | 21.0 | 21.4 | 30 |
| neighbourhood: depth 2, random topic | 23.8 | 123.8 | 124.8 | 30 |
| neighbourhood: depth 1, 600-edge hub (capped 300) | 120.6 | 125.9 | 135.9 | 30 |
| node detail: hub | 43.2 | 45.8 | 52.0 | 30 |
hub neighbourhood: returned 300 of total 607 (truncated=True)

Same machine as run 2 (list p50 16-19 ms then); list is now 20-24 ms. Reads
did not change in run 3; the difference is within this laptop's run-to-run
spread (an earlier run-3 measurement, with other processes busy, gave 27 ms).

### Graph at 500, 2,000 and 5,000 records (`scripts/kb_graph_perf.py`)

| Nodes | Renderer | Loaded | Load (ms) | FPS, labels (zoom 0.5-1.2) | FPS, no labels (0.2-0.45) | FPS, clustered (<0.16) | Switch to clusters (ms) |
|---|---|---|---|---|---|---|---|
| 500 | canvas | 501 | 545 | 53.8 | 59.7 | 60.0 | 134 |
| 500 | webgl | 501 | 658 | 54.0 | 59.9 | 60.3 | 130 |
| 2000 | canvas | 2001 | 1955 | 21.7 | 21.9 | 57.9 | 496 |
| 2000 | webgl | 2001 | 1493 | 45.3 | 50.1 | 60.1 | 383 |
| 5000 | canvas | 5001 | 4830 | 7.1 | 9.3 | 39.9 | 899 |
| 5000 | webgl | 5001 | 5179 | 13.6 | 21.5 | 59.8 | 1000 |

`Load` = from opening the page to the graph drawn (neighbourhood fetched and
laid out). FPS = frames per second while the view pans and zooms continuously
for 3 s in the zoom band shown. "Switch to clusters" = the one-time cost of
entering cluster mode. Headless Chrome renders in software (no GPU), so these
are floors; a laptop with a GPU does better.

Decisions from these numbers: the Graph page opens with at most 300 records
(the neighbourhood cap; expand loads more). Up to 800 records it uses
Cytoscape's canvas renderer; above that its WebGL renderer (at 2,000 records
WebGL is 45-60 fps against canvas's 22), with straight edges without arrows,
labels only when zoomed in, a texture while moving, and one bubble per type
when zoomed far out (60 fps at 5,000). With labels at 5,000 records it stays
slow (14 fps): that is the limit of drawing 5,000 labelled records at once,
and why the page never loads that many unless asked (`?limit=`).

Before the scale work (same machine, same script): 2,000 records canvas 10 fps
with labels, 5,000 records canvas 0.6 fps; the minimap redrew every record on
every frame (now cached).

## Run 2 (demo → team-ready), final

`bash scripts/verify_all.sh --fresh-clone --reset-db` (13:29–13:45): **VERIFY: ALL PASS**.

- Fresh clone of the branch → clean `uv` install → Python byte-compiles → all KB ES modules parse: PASS.
- `supabase db reset` → every migration 0001–0028 → KB rolled back to 0021 → re-applied: PASS
  (the projection step fails exactly as on `main`; pre-existing, docs/AUDIT.md).
- Lint, plugin copy in sync, `claude plugin validate --strict`, no server keys in `public/`,
  `.env` untracked, no secret-shaped strings in history, RLS on every kb table, deploy guard: PASS.
- Full suite: **1156 passed, 22 failed, 21 errors, 53 skipped**; all 43 failures/errors are the
  `main` baseline by name; **0 new**; all KB tests pass. (The Realtime test skipped there because
  the reset removed the demo users; it passes after reseeding: 1 passed.)
- KB tests by file: API 34, schema 16, RLS 11, concurrency 3, import 7, MCP 8, plugin 5,
  types 10, workspace 11, browser E2E 47, Realtime 1, deploy guard 8.

Browser tests (`tests/test_kb_e2e.py`, 47) run in Chrome under the production security headers:
the 14 run-1 paths updated for the redesign; custom type "Case Study" end to end; one-save create
with nested inline course, 2 relationships, 3 links (Drive, UpLevel, GitHub reused); rollback with
the field highlighted; duplicate warning; disallowed relationships; contributor proposal; archive →
permanent delete; two-user conflict; keyboard-only flows; outline reorder and quick-add; flag →
review; templates; shared saved view + bulk owner; Guide promises (Undo, draft restore, theme);
prefill from context and custom-field columns; no horizontal scroll at 1024px (10 screens);
accessible names on every control (9 screens + the form). Ran green repeatedly.

Performance at 5,000 records / 15,000 relationships (local, 20 runs): list p50 16–19 ms, search
p50 19–32 ms, depth-2 neighbourhood p95 120 ms, hub detail p50 32 ms; dashboard p50 33 ms,
outline 8 ms, quality 15 ms.

Only measured results are stated. Nothing here was run against a shared or
production database.

## Baseline before any change

| Run | Result |
|---|---|
| `main`, no DB (CI-like) | 892 passed, 12 failed, 187 skipped — all 12 Windows-environment failures |
| `main`, local DB | 998 passed, 22 failed, 21 errors, 50 skipped — list in `docs/baseline-failures.txt` (root cause: `project_graph.py` cannot load the committed graph into a fresh DB, `corpus_names_a_file`) |

## Regression check: branch vs `main`, by failing test NAME (run 2, A2, 2026-11-02 12:05)

Both suites ran against the same local stack (Supabase in Docker, migrations through
0026), each from its own git worktree, with the same `.venv`:

| Checkout | Result | Failing/erroring tests |
|---|---|---|
| `main` @ 688f988 | 998 passed, 22 failed, 21 errors, 50 skipped | 43 — **identical, name for name, to `docs/baseline-failures.txt`** |
| branch @ 33a5d48 | 1093 passed, 22 failed, 21 errors, 50 skipped | 43 — **the same 43 names**; 0 branch-only failures, 0 fixed |

So the branch fails nothing that passes on `main`; it adds 95 passing tests. All 43
are pre-existing (root cause: `pipeline/project_graph.py` cannot load the committed
graph into a fresh database, `corpus_names_a_file`; see docs/AUDIT.md).

## KB tests (last run of each file after its final change)

| File | Result |
|---|---|
| `tests/test_kb_schema.py` + `tests/test_kb_rls.py` | 27 passed |
| `tests/test_kb_api.py` + `tests/test_kb_e2e.py` | 44 passed (30 API + 14 browser, E2E under production CSP headers) |
| `tests/test_kb_concurrency.py` | 3 passed |
| `tests/test_kb_import.py` | 6 passed |
| `tests/test_kb_mcp.py` | 6 passed |
| `tests/test_kb_plugin.py` (+ taxonomy guard) | 11 passed |
| Repo guard tests touched by the change (`test_login_flow`, `test_lazy_route_table`, `test_taxonomy_single_source`, `test_pipeline_docs`, `test_documented_constraints_are_enforced`, `test_no_contact_data_in_tracked_files`) | pass |
| CI-like (no DB): KB files | 4 passed, 85 skipped — listed in `tests/ci-skips.yaml` |

## `scripts/verify_all.sh --fresh-clone --reset-db --perf`

| Step | Result |
|---|---|
| Fresh clone of the branch → clean `uv` install → compileall → `node --check` | PASS |
| `supabase db reset` → 25 migrations from 0001 → `down --to 0021` → `up` | PASS (projection step failed as on `main`) |
| ruff (E9 + pyflakes) on all KB code | PASS |
| Plugin server copy in sync; `claude plugin validate --strict` | PASS |
| No server key names / JWTs in `public/`; `.env` untracked; no secret-shaped strings in `git log -p` | PASS |
| RLS enabled and policies present on every `kb` table | PASS |
| **Full suite + regression comparison vs baseline** | **PASS** (re-run 2026-11-02, `bash scripts/verify_all.sh`): 1089 passed, 22 failed, 21 errors, 50 skipped in 6m31s — every failure and error is in `docs/baseline-failures.txt`; all KB tests pass; `VERIFY: ALL PASS` |

## Concurrency (measured)

- Two sessions edit the same record from version 1 → exactly one 200, one 409 with
  the winner's record.
- 20 parallel create+connect (5 racing on one name) → 16 created, 4 refused as
  duplicates, 0 other errors, **283 ms** total; 16 modules ↔ 16 edges (no orphans);
  audit inserts match rows created.
- 20 parallel edge creates racing an archive of the shared endpoint → 0 orphans.

## Performance (synthetic: 5,000 nodes, 15,000 edges; 40 runs each; in-process WSGI incl. token verification and RLS)

| Request | p50 ms | p95 ms | max ms |
|---|---|---|---|
| list: first page (updated) | 16.2 | 18.7 | 20.6 |
| list: type=topic sorted by name | 12.6 | 13.6 | 13.8 |
| list: text filter | 11.7 | 13.2 | 15.1 |
| search: full text | 20.1 | 22.9 | 27.4 |
| search: fuzzy (typos) | 29.8 | 33.3 | 50.0 |
| neighbourhood depth 1 | 14.2 | 18.7 | 20.4 |
| neighbourhood depth 2 | 17.8 | 122.5 | 141.7 |
| neighbourhood of a 600-edge hub (capped: 300 of 607 returned) | 112.9 | 128.7 | 135.4 |
| node detail of the hub | 24.2 | 26.4 | 28.6 |

Laptop → local Docker Postgres. Production adds network latency to Supabase;
these numbers say nothing about capacity under concurrent load beyond the 20-writer test.

## Live checks

- MCP + Claude Code: `claude -p` with the server via `--mcp-config` answered a
  retrieval question from the local KB — **VERIFIED**.
- Live Google Sheets import: **UNTESTED** (no credentials).
- Vercel preview deploy: **NOT RUN** (no token).
