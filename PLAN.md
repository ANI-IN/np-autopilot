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
