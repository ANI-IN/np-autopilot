> **Archived (run 6, G1, 2026-11-04).** Superseded by run 6: see README.md / docs/VISION_AND_ROADMAP.md / HANDOFF.md. Kept as history.

# HANDOFF

**Written 2026-09-30, right after the launch window, so a fresh session can
resume with nothing lost.** Every number in §A was measured when this was
written, not recalled. The previous handoff (2026-09-29, A–I) is in git
history at `b1c8329:docs/HANDOFF.md`; anything from it that is still true is
carried below.

**Section letters changed.** Code comments still cite the old ones:

| old | now |
|---|---|
| §A where things stand | §A |
| §B, §C completed work, B3 | §B |
| §D.1–§D.4 plan and the window | §B (done) and `docs/WINDOW-RUNSHEET.md` |
| §D.5 "immediately after launch" (R22, Indian Instructors, read-only role, `Dat` header) | §G (post-launch items) and §I (R22) |
| §D.6 first release after launch, §D.7 live sheet, §D.8 Interview Repo | §G |
| §E open review items | §G |
| §F owner decisions | §H |
| §G open issues and risks | §I |
| §H working agreement | §J |
| §I key commands, the local stack, running tests safely | §K |

---

# A · WHERE THINGS STAND (measured 2026-09-30, after the window)

## Production — LIVE: the new code on the new data

| | |
|---|---|
| site | `np-autopilot.vercel.app` → **`dpl_3HZSPGpQEsz9gogu9WofSGQdJR8r`** (target production, Ready, created 2026-09-30 20:57 IST); `/api/config` 200; `/api/me`, `/api/overview`, `/api/structure` 401 with our body; all six security headers; `index.html` byte-identical to the artifact |
| built from | `main` **`b1c8329`**, artifact `/tmp/np-deploy-b1c8329` (function map OK, no stub, no env file) |
| **code rollback** | `vercel rollback dpl_5wWZxv7ed1Bhq1fvCMSMVPgnfmxg` — the deployment current before the promote |
| **data rollback** | `db/window/restore_projection.sh ~/.config/np-autopilot/window-20260930-2105` — the ONLY way back after 0021 (never re-project the old graph) |
| also moved | the team-scoped alias `np-autopilot-b2c-courses-new-programs-4557s-projects.vercel.app` follows each `--prod` deploy |

## Database (production, read at the time of writing)

| migration | content hash | nodes | edges | node_sources | files | node_types | edge_rels | node_layout |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **0021** | **`9af6d9dbeb623e84…`** | **8,496** | **12,189** | **39,414** | 1,524 | 17 | 24 | **3,707** |

`projected_at` 2026-09-30 15:36:33Z. `verify_migration --source supabase`
**54/54 VERIFIED**; `curation.py check` **IN SYNC**. Curation tables
unchanged by the window: people 20, people_aliases 48, domain_aliases 21,
workflow_owners 92, curation_notes 45, curation_audit 0. profiles 6,
shared_accounts 1.

## Mastersheet

The live sheet `1setMmRvBUNu9_85nT4xvvUFySodB6kiWb7bQ8qLEqAQ` (Resource
Collection Mastersheet (Software + System)): **version 2742**, Drive modified
2026-09-30T11:46:31Z, fetched 14:59:29Z to `~/.config/np-autopilot/mastersheet/`.
Freshness guard: fresh. Version 2736's copy is kept at
`~/.config/np-autopilot/mastersheet-prev-20260930-2029/`. The 2736 → 2742 diff
had **0 changed facts** and the owner accepted it (§H).

## Git

| | |
|---|---|
| branch | `main` |
| HEAD at measurement | **`b1c8329`** (merge of `b4-ui-2`); this handoff's commit follows it |
| main CI | **green** on `b1c8329` — `test`, `payroll`, `secrets`, `renderer` (run 36734801749) |
| working tree at measurement | one change: **`public/stats.json`**, production's figures copied at window step 6 (differs from the deployed copy only in `projected_at`). **Committed with this handoff**, so the tree is clean |
| remote branches | `b4-ui` **deleted** (owner decision); `b4-ui-2` kept (merged); older merged branches remain |
| repository | **private**; pushes pass `.githooks/pre-push` |

## Verification

| check | result |
|---|---|
| local suite (local Supabase stack), `714f5c1` | **1,075 passed**, 16 skipped |
| `eval/check_3d.py` (GPU, production CSP) | all 11 checks passed — 60 fps, label overlay 0.27 ms/frame, the throttled slow-machine case |
| `eval/mastersheet_rederive.py` on version 2742 | **0 unexplained** across 20 modules |
| `docs/ACCEPTANCE-CHECKLIST.md` | 20/20 confirmed; 154/154 linkable items carry an Uplevel link |
| `node eval/drive_dom.mjs` on the LIVE `index.html` | all checks passed |
| production_only tests (read-only, through the session pooler) | **7 passed** |

## Local, still running

The local review server was left running (`eval/local_server.py` on port
8765, pid 32345 at writing) against the local Supabase stack, which holds the
same projection (`9af6d9db…`). Stop it with `pkill -f eval/local_server.py`.

---

# B · WHAT SHIPPED (all live since the 2026-09-30 window)

| what | commits |
|---|---|
| **The B4 explorer UI** — the network map as the default for every type, collapsed legacy groups, chips filter the map with ghost anchors, focus spreads and frames a module, floating nodes with springy drag, role order and colours (P/B1/B2/B3), Who teaches what, Programme timeline, historical files grouped, plain-language panels, crisp high-DPI rendering, decks as core structure, the local review mode | `ee47ccc` (review rounds 1–6, squashed from `b4-ui`) |
| **3D floating map as the default, 2D behind a toggle** (Three.js vendored, lazy, eval-free, CSP not widened; no-WebGL falls back to 2D) | `befa170` |
| **One-URL state** — one place, at most one focused item, real Back/Forward | `9945fb1` |
| **Slow-machine fallback to 2D**, the possessive-name filter, the landing copy | `714f5c1` |
| merge to `main` | `b1c8329` |
| **Links** — Uplevel for every module and session (**154/154**), each domain's Uplevel page, Drive files and folders on every item, the mastersheet only as the citation | `f9b4c69`, `2bb8609`, `579f72f`, `ee47ccc` |
| **Identity merges** — INS-08/30 (Bill Ogden = William David Ogden), INS-31 (Konstantinos Pappas), INS-32 (Shelby Cohen), PPL-02…05/10 (Nisarg Tanna, Cathy Ma, Faraaz Sareshwala), Robert K; PPL-11 (Bharath Anand); PPL-13 (Reginald Johnson); MOD-01…16 applied, MOD-17/18 kept separate | `cb3522f`, `579f72f`, `80dc2e8` (earlier: `9e202ce`, `a87f960`, `f9b4c69`) |
| **The pooler read-only guard** — production tests run read-only through the session pooler, proven by canaries 1–4 | `470ab48`, `94d25e8`, merge `210e84e` |
| **The live mastersheet as the source** — scope file, read-only fetch, freshness guard, fail-loud parsing, diff, pass 7 on the live sheet | `34cb5c6`, `80dc2e8`, `579f72f`, merge `694c323` |
| **The deploy artifact fix (R23)** — built from a `.vercelignore`-pruned tree, function map checked | `433f5f3`, merge `f4cd274` |
| **Landing copy** for this release | `714f5c1` |
| **The window** — migrations 0017–0021 (earlier sitting), the prebuilt deploy and **promote**, the projection, verification | run-sheet `3c37c9b`, `94d25e8`; deployment `dpl_3HZSPGpQEsz9gogu9WofSGQdJR8r` |

Before today (still true, detail in history): the row-B crawl and content
graph, B1 projection merge, B2 structure view, B2.5 verification, B3 speed
(cold starts, connection reuse and drop recovery, precomputed layout,
columnar brotli `/api/structure`, ETag, lazy panels; `pg_trgm` not shipped by
decision).

---

# C · STILL OPEN FROM THE WINDOW — DO THESE FIRST

1. **Step 7 click-through results from the owner.** Not yet reported. The
   list given to the owner: sign in → 3D map; search `API Design` (Backend
   Engineering, Week 11) → the chain (Module row: Uplevel module + Drive
   folder; Pre-class, Class, Alternate class, Task, Review, Alternate review,
   Post-class, each with its own Uplevel link; under Class 8 `Deck:` links, 1
   `File:`, a collapsed `Historical (4)`; instructors Robert Kreznarich and
   Tilo Dickopp primary, Shelby Cohen backup 1; no "Tilo’s …" topic); the
   Class row's **Uplevel** link; **Deck: IK-API-Design-presentation-RK-v3.pptx**;
   **Who teaches what** (Robert and Tilo green, Shelby blue); **Programme
   timeline** (API Design in Week 11, legacy apart); **Back** returns to the
   previous view. The owner was told to have the team **reload open tabs as
   soon as sign-in works**. A failure → §K rollbacks.
2. **`python3 eval/measure_signed_in.py --phase post --wait-for-enter`**
   (opens a browser; the owner signs in once), then before/after against
   `docs/PERF-BASELINE.md`, recorded there.
3. **Post-window cleanup.** `public/stats.json` — **done** (committed with
   this handoff). Still to do: delete the rehearsal copy
   (`rm -rf ~/.config/np-autopilot/rehearsal`), the rehearsal database
   (`psql postgresql://supabase_admin:postgres@127.0.0.1:54322/postgres -c "drop database rehearsal"`),
   and every `/tmp/np-deploy-*` artifact, preview copy and build log. **Keep** both window backups
   (`window-20260930-1133`, `window-20260930-2105`) and
   `mastersheet-prev-20260930-2029` until the owner says.
4. **Fix the deploy-check gap.** Building the preview sibling with
   `vercel pull --environment=preview` left `.vercel/.env.preview.local` in
   the copy (a zsh glob error aborted the cleanup line), and
   `db/window/check_function_map.py` still printed "no env file" and counted
   it among 90 uploaded files. It was deleted before any upload (re-check: 89
   files). Fix: the check must look under `.vercel/` for `.env*`, with a test
   on a synthetic artifact that fails before the fix.

---

# D · DEPLOY PROCEDURE — as it actually works now

Production deploys and promotes are **run by the owner in their own
terminal**: Claude Code's permission classifier blocks
`vercel deploy --prebuilt --prod` (observed 2026-09-30). In the owner's own
terminal there is **no `!`** — `!` is only for commands typed inside Claude
Code.

1. **Build the artifact** (Claude): `db/window/build_artifact.sh main <stats.json>`
   → `/tmp/np-deploy-<sha>`; it must print `function map OK … no local stub`.
2. **Preview** (Claude): the artifact is built for production, so build a
   preview-target sibling: copy it without `.vercel/output` and
   `.vercel/python`, `vercel pull --yes --environment=preview`,
   `vercel build`, **delete every `.vercel/.env*` file** (check with `find`,
   not a glob), re-run `check_function_map.py`, then `vercel deploy --prebuilt --yes`.
   Check with `vercel curl <path> --deployment <url>`: `/api/config` 200;
   `/api/me`, `/api/overview`, `/api/structure` 401 with our JSON body; six
   headers. The preview appends Vercel's feedback-toolbar tag to `index.html`
   (production does not; our CSP blocks it).
3. **Production deploy** (owner): `cd /tmp/np-deploy-<sha> && vercel deploy --prebuilt --prod --yes`
   → send the new `dpl_…` id.
4. **Checks** (Claude): `vercel inspect np-autopilot.vercel.app` must still
   show the previous id; on the new deployment's own URL: config 200, the
   three 401s, the six headers, CSP == `vercel.json`, `index.html`
   byte-identical to the artifact, `/vendor/np3d.min.js` served, `stats.json`.
5. **Promote** (owner): `vercel promote <dpl id> --yes`.
6. **Confirm** (Claude): the live URL shows the new id; re-check it. The
   rollback target is now the previous id.

A data change goes through `docs/WINDOW-RUNSHEET.md` (fresh backup →
freshness check → projection → verification); never `vercel ls`.

---

# E · NEXT PHASE — `docs/archive/NEXT-PHASE.md` (a plan only, awaiting the owner)

Nothing is built. The owner's direction of 2026-09-30 is recorded at the top
of that file:

- **Team & ownership**: internal `team_member` nodes from a **Keka export or
  a maintained sheet**; `reports_to`; `owns` with a role; a **Team tab** and a
  **"who owns what" matrix**.
- **All pods**, `pod` as the top level: **System Pod next**, then **Agentic
  AI**, then **Data & Management**.
- **Workflows & SOPs, programme operations, metrics & feedback (always with
  N).**
- **The MCP query layer plus four job plugins**: Staff a class · Prep a
  module · Run a workflow · Program/ops answers.
- **Distribution via a GitHub org and a separate, clean plugins repo.**

**What is needed from the owner** (`NEXT-PHASE.md` §5, §4.4):

- files shared to the service account: **the "NP Autopilot" spreadsheet**
  (Automations / All Tasks / To-Do & Working Notes — not in the corpus
  folder); **live P1/P2** poll sheets; **the live New Combined Schedule**; a
  Keka export or the maintained team sheet;
- **a GitHub org** (named, with the assistant's account as an owner) and the
  first team's members;
- **a Google Cloud OAuth client** for the MCP sign-in (project `np-autopilot`,
  Internal consent screen);
- **the §4.4 decisions**, items 1–4 before Phase 0: distribution, MCP sign-in,
  who sees what, metrics audience; items 5–10 before their phase.

---

# F · IMPROVEMENT BY OBSERVATION (new, 2026-09-30)

The owner's requirement: the site improves from what the team actually sees.

- **Intake — one place, two kinds.** A Slack channel (proposed
  `#np-autopilot-feedback`) or a short form with three fields: *what I was
  trying to do*, *what I saw* (a screenshot or the page URL — the URL now IS
  the view, so it reproduces exactly), *issue or idea*. The channel and its
  name are the owner's choice; nothing is set up yet.
- **Weekly triage** (owner + assistant, ~30 min): each item becomes a
  **fix** (a wrong or missing fact, a broken link, a UI bug), a **review row**
  (an identity or label question → `docs/REVIEW-QUEUE.md`), a **backlog
  item** (`docs/UI-BACKLOG.md` or `NEXT-PHASE.md`), or **declined with a
  reason**. An accuracy report always starts from CLAUDE.md §6: name the
  sheets read before concluding "not in the corpus".
- **Small releases through the same path**: branch → CI green → merge → §D
  (preview → owner's `--prod` → checks → owner's promote). A data change adds
  the run-sheet's backup, freshness check and verification.
- **A short changelog on the site**: dated, plain-language entries ("Decks now
  hang off their session"), newest first — proposed as a static page linked
  from the landing footer, generated from a `CHANGELOG.md`, so it stays in
  the CSP-hashed build. Not built.

---

# G · OPEN REVIEW ITEMS AND POST-LAUNCH WORK

## Review queue — `docs/REVIEW-QUEUE.md`, 106 rows: 68 answered, 38 open

| prefix | rows | state |
|---|---:|---|
| `MOD` | 18 | all answered — 16 applied; MOD-17/18 kept separate |
| `INS` | 32 | all answered and applied |
| `PPL` | 13 | 12 answered (PPL-13 = Reginald Johnson); **PPL-12 open** |
| `TOPv` / `TOPm` | 3 / 3 | answered and applied |
| `TOPt` | 6 | **open** — lesson-plan tab → module |
| `DCK` | 14 | **open** — deck filename → instructor |
| `NAM` | 16 | **open, queued for later** — instructor labels that are not one person's name (`2- Prateek`, `Robert/Shelby/`, `Indian SME hiring` …) |
| `DUP` | 1 | **open, queued** — DUP-01 `Anshaj` · `Anshaj Khare` |

**There is no `REM` prefix.** The handoff request named "REM-16 legacy names";
nothing in the repo uses `REM`. The 16 legacy-name rows are **NAM-01…16**,
taken to be what was meant.

**Tilo’s note pages — not a queue row, flagged.** The possessive rule holds
back 18 titles, all Tilo Dickopp's ("Tilo’s page 13 notes on Authorization"
…), so API Design's topics went 238 → 220 current. Some of those titles name a
real subject. The owner asked for the rule; whether those subjects should
come back as topics (e.g. with the prefix stripped) is an open question for
the owner, not decided.

## Post-launch items (deferred by the owner, no action before)

1. **`Agentic AI - SWE` date header** — `05-operations/New Combined
   Schedule.xlsx` heads that tab's date column `Dat`, so no `class_dates` are
   read; `Machine Learning DTC` and `MLSwitchUp DTC` have a blank header. Match
   by shape or a per-tab header map; never rename the corpus file; report any
   tab whose date column cannot be found.
2. **Indian Instructors review** — passes 2–4 read the corpus copy's `Indian
   Instructors` tab (`Indian SME Name`, `pipeline/lib/sources.py`); decide name
   by name which are active instructors and which are hiring candidates
   (candidates are withheld like R18's).
3. **A dedicated read-only database role** for the production tests — today
   read-only is a session setting that canary 5 (`SET TRANSACTION READ WRITE`)
   defeats; pinned by a strict xfail in `tests/test_read_only_through_pooler.py`.
   Rehearse locally, then flip the xfail.
4. **Topic categories and tool tags** (Release 2) — `config/topic-categories.yaml`
   and a closed `config/tools.yaml` with a `tool` node type; proposals only
   until confirmed. `docs/UI-BACKLOG.md`.
5. **Exact-slide deep links need the Slides API** — `drive.readonly` is
   enough scope; first check whether the Slides API is enabled in the service
   account's project (if not, tell the owner what to enable and pause);
   ~238 native decks; `.pptx`/`.pdf` keep the file link plus the number.
6. **Move the repository to the org** (with §E's distribution) — and off the
   synced Desktop (§I R22).
7. **The main graph still reads the corpus-copy mastersheet** for legacy-tier
   facts (`Indian Instructors`, `Instructor(FullStack)`, `Module Name` on eight
   tabs). Removing those reads would drop legacy people and the modules 16 MOD
   merges are keyed to — **owner decision pending** (`NEXT-PHASE.md` §4.4
   item 10).
8. **`Interview Repo`** tab — a candidate for a later release; not ingested.
9. **Billing decision pending**: one step up in the Vercel function `memory`
   setting, measured before/after on the cold-start premium (~1,131 ms).
10. Also specified earlier and still open: `docs/EXTERNALLY-OWNED-FILES.md`;
    a shared export map between pass 0 and the crawler; a plugin `/module`
    command (superseded by §E's plugins); other row-B domains (superseded by
    §E's pods).

---

# H · EVERY OWNER DECISION FROM TODAY

All **origin: hand, Animesh Kumar, 2026-09-30**. Each was checked present in
the file named while writing this. The 2026-09-29 decisions are in the
previous handoff's §F (`b1c8329:docs/HANDOFF.md`) and the files it names.

| decision | recorded in |
|---|---|
| Plan reordered: the fastest ACCURATE launch (B3 → merge → acceptance → window); deep links and B3.5 after launch | `docs/UI-BACKLOG.md` (top) |
| `pg_trgm` not shipped (unusable under RLS) | `docs/DEFAULT-VIEW.md` D3 status, `docs/PERF-BASELINE.md` §B3 |
| CI "all four green" applies to the branch's own run | previous handoff §G (`b1c8329`) — resolved: main is green |
| Window order: migrations → deploy → projection | `docs/WINDOW-RUNSHEET.md` |
| R22 accepted and deferred until after launch | `07-risks.md` R22 |
| Post-launch: Indian Instructors review; a read-only DB role; the `Dat` header | this file §G; `tests/test_read_only_through_pooler.py` (xfail) |
| The LIVE mastersheet replaces the corpus copy as the source; declared tabs only; `Interview Repo` a later candidate | `config/mastersheet-scope.yaml` |
| Checklist review 1–3 answers: identities (INS-08/30/31/32, PPL-02…05/10, Robert K), module labels = mastersheet names (TOPv/TOPm), MOD-17/18 kept separate, PPL-13 = Reginald Johnson | `docs/REVIEW-QUEUE.md` ("Checklist review" sections), `config/instructor-identity.yaml`, `config/module-merges.yaml` (`kept_separate`) |
| Daniel Grundel (SD1/4 Backup 3, red cell) no longer teaches it | `config/mastersheet-owner-facts.yaml` |
| Topic quality: person names and bios are not topics; housekeeping ranked last, never removed | `config/topic-quality.yaml`, `tests/test_not_a_topic.py` |
| 20 of 20 modules confirmed | `config/owner-confirmations.yaml` |
| Window paused; the new UI rejected on live; code rolled back to `dpl_5wWZ…`; next deploy by **promote** | `docs/WINDOW-RUNSHEET.md` ("Earlier state") |
| NAM and DUP rows queued for later, not changed now | `docs/REVIEW-QUEUE.md` (NAM, DUP) |
| The next-phase plan (plan only); **launch now, expand scope next** | `docs/archive/NEXT-PHASE.md` |
| **B4 UI decisions**: separate old/new domains, SD labels, legacy badge; the map as the default; chips filter the map; ghost anchors; labels never dropped; floating and drag; focus; role order and colours; historical grouping; plain language; crisp rendering; one-URL state; search holds back not_a_topic; decks core; the local review mode; screenshots not committed | **`docs/DEFAULT-VIEW.md` D6** — *recorded while writing this handoff* |
| **UI approved; 3D default, 2D one toggle away** (reconfirmed after the approval) | **`docs/DEFAULT-VIEW.md` D6** — *recorded while writing this handoff* |
| **Slow-machine fallback to 2D** with "Try 3D anyway" | `docs/DEFAULT-VIEW.md` D6, `tests/test_default_view_labels.py` |
| **Possessive first names** of known people are not topics | `docs/DEFAULT-VIEW.md` D6, `tests/test_not_a_topic.py` |
| **Landing "What it answers well"** for this release | `docs/DEFAULT-VIEW.md` D6, `public/index.html` |
| **Delete the remote `b4-ui` branch** after the merge | this file §A (done) |
| **Accept the empty mastersheet diff** (2736 → 2742, 0 facts changed, 0 unexplained, 20 ticks hold) | **`docs/WINDOW-RUNSHEET.md` STATE** — *recorded while writing this handoff* |
| **Go-ahead for window steps 5–6** with a FRESH backup first | `docs/WINDOW-RUNSHEET.md` STATE |
| **Keep the window backups until the owner says** | `docs/WINDOW-RUNSHEET.md` STATE, this file §C.3 |
| **Production deploys and promotes are run by the owner** in their own terminal | this file §D |
| **Next-phase direction**: team_member from Keka or a sheet, `reports_to`, `owns` with a role, Team tab, who-owns-what matrix; pods top-level (System Pod, then Agentic AI, then Data & Management) | **`docs/archive/NEXT-PHASE.md` "Owner direction"** — *recorded while writing this handoff* |
| **Improvement-by-observation loop** | **this file §F** — *recorded while writing this handoff* |

**Not recorded anywhere before this handoff** (only in commit messages or
conversation): the B4 UI decisions and the 3D default (now `DEFAULT-VIEW.md`
D6), acceptance of the empty mastersheet diff (now the run-sheet STATE), the
next-phase direction (now `NEXT-PHASE.md`), and the improvement loop (now
§F).

---

# I · RISKS AND DEFERRED ITEMS

- **R22 — the repository folder syncs to iCloud and a Google Drive
  "Computers" backup**, including the database password and withheld hiring
  data. Accepted, deferred until after launch — **now due**: (1) move the
  repo out of `~/Desktop` (e.g. `~/src/np-autopilot`); (2) remove the cloud
  copies, with version history and trash, and confirm which Google account
  held the backup; (3) **rotate the database password, then redeploy** (§D),
  so no rollback target holds the old one — after which the rollback target
  is the new build, not `dpl_5wWZ…`.
- **R20 — the Drive-upload incident.** The password was NOT rotated, by owner
  choice (so R22's rotation covers it). `07-risks.md` R20 disagrees with this
  on two facts (whether the copies are still present; whether rotation was
  done) — only the owner knows; re-list the folder read-only and record which
  is current.
- **R21 — the repository was public for 13 days** (to 2026-09-29); 81 external
  clones; the disclosure question is the owner's, alongside R18's. Private
  since; `pipeline/check_repo_private.py` gates every push.
- **Shared accounts**: `shared_accounts` has 1 row. A shared Google account
  signs in as `member` (migration 0014), but nothing can say which person used
  it (`docs/AUTH.md`: no technical answer).
- **`interview-kickstart.com` (hyphen): 185 files** — IT confirmation still
  pending; included in the externally-owned list.
- **Externally owned files**: 389 in all, **204 owned by personal accounts**
  (Drive cannot transfer ownership from a personal account; the fix is an
  IK-owned copy); **49 download-disabled** files are metadata-only, linked,
  marked "view only".
- **Coverage**: 127 of 374 worksheets have been read by an entity scan; every
  person / instructor / module count is a floor (CLAUDE.md §2). Widening
  coverage is also what removes the contact-data protection — read CLAUDE.md
  §2 first.
- Carried: registry drift (`count_registry.py` vs the live folder); registry
  row C shared "anyone with the link"; ~100 legacy "session rows wearing a
  module label"; 724 of 922 legacy modules with no programme edge (one faded
  cluster); a ~1,131 ms cold-start premium; `/api/structure` is a bulk
  download by design (parameterless).

---

# J · WORKING AGREEMENT (unchanged)

- **Step by step; STOP after each step** for the owner.
- **Nothing to production without the owner's explicit go-ahead** — no push to
  production data, projection, migration or deploy. Production deploys and
  promotes are the owner's (§D). Never touch the production database for
  previews.
- **Never print a secret, token or DSN**, even partially. The window env helper
  sources `~/.config/np-autopilot/env` — never echo it.
- **Ambiguity is returned, never guessed** (`lib/resolve.py`). **Thresholds
  rank or warn, never silently exclude** (CLAUDE.md §4).
- **Every owner decision is recorded** as `origin: hand`, with name and date,
  in a file.
- **Verify by measurement, never by status output; every check must be able
  to fail** — mutation-test it.
- A failed window step: stop, run that step's rollback from the run-sheet, and
  ask before anything else.
- Merge with a merge commit, one command at a time.
- The corpus is read-only; Drive access is `drive.readonly`; workbooks open
  `read_only=True`; contact columns are never printed or declared.

---

# K · KEY COMMANDS

```bash
# --- once per clone ----------------------------------------------------
git config core.hooksPath .githooks      # pre-push refuses a public repo (R21)
python3 pipeline/check_repo_private.py   # the same check, by hand

# --- environment -------------------------------------------------------
#  ~/.config/np-autopilot/env IS PRODUCTION. Load it only for a window step
#  or a read-only check; never before pytest (below).
set -a && . ~/.config/np-autopilot/env && set +a
export NP_DRIVE_SA_KEY=~/.config/np-autopilot/drive-sa.json   # a PATH, never the key

# --- mastersheet (the live sheet) ---------------------------------------
python3 -c "import sys; sys.path.insert(0,'.'); from pipeline.lib import freshness as f; f.require_fresh('check')"
python3 pipeline/fetch_mastersheet.py                 # read-only export, outside the repo
python3 eval/mastersheet_diff.py OLD.xlsx NEW.xlsx    # every fact; contact columns as counts
python3 eval/mastersheet_rederive.py                  # must be 0 unexplained

# --- pipeline ----------------------------------------------------------
python3 pipeline/00_fetch_drive.py                    # needs NP_DRIVE_SA_KEY
python3 pipeline/07_build_content_graph.py            # content graph (reads the live export)
python3 pipeline/08_merge_graphs.py                   # answered REVIEW-QUEUE rows, topic marks
python3 pipeline/refresh.py                           # end-to-end refresh
python3 pipeline/validate.py
python3 pipeline/gen_acceptance_checklist.py
python3 pipeline/gen_csp_hashes.py                    # after ANY edit to public/index.html

# --- local database: Supabase CLI stack --------------------------------
colima start && db/local/setup.sh                     # start, migrate, project, seed
LOCAL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
POOL="postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres"
#  project locally WITHOUT touching tracked public/stats.json:
SUPABASE_DB_URL_SESSION="$LOCAL" SUPABASE_DB_URL_TRANSACTION="$POOL" \
  NP_LANDING_STATS=/tmp/stats-scratch.json python3 pipeline/project_graph.py
SUPABASE_DB_URL_SESSION="$LOCAL" python3 pipeline/verify_migration.py --freeze   # only content hashes should move
python3 tests/test_structure_payload.py --write      # regenerate the payload fixture

# --- tests -------------------------------------------------------------
python3 -m pytest tests -q        # DB tests go to the local stack; refuses a production DSN
#  production_only, read-only, ONLY at a window step:
#    NP_ALLOW_PROD_TESTS=1 python3 -m pytest tests -m production_only -rs
node eval/drive_dom.mjs public/index.html              # renderer harness

# --- the local REVIEW server -------------------------------------------
#  Stub member sign-in + "LOCAL PREVIEW, not production" banner; can never ship
#  (tests/test_local_stub_never_ships.py). Restart after server-side changes.
nohup python3 -u eval/local_server.py 8765 > /tmp/np-local-server.log 2>&1 < /dev/null & disown
#  open http://127.0.0.1:8765/   (2D: /?dim=2d)

# --- the 3D map --------------------------------------------------------
eval/build_np3d.sh                  # rebuild the vendored bundle (three + 3d-force-graph)
python3 eval/check_3d.py            # GPU: CSP, fps, chips, focus, Esc, pause, fallback,
                                    # reduced motion, slow machine -> 2D
SUPABASE_DB_URL_SESSION="$LOCAL" python3 eval/screenshot_views.py

# --- deploy (§D; production steps are the OWNER's, no `!` in their terminal)
db/window/build_artifact.sh main /path/to/stats.json  # -> /tmp/np-deploy-<sha>, map checked
python3 db/window/check_function_map.py /tmp/np-deploy-<sha>
cd /tmp/np-deploy-<sha> && vercel deploy --prebuilt --prod --yes   # OWNER
vercel promote <dpl id> --yes                                      # OWNER
vercel inspect np-autopilot.vercel.app                # never `vercel ls`
vercel curl /api/config --deployment <url>

# --- window data steps (docs/WINDOW-RUNSHEET.md) -------------------------
db/window/backup.sh "$B"                              # before any projection
psql "$WINDOW_DSN" -At -F '	' -f db/window/counts.sql
python3 pipeline/verify_migration.py --source supabase   # 54/54
python3 pipeline/curation.py check                        # IN SYNC

# --- rollbacks ---------------------------------------------------------
vercel rollback dpl_5wWZxv7ed1Bhq1fvCMSMVPgnfmxg                              # code
db/window/restore_projection.sh ~/.config/np-autopilot/window-20260930-2105   # data

# --- performance -------------------------------------------------------
python3 eval/measure_signed_in.py --phase post --wait-for-enter   # the owner signs in once
```
