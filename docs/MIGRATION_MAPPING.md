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
