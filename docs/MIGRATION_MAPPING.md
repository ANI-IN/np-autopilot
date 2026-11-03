# Sheets → KB migration mapping

Source of truth for the mapping: `config/kb-sheets-mapping.yaml`. Code:
`pipeline/lib/kb_sheets.py` (stage / validate / plan / apply) and
`pipeline/kb_import_sheets.py` (fetch + CLI). Tests: `tests/test_kb_import.py`.

## Status of the source

**The real workbook was not inspected in this run.** No Google credentials were
available (DEGRADED mode), and CLAUDE.md records that the "NP Autopilot" master
spreadsheet has never been located in the corpus folder. The mapping is therefore
written against the Sheets API **response shape** (`values.batchGet`) and a
**synthetic** fixture (`fixtures/sheets_sample.json`, every value invented). When
the real sheet is available, adjust the tab and header names in the YAML; the
rules below do not change.

## Tabs → entities

| Tab | Becomes | Row key (→ external_id) | Fields | Relationships |
|---|---|---|---|---|
| Programs | node `program` | Program | name←Program, summary←Description | — |
| Courses | node `course` | Course | name←Course, summary←Summary | program **contains** course (from `Program`) |
| Modules | node `module`, scoped to its course | Course + Module | name←Module, summary←Summary | course **contains** module |
| Topics | node `topic` | Topic | name←Topic, summary←Notes | module (in `Course`) **covers** topic |
| Instructors | node `instructor` (name only) | Instructor | name←Instructor | instructor **teaches** each course in `Teaches` (comma list) |
| Resources | resource | URL | url, title, kind | attached to the module (Course+Module) or, when Module is blank, the course |

`external_id = <spreadsheet id>:<tab>:<normalised key>` — trimmed, whitespace
collapsed, lower-cased. A row that moves keeps its identity; a renamed key is a
new record (and the old one is left alone, never deleted by an import).

## Rules

1. **Allow-list.** Only the headers named in the YAML are read. Anything else in
   the sheet (e.g. `Internal Notes` in the fixture) never enters staging.
2. **No contact data.** A header matching e-mail / phone / mobile / WhatsApp /
   LinkedIn / contact / address is refused at mapping load — even if someone maps
   it. Node names containing `@` or a URL are invalid rows (and a DB constraint).
3. **Positional cells.** Short rows are padded, blanks never compacted.
4. **Multi-value cells** split on `,` only; an empty token (`A, , B`) fails the
   row instead of being skipped.
5. **Duplicates in the sheet** (same normalised key) → the later row is invalid
   ("duplicate of row N").
6. **Duplicates against the app** (a live record with the same type + scope + name
   and no import identity) → reported `duplicate`, not created, not adopted.
   Adoption is a ROADMAP item; it needs a human decision per record.
7. **Conflict rule.** If a record's `version` has moved past `imported_version`
   (someone edited it in the app) or it was archived in the app, the import
   **never** overwrites it; the row is reported `conflict`.
8. **Unedited records** whose sheet values changed are updated and re-stamped
   (`imported_version = version`).
9. **Broken references** (a link or attachment to a record that exists in
   neither the sheet nor the app) are reported; the row itself still imports.
10. **Report counts, enumerates only rows needing a human** (CLAUDE.md §5).

## Attribution

The importer acts as a named KB admin (`--as <profile email>`), through the
service layer and that admin's RLS, with `actor_type = 'import'` in the audit log.

## Custom fields (run 2)

A tab can target any record type, including custom ones (`type: case_study`),
and fill its custom fields with `props: {field_key: Column}`. Cells are
converted by the field's kind (number, duration, date, date-time, URL, checkbox
yes/no, text); select cells match an option's value or label; person and record
reference fields are not imported from cells. A cell that does not convert
makes the row `invalid` in the dry run with the field named; nothing is written.
Contact-shaped headers are refused in `props` exactly as in `fields`.

---

# Projection (existing production data) → KB mapping (2026-11-03)

Code: `pipeline/kb_import_projection.py`. Mapping: `config/kb-projection-mapping.yaml`
(checked against `config/taxonomy.yaml` at start; a taxonomy change fails loudly).
Results: docs/MIGRATION_REPORT.md. Run: `preview` (rolls back) then `apply`,
`--as <KB admin e-mail>`; idempotent; never overwrites a record edited in the app.

## Tables

| Source table | Goes to | Notes |
|---|---|---|
| `nodes` (not sensitive) | `kb.nodes` records, or `kb.resources` links | by type, below; `external_id = 'np:<id>'` |
| `edges` | `kb.edges`, or a link on a record | one relationship per (pair, type): the projection repeats a pair once per piece of evidence |
| `node_sources` | links on records, note "Source" | each record gets one link per distinct cited file (the file's Drive URL) |
| `node_layout` | `kb.graph_positions` (shared layout) | only where nobody has placed the record yet |
| `people` | Team member fields: team, title, seniority | matched by canonical name |
| `people_aliases` | Team member "Also known as" | |
| `domain_aliases` | Domain "Also known as" | matched by domain name (15 of 21) |
| `workflow_owners` | Process "Suggested owner" (unconfirmed) | no owner is confirmed in the source |
| `curation_notes` | the record's body, "Curation notes" | people.yaml and workflow-owners.yaml notes; author e-mail left out |
| `files` | (through artifacts) | its Drive URLs reach the KB via the artifact records that cite them |
| `profiles`, `shared_accounts`, `auth_hook_refusals`, `curation_audit`, `projection_meta`, `np_schema_migrations`, `node_types`, `edge_rels` | not mapped | sign-in, audit and bookkeeping of the original site; KB roles are granted with `pipeline/kb_admins.py` |

## Record types

| Projection type | KB type | Fields carried | Special rules |
|---|---|---|---|
| program | Program | Family, Document type | |
| domain | Domain | Cadence, Stage, Also known as | UpLevel and Drive-folder URL become links |
| module | Module | Granularity, Sequence | UpLevel link and Drive folders become links; scope = its only program or domain |
| class_session | Live session | Session kind, Resource type | UpLevel link and Drive folders become links; scope = its only module |
| program_week | Week | Week number | scope = the module it is scheduled in (so "Week 1" can repeat) |
| content_topic | Topic | | same name = same topic (merged); `not_a_topic` rows REJECTED; `boilerplate` tagged and marked for review |
| instructor | Instructor | | `review` → marked for review; recruiting-pipeline properties are NOT imported |
| workflow | Process | Workflow id, Effort, Steps, Alerts, Tools, Suggested owner | placed in its Theme |
| person | **Team member** (new type) | Team, Title, Seniority, Also known as | `employee_ids` never imported |
| theme | **Theme** (new type) | Theme id | allowed parent of Process |
| slide_deck, curriculum_doc, code_repo, assignment, assignment_review, file | **links** (`kb.resources`) | | one link per Drive URL; kind from the type, or from the MIME type for files; tags `historical`, `unavailable` |

A name that breaks a KB rule (contains an e-mail address or URL, or is over
300 characters) is rejected with its id. Two DIFFERENT records with the same
name and scope are both kept: the second as "Name (2)", marked for review.

## Relationships

| Projection relationship | KB |
|---|---|
| module covers_topic content_topic | covers |
| instructor teaches module / class_session | teaches (note: role and class dates) |
| module taught_by instructor | teaches (reversed) |
| instructor expert_in domain | subject expert for (sme) |
| program contains module; domain offers module; module delivers_session class_session; module scheduled_in program_week | contains (placement) |
| program covers domain | covers |
| workflow belongs_to theme | contains (Theme → Process) |
| domain owned_by / supported_by / delivered_by person | **owned by / supported by / delivered by** (new types) → Team member |
| module delivers file; presented_with slide_deck; ships_with code_repo; assessed_by assignment; reviewed_in assignment_review; domain described_by curriculum_doc; curriculum_doc introduces module | a link on the record (note says which) |

## Re-runs and edits in the app

- Records, links and relationships are found by `external_id`; nothing that
  exists is created again.
- A record is refreshed only while its `version` still equals
  `imported_version` (recorded in the same write as the import's change). Once
  someone edits it in the app, the import leaves it alone and counts it
  "kept (edited in the app)".
- Graph positions are written only where none exists, so a layout arranged
  in the app is never moved back.
- The import is one transaction, attributed to the named admin as an import
  (Activity: "Import (run by …)").

## Run 5: parity with NP Autopilot, owners, the sync

The import is now the sync engine `web/lib/kb/sync.py`
(`pipeline/kb_import_projection.py` is its CLI); docs/PARITY_REPORT.md proves
the result against NP Autopilot's own model.

- **Current vs legacy follows NP Autopilot** (public/index.html): a module
  without `domain_slug` is legacy (`adaptNode`); a domain is current when it
  `offers` a current module (`model()`); an instructor is current when it is an
  end of a `tier: mastersheet` edge (`currentInstructors()`); every programme
  is from the older sheets. Legacy records carry `is_legacy` and the tag
  `legacy`, are hidden from default lists and counts, and are filterable.
- **No merging by name.** One record per source row (topics: 2,733 of 2,770;
  37 rejected by the shape rules). A generic name sits under the record it
  belongs to (scope); a remaining same-name pair is kept apart with "(2)".
- **Roles.** `teaches` (instructor -> module) carries `props.role` = primary /
  backup_1..3, ONLY from the current mastersheet (`taught_by`,
  `instructor_role`); the older sheets' role is kept as `props.older_role`.
- **Owners by role.** Module: the mastersheet primary -> `owner_record_id`;
  the backups in order -> `co_owner_record_ids`. Domain: `owned_by` -> owner
  record, `supported_by` -> backups. A person record linked to a sign-in
  (`kb.person_accounts`, by e-mail, now or at their first sign-in) makes that
  person the account owner / co-owner of the same records.
- **Incremental.** kb.sync_map keeps, per unit (record, link, relationship,
  link on a record), the source checksum and a hash of what the sync wrote;
  only changes are written, an app edit becomes a conflict, a vanished row is
  flagged "removed at source". Details: docs/DEPLOYMENT.md "Scheduled sync".
- **Mapping keys** added in `config/kb-projection-mapping.yaml`: `roles`
  (module, domain, instructor, programme, domain_offers, programme_covers,
  programme_contains, session_link, topic_link, owner_link, co_owner_link,
  session, deck, deck_link, expertise), `new_record_types`, `type_fields`,
  `placement`. All are checked against config/taxonomy.yaml at start.
