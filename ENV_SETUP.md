# ENV_SETUP

Names and purposes only, never values. Template: `.env.example`. Status is what
the autonomous run on 2026-11-02 found in its own environment (presence check only).

| Variable | Required? | Used by | Where to get it | Server-only? | Status (2026-11-02) |
|---|---|---|---|---|---|
| `SUPABASE_DB_URL_SESSION` | Required (migrations, loaders, MCP token lookup) | `pipeline/migrate.py`, `project_graph.py`, `kb_admins.py`, `kb_import_sheets.py`, `mcp_server/` | Supabase dashboard → Connect → Session pooler (5432) | Yes | missing (local stack used) |
| `SUPABASE_DB_URL_TRANSACTION` | Required (web app) | `web/lib/data.py`, `mcp_server/` | Supabase → Connect → Transaction pooler (6543) | Yes | missing (local stack used) |
| `SUPABASE_URL` | Required (web) | `api/config.py`, `web/lib/auth.py` (JWKS, issuer) | Supabase → Settings → API | No (public) | missing |
| `SUPABASE_ANON_KEY` | Required (web) | `api/config.py` | Supabase → Settings → API | No (public by design) | missing |
| `SUPABASE_JWT_SECRET` | Optional (HS256 projects / local stack only) | `web/lib/auth.py` | Supabase → Settings → JWT (legacy) | **Yes** | missing |
| `GOOGLE_OAUTH_CLIENT_ID` | Required (sign-in) | `api/config.py`, `web/lib/auth.py` | Google Cloud → Credentials → OAuth client | No (public) | missing |
| `NP_ALLOWED_HD` | Required | `api/config.py`, auth | Fixed: `interviewkickstart.com` | No | default in template |
| `NP_SHARED_ACCOUNTS` | Optional | auth, 0014 | Ops list of shared mailboxes | No | missing |
| `ADMIN_EMAILS` | Required once (KB bootstrap) | `pipeline/kb_admins.py` | Owner decision | Yes (operator) | missing |
| `KB_MCP_TOKEN` | Required for MCP | `mcp_server/kb_server.py` | KB app → Settings → API tokens | **Yes** (per user) | missing |
| `KB_SHEETS_ID` | Optional (live Sheets import) | `pipeline/kb_import_sheets.py` | The spreadsheet URL's id | No | missing |
| `NP_DRIVE_SA_KEY` | Optional (Drive/Sheets read) | `00_fetch_drive.py`, `kb_import_sheets.py` | GCP service account key **path**, outside the repo | **Yes** | missing |
| `NP_CORPUS_PATH`, `NP_BUILD_LOG`, `NP_AS_OF`, `NP_FRESHNESS_SKIP`, `NP_LANDING_STATS` | Pipeline knobs | pipeline | See `pipeline/README.md` | n/a | n/a |
| `ANTHROPIC_API_KEY` | Not used | — | Only for future LLM features (docs/AI_ARCHITECTURE.md) | **Yes** | missing |
| `VERCEL_TOKEN` | Not used by code | deploy only | Vercel → Account → Tokens | **Yes** | missing |

Rules that hold regardless: the service-role key is not used anywhere (every web and
MCP request runs as `authenticated` under RLS); no server-only value is ever served by
`/api/config` or present under `public/` (`tests/test_login_flow.py` greps for it).

## Local stack (what this run used)

```bash
db/local/setup.sh            # Docker + npx supabase@2.118.0; applies migrations
export SUPABASE_DB_URL_SESSION=postgresql://postgres:postgres@127.0.0.1:54322/postgres
export SUPABASE_DB_URL_TRANSACTION=postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres
```
These are the CLI stack's fixed public defaults, not credentials.
