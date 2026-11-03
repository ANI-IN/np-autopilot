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
- [T+1:40] A2 docs/ARCHITECTURE.md: decision "kb is the single source of truth", the diagram, and the inventory of old-table readers (9 map routes + stats.json move to kb; curation routes stay as intake administration: the one recorded exception).
- [T+1:45] A3 docs/CONTRACTS.md + migration 0032 (node_types.shape/owner_expected, edge_types.color/line_style, kb.changes.kind/node_ids derived by the audit trigger; change-only events for graph_positions, person_accounts, finished sync runs) + web/lib/kb/graph.py (GET /api/kb/graph). 0032 up/down/up on a clone of kb_realdata: OK; paging over the real data returns 5,087 records and 4,408 relationships exactly once each; focus depth 2 = 118 ms. tests/test_kb_contracts.py 13 passed; KB API/sync/schema/RLS/migration/MCP files 156 passed. | VERIFIED
- D49. Real-data screenshots (and every "/" map screenshot, which shows the pipeline's real instructor names even in the demo) stay LOCAL in git-ignored folders; only demo screenshots are committed. The brief asks for screenshots in docs/run6/before/, the hard rules forbid committing real data: the rule wins. Reverse: none needed.
- D50. Contracts are backed by code before the split (0032 + graph.py written by the lead), so the streams build on a working API rather than a document.
- [T+2:05] A1 baseline: docs/run6/BASELINE.md. Every screen at 1536 px on :8766 and :8765: 28 screens each, 0 console errors, 0 warnings. | VERIFIED

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
