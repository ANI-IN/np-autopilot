# Dev deployment: the knowledge platform on a Vercel preview + the DEV database

Run 5, Part 6. **Nothing here touches Production**: not the production database
(project `yqmzjgzhxhihnpbgqmeh`), not the Production environment in Vercel.
The dev database is the separate Supabase project named by `DEV_SUPABASE_URL`;
`scripts/dev_db.py` refuses any database whose project ref is production's or
differs from `DEV_SUPABASE_URL`, and `scripts/deploy_dev_preview.sh` refuses
any Production target or a production variable.

## 1. The dev database (done in run 5)

`scripts/dev_db.py` (no URL, host or IP is ever printed):

| Step | Command | Result (run 5) |
|---|---|---|
| Not production; the refs agree | `python scripts/dev_db.py check` | yes; Postgres 17 |
| Backup before any change | `python scripts/dev_db.py backup` | `backups/dev_backup_20261102T221344Z.sql` (the project was empty) |
| Migrations 0001 -> 0031 | `python scripts/dev_db.py migrate` | 31 applied (run 5); the chain now reaches **0037** (0036 unused), applied on dev in run 6 |
| Roll back and re-apply | `python scripts/dev_db.py rollback-test`; and, while still empty, the whole chain down to nothing and up again | 0031+0030 down/up: ok; 31 down / 31 up: ok |
| The old tables | `python scripts/dev_db.py load-old-tables` | 13 projection tables, 65,598 rows, equal to the dump. User and account tables (profiles, shared_accounts, auth_hook_refusals, curation_audit) are **not** copied. |
| First import + legacy step | `python scripts/dev_db.py import` | 25,226 units created in 245 s (over a ~175 ms pooler); legacy: 874 archived (35 domains, 166 modules, 673 instructors) |
| One sync | `python scripts/dev_db.py sync` | ok, 0 writes, 0 conflicts (28.5 s from a laptop; see the note below) |
| Verify | `python scripts/dev_db.py verify` | every count equal to the local real-data copy (:8766); parity numbers equal; 25 kb tables, all with RLS; migrations at 0031 |

The first import runs with `--operator`: no KB admin exists on a new database
(nobody has signed in), so the session-pooler login, which owns the kb tables,
creates the record types the sync needs and is recorded as "Sync" with no
person. Operator mode is honoured only on a connection that owns `kb.nodes`
and asks for it in its transaction; a request connection runs as
`authenticated` and can never qualify (tests/test_kb_sync.py).

**The admin (morning).** `ADMIN_EMAILS` must name an IK account that has signed
in to the dev deployment once (kb_admins.py never invents a profile). This
checkout's git e-mail is not an IK address, so: sign in once (step 5), then

```
SUPABASE_DB_URL_SESSION="$DEV_SUPABASE_DB_URL" ADMIN_EMAILS=<you>@interviewkickstart.com python pipeline/kb_admins.py
```

## 2. Vercel variables: Preview, this branch only

Scope every variable to **Preview** AND the git branch
`auto/knowledge-platform-20261102`. **Never Production.** With the CLI:
`vercel env add <NAME> preview auto/knowledge-platform-20261102` (it prompts for
the value, so nothing lands in shell history). In the dashboard: Settings ->
Environment Variables -> tick **Preview** only -> "Select a custom Preview branch"
-> `auto/knowledge-platform-20261102`.

| Vercel variable (Preview, this branch) | Value |
|---|---|
| `SUPABASE_URL` | `DEV_SUPABASE_URL` |
| `SUPABASE_ANON_KEY` | `DEV_SUPABASE_ANON_KEY` |
| `SUPABASE_DB_URL_TRANSACTION` | `DEV_SUPABASE_DB_URL` with the port changed **5432 -> 6543** (the transaction pooler; same user, host and password). The app refuses 5432 and the direct host. |
| `SUPABASE_JWT_SECRET` | the dev project's JWT secret (Supabase -> Settings -> API), only if the project signs with HS256; not needed when it publishes JWKS |
| `GOOGLE_OAUTH_CLIENT_ID` | the Google OAuth client of step 5 |
| `NP_ALLOWED_HD` | `interviewkickstart.com` |
| `NP_SHARED_ACCOUNTS` | the same list as Production's |
| `KB_SYNC_SECRET` | a new random value, 32+ characters (`python -c "import secrets; print(secrets.token_urlsafe(32))"`); the same value goes into the dev Vault in step 6 |
| `KB_SYNC_ENABLED` | `true` (the kill switch: `false` stops every run) |
| `KB_SYNC_BUDGET_SECONDS` | `10` (the default; each run is a batch that resumes, well under the 60 s `maxDuration` in vercel.json; raise to 30-50 only if a measured batch needs it) |

**Never set in Vercel:** `DEV_SUPABASE_SERVICE_ROLE_KEY` (under any name), the
session-pooler URL, or any `DEV_` name itself. The app reads the names above
only.

## 3. Deploy

```
vercel login                         # once, by a person
vercel link                          # the existing project
bash scripts/deploy_dev_preview.sh --check   # the refusals, nothing deployed
bash scripts/deploy_dev_preview.sh           # deploy --target=preview, then the smoke tests
```

The script refuses: any argument naming production; another branch; Preview
variables naming the production project or not naming the dev project; a
database URL not on port 6543; a service-role key or session URL among them; a
deployment the CLI reports as Production.

## 4. Smoke tests (run by the script; by hand with `curl`)

The stable URL of this branch's latest preview is
`https://<project>-git-auto-knowledge-platform-20261102-<team>.vercel.app`
(Vercel -> Deployments -> the branch). If Deployment Protection is on, add
`-H "x-vercel-protection-bypass: <bypass secret>"` (Settings -> Deployment
Protection -> Protection Bypass for Automation).

| Request | Expect |
|---|---|
| `GET /api/config` | 200 |
| `GET /kb/` | 200 |
| `GET /api/kb/me` (no session) | 401 |
| `POST /api/cron/kb-sync` (no secret) | 401 |
| `GET /local-login` | 404 (the local sign-in exists only in eval/) |
| `POST /api/cron/kb-sync` with `Authorization: Bearer <KB_SYNC_SECRET>` | 200, `{"status": "ok", ...}`; a new row in Settings -> Sync with trigger "Schedule" |
| Sign in with an IK Google account (step 5), open `/kb/` | the dashboard; current counts only (legacy hidden) |

## 5. Google sign-in for the preview domain

1. **Google Cloud Console -> APIs & Services -> Credentials ->** the OAuth 2.0
   client used for `GOOGLE_OAUTH_CLIENT_ID` (or a new "Web application" client
   for dev):
   - Authorised JavaScript origins: `https://<project>-git-auto-knowledge-platform-20261102-<team>.vercel.app`
     (Google Identity Services checks the page's origin; wildcards are not
     accepted, so add the branch URL, not each deployment's URL).
   - Authorised redirect URIs: `https://<dev ref>.supabase.co/auth/v1/callback`.
2. **Supabase (the DEV project) -> Authentication -> Providers -> Google:**
   enable; the client ID and secret of step 1.
3. **Supabase (DEV) -> Authentication -> Hooks -> Before User Created:**
   `pg-functions://postgres/public/auth_before_user_created` (migration 0007
   granted it to `supabase_auth_admin`).
4. **Supabase (DEV) -> Authentication -> URL Configuration:** Site URL = the
   branch URL above; Redirect URLs: the branch URL with `/**`, and
   `https://*-<team>.vercel.app/**` if per-deployment URLs should sign in too.
5. Sign in once at `<branch URL>/kb/`, then make yourself admin (step 1, "The
   admin").

## 6. The schedule (cron)

The schedule lives in the dev DATABASE (migration 0031; docs/DEPLOYMENT.md
"Scheduled sync" has the reasons): pg_cron fires, pg_net POSTs to the
deployment's `/api/cron/kb-sync` with the secret from Vault. In the dev
project's SQL editor (Supabase dashboard), as the owner:

```sql
-- the same value as the Preview variable KB_SYNC_SECRET
select vault.create_secret('<KB_SYNC_SECRET>', 'kb_sync_secret');
-- a protected preview: Vercel's "Protection Bypass for Automation" secret
select vault.create_secret('<bypass secret>', 'kb_sync_vercel_bypass');
-- hourly (the default); any cron expression, e.g. '*/15 * * * *'
select kb.sync_schedule_install('https://<branch URL host>/api/cron/kb-sync', '0 * * * *');
-- check: the job, then (after the next hour) its HTTP result and the run log
select jobname, schedule, active from cron.job where jobname = 'kb-sync';
select status_code, created from net._http_response order by created desc limit 3;
select id, trigger, status, conflicts from kb.sync_runs order by id desc limit 3;
```

Switch off: `KB_SYNC_ENABLED=false` in Vercel (immediate, runs log "disabled"),
or `select kb.sync_schedule_remove();` (no more calls). "Sync now" (Settings ->
Sync, admins) works whatever the schedule.

## Dev status (end of run 5; run 6 rows last)

| | dev | local copy (:8766) |
|---|---|---|
| Old tables: nodes / edges / node_sources / people | 8,496 / 12,189 / 39,414 / 20 | same |
| KB records live (current) | 5,087 (3,087) | same |
| KB relationships live / links / links on records live | 4,408 / 1,827 / 8,855 | same |
| Domains current+legacy / modules / instructors | 4+42 / 20+904 / 25+1,886 | same (= NP Autopilot) |
| Roles P / B1 / B2 / B3 | 23 / 20 / 11 / 3 | same (= NP Autopilot) |
| Archived by the legacy step | 874 | 874 |
| RLS | 25 kb tables, 0 without | |
| Migrations | 0001-0031; run 5's two rolled back and re-applied; the whole chain rolled back and re-applied while empty | |
| Sync | 2 runs (import, one sync): ok, 0 conflicts. No schedule installed yet (step 6 needs the deployment URL) | |
| Admin | none yet: dev has no users. `ADMIN_EMAILS=<git e-mail>` dry run: "NO PROFILE ... sign in once first" (the git e-mail is not an IK address) | |
| **Run 6 (2026-11-04)** | R3 legacy deletion on dev: 946 records permanently deleted; domains / modules live 4 / 20; sync after it: 0 created / 0 conflicts; RLS on 26/26 kb tables; migrations at 0037 | |
| **Run 6: D2 preview** | **BLOCKED**: Vercel rejected the `VERCEL_TOKEN` in .env on 2026-11-04 ("token not valid"); nothing was deployed. Owner step below | |

**Owner step for the preview (D2).** Create a new Vercel token with access to
the project's team, put it in `.env` as `VERCEL_TOKEN`, run `vercel link`
(the existing project), then `bash scripts/deploy_dev_preview.sh --check`
(refusals only, nothing deployed) before the real deploy in step 3.

**Measure the sync's time in region before relying on the schedule.** An
unchanged run took 28.5 s from a laptop to dev (it reads ~65,000 source rows and
~25,000 sync-map rows over a ~175 ms link) and 1.1 s locally. From a Vercel
function in the database's region it should be a few seconds; the
function cap is now 60 s (`maxDuration` for `api/**` in vercel.json) and each
run is time-boxed by `KB_SYNC_BUDGET_SECONDS` (the next tick continues from
`sync_runs.resume`, 0033). After step 6, check Settings -> Sync: if a run shows
"running" and never finishes, lower the budget or run the sync from CI instead; a run killed by the cap is cleared as "abandoned" after 20 minutes.
