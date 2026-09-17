# 07 — Risk Register

Likelihood and impact are my judgement, stated plainly. Risks are ordered by expected damage, not by category.

---

## R1 — The master file the brief describes does not exist
**Likelihood: certain (already happened) · Impact: high**

The brief's taxonomy derives from an "NP Autopilot" spreadsheet with `Automations`, `All Tasks` and `To-Do & Working Notes` tabs. The corpus contains a Markdown workflow inventory with four fields and **no owner column**. Two of your nine node types (`Owner`, `Automation`) have no source in the file you expected them to come from.

**Mitigation:** taxonomy revised in doc 05 — `Automation` dropped, `Owner` re-sourced from `Domains_Courses Owners.xlsx` and renamed `Person`, `Domain` added as the bridge. **Before Part B starts, confirm whether the 3-tab spreadsheet exists elsewhere.** If it does, doc 05 changes materially and I should redo it.

---

## R2 — ~~Workflow ownership does not exist in any file~~ → **NOT A RISK. A finding.**
**Status: CLOSED 2026-09-10. Reclassified from a data gap to a fact about how the team works.**

**This entry was wrong, and the error mattered.** It read as *"ownership data is
missing"* and prescribed a fill-in file as the mitigation. It is not missing.

**Workflow-level ownership does not exist because that is not how New Programs is
organised.** Confirmed by the corpus owner, 2026-09-10:

> Everyone does every kind of work — each person has SMEs to coordinate with
> across development, live class, ARS, RCA. There is no per-workflow owner.

So any value in `workflow-owners.yaml` would be an **invention**, not a gap
someone failed to fill. The earlier decision to fill it is reversed on better
information, and the reversal is the right call: filling it would have
manufactured 92 false facts and made them look sourced.

**What ownership actually attaches to: `Domain`.** That is real, recorded in
`Domains_Courses Owners.xlsx`, and modelled as `owned_by` / `supported_by` /
`delivered_by`.

**The mechanism stays in place, empty.** `config/workflow-owners.yaml` (92 rows,
all blank, all `confirmed: false`), `pipeline/gen_workflow_owners.py` and the
`workflow_owned_by` edge type are all retained and emit zero edges. If ownership
ever formalises, nothing needs building. **Do not delete them, and do not fill
them speculatively.**

**Consequence for the graph, accepted deliberately:** it stays two components.
Component A is 92 workflows and 16 themes with no internal structure. That is the
correct picture of this corpus, not a defect (see R6b, which is likewise
reclassified from a cost to a description).

**Consequence for coverage — important.** Coverage must **NOT** report 92
workflows as "missing an owner". That would be a false-negative finding: it would
present a correct state as a defect and invite someone to fix it by inventing
data. Coverage must say **workflow-level ownership is out of scope** and point to
the domain owners.

---

## R3 — Person-name duplication
**Likelihood: certain · Impact: high**

I found **~28 humans expressed in 38+ distinct strings**. Specifically in this corpus:

- **`Srushit` / `Srushith` / `Srusith`** — three spellings, *inside one spreadsheet*
- **`Swarup` / `Swaroop`** — same file, two sheets
- **`Tanmaaya` / `Tanmaya`** — same file, two sheets
- ~~**`Kalindi .`** — a literal trailing space-dot in `IAims`~~ — **WITHDRAWN 2026-09-09.** `Kalindi .` is her actual HR record, confirmed against the NP directory. It is correct data, not corruption. Keep `label_raw`, do not strip, do not flag.
- Short/long pairs throughout: `Animesh`/`Animesh Kumar`, `Adil`/`Adil Panwar`, `Shashi`/`Shashi Bhushan Kumar`, `Prasad`/`M Prasad`/`M Prasad Khuntia`, `Utkarsh`/`Utkarsh Raj`, `Navdeep`/`Navdeep Singh`
- **`Karthika S` vs `Karthika Pai`** — unresolved; may be two people
- `Michael Savafi`/`Mickael Savafi`, `Huzaifa`/`Huzefa` among instructors
- One row where name and email disagree: `Anshuman` ↔ `somya@interviewkickstart.com` — still unresolved; Anshuman is not on the NP directory
- **A person no scan found at all:** `Yash Mathur` — 11 I-Aim rows in `IAims!Q226` with a **blank `ENo`**. He is on the current NP directory and appears in neither doc 08 list. An employee-id-keyed read drops him silently. **Second independent reason the R3 keying recommendation had to be reversed**, and a failure mode distinct from the coverage gap (the file was scanned; the row was dropped).

**Why it is worse than it looks:** fuzzy matching that correctly merges `Srushit`/`Srushith` will *also* be confident about `Karthika S`/`Karthika Pai`, which may be wrong. Precision and recall pull in opposite directions on the same threshold.

**Mitigation — CORRECTED 2026-09-09. Do not key on employee IDs.** The earlier version of this line recommended keying `people.yaml` on `IAims` employee IDs. **That is wrong and was reversed by doc 08 Q4.** The IDs are neither unique nor stable:

- **`IK-294` maps to two people**; so does **`IK-INT30`**.
- **`Animesh Kumar` carries two different IDs.**
- There is a fill-down artefact: `Karthika S` reads as `IK-115`…`IK-121` and `Prithika K` as `IK-915`…`IK-922` down consecutive rows — the ID increments while the name stays fixed.

Keying on them reproduces the `IK-294` collision directly in the graph.

**Key on a curated slug in `people.yaml`.** Employee IDs are carried as *evidence only*, in an `employee_ids` list property, never as the identity. Fuzzy matching **proposes only**, never applies; everything under threshold goes to `people-review.yaml`.

---

## R4 — Freeform extraction invents entities
**Likelihood: high · Impact: high**

Not hypothetical. The reference implementation's shipped graph contains **27 fake instructors (8% of that node type)** — slide bullets split on a comma into name + role: *"Workflows are powerful"* / *"but they have boundaries."*, *"AI doesn't read your mind"* / *"it follows your instructions."*, and a CSV row that lost its quoting and became a node ID containing someone's email and employment history. It is live in a public repo.

Our corpus is *more* dangerous for this: `AgenticAI Instructors Training Plan` alone has 18 sheets of loosely structured name grids, and `New Combined Schedule` has 62.

**Mitigation:** closed vocabulary in Pass 2 with a **non-empty rejection log**; structured parsers for the sheets whose columns are known (owners sheet, IAims, schedule); junk-name heuristics in `validate.py` (multi-word labels, sentence punctuation, stopwords, `@`, `http`, length > 40). The brief's extract/resolve split is the structural defence — the reference implementation fused them and this is the result.

---

## R5 — Column misalignment from blank cells
**Likelihood: high · Impact: high · *I hit this myself during A1***

`Domains_Courses Owners.xlsx` row 8 (`Early Engineering`) has no Secondary Owner. Any parser that compacts non-empty cells shifts `Every Week` into the owner column and produces **"Early Engineering is owned by Every Week"**. My own inspection dump did exactly this before I noticed. Row 36/37 (`Deval, Srushith, , Adil`) has a double comma yielding a blank owner.

**Mitigation:** read cells **positionally by index, never by filtering out blanks**. Add a `validate.py` check that no `Person` name matches a known cadence/status vocabulary (`Every Week`, `Once a month`, `TBD`, `NA`, `Discontinued`, `IP`, `SU`). Cheap, catches a whole class of error.

---

## R6 — Sensitive content
**Likelihood: certain · Impact: high (reputational/legal, not technical)**

Full detail in doc 01. Summary:

- **Compensation:** `US Instructor Cost Analysis.xlsx` — 23 MB, 74,961 rows, per-instructor hourly rates for 2025 and 2026.
- **Contact PII of external people:** personal Gmail addresses, **phone numbers**, LinkedIn URLs and Discord IDs across six files, including *rejected* candidates in `SME Tracker!Rejected, Re-applying`.
- **Written judgements about named individuals:** `AgenticAI Instructors Training Plan` sheets `WIP` and `Instructors` contain free text such as *"Bad ratings"*, *"GenAI ratings are not good"*, *"Unresponsive"* against named people.
- **Employee performance:** `IAims` holds named employees, IDs, goal attainment, `Manager's Ratings`, `People Effectiveness Score`.
### ⚠ CORRECTED after the full-row scan — this is far larger than I first reported

My first pass said *"no learner personal data found."* **That was wrong**, and it was wrong because I read headers instead of rows. The full scan of 344 sheets / 153,793 rows / 2,539,079 cells found: *(344 was correct when measured; the corpus is now **374 sheets / 75 files** after `UpLevel Schedule Structure.xlsx` was added mid-analysis — see BUILD_LOG round four.)*

| Measure | Count |
|---|---|
| **Distinct email addresses** | **8,001** (7,976 external; 7,313 `gmail.com`) |
| **Distinct phone numbers** | **8,074** |
| **Distinct LinkedIn URLs** | **4,524** |

**Learner data is explicit, not inferred.** `Operational Metrics.xlsx!Cohort Type Wise Coaching Raw D` (12,986 rows) has literal columns `learner | learner_email | Coach | Session_Title` — every row is a named learner, their personal email, their coach and their session. `Single cohort per student all w` (9,789 rows) carries `Student Name` against weekly activity.

**And `US Instructor Cost Analysis.xlsx` is misnamed.** It is a **Paycor HR payroll export**: `Employee File Number | Full Name | Email | Department | Employement Status | LWD`, with statuses including `Exited (Resigned)` and `Exited (Terminated)`, and per-labour-code hourly rates. It is employee compensation **plus termination records** for 5,387 distinct names — materially more sensitive than the filename implies.

**Per your decisions (D4, D7–D9), all of this is in scope**: ingested, tagged `sensitive: true`, rendered in `graph.html`, behind a single Cloudflare Access rule for `@interviewkickstart.com`, with a render filter that exists but defaults to off. Instructor contact fields are dropped at extraction.

**What I still owe you as a flag, having been asked to report rather than certify:** the decision was made when the understood exposure was "instructor cost and ratings." The actual exposure is **~8,000 learners' names and personal emails plus employee termination records**, visible to every `@interviewkickstart.com` account. That is a different decision surface, and it may be a GDPR/DPDP question rather than an access-control one. I have implemented your decision as given; I am noting the changed facts once, here, so the record shows you decided with them.

**This remains the risk most likely to cause real harm, and the one least fixable after the fact.**

---

## R6b — ~~The graph is two disconnected components~~ → **36 components. Reclassified as a description, not a risk.**

**CORRECTED 2026-09-10.** "Two components" was wrong. The rendered graph has
**36**, and the shape matters:

- **1 large component of 1,144** — domain, person, instructor, module, program.
- **16 theme-stars** — each a single theme plus the workflows that point at it.
  A workflow's only edge is `belongs_to`, so themes cannot reach each other.
- ~19 small fragments — modules and programs joined to each other but not to the
  main mass.

**From a workflow you can reach its theme and its sibling workflows, and nothing
else. There is no path to any person, program, module or instructor.** This is
correct given R2 — workflow-level ownership does not exist in NP — so it is a
description of how the team works, not a defect.

### Original entry follows


**Likelihood: certain (design consequence of D2) · Impact: medium**

With `Workflow → Person` out of scope for v1, nothing joins **Component A** (`Theme`–`Workflow`, from the master file) to **Component B** (`Domain`–`Person`–`Program`–`Module`–`Instructor`, from the spreadsheets) except `File` nodes — and all 92 workflows share one `File` node, so that "bridge" is a degree-92 hub, not a path.

Consequence: the graph answers *"how do we do X"* and *"who runs Y"* well, and **cannot answer anything crossing between them**. All 8 multi-hop eval questions survive because none crosses A↔B, but a question like *"which domains are exposed by workflow 3.7 having no owner?"* is permanently unanswerable in v1.

**Mitigation:** state it plainly in `USING_THE_KG.md` so queries are not written against a path that does not exist; have `validate.py` report component count and the size of each, so if a future bridge is added the change is visible. Revisit if the cross-component question shape turns out to matter.

---

## R7 — Nobody rebuilds the graph for three months
**Likelihood: high · Impact: medium-high**

The brief asks what happens. Concretely, from what I can see in this corpus:

The graph does not visibly break — it silently becomes wrong. Instructors marked active have resigned; `Advanced ML Ops` is already `Discontinued` in the source; rating rubrics change **every quarter** (5 versions already exist); the schedule file runs to 2027 dates, so class data ages continuously. Answers stay fluent and confident while drifting from reality — the worst failure mode for a system whose purpose is trustworthy grounding.

**Precedent:** the reference implementation's `plugin.json` claims *1,072 files · 61 clients · 773 instructors*; its actual graph holds *1,833 files · 32 clients · 351 instructors*. Roughly 70% off, published, and nobody caught it. Their `USING_THE_KG.md` also references two files that no longer exist.

**Mitigation:** stamp `built_at` and source-file `mtime` range into `INDEX.md` and into every answer's citation block; have `setup` **warn when the build is older than 30 days**; auto-generate all counts (never hand-write them, per doc 04); and the B10 v2 nightly job. Also: name the owner of the rebuild (open question 4) — an unowned refresh is the thing that stops happening.

---

## R8 — Taxonomy drift
**Likelihood: medium-high · Impact: high**

The reference implementation's own docs say it plainly: *"Topic taxonomy lives in `build_graph.py` (`TOPICS`) and must stay in sync with `CANON` in `merge_instructors.py`."* They documented the hazard and shipped with it.

Additional drift sources specific to us: theme names contain `&`, `/` and inconsistent spacing, so any hand-retyping diverges; themes **5 `LEARNER SUPPORT & LEARNER EXPERIENCE`** and **9 `LEARNERS`** overlap and someone will eventually merge them in the source doc.

**Mitigation:** B2 exactly as written — `taxonomy.yaml` single source, `pipeline/lib/taxonomy.py` the only module holding the strings, and the grep test that fails the build on a literal elsewhere. Add: **version the taxonomy** (`version: 1`) and record it in every build-log line, so a graph can be traced to the taxonomy that produced it.

---

## R9 — Files I cannot parse
**Likelihood: certain but small · Impact: low**

Only **1 of 74** files is unreadable: `Taking Class Confirmation Template.png` (image, no text layer). Two traps that look like parse failures but aren't:

- `A_sample_Mock_Session_Feedback_Documentation.docx` is **not a docx** — plain UTF-8 with a wrong extension; `python-docx` raises on it. **Sniff magic bytes, don't trust extensions.**
- Naming a pipeline script `inspect.py` shadows the stdlib module `openpyxl` and `python-docx` both import, and every spreadsheet and Word file fails with a misleading `circular import` error. I lost one run to this. Worth a line in `CLAUDE.md`.

**Mitigation:** record every failure with a stated reason; assert the failure count against an expected baseline so a *new* failure is loud.

---

## R10 — Near-duplicate documents double-count entities
**Likelihood: certain · Impact: medium**

Two pairs are near-identical (doc 01): the tools/reviews export differs from its `.md` twin by **3 bytes**; the course reference pair differs by ~2 KB. Ingesting both roughly doubles every entity they contain, and no error is raised.

**Mitigation:** normalised-text hash in Pass 1; keep the newer mtime; log the skip in `BUILD_LOG.md`. Do **not** delete source files — the corpus is read-only.

---

## R11 — Graph volume swamps the entity layer
**Likelihood: medium · Impact: medium**

153,793 non-blank spreadsheet rows exist, but the mass is transactional: 74,961 rows of cost data, 39,343 of 2019–2024 metrics, 13,706 of poll responses. A naive "ingest every row" produces a graph that is 95% time-series and unusable — and `graph.json` would balloon well past the multi-MB size that already causes private-repo clone timeouts (doc 03, §8).

**Mitigation:** entity-and-relationship layer only, as scoped in doc 05. Historical metrics stay in the source files. If they ever need querying, that is a separate artefact.

---

## R12 — Program ↔ Domain join is lossy
**Likelihood: high · Impact: medium**

There is no shared key between the 42 program PDFs (`Backend Engineering EdgeUP KYP`) and the 42 owner-sheet domains (`Backend`). Filename typos create phantom distinctions (`Businees`, `Enginnering Mnagement`, `Backend␣␣`), and `KYP` vs `EdgeUP KYP` may be two products or two versions — unresolved. Several domains (`Coding TC`, `SysD TC`, `Career Coaching`) have no program PDF at all.

**Mitigation:** expect this to be the noisiest edge; route low-confidence joins to a review queue rather than asserting them; **never spell-correct a filename-derived label** (it breaks the citation back to the file). Keep `label_raw`.

---

## R13 — Skill descriptions collide and the wrong skill fires
**Likelihood: medium · Impact: medium**

Per doc 03 §4, skill selection is pure description matching against a **1,536-character combined budget**. Our proposed `workflow`, `precedent` and `coverage` skills all describe "find things about workflows in the corpus" and will compete.

**Mitigation:** write the six descriptions as a set, not individually; lead each with its distinguishing use case; consider `disable-model-invocation: true` on `setup` and `refresh` so they never fire by accident. Test by asking the six eval question shapes and checking which skill actually activates.

---

## R14 — Silent plugin component drop
**Likelihood: low · Impact: medium**

A path that escapes the plugin root fails with `"path escapes plugin directory"` and **the plugin still loads, just without that component** (doc 03 §6). No hard error. If `knowledge/` were ever referenced by an absolute or `../` path, queries would return "not in the graph" and look like a data problem rather than a packaging problem.

**Mitigation:** `${CLAUDE_PLUGIN_ROOT}` everywhere; `claude plugin validate --strict` in CI; and a `setup` command whose whole job is to prove the graph loaded and report counts — which the brief already specifies.

---

## R15 — Forgotten version bump means fixes never ship
**Likelihood: medium-high · Impact: medium**

Confirmed by the docs: *"users only receive updates when you bump it"*, and auto-update is **off by default** for non-Anthropic marketplaces. A teammate keeps a stale graph indefinitely with no warning.

**Mitigation:** `refresh` bumps `version` automatically (B10, already specified); `setup` prints the graph build date so staleness is visible at the point of use.

---

## R16 — Public exposure of the reference implementation *(not our risk, but you should know)*
**Likelihood: certain · Impact: unknown — your call**

`voldemortuk/acceler-presales-plugin` is a **public** GitHub repo, licensed `Proprietary · Acceler / Interview Kickstart`, containing client account names (`Deloitte`, `Lytx`, `e&`, `PwC`), pricing bands, margin percentages, and instructor names with LinkedIn URLs (123 distinct profile URLs). One node ID contains an individual's email address and employment history.

**Largest monetary value present: `$940M`** — 237 distinct monetary values, 47 at `$__M` scale. *(This line previously read `$537M`; corrected per doc 04.)*

**And its own documentation contradicts itself about whether the repo may be public** — see doc 04, which is the authority. The repo is public in fact; the docs site instructs readers to keep it private.

Not in our scope to fix. Flagging it because it is your company's data and it informed our decision to keep this repo private.

---

## R17 — The excluded payroll file is now reachable by a cloud identity

**Likelihood: certain (it is already true) · Impact: high**

Added 2026-09-17, after pass 0 went live.

`03-instructors/US Instructor Cost Analysis.xlsx` — the Paycor export with
employee file numbers, work and personal emails, employment status including
`Exited (Resigned)` and `Exited (Terminated)`, and per-labour-code hourly rates
for **5,387 distinct names** — is excluded from the graph by
`taxonomy.yaml -> excluded.files`.

**That exclusion is an APPLICATION RULE, not an access control.** Drive lists 9
files in `03-instructors` against the manifest's 8; the difference is this file.
The service account can read it, and pass 0 downloads it into `.drive-cache/`
before pass 1 ever consults the exclusion list. It is on disk right now.

### What would have to be true for the exclusion to fail open

Each of these is a single edit or a single mistake, and none of them trips a
test today:

1. **The path changes.** The exclusion matches an exact relative path. Someone
   renaming the file in Drive — or fixing the misleading name, which is a
   reasonable thing to do — silently un-excludes it. There is no content-based
   guard.
2. **A new extractor is added to `sources.py` naming a sheet in it.** Adding a
   source is a deliberate act, but nothing cross-checks the new entry against
   `excluded.files`.
3. **The exclusion is read but the fields are not.** `excluded.fields` drops 17
   contact patterns by header match. This workbook's headers are not the same
   strings, so a generic scan over it would keep what the field rule is meant to
   remove.
4. **Someone runs a query directly against `.drive-cache/`.** Nothing stops
   this. The cache is the whole corpus including the excluded file, sitting in
   the repo working tree, gitignored but present.
5. **Unattended operation on a worker** — the case this risk exists for. A
   scheduled pass 0 pulls the payroll file onto a shared machine on a timer, with
   no human looking at the file list. The exposure moves from one laptop to
   whatever the worker is, and its backups.

### FIXED 2026-09-17 — at the boundary

- **Pass 0 now reads the exclusion list before fetching** and skips those files,
  so the bytes never land. It also **purges** an excluded file left in the cache
  by an earlier run. Verified live: the 23 MB payroll file was present, was
  purged on the next run, and was not re-fetched.
- **`validate.py` now asserts absence from the CACHE**, not merely from
  `files.json`, under its own category `excluded-file-cache`. Verified by firing
  on the real cache before the fix.

**The two layers are NOT independent, and the tests say so.** Pass 0 and pass 1
both read `taxonomy.yaml -> excluded.files`, so a wrong entry defeats both. They
are two layers against a bug in *one pass* — see DECISIONS §A.7a.

### What remains, and must not be claimed as solved

- **The service account can still read the file on demand.** The exclusion is a
  client-side decision made by code we control, not a permission. Anyone who can
  run the pipeline, or who holds the key, fetches it by editing one line of YAML.
  **Only narrowing the Drive share changes this.**
- **The exclusion is still path-keyed.** A rename un-excludes silently. A test
  pins this so closing it cannot happen unnoticed.
- **The exclusion list has one entry.** Every other corpus file is still fetched
  in full, including `Operational Metrics.xlsx` with its 12,986 named learners.
  See `docs/CACHE-EXPOSURE.md`, which is the document for that decision.

---

## R18 — The repository was PUBLIC for eight days

**Likelihood: n/a, it happened · Impact: high**

Found 2026-09-17 by querying the GitHub API before the planned deletion, rather
than by reading our own documentation.

```
gh api repos/ANI-IN/np-autopilot  ->  "private": false, "visibility": "PUBLIC"
created 2026-09-09T17:54:03Z · forks 0 · stars 0 · watchers 0
```

**Every document in this project stated the repo was private** — README, NEXT.md,
docs/AUDIT.md, docs/DECISIONS.md §F, and **R16 above**, which flags the reference
implementation being public *while contrasting it with this repo being private*.
The assumption was written down five times and verified zero times.

**Set to private immediately on discovery.** Exposure window ≈ 8 days.

### The repository that was exposed no longer exists

The cleanest single piece of evidence for the remediation, because a repository
id is immutable and GitHub never reuses one:

| | Exposed repository | Replacement |
|---|---|---|
| `id` | **1363038448** | **1374030791** |
| `node_id` | `R_kgDOUT5Q8A` | `R_kgDOUeYLxw` |
| `created_at` | 2026-09-09T17:54:03Z | 2026-09-17T06:27:47Z |
| `private` | **false** | **true** |

Different id, different node_id, created seven hours after the deletion. The
exposed repository was not made private and was not rewritten in place — it was
deleted, and what carries the name now is a different object.

**Traffic over the window: 0 clones, 0 views, 0 referrers, 0 popular paths**,
captured before the deletion and preserved with the archive. Its calibration
caveat is in `~/np-autopilot-archive/traffic-capture/CAPTURE-NOTE.md` and must
travel with the figures.

**CALIBRATION: STILL UNSETTLED (asked twice, 2026-09-17).** The question is
whether the corpus owner ever opened the repository page in a browser during the
14-day window. It decides what the zero means, and the two readings are not
close together:

- **If the page WAS opened in a browser:** the instrument recorded **zero views
  for a session that certainly occurred**. The zero is then evidence that the
  counter does not register what we assumed it registers — it is
  **unreliable, not reassuring**, and it cannot be cited as evidence that nobody
  else fetched the repository either.
- **If all work went through the CLI:** a clone by the owner would normally
  register, so zero across both counters is weak positive evidence, still
  bounded by everything below.

**Either way the ceiling is unchanged:** GitHub's traffic API reports a 14-day
window at daily granularity and does not count every automated fetch. Public
repositories are crawled by code-search indexes and mirrors, and `git clone`
needs no permission and leaves no entry a repository owner can read. **Zero
recorded traffic is not evidence of zero copies**, under either answer. The
calibration question changes how much weight the figure can carry; it does not
change that the figure is a floor.

**Publicly readable during that window:** 3,817 instructor names, of whom **277
hiring rejections** and 1,625 mid-pipeline candidates; 39 per-instructor ratings;
136 decline rates; 140 `rejections.json` entries naming a person against an SME
hiring-tracker sheet **and row number**; 43 internal staff with titles; and every
analysis document, including doc 01 §Tier 0 and R16 itself.

**NOT exposed:** the corpus. All seven directories are gitignored and the git
history scan confirms no corpus file was ever committed, so the 8,001 emails,
8,074 phone numbers and 4,524 LinkedIn URLs were not in the public repo.

**Consequences:** the history rewrite becomes remediation rather than hygiene;
deleting the repository is clearly right rather than merely tidier; zero forks
and zero stars is **not** evidence of zero copies, since public repos are crawled
and `git clone` needs no permission; and whether this requires disclosure is a
question for legal, not for me.

**The generalisable lesson is R16's, turned inward:** we recorded another team's
repo as wrongly public while never checking our own. Full detail in
`docs/CACHE-EXPOSURE.md` §0.

---

## Summary

| # | Risk | Likelihood | Impact |
|---|---|---|---|
| R1 | Master file differs from brief | certain | high |
| R2 | ~~No workflow ownership~~ — **CLOSED, not a risk**: ownership attaches to domains, not workflows | n/a | n/a |
| R3 | Person-name duplication | certain | high |
| R4 | Freeform extraction invents entities | high | high |
| R5 | Column misalignment from blanks | high | high |
| R6 | Sensitive content — **~8,000 learner emails + payroll/termination records** | certain | high |
| R6b | Graph is two disconnected components | certain | medium |
| R7 | Graph goes stale unnoticed | high | med-high |
| R8 | Taxonomy drift | med-high | high |
| R9 | Unparseable files | certain | low |
| R10 | Near-duplicate double-counting | certain | medium |
| R11 | Transactional volume swamps graph | medium | medium |
| R12 | Program↔Domain join lossy | high | medium |
| R13 | Skill description collision | medium | medium |
| R14 | Silent plugin component drop | low | medium |
| R15 | Forgotten version bump | med-high | medium |
| R16 | Reference impl is public | certain | your call |
| R17 | Excluded payroll file reachable by the cloud identity — **fixed at fetch time 2026-09-17**; the account can still read it on demand | certain | high |
| R18 | **The repository was PUBLIC for 8 days** — 277 named hiring rejections and 1,625 candidates readable by anyone. Set private on discovery | happened | high |
