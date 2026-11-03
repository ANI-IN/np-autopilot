# HANDOFF — run 5: parity with NP Autopilot, owners, legacy, scheduled sync, dev database (2026-11-03)

Branch `auto/knowledge-platform-20261102`. Nothing deployed, nothing on `main`,
production never contacted. The local real-data copy (:8766) holds the new
import; the fictional demo (:8765) is unchanged. Decisions D39-D47 and the
timeline are in PROGRESS.md ("Run 5 log").

## 1. Parity with NP Autopilot: zero unexplained differences

`docs/PARITY_REPORT.md` (re-run: `python eval/kb_parity.py`). NP's side is
read from NP Autopilot itself (its own `model()` and `currentInstructors()`,
evaluated in the browser on :8766); the import now uses the same rules.

| | NP Autopilot | KB |
|---|---|---|
| Domains current / legacy | 4 / 42 | 4 / 42 (same ids) |
| Modules current / legacy | 20 / 904 | 20 / 904 (same ids) |
| Instructors current / all | 25 / 1,911 | 25 / 1,911 (same ids) |
| Programmes (older sheets) | 42 | 42 |
| Roles P / B1 / B2 / B3 | 23 / 20 / 11 / 3 | 23 / 20 / 11 / 3 (same 57 instructor-module-role triples) |
| Sessions, decks, weeks of 10 current modules | | identical, module by module |
| Topics | 2,770 | 2,733: 37 rejected by the import's shape rules (explained; ids in the run report) |

- The brief asked for 5 current domains side by side: NP Autopilot has **4**;
  all 4 are in the report.
- Name merges are undone. There is one record per source row; a generic name
  sits under the record it belongs to, and 5 remaining same-name pairs are
  kept apart with "(2)".
- Legacy is hidden by default (lists, counts, dashboard, Data quality) and can
  be filtered: All records → Filter → "Legacy only" / "Current and legacy".

## 2. Owners from roles

- **Current modules:** all 20 have the mastersheet primary (P) as owner, and
  B1-B3 in order as backups (48 backup slots across the KB).
- **Domains:** `owned_by` maps to the owner and `supported_by` to the backups.
  The 4 current domains have no owner in NP's data, so they have none here
  either. 6 of the 7 legacy domains kept live have one.
- **Edits and display:** shown on the record (Owner by role: P, then B1, B2, ...).
  Editors change them there; only instructor and team-member records are
  accepted.
- **Sign-in accounts:** an admin links a person record to a sign-in by e-mail
  (record panel → "Sign-in account"). It resolves at once, or on that
  person's first sign-in; from then on that person is the account owner /
  co-owner of everything their record owns by role.
- **0 links today.** The data has no e-mail addresses, because contact columns
  are never imported.
- **"No owner" on Data quality** now counts only current records with neither
  kind of owner: **3,067**, made up of 2,733 topics, 134 sessions, 92 processes,
  43 team members, 25 instructors, 20 weeks, 16 themes and 4 domains. NP's
  data has no owners for those.

## 3. Legacy archive (reversible)

Archived (`kb.legacy_archive`): **874 records**, made up of 35 legacy domains,
166 legacy modules and 673 legacy instructors. Their relationships and links
are archived with them.

Not archived, and reported by id in PARITY_REPORT:
- **7 legacy domains**, because 23 current-instructor expertise links point at
  them (D44).
- **17 legacy modules / instructors** that are connected to a current item.
- **1,932** legacy modules / instructors with no domain at all (NP's
  "unlinked"). These are left live and stay tagged legacy.

```
# restore everything the legacy step archived (one command; tested twice: counts back exactly)
SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy.py restore
# re-apply (also re-applied by every sync once adopted)
SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy.py archive
```

**Permanent delete: prepared, NOT run. It needs the owner's go-ahead.** It
removes only what the legacy step archived and is still archived; their
relationships and links go with them (cascade), and the audit log keeps every
row. It cannot be restored afterwards except from a backup. In psql, as the
owner, after a backup:

```sql
begin;
select count(*) from kb.nodes n join kb.legacy_archive la on la.node_id = n.id where n.archived_at is not null;  -- expect 874
delete from kb.nodes n using kb.legacy_archive la where n.id = la.node_id and n.archived_at is not null;
commit;
```

## 4. The sync: how it works, how to switch it off

`web/lib/kb/sync.py` is one engine for the first import (CLI) and every
scheduled run. docs/DEPLOYMENT.md "Scheduled sync" has the full design.

**Schedule.**
- The database (pg_cron + pg_net, migration 0031) calls
  `POST /api/cron/kb-sync` hourly; the interval is any cron expression.
- The call carries a Bearer secret, read from Vault at fire time.
- Vercel Cron was not used: it fires on Production only and allows one run a
  day on Hobby.

**Each run.**
- The function runs one batch within `KB_SYNC_BUDGET_SECONDS` (10 s, under
  the 15 s function cap), and the next tick continues.
- It writes only units whose source changed (checksums in `kb.sync_map`); an
  unchanged re-run writes nothing.
- One run at a time (DB lock).
- A record edited in the KB is never overwritten: it becomes a **conflict** on
  Data quality and on the record.
- A row gone from the source is flagged **"removed at source"**, never
  deleted.
- KB-created records are never touched, and the legacy rules apply on every run.
- In Activity the actor is **"Sync"**.

**Admins.** Settings → Sync shows the run log and has **Sync now**. A banner
appears while the last run failed.

**Switch off.**
- `KB_SYNC_ENABLED=false` (Vercel variable) stops everything.
- `select kb.sync_schedule_remove();` stops the calls.

**Verified locally.**
- 24 tests in tests/test_kb_sync.py, one per rule.
- On :8766 through "Sync now" (eval/kb_sync_proof.py): change, add, remove,
  and a conflict with an app edit, then undo: PASS.
- The cron route with and without the secret: 401 / 200.
- The schedule install/remove in the local stack's pg_cron.
- Not yet verified: the container → deployment HTTP leg. It runs on dev in
  the morning.

**New views:**
- **Who teaches what:** instructors × modules and sessions with P/B1-B3
  badges; filters for domain, role, name and legacy; CSV export.
- **Programme timeline:** programmes by week, with sessions and slide decks.

eval/kb_run5_ui_check.py: PASS, 0 page errors.

## 5. Dev database: ready

Full table in docs/DEV_DEPLOY.md, "Dev status".

- **Checks:** the ref differs from production. Backed up to `backups/`.
- **Migrations:** 0001-0031 applied. Run 5's two rolled back and re-applied;
  while the database was still empty, the whole chain was also rolled back and
  re-applied.
- **Data:** the old tables were loaded from `backups/prod_data.sql`
  (projection tables only, no user tables). Then the import, the legacy step
  and one sync, as the operator (no admin exists yet).
- **Result:** every count and the parity numbers equal :8766, and RLS is on
  for all 25 kb tables.
- **Admin:** a dry run with `ADMIN_EMAILS=<git e-mail>` reports "NO PROFILE". Dev
  has no users, and the git e-mail is not an IK address, so this is a morning
  step.
- **Measure in region:** an unchanged sync took 28.5 s from this laptop over a
  ~175 ms link (1.1 s locally). Check it on Vercel against the 15 s cap
  (DEV_DEPLOY.md, "Dev status").

## 6. Morning: deploy the dev preview (docs/DEV_DEPLOY.md)

1. `vercel login`, `vercel link`.
2. Add the Preview variables for branch `auto/knowledge-platform-20261102`
   only (DEV_DEPLOY.md step 2; never Production). New: `KB_SYNC_SECRET`,
   `KB_SYNC_ENABLED=true`, `KB_SYNC_BUDGET_SECONDS=10`.
3. Run `bash scripts/deploy_dev_preview.sh --check`, then
   `bash scripts/deploy_dev_preview.sh`. It deploys a preview and runs the
   smoke tests.
4. Set up Google sign-in for the branch URL (step 5): the Google client's
   JavaScript origin, Supabase dev → Google provider, the before-user-created
   hook, and URL configuration.
5. Sign in once at `<branch URL>/kb/`. Then run:
   `SUPABASE_DB_URL_SESSION="$DEV_SUPABASE_DB_URL" ADMIN_EMAILS=<you>@interviewkickstart.com python pipeline/kb_admins.py`
6. Set up the schedule (step 6): two Vault secrets (sync, plus Vercel's
   protection bypass), then
   `select kb.sync_schedule_install('https://<branch host>/api/cron/kb-sync');`
   Check that the next run appears in Settings → Sync as "Schedule", and how
   long it took.
7. Link two or three person records to sign-ins and check that ownership
   follows.

## 7. Production go-live checklist (in order; nothing done yet)

1. Read PARITY_REPORT.md and confirm D44: 7 legacy domains stay live because
   current instructors point at them.
2. Merge the branch through review. Production is at migration 0021.
3. Back up production (read-only `pg_dump`, as in Step 0) into `backups/`.
4. Run `pipeline/migrate.py status`, then `up` (0022-0031), on the production
   session pooler during a quiet hour. Each migration has a rollback.
5. Run the first import: `pipeline/kb_import_projection.py apply --operator`
   (or `--as <admin>` once one exists). It took 245 s over a far pooler;
   expect less in region.
6. Run `pipeline/kb_legacy.py archive`. `restore` is the undo.
7. Admins sign in, then run `ADMIN_EMAILS=... pipeline/kb_admins.py`.
8. Vercel **Production** variables: add `KB_SYNC_SECRET` (new, 32+ chars),
   `KB_SYNC_ENABLED=true` and `KB_SYNC_BUDGET_SECONDS=10`, next to the existing
   ones.
9. Deploy production (`vercel --prod` from main), then the smoke tests of
   DEV_DEPLOY step 4.
10. In production: `vault.create_secret(<KB_SYNC_SECRET>, 'kb_sync_secret')`,
    then `kb.sync_schedule_install('https://<prod host>/api/cron/kb-sync')`.
    No bypass secret is needed. Watch the first scheduled run and its
    duration.
11. Link person records to sign-ins (owners by role become account owners).
12. Watch Data quality for sync conflicts and rows removed at source in the
    first week.
13. Later, with the owner's confirmation: run the prepared permanent delete of
    the 874 archived legacy records (§3), after a fresh backup.

---

# HANDOFF — real production data, local rehearsal (2026-11-03)

A copy of production's data now runs locally, migrated into the knowledge
base, next to the fictional demo. Production was read once, by two read-only
`pg_dump`s at 00:48; the read-only URL is deleted from `.env`, and nothing
connected to production after that. The data stays in `backups/`
(gitignored, never committed, never deployed) and in the local database
`kb_realdata`.

## Open it

| | URL | Sign in |
|---|---|---|
| **Real data (copy of production)** | **http://localhost:8766/local-login** | `realdata-admin@interviewkickstart.com` / `ik-realdata-local` (KB admin; exists only in the local copy) |
| Fictional demo (unchanged) | http://localhost:8765/local-login | `demo-admin@interviewkickstart.com` / `ik-demo-local` |

How the two are kept apart: separate database, server, port and sign-in
(docs/DEMO.md, "The real-data copy"). Rebuild: `python eval/kb_realdata_db.py
rebuild`, then the importer's `preview` and `apply`.

## Headline numbers

- **Copied:** 18 tables; every count equals production's (node_sources 39,414;
  edges 12,189; nodes 8,496; node_layout 3,707; files 1,524; people 20;
  profiles 7; the rest in the report).
- **Schema drift vs migrations 0001–0021:** none. 126 columns, 59 constraints,
  36 indexes, 8 functions, 9 triggers, 17 policies and RLS on all 18 tables are
  identical, and the migration checksums match.
- **KB migrations 0022–0029** applied on the real data in about 1 s, rolled
  back to 0021 and re-applied cleanly; the existing tables were untouched.
- **Imported into the KB:**
  - records: **5,741**;
  - relationships: **6,938**;
  - links: **1,827**;
  - links on records: **10,434**;
  - shared-layout positions: 3,707.

  Preview equals apply, and a re-run creates **0**. An edit made in the app
  survives a re-run.
- **Merged:** 220 same-name topics, 983 artifacts sharing a Drive URL, and 4,185
  repeated evidence rows for the same relationship.
- **Rejected:** 37 rows, with 53 relationships to them dropped.
- **43 baseline test failures:** **30 now pass** after the root-cause fix (3 of
  them also failed in the run before, so treat those as unstable). 13 remain,
  all environment issues (Windows line endings, executable bits, ignore rules,
  deploy-artifact checks), none of them KB tests. The final full suite: 1,240
  passed, 13 failed, 52 skipped, **0 new failures** vs the main baseline.
- **Browser check at 8766** (5 largest programs):
  - placement, All records and record panel match the source exactly;
  - the graph draws up to 300 records at 60 fps;
  - the dashboard equals the import report.

## Top 10 data problems to look at

1. **No KB admin exists after the migration.** Every one of production's 7
   profiles reads the KB as a viewer; the 2 site admins are not KB admins
   until `pipeline/kb_admins.py` runs.
2. **No record has an owner** (5,741). The source names owners as people,
   never as sign-in accounts, so ownership came across as owned by, supported
   by and delivered by relationships. 7 domains have none.
3. **892 instructors are connected to nothing:** in rosters, but teaching no
   module.
4. **721 of 924 modules and all 46 domains sit in no program.**
5. **508 links are marked unavailable in production; 441 links hang on no
   record;** 24 citations name a file without a Drive URL.
6. **No process has a confirmed owner** (92); 39 carry an unconfirmed
   suggestion, kept as a field.
7. **36 person names were extracted as topics** (the pipeline flagged them
   `not_a_topic`) and were rejected. One more topic name contains an e-mail
   address or URL: `con_7957d10a9373c9e3`.
8. **220 topics were merged by name.** Spot-check that no two different topics
   merged.
9. **Two domains share a name** (`dom_8eca42bd0bd17ab8`, `dom_fadfd977f7d5b5d7`;
   one is shown "(2)"). Two module pairs and 5 groups of weeks were kept apart
   by scope.
10. **123 records are marked for review:** 94 instructors and 26 boilerplate
    topics flagged by the pipeline, plus the same-name cases.

Full report: docs/MIGRATION_REPORT.md. Mapping: docs/MIGRATION_MAPPING.md.

## Schema drift found

**None** in production's `public` schema. Not checkable from this dump:
- privileges (`--no-privileges`);
- 0015's trigger on `auth.users`;
- the Realtime publication.

To check them in the Supabase SQL editor:

```sql
select table_name, grantee, string_agg(privilege_type, ',') from information_schema.table_privileges
 where table_schema = 'public' and grantee in ('anon','authenticated','service_role') group by 1,2 order by 1,2;
select tgname from pg_trigger where tgrelid = 'auth.users'::regclass and not tgisinternal;
select tablename from pg_publication_tables where pubname = 'supabase_realtime';
```

## What the 43-failure fix changed

`pipeline/project_graph.py` registered cited files and the domain Drive
folders only from the crawl cache (`.drive-cache/`, not in the repository).
On a fresh checkout every content citation therefore lost its file, and the
correct `corpus_names_a_file` constraint refused it. Now:
- `_file_rows(graph)` registers every path the graph cites, with its path only
  (no invented hash or Drive id);
- folders are registered regardless of the cache;
- a corpus citation without a registered file is a loud error.

The constraint is unchanged, and when the cache is present the projection is
byte-identical. A fresh projection now reproduces production's counts exactly.

## What will need to happen differently on dev and production

- **No dump or restore:** the data is already in place. Back up, then apply
  0022–0029 through the session pooler (`pipeline/migrate.py up`), exactly as
  rehearsed here.
- **Grant KB admins in the same window** (`pipeline/kb_admins.py`); until then
  nobody can administer the KB.
- **Run the importer** with `SUPABASE_DB_URL_SESSION=<session pooler>`, first
  `preview --as <your e-mail>`, then `apply`. The admin must have signed in
  once. It's one transaction, about 30 s locally and longer through the
  pooler. Re-running is safe.
- **Realtime:** on a real project 0029 moves the publication from
  `kb.audit_log` to `kb.changes`; that step was skipped locally.
- **Not used on dev or production:** the local `auth` schema, the local admin
  and the HS256 sign-in on 8766 are constructions of the local copy only
  (`eval/`, never deployed).
- **Connection pooling:** web requests must use the transaction pooler (6543).
  `pipeline/lib/db.py` now refuses a `SUPABASE_DB_URL_TRANSACTION` that points
  at the session pooler or the direct host (docs/DEPLOYMENT.md, "Connection
  pooling"). Check the Vercel variable before deploying.

## Action required from owner

1. **Run `drop role kb_readonly;` in the Supabase SQL editor.** The copy is
   done, and the read-only login is no longer needed. Its URL has already
   been deleted from `.env`.
2. Review the branch. Nothing was merged to main or deployed.
3. Run the three SQL checks above, plus the dev and production steps
   (migrations, KB admins, import).
4. Decide on owners (problem 2) and the 892 unconnected instructors (problem 3)
   before the team starts editing.
5. `backups/` holds real internal data. Keep it on this machine; delete it when
   the rehearsal is no longer needed.

---

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
10. One migration to add: **0029**. Regression vs `main`: the same 43 pre-existing failures by name, **0 new**; `verify_all --fresh-clone --reset-db`: ALL PASS.

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

| Nodes | Renderer | Loaded | Load (ms) | FPS, labels (zoom 0.5-1.2) | FPS, no labels (0.2-0.45) | FPS, clustered (<0.16) | Switch to clusters (ms) |
|---|---|---|---|---|---|---|---|
| 500 | canvas | 501 | 545 | 53.8 | 59.7 | 60.0 | 134 |
| 500 | webgl | 501 | 658 | 54.0 | 59.9 | 60.3 | 130 |
| 2000 | canvas | 2001 | 1955 | 21.7 | 21.9 | 57.9 | 496 |
| 2000 | webgl | 2001 | 1493 | 45.3 | 50.1 | 60.1 | 383 |
| 5000 | canvas | 5001 | 4830 | 7.1 | 9.3 | 39.9 | 899 |
| 5000 | webgl | 5001 | 5179 | 13.6 | 21.5 | 59.8 | 1000 |

The page opens at most 300 records (expand loads more); WebGL is used above
800. Before the scale work 2,000 records ran at 10 fps and 5,000 at 0.6.

Query plans at 5,000 records / 15,000 relationships, database time per
request: list 9–21 ms, search 15–22 ms, neighbourhood 13–20 ms, History 1–2 ms,
dashboard 180–360 ms uncached (cached until the next change), editor Activity
155 ms (the slowest uncached read; grows with the log). Full tables in
docs/TEST_RESULTS.md.

## Final verification

`bash scripts/verify_all.sh --fresh-clone --reset-db`: **VERIFY: ALL PASS**.

- Fresh clone → clean install → byte-compile → ES modules parse: PASS.
- `supabase db reset` → migrations 0001–0029 → KB down to 0021 → up again: PASS (projection
  step fails as on `main`, pre-existing).
- Lint, plugin, secrets, RLS on every kb table, deploy guard: PASS.
- Full suite: **1203 passed, 22 failed, 21 errors, 53 skipped**; all 43 are the `main` baseline by
  name; **0 new**; every KB test passes. Realtime test after reseeding: 1 passed.
- Honest notes: the first final run failed on a typo in verify_all's own lint list (fixed, re-run
  from the start). The Realtime test's cleanup no longer deletes audit rows (the log is
  append-only; the reseed clears it).
- KB tests by file (run 3 additions): run3 API 23; browser E2E 71 (22 new, plus Activity in the 1024px and accessible-name sweeps).

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
