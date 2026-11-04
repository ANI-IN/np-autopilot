# PLAN — run 6 (FINAL): one source of truth, a better graph, legacy cleanup, polish, go-live rehearsal (2026-11-03)

T0 = 2026-11-03 12:08. Memory: this file + PROGRESS.md ("Run 6 log"). Re-read both after any context reset.
Brief: the RUN 6 message. Contracts: docs/CONTRACTS.md (lead-owned). Architecture: docs/ARCHITECTURE.md (top).
No VERCEL_TOKEN in .env -> D2 (preview) is SKIPPED and said so at the top of HANDOFF.

## Memory rules (the laptop ran out twice)
- At most 3 subagents at once. ONE browser-test run at a time across all agents: take the lock with
  `mkdir .run6/browser.lock` (fails = someone has it: wait and retry), and `rmdir .run6/browser.lock` when done.
- Full suites: lead only, chunked, servers stopped. Streams run targeted tests only.

## Workspaces (A4)
| Stream | Worktree | Branch | Server DB (clone of kb_realdata) | Test DB (NP_TEST_DSN) | Port |
|---|---|---|---|---|---|
| B1 data flow | ../np-run6-b1 | run6/b1-dataflow | kb_b1 | kbtest_b1 | 8771 |
| B2 graph | ../np-run6-b2 | run6/b2-graph | kb_b2 | kbtest_b2 | 8772 |
| B3 UI/UX | ../np-run6-b3 | run6/b3-ui | kb_b3 | kbtest_b3 | 8773 |
| B4 legacy cleanup | ../np-run6-b4 | run6/b4-legacy | kb_b4 | kbtest_b4 | 8774 |
| B5 perf/QA | ../np-run6-b5 | run6/b5-perf | kb_b5 | kbtest_b5 | 8775 |

Server: `KB_LOCAL_DB=kb_b1 python eval/kb_realdata_server.py 8771` (sign-in as on :8766).
Tests: `NP_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:54322/kbtest_b1 python -m pytest tests/test_kb_x.py`.
Python: the main checkout's venv, `C:/Users/Lenovo/Desktop/np-autopilot/.venv/Scripts/python`.

## File ownership (Phase B)
Shared, LEAD ONLY (ask in PROGRESS.md): public/kb/js/app.js (router, sidebar), `:root` tokens in public/kb/kb.css,
db/migrations/ (numbers reserved below), docs/CONTRACTS.md, web/lib/kb/graph.py, api/kb_routes.py
(new routes by request; a stream may add a route block for ITS OWN feature at the end of `handle`,
marked with its stream id), PLAN.md, HANDOFF.md, scripts/verify_all.sh.
Migrations reserved: 0033 = B1. Others ask.

| Stream | Owns |
|---|---|
| B1 | web/lib/data.py, new web/lib/kb/npmap.py, api/{structure,overview,node,neighbourhood,search,staffing,coverage,me}.py, public/index.html (until B1 merges; then B2 for the map's visual language), pipeline/gen_landing_stats.py, web/lib/kb/{sync,sync_api,service,workspace,activity}.py, public/kb/js/{live,realtime}.js, new public/kb/js/views/people.js, the dashboard "Owned by you" card, Data quality owner/legacy-domain lists, guide.md permission text, vercel.json (maxDuration), tests/test_kb_propagation*.py |
| B2 | public/kb/js/views/graph.js, new public/kb/js/graph/*.js (style, layouts, legend, minimap, focus), public/kb/graph.css (new; the lead links it), public/vendor/ additions, scripts/kb_graph_perf.py; "/" visual language after B1 merges |
| B3 | public/kb/js/views/* except graph.js and people.js; detail.js, form.js, page.js, relpicker.js; core.js internals (not signatures); kb.css below `:root`; public/kb/index.html; public/kb/guide.md copy (except B1's permission text); docs/run6/before|after |
| B4 | docs/LEGACY_REMOVAL.md; removals it proves safe (after B1 merges, for old-table readers); redirects (api/index.py redirect table, by request) |
| B5 | scripts/kb_explain.py, kb_perf.py, new perf scripts; indexes (migration by request); flaky-test fixes in tests/; docs/run6/AUDIT_FINDINGS.md; fixes it finds (in another stream's file: by request, or after that stream merges) |

## Phases
- [ ] 0 Run 5 verified and committed
- [ ] A1 baseline (chunked tests; console errors + 1536px screenshots of every screen, :8766 and :8765) -> docs/run6/before/
- [x] A2 docs/ARCHITECTURE.md (decision, diagram, reader inventory)
- [x] A3 docs/CONTRACTS.md + 0032 (type styles, change kinds) + web/lib/kb/graph.py (GET /api/kb/graph) + tests/test_kb_contracts.py
- [ ] A4 worktrees, databases, ports, ownership map (this file)
- [ ] B1 + B2 + B3, then B4 + B5
- [ ] C merge B1 -> B5, matrix after each, full chunked suite, click-through, cleanup
- [ ] D1 dev DB, D2 SKIPPED (no token), D3 GO_LIVE.md + rehearsal on dev, D4 PR_DESCRIPTION.md
- [ ] Finish: verify_all (chunked), matrix, 0 console errors, demo re-seeded, :8765 + :8766 running, HANDOFF, push

---
# PLAN — run 5: parity with NP Autopilot, owners, legacy, scheduled sync, dev database (2026-11-03)

T0 = 2026-11-03 02:59. Memory: this file + PROGRESS.md ("Run 5 log"). Local real data: kb_realdata (:8766). Demo :8765 untouched.
Only remote DB allowed: the DEV project (ref checked != production yqmzjgzhxhihnpbgqmeh: OK, agrees with DEV_SUPABASE_URL).

NP Autopilot reference (public/index.html, run on :8766 against the old tables, read through its own functions):
domains 4 current + 42 legacy (legacy = offers no current module); modules 20 current + 904 legacy (legacy = no domain_slug;
721 legacy modules have no domain); instructors 25 with a current-mastersheet role + 1,886 older sheets; programmes 42 (all older sheets);
roles on 57 taught_by edges (tier mastersheet): primary 23, backup_1 20, backup_2 11, backup_3 3.

Design:
- web/lib/kb/sync.py = the import engine (moved from pipeline/kb_import_projection.py, which becomes the CLI): desired state from the
  old tables -> diff against kb.sync_map checksums -> write only changes; conflicts flagged; removed-at-source flagged; legacy rules.
- 0030: kb.nodes.is_legacy, owner_record_id, co_owner_record_ids; kb.person_accounts (email -> account, resolved on sign-in);
  kb.sync_map, kb.sync_runs, kb.legacy_archive; actor_type 'sync'.
- Production schedule: Vercel cron -> POST /api/kb/sync (CRON_SECRET), time-boxed, transaction-scoped advisory lock (works through
  the transaction pooler); Settings -> Sync "Sync now"; KB_SYNC_ENABLED=false kill switch.

- [x] 1 parity: NP logic mirrored (np_categories) + parity script reading NP's own model; topics unmerged; legacy flag; roles on teaches
- [x] 2 owners: roles -> owner/co-owner records; person_accounts linking by email on sign-in; Data quality "no owner"
- [x] 3 legacy archive (reversible, re-runnable) + restore + prepared permanent-delete command
- [x] 4 sync: engine, run log, lock, conflicts, removed-at-source, API + cron route + Settings -> Sync + banner, tests, local proof
- [x] 5 views: Who teaches what (matrix), Programme timeline
- [x] 6 dev: backup, migrate, fill old tables, import + legacy, sync, admin (morning step: no users on dev yet), verify, DEV_DEPLOY.md, deploy_dev_preview.sh
- [ ] Finish: verify_all, servers, HANDOFF, push

---
# PLAN — real-data rehearsal (local copy of production), 2026-11-03

T0 = 2026-11-03 00:48 (Step 0 dump). Memory: this file + PROGRESS.md ("Real-data run" log).
Production was read ONLY for the two pg_dump runs (Step 0); the URL is deleted from .env. LOCAL ONLY from here.
Real data lives only in backups/ (ignored by .gitignore and .git/info/exclude) and in the local database kb_realdata.
Reports: counts and record ids only.

- [x] Step 0 dumps (schema 41,935 B, data 17.3 MB, UTF-8, 18 tables, counts = production)
- [x] 1 schema drift vs 0001-0021 -> docs/MIGRATION_REPORT.md
- [x] 2 restore into kb_realdata (separate DB, same local cluster), counts = production
- [x] 3 apply 0022-0029 on the restored data (the rehearsal)
- [x] 4 project_graph.py corpus_names_a_file root cause; rerun suite
- [x] 5 migrate public -> kb (idempotent, preview, never overwrite app edits) + docs/MIGRATION_MAPPING.md
- [x] 6 (skipped: no workbook) ik_workbook.xlsx (skip if absent)
- [x] 7 preview / apply / re-run (0 duplicates) -> docs/MIGRATION_REPORT.md
- [x] 8 local-only admin sign-in on 8766
- [x] 9 browser check at 8766, 5 courses
- [x] 10 connection pooling (transaction pooler) -> docs/DEPLOYMENT.md
- [ ] Finish: 8765 + 8766 running, HANDOFF section, push

---
# PLAN — run 3: polish, graph editing, custom relationships, audit log

T0 = Mon 2026-11-02 21:18 local. Stop new work at T+2:50 = **00:08**, then Section 6 + handoff.
Memory: this file + PROGRESS.md (run-3 log at the end). Re-read both after any context reset.
Cut order if >20 min behind: A4 column drag -> B2 merge tool -> B3 clustering -> 3840 tuning -> 25-user test to 10.

## Phase A — owner bugs (<=30 min, each with a test)
- [x] A1 one attention query (tile = list = sidebar)   - [x] A2 named actors, no test leftovers, seed resets audit
- [x] A3 demo badge placement   - [x] A4 View popover   - [x] A5 full text, wrap, resizable columns
- [x] A6 Guide layout + images   - [x] A7 relationship combobox with sentences   - [x] 1536 sweep

## Phase B
- [x] B1 page template, dashboard grid, 4K (1280/1536/1920/2560/3840 @1x/2x)
- [x] B2 inline relationship types (admin/editor-unreviewed/contributor-proposal, DB-enforced), duplicate guard, merge, CRUD matrix, dependencies
- [x] B3 graph editing (create, connect, edit, rename, delete+undo, move+positions per view, navigate, sync, scale numbers)
- [x] B4 Activity page + History tab (DB-enforced visibility, immutable audit)
- [x] B5 admin-only "Back to <site>" link (server role)

## Phase C — perf + concurrency
- [x] EXPLAIN + indexes, caches, 25-user test -> docs/TEST_RESULTS.md

## Final (from 00:08)
verify_all --fresh-clone --reset-db; new browser tests; click-through 1536/2560; docs; reseed; handoff.

---
# PLAN — Knowledge Platform, run 2: demo → team-ready (branch `auto/knowledge-platform-20261102`)

T0 = Mon 2026-11-02 11:44 local. Stop new work at T+4:15 = **16:00**, then Section 7 + handoff.
Memory: this file + PROGRESS.md. Re-read both after any context reset.

Inputs: docs/SPEC.md does NOT exist in the repo (PROGRESS D15) -> the run-2 prompt is the spec.
backups/ does not exist -> D7 BLOCKED (D16). Frontend stays vanilla JS, no build (D17).

## Phase A — trustworthy verification (<=30 min)
- [x] A1 verify_all.sh: set -euo pipefail, git-root, every tool/path checked. Proven failing (wrong cwd, foreign repo, missing tool, bad option, missing path).
- [x] A2 main vs branch: identical 43 failing names -> docs/TEST_RESULTS.md
- [x] A3 deleted main_results.txt, verify_main.sh

## Phase B — inventory (<=30 min)
- [x] docs/INVENTORY.md (before + after) + screenshots

## Phase C — must ship
- [x] C1 design system + every screen rebuilt; before/after 1440/1280/1024
- [x] C2 custom types (0027), safe changes, link kinds, list_types
- [x] C3 one-step New record sheet (same form edits)
- [x] C4 complete CRUD, Archived, typed delete, bulk
- [x] C5 Guide (public/kb/guide.md)

## Phase D (cut from bottom first: D6 -> D4 -> D3 -> presence -> D5)
- [x] D1 Outline  - [x] D2 Realtime+presence  - [x] D3 Flag/review  - [x] D4 Templates
- [x] D5 Completeness  - [x] D6 Saved views  - [ ] D7 real data (BLOCKED: no backups/)  - [x] D8 deploy guard

## Final (from 16:00)
verify_all from fresh clone; full suite vs main baseline; browser tests (Case Study type, one-save create,
rollback, duplicate warning, disallowed rel, proposal, archive->delete, conflict); keyboard pass;
1024px no h-scroll; docs; reseed; leave demo server + supabase running.

---
# Run 1 (complete)

T0 = 2026-11-02 02:58 local. Run mode: **DEGRADED** (no Supabase dev project, no Google
credentials, no LLM key, no Vercel token; local Supabase stack via Docker is available).

## Adaptation to the real repo (the wrapper assumed a JS app; this repo is not one)

| Wrapper assumption | Real repo | Decision |
|---|---|---|
| React/Next frontend | Static `public/index.html` (vanilla JS, 3D map) + one Python WSGI app (`api/index.py`) on Vercel | Keep. New KB workspace is `public/kb/` (vanilla JS, no build step). |
| React Flow | No React anywhere | **Cytoscape.js**, vendored into `public/vendor/` (CSP is `script-src 'self'`). |
| TS MCP SDK | Python service layer | **Python MCP SDK** so MCP and HTTP share ONE service module (the wrapper's harder rule). |
| zod | No pydantic in the Vercel bundle (bundle is at its size limit) | Hand-written validators in `web/lib/kb/validate.py`, no new deploy dependency. |
| Supabase Realtime | CSP `connect-src 'self'`, no supabase-js in the app | Change feed over `kb.audit_log` polled via `/api/kb/changes` (RLS-scoped, cursor). Realtime = ROADMAP. |
| No auth → email login | Google Workspace SSO with verified `hd` already in production | Keep SSO. KB roles layered on top. Local tests mint HS256 tokens against the local stack. |
| `nodes`/`edges` tables | `public.nodes/edges` are a **pipeline projection replaced wholesale on every build** | New schema **`kb`** for authored records. Projection untouched; live app unaffected. |

## Milestones

- [x] **M1 Schema** — `db/migrations/0022_kb_schema` (+down). `kb.node_types`, `kb.edge_types`,
  `kb.edge_type_rules`, `kb.nodes`, `kb.edges`, `kb.resources`, `kb.node_resources`, `kb.tags`,
  `kb.node_tags`, `kb.memberships`, `kb.api_tokens`, `kb.audit_log`, `kb.proposals`,
  `kb.import_runs` (0024). Common columns, constraints, indexes, audit + cascade triggers.
  Accept: up/down/up on fresh local DB; `tests/test_kb_schema.py` green.
- [x] **M2 Roles + RLS** — admin/editor/contributor/viewer in `kb.memberships`; RLS on every kb table;
  `ADMIN_EMAILS` bootstrap script. Accept: `tests/test_kb_rls.py` (direct SQL as each role).
- [x] **M3 Service + API** — `web/lib/kb/` service, `/api/kb/*` routes. Accept: `tests/test_kb_api.py`.
- [x] **M4 Shell** — `public/kb/` design system, sidebar, ⌘K, dashboard, toasts, dialogs.
- [x] **M5 CRUD UI** — list/filter/side panel/conflict dialog/inline course create. Accept: Playwright.
- [x] **M6 Graph** — Cytoscape neighbourhood view. Accept: Playwright.
- [x] **M7 Collaboration** — optimistic UI, change feed, concurrency script.
- [x] **M8 Sheets import** — fetch/stage/validate/dry-run/apply, idempotent, synthetic fixture.
- [x] **M9 MCP server** — `mcp_server/kb_server.py`, token auth, all tools, automated test.
- [x] **M10 Skills + plugin** — skills inside `plugins/ik-knowledge-assistant/` (PROGRESS D8).
- [x] Phase 5 handoff. Phase 4: all steps PASS, including the full-suite regression run (re-run: 1089 pass, no regressions).

Cut order (from the wrapper): presence → MCP validation tools → plugin skeleton → graph filters
beyond type → Sheets apply.
