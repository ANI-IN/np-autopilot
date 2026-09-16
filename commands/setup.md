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

   > This graph is built from Google Drive, fetched read-only by a service
   > account. The three-tab "NP Autopilot" master spreadsheet is **not in that
   > folder** — checked across all 374 worksheets — so `Owner` and `Automation`
   > are not returning as node types. Counts for `person`, `instructor` and
   > `module` remain **floors, not totals**: 127 of 374 worksheets have been read
   > by an entity scan, and fetching from Drive fixed reproducibility, not
   > coverage.

   If `meta.drive_deferred` is true, say the opposite: the graph came from a
   hand-export, pass 0 did not run, and nothing about Drive's contents is
   supported.

4. Distinguish the two failure modes explicitly: **graph missing** is a
   packaging problem; **corpus missing** is expected and not an error.
