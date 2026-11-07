# Autonomous run B, 2026-11-07 (owner away ~2–3 hours)

**Production, its settings, `main` and Vercel settings were not touched.** Nothing was merged,
renamed or hard-deleted. Archiving happened only as approved in step 2, on DEV after a verified
backup. Nothing was written to the live graph from extraction.

**One incident to know about:** early in the run I loaded `.env` with the shell's `source`.
Two malformed lines made the shell print some values into my tool output. Nothing reached a
file, a commit or any service. From then on, variables were loaded only through Python
(`dotenv_values`), never printed. Rotating the production database password is a cautious
option; the decision is yours (§5).

## 1. What's done

**Commits** (branch `auto/knowledge-platform-20261102`, pushed):

- `c8b5e4f`: the code, tests and docs of this run.
- A follow-up commit: these deployment notes.

**DEV preview** redeployed to the same alias (`np-autopilot-kb-dev.vercel.app`, functions in
dub1), and the share link still works:
- smoke tests 7/7;
- the served CSP allows both of the map's inline scripts;
- the new modules are served.

Deploy note: `deploy_dev_preview.sh` must run in **Git Bash**. Started from Python, `bash` is
WSL's and has no `node`. The script's smoke tests also need `VERCEL_BYPASS` exported; without
it they see the login redirect (302).

### Step 1: Graph page (blocking)

**Root cause found in the client.** `api()` silently turned an unreadable 2xx reply into `{}`,
so `resp.nodes.forEach` threw. Reset then failed on the canvas that was never created.

**Likely trigger on Vercel:** the whole graph went out as one 1.6 MB reply, the largest in the
app. The data is identical on DEV and locally, and locally it loads, even with simulated latency.

**Fixes:**
- An unreadable or incomplete reply is now reported with its status and size.
- The whole graph loads in pages of 1,000 records.
- The toolbar says "did not load" instead of crashing.
- "Try again" is clickable; the canvas covered it before.
- "Save view" switches to the saved view; it stayed on the shared layout before.

**Tests:** 6 new browser tests (`tests/test_kb_graph_toolbar.py`) cover load, reset,
auto-layout, save view, connect, and two kinds of bad reply. The fix is also verified on the
real-data copy: 3 pages, auto-layout and reset.

**Not verified on DEV signed in:** I had no DEV token, and minting one was refused. Please open
`/kb/#/graph` on the preview. If anything still fails, the message now says exactly what
arrived.

### Step 2: Weeks, workflows and themes removed; navigation cleaned

**Data, on DEV and on the local real-data copy**, by `scripts/retire_legacy_sections.py`
(reversible, one transaction, fixed markers). The DEV backup
`dev_backup_20261107T084603Z.sql` (62.6 MB) was verified by restoring it into a scratch
database: 45/45 tables and 188,259/188,259 rows identical.

| | Before | After |
|---|---|---|
| Week / process / theme records live | 20 / 92 / 16 | 0 / 0 / 0 (archived) |
| Relationships touching them | 112 | 0 (archived with them) |
| Course→module links carrying the week number (`program: null`) | 0 | 20 |
| Process records with an owner suggestion | 39 | 0 (exported to `.measure/private/`, outside git) |
| Live records / relationships | 4,342 / 3,097 | 4,214 / 2,985 |

- **Revert was rehearsed** locally (apply → revert → apply), with exact counts each time.
- **The week records name no program;** they came from one sheet's schedule. So the number moved
  to the course→module link with the program left empty, for the KYP import to attribute.
- **The sync cannot bring them back.** It skips archived records, and
  `config/kb-projection-mapping.yaml` now lists `retired_types: [program_week, workflow, theme]`,
  which the sync never imports.
- **Sync preview after the change:** 0 created, 0 conflicts. The next real sync archives the
  108 source attachments of the retired records; undoing needs `revert` plus one sync.
- **Go-live:** this is step 6b in `docs/operations/GO_LIVE.md`. The script refuses the
  production project, so that gate is lifted only at go-live, with your approval.

**Code:**
- **Map:** the "Programme week" filter, `?week=` links (they open with no filter and the address
  is rewritten), the Programme timeline view, and the week, workflow and theme chips are gone.
  The map's admin button is now "Admin →" and opens the Admin area.
- **Workspace:** the Program timeline page and its API are gone; old addresses redirect to
  Programs.
- **Plugin:** the `workflow` command was removed; the descriptions and examples no longer
  mention weeks or workflows.
- **Guide:** updated for the new navigation.

**Legacy-section audit:** nothing else was clearly unused, so nothing else was removed.
Candidates for later, which wait for the KYP model:
- the map's "Who teaches what" uses older-sheet roles;
- "Live session" records (134) are tied to the old mastersheet;
- the root plugin's `commands/*.md` read the frozen `knowledge/graph.json`
  (see `docs/design/live-sources.md`).

### Visual direction (your decision, implemented)

**Built:** the Direction A shell, C's search-first Home, a search results page, an Admin area,
A's light and B's navy dark tokens, and a System → Light → Dark toggle. The details are in
`docs/design/phase1/DECISION.md`. The graph editor is admin-only, in the page and on the server
(layout writes return 403 to non-admins).

**Tests:** 13 new browser tests (`tests/test_kb_shell.py`) cover navigation by role, server
enforcement, the theme toggle, Home and Search, and AA contrast in both themes.

### Step 3: Live sources (audit and design)

`docs/design/live-sources.md`.
- **The app and API read no downloaded files at runtime.**
- **The pipeline upstream does:** every fact enters through local copies keyed by file path.
  Drive's modifiedTime lives only in local manifest files.
- **Design:** a `sources` table (ID, URL, modified time/version, owner domain only) plus
  `source_content` with provenance, re-crawled by ID. There's a 6-step migration order. Not
  built yet.

### Steps 4–5: Inventory and KYP analysis

Both are in §3 and §4.

### Step 6: End-to-end report

`docs/testing/E2E-REPORT.md` has one row per test. **Bugs found and fixed:** 11 (graph: 4;
script: 2; shell and UI: 5, i.e. the route race, focus ring, autofocus, radius tokens and missing icons). The one row **not verified** is the graph on
DEV signed in.

## 2. Test summary

All browser files ran one at a time with ≥ 2.5 GB free, and the graph file one test per
process. **No test hung.**

| Suite | Result |
|---|---|
| graph toolbar (new) | 6 passed |
| shell (new) | 13 passed |
| retire script (new) | 3 passed |
| e2e | 71 passed |
| UI | 36 passed |
| map switch | 15 passed |
| perf budget | 10 passed |
| Realtime gap / Realtime / propagation / console | 1 / 1 / 1 / 2 passed |
| graph (one test per process) | 11 passed |
| real-data UI check | 15/15 |
| `verify_all --skip-browser` (final) | **ALL PASS**: 1,338 passed, 13 = the known baseline, 50 skipped |

## 3. Sheets and Drive inventory (read-only)

The redacted summary is `docs/operations/sources-inventory-2026-11-07.md`. The full detail
stays local in `.measure/inventory/`.

- **Sheets:** 3 opened (the registry plus 2 linked), with 41 tabs and 2,940 data rows.
- **Links:** 64 links pointing at 47 targets: 39 folder, 10 doc, 10 slides, 5 sheet.
- **Drive:** 27 folders walked, with 2,890 sub-folders and 10,261 files (51.3 GB), modified
  between 2021-08-10 and 2026-11-07.
  - Two folders hold 47.9 GB.
  - The most common files are audio (wav, 4,004), Docs (738), docx (543), Slides (492) and
    PDF (420).
  - Video and ZIP files make up most of the size.
- **Access failures: 38, all recorded.** 20 sheet links are 404 or not shared with the service
  account, mostly docs and slides in one tracker sheet. 18 shortcut targets are missing.
- **Notes:**
  - `KB_SHEETS_ID` is empty in `.env`, so the registry ID was taken from the registry doc.
  - The **Sheets API is disabled** in the service account's Google project, so sheets were read
    through Drive's read-only export.
  - The tools are now in the repo: `eval/sources_inventory.py` and
    `eval/sources_inventory_report.py`.

## 4. KYP structure and proposed model

The redacted write-up is `docs/design/kyp-structure-and-model.md`. The full detail stays local
in `.measure/kyp/`, and the staging files are in `.measure/staging/`.

**What was read:** 182 pages across the 5 starting points.

**Structure.** The 2026 KYPs share a 21-section template; only Curriculum, Capstone, Live
projects, Assignments, Instructors and Schedule carry structure.
- The curriculum table runs week → module → agenda, and its section rows act as courses.
- Agenda bullets are topics.
- The short-course family builds programs from 24 shared "Module – X" pages, with the weeks on
  the program page. That is the "reusable content, schedule on the program link" pattern.
- The regional family wraps a separate course-outline page. In 12 cases that outline sits in an
  archived folder.

**Proposed mapping:**
- Program = a KYP page.
- Course = a section, or a shared module page; order and week range go on the Program–Course
  link.
- Module = a curriculum row; week label, order and floater go on the Program–Module placement.
- Topic = an agenda bullet.
- Concept = a tool or technology for now; real concepts aren't in the KYPs.
- Resource = a typed resource: project, assignment, capstone, video or link.
- Instructors stay at program level.
- Owners exist only as free-text notes and account IDs.

**What doesn't fit:**
- The same module title carries different content in different programs (11 titles in the
  pilot).
- Some programs are copy-paste duplicates.
- Courses are only implicit.
- Floater and bonus sessions have no week.
- Capstones are options to choose from, not a sequence.
- Career, placement and support sections have no home in the model.
- The regional family has 14 different table layouts.
- 42 pages have "TO BE FILLED" placeholders.
- No learning objectives or module-level SMEs appear anywhere.

**Pilot (Applied Agentic AI, local staging only):**
- 6 programs, 4 courses, 66 module variants (51 distinct titles), 337 topics (3 low-confidence),
  102 tool concepts and 205 resources.
- 96 module placements and 24 weekly-schedule rows.
- 1 do-not-use page and 45 attachments skipped and listed.
- Every item carries the page, version, heading and row it came from.

## 5. Decisions waiting for you (with my recommendation)

1. **Check the Graph page on the DEV preview** (signed in). *Recommendation:* if it still fails,
   send me the new error text. Or create a 7-day API token in Settings → API tokens and put it in
   `.env` as `DEV_PERF_TOKEN`, so I can test signed-in myself.
2. **Module identity across programs (KYP).** The same title carries different content.
   *Recommendation:* treat each as a module **variant** linked to a canonical module, with you or
   the NP team picking canonicals during the Phase 4 pilot review. This also unblocks the
   deferred topic-collision decisions.
3. **Copy-paste programs** (the "generic" program identical to another audience's; PM and TPM
   identical). *Recommendation:* import them as separate programs, flagged "duplicate of …" for
   the owner, never auto-merged.
4. **Courses.** *Recommendation:* create Course records from KYP section rows and shared module
   pages, named by the section title, reused across programs when the name matches.
5. **Concepts.** *Recommendation:* start with tools/technologies only. Derive real concepts in
   Phase 4 with model assistance, behind review.
6. **Owners and SMEs.** No structured data exists. *Recommendation:* a one-time owner sheet
   (module → NP owner, SMEs), filled by the NP team.
7. **Sheets API and `KB_SHEETS_ID`.** *Recommendation:* set `KB_SHEETS_ID` in `.env`. Enable the
   Sheets API on the service account's project (free) only if direct cell reads are needed;
   Drive export works today.
8. **The 20 unshared links** in the tracker sheet. *Recommendation:* share those docs with the
   service account (read-only), or mark them out of scope.
9. **Confluence token scope.** Search, user lookup and the new attachments API are refused.
   *Recommendation:* add read scopes for search and users if owner names are wanted from page
   metadata.
10. **`.env` exposure in my tool output** (incident above). *Recommendation:* rotate the
    production database password at a convenient time (low risk: the output stayed in this
    session).
11. **Lift the production gate for step 6b at go-live** (retire weeks, workflows and themes on
    production). *Recommendation:* yes, in the go-live window, after the backup.
12. Still open from run A: plan upgrades (deferred to the end), scheduled-run host, monitoring
    channel, first plugin, making the repo private.

## 6. Failed, skipped, or worth knowing

- **Graph on DEV, signed in: not verified** (see above).
- **Minting a DEV API token directly in the database was refused** by the permission layer. I
  did not work around it.
- **Vercel Hobby keeps runtime logs only about 1 hour,** so the owner's failing request was no
  longer in the logs.
- **The retire script's audit rows read "Sync (NP Autopilot) archived …"** in Activity: it runs
  with the sync's actor type. That's accurate about the mechanism, but you may prefer a
  dedicated "maintenance script" label later.
- **Programs shows "No programs yet" on real data:** all 42 current program records are
  legacy-flagged. Current programs come from the KYPs (decision 8 of the plan).
- **Not built (waits for the KYP model):** Programs and Courses pages, record-page sections
  (Concepts, schedules, Owners vs SMEs), and the map restyle.
