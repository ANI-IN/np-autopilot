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

### How the map reads kb (run 6, B1: `web/lib/kb/npmap.py`)

- **One module, the same shapes.** `npmap` answers /api/structure, /overview,
  /node, /neighbourhood, /search, /staffing, /coverage and /me with
  web/lib/data.py's response shapes (CONTRACTS §5), from ONE in-memory model of
  the live KB per change-feed head (rebuilt when `max(kb.changes.id)` or the
  live counts move; ~0.8 s on the real data, then cached per process).
- **Vocabulary, translated back.** `config/kb-projection-mapping.yaml` read
  backwards: KB type -> projection type (`session` -> the map's session type,
  `team_member` -> person, ...; a type the projection never had keeps its KB
  key and is carried in the structure); KB relationship (type, source type,
  target type) -> projection relation, with `flip`; the teaching pair split on
  the relationship's own props (`role` = current mastersheet, `older_role` =
  older sheets, class dates read back from the note). Links attached with a
  mapping note (Slides, Code, Assignment, ...) become the artifact nodes they
  came from (`link:<resource id>`). No taxonomy literal in the code.
- **Ids.** A record the sync brought in keeps its projection id
  (`external_id` `np:<id>`), so shared links still open; a KB-made record uses
  its uuid; /api/node and /api/neighbourhood accept either. Relationship ids
  are 32-bit numbers derived from the KB ids (the wire format packs Uint32).
- **Positions** from `kb.graph_positions` (layout `default`, the Graph page's
  shared layout, divided by the sync's scale 4); a record with none is placed
  next to its placed neighbours (deterministic), so the map never re-simulates.
- **Current domains' codes** (SD1-SD4) come from the domain records' `slug`
  field (0033; the sync fills it from the mastersheet), else the name.
- **ETag** = format + newest change id + live counts + the caller's NP and KB
  roles. **Landing numbers** (/api/stats, no session, counts only, through
  `kb.landing_stats()`) replace `public/stats.json`, which stays as the fallback.
- **Live.** The map polls `/api/kb/changes` every 2.5 s (it has no supabase-js;
  every NP member is a KB viewer) and refetches the structure on a relevant
  change (304 when nothing it shows changed); a relationship-type change also
  refetches `/api/kb/types` (a custom type is drawn in the legend with its own
  colour and line style). Positions, the camera and the open panel stay.

**What the KB cannot supply** (the key stays, empty):

| Key | Route | Why |
|---|---|---|
| `label_raw` | structure `raw`, /node | the KB keeps one name |
| `sensitive` | /node | the KB holds no sensitive rows (`false`) |
| provenance `sheet`, `row_num`, `col_num`, `col_name`, `page`, `within_cell`, `ordinal`, `prop`, `evidence`, `entered_at`, `sheet_count` | /node `provenance.corpus[]` | the KB keeps a cited file as a "Source" link (file name + Drive link only) |
| `provenance.hand`, `hand_note` | /node | hand-entered provenance is not imported |
| files as nodes (`file`), `delivers` file edges for unattached files | structure, /neighbourhood | files are links on records; only attached ones appear |
| edge props `rank`, `basis`, `inferred`, `avg_rating`, `via_alias`, `subject_raw`, `cell_order`, `attached_*` | structure, /node detail | not imported (MIGRATION_MAPPING.md) |
| node props outside `mapped_props` (`cross_validated`, `merge_ids`, `pipeline_status`, ...) | structure, /node | not imported |
| archived (legacy) records | every route | the map shows what the KB holds: archived legacy records are not on the map |

**Rollback:** `NP_MAP_SOURCE=old` (Vercel variable) serves every map route from
the old tables again (web/lib/data.py, unchanged) and /api/stats 404s (the page
falls back to `public/stats.json`). Nothing else changes; unset it to return
to kb.

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

## Connectors

The sync (`web/lib/kb/sync.py`, `run`) is one engine; the source it reads is a
**connector** (`web/lib/kb/connectors/`). Today there is one, NP Autopilot
(`connectors/np_autopilot.py`), and `sync.run(conn, ...)` uses it by default:
every call site, CLI flag, route, output key, checksum, lock and table is as
before.

| Step (`connectors/base.py`, `Connector`) | NP Autopilot |
|---|---|
| `name`, `actor_label` | `np_autopilot`, "Sync (NP Autopilot)" |
| `load_config(conn)`: the mapping, checked against the taxonomy | `sync.load_mapping` (`config/kb-projection-mapping.yaml`) |
| `desired_state(conn, config, **opts)`: records, links, relationships, attachments, layout, report, with the source's own rules | `sync.desired_state` (the old tables; `np_categories` for current vs legacy) |
| `exclusions(conn)`: what must never be created again | `legacy_delete.excluded` (`kb.sync_exclusions`, 0037) |
| `after_run(conn, out)`: the finishing step, never cut off by the budget | the legacy rules (`legacy.archive`), once adopted |

The engine does everything else, the same for every source: the lock, the run
log, the diff against `kb.sync_map`, the batched phases, conflicts, "removed
at source", the time budget and resume, the layout, `actor_type='sync'`.

A new source (Google Drive, Uplevel LMS, Atlassian) plugs in by subclassing
`Connector`, returning the desired-state dict the docstring describes,
registering an instance (`connectors.register`) and calling
`sync.run(conn, connector=connectors.get("<name>"))`.
`tests/test_kb_connectors.py` runs a fake one through the engine. Before a
second source runs for real, the bookkeeping needs a `source` column
(`sync_map`, `sync_runs`, `sync_exclusions`), a per-source external-id prefix
(today `np:`) and a lock per source; an incremental cursor, source permissions
and retries are not in the interface yet (`docs/VISION_AND_ROADMAP.md` §3,
item 4).
