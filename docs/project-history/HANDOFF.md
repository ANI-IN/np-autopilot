# HANDOFF: DEV preview deployed, Google sign-in working, manual testing (2026-11-07)

Branch `auto/knowledge-platform-20261102` is pushed. Nothing is on `main`. Production (Vercel Production and the production Supabase project) was not touched.

**The preview is live** at the fixed alias **https://np-autopilot-kb-dev.vercel.app**, wired to the DEV Supabase project, behind Vercel's deployment protection. The owner signs in with an IK Google account and holds the KB admin role on DEV. Manual testing by the owner is under way; issues come back to this branch.

## What was done

| Step | Result |
|---|---|
| Vercel variables | 8 set for **Preview (all previews)**, never Production; the 6 Production variables untouched (`docs/operations/dev-deploy.md` step 2) |
| DEV database | Was missing migration **0035** (member invites). Backed up first (`backups/`, gitignored), then applied; DEV now matches the chain exactly (36 migrations, same tables and functions, RLS on everywhere) |
| Deploy | `scripts/deploy_dev_preview.sh --check`, then the deploy; the script now moves a fixed alias to each preview (`DEV_PREVIEW_ALIAS`) |
| Smoke tests | 6/6 in the script, plus: config names DEV, security headers, forged tokens refused, a wrong sync secret refused, the alias protected (302 to Vercel's login without access) |
| Sync | One call through `/api/cron/kb-sync` with the secret: ok, 0 changes, 22.9 s. Vault holds the sync secret and the Vercel bypass; the hourly `kb-sync` cron job targets the alias |
| Google sign-in | The owner configured the Google client and DEV's Auth (provider, before-user-created hook, URL configuration); a first sign-in created the profile; `pipeline/kb_admins.py` granted KB admin on DEV, audited, and `kb.role()` evaluates to admin under RLS |
| Access | Through a Vercel shareable link on the alias (30-day expiry). Deployment protection stays on; the link is kept out of the repo |
| Drive | The service account was restored and re-keyed; the key lives outside the repo. The Drive corpus is reduced to one file on purpose for initial testing; nothing was run on it |

## Known limitations

- **Live updates poll every 2.5 s on the preview:** Realtime needs `KB_REALTIME_ORIGIN` and a `connect-src` change in `vercel.json`, which production shares.
- **The map at `/` labels every account "member":** that is the map's profile role (migration 0015), separate from the KB role.
- **The reduced Drive corpus has no extractable files** (its one file is the excluded crawl registry). Restoring the full corpus is on the backlog; no pipeline, import or sync runs on the reduced corpus without the owner's approval, and a smaller corpus must never be read as deletions.

## Next

1. The owner's manual test pass on the preview; fixes on this branch, redeployed with `bash scripts/deploy_dev_preview.sh` (the alias and the access link stay the same).
2. Then GO_LIVE steps 8–11 rehearsed on the preview, with timings.
3. Open the PR, review, merge; production via `docs/operations/GO_LIVE.md`.

---

# HANDOFF: local end-to-end test before the preview deploy (2026-11-06)

Branch `auto/knowledge-platform-20261102` is pushed. Nothing is on `main`, and nothing touched Vercel or Production in this run.

**The app passed end to end locally, after two real bugs were found and fixed.** The Vercel preview is on hold at the owner's request, until the owner gives the go-ahead.

**Owner decision (2026-11-05):** add the dev variables to the Preview environment for ALL previews, never Production. This settles "Action required" 1 in the section below, in favour of option (b). The variables are **not set yet**. On the go-ahead: set them, run `bash scripts/deploy_dev_preview.sh --check`, deploy, smoke-test, rehearse GO_LIVE steps 8–11.

Left running: the demo, **http://localhost:8765/local-login**; the real-data copy, **http://localhost:8766/local-login**; the local database. A reboot stops all three. Start Docker Desktop first, then follow `docs/operations/local-demo.md`.

## What was deployed and tested

The demo server ran from a fresh clone of the pushed branch, so nothing ignored or left over on this machine could hide a problem. Final numbers are all on commit `bb46ac5`.

| Check | Result |
|---|---|
| Browser and integration files, one at a time, from a fresh clone | **154 of 154**: sync 25, MCP 8, Realtime gap 1, e2e 71, UI 34, console 2, Realtime 1, propagation 1, graph 11 (one per process). No hung test |
| `bash scripts/verify_all.sh --skip-browser` | **VERIFY: ALL PASS.** 1,339 passed, 13 failed (all 13 in `main`'s baseline), 50 skipped |
| Journey on the demo, `eval/kb_journey_check.py` (new) | **51 of 51**: real sign-in, three roles in the UI, approvals, MCP over stdio, live Graph and `/` tabs, role limits, hostile input, sign-out |
| Workflows on the real-data copy | **26 of 26** |
| Dashboard fit, both servers | PASS at 1536×730 and 1920×1080 |
| Every screen on the real-data copy | 28 screens, 0 console errors. The demo's screens were also inspected by eye |
| "Sync now" on the real-data copy | HTTP 200, 5,015 records and 3,097 relationships unchanged |
| A full reboot of the laptop | The data survived; the stack and both servers came back |
| Markdown links | 0 broken |

`eval/kb_sync_proof.py` was not run on the real-data copy: it leaves a made-up row behind. The sync's changes are covered by `tests/test_kb_sync.py` (25 of 25).

## Found and fixed

| Problem | Reach | Evidence |
|---|---|---|
| **A rename could silently overwrite someone else's.** The Graph page read the version on Enter, not when the rename began. If another person's rename arrived live during typing, the save passed the conflict check | **Ships** | Old code loses the conflict 3 of 3; the fix passes 25 of 25. `test_b3` now plays the real sequence |
| **Live updates could arrive up to 20 s late after idle.** The page counted Realtime's join as "live" and slowed its polling, but after idle a change can't be delivered for a few more seconds (2.7 s measured). Nothing was lost | **Ships** | The old code polls 0 times in 9 s; the fix keeps polling until "Subscribed to PostgreSQL". The real-socket test passes on a Realtime that had really gone idle. New `tests/test_kb_realtime_gap.py` |
| **Local pages could stay blank.** The local server's listen queue of 5 overflowed on the page's burst of about 30 modules, and Windows refused the rest | Local servers only (`eval/` never ships) | About 1 run in 3 before; 20 of 20 after. New `tests/test_kb_dev_server.py` |

`test_b3` was already flaky on the commit before this run (3 of 15), which earlier runs had not shown. For a while it looked as if the server had accepted a stale write. It had not: the double-click had hit a neighbouring record, and the server's conflict check is sound.

## New known limitations

- **A record arriving live can land partly on top of a neighbour** on the Graph page, and a click then hits whichever is on top. Display only; Auto-layout clears it.
- **The `/` map's chips are wrong on the demo only:** "0 current domains + 4 legacy" and "0 current instructors + 6 from older sheets". The seed has no `domain_offers` relationships or mastersheet roles. On the real-data copy they match the database (4, 20 and 25). See `docs/operations/local-demo.md`.
- **`migrate.py status` reports 0029 as CHANGED on the local test database.** It ran before a comment in the file was reworded. The diff is comment-only, and `kb_realdata` holds the current checksum. Production is at 0021, so it will only run the final file. If `status` shows the same on DEV, check it is this comment-only change.
- **The preview is still untested,** including Google sign-in, which local sign-in does not exercise.

---

# HANDOFF — FINAL: pending items, preview, production-ready repository (2026-11-04)

Branch `auto/knowledge-platform-20261102` is pushed (last commit: see `git log`). Nothing is on `main`, and nothing touched Production or its settings.

**Preview: BLOCKED on one owner step.**
- **The new token works.** The `VERCEL_TOKEN` in `.env` returns 200 from the API, its team owns `np-autopilot`, and the project is linked.
- **The preview has no variables.** Vercel refuses variables scoped to this branch: "Project np-autopilot does not have a connected Git repository".
- **Not done in this run, on purpose:**
  - Connecting the repository. That is a project-wide change, and it can make pushes to `main` deploy Production.
  - Setting the variables for all Previews. The session's safety check refused it as wider than branch-only.
- **Result:** no variable written, nothing deployed. See "Action required" 1.

Left running: the real-data server, **http://localhost:8766/local-login**, and the local database. The demo server is off.

The README links here. The previous top section (run 6) follows this one. The run log is [PROGRESS.md](PROGRESS.md).

## Status

| Item | Status | Evidence |
|---|---|---|
| Browser test files, one at a time | **VERIFIED** | see "Final verification" below |
| Dashboard fit check | **VERIFIED** | `eval/kb_fit_check.py` on :8766. 1536×730: document 730/730. 1920×1080: 1080/1080. 9 API calls, 0 errors |
| D2 preview deploy and smoke test | **BLOCKED (owner step 1)** | token OK (API 200, project linked). Branch-scoped Preview variables refused: no connected Git repository |
| D3 GO_LIVE steps 8–11 rehearsed on the preview | **NOT DONE** (needs D2) | steps 0–7 rehearsed on DEV (run 6). Steps 3, 5 and 6 corrected against the code, see below |
| Finish items: PROGRESS, demo re-seed, commit and push | **VERIFIED** | demo re-seeded (63 records); every phase committed and pushed |
| Repository cleanup | **VERIFIED** | 31 moved, 314 deleted, 28 added; checkout 96.1 MB (803 files) → 33.5 MB (517 files); guard tests show no new failures |
| Standard repository files | **VERIFIED** | CONTRIBUTING, SECURITY, CHANGELOG, PR template, issue templates (bug, feature; blank issues off), .editorconfig. No LICENSE: the owner decides |
| Documentation with Mermaid diagrams | **VERIFIED** | 34 diagrams, 34 rendered (list below); every doc checked against the code |
| Every Markdown link resolves | **VERIFIED** | `python scripts/check_md_links.py`: 0 broken (new permanent script) |
| README quick start from a fresh clone | **VERIFIED, after 3 fixes** | `db/local/setup.sh` failed on Windows (see below); fixed, then setup, seed, demo server, `/local-login` 200 and `/kb/` 200 all from a fresh clone |
| `git ls-files` hygiene | **VERIFIED** | no `.env`, keys, backups, real data, local config or run artefacts. The plugin's `.mcp.json` holds only placeholders |
| Section 7 workflows after the cleanup | **VERIFIED** | `eval/kb_workflow_check.py` on :8766: 26/26 |
| Full suite after the cleanup | **VERIFIED: no new failures vs main** | see "Final verification" |
| Preview redeploy after the cleanup | **NOT DONE** (needs D2) | — |

### Final verification (after the cleanup and the docs)

All runs on 2026-11-04, after every cleanup and docs commit:

- **`bash scripts/verify_all.sh --skip-browser`: VERIFY: ALL PASS** (14:37–14:45).
  - Static checks, including ruff, which was fixed in this run.
  - Plugin copy and validation.
  - No server key names in the browser bundle.
  - `.env` is not tracked.
  - No secret-shaped strings in history.
  - RLS on every kb table.
  - The deploy guard.
  - All KB tests pass.
  - Non-browser suite: **1,338 passed, 13 failed, 50 skipped. All 13 are in main's baseline, so no new failures.**
- **Browser files, one at a time** (14:27–14:37). No test hung, so the 10-minute rule never triggered.

  | File | Result |
  |---|---|
  | `test_kb_e2e.py` | 71/71 |
  | `test_kb_ui_run6.py` | 34/34 |
  | `test_kb_console_run6.py` | 2/2 |
  | `test_kb_realtime.py` | 1/1 |
  | `test_kb_propagation_e2e.py` | 1/1 (the 26-operation matrix) |
  | `test_kb_graph_run6.py` | **11/11, one test per process** |

- **Section 7 workflows** (`eval/kb_workflow_check.py` on :8766): **26/26**.
  - The checks are made in the API, the database, the Graph page (about 3.3–3.9 s), the "/" map (under 0.1 s) and the Activity sentences.
  - The error paths pass too: 422 naming the field, 409 with the current record, and the network dropped and back.
- **Fit check:** PASS at 1536×730 and 1920×1080.
- **Link check:** 0 broken.
- **Diagrams:** 34 of 34 render.
- **Fresh-clone quick start:** works.

### Found and fixed in this run

- **Browser tests:** in a full run, 5 UI tests timed out waiting for the shell. Every test's browser context stayed open until the file ended, each still polling the change feed. Each test now closes its own pages. The UI file passes 34/34 in 60 s (it was 29/34 in 243 s).
- **`db/local/setup.sh` failed from a fresh clone on Windows:**
  - It ran `python3`, which in an activated venv is the system Python.
  - It needed `psql`, which Git Bash doesn't have.
  - The mastersheet freshness gate blocked the local projection.
  - All three are fixed. The freshness gate gets the same local-only reason `verify_all.sh` already uses.
- **GO_LIVE.md, checked against the code:**
  - Step 3's rollback was wrong: `migrate.py down` refuses once the import has data, so the rollback is to restore the step-1 backup.
  - Steps 5–6: `kb_legacy_delete.py` refuses production for `plan` and `restore` too, so both carry the explicit gate.
- **deployment.md:**
  - Change feed polling is 2.5 s, not 4 s.
  - The function limit is 60 s, not 15 s.
  - A first IK sign-in creates a `member` profile (migration 0015).
- **The "/" map reads kb through its own routes** (`npmap.py`), not `GET /api/kb/graph`. contracts.md, the PR description and the CHANGELOG said otherwise.
- **The in-app Guide:**
  - Graph gestures.
  - The real legacy filter labels.
  - Roles: everyone starts as a viewer.
  - Invitations and the last-admin rule.
  - Permanent deletion.
  - "Who to contact" no longer points viewers at an admin-only tab.
- **http-api.md role rows, and mcp.md:**
  - http-api.md: duplicating a record needs editor; a contributor's `PATCH` becomes a 202 proposal; approvals of type changes and claims need admin; the missing routes are added.
  - mcp.md: token expiry, and the test count.
- **Dead code removed:**
  - `PERMANENT_DELETE_SQL`, which had no callers.
  - `eval/kb_run5_ui_check.py`, replaced by the UI sweep.
- **Tests no longer write into `docs/`.** The change matrix goes to the temp folder.
- **New:**
  - `scripts/check_md_links.py`.
  - `verify_all.sh --skip-browser`, for 16 GB laptops: it lists the browser files as NOT RUN, to run one at a time.

## Repository cleanup

The full record is in the commit messages (53ce69c and those after it).

| | Count | Notes |
|---|---|---|
| **Removed** | 314 files | `docs/run6/` (112), `docs/redesign/` (162 images), `docs/inventory/`, `docs/perf/`, `docs/archive/`, `docs/screenshots/*.png` (no references; likely real names), 8 superseded reports, 6 root design docs, `ENV_SETUP.md`, `eval/kb_run5_ui_check.py`, `knowledge/.gitkeep` |
| **Untracked, kept on disk and gitignored** | 4 files | `knowledge/merged_graph.json` (21 MB), `_graph_data.json`, `_graph_files.json`, `_graph_logic.mjs`. They are generated and nothing reads them from git. This settles the earlier owner decision on `merged_graph.json` |
| **Moved** | 31 files | process logs to `docs/project-history/`; docs into `architecture/`, `operations/`, `integrations/`; Phase 0 design docs to `project-history/design/`; open plans to `project-history/decisions/`; `07-risks.md` to `docs/operations/risk-register.md` |
| **Added** | 28 files | the standard repository files, the docs index, the history page, 11 architecture, security and integration docs, 7 workflow docs, 5 operations docs, the link checker |
| **Size** | | tracked checkout 96.1 MB → 33.5 MB, 803 → 517 files. The git pack stays 61.5 MiB: history keeps everything, and only the history rewrite plan (`decisions/HISTORY-REWRITE-PLAN.md`) would shrink it |
| **Root** | 6 Markdown files | README, CLAUDE, CONTRIBUTING, SECURITY, CHANGELOG, BUILD_LOG, plus the tool configs |

**Kept on purpose, with the reason:**
- `BUILD_LOG.md` stays at the root: every pipeline pass appends to it, and a test pins the path.
- `knowledge/graph.json`, `content_graph.json` and `graph.html` stay tracked: code loads them at import and the CI renderer uses them. CI can't rebuild them yet.
- The pipeline's decision records stay in `docs/`, because code and tests read them by path: `PRE-CRAWL-DECISIONS.md` (the crawl gate), `ACCEPTANCE-CHECKLIST.md` (5 tests) and `baseline-failures.txt`.

**Not changed (recommendations):**
- Exclude `scripts/` from the deploy (about 100 KB uploaded for nothing). It changes the bundle, so do it with a preview to check.
- `.vercelignore` and `deploy_bundle_size.py` name a `pipeline/__init__.py` that doesn't exist.
- Comments inside the CSP-hashed inline scripts of `public/index.html`, and inside migrations (which are checksummed), still name old doc paths. Editing them changes the hashes.

## Documentation map

The full index is [docs/README.md](../README.md).

- **Architecture:** `overview` (system context, containers, service layer, request sequence), `data-model` (5 entity diagrams plus the intake mapping), `knowledge-graph`, `single-source-of-truth`, `contracts`, `schema`, `auth`, `import-mapping`, `design-system`.
- **Workflows:** CRUD and change propagation, sync, sign-in and roles, approvals, owner linking, legacy deletion and restore, MCP and Claude.
- **Operations:** deployment, dev-deploy, GO_LIVE, environment variables, backups and restore, monitoring and troubleshooting, runbook, testing, local demo, legacy removal, window runsheet, risk register.
- **Security:** `docs/security.md` (access model, role × action matrix, secrets) and the root `SECURITY.md`.
- **Integrations:** connectors (framework, lifecycle, how to add Google Drive, Uplevel and Atlassian), MCP, HTTP API.
- **Also:** `VISION_AND_ROADMAP.md` (now with a roadmap timeline), the project history, CONTRIBUTING, CHANGELOG.

## Diagrams and validation

Each diagram was rendered on its own with `@mermaid-js/mermaid-cli` 11.17.1 (Mermaid 11). **34 of 34 render.** Two were also checked by eye: the README overview, and the core entity diagram against the real `kb` columns.

| File | Diagrams |
|---|---|
| README.md | 1 flowchart (architecture) |
| architecture/overview.md | 3 flowcharts, 1 sequence |
| architecture/data-model.md | 5 erDiagrams, 1 flowchart |
| architecture/knowledge-graph.md | 2 flowcharts |
| architecture/single-source-of-truth.md | 2 flowcharts |
| security.md | 1 flowchart |
| integrations/connectors.md | 1 stateDiagram |
| integrations/mcp.md | 1 sequence |
| workflows/ (7 files) | crud 2, sync 1, auth 2, approvals 1, owner-linking 1, legacy 1, mcp 1 |
| operations/ | deployment 1, GO_LIVE 1 (step order; step 6 is the point of no return), backups 1, monitoring 1, runbook 1 |
| VISION_AND_ROADMAP.md | 1 gantt (roadmap) |
| project-history/audit.md | 1 flowchart (pre-existing) |

## Known limitations

- **Preview:** neither the preview nor GO_LIVE steps 8–11 has been exercised (owner step 1).
- **Graph tests:** two tests in `test_kb_graph_run6.py` hang when run back to back in one process. Each passes alone; run that file one test per process.
- **One flaky browser test:** `test_kb_e2e.py` failed once at the start of a run with 2.5 GB free and passed alone. It is counted as failed, then passed alone, not as a pass.
- **Graph page:** group-by-type takes about 40–50 s the first time on the test data.
- **AI tokens with an admin owner:** the AI can review and merge relationship types, restore records, manage tags and templates, and read the sync log. Nothing in the service or the database stops it. It still can't grant roles, link accounts, approve, start a sync or delete permanently. Documented in `docs/security.md`; see owner decision 6.
- **Connector contract:** the engine needs all four config keys from `load_config`, hard-codes the `np:` id prefix and ignores `actor_label` (documented in `docs/integrations/connectors.md`).
- **Not re-run, per the memory rules:** the 25-user load test and the 5,000-node benchmark.
- **The old explorer's read paths** in `web/lib/data.py` stay until production runs on kb (`docs/operations/legacy-removal.md`).
- **No LICENSE file:** that is the owner's decision.

## Action required from owner

In order, through to production.

1. **Vercel Preview variables.** The token is fine now. Choose one:
   - **(a)** Connect the Git repository (Vercel → Settings → Git) so the variables can be scoped to `auto/knowledge-platform-20261102`. **First** set the Production branch, and an Ignored Build Step so that pushes don't deploy Production.
   - **(b)** Add the variables for **Preview (all branches)**. Previews of this project come only from the CLI.

   The names and their sources are in `docs/operations/dev-deploy.md` step 2:
   - `SUPABASE_JWT_SECRET` isn't needed: the dev project signs with ES256 keys.
   - `NP_SHARED_ACCOUNTS` is optional.
   - Create a new `KB_SYNC_SECRET`.

   Then run `bash scripts/deploy_dev_preview.sh --check`, then the same command without `--check`. It deploys to Preview only.
2. **Google sign-in on the preview:**
   - Add the preview URL as an authorised JavaScript origin of the Google client.
   - On Supabase DEV, set up the Google provider, the before-user-created hook and the URL configuration (dev-deploy.md step 5).
   - Put the same `KB_SYNC_SECRET` in DEV's Vault and install the schedule (step 6).
3. **Make yourself admin on DEV:** sign in once on the preview, then run `ADMIN_EMAILS=<you>@interviewkickstart.com python pipeline/kb_admins.py` against DEV.
4. **Rehearse GO_LIVE steps 8–11 on the preview,** and record the timings in GO_LIVE.md. This includes one sync timed on Vercel.
5. **Decide:** may a shared mailbox (`NP_SHARED_ACCOUNTS`) hold an editor or admin role in the KB? See `docs/security.md`.
6. **Decide:** should an admin-owned AI token be limited further? It can currently review relationship types, restore records and manage tags and templates. See "Known limitations".
7. **Decide:** a LICENSE for the repository, if any.
8. **Decide:** whether to run the history rewrite (`docs/project-history/decisions/HISTORY-REWRITE-PLAN.md`). The deleted screenshots, likely with real names, and the large graph files are still in git history. Rewriting history needs every clone to re-clone, and it is not something this run may do.
9. **Review and merge the PR** (`docs/project-history/PR_DESCRIPTION.md`).
10. **Production:** follow `docs/operations/GO_LIVE.md`, including step 6, the **permanent legacy deletion**. It exports first and the restore is tested. After that step, rolling back means the export or the step-1 backup.
11. **After go-live:**
    - Remove the old-table read paths (`docs/operations/legacy-removal.md`).
    - Consider excluding `scripts/` from the deploy, checked against a preview.

---

# HANDOFF — Run 6 (final): one source of truth, a better graph, legacy cleanup, security, go-live rehearsal (2026-11-04)

Branch `auto/knowledge-platform-20261102` is pushed. Nothing is on `main` and nothing is on Production.

**Preview: none yet.** The new `VERCEL_TOKEN` works (team and project confirmed; project linked), but the preview has no variables: Vercel refuses branch-scoped Preview variables because the project has **no connected Git repository**, and setting them for all Previews was outside this run's permissions. See "Action required" 1.

**Final verification in progress** (see the "Full suite" row). At the end, only the real-data server (**http://localhost:8766/local-login**) and the local database will be left running; the demo server stays off.

Logs: PROGRESS.md, sections "Run 6 log" and "Run 6 resume".

## Status

Evidence for every row is in PROGRESS.md.

| Area | Status | Evidence |
|---|---|---|
| One source of truth: every view, including the "/" map, reads kb | **VERIFIED** | docs/ARCHITECTURE.md; the map's own tests (179 passed); rollback switch `NP_MAP_SOURCE=old` |
| Live updates everywhere, through the change feed and its kinds | **VERIFIED** | matrix: all 26 operations on the Graph page and on "/" (docs/run6/MATRIX.md); slowest about 2.6 s |
| Permanent deletion of legacy domains and modules, locally and on DEV | **VERIFIED** | 946 deleted in each; restore rehearsed with every table's row count back exactly; the next sync created 0 and found 0 conflicts |
| IK branding and the one-screen dashboard | **VERIFIED** | eval/kb_fit_check.py: fits at 1536×730 and 1920×1080; 0 page errors |
| Navigation: sidebar names match page titles, the palette reaches every page, old bookmarks redirect | **VERIFIED** | browser tests for the dashboard, palette and accessibility: 15 passed; tests/test_kb_redirects_run6.py |
| Activity as plain sentences (who, what, which record, old → new) | **VERIFIED** | tests/test_kb_activity_run6.py, one sentence per matrix operation; the workflow check (26 of 26) |
| Members by invitation; the last admin can't be removed | **VERIFIED** | tests/test_kb_members_run6.py |
| IK accounts only, checked on every request; security headers; access sweep | **VERIFIED** | tests/test_kb_access_sweep.py; docs/run6/SECURITY_SWEEP.md |
| One validation layer: the sync and the UI reject the same input | **VERIFIED** | tests/test_kb_one_validation.py |
| Graph: hierarchy, layouts, focus, legend, minimap, labels | **VERIFIED, one PARTIAL** | 11 of 11 tests pass, each in its own process. Tests 7 and 8 hang when run back to back in one process (a test-isolation defect; not seen in normal use). |
| Performance and memory | **VERIFIED** | every screen interactive in 0.26–0.74 s from a cold load; expand p95 48 ms; heap 6.0 → 9.6 MB over 50 graph openings (it was 9 → 165 MB) |
| Legacy code cleanup | **VERIFIED** | docs/LEGACY_REMOVAL.md has the evidence for each item; bundle 4,984,241 → 4,982,126 bytes; 19 dependencies |
| Connector interface, with the NP Autopilot sync behind it | **VERIFIED** | tests/test_kb_connectors.py; the sync test suites pass unchanged |
| Dev database and go-live rehearsal | **VERIFIED for the database steps, NOT DONE for the Vercel steps** | docs/GO_LIVE.md, "Rehearsal on dev"; the Vercel steps need a working token |
| Preview deploy (D2) | **BLOCKED (owner step)** | Token OK (API 200). Branch-scoped variables refused: "Project np-autopilot does not have a connected Git repository". No variable written, nothing deployed. |
| 10-minute memory session | **CUT** (allowed by the cut order) | replaced by the 50-opening heap check |
| Full suite | **VERIFIED: no new failures vs main** | Static + security spot checks PASS. Non-browser: 1,336 passed, 15 failed (13 in main's baseline; 2 docs checks fixed, 3/3 since). Browser, one file at a time: e2e 70/71 (the 1 passed alone; first run at 2.5 GB free), UI 29/34 → fixed (each test now closes its pages) → **34/34**, console 2/2, realtime 1/1, propagation 1/1, graph **11/11** one per process. Fit check PASS (1536×730 and 1920×1080). |

**Known limitations:**
- On the Graph page, group-by-type takes about 40 s on the first run with the test data. It's slow, not wrong.
- The 25-user load test and the 5,000-node benchmark were not re-run, per the memory rules.
- The old explorer's read paths in `web/lib/data.py` stay until production runs on kb (marked "remove after go-live" in LEGACY_REMOVAL.md).

## Legacy deletion (owner-approved): counts and restore

**Kept:** the current domains Full Stack, Backend Engineering, Frontend and Test Engineering. Once the duplicate legacy "Frontend" was gone, the sync renamed "Frontend (2)" back to "Frontend".

**Deleted**, with the same counts in the local copy and on DEV:
- 42 domains and 904 modules
- 3,844 relationships and 1,040 attachments
- 1,133 expertise links (the instructors stay)

No record was left without a parent.

**The sync never re-creates them.** Migration 0037 adds `kb.sync_exclusions`, which holds NP Autopilot's own legacy rule plus the 946 deleted ids. This is tested. NP Autopilot's old tables are untouched.

**Exports** (real data, gitignored): `backups/legacy_deleted_kb_realdata_*.json` (local) and `backups/legacy_deleted_supabase_*.json` (DEV).

**Restore:** `SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy_delete.py restore <export.json>`.

**Production:** GO_LIVE.md step 6. Not run.

## What each workstream delivered

- **B1, data flow:**
  - The "/" map reads kb through `npmap.py`, with the same response shapes as before.
  - Change kinds, and live updates everywhere.
  - Sync batches that resume where they stopped; the function limit (`maxDuration`) is 60 s.
  - People:
    - an e-mail on person records;
    - CSV upload with a match preview;
    - linking at sign-in;
    - claims;
    - "Owned by you".
  - Decisions applied:
    - "owner expected" per record type;
    - contributors' edits go to Approvals, enforced in the database;
    - the legacy domains still used as expertise are listed on Data quality.
- **B2, graph:**
  - One graph experience, built on `GET /api/kb/graph`.
  - Layouts: hierarchy, force, radial, saved positions.
  - Grouping and bundles.
  - Navigation: legend as filter, breadcrumbs, focus mode, search-jump, minimap, labels that never overlap, and a `?` shortcut sheet.
  - The same visual language on "/".
- **B3, UI:**
  - Every screen reviewed at 1280–2560 px in both themes.
  - 165 of 180 inline styles moved to classes.
  - AA contrast; the record page is one centred column.
  - Wording unified ("Links", "Program timeline").
- **B5, performance and QA:**
  - Data quality: 29 s → 0.05 s.
  - Edge indexes.
  - Guards on AI tokens and on the last admin.
  - Deterministic waits in the browser tests.
  - 17 audit findings fixed (docs/run6/AUDIT_FINDINGS.md).
- **Resume (F1–F7, G):**
  - IK brand and the one-screen dashboard; navigation fixes; Activity as sentences.
  - Members by invitation; the server-side IK check, headers and access sweep.
  - Legacy code cleanup, the memory-leak fix, and the connector interface.
  - Docs: README, VISION_AND_ROADMAP, GO_LIVE, PR_DESCRIPTION.

## Brand source

The source is interviewkickstart.com itself:
- **Colours and font:** the Elementor kit `wp-content/uploads/elementor/css/post-5.css`, whose `--e-global-color-*` variables give navy #324158, blue #3996D2, teal #00D1B4 and light #F0F3F6. The font is Inter.
- **Logo:** the header SVG, with fills #344158 and #3996D2, saved as `public/kb/brand/ik-logo.svg`.

The accent is #2670A6 in light mode (the brand blue darkened to 5.3:1 so it can carry text) and #3996D2 in dark mode (5.8:1). Details are in docs/DESIGN_SYSTEM.md, section "Brand".

## Security sweep

Full details: docs/run6/SECURITY_SWEEP.md.

- **Sign-in:** IK accounts only, re-checked on the server on every request: the KB API, the "/" map's routes and the change feed. A valid non-IK session gets 403; no session gets 401.
- **Route sweep:** every route was called as anonymous, a non-IK account, viewer, contributor, editor and admin, and each answered as designed. A new route fails the test until it is listed.
- **Database functions:** `authenticated` and `anon` can't run the owner-only SECURITY DEFINER functions.
- **Headers:** every response carries CSP, HSTS, nosniff, X-Frame-Options and Referrer-Policy. There's no CORS anywhere.
- **Cron secret:** compared in constant time; at least 24 characters.
- **MCP tokens:** hashed, valid for 1–365 days, revocable. They can't grant roles, link accounts or permanently delete.
- **No secret reaches the browser.**
- **Decisions:**
  - `/api/stats` stays public: counts only, exactly what the old static file showed.
  - No in-process rate limiter: it would limit nothing on serverless. Use a Vercel Firewall rule if one is needed.
- **Git history:** the secret scan in verify_all finds no secret-shaped strings, so there's nothing to rotate.

## Top 5 roadmap items

From docs/VISION_AND_ROADMAP.md §7.

1. Alerts for the sync and its schedule (stale, failed, conflict spike), sent to one channel. Value H, complexity L, 1–2 days.
2. A production backup check, a weekly kb dump, and a restore drill. Value H, complexity L, 2–3 days.
3. Schedule the intake: the Drive passes 0–4 and the projection in one worker, with the projection rewritten as a set-diff. Value H, complexity M, 5–8 days.
4. Namespace the sync per source: a connectors table, one lock per connector. Value M, complexity M.
5. A job table with retries and back-off, needed before any slow work such as extraction or embeddings. Value M, complexity M, 3–5 days.

## Updated 7-minute leadership demo (on :8766)

1. **Dashboard (1 min):** one screen with the numbers, what needs attention, and recent activity in plain sentences.
2. **Graph (1.5 min):** the hierarchy Program → Course → Domain → Module. Focus a domain, filter with the legend, and search to jump to a record.
3. **Live sync (1 min):** open "/" (NP Autopilot) next to it. Rename a module in /kb/: both update within seconds.
4. **Who teaches what and Program timeline (1 min):** the P and B1–B3 roles, taken from the mastersheet.
5. **Activity (1 min):** who changed what, from what to what; a sync run reads as one sentence.
6. **Settings → Members (0.5 min):** invite someone by IK e-mail before their first sign-in; the last admin can't be removed.
7. **Data quality (1 min):** records with no owner (only for types that need one), legacy expertise, conflicts. Finish on GO_LIVE.md.

## Action required from owner

In order, through to production.

1. **Vercel Preview variables** (the token is fine now):
   - Either connect the Git repository to the Vercel project (Settings → Git) so variables can be scoped to the branch `auto/knowledge-platform-20261102`; **first set the Production branch and an "Ignored Build Step"** so pushes to `main` do not auto-deploy Production. Or add the variables for **Preview (all branches)**: previews of this project only come from the CLI.
   - The names and values: docs/DEV_DEPLOY.md step 2 (`SUPABASE_JWT_SECRET` not needed: the dev project signs with ES256; `NP_SHARED_ACCOUNTS` optional). Then `bash scripts/deploy_dev_preview.sh --check`, then without `--check`. Preview only.
2. **Google sign-in for the preview:**
   - Add the branch URL as an authorised JavaScript origin.
   - On Supabase DEV: the Google provider, the before-user-created hook, and the URL configuration (DEV_DEPLOY.md, step 5).
3. **Make yourself admin on DEV:** sign in once on the preview, then run `ADMIN_EMAILS=<you>@interviewkickstart.com python pipeline/kb_admins.py` against DEV.
4. **Decide:** may a shared mailbox (from `NP_SHARED_ACCOUNTS`) hold an editor or admin role in the KB? See SECURITY_SWEEP.md.
5. **Decide:** keep access to "/" as it is today: any IK account with an NP role. Run 6 didn't change it.
6. **Decide:** whether to stop tracking these. Both stay in git history either way.
   - The older screenshots in docs/screenshots/, which likely show real names.
   - The large generated graph files, such as knowledge/merged_graph.json.
7. **Review and merge the PR** (docs/PR_DESCRIPTION.md).
8. **Production:** follow docs/GO_LIVE.md, including step 6, the **permanent legacy deletion**. It exports first, and the restore is tested. After that step, rollback means the export or the step-1 backup.
9. **After go-live:** remove the old-table read paths (marked "remove after go-live" in LEGACY_REMOVAL.md).

---

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
