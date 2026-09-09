# np-autopilot

A knowledge graph over the New Programs corpus, packaged as a Claude Code plugin.

**Read the limitations before the features.** They are first on purpose.

---

# What you should not trust

## Every count is a floor, not a total

**127 of 374 worksheets have been read by an entity scan.** The rest breaks down
as 37 sheets in the excluded payroll file, 139 sheets of learner data (both
deliberate), and **71 sheets / 4,572 rows that are a genuine blind spot**.

`person`, `instructor` and `module` carry **no expected count** in
`config/taxonomy.yaml` for this reason. Never quote one as a total.

**Coverage was audited per FILE for six rounds before anyone audited it per
SHEET.** That hid the biggest single finding in the project: `New Combined
Schedule.xlsx` had 1 of 62 sheets read, and the other 44 held the entire class
delivery log. A file counted as "read" while 98% of it was not.

## The master spreadsheet has never been located

The brief's taxonomy derives from an "NP Autopilot" spreadsheet with
`Automations`, `All Tasks` and `To-Do & Working Notes` tabs. **No such file is in
the corpus.** If it exists in Drive, `Owner` and `Automation` may return as node
types and the taxonomy is redone.

## The filters had a bias, and it ran for several rounds

Six name-shape rules were rejecting candidates outright. Re-applied to today's
population they would exclude **336 people (8.8%)**:

- **84 for holding a PhD, Dr, MD or Jr** — two thirds of everything the
  punctuation rule removed
- **28 for a middle initial** (`Benjamin O. Tayo`, `Minh P. Vo`)
- **4 of 5 stopword hits were people named `Will`** — the word is in the stopword
  list and is also a first name
- **22 for long multi-part names, disproportionately South Asian**
  (`Achanta Sri Surya Srinivasa Sai Kiran`)

**Noise removal that correlates with a category of person is not noise removal.**
All six now flag rather than reject. Full audit in `10-threshold-audit.md`.

## The junk rate

**No non-people found in a sample of 50. Upper bound ~6% at 95% confidence.**
Not "0%" — a point estimate of zero is a claim a 50-item sample cannot support.

## The module layer hangs off instructors, not programs

**671 of 922 modules (73%) connect only through `teaches`.** `contains` is 351
edges against 2,239 `teaches`, and `contains` is itself inferred via domain —
there is no row-level program↔module pairing anywhere in the corpus. Hide
instructors and the module layer shatters into 772 components.

## What the graph cannot answer

- **Workflow ownership.** It does not exist — everyone in NP does every kind of
  work. 92 workflows, all blank, and that is the correct final state.
- **Workflow sequencing.** `depends_on` has zero evidence.
- **Anything crossing from a workflow to a person, program or module.** From a
  workflow you reach its theme and its sibling workflows. No path exists onward.
- **`expert_in` is not teaching evidence.** 1,155 edges, ~92% Google Form
  responses. 320 also went through a confirmed alias — two inference steps.

---

# What it holds

`5,048 nodes · 36,677 edges` at plugin **v0.1.2**.

| nodes | | edges | |
|---|---|---|---|
| instructor | 3,817 | sourced_from | 32,656 |
| module | 922 | teaches | 2,239 |
| person | 43 | expert_in | 1,155 |
| domain | 42 | contains | 351 |
| program | 42 | belongs_to | 92 |
| workflow | 92 | owned/supported/delivered_by | 156 |
| theme | 16 | covers | 28 |

**Eval: 20/22 on the original set, 5/5 on five questions written fresh against
the finished graph. Zero fabrications. 4/4 on the correctly-unanswerable set.**

## Commands

| command | |
|---|---|
| `/staffing <domain>` | Who can teach it. **Tiers never merged**: taught → HR record → form response → alias-matched form response. Leads with absence. |
| `/coverage` | What is missing. Never reports workflows as missing an owner. |
| `/workflow <id>` | Steps, effort, alerts, tools. Lookup, not reasoning. |
| `/domain-owner <domain>` | Primary, secondary, delivery POC, cadence. |
| `/setup` | Graph counts, build date, and the Drive-deferral warning. |

---

# Running it

## Refresh

```
python3 pipeline/refresh.py
```

Runs all six passes, validates, prints a delta, **bumps the version, and stops.
It never commits.**

**The version bump is automatic AND enforced.** `validate.py` hard-fails if
`graph.json` content changed while `plugin.json` did not:

> *graph.json content changed but plugin.json is still 0.1.2. Teammates would
> never receive this build.*

Automatic-and-trusted is how a graph nobody can receive gets shipped.

**Determinism, verified:** a second refresh with no corpus change reports
`IDENTICAL — nodes and edges byte-identical` and does not bump.

## Passes

Pass 0 is the only one that touches the network; pass 1 only reads local files.
**Do not fuse them** — re-parsing must never re-download.

| 0 | `00_fetch_drive.py` | **never run** — deferred to v2 |
| 1 | `01_walk_corpus.py` | discovery, integrity, manifest |
| 2 | `02_extract.py` | candidates + rejection log |
| 3 | `03_resolve.py` | identity; fuzzy **proposes only** |
| 4 | `04_build_graph.py` | assembly |
| 5 | `05_render_html.py` | `graph.html` |
| — | `validate.py` | 17 categories, all fault-injection tested |

**Manifest rules:** a **changed or removed** file is a hard fail; an **added**
file is reported and ingested. `--rebaseline` accepts a change explicitly and
records it in BUILD_LOG — never use it to make an unexplained diff go away.

---

# Deferred and decided

## Drive ingestion — v2

`00_fetch_drive.py` exists and **has never run**. The graph is built from a
hand-exported local folder. Consequences: the master spreadsheet question stays
open, and **click-to-open a source file cannot work** — browsers block `file://`
links from HTML, so `file.drive_url` stays null and paths render as unlinked
text.

Setup, when you do it: enable the Drive API, **OAuth consent screen user type
Internal** (External + Testing expires the refresh token after 7 days and the
pipeline dies with `invalid_grant`), Desktop app credentials, scope
`drive.readonly` and nothing wider.

## Distribution — single-owner, deliberately

**`ANI-IN/np-autopilot`, private, no collaborators. This overrides D10 for v1.**

- **No teammate can install anything.** A private repo with no collaborators is
  unreachable by `/plugin marketplace add`.
- **Moving it later changes the marketplace URL**, which breaks
  `/plugin marketplace add` for anyone already installed — and removing a
  marketplace auto-uninstalls its plugins, so it is a remove-and-reinstall.
- **That cost scales with adoption. Move it before the second user, not after
  the tenth.**

Target state under D10 is a GitHub Organization + team. Honest first-time install
cost is **four steps**, not two: a GitHub account with org access, `gh auth
login`, `/plugin marketplace add`, `/plugin install`.

**Offboarding:** removing someone from the org stops *future* updates. It does
**not** remove the graph snapshot already in their local plugin cache.

## Cloudflare Access — documented, NOT configured

Nothing has been set up. When distribution becomes urgent:

- One rule: email domain `@interviewkickstart.com` (D7). No per-node filtering in
  the render (D8).
- The `sensitive` flag drives a render filter that **exists and defaults to off**
  (D9). It is not the access control.
- **Before enabling any of this**, re-read `07-risks.md` R6: the graph carries
  ratings and written judgements about named individuals, and the render already
  excludes 1,842 in-pipeline/rejected/lapsed instructors including 255 hiring
  rejections. Access control is not a substitute for that exclusion.

## Not built

**Refresh v2 (nightly)** needs pass 0 working. When built, it should use a
**service account** with the folder shared to its address — a headless job cannot
complete a browser consent, and a job tied to one person breaks when they leave.

---

# The corpus is read-only

It mirrors a live Drive folder and **has already changed under an active
analysis**. Filename typos (`Businees`, `Enginnering Mnagement`) are load-bearing
citation keys — correcting one breaks provenance.

## Exclusions

`03-instructors/US Instructor Cost Analysis.xlsx` — a Paycor payroll export with
termination records for 5,387 people. 17 contact-field patterns are dropped at
extraction. Cohort counts, session titles, coach assignments and names are kept.
Machine-readable list in `config/taxonomy.yaml` under `excluded:`.

**Known cost:** that file is the only corpus source for 14 of the 25 internal
`@interviewkickstart.com` addresses.

---

See `CLAUDE.md` for the five working rules, `knowledge/USING_THE_KG.md` for
traversal guidance, `BUILD_LOG.md` for every build and finding.
