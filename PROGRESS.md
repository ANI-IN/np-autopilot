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
