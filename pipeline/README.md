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

## Dependencies

`openpyxl`, `PyYAML`, `python-docx`, `pytest`. Pass 0 additionally needs
`google-api-python-client` and `google-auth`. There is no manifest yet — see
`docs/AUDIT.md` §6.8.
