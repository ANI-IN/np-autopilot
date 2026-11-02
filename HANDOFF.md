# HANDOFF — knowledge platform, run 3 (polish, graph editing, custom relationships, activity), 2026-11-02

1. Branch `auto/knowledge-platform-20261102`, pushed; **nothing merged to main, nothing deployed**; everything ran locally.
2. All seven owner-reported bugs fixed, each with a browser test; a scripted sweep of every screen at 1536px finds no clipped, overflowing or overlapping element.
3. **Custom relationship types inline** from any relationship picker: admins create, editors create for immediate use (reviewed later), contributors propose; enforced in the database; near-duplicates ("Teaches", "taught by") refused; **Merge** tool.
4. **The Graph is an editor**: create (double-click / N), connect (drag a handle), rename (double-click), archive (Delete) with Undo, move with saved layouts, filters, search, keyboard, live sync and presence.
5. **Activity** (Maintain → Activity): every change with a named actor, field-by-field diffs, filters, search, CSV; the History tab uses the same entries. Append-only and role-scoped **in the database**.
6. **Back to NP Autopilot** link for admins only, from the role the server verifies.
7. One page template on every screen, a 12-column dashboard, and a fluid scale above 2560px (screens at 1280–3840px, 1x and 2x).
8. CRUD matrix complete (tags, members, templates, relationship type change added); dependencies shown before every archive.
9. 25 people for 2 minutes: **0 server errors, 0 duplicates, 0 orphans, every conflict a 409, audit rows = writes**. Graph: 60 fps at 500 records; WebGL keeps 2,000 at 45–60 fps.
10. One migration to add: **0029**. Regression vs `main`: FINAL_REGRESSION.

## Open the app now

The local Supabase stack and the demo server are **running**.

- URL: **http://localhost:8765/local-login**
- `demo-admin@interviewkickstart.com` / `ik-demo-local` (admin). Also
  `demo-editor@…` (editor) and `demo-contributor@…` (contributor), same
  password. Local Supabase only; production keeps Google sign-in.
- Reset the demo data: `.venv/Scripts/python eval/kb_demo_seed.py` (also clears
  activity history, so no test leftovers show).
- Stop everything: docs/DEMO.md, "Stop".

## 5-minute leadership demo

1. **Dashboard (30 s).** Six numbers, then what needs attention and recent
   activity, every entry with a name. The "Need attention" number matches the
   list and the sidebar.
2. **Graph editing (1.5 min).** Sidebar → Graph → *Data Structures &
   Algorithms*. Double-click empty space → Topic "Union-find" → **Create**: it
   appears where you clicked. Hover *Graphs and Dynamic Programming*, drag its
   connect handle onto the new topic → "This module covers a topic" →
   **Connect**. Double-click the topic and rename it. Select it, press
   **Delete**: it shows what goes with it; **Undo** brings it back.
3. **Custom relationship (1 min).** Open an instructor → Relationships →
   **Connect** → type "mentors" → **Create relationship "mentors"** ("mentored
   by" is suggested) → Create. Try "Taught by": it is refused and the existing
   *teaches* is offered. As demo-editor, create one: it is usable at once, and
   the admin sees it in **Approvals** with Confirm, Rename and Merge.
4. **Activity (1 min).** Maintain → Activity: who changed what, with before and
   after. Filter Action = Updated, then **Export CSV**. Open any record →
   History: the same entries.
5. **Collaboration (40 s).** Open the same graph as demo-editor in a private
   window: a record added in one window appears in the other; a stale rename
   gets "This record changed since you opened it".
6. **Guide (10 s).** Sidebar → Guide: centred, with screenshots you can click
   to enlarge; new sections on graph editing, relationships and Activity.

## Status of every item

| Item | Status | Evidence |
|---|---|---|
| A1 one attention count | VERIFIED | `workspace.attention_counts` is the only definition (exact counts, total = sum of what the list shows), used by the tile, the list, `/counts` (sidebar) and Data quality; test_kb_run3 `test_attention_tile_list_and_sidebar_agree`; e2e `test_a1_…` |
| A2 named actors, no fixture leftovers | VERIFIED | 0029: `system` default actor, `kb.actor_emails`; server-side `actor_label` (person, "AI assistant (for X)", "Sheets import", "System"); the Realtime test deletes its probe and every trace of it; seed and test reset truncate `kb.changes` too; e2e `test_a2_…`, run3 `test_every_activity_entry_names_its_actor` |
| A3 demo badge placement | VERIFIED | its own `#sidebar-slot` above the user menu; folds to "Demo"; e2e `test_a3_…` |
| A4 View popover | VERIFIED | `core.popover` (viewport-clamped, flips), labelled density radiogroup, column checkboxes with a 10px gap, drag + ↑↓ reorder, Reset; stray tabs scrollbar hidden; e2e `test_a4_…` |
| A5 full text, wrap, resizable | VERIFIED | tooltip on every truncated text (`el()`), 2-line description in comfortable density, drag-to-resize headers (remembered); e2e `test_a5_…` |
| A6 Guide layout and images | VERIFIED | 760 + 220px centred as one unit; screenshots retaken cropped (`scripts/kb_guide_shots.py`), click to enlarge; e2e `test_a6_…` |
| A7 relationship picker | VERIFIED | searchable `relCombobox`; sentences grouped "This module …" / "… this module", no arrows; side-by-side layout so nothing hides the record input; e2e `test_a7_…` |
| A sweep at 1536px | VERIFIED | `scripts/kb_screens.py` on all 15 screens: 0 problems after fixes (truncated text without tooltip, Activity filter indent, anonymous "link on a record" entries) |
| B1 template + 4K | VERIFIED | `pageHead` on every screen; layouts full / contained / reading; 12-column dashboard; clamp() scale above 2560px; screenshots `docs/redesign/run3/` (1280, 1536, 1920, 2560, 3840; 1x and 2x); no horizontal scroll at 1024 (e2e, Activity added) |
| B2 inline relationship types | VERIFIED | admin / editor (unreviewed + Approvals) / contributor (proposal), policies in 0029; e2e for all three roles |
| B2 duplicate protection | VERIFIED | `kb.rel_stem` trigger + service pre-check with the existing type offered; 5 spellings tested in SQL and API; e2e |
| B2 merge tool | VERIFIED | preview count, moves relationships (duplicates archived), copies allowed pairs, audited; API + e2e |
| B2 CRUD completeness | VERIFIED | docs/INVENTORY.md "CRUD matrix (run 3)": every cell W or N/A with a reason; new: tags rename/merge/archive/restore, member removal, template rename/restore, relationship change of type |
| B2 dependency handling | VERIFIED | record, link, relationship type (offers merge), record type (change type first), tag (Undo restores), member; permanent delete admin-only, typed, audited |
| B3 graph editing | VERIFIED | create, connect, invalid reason + snap back, rename, archive + Undo, move + saved positions (layout only), saved graph views, auto-layout/reset, filters (type, relationship, owner, course/program), search, expand/collapse, legend, keyboard; e2e: 4 new graph tests + 2 existing |
| B3 sync + presence | VERIFIED (presence: Realtime only) | row-level live sync (e2e two people); presence rings use the Realtime presence channel, which runs in the local demo and in production only after owner step 5 |
| B3 scale | VERIFIED | measurements below; WebGL renderer above 800 records, simplified drawing (labels hidden, then one bubble per type) |
| B4 Activity | VERIFIED | page + History tab share `activityEntry`; filters, search, cursor, CSV; DB: append-only trigger, admin/editor-scope policy, `kb.record_history`; run3 + e2e |
| B5 admin-only link | VERIFIED | `/me.admin_links` only for a verified admin; sidebar + user menu; run3 (4 roles) + e2e (4 roles) |
| C EXPLAIN + indexes + no N+1 | VERIFIED | `scripts/kb_explain.py`; N+1 in course completeness removed (~1,000 → 3 queries); activity indexes |
| C caching, debounce, lazy load | VERIFIED | dashboard / counts / types cached per caller until the next change; search debounced (palette 120ms, tables 250ms, Activity 300ms); graph library and Guide images load only when needed |
| C 25-person concurrency | VERIFIED | `scripts/kb_load.py`, numbers below |
| D7 real-data rehearsal (run 2) | **BLOCKED** | still no `backups/`; place `backups/ik_workbook.xlsx` and/or `backups/prod_data.sql` |

Nothing was cut.

## Measured performance

25 people, 2 minutes (`scripts/kb_load.py`): 19,754 requests (164/s), 0 5xx.
Conflicts: 1,455 saves refused with 409, 318 saved; relationship race: the 9
possible created, 1,186 refused; audit rows equal successful writes for every
kind. p50 / p95 under that load: list 94 / 135 ms, search 84 / 120 ms,
neighbourhood 118 / 160 ms, dashboard 331 / 414 ms, Activity 75 / 137 ms.

Graph (headless Chrome, software rendering; a real GPU does better):

GRAPH_TABLE

Query plans at 5,000 records / 15,000 relationships, database time per
request: list 9–21 ms, search 15–22 ms, neighbourhood 13–20 ms, History 1–2 ms,
dashboard 180–360 ms uncached (cached until the next change), editor Activity
155 ms (the slowest uncached read; grows with the log). Full tables in
docs/TEST_RESULTS.md.

## Final verification

FINAL_VERIFY

## New migration to add to the dev → production list

Run 1 added 0022–0026, run 2 0027–0028. Run 3 adds:

- **0029_kb_activity_relationships**: `system` default actor and
  `kb.actor_emails`; the audit log made append-only (trigger) and readable by
  admins (all) and editors (own + scope) only, with `kb.record_history` for
  everyone's History tab; `kb.changes`, the content-free live feed (Realtime
  now publishes it instead of `kb.audit_log`); relationship-type review
  (`review_status`, `merged_into`, editor-insert policies, the near-duplicate
  trigger); `kb.graph_positions`; activity indexes.

Additive and reversible; the down refuses while unreviewed or merged
relationship types or saved layouts exist. Tested on a fresh local database
(`verify_all.sh --reset-db`: every migration from 0001, KB down to 0021, up
again) and up → down → up on the demo database.

## Decisions to review (PROGRESS.md D25–D32)

- **D25 viewers and contributors no longer read the activity log**, only a
  record's History tab (brief B4). Their dashboard shows no Recent activity.
  Live updates moved to `kb.changes` so they keep working for everyone.
- **D26** a change with no person and no declared actor is "System".
- **D28 editor scope** for Activity = their own changes + records they own or
  co-own and everything placed inside them + links they own.
- **D29 near-duplicate rule** for relationship names (case, spacing,
  punctuation, plurals, -ed/-ing/-es), applied to names and inverses.
- **D32 WebGL above 800 records** on the graph (Cytoscape's own WebGL mode),
  from the measurements; canvas below.
- **B5 access to the original site**: the link is admin-only, but `/` itself is
  unchanged: anyone with an Interview Kickstart Google account who passes its
  own sign-in can still open it. Decide whether that should change; nothing
  was changed.
- **Clicking a relationship on the graph** opens a small inspector beside it
  (the sentence, its note, Open, Remove) rather than the side panel: a
  relationship has no panel of its own. Clicking a record opens the panel.
- The graph's saved positions are shared (the shared layout, or a saved view
  anyone can open if shared); moving records never changes them.

## ACTION REQUIRED FROM OWNER

1. **Review the PR** `auto/knowledge-platform-20261102` → `main`. Nothing was merged.
2. **Apply migrations 0022–0029 to the dev Supabase project**, backup first:
   ```bash
   export SUPABASE_DB_URL_SESSION=<dev session pooler URL>
   mkdir -p backups && pg_dump "$SUPABASE_DB_URL_SESSION" --schema=public --schema=kb > backups/pre-kb-$(date +%F).sql
   python pipeline/migrate.py status && python pipeline/migrate.py up
   ```
   Then production the same way after a dev smoke test. Rollback:
   `python pipeline/migrate.py down --to 0021`.
3. **Bootstrap admins**: each signs in once at `/`, then
   `ADMIN_EMAILS=a@interviewkickstart.com,b@… python pipeline/kb_admins.py`.
4. **Vercel preview** of the branch pointed at the dev database; open `/kb/`.
5. **Optional live updates and presence**: run
   `KB_REALTIME_ORIGIN=https://<ref>.supabase.co python scripts/kb_csp_origin.py`,
   commit the vercel.json change, and set the same `KB_REALTIME_ORIGIN` in the
   Vercel project (docs/DEPLOYMENT.md). Without it the app polls every 4 s and
   graph presence rings do not show.
6. **Decide who may open the original site `/`** (see Decisions; unchanged).
7. **Sheets import**: share the workbook read-only with the service account;
   dry run `KB_SHEETS_ID=<id> NP_DRIVE_SA_KEY=<path> python pipeline/kb_import_sheets.py --as you@… --report /tmp/dry.json`.
8. **D7**: provide `backups/ik_workbook.xlsx` and/or `backups/prod_data.sql`
   (kept local, gitignored) for the real-data rehearsal.
9. **Brand colour**: if IK has an official accent, replace `--accent` in `public/kb/kb.css`.

## How to run

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt
npx -y supabase@2.118.0 start --workdir db/local
python pipeline/migrate.py up                # through 0029
python eval/kb_demo_seed.py                  # demo users + fictional data
python eval/kb_demo_server.py 8765           # http://localhost:8765/local-login
bash scripts/verify_all.sh [--fresh-clone] [--reset-db] [--perf] [--load]
python scripts/kb_screens.py --widths 1536   # layout sweep of every screen (demo server running)
python scripts/kb_graph_perf.py              # graph load time and frame rate at 500 / 2,000 / 5,000
python scripts/kb_explain.py                 # query plans at 5,000 / 15,000
```
Run 2's handoff is in git history (commit 035e123); run 1's before it (597b0e1).
