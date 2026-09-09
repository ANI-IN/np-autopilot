# pipeline

Passes are separate. Each writes to disk; the next reads from disk. Any pass can
be re-run without repeating the one before.

| Pass | Script | Status |
|---|---|---|
| 0 | `00_fetch_drive.py` | built — fetches Drive to `.drive-cache/` |
| 1 | `01_walk_corpus.py` | **not built** — B3 |
| 2 | `02_extract.py` | **not built** — B4 |
| 3 | `03_resolve.py` | **not built** — B5 |
| 4 | `04_build_graph.py` | **not built** — B6 |
| 5 | `05_render_html.py` | **not built** — B7 |
| — | `validate.py` | **not built** — B6 |

Helpers: `gen_workflow_owners.py` regenerates the 92-row ownership stub.

`lib/taxonomy.py` is the only module that may read `config/taxonomy.yaml`
(B2). `lib/paths.py` is the only place a corpus path is resolved.
