# Live sources instead of downloaded files: audit and design (2026-11-07)

Status: **audit done, design proposed, not yet built.** Nothing was deleted. `backups/` holds
safety backups, not sources, and stays.

## Target

Each source is stored in the database as:

- its **live URL** and **Drive/Sheets/Confluence ID**;
- **metadata**: kind, MIME type, parent, modified time or version, checksum, and the owner's
  *domain* only (never a person's address).

Its content is **extracted into the database with provenance**: source ID, version, and
tab/row, slide, page or section. It is **re-crawled by ID** when the modified time or version
changes. A local copy is allowed **only as a processing cache**, never as the source of truth.

## What the audit found

**The app and the API read no downloaded files at runtime.** `api/*`, `web/lib/kb/*` and the map
read only Postgres and `config/*.yaml`. `vercel.json` already excludes the corpus folders from
the functions.

**The pipeline upstream is where local files act as the source of truth.** Every fact enters the
database from a local copy, by way of `knowledge/*.json` and the `public.*` projection, keyed by
a corpus-relative **file path** instead of a Drive ID. Drive's `modifiedTime` lives only in local
manifest files. No database column stores it.

| # | Where | Local file used as truth | Replaced by |
|---|---|---|---|
| 1 | `pipeline/lib/paths.py` `corpus_root()` | Defaults to the repo root, i.e. a hand export of the Drive folders | A `sources` table keyed by Drive ID; a path becomes a display label |
| 2 | `pipeline/lib/sources.py` | About 25 hard-coded `folder/File.xlsx` paths × tab × column | The same tab/column registry, keyed by `drive_file_id` |
| 3 | `pipeline/00_fetch_drive.py` | `.drive-cache/.manifest.json`: the only store of id, MIME type and modifiedTime | Rows in `sources`; the bytes become a temporary cache |
| 4 | `pipeline/01_walk_corpus.py` | `knowledge/files.json`, which records the **local** mtime, not Drive's | The Drive listing in `sources`; the hash kept only to validate the cache |
| 5 | `pipeline/refresh.py` | Falls back to the hand export without asking (`--allow-fallback`) | Re-crawl by ID (changes since the last modifiedTime), with no fallback |
| 6 | `pipeline/02_extract.py` | Workbooks under `corpus_root()` (not the cache that pass 1 hashed, so the two can disagree) | Fetch by ID into a cache; provenance {id, version, tab, row, col} |
| 7 | `pipeline/04_build_graph.py` | A hard-coded owners workbook; file nodes carry a path but no ID, URL or modified time | Same as #6; file nodes from `sources` |
| 8 | `pipeline/gen_workflow_owners.py` | A local workflow inventory | Retired with the workflows (2026-11-07), or fetched by ID |
| 9 | `pipeline/06_crawl_content.py`, `list_folders.py`, `lib/folder_links.py` | `content-rowB/manifest.json`, `folders.json`, `text/*.txt` (cache by design, with re-crawl by modifiedTime, but held only on disk) | Manifest and folder rows in the database; extracted text in a `source_content` table |
| 10 | `pipeline/07_build_content_graph.py` | Reads the content cache as truth for `content_graph.json` | Reads the database tables |
| 11 | `pipeline/fetch_mastersheet.py`, `lib/freshness.py` | Fetch record `<id>.json` (modifiedTime, version, sha256): **the model to generalise** | The same pattern for every source, with the record in a database row |
| 12 | `pipeline/project_graph.py` | Truncates and reloads `public.*` from `knowledge/*.json` | An upsert keyed by (source ID, version) |
| 13 | `pipeline/lib/graphio.py`, `query.py`, `commands/*.md` | The committed `knowledge/graph.json`: a frozen snapshot that plugin commands read | The plugin queries `/api/kb/*`, as the MCP server already does; then stop tracking `graph.json` |
| 14 | `web/lib/kb/sync.py` | Database only, but it joins citations to links **by relative path** | Join by `drive_file_id` |
| 15 | `pipeline/kb_import_sheets.py` | Live Sheets API by ID (good); also accepts a fixture file on `--apply` | Refuse fixture sources outside development |

**Already in the database, and reused by the design:**

- `public.files`: `drive_file_id`, `drive_url`, sha256. It has no modifiedTime, version or MIME type.
- `public.node_sources`: tab, row, column, page and slide provenance.
- `kb.resources`: `url`, `url_norm`, `kind`, `external_id`.
- `kb.nodes.external_id`.
- `kb.sync_map`: per-unit checksums and seen/removed times, i.e. the change-detection engine.
- `kb.import_runs`, `kb.sync_runs`, `kb.sync_exclusions`.

## Design

```text
sources        (id PK, kind: drive_file|sheet|doc|slides|folder|confluence_page, external_id,
                url, mime, parent_id, path_hint, modified_time, version, md5, owner_domain,
                last_crawled_at, content_sha256, extractor_version, status, error)
source_content (source_id, version, locator: tab/row | slide | page | section, text, extracted_at)
provenance     (record or relationship) -> (source_id, version, locator)
```

**Crawl.**

1. A Drive `changes`/list query asks for anything with a modifiedTime newer than the stored
   one. For Confluence, compare the page version.
2. Only the changed sources are exported into a throwaway cache, re-extracted and upserted.
3. `kb.sync_map` checksums carry the changes into `kb`.
4. Access failures (permission, broken link, unsupported format) are stored on the source row
   (`status`, `error`), so the Sources page can list them. Nothing is skipped silently.

The read-only inventory of 2026-11-07 ([../operations/sources-inventory-2026-11-07.md](../operations/sources-inventory-2026-11-07.md))
is the first data for this table.

## Order

1. Migration: `sources` and `source_content`, plus modifiedTime, version and MIME type on
   `files`. Backfill from the stored `drive_file_id`s and from the inventory.
2. Fetch passes 00 and 06, `list_folders` and `fetch_mastersheet` write their rows to `sources`.
   Generalise `freshness.py` to every source.
3. Re-key `sources.py` and the hard-coded paths in 02 and 04 by Drive ID. Remove the
   `corpus_root()` and `--allow-fallback` defaults.
4. Store extracted text and provenance in the database; pass 07 reads the database.
5. Projection becomes an upsert by source ID and version. The sync joins citations by ID.
6. Plugin commands use the API. Stop tracking `knowledge/graph.json`. Update
   `docs/architecture/single-source-of-truth.md`.

Confluence (the KYPs) goes straight into `sources` as `confluence_page` rows with their
version. The pilot staging of 2026-11-07 already carries page ID, version and heading on every
item ([kyp-structure-and-model.md](kyp-structure-and-model.md)).
