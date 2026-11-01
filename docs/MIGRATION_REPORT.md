# Migration report — Sheets → KB

**Run:** 2026-11-02, local Supabase stack only, source = SYNTHETIC fixture
(`fixtures/sheets_sample.json`). **The live import is UNTESTED**: no Google
credentials were available. Nothing was written to any shared database.

## Dry run → apply → re-apply (actual output)

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

## Running it for real (owner)

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
