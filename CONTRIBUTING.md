# Contributing

This repository holds Interview Kickstart's New Programs knowledge platform: the
knowledge base at `/kb/`, the NP Autopilot map at `/`, the intake pipeline, and
the MCP server and Claude plugin. Read [README.md](README.md) first, then
[CLAUDE.md](CLAUDE.md) before you touch the pipeline.

## Set up

Follow the quick start in [README.md](README.md#quick-start). You need Python
3.12, Docker (the local Supabase stack), Node (for `npx supabase`) and,
optionally, `uv`. Then enable the push guard once per clone:

```bash
git config core.hooksPath .githooks   # refuses to push to a public repository
```

Never put a secret in the repository. Values live in Vercel, in Supabase Vault
or in your shell; `.env` is gitignored. See [SECURITY.md](SECURITY.md).

## Branches

- `main` is what production runs. Nobody pushes to it directly; it changes only
  through a reviewed pull request.
- Work on a branch named for the change, for example `fix/sync-lock-timeout`
  or `feat/people-csv`.
- Never force-push a shared branch and never rewrite published history.

## Commits

- One logical change per commit. The subject says what changed, in the area's
  words: `Sync: resume a batch after a timeout`, not `fixes`.
- The body says why, and anything a reviewer can't see in the diff (a decision,
  a measurement, how to reverse it).
- Never commit `.env`, tokens, `backups/`, real data, screenshots of real data,
  local configuration, or generated and temporary files. `.gitignore` covers the
  known ones; check `git status` before every commit.

## Tests

```bash
bash scripts/verify_all.sh                               # everything, against the local stack
.venv/Scripts/python -m pytest tests/test_kb_sync.py -q  # one suite (Linux/macOS: .venv/bin/python)
.venv/Scripts/python -m ruff check web api pipeline      # lint
```

- **Zero new failures.** `main` has a known list of failing tests,
  [docs/baseline-failures.txt](docs/baseline-failures.txt); `verify_all.sh`
  compares the run against it. A change may fix entries but never add one.
- **Browser tests** (Playwright: `tests/test_kb_e2e.py`, `test_kb_ui_run6.py`,
  `test_kb_graph_run6.py`, `test_kb_console_run6.py`, `test_kb_realtime.py`,
  `test_kb_propagation_e2e.py`): on a 16 GB laptop run **one file at a time**
  with nothing else heavy running. Run `test_kb_graph_run6.py` one test per
  process; two of its tests hang when run back to back in one process.
- Never skip a test to make a run pass, never weaken a permission check, and
  never swallow an error. CI enforces a skip ledger (`tests/ci-skips.yaml`).
- Running the KB tests wipes the local `kb` data: re-seed the demo afterwards
  (`eval/kb_demo_seed.py`).
- Details: [docs/operations/testing.md](docs/operations/testing.md).

## Database migrations

- Numbered pairs in `db/migrations/`: `NNNN_name.up.sql` and `NNNN_name.down.sql`.
- Additive and reversible. A down migration that would lose data refuses while
  the data exists.
- Apply with `pipeline/migrate.py up` (local stack or dev). Production
  migrations are part of [docs/operations/GO_LIVE.md](docs/operations/GO_LIVE.md).

## Rules that are not optional

The full text is in [CLAUDE.md](CLAUDE.md). In short:

- The Drive corpus is read-only (`drive.readonly`); never write, move or rename a corpus file.
- Contact data stays out: never declare a contact column; the sensitive half of the graph is never committed.
- `config/taxonomy.yaml` is the only source of type names: no type literals in Python.
- KB rules live once, in `web/lib/kb/` (`service.py`, `validate.py`), and the database enforces them again (RLS, triggers).
- The audit log is append-only. Use synthetic `kbtest-*@interviewkickstart.com` data in tests and docs, never real names or e-mail addresses.
- Never name a script after a standard-library module.
- Never connect to production from a laptop session. The remote targets for development are the DEV Supabase project and Vercel Preview.

## Pull request checklist

The same list is in [.github/pull_request_template.md](.github/pull_request_template.md).

- [ ] `bash scripts/verify_all.sh` passes: no new failures against `docs/baseline-failures.txt`.
- [ ] Browser tests run one file at a time, if the UI changed.
- [ ] New or changed behaviour has a test.
- [ ] Every migration has a `.down.sql`, and both were applied locally.
- [ ] Docs updated (README, `docs/`, the in-app Guide `public/kb/guide.md`), and `python scripts/check_md_links.py` passes.
- [ ] No secrets, real data, `backups/` or generated files in the diff.
- [ ] Rollback described for anything that changes production behaviour.
