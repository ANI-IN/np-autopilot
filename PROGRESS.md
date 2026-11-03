# PROGRESS — autonomous run

T0 = Mon 2026-11-02 02:58 (local clock). Mode: **DEGRADED** (no Supabase dev
project, Google, LLM or Vercel credentials in the environment; local Supabase stack
via Docker used for everything).

## Log

- [T+0:00] Phase 0 start. Cloned, branch `auto/knowledge-platform-20261102`. Python 3.12 + uv,
  Node 26, Docker 29 (daemon started), Supabase CLI via npx (pinned 2.118.0), Chrome present.
- [T+0:03] Credentials (presence only): all Supabase/Google/Anthropic/Vercel vars missing → DEGRADED.
- [T+0:08] Baseline (no DB): 892 pass / 12 fail / 187 skip — all 12 are Windows-environment failures.
- [T+0:12] Local DB seeded; `project_graph.py` FAILS on a fresh DB (`corpus_names_a_file`) — pre-existing.
- [T+0:15] M1+M2 done | tests: 27 pass / 0 fail | VERIFIED | kb schema 0022, RLS 0023
- [T+0:18] Baseline (DB, main): 998 pass / 22 fail / 21 error / 50 skip → docs/baseline-failures.txt
- [T+0:18] M3 done | tests: 29 pass / 0 fail | VERIFIED | service + /api/kb
- [T+0:34] M4-M6 done | tests: 13 E2E pass / 0 fail | VERIFIED | UI, conflict dialog, graph
- [T+0:36] M7 done | tests: 3 pass / 0 fail | VERIFIED | 20 parallel creates 283 ms, no dupes/orphans
- [T+0:39] M8 done | tests: 6 pass / 0 fail | VERIFIED (fixture) / live Sheets UNTESTED (no creds)
- [T+0:45] M9 done | tests: 6 pass / 0 fail | VERIFIED incl. live `claude -p` retrieval through the server
- [T+0:48] M10 done | `claude plugin validate --strict` pass, 5 tests | VERIFIED
- [T+0:55] Stretch: data-quality dashboard + CSV export (tests pass). E2E now runs under production CSP.
- [T+1:00] Perf (5,000 nodes / 15,000 edges): see docs/TEST_RESULTS.md.
- [T+1:05] Phase 4: verify_all.sh — clone, reset-DB migrations, lint, plugin, security, RLS all PASS; full-suite step stopped by the low-memory reaper (not re-run, per the reaper notice). Handoff written.
- [re-run] `bash scripts/verify_all.sh`: full suite 1089 pass / 22 fail / 21 error / 50 skip — all failures baseline, no regressions, VERIFY: ALL PASS.
- [demo, 2026-11-02] Local demo: migration 0026 (domain/week/session types,
  resource kinds, kb.link_checks, kb.people()), owner shown and editable in the
  record panel, Data quality lists unowned records and broken links, demo server
  with a local-only sign-in page, re-runnable fictional seed. Fixed: Settings →
  Roles showed other members as uuids (profiles are self-only under RLS); the
  tests' reset() left kb.import_runs behind, failing the import test on a re-run.
  KB tests: 95 pass, incl. 14 browser E2E.

- [run 2 T+0:00 11:44] Run 2 start (demo -> team-ready). docs/SPEC.md absent; backups/ absent.
- [T+0:10] A1 verify_all.sh rewritten (set -euo pipefail, git root, every tool/path/exit checked) | proven: wrong cwd, foreign repo, missing tool, bad option all FAIL (exit 2) | VERIFIED
- [T+0:10] A3 main_results.txt, verify_main.sh deleted | VERIFIED
- [T+0:12] D8 tests/test_deploy_guard.py (6 tests: .vercelignore, excludeFiles, routes, public/, shipped python, prebuilt output) | 6 pass | VERIFIED
- [T+0:20] A2 main vs branch by failing NAME: identical 43 = baseline; branch +95 passes, 0 new failures | VERIFIED
- [T+0:20] B inventory: docs/INVENTORY.md, 42 before screenshots (1440/1280/1024) + 6 dialogs | VERIFIED
- [T+0:30 12:14] Backend for C2/C3/C4/D1/D3-D6 (0027, typedefs.py, workspace.py, routes, MCP list_types) | 108 KB API tests pass (+21 new) | VERIFIED (API); UI next. Commit 11633a1
- [T+1:25 13:10] C1 redesign (tokens, components, every screen rebuilt as ES modules; Inter + Lucide self-hosted), C3 one-step New record sheet, C4 UI (Archived, typed delete, bulk bar, undo), C5 Guide page, D1 Outline, D2 Realtime client + presence (polling fallback), D3 flags UI, D4 templates UI, D5 completeness UI, D6 saved views | E2E 32/32 twice (14 updated + 18 new) | VERIFIED; 0028 palette + realtime publication
- [T+1:30 13:14] Sheets import custom fields (props), rule misfits on Data quality, phase-D browser tests | 36 E2E | VERIFIED
- [T+1:40 13:24] Custom-field columns, New record prefilled from context, Guide links from empty states, resource completeness, accessible-name sweep, plugin 0.2.0 | 47 E2E | VERIFIED
- [T+1:45 13:29] Final verify_all --fresh-clone --reset-db started (migrations 0001-0028 on a fresh DB: PASS; static/security/deploy guard: PASS)
- [T+2:05 13:50] FINAL: verify_all --fresh-clone --reset-db ALL PASS; full suite 1156 pass, 43 = main baseline, 0 new; realtime 1 pass after reseed; after-screens 1440/1280/1024 + dark, no issues | VERIFIED. Handoff written; demo reseeded; demo server + local Supabase left running.

## Decisions

- D1. APPENDIX was not pasted (placeholder only). The wrapper's must-ship list is the spec.
- D2. Repo is Python + static HTML, not a JS framework → vanilla JS UI, Cytoscape, Python MCP SDK
  (PLAN.md "Adaptation").
- D3. Authored knowledge in a new `kb` schema; the projection (`public.nodes`, rebuilt per build)
  is untouched → the live app cannot break.
- D4. Did NOT read `~/Desktop/Keys.txt` or the Desktop DB-URL file: outside the repo, not offered
  for this run, and the URL is the production pooler by its name.
- D5. Auth: kept production Google SSO (already domain-restricted). Did not add email/password
  login: it would weaken the verified-`hd` model. Local tests use real HS256 verification with a
  test-only secret.
- D6. Realtime → RLS-scoped change feed polled every 4 s (CSP `connect-src 'self'`, no
  supabase-js). Realtime + presence → ROADMAP.
- D7. MCP server is an HTTP client of /api/kb with per-user `ikkb_` tokens (migration 0025 lets
  `authenticated` call the definer function) — no DB credential on user machines.
- D8. Skills live in `plugins/ik-knowledge-assistant/skills/`, NOT repo-root `skills/`: the repo
  root is the `np-autopilot` plugin (marketplace source `./`), which would auto-load root skills.
- D9. Courses/programs are container node types; resources a separate many-to-many table.
- D10. Import duplicates against app records are flagged, never adopted automatically.
- D11. Test users are `kbtest-<role>@interviewkickstart.com` (not `synthetic-…`, which
  `test_role_boundary` counts).

- D12. Demo sign-in is a page in the eval/ demo server (never deployed), using the
  LOCAL Supabase Auth's password grant; tokens are then verified by the
  production code path. No change to production login.
- D13. Link health is checked by the client (MCP `check_broken_links`) and only
  RECORDED by the server (`POST /quality/link-results`, editor+). The server
  never fetches user-supplied URLs (no SSRF surface on Vercel).
- D14. Link results live in `kb.link_checks`, not on `kb.resources`, so a check
  never bumps a resource's version and causes a spurious edit conflict.

- D15. docs/SPEC.md does not exist in the repo; the run-2 brief is the specification.
- D16. backups/ does not exist (it is gitignored) -> D7 real-data rehearsal BLOCKED.
- D17. Frontend stays vanilla JS with no build step, split into ES modules (CSP script-src 'self'
  allows same-origin modules). A framework would add a toolchain the repo and Vercel setup do
  not have, for a UI of ~10 screens; see docs/DESIGN_SYSTEM.md.
- D18. No IK brand colour is recorded anywhere in the repo -> restrained deep blue accent.
- D19. Contributors' record creates become proposals (brief C3). Enforced in the database:
  0027 tightens kb.nodes INSERT to editor+. Contributors still edit, connect and attach.
- D20. UpLevel link kind uses uplevel.interviewkickstart.com, found in the repo's own data
  (tests/test_source_links.py, docs/ACCEPTANCE-CHECKLIST.md), not guessed.
- D21. Link kind (the service: Drive, GitHub, UpLevel...; configurable, URL-pattern detected)
  and resource kind (what it is: KYP slides, recording, solution...) are separate dimensions.

- D22. Hover actions fade by opacity, not visibility, so they stay keyboard-reachable.
- D23. Realtime is opt-in per deployment: /api/kb/realtime returns a socket config only when
  KB_REALTIME_ORIGIN (the origin also in the CSP connect-src) is set; otherwise the page polls.
  The local demo derives the origin from `supabase status`.
- D24. Type colours: one accessible, non-purple palette (0028 moved the seeded colours; admin
  choices are kept). Dark mode lightens icon colours with color-mix for contrast.

## Blockers (each with the unblock step) — see HANDOFF.md "Action required"

- Live Sheets import: needs `KB_SHEETS_ID` + `NP_DRIVE_SA_KEY` with the sheet shared read-only.
- Shared DB migration: needs a dev Supabase project URL (SUPABASE_ENV=dev) or owner-run commands.
- Vercel preview: needs VERCEL_TOKEN or the Git integration on this branch.

## Run 3 log (T0 = 2026-11-02 21:18)

- [T+0:47] A1 one attention definition (workspace.attention_counts; /counts for the sidebar) | test_kb_run3 + e2e a1 | VERIFIED
- [T+0:47] A2 named actors (0029 'system' default, kb.actor_emails, activity.label_actors); realtime test cleans its own rows; seed + reset truncate kb.changes too | run3 + e2e a2 | VERIFIED
- [T+0:47] A3 demo badge in its own sidebar slot above the user menu | e2e a3 | VERIFIED
- [T+0:47] A4 View popover (core.popover, viewport-clamped, density radiogroup, column checkboxes, drag + arrow reorder); stray tabs scrollbar hidden | e2e a4 | VERIFIED
- [T+0:47] A5 tooltip on every truncated text (core.el), 2-line description, resizable columns | e2e a5 | VERIFIED
- [T+0:47] A6 Guide centred as one unit (760 + 220), click to enlarge | e2e a6 | VERIFIED (crop: screenshots retaken at the end)
- [T+0:47] A7 relationship combobox (relpicker.js) with sentences grouped by direction, side by side with the record picker | e2e a7 | VERIFIED
- [T+0:47] B2 inline relationship types (admin reviewed / editor unreviewed + review proposal / contributor proposal; DB policies), rel_stem duplicate guard (DB trigger + service), merge with preview, archive shows dependants and offers merge | run3 (8) + e2e b2 (5) | VERIFIED
- [T+0:47] B3 graph editing: create (dbl-click, N), connect (handle drag, picker, Create relationship), invalid pair reason + snap back, inspector for edges, rename in place with 409 dialog, Delete → impact → archive + Undo, move + saved positions per layout, auto-layout/reset, saved graph views, filters (type, relationship, owner, course/program), search, keyboard, live sync (row-level), presence ring | e2e b3 (3) + existing graph tests | VERIFIED (perf numbers pending, Phase C)
- [T+0:47] B4 Activity page + History tab share activityEntry; DB: audit append-only trigger, editor scope policy, kb.record_history for others, kb.changes feed for live updates | run3 (3) + e2e b4 (2) | VERIFIED
- [T+0:47] B5 /me admin_links (server role) → sidebar + user menu | run3 + e2e b5 (4) | VERIFIED

Decisions (run 3):
- D25. Viewers/contributors no longer read kb.audit_log (B4: "others see only a record's History tab"). Live updates moved to kb.changes (no row content), which every member reads; Realtime publishes kb.changes instead of kb.audit_log. test_kb_api's dashboard assertion updated accordingly (viewer recent = []).
- D26. A write with no verified user and no declared actor is 'system' (was 'human' with a null id → "Someone").
- D27. Audit immutability: a BEFORE UPDATE/DELETE trigger refuses unless the current role is a superuser (none on Supabase, postgres included), on top of the missing grants. Local resets use TRUNCATE.
- D28. Editor scope for Activity = records they own or co-own, everything placed inside them (contains edges, scope), links they own, and their own actions.
- D29. Relationship-type near-duplicates: kb.rel_stem (case, spacing, punctuation, plural and -ed/-ing/-es endings) compared against every live label AND inverse; enforced by a trigger and pre-checked by the service so the UI can offer the existing type.
- D30. Graph renderer: Cytoscape canvas (already vendored, 3.34.4); its WebGL mode is used for very large neighbourhoods. Measured numbers in docs/TEST_RESULTS.md.
- D31. Dialogs can stack (opts.stack): New relationship type opens on top of Connect without losing it.
- [T+1:10] B2 CRUD completed: tags rename/merge/archive/restore, member removal, template rename/restore, relationship change of type | run3 (+5) | VERIFIED
- [T+1:10] C caching (dashboard/counts/types per caller until the next kb.changes id), lazy graph library, N+1 in course completeness removed (~1,000 -> 3 queries), EXPLAIN pass (scripts/kb_explain.py) | run3 cache test + EXPLAIN | VERIFIED
- [T+1:10] C 25 people x 2 min (scripts/kb_load.py): 19,754 requests, 0 5xx, 0 duplicates/orphans, 1,455 409s, audit = writes | LOAD: PASS | VERIFIED
- [T+1:10] B3 scale (scripts/kb_graph_perf.py): canvas vs WebGL at 500/2,000/5,000; WebGL above 800, haystack edges, label hiding, clustering, cached minimap | measured | VERIFIED
- [T+1:14] Guide screenshots retaken cropped (scripts/kb_guide_shots.py); run-3 screenshots 1280-3840 @1x/2x, sweep 0 problems | VERIFIED
- D32. Graph renderer: Cytoscape canvas up to 800 records, its WebGL mode above (2,000 records: 45-60 fps WebGL vs 22 canvas, headless software rendering).
- D33. The load test models each person as its own instance with its own connection: web/lib/data.py's single warm connection is per process (Vercel: one request at a time per instance; dev servers lock). Sharing it between threads breaks transactions and identity; never run api/index.py threaded without that lock.
- [T+1:58] Final: verify_all --fresh-clone --reset-db ALL PASS (1203 passed; the 43 main-baseline failures by name; 0 new). Realtime test 1 passed after reseed. First final run failed on a typo in verify_all's lint list (literal \n), fixed and re-run. | VERIFIED
- [T+1:58] Realtime test cleanup no longer deletes audit rows (append-only log refuses it; the demo seed truncates). A proposal to let the table owner bypass the append-only trigger was NOT made: the log stays append-only for every non-superuser role.

## Real-data run log (T0 = 2026-11-03 00:48)

- [T+0:00] Step 0: pg_dump (postgres:17 image, URL passed as a container env var, files written with -f to the mounted backups/): schema 41,935 B, data 17,264,682 B, both UTF-8 without BOM, 18 COPY blocks = 18 tables; row counts equal production's (node_sources 39,414; edges 12,189; nodes 8,496; node_layout 3,707; files 1,524; people 20; profiles 7; others as dumped). PROD_READONLY_DB_URL line removed from .env. | VERIFIED
- D34. Real data goes into a SEPARATE database `kb_realdata` in the same local Postgres (54322), served by its own process on 8766 with its own local-only sign-in; the demo database, its auth users and the 8765 server are untouched.
- D35. No placeholder auth users are needed: production's public tables have NO foreign key to auth.users (profiles keys on user_id with no constraint). auth.uid() and the 0015 sign-up trigger are the only auth dependencies; the real-data database gets a minimal auth schema (users table + uid/role/jwt functions) so they resolve.
- [T+0:10] Step 2 restore into kb_realdata: production schema, then data with user triggers off during COPY (FKs enforced), grants copied from migrations 0001-0021 (the dump has none, --no-privileges). 18/18 tables equal production's counts. | VERIFIED
- [T+0:12] Step 1 drift: production public schema vs migrations 0001-0021 built fresh: 0 differences (126 columns, 59 constraints, 36 indexes, 8 functions, 9 triggers, 17 policies, RLS on 18 tables); production records 0001-0021, checksums equal the files. Not comparable from this dump: privileges (dumped --no-privileges) and objects outside public (the 0015 trigger on auth.users). | VERIFIED
- [T+0:14] Step 3 rehearsal: migrate up 0022-0029 on kb_realdata, down to 0021, up again: all clean, ~1 s each way; the 18 public tables untouched (only np_schema_migrations 21 -> 29). Findings: (a) no supabase_realtime publication in a plain database, so 0028/0029 skip it here (on dev/prod they publish kb.changes); (b) kb.memberships starts EMPTY: every one of production's 7 profiles is a KB viewer through kb.role()'s fallback, and production's 2 site admins are NOT KB admins until pipeline/kb_admins.py runs (HANDOFF step 3); (c) seeded configuration is audited as 'system'. | VERIFIED
- [T+0:16] Step 3 rehearsal problems recorded (see MIGRATION_REPORT). Step 4: root cause of the 43 baseline failures = project_graph.py registered cited files and domain folders only from the untracked .drive-cache crawl manifest; on a fresh checkout every content-graph citation lost its file and corpus_names_a_file (correct) refused it. Fix: _file_rows(graph) registers every cited path (path only, no invented metadata; crawl rows still win), folders registered regardless of the cache, and a corpus citation without a registered file is now a loud SystemExit. Fresh projection now loads and reproduces production's counts exactly (nodes 8,496; edges 12,189; node_sources 39,414; node_layout 3,707). Suite: 27 of the 43 now pass; 16 baseline failures remain (none KB). | VERIFIED
- [T+0:16] 3 new failures came from this run's own files and were fixed properly: backups/ added to pass 1 SKIP_DIRS and .vercelignore (it holds real data); importer listed in pipeline/README.md; its mapping moved to config/kb-projection-mapping.yaml and checked against taxonomy.yaml at start (no taxonomy literals in code).
- [T+0:24] Step 5/7 import (pipeline/kb_import_projection.py): preview = apply = 5,741 records, 6,938 relationships, 1,827 links, 10,434 attachments; re-run creates 0 (5,741 records, 1,515 links, 6,938 relationships found existing); an app edit inside a rolled-back transaction is kept (kept_app_edits 1). Bug found and fixed on the way: recording imported_version with a separate UPDATE bumped version past it (stamp trigger), so every record looked "edited in the app" on re-run; now recorded in the same write. | VERIFIED
- [T+0:24] Step 6: backups/ik_workbook.xlsx does not exist -> skipped (no Sheets mapping change).
- D36. Projection edges are one row per piece of evidence (6,271 covers_topic rows = 2,770 pairs): one KB relationship per pair; teaches role/class dates kept in the relationship note.
- D37. not_a_topic rows (36, marked by the pipeline as a person's name or bio) are REJECTED, never imported; same-name topics merge (220); other same-name records are kept apart with "(2)" and needs_review (2).
- D38. Owners: the projection names owners as people (person nodes, workflow suggestions), never as sign-in accounts, so KB owner_id stays empty for all records; ownership is kept as "owned by / supported by / delivered by" relationships to Team member records.
- [T+0:30] Step 8: local admin + eval/kb_realdata_server.py on 8766 (own sign-in against kb_realdata's auth.users, per-process HS256 secret, loopback only). Step 9: eval/kb_realdata_check.py PASS (5 programs: placement = projection, All records count, panel relationships, graph <=300 records at 60 fps; dashboard = import report). Step 10: request path already on the transaction pooler; added db.assert_transaction_pooler (refuses 5432 / direct host for SUPABASE_DB_URL_TRANSACTION), tests/test_db_pooling.py, DEPLOYMENT.md "Connection pooling". | VERIFIED
- [T+0:52] Final suite: 1,240 passed, 13 failed, 52 skipped; 0 new vs main baseline; 30 of 43 baseline failures pass (3 of them failed in the previous run: unstable). Demo re-seeded. | VERIFIED

## Run 5 log (T0 = 2026-11-03 02:59)

- [T+0:05] Read NP Autopilot's map (public/index.html adaptNode/model/currentInstructors) and ran it on :8766 against the old tables: domains 4+42, modules 20+904 (721 legacy without a domain), instructors 25+1,886, programmes 42 (older sheets), 57 role edges (P 23, B1 20, B2 11, B3 3). Dev DB precondition: project ref != production, agrees with DEV_SUPABASE_URL. | VERIFIED
- D39. "Legacy" follows NP Autopilot exactly: module without domain_slug; domain offering no current module; instructor not at either end of a current-mastersheet edge; every programme (older sheets). Other types are not split by NP and are not split here.
- D40. Topics are NOT merged by name any more (NP shows 2,770 distinct topics). Name uniqueness is kept by scoping a topic to its only module; remaining same-name pairs are kept apart with "(n)".
- [T+0:21] web/lib/kb/sync.py = the import/sync engine (desired state from the old tables -> diff vs kb.sync_map -> write only changes; conflicts; removed-at-source; batches + time budget; one run at a time). pipeline/kb_import_projection.py is now its CLI. kb_realdata rebuilt with 0030 and imported: 25,226 units created in 113 s; re-run 4.4 s, 0 writes (idempotent). | VERIFIED
- D41. P/B1-B3 come ONLY from the current mastersheet (`taught_by`, tier mastersheet, `instructor_role`), as in NP. The first engine run mixed in the older sheets' `role` (1,822 "primary") because the KB keeps one relationship per pair; fixed by keeping it as `older_role`. Matrix now P 23 / B1 20 / B2 11 / B3 3 = NP exactly; the fix went out as an incremental run (2,239 relationships updated, nothing else). | VERIFIED
- D42. A module with two mastersheet primaries: the first (by edge id) is the owner, the other primary and then B1-B3 (in order) are backups. Domains: owned_by -> owner record; supported_by -> backups.
- D43. Schedule: the database's pg_cron + pg_net call /api/cron/kb-sync (Bearer KB_SYNC_SECRET); the function runs one time-boxed batch (KB_SYNC_BUDGET_SECONDS, default 10 < maxDuration 15) and the next tick continues. Vercel Cron was rejected: it fires only on Production deployments, so it cannot drive the dev preview, and Hobby limits it to daily.
- D44. 7 of the 42 legacy domains are NOT archived: 25 current instructors' declared expertise (`sme`, 23 links) points at them, and archiving a domain archives its relationships (cascade). The brief's "never archive anything also connected to current items" wins over "archive the 42"; the 7 are listed by id in docs/PARITY_REPORT.md and stay tagged legacy (hidden from default views anyway).
- [T+0:36] Parity: eval/kb_parity.py reads NP's own model() in the browser on :8766; every category, the 57 role edges (P 23 / B1 20 / B2 11 / B3 3) and the 20 owners-by-role match; only difference = 37 topics rejected by the import's shape rules (explained). docs/PARITY_REPORT.md written. | VERIFIED
- [T+0:36] Legacy step: 874 archived (35 domains, 166 modules, 673 instructors); twice archive -> restore gave back 5,961 / 6,941 / 10,437 exactly. Bug found and fixed on the way: restoring one record at a time lost 1,071 relationships between two legacy records (the cascade restores a relationship only when both ends are live); restore is now ONE update statement. kb_realdata was rebuilt to undo the loss. | VERIFIED
- [T+0:36] tests/test_kb_sync.py: 21 tests, one per rule, on a synthetic source schema. While writing them, the first attempt let the sync add optional fields to the shared test DB's core types; fields can never be removed (trigger), so they were ARCHIVED (hidden; the demo looks as before) and process.allowed_parents put back to {}. The tests now pass a mapping that leaves core types alone. | VERIFIED
- [T+0:36] Live proof on :8766 through "Sync now" (eval/kb_sync_proof.py): change, add, remove, conflict with an app edit, then undo: PASS. The made-up row stays flagged "removed at source" (never deleted) until kb_realdata is rebuilt at the end. | VERIFIED
- [T+0:57] Dev database (Part 6): ref != production, agrees with DEV_SUPABASE_URL; backup into backups/ (it was empty); migrations 0001-0031 applied; run 5's two rolled back and re-applied, and (still empty) the whole chain 31 down / 31 up; old tables loaded from backups/prod_data.sql (13 projection tables, 65,598 rows; no user/account tables); first import as operator, legacy step, one sync; `scripts/dev_db.py verify`: every count and the parity numbers equal :8766; 25 kb tables with RLS. Admin: dev has no users -> morning step. | VERIFIED
- D45. The first import on dev hit 175 ms round trips: ~100k statements would have taken ~5 h (and the same for production's first import from a laptop). Creation is now set-based (ids made client-side, pipelined executemany, bulk read-back, prefetched lookups; legacy archive in 3 statements): local import 113 s -> 18 s, dev 245 s. Updates stay row by row (they are the few changed rows).
- D46. Operator mode for a database with no admin yet: `kb_import_projection.py --operator`; honoured only when the connection OWNS kb.nodes (already above RLS) and asks for it in its transaction; request connections (`authenticated`) can never qualify. Tested both ways.
- D47. Preview deployments sit behind Vercel Deployment Protection: the scheduled call also carries the "Protection Bypass for Automation" secret when Vault holds `kb_sync_vercel_bypass`. The local :8766 server binds 127.0.0.1 with a Host check, so pg_cron in Docker cannot reach it: the schedule was proven in two legs (install/remove creates the right job; the real :8766 cron route runs a 'cron' sync with the secret, 401 without).
- [T+1:10] STOPPED before Finish: Claude Code killed every background process for low system memory: the full verify_all (during the pytest suite; every static, security and RLS check before it had passed), the demo server (:8765) and the real-data server (:8766). Per the notice they were NOT restarted automatically. Not committed, not pushed: the brief requires a full verify_all pass first. Targeted tests passed beforehand: 149 in the affected KB test files and 24 in tests/test_kb_sync.py. The demo database may be mid-test: re-seed it (`eval/kb_demo_seed.py`) once the suite has run.
- [10:36, resumed on the user's go-ahead] Full verify_all: 1,263 pass / 14 fail / 52 skip; ONE new failure vs main: test_replace_all_switch_conditions_are_still_false, a tripwire asserting "pg_cron is not installed" as a proxy for "nothing schedules the projection". Migration 0031 installs pg_cron for the kb-sync job only. | VERIFIED
- D48. That tripwire now checks its stated condition instead of the proxy (as it already does for audit tables): pg_cron may exist, but any cron job other than `kb-sync`, or a kb-sync command that does anything but call /api/cron/kb-sync (project_graph / truncate / delete / insert), fails. The KB sync only READS public.nodes/edges/node_sources (grep: no write to them in sync/legacy/sync_api). Proven to still bite: a scheduled `truncate public.nodes` job made it fail; removed, it passes. Not a weakening: the replace-all risk it guards is still caught.
- [Run 6 T+0:00 12:08] Run 5 final check before its commit. verify_all found a real defect in itself: this session sets FORCE_COLOR, pytest coloured its FAILED lines, `^(FAILED|ERROR)` matched nothing, and a failing suite compared as "no new failures". Fixed: pytest runs with --color=no, and verify_all fails when pytest reports failures it cannot read by name. Re-run on the pure Run 5 tree (run-6 edits set aside): 1,264 pass / 13 fail / 52 skip; the 13 are main-baseline failures, 30 of the 43 baseline failures pass, 0 KB failures, VERIFY: ALL PASS. | VERIFIED

## Run 6 log (T0 = 2026-11-03 12:08)
- [T+0:00] No VERCEL_TOKEN in .env: D2 (preview) will be skipped and said so at the top of HANDOFF.
- [T+0:10] verify_all bug found and fixed (FORCE_COLOR hid failures; see Run 5's last entry). Run 5 committed as 9a739f9 after a clean full run (1,264 pass / 13 baseline / 0 new). | VERIFIED
- [T+0:45] A2 docs/ARCHITECTURE.md: decision "kb is the single source of truth", the diagram, and the inventory of old-table readers (9 map routes + stats.json move to kb; curation routes stay as intake administration: the one recorded exception).
- [T+0:55] A3 docs/CONTRACTS.md + migration 0032 (node_types.shape/owner_expected, edge_types.color/line_style, kb.changes.kind/node_ids derived by the audit trigger; change-only events for graph_positions, person_accounts, finished sync runs) + web/lib/kb/graph.py (GET /api/kb/graph). 0032 up/down/up on a clone of kb_realdata: OK; paging over the real data returns 5,087 records and 4,408 relationships exactly once each; focus depth 2 = 118 ms. tests/test_kb_contracts.py 13 passed; KB API/sync/schema/RLS/migration/MCP files 156 passed. | VERIFIED
- D49. Real-data screenshots (and every "/" map screenshot, which shows the pipeline's real instructor names even in the demo) stay LOCAL in git-ignored folders; only demo screenshots are committed. The brief asks for screenshots in docs/run6/before/, the hard rules forbid committing real data: the rule wins. Reverse: none needed.
- D50. Contracts are backed by code before the split (0032 + graph.py written by the lead), so the streams build on a working API rather than a document.
- [T+1:05] A1 baseline: docs/run6/BASELINE.md. Every screen at 1536 px on :8766 and :8765: 28 screens each, 0 console errors, 0 warnings. | VERIFIED
- [T+1:15] A4 workspaces: worktrees ../np-run6-b1|b2|b3 on run6/b1-dataflow, run6/b2-graph, run6/b3-ui from fb25b56; per-stream clones of kb_realdata (kb_b1..b3 for servers, kbtest_b1..b3 for tests; a pg_restore of the Supabase test database failed on Supabase-managed schemas, a clone of kb_realdata runs the KB tests: 57 passed on kbtest_b1). Ports 8771-8773. Ownership map in PLAN.md. | VERIFIED
- [T+1:18 13:26] Phase B started: B1, B2, B3 launched (3 subagents, the maximum). B4 and B5 wait for free slots and for B1's merge.
- [T+2:20 ~14:30] B3 finished (run6/b3-ui @ f69b8cf; full report in its branch's PROGRESS.md): 165/180 inline styles to classes, dark-mode danger contrast fixed (2.8 -> 6.8:1), record page one column, matrix headers readable, tests/test_kb_ui_run6.py 34 passed x2, test_kb_e2e.py 71 passed in chunks, 0 console errors on 28 screens x 5 sets. Waits for B1/B2 to merge first (order B1 -> B2 -> B3). Requests for the lead: sidebar "Links"/"Program timeline", palette Go-to entries and ranking (an exact page name + Enter created a program), DESIGN_SYSTEM.md classes.
- [T+2:20] B3 reported that its browser lock was removed by another stream: lock now carries an owner file (rule appended to .run6/common.md and sent to B1 and B2).
- [T+2:22] B5 launched early in B3's slot (worktree ../np-run6-b5 from fb25b56, kb_b5/kbtest_b5, :8775, migration 0034): independent profiling, indexes, flaky tests, audit, and the Data quality > 45 s load B3 measured. Files owned by B1/B2 are handed back as findings.
- [15:23] B5 finished (run6/b5-perf @ 9d53f5c, 6 commits): Data quality 29 s -> 53 ms server / 19.6 -> 0.88 s browser (web/lib/kb/duplicates.py, same pairs and scores; wiring is a patch on B1's service.py: docs/run6/patches/b5-service-find-duplicates.patch, apply after B1). 0034: edge-end indexes (graph with archived 1.0-1.4 s -> 0.16-0.23 s) + DB guards (AI tokens cannot grant roles / link accounts / permanently delete; the last admin cannot be removed). Targets met except opening the graph on a 360-neighbour record (2.7 s, 2.3 s of it B2's client layout). Graph heap leak (~3 MB per open) handed to B2/B1. Flaky e2e sleeps replaced by condition waits (24 cases x5). AUDIT_FINDINGS.md: 17 findings; lead items A4, A9b, A11, A16 + graph.py id lists. Realtime test not run by B5 (needs the demo DB): the lead runs it in Phase C, x5, then re-seeds.
- [15:26] B2 finished (run6/b2-graph @ 5a121d6): #/graph is the whole graph (hierarchy default, force, radial, saved positions; group by type/program/course/domain/module; bundles above 8 satellites; legend = filter; breadcrumbs; focus 1-2 steps; search-jump; minimap; no label overlap; ? sheet; live applyChanges). tests/test_kb_graph_run6.py 11 passed; e2e graph subset 8 passed. Perf: real-data overview 1.1 s / 59 fps; 5,000-record hub 13.8 s -> 7.9 s, 1.0 -> 4.1 fps; WebGL slower than canvas headless, only above 6,000. Contract change request applied by the lead (b9ac707: version + note in GET /api/kb/graph). For the lead: graph.css link; docs/run6/b2-map.patch for "/" after B1; DESIGN_SYSTEM keyboard line. One unexplained hang in a full run of its new test file (later runs all pass): watch it in Phase C.
- [T+2:05] A1 baseline: docs/run6/BASELINE.md. Every screen at 1536 px on :8766 and :8765: 28 screens each, 0 console errors, 0 warnings. | VERIFIED

## Run 6 — B1 report (data flow: every admin change appears everywhere)

Branch run6/b1-dataflow (worktree ../np-run6-b1), DBs kb_b1 / kbtest_b1, port 8771. Migration 0033.

**What changed**
- **"/" map reads kb**: new `web/lib/kb/npmap.py` serves /api/structure, /overview, /node, /neighbourhood, /search, /staffing, /coverage, /me with data.py's shapes (contract §5), one in-memory model per change-feed state (0.8 s build on real data, then cached; structure 40 ms warm, 110 KB brotli). Vocabulary read backwards from config/kb-projection-mapping.yaml (no taxonomy literals); projection ids kept (`np:<id>`), KB-made records by uuid, artifacts as `link:<uuid>`; positions from kb.graph_positions (computed fallback). ETag = format + newest change id + counts + roles. Rollback: `NP_MAP_SOURCE=old` (data.py untouched). Keys the KB cannot supply listed in docs/ARCHITECTURE.md. `/api/stats` (no session, counts only via `kb.landing_stats()`) replaces public/stats.json at request time (file stays as fallback). Map polls /api/kb/changes every 2.5 s and reconciles in place; custom relationship types in its legend with their own colour/line style (KBREL from /api/kb/types). CSP hashes regenerated.
- **Change events**: 0032's trigger already covered every audited table; verified per write path in tests (no table was missing). 
- **Live updates**: public/kb/js/live.js = one policy by `kind` (patch from node_ids; refetch on type/reltype/tag/sync or >=200), reloads any view with S.listReload (lists, outline, dashboard, quality, approvals, Who teaches what / timeline via a 1-line edit), poll 2.5 s. Graph page (graph.js, minimal marked edits): follows every change incl. layout moves, reloads types, per-type edge colour/line style + legend swatch, merge updates edge type.
- **Sync resumable**: phases with SAVED place (`kb.sync_runs.resume`), next run continues; finish never cut off. vercel.json maxDuration 15 -> 60 (justified in docs/run6/SYNC_TIMING.md + DEPLOYMENT.md). Domain `slug` field (0033 + mapping) so the map keeps SD1-SD4 codes.
- **People**: web/lib/kb/people.py + routes (kb_routes B1 block): Settings -> People list + CSV preview (exact / normalised / suggested / ambiguous / none / invalid; writes nothing) and confirm; sign-in auto-link by e-mail, else by an UNAMBIGUOUS name (" (2)" suffix ignored; two same-name records never linked); "Claim this profile" proposals approved by admins; "Owned by you"; person_accounts readable by admins/self only (was editors); e-mails never in audit log, kb.changes or proposals (tested). UI: public/kb/js/views/people.js (peopleTab, ownedByYouCard, legacyExpertiseSection, noOwnerSection).
- **Decisions**: owner_expected editable (typedefs + Settings checkbox, admins); "No owner" on dashboard/sidebar/Data quality counts only those types (the records list filter stays literal). Contributors: field edits -> `update` proposals (bulk too), archives proposals; links + relationships direct; DB trigger `kb.guard_contributor` (0033) refuses contributor UPDATEs on nodes and archive toggles on edges/resources/attachments. Guide permission text updated. Legacy domains still used as expertise listed on Data quality (7 on real data).
- Tests adapted to the decisions (not weakened): test_kb_api (3), test_kb_rls (1), test_kb_workspace (1), test_kb_run3 (1), test_kb_concurrency (1), test_kb_sync (1), test_kb_e2e::test_two_sessions_conflict_dialog (writers are admin+editor; contributor path covered by API tests).

**Tests run (kbtest_b1)**: 24 targeted files (all KB non-browser files + map/CSP/taxonomy/route tests): 324 passed, 3 skipped, 0 failed. New: tests/test_kb_propagation.py 12 passed (26 operations), tests/test_kb_people.py 7 passed, tests/test_kb_sync.py resume test. Browser: tests/test_kb_propagation_e2e.py 1 passed — 26 operations, every one on both pages, slowest 2.64 s (docs/run6/MATRIX.md); test_kb_e2e.py contributor/conflict/bulk subset 7 passed. NOT run by me: the other ~64 tests of test_kb_e2e.py (lead's full suite).
**Migration 0033**: up/down/up on kbtest_b1 and kb_b1, clean; the slug field is archived (values kept) on down.
**Measurements**: sync batches on kb_b1 (budget 10 s): no change 1 batch 2.3 s; 100 source changes 1 batch 4.8 s (286 writes); full first import into an empty KB 5 batches, 43.2 s, max 10.4 s/batch. Real-data smoke on :8771: map ready 1.5 s with 2,833 structure records, SD codes intact, 0 console errors; People 68 current person records; legacy-expertise 7.

**Decisions taken (how to reverse)**
- Sign-in auto-link by unambiguous name (not only e-mail): drop the name step in `kb.auto_link_person` (0033).
- Contributors' relationships stay direct (only links named in the brief; relationships were not in the approval list): add edges to `kb.guard_contributor`.
- Records-list "No owner" filter stays literal (all types); only counts follow owner_expected: add the owner_expected clause in service.list_nodes.
- The map refetches the structure on a change (server-cached, 304 if unchanged) rather than per-node patching (its ids/format are projection-shaped): live block in public/index.html.
- Archived (legacy) KB records are not on the map; KB-only types (course, custom) are carried in the structure.
- `/api/stats` is public like stats.json (aggregate counts only): remove the route to make it session-only.
- maxDuration 60 for api/** (the sync shares the single function).

**For the lead**
- Wiring already done minimally in this branch (marked "B1 (run 6)"): settings.js People tab + owner-expected checkbox (2 imports/4 lines), dashboard.js `right.appendChild(ownedByYouCard())`, quality.js `left.appendChild(legacyExpertiseSection())`, approvals.js ACTION update/claim + admin-only claim buttons, detail.js "Claim this profile" row, teaching.js `S.listReload`, graph.js live/style lines (B2 should keep: onLiveFeed handler, per-type edge colour/line, G.feed counter used by the matrix test).
- HANDOFF note: access to "/" unchanged (owner decision).
- Finding for B5: GET /api/kb/quality takes ~36 s on real data — all of it `find_duplicate_nodes` (pre-existing, not B1).
- No contract change requests. No BLOCKED items.
## Run 6 — B2 report (knowledge graph: structure and navigation)

Branch `run6/b2-graph` (worktree ../np-run6-b2). Server kb_b2 on :8772, tests on kbtest_b2.

### What changed
- `public/kb/js/views/graph.js` (rewritten on the same editing code): reads GET /api/kb/graph (contract §1) and
  /api/kb/types (§3). `#/graph` is now the **whole graph** (was a start page); `#/graph/<id>` the neighbourhood
  (focus=id, depth 1-2) with progressive expansion. Default arrangement **Hierarchy** (Program > Course > Domain >
  Module > Week > Session in rows; topics, people, links and custom types as satellites under their record;
  >8 of one type on one record = a bundle that opens on click / E / search). Arrangements: Hierarchy, Force (cose),
  Radial (rings around the selected record), Saved positions (`?arrange=`, keys 1-4). Group by type / program /
  course / domain / module with a box per group whose title folds it into one node (`?group=`). Legacy and archived
  hidden unless "Show: Legacy / Archived" (`legacy=all`, `archived=1`, refetched). Legend = filter (checkbox per
  type and relationship, "Only" per type, line colour + style swatch). Breadcrumbs for the focused record. Focus mode
  off / 1 / 2 steps dims the rest (`?focus=`, key O). Search jumps into bundles and groups. Minimap (click/drag,
  arrows, toggle M) and Fit. Labels never overlap (greedy declutter, hidden labels return on hover), semantic zoom,
  faint cross-hierarchy edges, edges outside the hierarchy hidden below zoom 0.3. `?` shortcut sheet, hover handles
  (connect, expand, focus, rename), first-visit hint, empty state with a New record action.
  Editing kept as built (create, connect, rename, archive + Undo, move, saved views). The read API carries no
  `version`: rename fetches it once when it starts (a known stale version still conflicts).
- **Live:** `applyChanges(rows)` is the one entry point (dedupes by change id, handles `kind`/`node_ids` rows and the
  old table_name/row_id shape, type changes restyle, >200 rows refetch). Fed by live.js `onLiveChange` and by the
  page's own poll of `/changes?since=<head>` (4 s). Exposed as `window.__kbGraph.applyChanges` for B1.
- New modules `public/kb/js/graph/`: `style.js` (types metadata -> Cytoscape rules, legend swatches, icons; pure,
  shared with "/"), `layouts.js` (hierarchy / radial / grouped, pure), `labels.js`, `minimap.js`, `map.js` (adapter for
  the "/" map). New `public/kb/graph.css` (tokens only, no new token).
- `scripts/kb_graph_perf.py`: tree scenario shaped like the real data, `--base` read-only real-data mode, timings.
- `docs/run6/GRAPH_PERF.md` (before/after), `docs/run6/b2-map.patch`, `tests/test_kb_graph_run6.py` (new).
- `public/kb/index.html`: ONE marked line linking graph.css (for my testing; B3 owns the file).

### Tests (kbtest_b2, browser lock taken each time)
- `tests/test_kb_graph_run6.py`: **11 passed** (hierarchy default + bundles, legend filter, focus + breadcrumbs,
  search into a bundle, minimap + fit, layout switch, legacy toggle, group fold/unfold, `?` sheet + hint + empty
  state + hover handles, live change via the feed, label overlap = 0 in hierarchy/radial/force at zoom 1).
- `tests/test_kb_e2e.py -k "graph or edge"`: **8 passed** (all run-3 graph editing tests, a11y + no-scroll on #/graph).
  An earlier accidental run of the whole e2e file: 71 passed, 1 failed (the legend filter, since fixed).
- `tests/test_taxonomy_single_source.py`: 6 passed. Layout functions also checked in node on real-shaped data (0 slot overlaps).
- Real data on :8772: overview, group by domain, legacy=all, expand=all: **0 console errors/warnings, 0 label overlaps**.

### Measurements (docs/run6/GRAPH_PERF.md)
Real data overview: 3,087 records, 352 drawn, load 1.1 s, 58.7 fps. All 3,087 drawn: 2.6 s, 28.7 fps.
Hub 5,000 (every record drawn): before 13.8 s / 1.0 fps, after 7.9 s / 4.1 fps (canvas). Hub 500: 1.8 s / 30.6 -> 1.1 s / 36.9.

### Decisions (and how to reverse)
1. `#/graph` opens the whole current graph instead of the start page (start chips dropped; search covers it).
   Reverse: restore `startPage()` from fb25b56 for an empty path.
2. Saved positions apply only in "Saved positions" (default for `?view=`); kb_realdata holds 3,228 shared positions
   that would otherwise override the hierarchy. Dragging still saves. Reverse: default `opt.arrange` to 'saved'.
3. WebGL only from 6,000 drawn records (slower than canvas on real-shaped graphs here). Reverse: `GL_FROM` in graph.js.
4. Bundle threshold 9 satellites (`BUNDLE_FROM`), dashes solid above 400 lines, icons off above 400 records.
5. Owner filter now uses `owner_record_id` (the run-5 owner record) instead of the account `owner_id`.
6. Satellite anchor = deepest structural neighbour, then scope (scope_id can skip levels).

### Contract change requests
- §1 GET /api/kb/graph: add `version` to nodes and edges (and `note` to edges) so rename/edge editing need no extra
  GET. Workaround in place (lazy fetch).

### For the lead
- index.html (kb): keep `<link rel="stylesheet" href="/kb/graph.css">` after kb.css (graph.js also adds it if missing).
- "/" map, after B1 merges: `git apply docs/run6/b2-map.patch` (checked with `git apply --check` against this
  branch's public/index.html; patched scripts pass `node --check`). It loads `/kb/js/graph/map.js` after sign-in:
  type colours from /api/kb/types (lifted for the dark ground) into `C`, `window.__NP.look` (edgeColor/edgeDash), and
  the hierarchy as the 3D view's home positions in `build3D`. If B1 changed those lines, apply by hand: (a) in
  `afterSignIn` after `hideGate(); banner('');` the import block; (b) at the end of `build3D` the home-position loop.
  NOT browser-tested on "/" (I must not edit index.html).
- DESIGN_SYSTEM.md "Keyboard" graph line could add `?`, 1-4, O, M, +/- (not my file).
- Not explained: one full run of the new test file hung after loading /api/kb/graph (killed at ~9 min); every run
  since (3 full, 11 single) passed in ~2 min. Added guards for non-finite label boxes in labels.js.

### Blocked
Nothing.
- [22:26] Phase C: B1 merged (4e0694a). 0033 applied to postgres + kb_realdata. Targeted: 24 KB/API files 178 passed; the map's own tests (structure, data layer, staffing, role boundary, sensitive split, default view, layout, measurement, grants, adapters) 179 passed / 9 skipped, failures only the baseline ones. Matrix (browser) after B1: 26/26 on both pages, slowest 2.72 s. B1's test edits reviewed: they follow the decisions (contributor edits are proposals; "No owner" follows owner_expected), none loosens a check. | VERIFIED
- [22:26] B2 merged (0dad7da; graph.js taken from B2, B1's live hooks superseded by B2's applyChanges). Matrix then failed on the Graph page for 15 of 26 operations: B2's page did not count feed batches, did not re-type an edge after a merge, did not restyle nodes after a type colour change, ignored layout.update. Fixed in graph.js (edge data refreshed on type/version/label/colour change, node colour compared, G.feed counter, saved positions applied in the "Saved positions" arrangement). Test aligned with B2's documented decisions only (legend swatch class .legend-edge; owner filter by owner record; the layout step in the Saved positions arrangement). Matrix re-run: PASS, 26/26. | VERIFIED
- [22:26] B2's map patch (docs/run6/b2-map.patch) applied to public/index.html. Its browser check (test_kb_graph_run6.py + matrix + e2e graph subset) was KILLED by Claude Code for low system memory; per the notice it is NOT restarted. Not verified yet.

## Run 6 resume (owner: "Yes, resume"), T0 = 2026-11-04 02:15, stop new work at 05:15
- [T+0:00] Free memory 2.49 GB (the owner's Chrome holds 1.8 GB; nothing of ours running). VERCEL_TOKEN now in .env -> D2 back in scope.
- D51. Stay on Windows, not WSL: Docker Desktop already runs the WSL VM; a second toolchain (venv, Chromium, deps) costs setup time and memory for no measured gain. Reverse: none.
## Run 6 — B3 report (UI/UX across every page)

Branch run6/b3-ui, worktree ../np-run6-b3. Servers: kb_b3 real-data copy on :8773, then the demo
(eval/kb_demo_server.py, read-only screenshots) on :8773; both stopped. Detail: docs/run6/UI_REVIEW.md.

### What changed
- **kb.css (below `:root` only)**: a "run 6 (B3)" section — utilities on the 8px grid, named components
  (`.tab-intro`, `.record-page`, `.field-card`, `.type-editor`, `.queue`, `.contained`, `.deck-list`,
  `.view-toolbar`, `.swatch`, …), one focus ring for every interactive element, reduced motion for every
  animation/transition, the Activity filter grid, the teaching matrix header fix. Existing rules fixed:
  `.empty > .i` (the help icon in every empty state was 20px), selected tab no longer bold (neighbours
  shifted), danger button / error toast text `--on-accent` (white on #f87171 was 2.8:1 in dark), one
  radius and weights 400/600 only (matrix, timeline, `kbd`).
- **JS (views/* except graph.js and people.js, detail.js, form.js, core.js internals, page.js unchanged)**:
  165 of 180 inline `style:` values became classes; the 15 left are data-driven (type colour, avatar hue,
  swatch, bar %, resizable column width). `pageHead` now used by All records, Programs, Courses and Links.
  Record as a page = one centred column. Teaching matrix headers readable (were clipped to 3–4 letters).
  Timeline decks one line each (overlapped on real data). Guide screenshots at real size. Data quality says
  when it is slow. Archived/Approvals lists keep to the page width.
- **Copy**: Resources page titled "Links", record tab and form section "Links", "Program timeline",
  Activity filter "What changed", plurals instead of "(s)". guide.md: Links, Who teaches what, Program
  timeline, a new "Legacy records and the sync" section; B1's contributor/link permission text untouched.
- **public/kb/index.html**: the sign-in gate has an `h1` and a labelled region.
- **New**: eval/kb_ui_sweep.py (every screen × widths × themes, plus `--layers` for panels, sheets,
  dialogs, menus; counts and selectors only), tests/test_kb_ui_run6.py, docs/run6/after/ (demo; 1536 light
  all 28 screens; 1280/1920/2560 and dark for the 11 main screens; quantised PNGs, 4.2 MB),
  docs/run6/UI_REVIEW.md.

### Tests (NP_TEST_DSN = kbtest_b3, browser lock held for every run)
- tests/test_kb_ui_run6.py: 34 passed (20 without a browser: contrast both themes, avatar hues, one
  radius/two weights, no one-off inline styles per file; 14 in Chrome: no horizontal scroll at 1024 on all
  22 screens + record page + panel in light and dark, accessible names and tooltips on every screen,
  names on 10 layers, focus ring on 40 Tab stops × 6 screens, keyboard path (palette search → record →
  menu → Esc → Settings tabs → Activity search), reduced motion, centred record page, tabs do not shift).
  One earlier run had 1 failure: the first page load of the module waited >5 s for `whoami` (server warm-
  up); the wait is now 20 s and the two later full runs passed (34/34 each, the last after the guide.md edit).
- tests/test_kb_e2e.py in three chunks: 71 of 71 passed (test_quality_dashboard_and_csv_export failed once
  on the same first-load 5 s `whoami` wait in its chunk and passed on the re-run; not touched by B3).
- After the guide.md and final CSS edits: e2e guide/tablet/no-horizontal-scroll subset 14 passed.
- tests/test_deploy_guard.py: 8 passed.
- Sweeps on the real-data copy (1024/1536/2560, light and dark, plus layers at 1024/1536): 0 horizontal
  scroll, 0 unnamed controls, 0 cut text without a tooltip, 0 console errors. eval/kb_screens.py after sets:
  0 console errors, 0 warnings, 28 screens × 5 sets.

### Measurements
- Contrast (computed from kb.css): lowest text pair 4.64:1 (faint text on a hovered row, light); every
  pair the components use ≥ 4.5:1 in both themes; avatar hues ≥ 4.99:1 with white.
- Real data: Data quality takes more than 45 s to load on kb_b3 (/api/kb/quality + /dashboard over
  3,087 records); everything else loads within the sweep's wait. For B5/B1 (not a UI fix).

### Decisions (and how to reverse)
- Selected tabs keep the regular weight (colour + underline only) so neighbours do not move. Reverse:
  put `font-weight: var(--w-strong)` back on `.tabs [aria-selected="true"]`.
- "Resources" page titled "Links" (the Guide's and the record tab's term). Reverse: title in
  views/resources.js.
- After screenshots are quantised to 256 colours to keep the repo small. Reverse: re-run eval/kb_screens.py.
- Demo after-screenshots were taken from a demo server started in this worktree against the shared demo
  database, read-only (no saves; the New record sheet is closed with Esc).

### Requests to the lead (files B3 does not own)
1. app.js NAV: `['resources', 'Resources', …]` → `'Links'`; `['timeline', 'Programme timeline', …]` →
   `'Program timeline'` (pages now say Links / Program timeline).
2. app.js palette "Go to": add `['Who teaches what', 'teaching']`, `['Program timeline', 'timeline']`, and
   rename `Resources` → `Links`.
3. app.js palette ordering: typing an exact page name ("Settings") and Enter runs "New program
   “Settings”" because Create commands rank above Go to. Put Go-to matches before Create commands.
4. app.js `renderSidebar`: the New record button's inline `style: 'width:100%;margin-bottom:4px'` and the
   user label's `style: 'gap:0;min-width:0'` → classes `w-full mb-1` and `gap-0` (they exist in kb.css).
5. DESIGN_SYSTEM.md: document the run-6 utility classes and components (lead-owned doc).
- No contract change requests.

### Blocked / not done
- Settings → People tab: B1's people.js is not on this branch; reviewed when B1 merges.
- Graph page chrome: unchanged here (graph.js is B2's); the sweep found no problems on it.
- Note: once during this run my browser.lock directory disappeared while I held it (another agent removed
  it); I re-took it before every later run. I also ran one 2-second headless probe (a date input's focus style) without the lock; every other browser run held it.
## Run 6 — B5 report

Branch `run6/b5-perf` (from fb25b56, Phase A), worktree ../np-run6-b5, kb_b5 / kbtest_b5, port 8775. It started in parallel with B1 and B2 and before the B3 merge, so it covers the current endpoints and leaves fixes in B1's, B2's and lead files as requests (below).

**What changed**
- `web/lib/kb/duplicates.py` (new): an exact, prefix-filtered trigram similarity join. It returns the same pairs and scores as the old all-pairs SQL, keeps memory bounded (top 200 in a heap), is cached on the change-feed head, and gives a 422 for a non-numeric threshold. **Data quality went from 29 s to 53 ms on the server, and from 19.6 s to 0.88 s in the browser on real data.** This is the >45 s that B3 measured. The wiring patch for B1's `service.py`: `docs/run6/patches/b5-service-find-duplicates.patch`.
- `db/migrations/0034_kb_perf_indexes` (reserved for B5): non-partial indexes on `edges(source_id)` and `edges(target_id)`, which take `graph?archived=1` from 1.0–1.4 s to 0.16–0.23 s. Also two database guards from the audit: the AI assistant is refused role, sign-in-link and permanent-delete writes (A1), and a request cannot leave the workspace without an admin (A2). Applied to kb_b5 and kbtest_b5, and proven by running up, down, up on both (triggers 6 → 0 → 6, indexes 2 → 0 → 2).
- `public/kb/js/views/settings.js`: a non-admin who follows a link to an admin-only tab now gets Types, where before there were two 403 errors (A13). One line, which merges cleanly with B3.
- `api/curate.py`: 400 for a malformed body (A9).
- Tests: `tests/test_kb_duplicates.py` (15), `tests/test_kb_audit_run6.py` (8), `tests/test_kb_console_run6.py` (2: every screen and flow as admin and as viewer; it fails on any console error, page error or unhandled rejection).
- Flaky tests: `tests/test_kb_e2e.py` (fixed sleeps replaced by `eventually()` / `settled()` / waiting for the draft itself) and `tests/test_kb_realtime.py` (proof by socket frames, not by the wall clock).
- Scripts: `scripts/kb_realdata_profile.py` (every screen's requests, the map's routes, `/api/kb/graph`, EXPLAIN, at real-data size), `scripts/kb_browser_profile.py` (time to interactive, JS bytes, graph expand, heap over 50 graph opens). `kb_perf.py` and `kb_explain.py` now cover the run-6 endpoints.
- Docs: `docs/run6/PERF.md` (before and after for every screen, the targets), `docs/run6/AUDIT_FINDINGS.md` (17 findings).

**Tests run (kbtest_b5, targeted)**
- 14 non-browser KB files, including duplicates and audit: **188 passed**.
- `test_node_id_scheme`, `test_taxonomy_single_source`, `test_lazy_route_table`: 19 passed, 1 skipped.
- Browser runs, with the lock held:
  - the e2e tests whose waits I changed (`-k "resource_lifecycle or no_horizontal_scroll or outline_quick_add or draft_restore or accessible_name"`): **24 passed, 5 times in a row**;
  - e2e and run3 tests touching settings, tokens, members and types: 13 passed;
  - `test_kb_console_run6.py`: 2 passed, 5 runs, including one without the service patch.

**Flaky tests: cause and fix**
1. `test_resource_lifecycle_and_reuse`: `time.sleep(0.5)` and then an assertion on the server state raced the restore. Now it polls with `eventually()`.
2. `test_no_horizontal_scroll_at_1024[*]` (11 cases): a fixed 700 ms wait raced rendering, so the check could run on a half-drawn page. Now it waits for `settled()` (no skeleton, nothing aria-busy).
3. `test_outline_quick_add_reorder_and_copy`: a 500 ms wait after "Order saved" raced the re-render. Now `eventually()` checks the order.
4. `test_guide_promises_undo_after_create_draft_restore_and_theme`: a 600 ms wait guessed the 400 ms debounce. Now it waits for the draft in localStorage.
5. `test_every_control_has_an_accessible_name[*]` (10 cases): fixed 1,200 and 300 ms waits. Now `settled()`, and the sheet's name field must be visible.
6. `test_kb_realtime.py`: `assert time.time() - t0 < 3.0` failed on a loaded machine even when the socket had delivered. It now records the admin page's WebSocket frames and change-feed fetches, and asserts that a `postgres_changes` frame arrived after the edit and that a feed fetch followed that frame.

All 24 affected e2e cases passed 5 consecutive runs. **The realtime test was NOT run.** It runs only against the local stack's `postgres` database (the demo's), and running it there was refused as a change to a shared resource. With `NP_TEST_DSN=kbtest_b5` it skips. Unblock: the lead runs `NP_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:54322/postgres python -m pytest tests/test_kb_realtime.py` five times, then re-seeds the demo.

**Measurements** (docs/run6/PERF.md)
- Targets met: every list and report screen is interactive in 0.21–0.88 s; graph expand has p50 90 ms and p95 129 ms; list and search p95 on the server is 10–40 ms; console errors are 0.
- **Missed:** opening the graph on a record with 360 neighbours takes 2.7 s. About 2.3 s of that is the client-side Cytoscape layout in `graph.js` (B2).
- Found:
  - a graph memory leak of about 3 MB per opening (B2 and B1);
  - the "/" map loads 1.49 MB of JS (B1 and B2);
  - a local-only stall of about 40 ms for statements whose parameters exceed 8 KB (Docker Desktop on Windows).

**Decisions made (each with how to reverse it)**
- The duplicate finder lives in a new module and is wired by a patch, because `service.py` is B1's file. To reverse, do not apply the patch.
- The AI and last-admin rules are enforced in the database (0034), not in B1's service code. That covers every path and needs no B1 change. To reverse, run `migrate.py down` (0034 down drops them) or remove that part of 0034.
- The last-admin rule binds only request connections (`role` = `authenticated`), so that operator scripts and fixtures can still manage memberships.
- `add_edge_rule` for `ai` is not refused in the database, because inline relationship types created by the AI write rules. It is left to B1 (A1b).
- `similarity` keeps the old wire format (numeric rounded to 3 places, serialised by `default=str`).

**Requests for the lead and other streams** (exact fixes in AUDIT_FINDINGS.md and PERF.md)
- Apply `docs/run6/patches/b5-service-find-duplicates.patch` (B1's `service.py`) after B1 merges. Without it, Data quality stays at about 29 s.
- Lead, `kb_routes.py:222`: pass the raw `threshold` (A4). Lead, `index.py`: a negative Content-Length (A11) and an array body in `_serve_write` (A9b). Lead: `PUT /graph/positions` is dead code (A16). Lead, `graph.py`: keep the id list on the server (PERF).
- B1: A1b, A5, A6, A7, A8, A10, A12, and `onLiveChange` / `onPresence` returning an unsubscribe function.
- B2: `graph.js` unsubscribes and calls `cy.destroy()` when the view is left (the leak), and paints the first frame without a long layout.
- Contract change request: none.

**BLOCKED**
- `tests/test_kb_realtime.py`: the 5 consecutive runs (see above).
- The "/" map's routes should be profiled again after B1 moves them to kb: `python scripts/kb_realdata_profile.py --db kb_b5 --only "map /"`.
- [T+0:10] R2: B3 merged (6f4f968; settings.js conflict: B1's owner-expected toggle kept with B3's classes), B5 merged (0fb18f4) + its Data quality patch on B1's service + audit A4 (1b218fc). 0034 on postgres + kb_realdata. API-level suite (16 files): 214 passed. | VERIFIED
- [T+0:20] R1: the "/" map's inline script was BLOCKED by its CSP hash after B2's patch (the browser refused it); pipeline/gen_csp_hashes.py rewrote vercel.json; matrix 26/26 on both pages after B3+B5. test_kb_graph_run6.py: all 11 pass one per process; tests 7+8 together (legacy toggle, then group by type) hang reproducibly (test-isolation defect, not reproduced in use; repro: run those two node ids together). Group by type takes 45 s alone: slow, logged. test_kb_ui_run6.py 34/34 (4 failed once while kb.css was being edited; re-run 8/8). test_kb_console_run6.py 2/2. | VERIFIED (graph: PARTIAL, isolation defect open)
- [T+0:40] R3 (owner-approved permanent deletion): web/lib/kb/legacy_delete.py + pipeline/kb_legacy_delete.py (plan / delete = export to backups/ then delete in one transaction / restore <file>), 0037 kb.sync_exclusions (rule np_legacy_domains_modules + every deleted source id; the sync leaves them out, and their relationships and attachments). Rehearsal on a clone: delete then restore = every table's count back exactly. kb_realdata: 946 deleted (42 domains, 904 modules), 3,844 relationships, 1,040 attachments, 1,133 expertise links (instructors kept), 0 records left without a parent, 0 links left alone; a sync after: 0 created, 0 conflicts; live domains 4, modules 20. tests/test_kb_legacy_delete.py 5 passed; sync + propagation + taxonomy 48 passed. Export: backups/legacy_deleted_kb_realdata_20261104_025304.json (gitignored). | VERIFIED
- D52. F1 brand from interviewkickstart.com itself (Elementor kit post-5.css and the header logo SVG): blue #3996D2, navy #324158/#344158, font Inter. Accent #2670A6 in light (the brand blue darkened to 5.3:1 for white text; #3996D2 is 3.25:1), the exact #3996D2 in dark (5.8:1 with dark text). Reverse: the three token lines in kb.css.
