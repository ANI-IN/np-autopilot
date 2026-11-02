# HANDOFF — knowledge platform (autonomous run, 2026-11-02)

Branch `auto/knowledge-platform-20261102` (pushed; **not merged, not deployed**).

## 1. Summary

- Run mode: **DEGRADED** — no Supabase dev project, Google, LLM or Vercel credentials
  were available, so everything ran against the **local Supabase stack** (Docker).
- New, additive **`kb` schema** (migrations 0022–0026) for authored knowledge:
  configurable node/edge types with allowed-pair rules, resources (many-to-many),
  tags, proposals, per-user API tokens, an audit log of every write, RLS on every table.
- **`/api/kb/*`** behind the existing single front door; one service module holds every
  rule (validation, roles, optimistic locking, transactions).
- **`/kb/` workspace**: dashboard, lists with filters and cursor pagination, side panel
  with inline editing, conflict dialog, ⌘K palette, Cytoscape graph, approvals,
  settings (tokens, roles, types), data-quality page, CSV export.
- **Sheets importer** (dry run → apply, idempotent, never overwrites app edits),
  **MCP server** (19 tools, verified live with Claude Code), and a **Claude Code
  plugin** with two skills.
- The pipeline projection, the corpus explorer and production were not touched.

## 2. Must-ship checklist

| Item | Status | Evidence |
|---|---|---|
| M1 Schema and data layer | VERIFIED | `tests/test_kb_schema.py` (15); migrations up → down → up on fresh DB (`verify_all.sh --reset-db`) |
| M2 Auth and permissions in the DB | VERIFIED | `tests/test_kb_rls.py` (12): direct SQL as each role; viewer write and contributor archive/delete refused |
| M3 Service/API layer | VERIFIED | `tests/test_kb_api.py` (30): success, 422, 403, 404, 409 conflict, 409 duplicate per family |
| M4 Design system and shell | VERIFIED | `tests/test_kb_e2e.py`, screenshots reviewed; no placeholder controls (role-hidden) |
| M5 CRUD workflows | VERIFIED | E2E: node + inline course, resource (incl. reuse), edge: create → edit → connect → archive → restore |
| M6 Graph view | VERIFIED | E2E: open, expand, details panel in place, filter by type; 300-node cap reported |
| M7 Collaboration | VERIFIED | `tests/test_kb_concurrency.py`: two editors → one wins, one 409; 20 parallel creates → no dupes/orphans, audit rows match; E2E two-session conflict + live update. Presence: deferred (cut #1) |
| M8 Sheets import | VERIFIED on synthetic fixture · live UNTESTED | `tests/test_kb_import.py` (6); docs/MIGRATION_REPORT.md |
| M9 MCP server | VERIFIED (+ live Claude check) | `tests/test_kb_mcp.py` (6) calls every tool incl. denied/approval/expired/revoked paths; `claude -p` retrieval answered from the local KB |
| M10 Skills + plugin | VERIFIED | `claude plugin validate --strict` passes; `tests/test_kb_plugin.py` |
| Phase 4 verification | see §6 | `scripts/verify_all.sh --fresh-clone --reset-db --perf` |

## 3. How to run

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt
db/local/setup.sh                    # Docker; local Supabase on 54322 + pooler 6543
export SUPABASE_DB_URL_SESSION=postgresql://postgres:postgres@127.0.0.1:54322/postgres
export SUPABASE_DB_URL_TRANSACTION=postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres
python pipeline/migrate.py up        # applies 0022–0026 if setup.sh predates them
python eval/kb_dev_server.py 8765    # local only; then open http://127.0.0.1:8765/kb/
```
**Leadership demo:** `docs/DEMO.md` (local sign-in page, fictional seed data,
reset and stop). Locally there is no Google sign-in; the browser tests inject a session minted with
the test-only secret (`tests/kb_support.py`). Verification:
`bash scripts/verify_all.sh [--fresh-clone] [--reset-db] [--perf]`.
MCP: docs/MCP.md (token from Settings → API tokens; `.mcp.json` from
`mcp_server/mcp.example.json`, or install the plugin).

## 4. ACTION REQUIRED FROM OWNER

1. **Review the PR** for `auto/knowledge-platform-20261102` → `main`. Nothing was merged.
2. **Apply the migrations to a DEV Supabase project first**, then production:
   ```bash
   export SUPABASE_DB_URL_SESSION=<session pooler URL>     # dev project
   mkdir -p backups && pg_dump "$SUPABASE_DB_URL_SESSION" --schema=public --schema=kb > backups/pre-kb-$(date +%F).sql
   python pipeline/migrate.py status && python pipeline/migrate.py up   # 0022–0026, additive
   ```
   Repeat on production after the dev smoke test (db/window/backup.sh for the full
   backup procedure). Rollback: `python pipeline/migrate.py down --to 0021` (drops only `kb`).
3. **Bootstrap admins:** each admin signs in once at `/` (creates their profile), then
   `ADMIN_EMAILS=a@interviewkickstart.com,b@… python pipeline/kb_admins.py`.
4. **Vercel:** no new environment variables are needed for the web app (`/kb/` uses
   the existing `SUPABASE_*` and `GOOGLE_OAUTH_CLIENT_ID`). Open a **preview** of the
   branch and load `/kb/`; previews must point at the dev database.
5. **Sheets import (live):** share the workbook read-only with the service account,
   then `KB_SHEETS_ID=<id> NP_DRIVE_SA_KEY=<path> python pipeline/kb_import_sheets.py --as you@… --report /tmp/dry.json`;
   adjust `config/kb-sheets-mapping.yaml` to the real tab/header names; then `--apply` on dev.
6. **Supabase dashboard:** nothing required for this build (no Realtime used; Google SSO
   already configured). For the ROADMAP Realtime item: enable Realtime on `kb` tables
   and add the realtime host to the CSP `connect-src`.
7. **Missing credentials, for a FULL-mode run next time:** a dev project
   `SUPABASE_DB_URL_SESSION`/`_TRANSACTION` with `SUPABASE_ENV=dev`; `NP_DRIVE_SA_KEY`
   path + `KB_SHEETS_ID`; `VERCEL_TOKEN` (preview deploys only).

## 5. Decisions and assumptions to review

See PROGRESS.md "Decisions" D1–D11. The ones most worth a second look:
- D3 separate `kb` schema (vs. making the projection editable);
- D5 no email/password login (production SSO kept);
- D6 polling change feed instead of Supabase Realtime;
- D7 MCP via HTTP + per-user tokens (migration 0025 grants `authenticated` execute on
  the SECURITY DEFINER token resolver);
- D8 skills inside the new plugin rather than at the repo root;
- starting vocabulary of node/edge types (0022) — admins can extend it in Settings.

## 6. Verification, blockers, limitations, performance

Full detail: docs/TEST_RESULTS.md.

- **Verified:** fresh clone + clean install; every migration from 0001 on a reset local
  DB with the kb round trip; lint; plugin validation; security spot checks; RLS on
  every kb table; every KB test file passing (91 KB tests: 27 schema/RLS, 30 API,
  14 browser E2E, 3 concurrency, 6 import, 6 MCP, 5 plugin).
- **Full suite + regression comparison:** PASS on re-run (`bash scripts/verify_all.sh`):
  1089 passed, 22 failed, 21 errors, 50 skipped. Every failure and error is a
  pre-existing baseline item (`docs/baseline-failures.txt`); no regressions;
  `VERIFY: ALL PASS`.
- **Pre-existing, not fixed:** `project_graph.py` fails on a fresh DB
  (`corpus_names_a_file`); 12 Windows-only test failures (docs/AUDIT.md).
- **Limitations:** no presence indicators; collaboration uses 4-second polling, not
  Realtime; the HTTP MCP transport is single-token (one user), so Claude.ai remote
  use needs the OAuth design first; duplicate adoption in imports is manual; edge
  type cannot be changed after creation (archive and re-create).
- **Performance (5k nodes / 15k edges, local):** list p50 12–16 ms, search p50
  20–30 ms, neighbourhood depth-1 p50 14 ms, depth-2 p95 123 ms, 600-edge hub
  113 ms p50 (capped at 300 of 607).

## 7. Next session

The top five from docs/ROADMAP.md: apply to dev → prod with admin bootstrap; real
Sheets import; remote MCP with per-user OAuth for Claude.ai; duplicate-adoption flow
for import; Realtime + presence.
