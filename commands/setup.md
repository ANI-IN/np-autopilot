---
description: Verify the knowledge graph loaded, report its counts and build date, and state what it was built from.
disable-model-invocation: true
---

Report on the installed graph. Do not attempt to reach the corpus — it is not
bundled with the plugin, and its absence on a teammate's machine is expected and
fine.

1. Read `${CLAUDE_PLUGIN_ROOT}/knowledge/graph.json` and report `meta`: node and
   edge counts by type, `built_at`, `taxonomy_version`.
2. Warn if `built_at` is more than 30 days old. A stale graph does not break; it
   silently becomes wrong.
3. **Always print this, verbatim, before any counts:**

   > ⚠ This graph was built from a hand-exported local folder, not Google Drive.
   > `00_fetch_drive.py` has never been run; Drive ingestion is deferred to v2.
   > The three-tab "NP Autopilot" master spreadsheet has never been located — if
   > it exists in Drive, `Owner` and `Automation` may return as node types and
   > the taxonomy is redone. Counts for `person`, `instructor` and `module` are
   > floors, not totals.

4. Distinguish the two failure modes explicitly: **graph missing** is a
   packaging problem; **corpus missing** is expected and not an error.
