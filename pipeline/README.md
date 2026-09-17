# pipeline

Passes are separate. Each writes to disk; the next reads from disk. Any pass can
be re-run without repeating the one before.

**Pass 0 is the only one that touches the network. Do not fuse it with pass 1** —
re-parsing must never re-download.

| Pass | Script | Status | Reads | Writes |
|---|---|---|---|---|
| 0 | `00_fetch_drive.py` | built — **never run**, deferred to v2 | Drive API | `.drive-cache/` |
| 1 | `01_walk_corpus.py` | built | corpus (cache, else `NP_CORPUS_PATH`) | `knowledge/files.json` |
| 2 | `02_extract.py` | built | `files.json` + corpus | `candidates.json`, `rejections.json` |
| 3 | `03_resolve.py` | built | `candidates.json`, `config/people.yaml` | `resolved.json`, `config/people-review.yaml` |
| 4 | `04_build_graph.py` | built | `resolved.json`, `candidates.json`, `files.json`, corpus, config | **`graph.json`**, two review files |
| 5 | `05_render_html.py` | built | `graph.json`, `files.json` | `graph.html`, `_graph_*.{json,mjs}` |
| — | `validate.py` | built — 17 categories, all fault-injection tested | `graph.json` | stdout, build log |

Helpers: `gen_index.py` regenerates `knowledge/INDEX.md` from `graph.json` —
never hand-write a count there. `gen_workflow_owners.py` regenerates the 92-row
ownership stub; every suggestion lands `confirmed: false`.

`refresh.py` runs 1–5 plus `gen_index` and `validate`, prints a delta, bumps
`plugin.json`, and **stops without committing**.

## Database (D3)

The graph is projected into Postgres. The pipeline remains the source of truth
for everything derived; Postgres is the source of truth for CURATION only
(DECISIONS §B.1).

| Script | |
|---|---|
| `migrate.py` | numbered SQL migrations with an explicit `.down.sql` for each. `status` / `up` / `down`. |
| `project_graph.py` | replace-all in one transaction. **Public half only** — `--scope full` is refused until the recruiting RLS path exists. |
| `curation.py` | `import` / `export` / `roundtrip` / `check` for people, domain aliases and workflow owners. `roundtrip` proves the mechanism by reloading from YAML; `check` compares the database **as it is**, which is the only one that can see drift. |
| `grant_access.py` | `list` / `grant` / `revoke` a profile. **The deliberate act that a session is not** — signing in proves a Workspace identity, a profile is what grants data, and there is no self-service path between the two. Runs as the owner because `profiles` has no INSERT policy, so this cannot be done over the web app. |

```
set -a && . ~/.config/np-autopilot/env && set +a
python3 pipeline/migrate.py up
python3 pipeline/project_graph.py
python3 pipeline/verify_migration.py --source supabase
```

**Connections go through `lib/db.py`, never a literal.** The session pooler
(5432) for migrations and the projection; the transaction pooler (6543) for
anything request-scoped, with `prepare_threshold=None` because transaction-mode
pooling cannot hold prepared statements. The direct
`db.<ref>.supabase.co:5432` connection is **refused** — it is IPv6-only on this
project, so it works on a laptop and fails on Vercel.

**Every migration ships its rollback.** `migrate.py` refuses to run a `.up.sql`
with no matching `.down.sql`: an irreversible migration is a decision, and it has
to be written down as one. Migration 0001 is deliberately empty so the rollback
path is exercised before there is anything to lose.

## Migration verification

`verify_migration.py` checks a graph against the frozen reference in
`config/migration-baseline.yaml`: node counts by type, edge counts by rel, the
1,687 legitimate duplicate triples, provenance coverage on both origin shapes,
and connected-component structure excluding provenance.

```
python3 pipeline/verify_migration.py            # verify knowledge/graph.json
python3 pipeline/verify_migration.py --freeze   # re-record the reference
```

Expected values live in config, never in the script — three alias decisions are
still open and resolving them will legitimately move several of these figures.
Re-freeze deliberately, in a commit that says why; never edit the baseline to
make a diff go away.

It runs file-against-file today so it is known-good before the Supabase
projection exists. A verification script first exercised during a migration gets
debugged during the migration, which is when nobody can tell whether the script
or the migration is wrong.

## Query layer

`query.py` is not a pass. It is what the plugin commands call — `/staffing` and
`/coverage` shell out to it rather than reading `graph.json` themselves.

Retrieval and tiering happen there, in Python, so they cannot be paraphrased,
reordered or merged by a language model. The command presents what the script
returns; it does not decide it. `/staffing` never merges its evidence tiers, and
`tests/test_staffing_tiers.py` exists so a refactor cannot quietly undo that.

## Rules

- **`lib/taxonomy.py` is the only module that may read `config/taxonomy.yaml`.**
  A grep test fails the build on any type string written as a literal elsewhere.
- **`lib/paths.py` is the only place a path is resolved.** Not the corpus root,
  not the build log. Pass 0 used to re-derive both and no longer does.
- **`lib/resolve.py` is the only name-resolution rule.** Ambiguity is the default
  return and must never be collapsed to the first candidate.
- **Never name a script after a stdlib module.** `inspect.py` shadows the module
  `openpyxl` and `python-docx` both import, and every file then fails with a
  misleading circular-import error. One run was lost to this.

## Environment

| variable | default | purpose |
|---|---|---|
| `NP_CORPUS_PATH` | repo root | corpus root. The one override; never hardcode a path. |
| `NP_BUILD_LOG` | `BUILD_LOG.md` | where a pass appends its run record. Tests redirect it so `pytest` cannot dirty the working tree. |
| `NP_AS_OF` | today, UTC | the date pass 4 treats as "now". `teaches` splits class dates into past and future, so the graph is deterministic within a day and not across days. Pin this to reproduce a historical build. |
| `NP_DRIVE_SA_KEY` | `service_account_key` in `config/drive.yaml` | path to the pass-0 service-account key. **A path, never the key.** Pass 0 refuses to read a key from inside the repo: `.gitignore` stops a commit, not a copy into a build context. |
| `NP_ALLOWED_HD` | `interviewkickstart.com` | the Google Workspace hosted domain a token must carry. **Deployment-level, never per request** — it is the domain rule, not a preference. Read by `web/lib/auth.py` and by `grant_access.py`, which refuses to provision an account whose provider `hd` disagrees. |
| `NP_SHARED_ACCOUNTS` | empty | comma-separated local-parts of known shared mailboxes. Flags them on every audit line and stops them being granted `recruiting` or `admin` — a shared account resolves several humans to one identity, so its access log names an account, not a person. A **configured list, not detection**: Google does not tell us, and an unlisted shared mailbox is indistinguishable from a personal one. |

## Dependencies

`openpyxl`, `PyYAML`, `python-docx`, `pytest`. Pass 0 additionally needs
`google-api-python-client` and `google-auth`. There is no manifest yet — see
`docs/AUDIT.md` §6.8.

## Web app (E2/E3)

`web/` is a read-only explorer deployed on Vercel. `member` role only; no writes,
no curation UI, no sensitive data.

| Path | |
|---|---|
| `web/lib/auth.py` | Google ID token verification — JWKS, `aud`, `iss`, `exp`, and the `hd` claim |
| `web/lib/data.py` | request-scoped reads. ALWAYS runs as `authenticated` with the caller's claims |
| `web/lib/guard.py` | route guard and the audit line |
| `api/*.py` | search, node, neighbourhood, coverage, staffing |
| `public/index.html` | the explorer |

**`web/lib/data.py` never connects as the owner.** That is what makes the route
guard safe to be the last layer: an unguarded route arrives with no identity and
RLS returns zero rows, so it answers "nothing found" rather than leaking.

`coverage` is SQL. `staffing` tiering and name resolution stay in Python, because
an `ORDER BY` expresses ranking but cannot express "these are different kinds of
evidence and merging them is the worst failure this system can produce".

See `docs/AUTH.md`.
