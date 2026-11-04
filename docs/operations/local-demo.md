# Local demo — knowledge platform

Everything runs on this machine: the local Supabase stack in Docker, the local demo
server, fictional data. Nothing here touches production, Vercel or Google.

## Start

```bash
# Docker Desktop must be running.
npx -y supabase@2.118.0 start --workdir db/local
export SUPABASE_DB_URL_SESSION=postgresql://postgres:postgres@127.0.0.1:54322/postgres
export SUPABASE_DB_URL_TRANSACTION=postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres
.venv/Scripts/python pipeline/migrate.py up          # every pending migration, through the latest (0037) (bin/python on macOS/Linux)
.venv/Scripts/python eval/kb_demo_seed.py            # demo users + fictional data (re-runnable)
.venv/Scripts/python eval/kb_demo_server.py 8765     # leave running; prints READY 8765
```

Open **http://localhost:8765/local-login**. After signing in you land on the
**Dashboard**: one screen, no scrolling (key numbers, what needs attention, the
newest activity, quick actions, what you own, records by type). The sidebar's
Browse group holds Programs, Courses, **Links** (the resources),
Who teaches what and **Program timeline**.

## Sign in

| Email | Password | KB role |
|---|---|---|
| `demo-admin@interviewkickstart.com` | `ik-demo-local` | admin |
| `demo-editor@interviewkickstart.com` | `ik-demo-local` | editor |
| `demo-contributor@interviewkickstart.com` | `ik-demo-local` | contributor |

These are users in the LOCAL Supabase Auth only, made by the seed script. Use a
second browser profile or a private window for a second user (the session lives
in the browser's local storage, one user per profile).

The contributor's new records go to an editor for approval (Approvals). Live
updates and presence ("demo editor is editing") use the local stack's Realtime;
the demo server takes its origin from `supabase status` and allows exactly that
origin in the page's security policy.

### How the local sign-in works, and why production is unaffected

- `/local-login` exists only in the local servers in `eval/`
  (`eval/kb_demo_server.py`, and `eval/kb_realdata_server.py` below). `eval/` is
  excluded from every deploy (`.vercelignore`, and `excludeFiles` in `vercel.json`). The production app and its code have no password
  login; `public/kb/index.html` is unchanged (the demo server rewrites its
  "Sign in" link to `/local-login` in memory).
- The page posts email + password to the demo server, which asks the **local**
  Supabase Auth for a session (password grant) and returns it in the same shape
  `/api/session` does. From then on every request carries a real local-Supabase
  access token, verified by `web/lib/auth.py` exactly as in production
  (signing keys from the local stack, issuer checked), and RLS applies as usual.
- The demo server and the seed refuse any database or auth URL that is not
  loopback. Keys come from `supabase status` in-process and are never printed.

## Demo data (`eval/kb_demo_seed.py`)

2 programs, 4 domains, 4 courses, 9 modules, 12 weeks, 13 live sessions,
6 instructors, 12 topics, 1 process, 25 links (slides, recordings,
assignments, solutions, GitHub repos; "Links" in the sidebar), 96 relationships. All fictional: the
people, schedules and URLs. Deliberate gaps for **Data quality**:

- the module **Interview Strategy** has no owner;
- **DP on grids — solutions repo** is a broken link (the seed checks it for real
  and records the true HTTP 404; offline, it records nothing);
- the draft topic **Bit Manipulation** is connected to nothing;
- several live sessions have no resources yet.

The resource URLs are fictional and do not open real files.

## Reset

```bash
.venv/Scripts/python eval/kb_demo_seed.py
```

Wipes every kb record, relationship, resource, tag, proposal, token and audit
entry, and recreates the set above. Types, rules and the demo users stay (their
passwords are reset). Reload the browser afterwards. The KB test suite also wipes
kb data: re-run the seed after running tests.

## Stop

Stop the demo server (Ctrl+C in its terminal, or end the `python
eval/kb_demo_server.py` process), then:

```bash
npx -y supabase@2.118.0 stop --workdir db/local      # keeps the data for next time
```

Quit Docker Desktop if nothing else needs it.

## The real-data copy (http://localhost:8766)

A second, separate local workspace over a **copy of production's data**, next
to the demo, which it never touches.

**How it is kept apart (the cleanest way on one machine):**
- Its own **database**, `kb_realdata`, in the same local Postgres
  (127.0.0.1:54322). The demo's `postgres` database, its users and its data
  are untouched, and dropping one never affects the other.
- Its own **server and port**, `eval/kb_realdata_server.py` on 8766. It binds
  127.0.0.1 and refuses any non-local database or Host header.
- Its own **sign-in**: the demo's `/local-login` page, with an account that
  exists only in `kb_realdata`. A session lasts 8 hours and is signed with a
  secret generated each time the server starts, so restarting the server
  signs everyone out.
- The data comes from `backups/` (gitignored, never deployed): `prod_schema.sql`
  and `prod_data.sql`, from the read-only dump of 2026-11-03.

| Sign in | Password | Role |
|---|---|---|
| `realdata-admin@interviewkickstart.com` | `ik-realdata-local` (or `KB_REALDATA_PASSWORD` when building) | KB admin |

**Build or rebuild it** (about 10 s, then about 30 s for the import):

```bash
python eval/kb_realdata_db.py rebuild            # database, production schema + data, KB migrations, admin
SUPABASE_DB_URL_SESSION=postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata \
  python pipeline/kb_import_projection.py preview --as realdata-admin@interviewkickstart.com
SUPABASE_DB_URL_SESSION=postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata \
  python pipeline/kb_import_projection.py apply   --as realdata-admin@interviewkickstart.com --report backups/import-apply.json
python eval/kb_realdata_server.py 8766           # leave running; prints READY 8766
python eval/kb_realdata_check.py                 # optional: 5 programs checked in a browser (ids and counts only)
```

Other commands: `python eval/kb_realdata_db.py counts | drift | admin`.

**Stop:** end the `eval/kb_realdata_server.py` process. To remove the copy
entirely, run `python eval/kb_realdata_db.py drop-reference`, then
`dropdb`/`drop database kb_realdata` in the local stack, and delete the files
in `backups/`.

The test suite and the demo seed use only the demo's database. `scripts/verify_all.sh --reset-db` resets the whole local stack and can remove `kb_realdata`: rebuild it with the commands above afterwards.
