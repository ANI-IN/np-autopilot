# End-to-end test report: autonomous run B (2026-11-07)

Every change in this run, tested end to end. Each row gives the test data, the steps, the
expected and actual result, and any bug found with its fix and retest. There are no real names
or e-mails here. Raw logs and real-data evidence stay local in `.measure/` (gitignored); the
**Evidence** column names the file. A row without evidence is marked **not verified**.

**Test data:**
- **Synthetic:** records created through the API in the local test database. `kb_support`
  resets the kb tables around each test.
- **Real-data copy:** the local `kb_realdata` database, a copy of production, served on :8766.
- **DEV:** the DEV Supabase project (database only).

Production was not touched.

## 1. Graph page (the DEV report: "reading 'forEach'" on load, "reading 'edges'" on Reset)

| # | Scenario | Steps | Expected | Actual | Result | Bug found → fix | Retest | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1.1 | Reproduce locally | Real-data copy, admin, `#/graph`, also with 400 ms latency and 2 MB/s simulated | The error appears | Loads correctly; Reset works | Not reproduced locally | — | — | debug script output (session) |
| 1.2 | Root cause, client side | Read `api()` | A 2xx reply that isn't JSON is an error | `r.json().catch(() => ({}))` turned it into `{}`, so `resp.nodes.forEach` threw | **Bug** | `api()` reads the text and throws "The reply from the server could not be read (HTTP n, size)", logging the status, content type and encoding | 1.4 passes | `public/kb/js/core.js` |
| 1.3 | Likely trigger on Vercel | Payload size on DEV and the local copy (read-only) | — | Whole graph in one reply: 1,597,530 B (241 KB brotli), the largest reply in the app; identical data on DEV and local | — | Whole graph now fetched in pages of 1,000 records (~0.5 MB each, the size of replies known to arrive intact on the preview); each page's shape is checked | 1.5 passes | session output |
| 1.4 | Unreadable reply | Synthetic; the `/graph` reply replaced with HTML | Error box: "could not be read"; toolbar safe | As expected | Pass | — | — | `.measure/suiteB2/test_kb_graph_toolbar.log` |
| 1.5 | Incomplete reply `{}` | Same, with `{}` | Error box: "incomplete" | As expected | Pass | — | — | same |
| 1.6 | Toolbar before or without a graph | Click Reset, Auto-layout, Save view, Connect after a failed load | A toast: "did not load. Use Try again first" | As expected; no confirm dialog opens | Pass | **Bug:** Reset dereferenced a null canvas ("reading 'edges'") → `ready()` guard | Pass | same |
| 1.7 | Try again after a failure | Click "Try again" in the error box | The graph reloads | First run: the click was blocked | Fail, then pass | **Bug:** the empty canvas covered the error box → canvas hidden on failure | Pass | same |
| 1.8 | Paged load | 5 records, `?limit=2` | ≥ 3 `/graph` requests; every record drawn | As expected | Pass | — | — | same |
| 1.9 | Auto-layout then Reset | Admin clicks Auto-layout, then Reset → confirm | Positions saved, then forgotten | As expected (≥ 5 saved, then 0) | Pass | — | — | same |
| 1.10 | Save view | Name it, then Save | The page switches to the new view, with positions saved | First run: stayed on "Shared layout" | Fail, then pass | **Bug:** a `?view=` change did not rebuild the page → rebuild on a view change | Pass | same |
| 1.11 | Connect | Admin: Connect, click two records, pick a relationship, Submit | "Connected"; one relationship in the API | As expected | Pass | — | — | same |
| 1.12 | Real data | Real-data copy as admin: load, Auto-layout, Reset | Paged load, no error, toasts | 3 pages; "Showing 226 record(s) · 2,733 more in 20 bundles"; both toasts | Pass | — | — | `.measure/b/realdata_ui_check.log`, `screens/b-graph-light.png` |
| 1.13 | **On DEV, signed in** | Owner opens `/kb/#/graph` on the preview | Loads | **Not verified.** A signed-in request on DEV wasn't possible this run (no token; minting one was refused) | **Not verified** | If it still fails, the error now says what arrived (status, size) | Owner | — |

## 2. Weeks, workflows and themes retired

| # | Scenario | Steps | Expected | Actual | Result | Bug → fix | Retest | Evidence |
|---|---|---|---|---|---|---|---|---|
| 2.1 | Plan, apply, revert, apply on the real-data copy | `scripts/retire_legacy_sections.py` | Exact counts; revert restores every count | Apply: 92 processes, 16 themes and 20 weeks archived, 112 relationships with them, 20 schedules moved, 39 suggestions exported and cleared, 3 types archived; live records 4,342 → 4,214, relationships 3,097 → 2,985. Revert: all back to the "before" counts | Pass | — | — | `.measure/b/retire_local.log` |
| 2.2 | DEV backup verified by restore | `dev_db.py backup`, then restore into a scratch database, then compare every table's row count with DEV | Identical | 45/45 tables, 188,259/188,259 rows, 0 differences; 62.6 MB with end marker | Pass | — | — | `.measure/b/dev_restore_check.log` |
| 2.3 | Apply on DEV | `apply --remote-ok` | Same counts as 2.1 | Identical to 2.1; 4.9 s | Pass | — | — | `.measure/b/retire_dev.log` |
| 2.4 | Owner suggestions exported outside git | After apply | A local admin-only file; not on the records | 39 rows in `.measure/private/workflow-owner-suggestions-{local,dev}.json`; `git check-ignore` confirms; `suggested_owner` count 0 | Pass | — | — | 2.1 and 2.3 logs |
| 2.5 | Week numbers kept, program-specific, not on modules | After apply | The number on the course→module link with `program: null`; the module unchanged | 20 links carry `schedule.week`; synthetic test asserts the module has no week | Pass | — | — | `tests/test_retire_legacy_sections.py` (3 passed, `.measure/suiteB2/retire2.log`) |
| 2.6 | The sync does not re-create them | Sync preview on the real-data copy after apply | 0 created | created {}, updated {}, conflicts {}; records seen as gone at source (128 records, 112 relationships, 108 source attachments; already archived) | Pass (side effect noted) | The 108 source attachments of the retired records get archived by the next sync. Undo = remove `retired_types` + `revert` + one sync | — | `.measure/b/sync_dryrun_after_retire.log` |
| 2.7 | Refuses production and remote databases | Run with the production ref, and with a remote host without `--remote-ok` | Exit 2, "refused" | As expected | Pass | — | — | test 2.5 file |
| 2.8 | Types gone from the API | `/api/kb/types` on the real-data copy | No week, process or theme | `program, domain, course, module, session, topic, instructor, team_member` | Pass | — | — | `.measure/b/realdata_ui_check.log` |
| 2.9 | Script crashes on a database without one of the types | Test database has no "theme" type | Counts work | Crashed (`None[0]`) | Fail, then pass | **Bug** → tolerate a missing type | Pass | 2.5 |
| 2.10 | Report path for a file outside the repo | Synthetic test with a temporary folder | The path is reported | `relative_to` raised | Fail, then pass | **Bug** → only relativise inside the repo | Pass | 2.5 |

## 3. Map and workspace cleanup

| # | Scenario | Steps | Expected | Actual | Result | Bug → fix | Retest | Evidence |
|---|---|---|---|---|---|---|---|---|
| 3.1 | Old `?week=` links | `/?week=10`, `/?week=10&domain=x` | No week filter; address rewritten | As expected | Pass | — | — | `.measure/suiteB2/test_kb_map_switch.log` (15 passed) |
| 3.2 | Timeline view gone | `/?view=timeline` | Map opens; no timeline button; address rewritten | As expected | Pass | — | — | same |
| 3.3 | Retired types in old links | `/?types=program_week,workflow,theme,module` | Map works without them | As expected | Pass | — | — | same |
| 3.4 | Map admin button | Admin vs viewer on `/` | Admin: "Admin →" to `/kb/#/admin`, at the top; viewer: hidden | As expected | Pass | — | — | same, plus `.measure/b/realdata_ui_check.log` |
| 3.5 | Workspace timeline retired | `#/timeline`, `#/program-timeline` | Redirect to Programs; `/api/kb/views/timeline` 404 | As expected | Pass | — | — | `tests/test_kb_redirects_run6.py` (verify_all), real-data check |
| 3.6 | Map on real data | `/?week=10` on :8766 | No week filter, timeline or "Programme week" text | As expected | Pass | — | — | `.measure/b/screens/b-map.png` |

## 4. Navigation shell and visual direction

| # | Scenario | Steps | Expected | Actual | Result | Bug → fix | Retest | Evidence |
|---|---|---|---|---|---|---|---|---|
| 4.1 | Navigation by role | viewer, contributor, editor, admin | Browse identical for all; Admin group only with the role's items, at the bottom; no "Graph" in Browse; Map → `/` | As expected for all 4 | Pass | Test-ID collision (group vs Overview link) → `nav-admin-group` | Pass | `.measure/suiteB2/test_kb_shell.log` (13 passed) |
| 4.2 | Graph editor admin-only | viewer, contributor, editor: `#/graph`; API `POST`/`DELETE /graph/positions` | "Admins only"; no "Show in graph" button; API 403; admin 200 | As expected | Pass | **Bug:** a slow Home could draw over "Admins only" (router counter not bumped) → fixed | Pass | same |
| 4.3 | Members and Sources & sync server-side | `GET /api/kb/sync` per role | 403 unless admin | As expected | Pass | — | — | same; `tests/test_kb_access_sweep.py` |
| 4.4 | Admin overview | admin, contributor | 7 and 2 cards | As expected | Pass | — | — | same |
| 4.5 | Theme toggle | Follow system dark/light; click Light, Dark (persist on reload), System | System by default; an explicit choice wins; persisted | As expected; dark = `rgb(11,18,32)` | Pass | — | — | same |
| 4.6 | Home and search | Synthetic: 7 topics; type "hashing", Enter; See all; open a hit; recent chip; no results | Search-first above cards; 5 per group then "See all"; type filter; the record opens beside the results | As expected | Pass | — | — | same |
| 4.7 | AA contrast | light and dark: Home, Search, All records, Admin | Every chip, filter chip, badge, count and group label ≥ 4.5:1 | 0 below 4.5 | Pass | — | — | same |
| 4.8 | Focus ring on Home's search box | `test_every_tab_stop_shows_a_focus_ring[#/]` | Visible ring | None | Fail, then pass | **Bug** → ring on the input | Pass | `.measure/suiteB2/test_kb_ui_run6_final.log` (36 passed) |
| 4.9 | Keyboard: Ctrl K from Home | Palette search, open, menu, Settings | Palette keeps focus | Home's autofocus stole it | Fail, then pass | **Bug** → autofocus only when nothing has focus | Pass | same |
| 4.10 | One radius set | Stylesheet check | No new literal radii | 12px and 999px | Fail, then pass | **Bug** → `--radius-lg`, `--radius-pill` tokens | Pass | same |
| 4.11 | Real data, light and dark | :8766 Home, Search, Admin | Renders; grouped results | As expected | Pass | **Bug (visual):** 4 nav icons not in the icon sprite → existing icons used | Screenshot retaken | `.measure/b/screens/` |

## 5. Crawling (read-only)

| # | Scenario | Steps | Expected | Actual | Result | Notes | Evidence |
|---|---|---|---|---|---|---|---|
| 5.1 | Registry and linked Sheets | Service account, read-only | Every link read or recorded | 3 sheets, 41 tabs, 2,940 rows, 64 links (47 targets) | Pass | `KB_SHEETS_ID` is empty in `.env` (id taken from the registry doc); the **Sheets API is disabled** in the service account's project → read through Drive's read-only export instead | `.measure/inventory/sheets_drive_inventory.md` |
| 5.2 | Drive folders, recursive | 27 folders | Full tree | 2,890 sub-folders, 10,261 files, 51.3 GB, 2021-08-10 → 2026-11-07; cap 30k not reached | Pass | — | same |
| 5.3 | Access failures recorded | — | Every failure listed with a reason | 38: 20 links 404/not shared, 18 shortcut targets missing | Pass | Nothing skipped silently | same; redacted: `docs/operations/sources-inventory-2026-11-07.md` |
| 5.4 | KYP pages, 5 starting points | GET only | Structure, includes, attachments listed | 182 pages; 53 include targets resolved; 1,635 attachments listed (not downloaded) | Pass | Search 403 and user lookup 403 (token scope); the newer attachments API returns 401 (the older one works) | `.measure/kyp/kyp_structure.md` |
| 5.5 | KYP pilot into staging | Applied Agentic AI → `.measure/staging/` (local files, not the live graph) | Entities with provenance; "[Do not Use]" and attachments listed | 6 programs, 4 courses, 66 module variants, 337 topics, 102 tool concepts, 205 resources; 1 page and 45 attachments skipped and listed | Pass | Quality: `docs/design/kyp-structure-and-model.md` §5 | `.measure/staging/kyp-applied-agentic-ai/quality.md` |

## 6. Suites

Run on the final code, one browser file at a time with ≥ 2.5 GB free; the graph file ran one
test per process. **No test hung.**

| Suite | Result | Evidence |
|---|---|---|
| graph toolbar (new) | 6 passed | `.measure/suiteB2/test_kb_graph_toolbar.log` |
| shell (new) | 13 passed | `.measure/suiteB2/test_kb_shell.log` |
| retire script (new) | 3 passed | `.measure/suiteB2/retire2.log` |
| e2e | 71 passed | `.measure/suiteB2/test_kb_e2e.log` |
| UI | 36 passed | `.measure/suiteB2/test_kb_ui_run6_final.log` |
| map switch | 15 passed | `.measure/suiteB2/test_kb_map_switch.log` |
| perf budget | 10 passed | `.measure/suiteB/test_kb_perf_budget.log` |
| Realtime gap / Realtime / propagation / console | 1 / 1 / 1 / 2 passed | `.measure/suiteB/` |
| graph (one test per process) | 11 passed | `.measure/suiteB/graph__*.log` |
| Map default view, redirects, taxonomy rule, sign-in CSP (after fixes) | 141 passed | `.measure/suiteB2/fixes5.log` |
| Re-run after the last map/icon changes: map switch, shell, propagation, console, perf | 15, 13, 1, 2, 10 passed | `.measure/suiteB3/summary.txt` |
| Real-data UI check (final code) | 15/15 | `.measure/b/realdata_ui_check.log` |
| DEV preview after deploy (`c8b5e4f`) | 7/7 smoke tests (config 200, /kb/ 200, me 401, cron 401, no local-login 404, new module served, dub1); the served CSP allows both map inline scripts | `.measure/b/smoke.log` |
| `verify_all --skip-browser` (final) | **ALL PASS**: 1,338 passed, 13 failed (= the known `main` baseline), 50 skipped | `.measure/suiteB3/verify.log` |

## 7. Found by the full check and fixed

The first `verify_all` run flagged 5 new failures, all caused by this run's changes:

- the alias table: 2 new redirects needed test cases;
- the taxonomy rule: 2 literals in new files;
- 3 map default-view tests: themes and workflows still drawn from older data, and `DEFAULT_TYPES` still listed them, so a reloaded link didn't match.

The map now drops the retired types where its data arrives (`mergeGraph`), for any data source. All are fixed, and the final run passes.
