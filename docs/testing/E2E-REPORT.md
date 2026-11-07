# End-to-end test report: run C (2026-11-07)

Every feature of run C, tested end to end: the data was prepared, the real workflow run, and the API, the database and the UI checked, including error and permission cases. One row per test.

**Screenshots** are named in the *Screenshot* column. They are stored **locally only** under `testing/evidence/<feature>/` and are gitignored: the GitHub repository is **public** and real-data screenshots show real names. This report contains no real names or e-mail addresses.

**Data used**
- *Synthetic*: records created through the API in the local test database (reset around each test).
- *Local copy*: the local `kb_realdata` database, mirrored from DEV at the start of this run (from the restore-tested DEV backup), then put through exactly the same scripts as DEV. Served on :8766.
- *DEV preview*: the DEV project and the redeployed DEV preview, signed in with the owner's API token. The Map is checked on the local copy only: on the preview it needs a Google session.

Production was not touched. Destructive steps ran on the local copy first, then on DEV.

## Suites

| Suite | Result | Evidence |
|---|---|---|
| Non-browser suite (`verify_all.sh --skip-browser`) | 1,346 passed, 13 failed (the **same 13** as `main`'s baseline), 50 skipped: **0 new failures**. Static checks pass (ruff flagged 2 unused test variables after this run; fixed and re-checked) | `.measure/suiteC/verify_5.log` |
| Browser files, one at a time, at least 2.5 GB free, 10-minute HUNG watchdog | 11 files and 11 graph tests (one per process): **all pass**, none hung (`test_kb_e2e` 71, `test_kb_ui_run6` 36, `test_kb_map_switch` 15, `test_kb_shell` 13, `test_kb_perf_budget` 10, `test_kb_run_c_ui` 7, `test_kb_graph_toolbar` 6, `test_kb_console_run6` 2, realtime, realtime gap, propagation matrix, 11 graph tests) | `.measure/suiteC/browser/summary_final.txt` |
| Real-data checks, local copy (`eval/run_c_e2e.py`) | **40 / 40** | `testing/evidence/run_c_e2e_local.json` |
| Real-data checks, DEV preview | **39 / 39** | `testing/evidence/run_c_e2e_dev.json` |
| DEV smoke after redeploy | **7 / 7**, functions in dub1 | deploy output (session) |

## 1. Sources: registry sheet, Drive, KYPs

| ID | Feature | Scenario | Expected | Actual | Result | Screenshot | Issues | Fixes | Retest |
|---|---|---|---|---|---|---|---|---|---|
| SRC-01 | Sheets API | Read the registry through the Sheets API (not a Drive export): every tab, column and row, with cell hyperlinks, rich-text links and smart chips | All tabs read; links found | Registry and 2 linked sheets (41 tabs); 818 link occurrences | Pass | — | First crawl read only 2 of 3 sheets | A linked sheet already listed by a folder walk was not read; fixed | Re-crawl: 3 sheets, 818 links |
| SRC-02 | Sheets API vs export | Compare with the earlier Drive-export inventory | Report what the export missed | Every Google target the export found is found again (47); **754 web links the export never captured** (UpLevel 638, LinkedIn 97, others 19) | Pass | — | — | — | — |
| SRC-03 | Recursive Drive crawl | Follow every link: folders recursively (shared drives included), shortcuts to their targets | Every reachable item listed with live URL, id, version, modified time, size, provenance | 13,148 items (2,890 folders); not capped | Pass | — | — | — | — |
| SRC-04 | First-pass extraction | Docs, Slides, Sheets, PDF, Word, PowerPoint, Excel; audio and video counted only | Text cached locally (a cache, not the source of truth) | 2,699 read (2 with no text); 4,297 audio/video listed with sizes | Pass | — | — | — | — |
| SRC-05 | Failures recorded | Every inaccessible link recorded with link and reason | No silent skip | 151 failures: 96 download not permitted, 17 export not permitted, 20 not found or not shared, 18 shortcut targets missing | Pass | `testing/evidence/source-crawling/local-RD-SC-02-failures.png` | — | — | — |
| SRC-06 | Re-crawl by resource id | Second crawl compared with the first | Unchanged reused, changed re-read, removed marked | 13,140 unchanged, 8 changed (4 re-extracted, 2,695 reused), 0 removed | Pass | — | — | — | — |
| SRC-07 | KYP extraction | Fetch in-scope pages at their current version; parse the structure | Four domains' programs, courses, modules, topics, with provenance | 8 programs, 34 courses, 91 modules (38 variants), 356 topics, 25 instructor listings; 182 pages re-checked (0 changed since run B) | Pass | — | Three page shapes; India outlines use bold paragraphs and repeated course rows | Parser handles bold-paragraph modules, "Course: Module" titles, merges repeated module rows | 7 ambiguities listed, none guessed |
| SRC-08 | Do-not-use pages and attachments | Skip "[Do not Use]" pages and attachments, list them | Listed on the Sources page | 1 do-not-use page, 1,635 attachments listed; 122 pages deferred | Pass | `testing/evidence/source-crawling/UI-SC-01-sources-page.png` | — | — | — |
| SRC-09 | Source catalog in the database | Load into `kb.sources` by resource id; load again | Idempotent; admins only | 15,000 sources; second load: 15,000 unchanged; viewer and editor get 403 | Pass | `testing/evidence/source-crawling/UI-SC-01-sources-page.png` | — | — | — |
| SRC-10 | Folder links | Registry domain folders and `Module-N: <name>` folders attached to their domain and module | Exact matches only | 4 domain folders, 5 module folders (Backend) | Pass | — | — | — | — |

## 2. Model, owners and SMEs (synthetic: `tests/test_kb_run_c.py`, `tests/test_kb_run_c_ui.py`)

| ID | Feature | Scenario | Expected | Actual | Result | Screenshot | Issues | Fixes | Retest |
|---|---|---|---|---|---|---|---|---|---|
| API-01 | Owners | Instructor as owner; two team-member owners on a module; one on a program | Instructor refused (API and database); many-to-many works | As expected | Pass | — | Fresh databases lacked the team-member type and the owner relationship | 0039 creates both and marks them core | Pass |
| API-02 | SME roles | No role; backup rank 4; SME on a course; primary + backup 1 + backup 2; role change | Refused, refused, refused; ordered Primary, Backup 1, Backup 2; role change keeps provenance | As expected | Pass | — | — | Role change merges into the assignment's data | Pass |
| API-03 | Two primaries | Two primaries on one module | Kept and listed by Data quality | As expected | Pass | — | The mastersheet has this on 3 modules | Not unique on purpose; reported | Pass |
| API-04 | Week-agnostic | Create a week; place a module under a domain | Refused | As expected | Pass | — | — | — | — |
| API-05 | Hidden aliases | Search "SD3" | Finds the domain; the alias is never returned | As expected | Pass | — | — | — | — |
| API-06 | Program schedule and provenance | Module used in a course with a program week label; KYP provenance | Profile shows course, program, week label, source page and version | As expected | Pass | — | — | — | — |
| API-07 | Source catalog permissions | Viewer, editor, admin | 403, 403, 200 | As expected | Pass | — | — | — | — |
| API-08 | One save with people | Module with two owners, a Primary and two Backup SMEs (one new) | All created; an instructor as owner refused with the field named | As expected | Pass | — | — | — | — |
| API-09 | Sync never re-creates a removed relationship | Exclude a relationship key, delete it, sync | Not written again | As expected | Pass | — | — | — | — |
| UI-OS-01 | Detail panel | Module panel: domain, used in, SMEs Primary first, live resource link | As described | As expected | Pass | `testing/evidence/owner-sme/UI-OS-01-module-panel.png` | Toasts said "undefined"; the "Used in" note sat in its header; Type shown twice | All three fixed | Pass |
| UI-OS-02 | Owner picker | Add owner | Only NP team members offered | As expected | Pass | `testing/evidence/owner-sme/UI-OS-02-owner-picker-team-only.png` | — | — | — |
| UI-OS-03/04 | Add SME with a role | Pick an instructor, choose Backup 2 | Listed after the primary and backup 1 | As expected | Pass | `testing/evidence/owner-sme/UI-OS-04-sme-added.png` | — | — | — |
| UI-OS-05 | Persistence | Change the role to Backup 3; go to the course; close; reopen | Database, API and panel agree after reopening | As expected | Pass | `testing/evidence/owner-sme/UI-OS-05-reopened-persisted.png` | — | — | — |
| UI-OS-06 | Permissions | Viewer opens the module; tries to add an owner through the API | No edit controls; 403 | As expected | Pass | `testing/evidence/owner-sme/UI-OS-06-viewer-read-only.png` | — | — | — |
| UI-OS-07 | New record form | Owners (NP team), Primary SME, Backup SMEs | Roles Primary, Backup 1, Backup 2 saved | As expected | Pass | `testing/evidence/owner-sme/UI-OS-07-new-record-people.png` | The form sent SMEs without a role (now refused) | People section rebuilt | Pass |
| UI-CU-01 | Navigate | Click the course in "Used in" | Course panel with its modules | As expected | Pass | `testing/evidence/curriculum/UI-CU-01-course-panel.png` | — | — | — |
| UI-GR-01 | Graph owner filter | Owner filter options | Team members only, never instructors | As expected | Pass | `testing/evidence/graph/UI-GR-01-owner-filter-team-members.png` | It listed instructors (run-5 owners by role) | Owners come from `owned_by` | Pass |
| UI-MP-01 | Map panel and role | Open a module on the Map | Same entity component, read-only; KB role "admin"; no SD code | As expected | Pass | `testing/evidence/graph/UI-MP-01-map-entity-panel.png` | The Map showed "SD3 · Backend" | The Map shows domain names only | Pass |
| UI-SC-01/02 | Sources page | Counts, failed filter, search | Failures with reasons; live links | As expected | Pass | `testing/evidence/source-crawling/UI-SC-02-failures-with-reason.png` | Test race (count read before the reload) | Test waits for each state | Pass |
| UI-GU-01 | Guide | Sections and terms | Owners and SMEs, the four domains, registry, re-crawl; no workflow, theme, programme week, SD1–SD4, mastersheet | As expected | Pass | `testing/evidence/guide/UI-GU-01-guide.png` | — | — | — |

## 3. Data on DEV (the safety sequence)

| ID | Feature | Scenario | Expected | Actual | Result | Screenshot | Issues | Fixes | Retest |
|---|---|---|---|---|---|---|---|---|---|
| DATA-01 | Restore-tested backup | Full DEV backup restored into a scratch database | Every table identical | 45 / 45 tables, 189,094 rows identical (at the start, and again just before the first write) | Pass | — | — | — | — |
| DATA-02 | Migrations | 0039, 0040, 0041 on DEV (up, down, up rehearsed locally) | Applied | Applied | Pass | — | — | — | — |
| DATA-03 | Model conversion | Domains renamed with hidden aliases; domain links become `in_domain`; teaching becomes SME assignments with roles; owner-by-role cleared | Counts as rehearsed locally | 4 renamed, 20 `in_domain`, 64 SME assignments (23 primary, 34 backup, 7 named older-sheet roles), 20 owner fields cleared after checking each equals an SME | Pass | — | Local rehearsal overwrote its before-state (my piped command chain did not stop on a failure) | Before-state rebuilt from provenance and the audit log; the script now refuses to overwrite; revert proven (down, revert, up) | Pass |
| DATA-04 | KYP import | Apply twice | Second run changes nothing | 4 programs adopted + 4 created, 34 courses, 15 modules adopted + 76 created, 356 topics, 38 variants, 537 placements; second run unchanged | Pass | — | Adopted programs kept the old legacy flag (hidden from lists); domain-scoped old modules were not adopted | The importer clears the flag; the conversion clears domain scopes | Pass |
| DATA-05 | Cleanup: export, archive, verify, delete | Run the sequence | Every check passes before and after | 839 records (801 already archived, 38 old document programs), 98 relationships and 39 links removed; export in `backups/`; restore rehearsed locally (exact counts back) | Pass | — | — | — | — |
| DATA-06 | Graph validation | `cleanup_obsolete.py verify` | 4 domains; no week records or links; owners only team members; no SME without a role; no live link to an archived record; no duplicates; every curriculum link has provenance | All true | Pass | — | — | — | — |
| DATA-07 | Nothing comes back | Sync preview on DEV (rolled back) | Creates nothing | First preview would re-create 14 relationships and 39 links | **Bug** | — | Exclusions covered deleted records only | Migration 0041 and key exclusions; the sync skips them | Second preview: creates nothing |

## 4. Real-data checks (local copy and DEV preview)

| ID | Feature | Scenario | Expected | Actual | Result | Screenshot | Issues | Fixes | Retest |
|---|---|---|---|---|---|---|---|---|---|
| RD-AU-01 (local copy) | admin-dashboard | signed in as admin (workspace role) | Pass condition in the scenario | As expected | Pass | `testing/evidence/admin-dashboard/local-RD-AU-01-home.png` | — | — | — |
| RD-DM-01 (local copy) | curriculum | exactly four domains: Backend, Frontend, Fullstack, Test | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-DM-02 (local copy) | curriculum | old code SD3 finds Backend (hidden alias), never displayed | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-WK-01 (local copy) | curriculum | no week, workflow or theme record types | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-OS-01 (local copy) | owner-sme | module panel: SMEs with Primary first, then backups in order | Pass condition in the scenario | As expected | Pass | `testing/evidence/owner-sme/local-RD-OS-01-module-smes.png` | — | — | — |
| RD-CU-01 (local copy) | curriculum | module panel shows domain, used-in (course + program + week), topics, sources | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/local-RD-CU-01-module-panel.png` | — | — | — |
| RD-CU-02 (local copy) | curriculum | module sources are KYP pages with version | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-CU-03 (local copy) | curriculum | click a related course from the module panel | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/local-RD-CU-03-course-panel.png` | — | — | — |
| RD-CU-04 (local copy) | curriculum | program panel lists its courses in order | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/local-RD-CU-04-program-panel.png` | — | — | — |
| RD-CU-05 (local copy) | curriculum | domain panel lists the programs, courses and modules it classifies | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/local-RD-CU-05-domain-panel.png` | — | — | — |
| RD-AD-01 (local copy) | admin-dashboard | Admin overview cards | Pass condition in the scenario | As expected | Pass | `testing/evidence/admin-dashboard/local-RD-AD-01-admin-overview.png` | — | — | — |
| RD-SC-01 (local copy) | source-crawling | Sources & sync: catalog counts by provider and status | Pass condition in the scenario | As expected | Pass | `testing/evidence/source-crawling/local-RD-SC-01-sources.png` | — | — | — |
| RD-SC-02 (local copy) | source-crawling | failures listed with link and reason | Pass condition in the scenario | As expected | Pass | `testing/evidence/source-crawling/local-RD-SC-02-failures.png` | — | — | — |
| RD-AD-02 (local copy) | admin-dashboard | Data quality lists SME role issues from the sources | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-GU-01 (local copy) | guide | Guide explains the model; no legacy terms | Pass condition in the scenario | As expected | Pass | `testing/evidence/guide/local-RD-GU-01-guide.png` | — | — | — |
| RD-GR-01 (local copy) | graph | Graph editor loads on real data (paged) | Pass condition in the scenario | As expected | Pass | `testing/evidence/graph/local-RD-GR-01-graph.png` | — | — | — |
| RD-GR-02 (local copy) | graph | owner filter lists NP team members, never instructors | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-GR-03 (local copy) | graph | auto-layout then reset | Pass condition in the scenario | As expected | Pass | `testing/evidence/graph/local-RD-GR-04-reset.png` | — | — | — |
| RD-GR-04 (local copy) | graph | no page errors on the graph | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-RS-1366x768@1 (local copy) | responsive | graph at 1366x768, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 906×703 of 1366, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1366x768-dpr1.png` | — | — | — |
| RD-RP-1366x768@1 (local copy) | responsive | detail panel at 1366x768, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1366x768-dpr1.png` | — | — | — |
| RD-RS-1366x768@2 (local copy) | responsive | graph at 1366x768, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 906×703 of 1366, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1366x768-dpr2.png` | — | — | — |
| RD-RP-1366x768@2 (local copy) | responsive | detail panel at 1366x768, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1366x768-dpr2.png` | — | — | — |
| RD-RS-1440x900@1 (local copy) | responsive | graph at 1440x900, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 980×835 of 1440, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1440x900-dpr1.png` | — | — | — |
| RD-RP-1440x900@1 (local copy) | responsive | detail panel at 1440x900, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1440x900-dpr1.png` | — | — | — |
| RD-RS-1440x900@2 (local copy) | responsive | graph at 1440x900, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 980×835 of 1440, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1440x900-dpr2.png` | — | — | — |
| RD-RP-1440x900@2 (local copy) | responsive | detail panel at 1440x900, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1440x900-dpr2.png` | — | — | — |
| RD-RS-1920x1080@1 (local copy) | responsive | graph at 1920x1080, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 1460×1015 of 1920, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1920x1080-dpr1.png` | — | — | — |
| RD-RP-1920x1080@1 (local copy) | responsive | detail panel at 1920x1080, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1920x1080-dpr1.png` | — | — | — |
| RD-RS-1920x1080@2 (local copy) | responsive | graph at 1920x1080, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 1460×1015 of 1920, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-1920x1080-dpr2.png` | — | — | — |
| RD-RP-1920x1080@2 (local copy) | responsive | detail panel at 1920x1080, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-1920x1080-dpr2.png` | — | — | — |
| RD-RS-2560x1440@1 (local copy) | responsive | graph at 2560x1440, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 2100×1375 of 2560, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-2560x1440-dpr1.png` | — | — | — |
| RD-RP-2560x1440@1 (local copy) | responsive | detail panel at 2560x1440, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-2560x1440-dpr1.png` | — | — | — |
| RD-RS-2560x1440@2 (local copy) | responsive | graph at 2560x1440, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 2100×1375 of 2560, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-2560x1440-dpr2.png` | — | — | — |
| RD-RP-2560x1440@2 (local copy) | responsive | detail panel at 2560x1440, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-2560x1440-dpr2.png` | — | — | — |
| RD-RS-3840x2160@1 (local copy) | responsive | graph at 3840x2160, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 3242×2080 of 3840, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-3840x2160-dpr1.png` | — | — | — |
| RD-RP-3840x2160@1 (local copy) | responsive | detail panel at 3840x2160, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-3840x2160-dpr1.png` | — | — | — |
| RD-RS-3840x2160@2 (local copy) | responsive | graph at 3840x2160, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 3242×2080 of 3840, no sideways scroll | Pass | `testing/evidence/responsive/local-RD-RS-graph-3840x2160-dpr2.png` | — | — | — |
| RD-RP-3840x2160@2 (local copy) | responsive | detail panel at 3840x2160, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/local-RD-RP-panel-3840x2160-dpr2.png` | — | — | — |
| RD-MP-01 (local copy) | graph | the Map shows the same entity panel and the KB role | Pass condition in the scenario | As expected | Pass | `testing/evidence/graph/local-RD-MP-01-map-panel.png` | — | — | — |
| RD-AU-01 (DEV preview) | admin-dashboard | signed in as admin (workspace role) | Pass condition in the scenario | As expected | Pass | `testing/evidence/admin-dashboard/dev-RD-AU-01-home.png` | — | — | — |
| RD-DM-01 (DEV preview) | curriculum | exactly four domains: Backend, Frontend, Fullstack, Test | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-DM-02 (DEV preview) | curriculum | old code SD3 finds Backend (hidden alias), never displayed | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-WK-01 (DEV preview) | curriculum | no week, workflow or theme record types | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-OS-01 (DEV preview) | owner-sme | module panel: SMEs with Primary first, then backups in order | Pass condition in the scenario | As expected | Pass | `testing/evidence/owner-sme/dev-RD-OS-01-module-smes.png` | — | — | — |
| RD-CU-01 (DEV preview) | curriculum | module panel shows domain, used-in (course + program + week), topics, sources | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/dev-RD-CU-01-module-panel.png` | — | — | — |
| RD-CU-02 (DEV preview) | curriculum | module sources are KYP pages with version | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-CU-03 (DEV preview) | curriculum | click a related course from the module panel | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/dev-RD-CU-03-course-panel.png` | — | — | — |
| RD-CU-04 (DEV preview) | curriculum | program panel lists its courses in order | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/dev-RD-CU-04-program-panel.png` | — | — | — |
| RD-CU-05 (DEV preview) | curriculum | domain panel lists the programs, courses and modules it classifies | Pass condition in the scenario | As expected | Pass | `testing/evidence/curriculum/dev-RD-CU-05-domain-panel.png` | — | — | — |
| RD-AD-01 (DEV preview) | admin-dashboard | Admin overview cards | Pass condition in the scenario | As expected | Pass | `testing/evidence/admin-dashboard/dev-RD-AD-01-admin-overview.png` | — | — | — |
| RD-SC-01 (DEV preview) | source-crawling | Sources & sync: catalog counts by provider and status | Pass condition in the scenario | As expected | Pass | `testing/evidence/source-crawling/dev-RD-SC-01-sources.png` | — | — | — |
| RD-SC-02 (DEV preview) | source-crawling | failures listed with link and reason | Pass condition in the scenario | As expected | Pass | `testing/evidence/source-crawling/dev-RD-SC-02-failures.png` | — | — | — |
| RD-AD-02 (DEV preview) | admin-dashboard | Data quality lists SME role issues from the sources | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-GU-01 (DEV preview) | guide | Guide explains the model; no legacy terms | Pass condition in the scenario | As expected | Pass | `testing/evidence/guide/dev-RD-GU-01-guide.png` | — | — | — |
| RD-GR-01 (DEV preview) | graph | Graph editor loads on real data (paged) | Pass condition in the scenario | As expected | Pass | `testing/evidence/graph/dev-RD-GR-01-graph.png` | — | — | — |
| RD-GR-02 (DEV preview) | graph | owner filter lists NP team members, never instructors | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-GR-03 (DEV preview) | graph | auto-layout then reset | Pass condition in the scenario | As expected | Pass | `testing/evidence/graph/dev-RD-GR-04-reset.png` | — | — | — |
| RD-GR-04 (DEV preview) | graph | no page errors on the graph | Pass condition in the scenario | As expected | Pass | `—` | — | — | — |
| RD-RS-1366x768@1 (DEV preview) | responsive | graph at 1366x768, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 906×703 of 1366, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1366x768-dpr1.png` | — | — | — |
| RD-RP-1366x768@1 (DEV preview) | responsive | detail panel at 1366x768, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1366x768-dpr1.png` | — | — | — |
| RD-RS-1366x768@2 (DEV preview) | responsive | graph at 1366x768, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 906×703 of 1366, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1366x768-dpr2.png` | — | — | — |
| RD-RP-1366x768@2 (DEV preview) | responsive | detail panel at 1366x768, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1366x768-dpr2.png` | — | — | — |
| RD-RS-1440x900@1 (DEV preview) | responsive | graph at 1440x900, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 980×835 of 1440, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1440x900-dpr1.png` | — | — | — |
| RD-RP-1440x900@1 (DEV preview) | responsive | detail panel at 1440x900, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1440x900-dpr1.png` | — | — | — |
| RD-RS-1440x900@2 (DEV preview) | responsive | graph at 1440x900, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 980×835 of 1440, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1440x900-dpr2.png` | — | — | — |
| RD-RP-1440x900@2 (DEV preview) | responsive | detail panel at 1440x900, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1440x900-dpr2.png` | — | — | — |
| RD-RS-1920x1080@1 (DEV preview) | responsive | graph at 1920x1080, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 1460×1015 of 1920, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1920x1080-dpr1.png` | — | — | — |
| RD-RP-1920x1080@1 (DEV preview) | responsive | detail panel at 1920x1080, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1920x1080-dpr1.png` | — | — | — |
| RD-RS-1920x1080@2 (DEV preview) | responsive | graph at 1920x1080, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 1460×1015 of 1920, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-1920x1080-dpr2.png` | — | — | — |
| RD-RP-1920x1080@2 (DEV preview) | responsive | detail panel at 1920x1080, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-1920x1080-dpr2.png` | — | — | — |
| RD-RS-2560x1440@1 (DEV preview) | responsive | graph at 2560x1440, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 2100×1375 of 2560, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-2560x1440-dpr1.png` | — | — | — |
| RD-RP-2560x1440@1 (DEV preview) | responsive | detail panel at 2560x1440, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-2560x1440-dpr1.png` | — | — | — |
| RD-RS-2560x1440@2 (DEV preview) | responsive | graph at 2560x1440, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 2100×1375 of 2560, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-2560x1440-dpr2.png` | — | — | — |
| RD-RP-2560x1440@2 (DEV preview) | responsive | detail panel at 2560x1440, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-2560x1440-dpr2.png` | — | — | — |
| RD-RS-3840x2160@1 (DEV preview) | responsive | graph at 3840x2160, device scale 1: fills the space, no sideways scroll | Pass condition in the scenario | canvas 3242×2080 of 3840, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-3840x2160-dpr1.png` | — | — | — |
| RD-RP-3840x2160@1 (DEV preview) | responsive | detail panel at 3840x2160, scale 1: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-3840x2160-dpr1.png` | — | — | — |
| RD-RS-3840x2160@2 (DEV preview) | responsive | graph at 3840x2160, device scale 2: fills the space, no sideways scroll | Pass condition in the scenario | canvas 3242×2080 of 3840, no sideways scroll | Pass | `testing/evidence/responsive/dev-RD-RS-graph-3840x2160-dpr2.png` | — | — | — |
| RD-RP-3840x2160@2 (DEV preview) | responsive | detail panel at 3840x2160, scale 2: proportionate width | Pass condition in the scenario | As expected | Pass | `testing/evidence/responsive/dev-RD-RP-panel-3840x2160-dpr2.png` | — | — | — |


The real-data rows above give no record details: some show people's names. The details are in the local JSON files.

## 5. Bugs found and fixed in this run

1. A linked sheet was skipped by the crawler when a folder walk had listed it first (SRC-01).
2. India outline shapes (bold-paragraph modules, repeated course rows) were mis-parsed (SRC-07).
3. Owner fields accepted instructors, and the Graph editor's owner filter listed instructors (UI-GR-01).
4. The New record form and the generic relationship picker created SMEs without a role (UI-OS-07). Owners and SMEs now have their own controls.
5. Linking an instructor to a sign-in account was refused after the owner change (the checks are now separate).
6. The Map displayed SD codes (UI-MP-01).
7. Detail panel: "undefined" toasts, a squeezed note, a duplicate Type row, and no description for viewers.
8. Databases built from the migrations alone lacked the team-member type and the owner relationship (0039 creates them).
9. Adopted programs were hidden as legacy; domain-scoped old modules were not adopted (DATA-04).
10. The sync would have re-created removed relationships and links (DATA-07, migration 0041).
11. Graph: trees stacked in a tall column, and nothing was readable when zoomed out (fixed: packing fitted to the canvas, program and course labels at a constant on-screen size).
12. A local rehearsal command chain did not stop on a failure and overwrote a local before-state (local only; recovered; the scripts now refuse).
