# Testing

How the test suite runs and what keeps it from touching production: the local
stack, the suites, browser tests on a 16 GB laptop, the production-only
read-only tests, the skip ledger and the baseline failures.

Code and comments cite the sections below as `docs/operations/testing.md §n`.

## 1. The local stack

The database tests run against the Supabase CLI local stack in `db/local/`:
Supabase's own Postgres image, the auth schema (GoTrue's migrations), roles and
RLS. A DB test that passes there says something true about production. It is
**not** a copy of production's data: no real identities, and the projection is
whatever `knowledge/` holds now.

```bash
db/local/setup.sh          # start (first run pulls about 2 GB of images), migrate, project, seed
db/local/setup.sh --stop   # stop; data is kept in the Docker volume
```

It needs Docker and Node (for `npx`). The Supabase CLI version is pinned in
[`db/local/setup.sh`](../../db/local/setup.sh); change it deliberately and
re-run the suite.

What `setup.sh` does, in order: starts the stack (key and secret lines are
filtered from the output), runs `pipeline/migrate.py up`, projects the graph
with `NP_LANDING_STATS` and `NP_BUILD_LOG` redirected to a scratch folder (a
local projection must never overwrite the tracked `public/stats.json` or
`BUILD_LOG.md`), runs `pipeline/curation.py import`, and inserts the shared
team mailbox into `auth.users` so the shared-account tests (migration 0014)
exercise the derivation instead of skipping.

Every connection string it uses is the stack's fixed local default, not a
secret. The same defaults are in `pipeline/lib/db.py` (`LOCAL_TEST_DSN`, and
`LOCAL_TEST_DSN_TRANSACTION` for the stack's transaction pooler).

**Which database a run uses** (`tests/conftest.py`, `pytest_configure`):

- If `SUPABASE_DB_URL_SESSION` / `SUPABASE_DB_URL_TRANSACTION` are set, those.
- Otherwise `NP_TEST_DSN` / `NP_TEST_DSN_TRANSACTION`, or the local defaults,
  but only if the stack is listening. If it is not, the database tests skip.
- A **production DSN is refused before collection** (`pytest.UsageError`),
  unless `NP_ALLOW_PROD_TESTS=1`. "Production" is derived from the DSN itself
  (`db.production_reason`: the host and the project ref), never from a flag
  that says "this is local". The database tests insert, delete and re-project,
  so a plain `pytest` pointed at production would rewrite it.

So never load a production environment file before running pytest.

The test session also redirects the build log and the landing stats to temp
files (`isolate_build_log`, `isolate_landing_stats`), so a run never dirties
tracked files.

The kb tests (migrations 0022 and later) skip with
`kb: needs the local database with the kb migrations (0022+) applied (db/local/setup.sh)`
when the kb schema is missing (`tests/kb_support.py`).

## 2. The suites

```bash
bash scripts/verify_all.sh             # everything, against the local stack
bash scripts/verify_all.sh --reset-db  # also: wipe the local DB, apply every migration from 0001
bash scripts/verify_all.sh --fresh-clone | --perf | --load
.venv/Scripts/python -m pytest tests/test_kb_sync.py -q   # one file
```

[`scripts/verify_all.sh`](../../scripts/verify_all.sh) is local only: it
refuses a non-local session DSN and aborts if the local database is
unreachable. A check passes only when its command ran and exited 0; a missing
tool or path is a FAIL, never a silent skip. It runs static checks (ES module
parse, ruff on the KB code, the plugin server copy, plugin validation),
security spot checks (no server key names in `public/`, `.env` untracked, no
secret-shaped strings in history, RLS and policies on every kb table, the
deploy guard), then the full pytest suite, compared with the baseline (§6).

CI (`.github/workflows/ci.yml`) has no database: the DB tests skip there, and
the skips are held to the ledger (§5).

## 3. Browser tests: one file at a time on 16 GB

The Playwright tests are `tests/test_kb_e2e.py`, `test_kb_propagation_e2e.py`,
`test_kb_realtime.py`, `test_kb_ui_run6.py`, `test_kb_graph_run6.py` and
`test_kb_console_run6.py`. They need the local stack.

**On a 16 GB laptop, run them one file at a time**, with nothing else heavy
running. Running them together has run the machine out of memory.

```bash
.venv/Scripts/python -m pytest tests/test_kb_e2e.py -q
.venv/Scripts/python -m pytest tests/test_kb_propagation_e2e.py -q -s   # -s prints the change matrix path
```

`verify_all.sh` runs the whole suite in one pytest process, browser files
included; on a 16 GB machine close everything else first, or run the browser
files separately as above.

`test_kb_propagation_e2e.py` writes its change matrix (operation, latency) to
`kb_change_matrix.md` in the system temp folder and prints the path; nothing
is written into the repository.

Running the kb tests wipes `kb` data. Re-run `eval/kb_demo_seed.py` afterwards
if you use the local demo ([local-demo.md](local-demo.md)).

## 4. Production-only read-only tests

Tests marked `production_only` assert on production's own rows (real
identities, the live projection). They are skipped unless the run targets
production, with the reason
`production_only: asserts on production's own rows ...` (`tests/conftest.py`).

Run them only deliberately, at a window step
([window-runsheet.md](window-runsheet.md)), and read-only:

```bash
NP_ALLOW_PROD_TESTS=1 python -m pytest tests -m production_only -rs
```

Read-only is enforced by the server, not by how the tests are written
([`tests/db_guard.py`](../../tests/db_guard.py)):

- `db.connect` sets `default_transaction_read_only=on` after every connection
  opens (`NP_DB_READ_ONLY`), because the pooler drops libpq's `PGOPTIONS`.
  This covers every connection the test opens, autocommit ones, and any
  subprocess.
- The transaction pooler is refused for read-only runs; transaction-pooler
  connections are routed through the session URL.
- The setting is **verified** before the test runs (`show
  default_transaction_read_only`). If the target does not report `on`, the
  test fails instead of running unguarded.

The write canaries (`tests/read_only_canaries.py`) prove this against the
local stack (`tests/test_production_only_is_read_only.py`, never against
production) and through a real session pooler
(`tests/test_read_only_through_pooler.py`; set `NP_TEST_SESSION_POOLER_DSN`
and `NP_TEST_TRANSACTION_POOLER_DSN`; the local stack has both).

**Known gap.** A session setting is only a default: a test that runs
`SET TRANSACTION READ WRITE` first can still write (canary 5). Closing it needs
a dedicated database role without write privileges for the production tests.
That is open post-launch work: rehearse it locally, then flip the strict xfail
in `tests/test_read_only_through_pooler.py`, which fails the day the gap
closes.

## 5. The skip ledger

A skip is a test that did not run. Every run prints its skips grouped by
reason. With `NP_SKIP_LEDGER=enforce` (set in `ci.yml`), the counts must equal
[`tests/ci-skips.yaml`](../../tests/ci-skips.yaml) **exactly**: a new or grown
skip fails the job until it is listed, and a vanished one fails until the
ledger is tightened, so a stale allowance cannot absorb a new skip later.

When you add, remove or rename a skip reason, update `tests/ci-skips.yaml` in
the same change, with a dated comment. Almost all listed skips are DB tests
(no database in CI; they run against the local stack, §1) or tests that need
gitignored corpus, withheld or build files that must never be committed.
`tests/test_skip_ledger.py` proves the ledger fails on a mismatch.

## 6. Baseline failures

[`docs/baseline-failures.txt`](../baseline-failures.txt) lists the tests that
already fail on `main` (43 entries; root cause: `pipeline/project_graph.py` on
a fresh database). `scripts/verify_all.sh` requires the file, compares the
suite's `FAILED`/`ERROR` lines against it, fails on any failure not in the
list, and reports how many baseline failures now pass. All KB tests
(`test_kb_*`) must pass regardless of the baseline.

When a baseline failure is fixed, remove its line from the file.
