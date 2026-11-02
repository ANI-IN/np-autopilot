# Architecture — KB workspace (knowledge platform)

```
Browser /kb/ (vanilla JS, Cytoscape)        Claude Code / Claude.ai
   │  Supabase session (Google SSO)            │  MCP (stdio | streamable HTTP)
   ▼                                           ▼
api/index.py  ── /api/kb/* ──►  _serve_kb ◄── mcp_server/kb_server.py (HTTP client)
   │   identify(): Supabase JWT  │  or  ikkb_ token → kb.resolve_token → owner
   │   one connection, role `authenticated`, caller's claims (RLS)
   ▼
api/kb_routes.py   (parse → call → shape; no rules)
   ▼
web/lib/kb/service.py   ← THE business logic: validation, role checks,
   │                       optimistic locking, transactions, proposals
   ▼
Postgres (Supabase)  schema kb: RLS on every table, triggers for authorship,
                     version bumps, audit log, edge rules, archive cascade

pipeline/kb_import_sheets.py ── acts as a named admin ──► service (actor_type=import)
pipeline/kb_admins.py        ── ADMIN_EMAILS bootstrap (operator, owner connection)
```

## Principles

1. **One front door.** Every HTTP request enters `api/index.py`; identity is
   established before any module loads or connection opens (the repo's existing
   rule, extended to `/api/kb/*`).
2. **One rulebook.** `web/lib/kb/service.py` is the only place KB rules live. The
   HTTP routes, the MCP server (through HTTP) and the Sheets importer (directly)
   all call it.
3. **The database is the last line.** RLS (0023) and triggers enforce roles,
   uniqueness, edge rules, archive cascades and audit even if the service is
   bypassed — tested directly in `tests/test_kb_rls.py` / `test_kb_schema.py`.
4. **Never the whole graph.** Pages ≤200, neighbourhoods ≤2 hops and ≤300 nodes,
   with `total`/`truncated` reported.
5. **Additive.** New schema, new routes, new page. The pipeline projection, the
   explorer and the curation tables are untouched.

## Collaboration model

- **Optimistic locking** everywhere: writes carry `version`; mismatch → 409 with
  the current record; the UI shows a field diff and offers reload, or overwrite
  for editors.
- **Change feed** instead of Supabase Realtime: `GET /api/kb/changes?since=<audit
  id>` (RLS-scoped) polled every 4 s while the tab is visible, with exponential
  back-off on failure and a refetch on recovery. Lists refresh; an open record
  that changed elsewhere reloads (or warns, if you are mid-edit). Chosen because
  the CSP allows only same-origin connections and the app has no supabase-js;
  Realtime is a ROADMAP item.
- **Optimistic UI** for inline edits and tags, rolled back with a toast on error.

## Why these choices

| Choice | Reason |
|---|---|
| Vanilla JS, no framework | The repo has no build step and a strict CSP; the explorer is vanilla. |
| Cytoscape.js (not React Flow) | Framework-free, canvas renderer comfortable at 300 nodes, built-in layouts; vendored under `public/vendor/` (MIT). |
| Python MCP SDK | Shares the service layer instead of re-implementing it in TypeScript. |
| MCP over HTTP + per-user token | No database credential on users' machines; RLS acts as the user. |
| Hand-written validation | The Vercel bundle is at its size limit; no pydantic in the function. |

## Files

| Path | Role |
|---|---|
| `db/migrations/0022–0026` | schema, RLS, import runs, token resolution, course shape + link health + people |
| `web/lib/kb/{service,validate,errors}.py` | rules |
| `api/kb_routes.py`, `api/index.py::_serve_kb` | HTTP |
| `public/kb/{index.html,kb.css,kb.js}` | UI (design system in `docs/DESIGN_SYSTEM.md`) |
| `mcp_server/kb_server.py` | MCP server |
| `plugins/ik-knowledge-assistant/` | Claude Code plugin (MCP config + 2 skills) |
| `pipeline/kb_import_sheets.py`, `pipeline/lib/kb_sheets.py`, `config/kb-sheets-mapping.yaml` | Sheets import |
| `pipeline/kb_admins.py` | admin bootstrap |
| `eval/kb_dev_server.py` | local server for the browser/MCP tests (never deployed) |
| `scripts/verify_all.sh`, `scripts/kb_perf.py` | verification |
