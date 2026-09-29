# HANDOFF

**Written 2026-09-29 at the end of a long session, so a fresh one can resume
with nothing lost.** Every number below was measured when this was written, not
recalled.

---

# A · WHERE THINGS STAND

## Repository

| | |
|---|---|
| branch | `content-crawl-rowB` |
| HEAD | **`42af286`** |
| ahead of `origin/main` | **33 commits** |
| `git status` | clean |
| pushed? | **no** — nothing pushed, nothing merged |

## Verification, all green

| check | result |
|---|---|
| test suite | **559 passed**, 120 skipped, 0 failed |
| `pipeline/validate.py` | **0 FAIL**, 19 WARN, 20/27 categories exercised |
| `eval/content_eval.py` | **14/14**, 0 fabrications |
| `eval/content_eval_all.py` | **103/103**, 0 fabrications (§D2 excluded as unfailable) |
| `eval/mastersheet_rederive.py` | **0 unexplained differences** across 20 modules |
| `verify_migration.py --source supabase` | **54/54 VERIFIED** (against the LOCAL database) |
| `eval/drive_dom.mjs` | all checks passed |
| `pipeline/check_no_payroll_committed.py` | clean |

## LIVE IN PRODUCTION vs LOCAL ONLY

**Production (`np-autopilot.vercel.app`) is still the OLD system.** Nothing from
this session has been deployed or applied.

| | production today | local only |
|---|---|---|
| graph | 3,146 nodes / 4,021 edges, projected 2026-09-18 | merged public **8,507 / 42,741** |
| UI | the old bounded ~60-node overview | structure view, panels, matrix, timeline, filters |
| database | migrations through **0016** | local PostgreSQL 17 with **0017, 0018, 0019 applied** |
| connections | one per request | one per warm instance (cold-start fixes) |
| `/api/structure` | **404, does not exist** | serving 3,307 nodes / 4,970 edges |

`public/stats.json` still describes production (3,146 / 4,021) and was
deliberately not overwritten by local projections.

## Graph counts

| | nodes | edges |
|---|---:|---:|
| merged, public half | **8,507** | 42,741 |
| merged, full (incl. 28 `instructor_contact`) | 10,437 | 44,879 |
| **default structure view** | **3,307** | **4,970** |
| of which legacy modules, faded | 904 | |

---

# B · COMPLETED WORK

| work | commits |
|---|---|
| Drive-upload incident handled; `07-risks.md` R19 | (pre-session baseline) |
| Phase 0 — row B mapping, SD1–SD4, D2a drafted then approved | `b3add86`, `e358f8f` |
| Phase 1 — 21 guards written BEFORE the crawler, each mutation-verified; D1/D3/D4/D5/D6 enforced by tests | `b4e473c` |
| Phase 2 — the crawl: three runs, two filename-collision classes, file-id naming, binaries no longer decoded as noise, redaction v2 as a cache contract, integrity check made permanent, run summary durable | `3eaed24`, `2fa718f`, `65e1f26`, `bf205d8`, `405f9f9`, `b8d6341`, `c4b60bd` |
| Phase 3 — content model, sessions from the mastersheet, programme weeks, instructors un-deferred, contact data in the sensitive half only | `50e965c`, `0db1afa` |
| Phase 4 — completeness matrix, both evals, four guards repaired | `a4edaef`, `ffa3505` |
| `live_class` retired: 845 file-derived nodes that were never sessions | `0243e41` |
| MOD-01…16 merges | `9e202ce` |
| INS answers (individual) and the bulk of 26 | `c4450d6`, `a87f960` |
| PPL-11 (Bharath = Bharath Anand) and the Balaram Velaga alias | `f9b4c69`, `c4450d6` |
| B1 — one id minter, projection merge of the public half, coverage and staffing fixes, Types panel, landing stats, migrations 0017/0018 staged and proven | `99f768b`, `ad5c458`, `3edb8f7` |
| B2 — structure default view, faded legacy, instructor and module panels, matrix, timeline, filters, search badges, shareable URLs | `c603117`, `63df326`, `90c29f5` |
| B2.5 — 54/54 verification; migration 0019 (slide, tab, owner_domain, mime, evidence_kind) | `683fb9b` |
| one row per person with tier badges; the matrix load column | `683fb9b` |
| source links — Uplevel + Drive for every item; the mastersheet only as the citation | `f9b4c69` |
| perf baseline and measurement-script fixes (`--phase pre/post`, `--wait-for-enter`, 5 cold loads, authenticated timing) | `737c3a4`, `93b5db0`, `e7235ee`, `8f2ec96`, `c9dc329`, `65dd734` |
| **B3 cold-start investigation** | **`42af286`** |

## B3 cold-start findings (`42af286`) — the detail

- **Connection reuse.** One database connection per warm instance instead of one
  per request. Laptop→Seoul: **1,624 ms → 712 ms median (−64%)**.
  **Safety comes from the transaction-local state plus a `finally:` ROLLBACK,
  never a commit** — held by 8 tests, including *"an unidentified request after
  an identified one sees nothing"* and the error path clearing state.
- **Setup collapsed to one round trip.** `set_config(...)` and `SET LOCAL ROLE`
  merged into a single statement → **591 ms median** (~120 ms saved).
- **Lazy endpoint imports** in the router: **80.9 ms → 56.2 ms**. The dead
  `http.server` import removed from `api/session.py`. The guard-order regression
  this caused — an import running before `identify()` — was caught by a test,
  fixed and asserted.
- **Ruled out, no action:** bundle size after `excludeFiles` (**1.43 MB**),
  region (`icn1` is already co-located with Supabase `ap-northeast-2`).
- **Remaining cold-start premium** (first request on a new instance, still
  paying the connect): **1,131 ms** — the likely shape of the 5.5 s settled
  outlier.

---

# C · IN PROGRESS — B3

| item | state |
|---|---|
| cold-start investigation | **DONE** — `42af286` |
| precomputed layout | **not started** |
| columnar brotli payload for `/api/structure` | **not started** |
| ETag with private caching | **not started** |
| lazy panels | **not started** |
| `pg_trgm` search index | **not started** |

Nothing is half-written. The tree is clean and there is no WIP commit.

---

# D · NEXT PLAN — each step ends with a STOP for the owner

## 1 · Finish B3 (speed)
Precomputed layout; columnar brotli `/api/structure`; ETag + private caching;
lazy panels; `pg_trgm` index.

**Also:** verify the reused database connection recovers when the pooler or the
network drops it while idle — the next request must reconnect transparently
rather than fail. **Write a test that kills the connection between two
requests.**

Report LOCAL before/after against `docs/PERF-BASELINE.md`: settled time,
cold-start time, bytes per node, p50/p95 per endpoint.

## 2 · Exact-slide deep links
Google documents `https://www.googleapis.com/auth/drive.readonly` among the
accepted scopes for Slides API `presentations.get`, so **no scope widening is
needed**.

First check whether the Slides API is **enabled in the service account's Google
Cloud project**. If not: tell the owner exactly what to enable and where, and
**pause this item**. If enabled: report the call count (~238 native decks),
fetch page object ids, store `slide_number → page_object_id`, and link topics to
`/presentation/d/<id>/edit#slide=id.<page_object_id>`. `.pptx` and `.pdf` keep
the file link plus the slide/page number. Test: a topic from a native deck links
to its exact slide.

## 3 · B3.5 — UI features
Specified in full in **`docs/UI-BACKLOG.md`**. Display only, no new data, CSP
stays strict, self-hosted only. Header stat chips; type filter chips;
single-type view; focus mode; breadcrumb; module panel header; Files · Open
list; hint bar; one colour legend; and the explicit "do better than the B2B
version" list (no overlapping labels, generic names always with parent context,
grouped search with keyboard nav, URL-held state, readable dimmed nodes).

## 4 · Push and merge
Push `content-crawl-rowB` → show all four CI jobs green → merge into `main`
**only when green**.

## 5 · Phase C (database)
`pg_dump` of exactly the tables `project_graph.py` replaces, to a gitignored
path (report size and row counts) → apply **0017, 0018, 0019** to production
(`migrate.py status` before and after) → project the merged public half →
`verify_migration.py` and `curation.py check` → confirm the curation tables
(people, aliases, workflow owners, notes, audit) are untouched, with row counts
before and after.

## 6 · Owner acceptance
Regenerate `docs/ACCEPTANCE-CHECKLIST.md` — one block per module: domain,
programme week, sessions with links, instructors with roles, assignment, deck
count, top 5 topics with locators, every link. **The owner ticks each module
against the mastersheet. Phase D does not start until they confirm.**

## 7 · Phase D (deploy)
Deploy from a **`.git`-less `/tmp` copy** → verify `/api/config` 200,
`/api/me` and `/api/overview` 401 unauthenticated, `stats.json` counts, the
security headers, and `drive_dom.mjs` against the live site →
`measure_signed_in.py --phase post` (before/after against the baseline,
including a first-request-after-idle cold-start figure on the live `icn1`
function) → document rollback (restore from the Phase C backup, redeploy the
previous build) → tell the owner exactly what to click to see API Design's full
chain, the matrix and the single-type views.

## 8 · After launch — each its own phase
a. **Release 2, topic categories** — `config/topic-categories.yaml`, proposals
   only until confirmed. See `docs/UI-BACKLOG.md`.
b. **Release 2, tools/tech** — closed list in `config/tools.yaml`, new `tool`
   node type, `uses_tool` edge. D1 unchanged.
c. **`docs/EXTERNALLY-OWNED-FILES.md`** — 389 files, ONE list including the 185
   hyphen-domain files, owner domain shown (never an address), videos separate,
   grouped by domain and module, noting Drive cannot transfer ownership from a
   personal account.
d. **Shared export map** between pass 0 and the crawler — one native-type
   vocabulary with a per-pass rule table; tests for type parity and
   `[tab]`-marker count == xlsx tab count; add the Drive drawing → PDF entry.
e. **Plugin `/module` command** (e.g. `/module API Design`) answering the full
   chain with citations; bump `plugin.json`.
f. **Extend to other row-B domains** — scope change, re-run from Phase 2.

---

# E · OPEN REVIEW ITEMS AND PENDING OWNER DECISIONS

`docs/REVIEW-QUEUE.md` holds **86 rows**. Answered: MOD 16, INS 32, PPL-11.

| prefix | rows | state |
|---|---:|---|
| `MOD` | 16 | **all answered and applied** |
| `INS` | 32 | **all answered** (26 bulk + 6 individual) |
| `PPL` | 12 | **1 answered** (PPL-11); PPL-01/06 resolved via INS-31/32; **9 open** |
| `DCK` | 14 | **open** — deck filename → instructor proposals |
| `TOPv` | 3 | **open** — module label variants |
| `TOPm` | 3 | **open** — mastersheet vs folder label |
| `TOPt` | 6 | **open** — lesson-plan tab → module |

**Deliberately unresolved, by owner decision — do not "fix" these:**
- `INS-08` / `INS-30` — Bill Ogden / William David Ogden. Two nodes, rendered
  unconfirmed, hatched in the matrix.
- `INS-31` / `INS-32` — `Konstantinos`, `Shelby`. First-name forms keep their
  module rows.

Answer the remaining 35 before Phase C where possible.

**PENDING — billing decision, the owner's:** raising the Vercel function
`memory` setting buys proportionally more CPU, shortening interpreter start-up
and connection setup on cold starts. Proposed: one step up, measure the
cold-start premium before and after, keep it only if the gain justifies the
cost. **Not applied.**

---

# F · EVERY OWNER DECISION FROM THIS SESSION

All `origin: hand`, **Animesh Kumar, 2026-09-29**. Each was verified present in
the file named.

| decision | recorded in |
|---|---|
| D2a approved: row B only, SD1 Full Stack / SD2 Frontend / SD3 Backend / SD4 Test Engineering; rows A and C out of scope; P1/P2 (ratings) deferred | `docs/PRE-CRAWL-DECISIONS.md` |
| Folder `Week N` is LOCAL sequencing only; programme weeks come from curriculum docs or owner facts, never computed | `docs/PRE-CRAWL-DECISIONS.md`, `pipeline/lib/curriculum.py` (`ArithmeticWeekRefused`) |
| Programme weeks, explicit per module: Full Stack 9–13, Frontend 9–12, Backend 9–13, Testing 9–14 (after DSA 1–5 and Systems Design 6–8) | `config/out-of-corpus-facts.yaml` → `rowb-program-weeks` |
| Base versions current; Revamp 2024 / Q4 2024 / New Material Aug 2023 non-current (`superseded_by`); "Updated Content - Aug 2023" (SD3 Concurrency) stays ambiguous | `config/out-of-corpus-facts.yaml` → `rowb-revamp-base-is-current` |
| Resume files are fictional templates (redaction stays on) | `config/out-of-corpus-facts.yaml` → `rowb-resume-folders-are-fictional-templates` |
| Roland Kunkel is an instructor; 3 speaker-notes/solutions files included by Drive file id; learner content otherwise excluded | `pipeline/lib/content_scope.py` → `INCLUDE_DESPITE_LEARNER_RULE` |
| Practice problems are optional per module — shown as "not offered", never as a gap | `config/out-of-corpus-facts.yaml` → `practice-problems-are-optional` |
| Instructors un-deferred, from the Resource Collection Mastersheet only (D1 unchanged); roles primary / backup_1 / backup_2 / backup_3; `A/B` cells split into two people | `docs/CONTACT-DATA.md` §R, `pipeline/lib/mastersheet.py` |
| Contact-data reversal: all instructor-table columns ingested, but contact #, email and LinkedIn ONLY in the sensitive half (gitignored, admin-only via RLS when projected), never in a git-tracked file | `docs/CONTACT-DATA.md` §R |
| `label_not_contact` narrowed to email-shaped strings and `https?://` | `docs/CONTACT-DATA.md` §L, `db/migrations/0018_*` |
| MOD-01…16, including MOD-04 (legacy Full-Stack edges kept but unconfirmed) and MOD-15 (mapped to SD4/5's sessions) | `config/module-merges.yaml` |
| INS bulk of 26; INS-05/06 (Balaram Velaga canonical, Velega alias); INS-08/30/31/32 left unresolved | `config/instructor-identity.yaml` |
| PPL-11: `Bharath` = Bharath Anand; `Bharath` kept in `label_raw` | `config/instructor-identity.yaml` |
| Default view = the whole structure layer; legacy modules faded, not hidden; the no-programme legacy cluster labelled as such | `docs/DEFAULT-VIEW.md` D1/D2 |
| Source-links spec: every item shows all of its own links (Uplevel + Drive); the mastersheet only as the provenance citation; all IK staff have view access, so no access warnings | `docs/ACCEPTANCE-CHECKLIST.md`, `config/out-of-corpus-facts.yaml` → `ik-has-view-access-to-drive-and-uplevel` |
| **The matrix load column** (Primary / Backup, per node, never summed across unresolved identities) | `docs/DEFAULT-VIEW.md` **D4a** — *added while writing this handoff* |
| The speed plan, including the cold-start fixes | `docs/DEFAULT-VIEW.md` D3, `docs/PERF-BASELINE.md` |
| **The accuracy standard** (1 faithful to source; 2 nothing guessed; 3 re-derivation diff = 0; 4 owner acceptance before deploy) | **`docs/ACCURACY-STANDARD.md`** — *added while writing this handoff* |
| **The B2B-style UI features** (B3.5: single-type view, focus mode, files list, label and context improvements) | **`docs/UI-BACKLOG.md`** — *added while writing this handoff* |
| **Release 2: topic categories as graph nodes** (proposals until confirmed) | **`docs/UI-BACKLOG.md`** — *added while writing this handoff* |
| **Release 2: tools/tech as graph nodes** (closed curated list, `uses_tool`) | **`docs/UI-BACKLOG.md`** — *added while writing this handoff* |

**Five of these were NOT recorded anywhere before this handoff** — the last five
rows above. They existed only in conversation. They are recorded now.

---

# G · OPEN ISSUES AND RISKS (none are blockers)

- **`interview-kickstart.com` (hyphen): 185 files.** IT confirmation still
  pending. Included in the main externally-owned list by owner decision.
- **204 files owned by personal accounts** — content-continuity risk. Drive
  cannot transfer ownership from a personal account; the fix is an IK-owned
  copy.
- **49 download-disabled files** — metadata-only nodes, still linked, marked
  "view only". `docs/DOWNLOAD-DISABLED-FILES.md`.
- **The Drive-upload incident**: the database password was **NOT rotated**, by
  owner choice. The uploaded copies were moved out of the corpus folder.
- **R19/R20 numbering is unresolved.** `07-risks.md` R19 and
  `docs/CACHE-EXPOSURE.md` §0a both claim R19. Decide; do not leave two.
- **Registry drift**: the hardcoded registry in `count_registry.py` versus the
  live folder.
- **Registry row C is shared "anyone with the link"** — out of scope, but the
  sharing state is a finding.
- **~100 legacy "session rows wearing a module label"** (62 `… Class`, 37
  `… Assignment Review Class`, 1 `… Assignment`) — recorded in
  `config/module-merges.yaml` findings, not fixed.
- **724 of 922 legacy modules have no programme edge** — the default view puts
  them in one faded cluster labelled "Legacy — no programme recorded".
- **Cold starts**: ~1,131 ms first-request premium remains after the fixes; a
  5.5 s settled outlier was seen once. The `memory` decision is pending (§E),
  and the reused connection must be proven to survive idle drops (§D.1).
- **30 instructor labels were duplicated before the INS bulk; 4 remain**, all by
  owner decision.
- **`/api/structure` is unbounded by design** (3,307 nodes). It is parameterless
  so it cannot become an arbitrary-subgraph endpoint, but it IS a bulk download
  and the anti-bulk reasoning in `web/lib/data.py::overview` still applies to
  everything else.

---

# H · WORKING AGREEMENT FOR THE NEXT SESSION

- **Step by step. STOP after every phase.** Nothing pushed, projected, deployed
  or applied to production without the owner's explicit go-ahead.
- **Never print a secret or a token**, even partially. The measurement script
  reads the session token inside the page and it never reaches Python.
- **Ambiguity is returned, never guessed** (`lib/resolve.py`). **Thresholds rank
  or warn, never silently exclude** (`CLAUDE.md` §4).
- **Every owner decision is recorded** as `origin: hand`, with the owner's name
  and the date.
- **Verify by measurement, never by status output. Every check must be able to
  fail — mutation-test it.** This session found four checks that could not:
  eval C12, `q_instructor`, a vacuous ordinal test, and `verify_migration`
  comparing two things that already agreed.
- **Deploy only from a `.git`-less `/tmp` copy. Check the live URL, never
  `vercel ls`.**
- **Keep docs in sync with code**, and fix drift the moment it is found.

---

# I · KEY COMMANDS

```bash
# --- environment -------------------------------------------------------
set -a && . ~/.config/np-autopilot/env && set +a     # DB + Drive credentials

# --- pipeline ----------------------------------------------------------
python3 pipeline/00_fetch_drive.py                  # needs NP_DRIVE_SA_KEY
python3 pipeline/01_parse.py                        # 1..5 build the main graph
python3 pipeline/05_render_html.py
python3 pipeline/06_crawl_content.py                # row B crawl (Drive)
python3 pipeline/07_build_content_graph.py          # content graph, no network
python3 pipeline/08_merge_graphs.py                 # apply answered REVIEW-QUEUE rows
python3 pipeline/refresh.py                         # end-to-end refresh
python3 pipeline/validate.py

# --- evals and accuracy ------------------------------------------------
python3 eval/content_eval.py                        # 14/14
python3 eval/content_eval_all.py                    # 103/103, all 20 modules
python3 eval/mastersheet_rederive.py                # must be 0 differences
node   eval/drive_dom.mjs public/index.html

# --- database ----------------------------------------------------------
python3 pipeline/migrate.py status
python3 pipeline/migrate.py up
python3 pipeline/project_graph.py                   # public half only
python3 pipeline/project_graph.py --scope full      # REFUSES, by design
python3 pipeline/verify_migration.py --source supabase      # 54/54
python3 pipeline/verify_migration.py --freeze --scope full  # deliberate re-freeze
python3 pipeline/curation.py check

# --- generated docs ----------------------------------------------------
python3 pipeline/gen_acceptance_checklist.py
python3 pipeline/gen_csp_hashes.py                  # after ANY edit to index.html
python3 pipeline/gen_csp_hashes.py --check          # CI form

# --- performance -------------------------------------------------------
python3 eval/measure_signed_in.py --phase pre       # before the deploy
python3 eval/measure_signed_in.py --phase post      # after; /api/structure REQUIRED
python3 eval/measure_signed_in.py --phase pre --wait-for-enter

# --- local PostgreSQL (the B2/B3 workbench) ----------------------------
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
PGDATA=<scratch>/pgdata; PGSOCK=<scratch>/pgsock
initdb -D "$PGDATA" -U np --auth=trust
pg_ctl -D "$PGDATA" -o "-k $PGSOCK -h 127.0.0.1 -p 55432" -l <scratch>/pg.log start
psql -h 127.0.0.1 -p 55432 -U np -d postgres -c "create database np_b2;"
# the Supabase surface the migrations expect:
psql "$DSN" -c "create role anon; create role authenticated; create role service_role;"
psql "$DSN" -c "create schema if not exists auth;"
psql "$DSN" -c "create table if not exists auth.users (id uuid primary key default gen_random_uuid(), email text, raw_app_meta_data jsonb default '{}'::jsonb, raw_user_meta_data jsonb default '{}'::jsonb);"
psql "$DSN" -c "create or replace function auth.uid() returns uuid language sql stable as \$\$ select nullif(coalesce(nullif(current_setting('request.jwt.claims', true),'')::jsonb->>'sub',''),'')::uuid \$\$;"
psql "$DSN" -c "grant usage on schema public, auth to authenticated, anon;"
psql "$DSN" -c "grant select on all tables in schema public to authenticated;"
psql "$DSN" -c "grant execute on all functions in schema auth to authenticated, anon;"
DSN="postgresql://np@127.0.0.1:55432/np_b2"
SUPABASE_DB_URL_SESSION="$DSN" SUPABASE_DB_URL_TRANSACTION="$DSN" python3 pipeline/migrate.py up
SUPABASE_DB_URL_SESSION="$DSN" NP_LANDING_STATS=<scratch>/stats.json \
  NP_BUILD_LOG=<scratch>/BUILD_LOG.md python3 pipeline/project_graph.py
#  ^ ALWAYS redirect those two, or a local run overwrites public/stats.json

# --- screenshots (local harness; stubs ONLY guard.identify) ------------
SUPABASE_DB_URL_SESSION="$DSN" python3 eval/screenshot_views.py

# --- deploy (Phase D) ---------------------------------------------------
#  copy to /tmp WITHOUT .git, deploy from there, then check the live URL.
#  Never `vercel ls`.
```
