# np-autopilot

Interview Kickstart's New Programs (NP) knowledge, in one deployment:

- **The NP Autopilot map at `/`** (`public/index.html`): the programme,
  domain, module and instructor graph that the NP team uses day to day.
- **The knowledge base at `/kb/`** (`public/kb/`): an editable, audited
  workspace of programs, courses, domains, modules, weeks, live sessions,
  topics, people and their links, with custom record and relationship types.
- **The pipeline** (`pipeline/`): reads the NP Google Drive folder
  (read-only) and builds the graph that feeds the knowledge base.
- **An MCP server and a Claude Code plugin**, so Claude can search and edit
  the knowledge base as you, under your role.

**The `kb` schema is the single source of truth** (run 6). Every page,
including the map at `/`, reads `kb`. The pipeline's old tables in `public`
are only its *intake*: a scheduled one-way sync copies them into `kb`.
Background: `docs/architecture/overview.md`. Where this could go next:
`docs/VISION_AND_ROADMAP.md`.

**Read `CLAUDE.md` before touching the pipeline.** It holds the safety rules
summarised under "Rules that are not optional" below.

---

## Architecture

```
 Google Drive (one folder, read-only, service account, drive.readonly)
        │  pipeline/00_fetch_drive.py … 04_build_graph.py, project_graph.py   (run by hand)
        ▼
 OLD TABLES (public.*): nodes · edges · node_sources · node_layout · files · curation
        │  ONE-WAY sync, web/lib/kb/sync.py: hourly (pg_cron → POST /api/cron/kb-sync),
        │  "Sync now" (Settings → Sync), or the first import (pipeline/kb_import_projection.py)
        ▼
 KB (kb.*)  RLS on every table · triggers: version, audit log, archive cascade
        │  every write → kb.changes (the change feed; Realtime, or polling /api/kb/changes)
        ├──► /api/kb/*   api/kb_routes.py → web/lib/kb/service.py (the one rulebook) ──► /kb/
        ├──► /api/kb/graph (docs/architecture/contracts.md §1) ──► the KB Graph page AND the map at "/"
        ├──► /api/structure, /node, /neighbourhood, /search, /overview, /staffing,
        │    /coverage, /me   (the map's routes, web/lib/kb/npmap.py, read from kb)
        └──► mcp_server/kb_server.py (an HTTP client of /api/kb/*, your own token)
```

Every request enters `api/index.py` (one WSGI app on Vercel). Identity is
checked there before any database connection. Requests run as Postgres role
`authenticated` with the caller's claims, so RLS applies. The map can be
switched back to the old tables with `NP_MAP_SOURCE=old` (rollback only:
`docs/architecture/overview.md`, "Rollback").

| Path | What it is |
|---|---|
| `api/` | HTTP: `index.py` (front door), `kb_routes.py` (KB adapter), the map's routes |
| `web/lib/kb/` | KB logic: `service.py`, `validate.py`, `typedefs.py`, `graph.py`, `npmap.py`, `sync.py`, `activity.py`, `workspace.py`, … |
| `public/` | the map (`index.html`) and the KB app (`kb/`, vanilla JS, Cytoscape; `kb/guide.md` is the in-app Guide) |
| `db/migrations/` | numbered `.up.sql` / `.down.sql`; `kb` is 0022 onwards |
| `pipeline/` | Drive fetch, extraction, graph build, projection, KB import/admin CLIs |
| `config/` | `taxonomy.yaml` (the only source of type names), the KB mapping files |
| `mcp_server/`, `plugins/ik-knowledge-assistant/` | MCP server and Claude Code plugin |
| `eval/` | local servers, seeds and checks (never deployed: `.vercelignore`) |
| `tests/` | pytest suites; `tests/kb_support.py` holds the KB fixtures |

---

## Setup

You need Python 3.12, Node (for `npx supabase`), Docker (for the local
Supabase stack), and `uv` (optional, used by `scripts/verify_all.sh`).

### Windows (Git Bash)

Use Git Bash for every command in this README.

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt
#   or: py -3.12 -m venv .venv && .venv/Scripts/pip install -r requirements.txt
# Docker Desktop must be running.
bash db/local/setup.sh                       # local Supabase stack (first run pulls ~2 GB), migrates, seeds
```

The interpreter is `.venv/Scripts/python`.

### Linux / macOS

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt
bash db/local/setup.sh                       # needs Docker (macOS here: colima)
```

The interpreter is `.venv/bin/python`.

`db/local/setup.sh --stop` stops the stack and keeps its data. The stack uses
fixed loopback addresses and development keys. The test suite and the local
servers refuse any non-local database.

`requirements.txt` is the full environment (pipeline, MCP, tests).
`pyproject.toml` is only the Vercel function's dependencies. Do not add
packages there: the bundle is at its size limit.

---

## Environment variables (names only)

Never put a value in the repository, in a doc or in a commit. Values live in
Vercel (per environment), in Supabase Vault, or in your shell.

| Name | Used by | Purpose |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | app (`/api/config`) | public by design (`docs/operations/deployment.md`) |
| `SUPABASE_DB_URL_TRANSACTION` | app | transaction pooler (port 6543), every request; the session pooler and the direct host are refused |
| `SUPABASE_DB_URL_SESSION` | CLIs, migrations | session pooler (owner); laptop/CI only, **never set in Vercel** |
| `SUPABASE_JWT_SECRET` | app | only for HS256 projects |
| `GOOGLE_OAUTH_CLIENT_ID` | app | Google sign-in audience |
| `NP_ALLOWED_HD` | app | the one allowed Google Workspace domain |
| `NP_SHARED_ACCOUNTS` | app | shared mailboxes, flagged in the audit log |
| `NP_MAP_SOURCE` | app | `old` = rollback the map to the old tables |
| `KB_SYNC_ENABLED` | app | `false` stops every sync run (kill switch) |
| `KB_SYNC_SECRET` | app + Vault (`kb_sync_secret`) | authorises pg_cron's call to `/api/cron/kb-sync` |
| `KB_SYNC_BUDGET_SECONDS` | app | time budget per sync run (default 10) |
| `KB_REALTIME_ORIGIN` | app | enables Supabase Realtime in the KB page's CSP |
| `ADMIN_EMAILS` | `pipeline/kb_admins.py` | bootstrap KB admins (operator) |
| `KB_API_URL`, `KB_MCP_TOKEN`, `KB_APP_URL` | MCP server | KB host, your personal `ikkb_` token, links in answers |
| `NP_DRIVE_SA_KEY`, `NP_DRIVE_CONFIG` | pass 0 | path to the service-account key (outside the repo), Drive config |
| `NP_CORPUS_PATH` | pipeline | fallback local corpus mirror |
| `NP_AS_OF`, `NP_BUILD_LOG`, `NP_LANDING_STATS`, `NP_FRESHNESS_SKIP` | pipeline | pinned build date, log path, stats output, freshness override (a reason) |
| `KB_SHEETS_ID` | `pipeline/kb_import_sheets.py` | spreadsheet to import |
| `NP_TEST_DSN`, `NP_TEST_DSN_TRANSACTION` | tests | override the local test database |
| `KB_REALDATA_PASSWORD`, `KB_LOCAL_DB`, `KB_LOCAL_DB_CONTAINER` | `eval/` | local servers only |
| `NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION` | `web/lib/kb/legacy_delete.py` | explicit gate for the owner-approved legacy delete |

`SUPABASE_SERVICE_ROLE_KEY` is never set in Vercel. The dev deployment's
`DEV_*` variables are described in `docs/operations/dev-deploy.md`.

---

## Run it locally

### Demo (fictional data), http://localhost:8765

```bash
.venv/Scripts/python eval/kb_demo_seed.py          # demo users + fictional data (re-runnable = reset)
.venv/Scripts/python eval/kb_demo_server.py 8765   # prints READY 8765
```

Open `http://localhost:8765/local-login`. The demo accounts and the password
login exist only in the local stack and `eval/` (never deployed). Details,
sign-ins and reset: `docs/operations/local-demo.md`. Running the KB tests wipes `kb` data, so
re-run the seed afterwards.

### Real-data copy, http://localhost:8766

A separate local database (`kb_realdata`) built from a read-only production
dump in the gitignored `backups/`. Server: `eval/kb_realdata_server.py 8766`.
It binds 127.0.0.1 and refuses non-local databases. Build steps:
`docs/operations/local-demo.md`, "The real-data copy". Never copy anything from it into code,
tests, docs or commits.

---

## Tests

```bash
bash scripts/verify_all.sh            # everything, against the local stack (PASS only if each check really ran)
bash scripts/verify_all.sh --reset-db # also re-applies every migration from 0001 (can remove kb_realdata)
.venv/Scripts/python -m pytest tests/test_kb_sync.py -q      # one suite
.venv/Scripts/python -m pytest tests/test_kb_rls.py -q -k viewer
```

Browser tests (Playwright) are `tests/test_kb_e2e.py`,
`test_kb_propagation_e2e.py`, `test_kb_realtime.py`, `test_kb_ui_run6.py`,
`test_kb_graph_run6.py` and `test_kb_console_run6.py`. **On a 16 GB laptop,
run them one file at a time**, with nothing else heavy running. Running them
together has run the machine out of memory. Other options of
`verify_all.sh`: `--fresh-clone`, `--perf`, `--load`.

---

## Roles

Sign-in is Google SSO, restricted to `@interviewkickstart.com` and checked on
every request. KB roles are enforced in the database (RLS, `0023_kb_rls`), so
they hold whatever tool is used: the app, MCP or SQL as `authenticated`. Any
signed-in IK account with no membership is a **viewer**. Admins add members by
e-mail in Settings → Members, before or after their first sign-in
(`0035_kb_member_invites`). The last admin cannot be removed.

| Role | Can |
|---|---|
| **viewer** | read everything in the KB and the map; flag something as incorrect; claim their own person record (an admin confirms) |
| **contributor** | + attach links and add relationships to existing records directly; new records, field edits, archive requests and type changes go to **Approvals** |
| **editor** | + create and archive directly, approve proposals, overwrite on a conflict, see sync conflicts; a new relationship type is usable at once but reviewed by an admin |
| **admin** | + record and relationship types, roles and members, people's e-mail addresses, profile claims, permanent deletion of archived items, Settings → Sync |

An AI caller (MCP token) acts with its owner's role. Its archive and delete
calls always become proposals, and it cannot approve or start a sync. Source:
`public/kb/guide.md` ("Roles"), `db/migrations/0023_kb_rls.up.sql`,
`web/lib/kb/service.py`.

---

## The sync

`web/lib/kb/sync.py` builds the desired KB state from the old tables. It
compares each unit with `kb.sync_map` checksums and writes only what changed.
A unit edited in the KB since the sync wrote it is **not** overwritten: it
becomes a conflict on Data quality. A row that disappears at the source is
flagged "removed at the source". Records are never deleted, and relationships
and links are archived (reversible). Records created in the KB are never
touched. `kb.sync_exclusions` (0037) keeps permanently deleted legacy
records from coming back. One run at a time, time-boxed, resumable.

- **Schedule:** pg_cron + pg_net in the database (migration 0031), hourly by
  default, calling `/api/cron/kb-sync` with the Vault secret. Set up as in
  `docs/operations/dev-deploy.md` step 6.
- **By hand:** Settings → Sync → **Sync now** (admins), which also shows the
  run log. Admins see a banner while the last run failed.
- **Off:** `KB_SYNC_ENABLED=false` stops every run. `select kb.sync_schedule_remove();`
  stops the calls.
- The sync only copies what the pipeline last projected. Passes 0–4 and
  `project_graph.py` are still run by hand (`pipeline/README.md`).

Details: `docs/operations/deployment.md` "Scheduled sync".

---

## Claude: MCP server and plugin

`mcp_server/kb_server.py` (stdio, or `--http` on 127.0.0.1) is a thin client
of `/api/kb/*`: search, read, traverse, create, connect, attach, audit tools.
It authenticates with **your** personal token (Settings → API tokens; only a
hash is stored) and runs as you under RLS. Retrieved text is returned as
data, with source links. `plugins/ik-knowledge-assistant/` bundles the same
server (a byte-identical copy, enforced by `tests/test_kb_plugin.py`) and
two skills: `ik-knowledge-search` and `ik-course-audit`.

```bash
cp mcp_server/mcp.example.json .mcp.json     # gitignored; never put the token in it
export KB_API_URL=...  KB_MCP_TOKEN=...      # set in your shell
```

A multi-user remote (Claude.ai) deployment needs per-user OAuth, which is not
built. See `docs/integrations/mcp.md`.

The repository's marketplace (`.claude-plugin/marketplace.json`) also lists
the older `np-autopilot` plugin. Its commands (`commands/`: `/staffing`,
`/coverage`, `/workflow`, `/domain-owner`, `/setup`) read the pipeline's
committed `knowledge/graph.json` snapshot, not the live KB.

---

## Deployment

One Vercel project (`vercel.json`; `api/index.py` is the only function). Read,
in order:

- `docs/operations/deployment.md`: variables, Supabase Auth, pooling, the scheduled sync,
  checks after deploying.
- `docs/operations/dev-deploy.md`: the dev database and the Vercel preview.
  `scripts/dev_db.py` refuses the production project.
- `docs/operations/GO_LIVE.md`: the production go-live steps (being written by the lead
  in run 6).

Migrations: `pipeline/migrate.py up` with `SUPABASE_DB_URL_SESSION`. Each
migration is additive and has a `.down.sql`.

---

## The pipeline's graph (the intake), generated

These are the counts of the pipeline's own graph (`knowledge/graph.json`), which is the
intake of the knowledge base, not the KB's live numbers. **Generated by
`pipeline/gen_index.py`; do not hand-edit the block** (`tests/test_readme_counts.py`).
Person, instructor and module counts are floors (CLAUDE.md §2).

<!-- generated:counts -->
`3,146 nodes · 34,575 edges` at plugin **v0.1.9**, built `2026-09-17`.

**Plus 1,902 nodes and 2,102 edges withheld from this repo** — `sensitive: true`, hiring rejections and in-pipeline candidates about named external people. They live in `graph-sensitive.json`, which is gitignored, and are projected behind the `recruiting` access policy. Full graph is 5,048 nodes / 36,677 edges. See `docs/DECISIONS.md` §F.2.

| node type | count |
|---|---:|
| instructor | 1,915 |
| module | 922 |
| workflow | 92 |
| file | 74 |
| person | 43 |
| domain | 42 |
| program | 42 |
| theme | 16 |

| edge type | count |
|---|---:|
| sourced_from | 30,554 |
| teaches | 2,239 |
| expert_in | 1,155 |
| contains | 351 |
| belongs_to | 92 |
| supported_by | 58 |
| owned_by | 55 |
| delivered_by | 43 |
| covers | 28 |

Declared but at zero, deliberately: `depends_on`, `workflow_owned_by`. No evidence in the corpus.
<!-- /generated:counts -->

---

## Rules that are not optional

The full text is in `CLAUDE.md`. In short:

- **The corpus is read-only.** Never write, move or rename a Drive/corpus
  file. Drive scope stays `drive.readonly`. Filename typos are citation keys.
- **Contact data stays out.** Extraction reads declared name columns only
  (`pipeline/lib/sources.py` is the allow-list). Never declare a contact
  column (`tests/test_exclusion_is_deny_by_default.py`). The payroll file is
  excluded (`config/taxonomy.yaml` `excluded:`). The sensitive half of the
  graph is never projected or committed.
- **Counts are floors, not totals.** Entity scans have not read every file.
  Never quote person, instructor or module counts as totals.
- **Thresholds rank or warn. They never silently exclude** (CLAUDE.md §4).
- **`config/taxonomy.yaml` is the only source of type names**
  (`tests/test_taxonomy_single_source.py`).
- **One rulebook:** KB rules live in `web/lib/kb/service.py` and its siblings,
  and the database enforces them again.
- **The audit log is append-only.** No real names or e-mails in code, tests,
  docs or commits: use synthetic `kbtest-*@interviewkickstart.com` data.
- **Never connect to production** from a laptop session without the owner.
  Never print secrets, URLs or hosts.

## More docs

`docs/architecture/overview.md` · `docs/architecture/contracts.md` · `docs/integrations/http-api.md` ·
`docs/architecture/schema.md` · `docs/architecture/design-system.md` · `docs/integrations/mcp.md` · `docs/operations/local-demo.md` ·
`docs/architecture/auth.md` · `docs/CONTACT-DATA.md` · `docs/VISION_AND_ROADMAP.md` ·
`docs/project-history/HANDOFF.md` · `BUILD_LOG.md` · `pipeline/README.md`
