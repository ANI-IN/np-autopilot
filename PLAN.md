# PLAN — Knowledge Platform (autonomous run, branch `auto/knowledge-platform-20261102`)

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
- [x] Phase 5 handoff. Phase 4: all steps PASS except the final full-suite regression run (stopped by the low-memory reaper; re-run `scripts/verify_all.sh`).

Cut order (from the wrapper): presence → MCP validation tools → plugin skeleton → graph filters
beyond type → Sheets apply.
