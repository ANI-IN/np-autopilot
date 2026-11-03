# Architecture — one source of truth (run 6, 2026-11-03)

**Decision (run 6, A2): the `kb` schema is the single source of truth for
everything a person sees or edits.** Every graph and view reads `kb`: the
knowledge base Graph page, Outline, Who teaches what, Programme timeline, and
the NP Autopilot map at `/`. The old tables (`nodes`, `edges`, `node_sources`,
`node_layout`, `files`, `projection_meta`, the curation tables) remain only as
the INTAKE of the NP Autopilot pipeline. They flow into `kb` through the
scheduled one-way sync, and nothing that users see reads them directly.

```
 Google Drive / Sheets (read-only corpus)
        │  pipeline/00_fetch_drive.py … 04_build_graph.py, project_graph.py
        ▼
 OLD TABLES (public.*): nodes · edges · node_sources · node_layout · files
                        projection_meta · curation_notes / aliases (admin curation)
        │  ONE-WAY sync, web/lib/kb/sync.py: hourly (pg_cron → /api/cron/kb-sync),
        │  "Sync now", or the first import. Checksums, conflicts kept, legacy rules
        ▼
 KB (kb.*): nodes · edges · resources · node_types · edge_types · tags · …
        │  every write → audit trigger → kb.changes (the change feed)
        ├──► /api/kb/*   service.py (RLS as the caller) ──► /kb/ workspace: lists, record,
        │                                                   Outline, Graph, Who teaches what,
        │                                                   Programme timeline, Data quality …
        ├──► /api/kb/graph  (the one graph read API, docs/CONTRACTS.md §1)
        │         └──► the knowledge base Graph page AND the NP Autopilot map at "/"
        ├──► /api/structure, /node, /neighbourhood, /search, /overview, /staffing,
        │    /coverage, /me  (the map's routes: same response shapes, now read from kb)
        └──► MCP server (through HTTP)
 Live updates: kb.changes → Supabase Realtime (polling /api/kb/changes as the fallback)
```

### Readers of the old tables that must move to kb (inventory, run 6 A2)

| Reader | Reads | Seen by | Moves to |
|---|---|---|---|
| `api/structure.py` → `data.structure`, `structure_etag` | nodes, edges, node_layout, projection_meta | everyone on `/` (the map) | kb nodes/edges/graph_positions; ETag from the newest `kb.changes` id |
| `api/overview.py` → `data.overview` | nodes, edges | `/` landing view | kb |
| `api/node.py` → `data.node`, `provenance`, `node_detail` | nodes, edges, node_sources, files | `/` record panel | kb record + its links (resources) and the sync's source reference |
| `api/neighbourhood.py` → `data.neighbourhood` | nodes, edges | `/` expand | kb (`/api/kb/graph?focus=`) |
| `api/search.py` → `data.search` | nodes | `/` search | kb search |
| `api/staffing.py` → `data.domain_subgraph` | nodes, edges | `/` "Who teaches what" | kb (the same rules as `views.teaching_matrix`) |
| `api/coverage.py` → `data.coverage` | nodes, edges | `/` coverage panel | kb |
| `api/me.py` | `count(*) from nodes` | `/` header | kb count |
| `pipeline/gen_landing_stats.py` → `public/stats.json` | nodes | `/` landing numbers | numbers from kb at request time |
| `api/aliases.py`, `api/curate.py` → `curation_service` | curation tables, nodes, edges | admins on `/` (curation) | **stay**: they are pipeline intake administration (they write the intake the sync reads). Recorded as the one exception. |
| `web/lib/kb/sync.py` | all old tables | nobody (it is the sync) | stays: it IS the intake path |
| `eval/kb_parity.py`, `eval/kb_realdata_check.py`, `eval/kb_sync_proof.py`, `pipeline/verify_migration.py`, `pipeline/04_build_graph.py`, `pipeline/curation.py` | old tables | nobody (checks and the pipeline) | stay |

What changes for users of `/`: the map shows what the KB holds. Edits made in
the KB (names, relationships, owners, archiving) appear on the map, and legacy
items follow the KB's legacy flag. Records the sync skips (files as nodes,
provenance edges) are shown through the record's links instead of as nodes.
Access to `/` is unchanged (anyone with an NP role is at least a KB viewer,
`kb.role()`).

---

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
