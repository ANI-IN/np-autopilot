# Changelog

Notable changes, newest first. Production runs `main`, at database migration
0021. Everything below "Unreleased" is on the branch
`auto/knowledge-platform-20261102` and goes live through
[docs/operations/GO_LIVE.md](docs/operations/GO_LIVE.md). The detailed history
is in [docs/project-history/](docs/project-history/README.md).

## Unreleased

### Autonomous run B (2026-11-07)

- **Graph page:** an unreadable or incomplete server reply is now reported as such
  (it used to become `{}` and fail with "reading 'forEach'"). The whole graph loads
  in pages of 1,000 records. The toolbar is safe before the graph loads, "Try again"
  can be clicked, and "Save view" switches to the saved view.
- **Weeks, workflows and themes retired:** the map's week filter, `?week=` links,
  the timeline views, and the week, workflow and theme types are gone. The data is
  archived reversibly by `scripts/retire_legacy_sections.py`, with week numbers kept
  on the course→module links. The sync skips `retired_types`.
- **Visual direction A** (with C's search-first Home and B's dark theme): a new
  navigation with an Admin group, a search results page, an Admin overview, a
  light/dark toggle that follows the system, and WCAG AA chips. The graph editor
  is admin-only, and its layout writes require admin.
- Docs: `docs/design/phase1/DECISION.md`, `kyp-structure-and-model.md`,
  `live-sources.md`, `docs/operations/sources-inventory-2026-11-07.md`,
  `docs/testing/E2E-REPORT.md`.

### Local end-to-end test before the preview (2026-11-06)

- **Graph rename:** a rename keeps the version it started from, so another
  person's rename arriving live during typing raises the conflict dialog instead
  of being silently overwritten.
- **Live updates:** the page keeps polling fast until Realtime confirms its
  subscription. After idle, a change could otherwise show up to 20 s late.
- **Local servers:** a listen queue of 128 fixes intermittent blank pages.
- `eval/kb_journey_check.py`: the pre-deploy journey (real sign-in, three roles,
  MCP, live tabs).

### Run 6: one source of truth, the graph, legacy cleanup, security (2026-11-03/04)

- **One source of truth:** every view reads the `kb` schema, including the NP
  Autopilot map at `/` (`web/lib/kb/npmap.py`; rollback `NP_MAP_SOURCE=old`).
  `GET /api/kb/graph` serves the Graph page; the map's routes read kb too. The change feed carries a kind and
  the affected records, and every page updates within about 3 s (26 operations
  checked on the Graph page and on `/`).
- **Graph:** hierarchy layout by default, plus force, radial and saved positions;
  grouping and bundles; legend as a filter, breadcrumbs, focus mode,
  search-jump, minimap, labels that don't overlap, a shortcut sheet. Leaving
  the page releases its memory (heap 6.0 → 9.6 MB over 50 openings, was 9 → 165 MB).
- **Legacy data:** owner-approved permanent deletion of 42 legacy domains and 904
  legacy modules, with export and a tested restore
  (`pipeline/kb_legacy_delete.py`); migration 0037 stops the sync re-creating
  them. Run on the local copy and on DEV; not on production.
- **Security:** the IK domain is checked on the server on every request;
  security headers on every response; an access sweep over every route and six
  kinds of caller; one validation layer shared by the sync and the UI; the AI's
  token can't grant roles or delete permanently.
- **People and members:** invite members by e-mail before their first sign-in;
  the last admin can't be removed; owners linked to people (CSV with a match
  preview, linking at sign-in, "Claim this profile").
- **UI:** Interview Kickstart brand colours and logo; a one-screen dashboard
  (1536×730 and 1920×1080); Activity as plain sentences; navigation names match
  page titles; old bookmarks redirect; WCAG AA contrast.
- **Performance:** Data quality 29 s → 0.05 s; every screen interactive in
  0.26–0.74 s on real data; graph expand p95 48 ms.
- **Code:** the NP Autopilot sync sits behind a connector interface
  (`web/lib/kb/connectors/`); legacy code removed with evidence.
- **Repository:** cleanup (process logs to `docs/project-history/`, outdated
  reports and screenshots removed, generated graph files untracked),
  documentation with diagrams, CONTRIBUTING, SECURITY and templates.
- Migrations 0032–0035 and 0037 (0036 unused).

### Run 5: parity with NP Autopilot, scheduled sync, dev database (2026-11-03)

- Parity with NP Autopilot's own legacy and role rules, with no unexplained
  differences; owners derived from roles (P → owner, B1–B3 → co-owners).
- A scheduled, incremental, locked one-way sync from the pipeline's tables into
  the KB (pg_cron + pg_net, migration 0031). It never overwrites a KB edit; it
  records a conflict instead.
- A reversible archive of legacy records, with a one-command restore.
- The DEV Supabase project: first import of 25,226 units in 245 s.
- Migrations 0030–0031.

### Runs 2–3: the knowledge base workspace (2026-11-02)

- The `kb` schema with row-level security, versioning, an append-only audit
  log and archive cascades (migrations 0022–0029).
- The workspace at `/kb/`: records and relationships with custom types, links,
  tags, owners, templates, approvals, saved views, Activity, Data quality, a
  ⌘K palette and the in-app Guide.
- The MCP server (`mcp_server/kb_server.py`) and the
  `ik-knowledge-assistant` Claude plugin.

## Production (`main`)

### 2026-09-30: launch window

- The NP Autopilot map at `/`, backed by the pipeline's graph in Supabase
  (migrations 0001–0021): about 8,500 nodes and 12,200 edges, with a layout
  computed at projection time.
- Google sign-in restricted to `interviewkickstart.com`; roles enforced by RLS.
- The intake pipeline: read-only Drive fetch, extraction, graph build and
  projection (`pipeline/`).
