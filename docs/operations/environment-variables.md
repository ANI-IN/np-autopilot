# Environment variables

Every environment variable the code reads, found with
`git grep -nE "environ|getenv"` over `api/`, `web/`, `pipeline/`, `eval/`,
`scripts/`, `mcp_server/`, `tests/` and the shell scripts. **Names only:
values are never written in this repository**, except the stack's fixed local
defaults (see [testing.md](testing.md) §1). The template for a local file is
[`.env.example`](../../.env.example); the real `.env` is gitignored.

Where a variable is set:

- **Vercel P / Pv**: the Vercel project's Production / Preview environment.
  A change takes effect on the next deployment.
- **Vault**: a Supabase Vault secret (not an environment variable; listed for
  completeness).
- **Local**: your shell or the gitignored `.env` (operator commands, local
  servers). **CI**: `.github/workflows/ci.yml`.

## Rules that hold for every environment

- **Never set in Vercel:** `SUPABASE_SERVICE_ROLE_KEY` (nothing reads it; it
  bypasses RLS), `SUPABASE_DB_URL_SESSION` (the session pooler connects as the
  owner; it is for migrations from a laptop), and any `DEV_*` name.
  `scripts/deploy_dev_preview.sh` refuses to deploy if the first two are set
  for Preview.
- **`DEV_*` names are local only.** They hold the DEV project's values for
  `scripts/dev_db.py` and `scripts/deploy_dev_preview.sh`. In Vercel the same
  values go under the names the app reads (`SUPABASE_URL`, ...), see
  [dev-deploy.md](dev-deploy.md) step 2.
- **Never the direct database host** (`db.<ref>.supabase.co`): it is IPv6-only
  on this project and is refused at runtime (`pipeline/lib/db.py`).

## The deployed app (read by `api/` and `web/`)

| Name | Purpose | Required | Set in | Read by |
|---|---|---|---|---|
| `SUPABASE_URL` | The Supabase project URL: the JWKS location and token issuer, GoTrue, and the Realtime check. Served to the browser by `/api/config`. | yes | Vercel P, Pv | `api/config.py`, `web/lib/auth.py`, `web/lib/gotrue.py`, `api/kb_routes.py` |
| `SUPABASE_ANON_KEY` | The public anon key the browser and GoTrue calls use; grants nothing on its own. | yes | Vercel P, Pv | `api/config.py`, `web/lib/gotrue.py`, `api/kb_routes.py` |
| `SUPABASE_DB_URL_TRANSACTION` | The **transaction pooler** (port 6543) for every request and for the sync's owner connection. Refused if it points at port 5432 or the direct host. | yes | Vercel P, Pv; Local for local servers | `pipeline/lib/db.py` (through `web/lib/data.py`, `web/lib/kb/sync_api.py`) |
| `SUPABASE_JWT_SECRET` | HS256 secret for Supabase access tokens **without** a `kid`. Not needed when the project publishes JWKS (ES256 / RS256 signing keys). | only for HS256 projects | Vercel P, Pv; Local (tests) | `web/lib/auth.py`, `tests/kb_support.py`, eval servers |
| `GOOGLE_OAUTH_CLIENT_ID` | The Google OAuth client: the button's client id and the `aud` a Google ID token must carry. | yes | Vercel P, Pv | `api/config.py`, `web/lib/auth.py` |
| `NP_ALLOWED_HD` | The one allowed Workspace domain for sign-in and for the per-request check. The database hook and the invitation CHECK hard-code `interviewkickstart.com` regardless. | no (default `interviewkickstart.com`) | Vercel P, Pv | `web/lib/auth.py`, `api/config.py`, `pipeline/grant_access.py` |
| `NP_SHARED_ACCOUNTS` | Comma-separated local parts of shared mailboxes, flagged as `shared_account` in the request audit line. | no (empty) | Vercel P, Pv | `web/lib/auth.py` |
| `KB_SYNC_SECRET` | The bearer secret for `POST /api/cron/kb-sync`; at least 24 characters, otherwise the route refuses everyone. Must equal the Vault secret `kb_sync_secret`. | yes for the schedule | Vercel P, Pv | `web/lib/kb/sync_api.py`, `scripts/deploy_dev_preview.sh` (length check) |
| `KB_SYNC_ENABLED` | The sync's kill switch: `false`, `0`, `no` or `off` stops every run (cron and Sync now). | no (default `true`) | Vercel P, Pv | `web/lib/kb/sync.py`, `web/lib/kb/sync_api.py` |
| `KB_SYNC_BUDGET_SECONDS` | Seconds per sync run before it stops and saves its place. Keep well under `maxDuration` (60 s, `vercel.json`). | no (default `10`, minimum `3`) | Vercel P, Pv | `web/lib/kb/sync_api.py`, `scripts/kb_sync_timing.py` |
| `KB_REALTIME_ORIGIN` | Turns on Supabase Realtime for live updates when it equals `SUPABASE_URL`; the same origin must be in the CSP (`scripts/kb_csp_origin.py`). Unset means polling only. | no | Vercel P, Pv | `api/kb_routes.py`, `scripts/kb_csp_origin.py` |
| `NP_MAP_SOURCE` | `old` makes the "/" map and its routes read the old tables again (the rollback switch). Anything else, or unset, reads the KB. | no (default `kb`) | Vercel P (only for a rollback) | `web/lib/kb/npmap.py`, `api/index.py`, `api/structure.py` and the other `/api/*` read modules |

Supabase Vault (set in the SQL editor as the owner, see
[dev-deploy.md](dev-deploy.md) step 6): `kb_sync_secret` (same value as
`KB_SYNC_SECRET`) and, for a protected preview only, `kb_sync_vercel_bypass`.
The Google provider's client id and **client secret** are set in the Supabase
dashboard (Authentication → Providers → Google), not in an environment
variable.

## Operator commands (a laptop or CI; never Vercel)

| Name | Purpose | Required | Set in | Read by |
|---|---|---|---|---|
| `SUPABASE_DB_URL_SESSION` | The **session pooler** (port 5432), as the table owner: migrations, the import and sync from the command line, the legacy tools, role grants, the test suite. | yes for these commands | Local, per command | `pipeline/migrate.py`, `kb_import_projection.py`, `kb_import_sheets.py`, `kb_legacy.py`, `kb_legacy_delete.py`, `kb_admins.py`, `grant_access.py`, `curation.py`, `project_graph.py`, `verify_migration.py`, `gen_landing_stats.py`, `pipeline/lib/db.py`, `tests/conftest.py` |
| `ADMIN_EMAILS` | Comma-separated IK addresses to make KB admins (each must have signed in once). | yes for `kb_admins.py` | Local, per command | `pipeline/kb_admins.py` |
| `NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION` | Exactly `yes` lets `kb_legacy_delete.py` run against production (GO_LIVE step 6). | no | Local, for that one command only | `pipeline/kb_legacy_delete.py` |
| `KB_SHEETS_ID` | The Google Sheet to import (or `--sheet-id`). | for the Sheets import | Local | `pipeline/kb_import_sheets.py` |
| `NP_DRIVE_SA_KEY` | Path to the Drive service-account key file, kept **outside** the repo. | for Drive reads | Local | `pipeline/00_fetch_drive.py`, `pipeline/kb_import_sheets.py` |
| `NP_DRIVE_CONFIG` | Path to the Drive config. | no (default `config/drive.yaml`) | Local | `pipeline/lib/paths.py` |
| `NP_CORPUS_PATH` | The read-only corpus folder. | no (documented default) | Local | `pipeline/lib/paths.py`, `pipeline/01_walk_corpus.py` |
| `NP_BUILD_LOG` | Where the pipeline writes its build log. | no (default `BUILD_LOG.md`) | Local; tests and `db/local/setup.sh` redirect it | `pipeline/lib/paths.py` |
| `NP_LANDING_STATS` | Where `gen_landing_stats.py` writes. | no (default `public/stats.json`) | Local; tests redirect it | `pipeline/gen_landing_stats.py` |
| `NP_AS_OF` | Overrides "today" (ISO date) for the build. | no | Local | `pipeline/04_build_graph.py`, `pipeline/lib/teaching.py` |
| `NP_MASTERSHEET_DRIVE_ID` | The mastersheet's Drive id for the freshness check. | no | Local | `pipeline/lib/freshness.py` |
| `NP_MASTERSHEET_DIR` | Local mastersheet cache. | no (default `~/.config/np-autopilot/mastersheet`) | Local | `pipeline/lib/freshness.py`, `pipeline/fetch_mastersheet.py` |
| `NP_FRESHNESS_SKIP` | A **reason** to skip the mastersheet freshness check (printed). | no | Local; tests set it | `pipeline/lib/freshness.py` |
| `DEV_SUPABASE_DB_URL` | The DEV project's session pooler URL. | for `dev_db.py` | Local (`.env`) | `scripts/dev_db.py` |
| `DEV_SUPABASE_URL` | The DEV project URL (its ref must match the database URL's). | for `dev_db.py`, the preview deploy | Local (`.env`) | `scripts/dev_db.py`, `scripts/deploy_dev_preview.sh` |
| `VERCEL_TOKEN` | A Vercel token for the CLI instead of `vercel login`. | no | Local (`.env`) | `scripts/deploy_dev_preview.sh` |
| `VERCEL_BYPASS` | Vercel "Protection Bypass for Automation" secret, for the preview smoke tests. | no | Local | `scripts/deploy_dev_preview.sh` |
| `WINDOW_DSN` | The database for the window scripts (backup, restore of the projection). | for `db/window/*.sh` | Local | `db/window/_guard.sh`, `backup.sh`, `restore_projection.sh` |
| `GITHUB_TOKEN` | Lets the repo-visibility check use the GitHub API. | no | CI (`github.token`) | `pipeline/check_repo_private.py` |

`KB_DEV_DUMP_URL` is not set by people: `scripts/dev_db.py backup` sets it
for the `pg_dump` container it starts, so the URL never appears on a command
line.

`DEV_SUPABASE_ANON_KEY` and `DEV_SUPABASE_SERVICE_ROLE_KEY` appear in
[dev-deploy.md](dev-deploy.md) as names for the DEV project's keys in `.env`.
**No code reads them**: the anon key's value is copied into Vercel Preview as
`SUPABASE_ANON_KEY`; the service-role key is never copied anywhere.

## The MCP server (the user's machine)

| Name | Purpose | Required | Set in | Read by |
|---|---|---|---|---|
| `KB_MCP_TOKEN` | The person's `ikkb_` API token. | yes | the MCP client config, or the plugin's prompted value | `mcp_server/kb_server.py` |
| `KB_API_URL` | The deployment base URL. | no (default `http://127.0.0.1:8765`) | the same | `mcp_server/kb_server.py` |
| `KB_APP_URL` | Base for record links in results. | no (default `KB_API_URL`) | the same | `mcp_server/kb_server.py` |

## Local servers, tests and measurements

| Name | Purpose | Default | Read by |
|---|---|---|---|
| `NP_TEST_DSN` / `NP_TEST_DSN_TRANSACTION` | The test database (session / transaction pooler) when the `SUPABASE_DB_URL_*` names are unset. | the local stack | `tests/conftest.py`, `pipeline/lib/db.py`, `scripts/kb_graph_perf.py` |
| `NP_TEST_SESSION_POOLER_DSN` / `NP_TEST_TRANSACTION_POOLER_DSN` | Real poolers for the read-only canaries. | unset (tests skip) | `tests/test_read_only_through_pooler.py` |
| `NP_ALLOW_PROD_TESTS` | Exactly `1` allows a test run against production (read-only tests only). | unset | `tests/conftest.py`, `pipeline/lib/db.py` |
| `NP_DB_READ_ONLY` | `1` makes every connection read-only; set by the test guard. | unset | `pipeline/lib/db.py`, `tests/db_guard.py` |
| `PGOPTIONS` | libpq options; the test guard appends a read-only option. | | `tests/db_guard.py` |
| `NP_SKIP_LEDGER` | `enforce` makes skip counts match `tests/ci-skips.yaml`. | unset | `tests/conftest.py`; CI sets it |
| `NP_SKIP_LEDGER_FILE` | Another ledger file. | `tests/ci-skips.yaml` | `tests/conftest.py` |
| `NP_VERIFY_URL` | A live deployment for one opt-in test. | unset (skips) | `tests/test_exclusion_is_deny_by_default.py` |
| `KB_REALDATA_PASSWORD` | The local real-data admin's password when building. | a fixed local default | `eval/kb_realdata_db.py` |
| `KB_LOCAL_DB` | The real-data server's database name. | `kb_realdata` | `eval/kb_realdata_server.py` |
| `KB_LOCAL_DB_CONTAINER` | The local Postgres container for `docker exec psql`. | `supabase_db_np-autopilot-test` | `eval/kb_realdata_db.py` |
| `NP_MEASURE_BASE` | Site for the signed-in measurement script. | the production site | `eval/measure_signed_in.py` |

## Names that look like variables but are not read here

- **`ANTHROPIC_API_KEY`**: no code in this repository reads it. It appears
  only in `scripts/verify_all.sh`, which fails if the name shows up anywhere
  under `public/`. A Claude client that uses the MCP server has its own
  configuration outside this repository.
- **`SUPABASE_SERVICE_ROLE_KEY`**: read by nothing;
  `tests/test_login_flow.py` asserts no API route reads it, and
  `scripts/verify_all.sh` and CI fail if a service-role key shape appears
  under `public/`.
- **`PROD_SESSION_URL`, `PROD`** in [GO_LIVE.md](GO_LIVE.md): shell
  placeholders for the command line, not variables any code reads.
