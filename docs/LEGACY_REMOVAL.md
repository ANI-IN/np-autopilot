# Legacy removal — run 6, F6 (code only)

Every legacy component in the repository: what it is, why it is legacy, what
replaces it, and the evidence for its status. **Legacy DATA is not in scope**
except for the prepared production step in §7. Base: the integrated run-6 HEAD
`36aad36` (B1, B2, B3, B5, R3, F1, F2, F3 merged). Cleanup commit: `036baf1`.

Status words: **REMOVED** (done in F6, with the evidence) · **AFTER GO-LIVE**
(keep until production reads kb, then remove) · **KEPT** (in use, or protected
by the rules below) · **ARCHIVED** (doc moved to `docs/archive/`).

Never removed, by rule: the pipeline intake (`pipeline/00_*`..`04_*`,
`project_graph.py`, `pipeline/lib/*`), the sync (`web/lib/kb/sync*.py`,
`legacy*.py`), migrations, eval servers and the helpers tests import, tests,
and anything production depends on.

How the evidence was taken: `git grep` against `36aad36` (the state before the
cleanup), so each result shows every use there was. "Deploy" means
`docs/DEPLOYMENT.md`, `docs/DEV_DEPLOY.md`, `vercel.json`, `.vercelignore` and
`.github/`; for every removed item:

```
$ for t in kb_screens grid-12 ownedByYouCard noOwnerSection onLiveFeed legend-line NEXT.md people.js live.js kb.css; do
    echo "$t: $(git grep -l "$t" 36aad36 -- docs/DEPLOYMENT.md docs/DEV_DEPLOY.md vercel.json .vercelignore .github)"; done
kb_screens:   grid-12:   ownedByYouCard:   noOwnerSection:   onLiveFeed:   legend-line:   NEXT.md:   people.js:   live.js:   kb.css:
```

(no deploy file names any of them).

---

## 1. Removed in F6

| # | Item | Why legacy | Replacement | Evidence of zero use (at `36aad36`) |
|---|---|---|---|---|
| R1 | `public/kb/kb.css`: `.grid-12`, `.span-2/3/4/6/12`, `.grid-12 > .card…`, the `@media (max-width:1180px)` rule for them | The dashboard's 12-column grid; F1 (`36aad36`) rebuilt the dashboard on `.dash-grid` / `.dash-tiles` / `.dash-cols` | `.dash-*` rules (kb.css), documented in DESIGN_SYSTEM.md (updated) | `git grep -nE "grid-12\|span-(2\|3\|4\|6\|12)\b" 36aad36 -- public tests eval scripts .github` → only kb.css itself and two `wait_for_selector("[data-testid=dashboard] .grid-12")` in `scripts/kb_guide_shots.py:36` and `scripts/kb_screens.py:82`, both waiting for an element F1 removed (they would time out). The first now waits for `[data-testid=dash-grid]`; the second is R6. |
| R2 | kb.css `.legend-line` | Graph legend swatch from run 3; B2's legend draws shapes (`.legend-shape`) and line styles inline | `.legend-shape`, `.legend-item` | `git grep -n legend-line 36aad36 -- public tests eval scripts` → `public/kb/kb.css:437` only. `git log -S legend-line -- public` → added `00e4abb`, last use removed `b939513` (B2). |
| R3 | kb.css `.type-col`, `.bar.w-120`, and the `.menu .menu-item` selector (the `[role=menuitem]`/`[role=option]` parts of the same rule stay) | Leftovers of earlier layouts | — (nothing renders them) | `git grep -nE "type-col\|w-120\|menu-item" 36aad36 -- public tests eval scripts` → kb.css only (a `type-colors` test id is a different word). A scan of every class in kb.css and graph.css against every `.js`/`.html` under public/ (vendor excluded), eval/ and tests/, including `'prefix-' +` concatenations, found these and two utilities kept on purpose: `.mt-4` (the `.mt-1..5` scale) and `.sr-only` (accessibility utility). |
| R4 | `public/kb/js/views/people.js`: `ownedByYouCard()` | The dashboard card "Owned by you"; F1 moved it into `views/dashboard.js` (one `/dashboard` request, account linking once per session) and stopped importing it | `views/dashboard.js` "Owned by you" block (`data-testid=owned-by-you`); a claim ("This is me") is still made from the record panel (`detail.js:178`, `POST /claims`) | `git grep -nw ownedByYouCard 36aad36 -- public tests eval scripts mcp_server plugins` → `people.js:8` (comment) and `people.js:111` (definition) only. `git log -S ownedByYouCard -- public/kb/js/views/dashboard.js` → `36aad36` (the import removed). |
| R5 | `people.js`: `noOwnerSection()` | Written in B1 (`98627ed`) and never imported: no version of `views/quality.js` ever contained it | Data quality's "Records without an owner" list (`q.unowned`) and the "No owner" count; the API `GET /api/kb/quality/no-owner` **stays** (tests/test_kb_propagation.py:305 uses it) | `git grep -nw noOwnerSection 36aad36 -- public tests eval scripts` → `people.js:12` (comment), `people.js:152` (definition). `for c in 98627ed 4e0694a 1b218fc 0fb18f4 6f4f968 c241c3b; do git show $c:public/kb/js/views/quality.js \| grep -c noOwnerSection; done` → 0 every time. |
| R6 | `public/kb/js/live.js`: `onLiveFeed()` and its `feedListeners` list | A subscription hook B1 added that no page subscribed to | `onLiveChange()` (every page uses it) | `git grep -nwE "onLiveFeed\|feedListeners" 36aad36 -- public tests eval scripts` → `live.js:20,27,46` only (definition and the loop that called the empty list). |
| R7 | `scripts/kb_screens.py` (107 lines) | **Duplicated helper** (one of three screen sweepers: `scripts/kb_screens.py` run 3, `eval/kb_screens.py` and `eval/kb_ui_sweep.py` run 6). It was demo-only (hard-coded port 8765 and demo password), covered 15 of today's 23 screens, and was already broken: it waited for `.grid-12` (R1) | **Decision:** `eval/kb_screens.py` stays as the screenshot + console tool (the lead's after sets; CLI unchanged) and `eval/kb_ui_sweep.py` stays as the layout sweep (any local server, 23 screens, themes, layers). The two checks only the old script had, *elements past the right edge* and *controls overlapping*, and its `--dpr` option were ported into `eval/kb_ui_sweep.py` (`edge`, `overlap` in its report) | `git grep -n kb_screens 36aad36 -- tests scripts eval .github api web pipeline vercel.json` → its own docstring, `eval/kb_screens.py:7` (a different file's usage line), and `scripts/verify_all.sh:125,127` (the ruff file list; updated). No test imports it. History docs that mention it (`HANDOFF.md:413,549`, `docs/INVENTORY.md:164`, run-3 records) are history and were not edited: use `python eval/kb_ui_sweep.py --base http://localhost:8765 --email <demo admin> --password <demo password> --widths 1280,1536,1920,2560,3840 --dpr 1,2` instead. |
| R8 | `NEXT.md` → **ARCHIVED** to `docs/archive/NEXT.md` (pointer on its first line) | The 2026-09-10 handover list; its first item (pass 0, Drive) is live (CLAUDE.md "pass 0 is live as of 2026-09-16") and the order of work now lives in `docs/ROADMAP.md`, `HANDOFF.md`, `docs/HANDOFF.md` | those three | No code reads the file: `pipeline/01_walk_corpus.py:51` names it in `OWN_DOCS` (a set of names the corpus walk skips; harmless if absent) and `tests/test_cache_is_not_corpus.py:14`, `pipeline/00_fetch_drive.py:563` mention it in comments. `.vercelignore` excludes `*.md`, so the deploy never shipped it. |

No test was removed or weakened. No test covered R1–R7 (grep above).

## 2. Remove after go-live (production reads kb; keep the switch until then)

B1 moved every `/` map route to kb (`web/lib/kb/npmap.py`) behind the rollback
switch `NP_MAP_SOURCE=old` (docs/ARCHITECTURE.md "Rollback"). The old-table
code below is the rollback path. **Kept now**; remove in one change after
production has run on kb and the owner signs off.

| Item | Old-table reader | Kept because | After go-live |
|---|---|---|---|
| `npmap.enabled()` and each route's `_src()` switch: `api/structure.py:21`, `overview.py:20`, `node.py:11`, `search.py:11`, `neighbourhood.py`, `staffing.py`, `coverage.py`, `me.py:27`; `/api/stats`'s 404 branch in `api/index.py` | — (the switch) | rollback | call `npmap` directly; drop `NP_MAP_SOURCE` |
| `web/lib/data.py` read functions: `search`, `node`, `neighbourhood`, `overview`, `provenance`, `structure`, `structure_etag`, `node_detail`, `coverage`, `domain_subgraph` | nodes, edges, node_sources, node_layout, files, projection_meta | the `old` path; tests `test_web_data_layer.py`, `test_structure_payload.py`, `test_client_adapters_lose_nothing.py`, `test_search_holds_back_topics.py` cover them (`git grep -lE "data\.(search\|node\|…)\(" -- tests`) | remove with those tests, in the same change (a test for removed code goes with it) |
| `data.py` **stays** in part: `request_connection` (+`_warm_connection`, `_begin`, `_discard`, `_reset_or_discard`, 56 call sites: every route and the KB), `pack_structure`, `STRUCTURE_FORMAT`, `STRUCTURE_TYPES`, `DEFERRED_TYPES`, `MAX_DEPTH`, `DepthExceeded`, `OVERVIEW_RELS` (and `_overview_spec`, which computes it) | — | `npmap.py:47-54,359,375,468` imports them; it keeps data.py's wire format | move them next to npmap or leave them |
| `public/stats.json` and `pipeline/gen_landing_stats.py` | nodes | the landing page falls back to it (`public/index.html:3550`); written by `pipeline/project_graph.py:531` (intake, protected) | stop writing it in project_graph, delete the file and the fallback |
| `tests/test_kb_propagation.py`'s `NP_MAP_SOURCE` cases | — | prove the switch | remove with the switch |

## 3. Kept: in use, or protected

| Item | Why it is not removed (evidence) |
|---|---|
| `public/index.html` (the `/` map, 4,415 lines): 2D map, 3D view, curation UI, old `#/node/<id>` links | In use: it is the NP Autopilot map; it already rewrites an old `#/node/<id>` link to the query-string form (`index.html:3710-3711`, kept). Its curation UI writes the intake (`api/aliases.py`, `api/curate.py` → `web/lib/curation_service.py`: the one recorded exception in docs/ARCHITECTURE.md). |
| `public/vendor/cytoscape.min.js` | loaded by `public/kb/js/views/graph.js:55` |
| `public/vendor/np3d.min.js` (+ `eval/build_np3d.sh`, `eval/np3d-ngraph-stub.js` that build it) | loaded by `public/index.html:4157` (the 3D view, the map's default); tests/test_default_view_labels.py |
| `public/vendor/lucide-sprite.svg` | `core.js:49`, `graph/style.js:165` |
| `public/vendor/inter/` | `kb/index.html:8` (preload), `kb.css:7` |
| `public/kb/guide/*.png`, `public/kb/brand/ik-logo.svg` | every image is referenced by `public/kb/guide.md`; the logo by `kb/index.html` |
| Exported-but-internal JS (`app.js loadPeople`, `core.js saveSession`, `detail.js linkRow`, `graph/map.js mapLook`, …) | each is used inside its own module; `realtime.js realtimeActive` is used by tests/test_kb_realtime.py:75 |
| Python dependencies (requirements.txt, 15 entries) | every one is imported: `openpyxl` (8 files), `python-docx` (`pipeline/01_walk_corpus.py:116`, `lib/extract_text.py:87`), `PyYAML` (`03_resolve.py`, `04_build_graph.py`, …), `python-pptx`/`PyMuPDF` (2 files each), `google-api-python-client` (6), `google-auth` (`google.oauth2` in `00_fetch_drive.py:89`, `count_registry.py`, `kb_import_sheets.py`), `psycopg` (29), `PyJWT` (`web/lib/auth.py:97`), `Brotli` (3), `numpy` (`pipeline/lib/layout.py`), `mcp`/`httpx` (`mcp_server/kb_server.py`), `pytest` (96), `playwright` (19). Command: `grep -rnE --include=*.py "^\s*(import\|from) <module>(\.\| \|$)" .` per module. |
| Function dependencies (pyproject, 4) and uv.lock (11 packages: those 4 and their transitive cffi, cryptography, psycopg-binary, pycparser, typing-extensions, tzdata, plus the project) | the function imports all four (pyproject comments); a test asserts the pins match requirements.txt |
| Feature flags: `NP_MAP_SOURCE` (§2), `KB_SYNC_ENABLED`, `KB_SYNC_SECRET`, `KB_SYNC_BUDGET_SECONDS`, `KB_REALTIME_ORIGIN`, `NP_ALLOWED_HD`, `NP_SHARED_ACCOUNTS`, `NP_AS_OF`, `NP_BUILD_LOG`, `NP_CORPUS_PATH`, `NP_DRIVE_CONFIG` | all read by live code (`grep -rhoE "environ(\.get)?\(?\[?[\"'][A-Z_]+" api web pipeline/lib`); none is a dead toggle |
| API routes (`READ_NAMES`, `curate`, `/api/config`, `/api/session`, `/api/stats`, `/api/cron/kb-sync`, `/api/kb/*`) | every one has a caller (the map, the KB, pg_cron, the MCP server); tests/test_lazy_route_table.py |
| Python helpers with a single reference (only their definition): `web/lib/kb/sync.py::_rec_content`; `pipeline/lib/paths.py` `PIPELINE_DIR`, `PEOPLE_FILE`, `relative_to_corpus`; `pipeline/lib/redact.py::_bare_run`; `pipeline/lib/sources.py::PERSON_SOURCES`; `pipeline/lib/taxonomy.py` `seniorities`, `validate_rules` | **protected** (sync and pipeline/lib). Listed for the sync/pipeline owner; not touched. No other unreferenced top-level def exists in `web/lib/`, `web/lib/kb/` or `api/` (scan: every `def`/CONSTANT counted across `*.py *.js *.html *.sh *.yml`). |
| `config/*.yaml` (24 files) | all read by the pipeline intake or the sync (`kb-projection-mapping.yaml` by `npmap.py` and `sync.py`); `drive.yaml.example` is the operator template for `NP_DRIVE_CONFIG` |
| eval/ (servers, `kb_parity.py`, `kb_realdata_*`, `kb_sync_proof.py`, `local_server.py`, `mastersheet_*`, `measure_*`, `check_3d.py`, `drive_*.mjs`, fixtures) | imported by tests or named by `verify_all.sh` / ci.yml; operator tools (`kb_fit_check.py` F1, `kb_screens.py`, `kb_ui_sweep.py`, `content_eval*.py`, `screenshot_views.py`) are local-only, never deployed (vercel.json `excludeFiles`, `.vercelignore`), and documented in their docstrings or HANDOFF |
| `docs/run6/b2-map.patch`, `docs/run6/patches/` | records of patches the lead applied in Phase C; history |
| `knowledge/*` (graph.json, graph.html, …) | pipeline outputs (`04_build_graph`, `05_render_html`), excluded from the deploy; intake |

## 4. Docs

| Doc | Status | Why |
|---|---|---|
| `NEXT.md` | ARCHIVED (R8) | superseded handover list |
| `docs/DESIGN_SYSTEM.md` | updated | the Tile row and the dashboard grid paragraph described `.grid-12`/`.span-2` (R1) |
| `docs/DECISIONS.md`, `HANDOFF.md`, `docs/HANDOFF.md`, `BUILD_LOG.md`, `PROGRESS.md`, `docs/STATE.md`, `docs/AUDIT.md`, `docs/A7B.md`, run reports (`docs/run6/*`, `docs/MIGRATION_REPORT.md`, `docs/PARITY_REPORT.md`, `docs/TEST_RESULTS.md`, `docs/PERF-BASELINE.md`, `docs/LATENCY-MEASUREMENT.md`) | KEPT | decision records and history: never archived or deleted |
| `docs/HISTORY-REWRITE-PLAN.md` | KEPT | DECISIONS.md:20 lists it as "PLANNED, NOT RUN" (still open) |
| `docs/UNTRACKING-GRAPH-JSON.md` | KEPT | `knowledge/graph.json` is still tracked (`git ls-files knowledge/graph.json`), so the costing is still current |
| `docs/ONE-APP-OR-TWO.md` | KEPT | the decision `docs/DEPLOYMENT.md:3` cites |
| `docs/NEXT-PHASE.md`, `docs/UI-BACKLOG.md` | KEPT | owner plans referenced by docs/HANDOFF.md as open items |
| `01-…10-*.md` (design-phase docs) | KEPT | cited by pipeline code and DECISIONS |
| `docs/GO_LIVE.md` | **missing** | `pipeline/kb_legacy_delete.py` refuses production with "see docs/GO_LIVE.md (legacy deletion step)", and the file does not exist. §7 below is that step until the lead writes GO_LIVE.md. |

## 5. Redirects for old addresses

**No server path and no KB page was removed in run 6.** Checked: `git log
--diff-filter=DR --name-status` over the whole history (the only deletions are
`public/kb/kb.js` in run 2, whose routes all still exist, and the run-0
`web/api/*` move); every `ROUTES` key since run 5 (`9a739f9`) is still in
`public/kb/js/app.js`; `api/index.py`'s route set is unchanged since run 5
apart from the added `/api/stats`. What run 6 did change is page NAMES
("Resources" → "Links", "Programme timeline" → "Program timeline", F2) and
People moved into Settings (B1), so a typed or bookmarked `#/links` or
`#/people` landed on "Page not found".

`public/kb/js/aliases.js` (new; no DOM, so a test can run it with node) maps
those to their pages, and `route()` in app.js calls `location.replace()` before
it looks up `ROUTES` (the old address does not stay in the history; the query,
e.g. `?open=<id>`, is kept):

| Old | New |
|---|---|
| `#/links` | `#/resources` |
| `#/people` · `#/members` · `#/sync` · `#/tokens` | `#/settings?tab=people` · `members` · `sync` · `tokens` |
| `#/reviews` | `#/approvals?tab=reviews` |
| `#/dashboard` | `#/` |
| `#/program-timeline` · `#/programme-timeline` | `#/timeline` |
| `#/who-teaches-what` | `#/teaching` |
| `#/record/<id>` | `#/r/<id>` |

`#/proposals` was already an alias in ROUTES and stays. The map's old
`#/node/<id>` links are already rewritten by `public/index.html` (kept).

Tests: `tests/test_kb_redirects_run6.py` — one case per alias (it lands on a
page that exists, Settings/Approvals tabs included), no alias shadows a page,
the router redirects before the lookup with `replace`, the resolver run with
node (skipped without node), and for the server: every pre-run-6 server path
is still routed (405 for the wrong method, never 404), an unknown path is a
404 listing the endpoints, and `/`, `/kb/` and `public/stats.json` are still
shipped.

## 6. Bundle size and dependency count

Measured with `scripts/deploy_bundle_size.py` (new): tracked files of a git
revision under the deploy's roots, `api/`, `web/`, `pipeline/lib/` +
`pipeline/__init__.py`, `config/`, `public/` (vercel.json's static output and
the function's import reach, per `.vercelignore`'s header and
tests/test_deploy_guard.py), with `.vercelignore` applied (`*.md` except
README.md and `public/kb/guide.md`; `pipeline/*.py` except `__init__.py`).

```
python scripts/deploy_bundle_size.py --rev 36aad36    # before
python scripts/deploy_bundle_size.py --rev 036baf1    # after
```

| | Before (`36aad36`) | After (`036baf1`) |
|---|---|---|
| Files shipped | 130 | 131 (+`aliases.js`) |
| Bytes shipped | 4,984,241 | 4,982,126 (−2,115) |
| of which public/ | 48 files, 4,017,148 B | 49 files, 4,015,033 B |
| api/ · web/ · pipeline/lib/ · config/ | 14 · 21 · 23 · 24 files (77,897 · 461,394 · 228,727 · 199,075 B) | unchanged |
| Python: requirements.txt entries | 15 | 15 |
| Python: function (pyproject) · uv.lock packages | 4 · 11 | 4 · 11 |
| Vendored JS/asset libraries | 4 (cytoscape, inter, lucide, np3d) | 4 |
| **Dependencies** (requirements + vendored) | **19** | **19** |

The bundle barely moves because nothing big was dead: the 1.5 MB np3d bundle
and the 0.4 MB Cytoscape are both loaded. The large wins are AFTER GO-LIVE
(§2: roughly 450 lines of data.py read paths, the switch, stats.json) and in legacy
DATA (§7). scripts/ and eval/ are not shipped, so R7 and R8 do not change the
numbers.

## 7. Production permanent delete of the legacy DATA (prepared, NOT run)

Tooling from R3: `pipeline/kb_legacy_delete.py plan|delete|restore`, rules in
`web/lib/kb/legacy_delete.py`, migration **0037** (`kb.sync_exclusions`: the
sync never re-creates a deleted legacy domain or module). It deletes every
domain other than the four current ones and every legacy module; with them, by
cascade, their relationships, attachments, tags, saved positions and
legacy-archive rows. Records inside a deleted record are detached and flagged
for Data quality, never deleted. The old tables (`public.*`) are not touched.

Local real-data counts for reference (not production's): **946 records (42
domains, 904 modules), 3,844 relationships, 1,040 attachments, 1,133 expertise
links.**

Steps, for the owner and the lead, on production, in a maintenance window:

1. **Preconditions.** Production runs on kb (§2 switch unset), migration 0037
   applied (`pipeline/migrate.py status` shows it), a fresh database backup
   taken (DEPLOYMENT.md), the scheduled sync paused (`KB_SYNC_ENABLED=false`, web/lib/kb/sync.py:424) so
   no run lands mid-delete.
2. **Plan (no change):**
   `SUPABASE_DB_URL_SESSION=<production session URL> NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION=yes python pipeline/kb_legacy_delete.py plan`
   → counts only. Compare with the local reference above; the owner approves
   the numbers (a large difference is a stop).
3. **Delete:** the same command with `delete`. It writes the export to
   `backups/legacy_deleted_<db>_<date>.json` (gitignored: real data), reads it
   back, refuses if it does not hold every record, then deletes in one
   transaction and prints the counts and the export path.
4. **Check:** Data quality lists the detached records and lone links; the map
   at `/` and the Graph page show no legacy domains or modules; turn the sync
   back on and run "Sync now": it must re-create nothing (0037).
5. **Undo, if needed:** `… python pipeline/kb_legacy_delete.py restore backups/legacy_deleted_<db>_<date>.json`
   puts every row back with the same ids and switches the exclusions off.
6. Unset `NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION` afterwards. Keep the export
   file off the repo (it is gitignored) and in the owner's backup store.

The tool refuses production without `NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION=yes`
(`db.production_reason`), and no run of this repository sets it.
