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
| test suite, no database (what CI sees) | **581 passed**, 130 skipped, 0 failed — 2026-09-30, after step 0 (was 559 / 120) |
| test suite, local Supabase stack (§I) | **699 passed, 2 FAILED**, 10 skipped — the 2 are real migration gaps, §G; 7 skips are `production_only` |
| `pipeline/validate.py` | **0 FAIL**, 19 WARN, 20/27 categories exercised |
| `eval/content_eval.py` | **14/14**, 0 fabrications |
| `eval/content_eval_all.py` | **103/103**, 0 fabrications (§D2 excluded as unfailable) |
| `eval/mastersheet_rederive.py` | **0 unexplained differences** across 20 modules |
| `verify_migration.py --source supabase` | **54/54 VERIFIED** (against the LOCAL database) |
| `eval/drive_dom.mjs` | all checks passed — **hosted build only.** From B2.5 (`683fb9b`) the offline `knowledge/graph.html` threw (`taughtRows is not defined`); CI caught it on the first branch push. Fixed 2026-09-30 by scoping the B2 block to the hosted build, with an assertion that the offline build lacks those functions. Both builds pass since |
| `pipeline/check_no_payroll_committed.py` | clean |

## LIVE IN PRODUCTION vs LOCAL ONLY

**Production (`np-autopilot.vercel.app`) is still the OLD system.** Nothing from
this session has been deployed or applied.

| | production today | local only |
|---|---|---|
| graph | 3,146 nodes / 4,021 edges, `projected_at` **2026-09-20 11:00:22Z** (see below) | merged public **8,507 / 42,741** |
| UI | the old bounded ~60-node overview | structure view, panels, matrix, timeline, filters |
| database | migrations through **0016** | local Supabase stack with **0017–0020 applied** |
| connections | one per request | one per warm instance (cold-start fixes) |
| `/api/structure` | **404, does not exist** | serving 3,307 nodes / 4,970 edges |

`public/stats.json` still describes production (3,146 / 4,021) and was
deliberately not overwritten by local projections.

**Production's `projected_at` is 2026-09-20, not 2026-09-18** as this table
first said. Read 2026-09-29 from `projection_meta` in a read-only transaction:
same counts (3,146 / 4,021 / 30,658 sources), re-projected at 16:30 IST on
2026-09-20 — between two commits of that day's session, **before this
branch's merge-base (2026-09-21)**, so nothing in the row-B work touched it.
Cause not recorded; it is the shape of a test-suite run with production's env
loaded (`test_db_migration_verification` re-projects), which is exactly the
hazard §I now refuses.

## Graph counts

| | nodes | edges |
|---|---:|---:|
| merged, public half | **8,507** | 42,741 |
| merged, full (incl. 28 `instructor_contact`) | 10,437 | 44,879 |
| **default structure view** | **3,307** | **4,970** |
| of which legacy modules, faded | 904 | |

**3,307 / 4,970 is the one structure-view figure**, re-measured 2026-09-30 two
ways that agree: `web/lib/data.py::structure()` on the local projection, and
the same type filter over `knowledge/merged_graph.json`. `DEFAULT-VIEW.md`'s
3,355 was correct when measured, before the MOD, INS and PPL-11 merges absorbed
48 nodes; `PERF-BASELINE.md`'s 3,308 was copied from a B2 comment written
before PPL-11 (the comment, in `public/index.html`, still says 3,308 — it sits
in a CSP-hashed inline script, so it is corrected with B3's next edit there).

---

# B · COMPLETED WORK

| work | commits |
|---|---|
| Drive-upload incident handled; `07-risks.md` R20 (first written as R19) | (pre-session baseline) |
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
Push `content-crawl-rowB` → show all four CI jobs green **on the branch's own
run** → merge into `main` **only when green**. Main's current red is the known
pre-existing failures (owner ruling 2026-09-30, §G), not the bar. The push
itself is refused while the repository is public (R21).

## 5 · Phase C (database)
`pg_dump` of exactly the tables `project_graph.py` replaces, to a gitignored
path (report size and row counts) → apply **0017, 0018, 0019, 0020** to production
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
function) → **run the `production_only` tests against production, read-only**:

```bash
set -a && . ~/.config/np-autopilot/env && set +a
NP_ALLOW_PROD_TESTS=1 python3 -m pytest tests -m production_only -rs
```

They are the 7 tests that assert on production's own rows (real Google
identities, the live projection vs `public/stats.json`). Each runs under
`default_transaction_read_only=on`, verified before it starts
(`tests/db_guard.py`), so a write fails the test instead of landing. **Only
with `-m production_only`**: the opt-in lifts the refusal for the whole suite,
and the rest of it writes. The auth/RLS tests need no production run — they
already run against Supabase's real stack locally (§I), not a shim. **Expect
`test_the_landing_page_describes_the_projection_not_the_pipeline_graph` to
fail after Phase C**: it asserts `stats.json` nodes `< 5048`, and the merged
public half is 8,507 — fix that assertion in Phase C, before this run.
→ document rollback (restore from the Phase C backup, redeploy the
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

`docs/REVIEW-QUEUE.md` holds **86 rows: 51 answered, 35 open.** Answered = the
owner has decided the row, "leave unresolved" included (convention stated at
the top of `REVIEW-QUEUE.md`, same in both files).

| prefix | rows | state |
|---|---:|---|
| `MOD` | 16 | **all answered and applied** |
| `INS` | 32 | **all answered** (26 bulk + 6 individual) |
| `PPL` | 12 | **3 answered** — PPL-11 applied; PPL-01/06 left unresolved with INS-31/32; **9 open** |
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

**R21 — the GitHub repository was PUBLIC from creation (2026-09-17) for 13
days**, found 2026-09-29 before a push. **Private, verified 2026-09-29
19:06:50Z** (anonymous 404, authenticated `private: true`); last seen public
18:58:55Z. **81 clones were external** (owner: nobody on our side cloned
or pulled), so the disclosure question is escalated alongside R18's. No copy
found in Software Heritage or the Wayback Machine (checked read-only).
Recorded in `07-risks.md` R21, with the disclosure question left to the owner.
**Nothing is pushed until `pipeline/check_repo_private.py` passes** — CI's
`secrets` job runs it first, and `.githooks/pre-push` refuses the push.

**Found 2026-09-29 by the first run of the DB tests against Supabase's real
stack — both are the migrations relying on the environment, and both fail
`tests/` today:**

- **`auth_hook_refusals` has RLS disabled — in production too**
  (`relrowsecurity = false`, read-only check). Migration 0016 creates it
  without `enable row level security`. Not exposed today: `anon` and
  `authenticated` hold no privilege on it in production, and it has 0 rows.
  `test_rls_is_enabled_on_every_table` fails.
- **The migrations do not stop `anon` executing the sign-in hook.** 0007
  revokes EXECUTE from `anon`, `authenticated` but not from `PUBLIC`.
  Production's function ACL happens to carry no `PUBLIC` grant; a fresh apply
  on Supabase's own image does (`=X/postgres`). Safe in production by
  environment, not by migration. `test_the_hook_is_callable_by_the_role_gotrue_uses`
  fails.
- **Fixed by migration 0020 — written and tested LOCALLY only** (owner approval
  2026-09-30). RLS on `auth_hook_refusals` with one insert policy for
  `supabase_auth_admin`; EXECUTE on the hook and `_hook_pick` revoked from
  PUBLIC, anon, authenticated and service_role, granted to
  `supabase_auth_admin` only. Up, down and up again on the local stack; both
  failing tests green; new tests call the hook AS `supabase_auth_admin` under
  RLS (allow, and refuse-with-recorded-row) and as each client role (denied).
  The down restores production's pre-0020 ACLs, never the fresh-apply PUBLIC
  grant. **Goes to production in Phase C with 0017–0019.**

- **`interview-kickstart.com` (hyphen): 185 files.** IT confirmation still
  pending. Included in the main externally-owned list by owner decision.
- **204 files owned by personal accounts** — content-continuity risk. Drive
  cannot transfer ownership from a personal account; the fix is an IK-owned
  copy.
- **49 download-disabled files** — metadata-only nodes, still linked, marked
  "view only". `docs/DOWNLOAD-DISABLED-FILES.md`.
- **The Drive-upload incident**: the database password was **NOT rotated**, by
  owner choice. The uploaded copies were moved out of the corpus folder.
- **R19/R20 numbering — RESOLVED 2026-09-30.** The Drive-upload incident is
  `07-risks.md` **R20**; `docs/CACHE-EXPOSURE.md` §0a keeps R19 for the
  folder-visibility question.
- **`07-risks.md` R20 disagrees with this file on two facts, not reconciled
  here because only the owner knows them:** it says both uploaded artefacts
  were *still present* 2026-09-29 and that the password rotation was *stated as
  done* 2026-09-28; the incident bullet above says the copies were moved out and the password was
  NOT rotated. Re-list the folder read-only and record which is current.
- **CI has been red on `main` since at least 2026-09-20** — `test`, `payroll`
  and `secrets` fail, `renderer` passes; no successful run in the last 40.
  **Owner ruling 2026-09-30 (Animesh Kumar, origin: hand):** §D.4's "all four
  jobs green" applies to the **`content-crawl-rowB` branch's own CI run**;
  main's red state is the known pre-existing failures this branch fixes.
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
- **Never push without the visibility check passing** (R18, R21):
  `git config core.hooksPath .githooks` once per clone makes it automatic.
- **Keep docs in sync with code**, and fix drift the moment it is found.

---

# I · KEY COMMANDS

```bash
# --- once per clone ----------------------------------------------------
git config core.hooksPath .githooks      # pre-push refuses a public repo (R21)
python3 pipeline/check_repo_private.py   # the same check, by hand

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

# --- the local database: Supabase CLI stack (tests, B3, screenshots) ---
#  Supabase's own images — Postgres 17.6.1.171 (production: 17.6), GoTrue
#  v2.197.0, Supavisor transaction pooler on 6543 — so auth, roles and RLS
#  behave as in production. Its DATA is not production's. Config: db/local/.
colima start                                       # Docker, if not running
db/local/setup.sh                                  # start, migrate, project, seed
db/local/setup.sh --stop                           # data kept in the volume
#  CLI pinned in setup.sh: supabase@2.118.0 (via npx, no global install)
LOCAL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"   # fixed local default

# --- running the tests SAFELY ------------------------------------------
python3 -m pytest tests -q         # DB tests go to the local stack if it is up,
                                   # and skip if it is not
#  NEVER load ~/.config/np-autopilot/env before pytest: that env IS production,
#  and the DB tests insert, delete and re-project. tests/conftest.py refuses a
#  production DSN (Supabase host or project ref) with a usage error unless
#  NP_ALLOW_PROD_TESTS=1 — and that opt-in is for Phase D's read-only
#  production_only run ONLY (§D.7):  pytest tests -m production_only
#  The report header's first line says which database the run used.
#  Other targets: NP_TEST_DSN / NP_TEST_DSN_TRANSACTION (still refused if prod).
#  Every run ends with "skips by reason (N)". CI enforces tests/ci-skips.yaml
#  (NP_SKIP_LEDGER=enforce): a new, grown or vanished skip fails until the
#  ledger is edited on purpose. Reproduce CI's view in a clean clone:
#    NP_TEST_DSN=postgresql://x@127.0.0.1:1/x NP_SKIP_LEDGER=enforce pytest tests

# --- screenshots (local harness; stubs ONLY guard.identify) ------------
SUPABASE_DB_URL_SESSION="$LOCAL" python3 eval/screenshot_views.py

#  The hand-built plain-PostgreSQL workbench (port 55432, `np_b2`) used for
#  B2/B2.5 is SUPERSEDED: its shim lacked auth.identities, the postgres and
#  supabase_auth_admin roles, and a non-superuser owner, so 24 DB tests
#  failed there for reasons production does not have.

# --- deploy (Phase D) ---------------------------------------------------
#  copy to /tmp WITHOUT .git, deploy from there, then check the live URL.
#  Never `vercel ls`.
```
