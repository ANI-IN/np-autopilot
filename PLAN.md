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

- [ ] **M1 Schema** — `db/migrations/0022_kb_schema` (+down). `kb.node_types`, `kb.edge_types`,
  `kb.edge_type_rules`, `kb.nodes`, `kb.edges`, `kb.resources`, `kb.node_resources`, `kb.tags`,
  `kb.node_tags`, `kb.memberships`, `kb.api_tokens`, `kb.audit_log`, `kb.proposals`,
  `kb.import_runs`/`kb.import_rows`. Common columns, constraints, indexes, audit + cascade triggers.
  Accept: up/down/up on fresh local DB; `tests/test_kb_schema.py` green.
- [ ] **M2 Roles + RLS** — admin/editor/contributor/viewer in `kb.memberships`; RLS on every kb table;
  `ADMIN_EMAILS` bootstrap script. Accept: `tests/test_kb_rls.py` (direct SQL as each role).
- [ ] **M3 Service + API** — `web/lib/kb/` service, `/api/kb/*` routes. Accept: `tests/test_kb_api.py`.
- [ ] **M4 Shell** — `public/kb/` design system, sidebar, ⌘K, dashboard, toasts, dialogs.
- [ ] **M5 CRUD UI** — list/filter/side panel/conflict dialog/inline course create. Accept: Playwright.
- [ ] **M6 Graph** — Cytoscape neighbourhood view. Accept: Playwright.
- [ ] **M7 Collaboration** — optimistic UI, change feed, concurrency script.
- [ ] **M8 Sheets import** — fetch/stage/validate/dry-run/apply, idempotent, synthetic fixture.
- [ ] **M9 MCP server** — `mcp/kb_server.py`, token auth, all tools, automated test.
- [ ] **M10 Skills + plugin** — `skills/`, `plugins/ik-knowledge-assistant/`.
- [ ] Phase 4 verification (`scripts/verify_all.sh`) and Phase 5 handoff.

Cut order (from the wrapper): presence → MCP validation tools → plugin skeleton → graph filters
beyond type → Sheets apply.
