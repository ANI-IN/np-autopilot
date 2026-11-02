# Inventory — KB workspace

Two snapshots of the same app, taken by clicking through the running local demo
(`eval/kb_demo_server.py`, seeded with `eval/kb_demo_seed.py`), not by reading code.

- **Before** — 2026-11-02 11:50, commit `33a5d48` (end of run 1 + demo). Screens:
  `docs/redesign/before/<width>-<screen>.png` (1440/1280/1024) and dialogs in
  `docs/inventory/screens/`.
- **After** — see the run-2 section, then **Run 3** at the end (the current state).

docs/SPEC.md does not exist in this repository (PROGRESS D15); the gap list below
is measured against the run-2 brief, which is the specification for this work.

---

## Before

### Screens

| Screen | Route | Screenshot (1440) | Notes |
|---|---|---|---|
| Sign-in (demo only) | `/local-login` | inventory/screens/login.png | |
| Dashboard | `#/` | redesign/before/1440-dashboard.png | type count cards, raw activity log |
| All records | `#/records` | 1440-records.png | 7 filter controls wrap onto two rows |
| Programs / Courses | `#/programs`, `#/courses` | 1440-programs.png, 1440-courses.png | same table, type fixed |
| Record detail | `?open=<id>` | 1440-record-detail.png | 50% overlay panel, one long scroll |
| Resources | `#/resources` | 1440-resources.png | |
| Graph | `#/graph[/id]` | 1440-graph-home.png, 1440-graph.png | |
| Data quality | `#/quality` | 1440-quality.png | |
| Approvals | `#/proposals` | 1440-approvals.png | |
| Settings | `#/settings` | 1440-settings.png | tokens, roles, read-only type list |
| New record | dialog | inventory/screens/new-record.png | type, name, summary, scope, status only |
| Attach / Connect / Archive | dialogs | attach.png, connect.png, archive-confirm.png | |
| ⌘K palette | overlay | palette.png | |
| Outline, Archived, Guide | — | 1440-outline.png etc. | **do not exist** ("Page not found") |

### CRUD matrix (before)

W = WORKS, P = PARTIAL, M = MISSING, B = BROKEN.

| Entity | Create | View | Edit | Archive | Restore | Perm. delete | Duplicate | Bulk edit | Import | Export |
|---|---|---|---|---|---|---|---|---|---|---|
| Record (any type) | W | W | W (inline) | W | W | P (admin, only from an archived record's panel; no Archived page to find it) | W | M | P (Sheets CLI only, no UI) | P (CSV of the list; no import counterpart) |
| Course / program | W (incl. inline from picker) | W | W | W | W | P (as records) | W | M | P | P |
| Relationship | W | W (panel, graph) | P (API only: note/props; no UI) | W (× on row, editor) | P (API only; no UI) | P (API only) | M | M | P | M |
| Resource | W | W | W | W | W | P (API only; no UI) | M | M | P | M |
| Attachment (record ↔ resource) | W | W | P (note via API only) | W (detach) | M | M | — | M | P | M |
| Tag | W (add on record) | W | M (no rename) | M | M | M | — | M | M | M |
| Record type | P (API `POST /types/node`; no UI) | W (read-only list) | M | M | M | M | M | — | M | M |
| Relationship rule | P (API only) | W (read-only) | M | M | M | M | — | — | M | M |
| Member role | W (admin) | W | W | — | — | M (no removal) | — | M | — | M |
| API token | W | W | — | W (revoke) | — | — | — | — | — | — |
| Proposal | W (from archive) | W | — | — | — | — | — | — | — | — |

### Gaps against the brief (section by section)

- **C1 design:** purple accent (`#4f46e5`, brand-mark gradient) — both banned. No icon
  set (text-only nav). No dark-mode toggle (follows the system only). System font,
  not Inter/Geist. Card grid for tabular counts on the dashboard. Filler copy
  ("Every authored record, filterable."). Status pill shown on every row even when
  live. Detail panel overlays the list (does not push) and is not resizable or
  expandable to a page. No sticky table header, no row checkboxes, no bulk bar,
  no density toggle, no j/k/x/e keyboard model, no saved views, no breadcrumb, no
  tabs in the detail, no owner avatars, no link count column.
- **C2 custom types:** no fields at all (records have name/summary/notes only);
  types can be added only through the API; no icon/colour choice; no field kinds;
  no link-kind registry (kinds are a fixed CHECK list); no safe-change rules; MCP
  has no `list_types`.
- **C3 new record:** a small modal with five fields. No relationships, links,
  people, tags or custom fields at creation; no draft autosave; no duplicate
  warning while typing; no "create and add another"; no undo.
- **C4 CRUD:** see matrix — no Archived page, permanent delete hard to reach and
  without typed confirmation, no bulk actions, resources/edges cannot be deleted
  permanently from the UI.
- **C5 Guide:** none.
- **D1 Outline:** none. **D2:** 4-second polling, no presence. **D3:** no flag/review.
  **D4:** no templates. **D5:** completeness only per course on Data quality.
  **D6:** no saved views. **D7:** no real data available (no backups/). **D8:** the
  demo server is excluded only by convention; no test proved it.

### Design critique (honest)

The app is functional and calm but reads as an internal prototype, not a tool a
curriculum team would live in:

1. **Identity**: purple accent and a gradient logo mark — generic, and against the brief.
2. **Density**: tables use 2-line rows with summaries; at 1440 only ~12 rows fit.
   Filters take two rows. The dashboard spends the first screen on 12 count cards.
3. **Hierarchy**: page titles are 28px, section headings compete with content;
   everything is the same weight of grey.
4. **Detail panel**: one long scroll mixing facts, tags, relationships, resources
   and history; no breadcrumb, so "where does this live" needs a click.
5. **Navigation**: text-only sidebar, no counts, no grouping; "Corpus explorer"
   link sits next to the user identity.
6. **Graph**: good once loaded; no legend shapes, no minimap.
7. **Forms**: native selects everywhere; the new-record dialog cannot express a
   real record (no fields, no links, no relationships).
8. **Feedback**: toasts and conflict dialog are solid; empty states are fine but
   centred in dashed boxes.
9. At 1024px nothing scrolls horizontally, but the overlay panel hides the list.

---

## After — 2026-11-02 (run 2, branch `auto/knowledge-platform-20261102`)

Screens: `docs/redesign/after/<width>-<screen>.png` (1440/1280/1024, plus dark
mode at 1440 in the HANDOFF), Guide screenshots in `public/kb/guide/`. Every
screen was clicked through in Chrome (scripted with Playwright against the demo
server and the test server) and checked against the banned list in
docs/DESIGN_SYSTEM.md; no screen scrolls horizontally at 1024px (tested).

### Screens (after)

| Screen | Route | Notes |
|---|---|---|
| Dashboard | `#/` | headline numbers, records by type, completeness by course, needs attention, activity sentences |
| All records / Programs / Courses | `#/records` `#/programs` `#/courses` | one-row toolbar, filter chips, saved views as tabs, bulk bar, density, custom-field columns for a one-type list, CSV |
| Record detail | `?open=<id>` panel, `#/r/<id>` page | breadcrumb, editable title, properties incl. custom fields and completeness, tabs Overview · Links & resources · Relationships · History (diffs) |
| New record / Edit | side sheet | one save: placement (nested inline), relationships, links, people, tags, fields |
| Outline | `#/outline` | tree, drag reorder, quick-add, completeness, copy as text |
| Graph | `#/graph[/id]` | shapes by type, legend and filters, minimap, fit, connect mode |
| Resources | `#/resources` | service and kind filters, health |
| Data quality | `#/quality` | no owner, missing required, broken links, flagged, orphans, rule misfits, duplicates, completeness |
| Approvals | `#/approvals` | proposals (creates, archives, type changes) and Reviews (flags) |
| Archived | `#/archived` | records, links, relationships; restore; typed permanent delete |
| Settings | `#/settings` | record types (fields, placement, live preview, change type), relationship types, link kinds, members, API tokens, templates |
| Guide | `#/guide` | `public/kb/guide.md` |

### CRUD matrix (after)

W = WORKS (verified by a browser or API test named in docs/TEST_RESULTS.md),
N/A = not meaningful for that entity (reason given).

| Entity | Create | View | Edit | Archive | Restore | Perm. delete | Duplicate | Bulk edit | Import | Export |
|---|---|---|---|---|---|---|---|---|---|---|
| Record (any type, incl. custom) | W (one-step sheet; contributors propose) | W | W (inline + sheet) | W (impact first) | W | W (Archived, admin, typed) | W (editor) | W (owner, tags, status, placement) + bulk archive | W (Sheets CLI, custom fields) | W (CSV with custom fields) |
| Relationship | W (form, Connect, graph) | W | W (note via API; type is fixed: archive and re-create) | W (× with undo) | W (undo, Archived) | W (Archived, admin) | N/A (a pair can hold a type once) | N/A | W (Sheets links) | N/A (exported with the graph neighbourhood API) |
| Link (resource) | W (form, Add link, library) | W | W | W | W | W (Archived, admin) | W ("Duplicate" opens a prefilled New link; URLs are unique) | N/A | W | N/A |
| Attachment (link on a record) | W | W | W (purpose) | W (× with undo) | W (undo re-attaches) | N/A (archived with its record or link) | N/A | N/A | W | N/A |
| Record type | W (admin; editors propose) | W | W (safe-change rules) | W (blocked while in use; core never) | W | N/A (archive only; types are audited configuration) | W | N/A | N/A | via `GET /types` / MCP `list_types` |
| Relationship type | W | W | W (narrowing reported) | W (custom, unused) | N/A | N/A | N/A | N/A | N/A | via `GET /types` |
| Link kind | W | W | W | W (custom; built-ins editable, not archivable) | N/A | N/A | N/A | N/A | N/A | via `GET /types` |
| Flag | W | W | N/A | resolve / dismiss | N/A | N/A | N/A | N/A | N/A | N/A |
| Template | W | W | N/A | W | N/A | N/A | N/A | N/A | N/A | N/A |
| Saved view | W | W | W (update, share) | N/A | N/A | W (owner) | N/A | N/A | N/A | N/A |
| Member role / API token | W | W | W | W (revoke) | N/A | N/A | N/A | N/A | N/A | N/A |

### Gaps that remain (honest)

- D7 real-data rehearsal: BLOCKED (no `backups/`; PROGRESS D16).
- Relationship type of an existing relationship cannot be changed in place
  (archive and re-create), unchanged from run 1.
- Sheets import cannot fill person or record-reference custom fields from cells.
- Realtime and presence are off in production until the owner sets
  `KB_REALTIME_ORIGIN` (docs/DEPLOYMENT.md); polling is the fallback.
- Live Sheets import and a Vercel preview remain untested (no credentials).

---

## Run 3 — 2026-11-02 (polish, graph editing, custom relationships, activity)

Screens: `docs/redesign/run3/` (every screen at 1536 and 2560px; key screens at
1280, 1920 and 3840px; 1536 and 3840 at 2x). Swept automatically with
`scripts/kb_screens.py` (horizontal scroll, elements past the right edge,
clipped text without a tooltip, overlapping controls, script errors) and by
eye.

### Screens added or changed

| Screen | Route | What changed |
|---|---|---|
| Every screen | | one page template (`pageHead`): title, count, context, actions right; three widths (full, contained, reading); fluid scale above 2560px |
| Dashboard | `#/` | 12-column grid: six equal tiles, two equal columns; one attention number everywhere |
| All records | `#/records` | View popover (density switch, column checkboxes, drag/arrow reorder), resizable columns, full text on hover, two-line descriptions |
| Graph | `#/graph/<id>` | an editing surface: create, connect by dragging a handle, rename, archive + Undo, move with saved layouts, saved graph views, filters, search, keyboard, live sync, presence, clustering when zoomed far out |
| Activity | `#/activity` | new: every change with who, what, which, when and field diffs; filters, search, CSV; editors and admins |
| Record History tab | panel | same entries as Activity |
| Approvals | `#/approvals` | relationship types to review: Confirm, Rename…, Merge into…, Reject |
| Settings → Relationship types | `#/settings?tab=relationships` | review badge, Merge…, Archive (shows what uses it, offers merge) |
| Settings → Tags | `#/settings?tab=tags` | new: rename, merge, archive with Undo |
| Settings → Members | | Remove (audited; regrant any time) |
| Guide | `#/guide` | content and contents centred as one unit; screenshots cropped, click to enlarge; three new sections |
| Sidebar | | demo badge in its own slot; Activity (editors, admins); Back to NP Autopilot (admins only) |

### CRUD matrix (run 3)

W = WORKS (each verified by a test named in docs/TEST_RESULTS.md, run 3).
N/A says why the operation does not apply.

| Entity | Create | View | Edit | Archive | Restore | Perm. delete | Duplicate | Bulk edit | Import | Export |
|---|---|---|---|---|---|---|---|---|---|---|
| Record (any type) | W (form, graph, palette; contributors propose) | W | W (form, inline, graph rename) | W (impact first; graph Delete) | W (Archived, Undo) | W (admin, typed name) | W | W | W (Sheets) | W (CSV) |
| Relationship | W (form, Connect, graph drag) | W | W (note; **type: Change type, one step**) | W (× / graph Delete, Undo) | W | W (admin) | N/A: a pair holds a type once | N/A: edited one at a time | W | W (Activity CSV; neighbourhood API) |
| Link (resource) | W | W | W | W | W | W (admin) | W | N/A | W | N/A: links export with their records |
| Attachment | W | W | W (purpose) | W | W | N/A: archived with its record or link | N/A | N/A | W | N/A |
| Record type | W (admin; editors propose) | W | W (safe changes) | W (blocked while in use: Change type of N records first) | W | N/A: types are audited configuration, archive only | W | N/A | N/A | W (`GET /types`) |
| Field | W (in the type editor) | W | W (convertible kinds) | W (hides, keeps data) | W | N/A: data is kept | N/A | N/A | W (Sheets `props:`) | W (CSV) |
| Relationship type | **W inline everywhere** (admin; editor unreviewed; contributor proposal) | W | W (+ review: confirm/rename) | W (shows uses; offers **Merge**) | N/A: merged types point at the kept one | N/A: archive only | N/A | N/A | N/A | W (`GET /types`) |
| Link kind | W | W | W | W (custom) | N/A | N/A | N/A | N/A | N/A | W |
| Tag | W (on a record) | W | **W (rename)** | **W (Undo restores it on its records)** | **W** | N/A: archive keeps history | N/A | **W (Merge)** | N/A | W (`GET /tags`) |
| Member / role | W (admin) | W | W | **W (Remove, audited)** | W (grant again) | N/A: memberships are audited, never deleted | N/A | N/A | N/A | N/A |
| API token | W | W | N/A: shown once, by design | W (revoke) | N/A: issue a new one | N/A | N/A | N/A | N/A | N/A |
| Saved view (table or graph) | W | W | W (update, share) | N/A | N/A | W (owner) | N/A | N/A | N/A | N/A |
| Graph layout | W (move) | W | W | N/A | N/A | W (Reset) | W (Save view copies it) | W (Auto-layout) | N/A | N/A |
| Template | W | W | **W (rename)** | W | **W (Undo)** | N/A | N/A | N/A | N/A | N/A |
| Flag | W | W | N/A | resolve / dismiss | N/A | N/A | N/A | N/A | N/A | N/A |
| Activity entry | automatic | W | **never** (append-only, enforced by a trigger) | never | never | never | N/A | N/A | N/A | W (CSV) |

### Dependency handling (B2)

Before anything is archived or deleted the app shows what depends on it and
offers the safe path:

- **Record** (panel, bulk, graph): relationships and links that go with it;
  records placed in it stay. Undo restores everything.
- **Link**: the records it is attached to.
- **Relationship type**: how many relationships use it; archiving is offered
  only when unused, otherwise **Merge into another type**.
- **Record type**: archiving is blocked while records use it; **Change type of
  N records** moves them first.
- **Tag**: how many records carry it; Undo puts it back on all of them; Merge
  moves them to another tag.
- **Member**: what removal means (they stay a viewer if they can sign in to the
  main site); last admin and yourself are refused.
- **Permanent delete**: admin only, typed-name confirmation, what goes with it
  listed, recorded in Activity.

### Gaps that remain (honest)

- D7 real-data rehearsal: still BLOCKED (no `backups/`).
- Sheets import cannot fill person or record-reference fields from cells.
- Graph positions are not in the live feed: another person's moves appear on
  your next load, not instantly (records and relationships do sync live).
