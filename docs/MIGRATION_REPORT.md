# Migration report

## Production data → KB: local rehearsal (2026-11-03)

**What ran:** a copy of production's `public` schema and data (two read-only
`pg_dump`s, 2026-11-03 00:48; kept only in the gitignored `backups/`) was
restored into a SEPARATE local database, `kb_realdata`. The KB migrations
0022–0029 were applied on top, and `pipeline/kb_import_projection.py` mapped
the data into the KB. Everything ran on this machine; nothing was written to
production or the dev project. This report gives counts and record ids only,
never names or values. The mapping is in docs/MIGRATION_MAPPING.md.

### 1. Copy and restore

| Table | Rows in production | Rows restored |
|---|---|---|
| node_sources | 39,414 | 39,414 |
| edges | 12,189 | 12,189 |
| nodes | 8,496 | 8,496 |
| node_layout | 3,707 | 3,707 |
| files | 1,524 | 1,524 |
| workflow_owners | 92 | 92 |
| people_aliases | 48 | 48 |
| curation_notes | 45 | 45 |
| edge_rels | 24 | 24 |
| domain_aliases | 21 | 21 |
| np_schema_migrations | 21 | 21 |
| people | 20 | 20 |
| node_types | 17 | 17 |
| profiles | 7 | 7 |
| projection_meta | 1 | 1 |
| shared_accounts | 1 | 1 |
| auth_hook_refusals | 0 | 0 |
| curation_audit | 0 | 0 |

How: production's schema first; then the data with each table's user
triggers off during COPY and back on afterwards. Foreign keys stayed enforced
throughout. With the triggers on, the "service only" guards would refuse rows,
and `derive_shared_account` would recompute `profiles.is_shared_account` before
`shared_accounts` was loaded.

**auth.users:** production's public tables have **no foreign key to
auth.users**, so the copy needs no placeholder sign-in accounts and loses no
rows. The real-data database gets a minimal `auth` schema (a `users` table
and `auth.uid()`, `auth.role()`, `auth.jwt()` and `auth.email()`, copied from
the local stack) so the functions and policies resolve. Its only row is the
local admin for 8766. Production's 7 profiles have no `auth.users` row here.

**Grants:** the dump was taken with `--no-privileges`, so the copy carries the
grants the migrations define. They're read from migrations 0001–0021 built
fresh in a scratch database (33 table/role grants), plus Supabase's default
privileges for `public`. Production's actual grants could not be compared.

### 2. Schema drift: production vs migrations 0001–0021

**None found.** Production's `public` schema, compared object by object with
migrations 0001–0021 built into a fresh database:

| Object | Production | Migrations | Differences |
|---|---|---|---|
| Columns (type, nullability, default) | 126 | 126 | 0 |
| Constraints | 59 | 59 | 0 |
| Indexes | 36 | 36 | 0 |
| Functions (definition hash) | 8 | 8 | 0 |
| Triggers | 9 | 9 | 0 |
| Policies | 17 | 17 | 0 |
| RLS enabled | 18 tables | 18 tables | 0 |

Production records 0001–0021 as applied, and every recorded checksum equals
the migration file today: no file changed after production applied it.

**Not comparable from this dump** (each needs owner access to check):
- privileges, since the dump was taken with `--no-privileges`;
- objects outside `public`, notably 0015's trigger on `auth.users`;
- the Realtime publication.

### 3. KB migrations 0022–0029 on the real data (the rehearsal)

`migrate up` applied 0022–0029 in about 1 s, then `down --to 0021` and `up`
again; both were clean. The 18 public tables were untouched (only
`np_schema_migrations` went from 21 to 29 rows). Problems and differences
recorded:

1. **No KB admin after the migration.** `kb.memberships` starts empty. Every
   one of production's 7 profiles reads the KB as a viewer (`kb.role()` falls
   back to viewer), and production's 2 site admins are **not** KB admins until
   `pipeline/kb_admins.py` runs (HANDOFF step 3). Expected, but it must happen
   in the same window.
2. **Realtime publication:** a plain database has no `supabase_realtime`, so
   0028/0029 skipped it here. On dev and production it exists, and 0029 moves
   it from `kb.audit_log` to `kb.changes`.
3. **Configuration seeded by the migrations is audited as "System"** (93 rows),
   which is correct.
4. Nothing else: no lock waits, no constraint conflicts with the existing data
   (the `kb` schema is new and touches `public` only through `kb.people()`,
   which reads `profiles`).

### 4. The 43 baseline failures: root cause fixed

`pipeline/project_graph.py` could not load the committed graph into a fresh
database. The content graph cites 1,437 content files and the four domain
Drive folders. These were registered in `files` only from the crawl manifest
in `.drive-cache/`, which is not in the repository. On any fresh checkout
those citations lost their file, and `corpus_names_a_file` (correct: a corpus
assertion must name a registered file) refused the first one.

**Fix (the constraint is unchanged):**
- `_file_rows(graph)` registers every path the graph cites, with its path
  only; no hash, size or Drive id is invented, and crawl rows still win.
- Folders are registered whether or not the cache is present.
- A corpus citation without a registered file is now a loud error instead of
  a silent NULL.

The fresh projection now loads and reproduces production's counts exactly:
nodes 8,496; edges 12,189; node_sources 39,414; node_layout 3,707. `files`
has 1,516 rows to production's 1,524; the 8 production-only rows are crawl
entries no citation uses.

**Suite** (final full run, 2026-11-03): 1,240 passed, 13 failed, 52 skipped;
**0 new failures** vs the main baseline. **30 of the 43 baseline failures now
pass.** Three of them (two client-adapter tests and one curation-write test)
also failed in the run before, so treat those as unstable. The 13 that remain
are environment issues: Windows and CRLF, executable bits, deploy-artifact
checks, ignore rules (docs/AUDIT.md); none are KB tests. The three failures
this run first introduced are fixed:
- `backups/` was added to pass 1's skip list and `.vercelignore`;
- the importer is listed in pipeline/README.md;
- the mapping lives in config/ and is checked against `taxonomy.yaml`.

### 5. Preview → apply → re-run

| Run | Created | Already there | Kept (edited in the app) |
|---|---|---|---|
| preview (rolled back) | 24,961 rows (as apply) | — | — |
| apply | 24,961 rows | — | — |
| re-run (apply again) | **0** | 5,741 records, 6,938 relationships, 1,515 links | 0 |
| an app edit, then a re-run (in a rolled-back transaction) | 0 | — | **1** (the edit survived) |

**Rows read per source table:** nodes 8,496 (0 sensitive); edges 12,189;
node_sources 39,414; node_layout 3,707; files 1,524; people 20;
people_aliases 48; workflow_owners 92; domain_aliases 21; curation_notes 45;
profiles 7 (+ the local admin).

**Created:**

| What | Count |
|---|---|
| Records | **5,741**: topic 2,513 · instructor 1,911 · module 924 · session 134 · process 92 · domain 46 · team member 43 · program 42 · week 20 · theme 16 |
| Relationships | **6,938**: covers 2,758 · teaches 2,274 · sme 1,133 · contains 617 · supported by 58 · owned by 55 · delivered by 43 |
| Links | **1,827**: 1,515 from artifact records (Drive URLs), 312 UpLevel and Drive-folder links |
| Links on records | **10,434**: the artifact relationships and the 11,615 resolvable source citations, one per record and link |
| Configuration | 2 record types (Team member, Theme), 16 fields on built-in types, 3 relationship types (owned by, supported by, delivered by) |
| Graph positions | 3,707 read into the shared layout |
| Curation notes | 41 placed in the body of their person or process |

**Duplicates merged:**

| What | Count | Why |
|---|---|---|
| Topics with the same name | 220 into 149 | the same concept extracted from several files |
| Artifacts with the same Drive URL | 983 | one file seen as both a `file` and a `slide_deck`, and similar |
| Relationship rows for the same pair | 4,185 | the projection keeps one edge row per piece of evidence (`covers_topic` 6,271 rows = 2,770 pairs) |

**Rejected (37 rows):**
- 36 topics that the pipeline itself marked `not_a_topic` (35 person names, 1
  person bio). Ids are in `backups/import-apply.json`.
- 1 topic whose name contains an e-mail address or URL: `con_7957d10a9373c9e3`.
- 53 relationships whose end was one of these rejected rows.

**Unmapped columns** (kept in the projection, not in the KB):
- **instructor:** `file_count`, `cross_validated`, `renderable`, `roster_count`,
  `merge_ids`, `merged_from`, `merged_label_raw`. **Deliberately not imported:**
  `pipeline_status`, `admitted_by`, `requests_to`, `requests_from`,
  `decline_rate`, `declined_count`, `confirmed_count`, `current_company`,
  `past_companies`, `years_experience`, `current_designation` and
  `withdrawn_roles`. These are recruiting-pipeline data about external people
  and don't belong in a curriculum knowledge base.
- **person:** `employee_ids` (never a key; CLAUDE.md §2a), `status`,
  `seen_in_sheets`, first and last seen quarter, `corpus_disagrees`,
  `file_count`.
- **file and slide_deck:** `owner_domain`, `unavailable_rule`, `unavailable_reason`,
  `parsed`, `sheet_count`, `slide_count`, `superseded_by`, `drive_file_id`.
  "Not available" became the tag `unavailable`.
- **module:** `domain_slug`, `label_variants` and the merge bookkeeping.
- **content_topic:** `locator_kind`, `label_had_link`.
- **Everywhere:** `file_count`, and `workflow.theme_id`, which is mapped through
  the `belongs_to` relationship instead.
- **edges.props:** the per-edge evidence (rank, sources, slide, deck URL,
  provenance, tier, page). Kept: the `teaches` role and class dates, as the
  relationship's note.
- **Tables:** `profiles`, `shared_accounts`, `auth_hook_refusals`,
  `curation_audit`, `projection_meta`, `np_schema_migrations`, `node_types`,
  `edge_rels`, `files` (its URLs arrive through the artifacts). Reasons are in
  the import report.

**Broken or suspicious links:**
- 508 links tagged `unavailable`, which production marks as unreadable.
- 63 tagged `historical`.
- 441 links attached to no record.
- 24 citations whose file has no Drive URL, so no link.
- 0 malformed URLs.

No link health was checked: the server never fetches URLs (D13), and
`check_broken_links` needs a token holder.

**Records with no owner or placement:**
- **All 5,741 records have no owner.** The projection names owners as people
  (team members and workflow suggestions), never as sign-in accounts, so
  ownership arrives as "owned by", "supported by" and "delivered by"
  relationships. 7 of the 46 domains have none. None of the 92 processes has a
  confirmed owner (39 carry an unconfirmed suggestion, kept as a field).
- **No placement:** 721 of the 924 modules sit in no program or domain, and
  none of the 46 domains sits in a program (the projection doesn't place them).
- **Not connected to anything:** 976 records (instructor 892, module 53,
  team member 17, program 14).
- **Marked for review:** 123 (instructor 94, topic 26, domain 2, module 1).

### 6. Top 10 data problems to look at

1. **No KB admin** until `pipeline/kb_admins.py` runs; every profile is a
   viewer (section 3).
2. **Nobody owns anything:** all 5,741 records have no owner account. Owners
   need to be assigned (bulk owner in All records), or team members linked to
   sign-in accounts.
3. **892 instructors are connected to nothing:** they appear in rosters but
   teach no module and are no subject expert.
4. **721 modules and all 46 domains have no placement** in a program.
5. **508 links are marked unavailable** in production (unreadable files) and
   **441 links hang on no record.**
6. **92 processes have no confirmed owner;** 39 have a suggestion waiting for
   confirmation.
7. **37 rows rejected:** 36 person names extracted as topics, and 1 topic name
   containing an address or URL (`con_7957d10a9373c9e3`).
8. **220 duplicate topics** were merged by name. Check that none merged
   genuinely different topics.
9. **2 domains share a name** with another domain (`dom_8eca42bd0bd17ab8`,
   `dom_fadfd977f7d5b5d7`; one is shown as "(2)" and marked for review), plus
   2 module pairs and 5 groups of weeks, which were kept apart by their scope.
10. **123 records are marked for review** (94 instructors and 26 topics flagged
    by the pipeline, plus the same-name cases).

### 7. What has to happen differently on dev and production

- **No dump or restore:** the data is already there. Apply 0022–0029 with
  `pipeline/migrate.py up` through the **session** pooler, back up first, and
  grant KB admins right away (`pipeline/kb_admins.py`).
- **Run the import** with `SUPABASE_DB_URL_SESSION=<project session pooler>
  python pipeline/kb_import_projection.py preview --as <admin email>`, read the
  counts, then `apply`. The `--as` admin must have signed in once and have a
  KB admin membership. Re-running is safe.
- **Duration:** apply took about 30 s locally; through the pooler,
  expect a few minutes. It's one transaction, so a failure leaves nothing
  behind.
- **Realtime:** 0029 moves the publication to `kb.changes` on a real project
  (skipped here).
- **Privileges and `auth.users` objects** could not be compared from the dump.
  Check them in the project (SQL in HANDOFF).
- **The real-data copy's auth and admin are local constructions**
  (`eval/kb_realdata_db.py`). Nothing of them is part of what runs on
  dev or production.

---

---

## Sheets → KB (synthetic fixture, 2026-11-02)

**Run:** 2026-11-02, local Supabase stack only, source = SYNTHETIC fixture
(`fixtures/sheets_sample.json`). **The live import is UNTESTED**: no Google
credentials were available. Nothing was written to any shared database.

### Dry run → apply → re-apply (actual output)

```
dry-run from fixture:sheets_sample.json
  create=13  update=0  unchanged=0  duplicate=0  conflict=0  invalid=7  broken_references=1
apply from fixture:sheets_sample.json
  create=13  update=0  unchanged=0  duplicate=0  conflict=0  invalid=7  broken_references=1
  written: nodes_created=11  edges_created=9  resources_created=2  attachments_created=2  skipped_races=0
apply from fixture:sheets_sample.json            # re-run: idempotent
  create=0  update=0  unchanged=13  duplicate=0  conflict=0  invalid=7  broken_references=1
  written: (all zero)
```

The 7 invalid rows are planted in the fixture on purpose: a case-variant
duplicate key, a blank key, a module whose course does not exist, a name with
`@`, an empty token in a multi-value cell, an invalid URL, and a duplicate URL.
The broken reference is a course pointing at a program that does not exist.

Conflict handling (app edit after import → flagged, not overwritten) and the
app-duplicate rule are proven in `tests/test_kb_import.py`.

### Running it for real (owner)

```bash
export SUPABASE_DB_URL_SESSION=...             # DEV project first, never prod first
export NP_DRIVE_SA_KEY=~/.config/np-autopilot/drive-sa.json   # path, outside the repo
export KB_SHEETS_ID=<spreadsheet id>           # sheet shared read-only to the SA address
python3 pipeline/kb_import_sheets.py --as you@interviewkickstart.com --report /tmp/dry.json
# read the report; fix the sheet or the YAML; repeat until it says what you expect
python3 pipeline/kb_import_sheets.py --as you@interviewkickstart.com --apply --report /tmp/apply.json
```

Against production (only after the dev run is clean): back up first
(`pg_dump --schema=kb "$SUPABASE_DB_URL_SESSION" > backups/kb-$(date +%F).sql`),
then add `--allow-production`. The script refuses production without it.
