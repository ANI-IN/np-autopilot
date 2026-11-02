# Test results — 2026-11-02 (local Supabase stack, Windows 11, Python 3.12, Chrome)

Only measured results are stated. Nothing here was run against a shared or
production database.

## Baseline before any change

| Run | Result |
|---|---|
| `main`, no DB (CI-like) | 892 passed, 12 failed, 187 skipped — all 12 Windows-environment failures |
| `main`, local DB | 998 passed, 22 failed, 21 errors, 50 skipped — list in `docs/baseline-failures.txt` (root cause: `project_graph.py` cannot load the committed graph into a fresh DB, `corpus_names_a_file`) |

## KB tests (last run of each file after its final change)

| File | Result |
|---|---|
| `tests/test_kb_schema.py` + `tests/test_kb_rls.py` | 27 passed |
| `tests/test_kb_api.py` + `tests/test_kb_e2e.py` | 44 passed (30 API + 14 browser, E2E under production CSP headers) |
| `tests/test_kb_concurrency.py` | 3 passed |
| `tests/test_kb_import.py` | 6 passed |
| `tests/test_kb_mcp.py` | 6 passed |
| `tests/test_kb_plugin.py` (+ taxonomy guard) | 11 passed |
| Repo guard tests touched by the change (`test_login_flow`, `test_lazy_route_table`, `test_taxonomy_single_source`, `test_pipeline_docs`, `test_documented_constraints_are_enforced`, `test_no_contact_data_in_tracked_files`) | pass |
| CI-like (no DB): KB files | 4 passed, 85 skipped — listed in `tests/ci-skips.yaml` |

## `scripts/verify_all.sh --fresh-clone --reset-db --perf`

| Step | Result |
|---|---|
| Fresh clone of the branch → clean `uv` install → compileall → `node --check` | PASS |
| `supabase db reset` → 25 migrations from 0001 → `down --to 0021` → `up` | PASS (projection step failed as on `main`) |
| ruff (E9 + pyflakes) on all KB code | PASS |
| Plugin server copy in sync; `claude plugin validate --strict` | PASS |
| No server key names / JWTs in `public/`; `.env` untracked; no secret-shaped strings in `git log -p` | PASS |
| RLS enabled and policies present on every `kb` table | PASS |
| **Full suite + regression comparison vs baseline** | **PASS** (re-run 2026-11-02, `bash scripts/verify_all.sh`): 1089 passed, 22 failed, 21 errors, 50 skipped in 6m31s — every failure and error is in `docs/baseline-failures.txt`; all KB tests pass; `VERIFY: ALL PASS` |

## Concurrency (measured)

- Two sessions edit the same record from version 1 → exactly one 200, one 409 with
  the winner's record.
- 20 parallel create+connect (5 racing on one name) → 16 created, 4 refused as
  duplicates, 0 other errors, **283 ms** total; 16 modules ↔ 16 edges (no orphans);
  audit inserts match rows created.
- 20 parallel edge creates racing an archive of the shared endpoint → 0 orphans.

## Performance (synthetic: 5,000 nodes, 15,000 edges; 40 runs each; in-process WSGI incl. token verification and RLS)

| Request | p50 ms | p95 ms | max ms |
|---|---|---|---|
| list: first page (updated) | 16.2 | 18.7 | 20.6 |
| list: type=topic sorted by name | 12.6 | 13.6 | 13.8 |
| list: text filter | 11.7 | 13.2 | 15.1 |
| search: full text | 20.1 | 22.9 | 27.4 |
| search: fuzzy (typos) | 29.8 | 33.3 | 50.0 |
| neighbourhood depth 1 | 14.2 | 18.7 | 20.4 |
| neighbourhood depth 2 | 17.8 | 122.5 | 141.7 |
| neighbourhood of a 600-edge hub (capped: 300 of 607 returned) | 112.9 | 128.7 | 135.4 |
| node detail of the hub | 24.2 | 26.4 | 28.6 |

Laptop → local Docker Postgres. Production adds network latency to Supabase;
these numbers say nothing about capacity under concurrent load beyond the 20-writer test.

## Live checks

- MCP + Claude Code: `claude -p` with the server via `--mcp-config` answered a
  retrieval question from the local KB — **VERIFIED**.
- Live Google Sheets import: **UNTESTED** (no credentials).
- Vercel preview deploy: **NOT RUN** (no token).
