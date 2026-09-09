# 05 — Taxonomy Proposal

This is my recommendation, challenged against the evidence rather than against the hypothesis. Where I disagree with the brief I say so and show the count that drove it.

**Summary of what changes from your hypothesis:**

| Your hypothesis | My recommendation | Why |
|---|---|---|
| `Theme` | ✅ **Keep** | 16, verbatim, unambiguous |
| `Workflow` | ✅ **Keep** — make it the hub | 92 |
| `Owner` | ✏️ **Rename to `Person`** | Same humans appear as owner, delivery POC and employee; three types would triplicate them |
| `Program` | ✅ **Keep** | 42 |
| `Module` | ✅ **Keep** | Well-evidenced in curriculum sheets |
| `Instructor` | ✅ **Keep, separate from `Person`** | Externals vs internal staff — different lifecycle, different PII exposure |
| `Tool` | ❌ **DEMOTED to `workflow.tools`** | **6 tools**, 8 edges, 2 of 6 pass degree ≥ 2. See the earns-its-place test below. *(This row previously read "Keep, but it is the weakest" / "5 tools" and contradicted Tier 2. Corrected.)* |
| `Alert` | ❌ **Demote to a property on `Workflow`** | **322 of 335 clauses are unique.** As nodes they'd be 322 one-edge orphans |
| `Automation` | ❌ **Drop** | **No source exists.** The "Automations" tab the brief describes is not in the corpus |
| — | ➕ **Add `Domain` (42)** | **This is the missing bridge that carries all ownership** |
| — | ➕ **Add `File` (74)** | Provenance as a first-class hop (copied from the reference implementation) |

---

## The structural problem you need to decide on

**There is no `Workflow → Owner` relationship anywhere in the corpus.**

- The master file (92 workflows) has **no owner field** — see doc 02.
- `Domains_Courses Owners.xlsx` assigns owners to **Domains** (`Backend`, `Cloud`, `TPM`…), not to workflows.
- `IAims` assigns **objectives** to employees ("Maintain High Live Class Ratings"), which resemble workflows but do not map to them 1:1 and use different wording.

So the graph can answer **"who owns the Cloud domain?"** (`Animesh`, secondary `Utkarsh, Shashi`) with a citation. It **cannot** answer **"who owns *Instructor Rating Communication*?"** (workflow 8.2) — that fact does not exist in any file.

I will not invent it. Three honest options:

| Option | What it costs | What you get |
|---|---|---|
| **A. Ship without it** (my recommendation for v1) | `owner` queries work at domain level only; the `owner` skill must say "not in the corpus" for workflow-level asks | Zero fabrication. Ships now. |
| **B. You fill a `workflow-owners.yaml`** — 92 rows, one owner each | ~45–60 min of your time, once | The single highest-value question shape becomes answerable. **This is the best return on effort in the whole project.** |
| **C. Infer from `IAims` objectives** | Cheap to code | **Reject.** Objective text ≠ workflow text; it would be a guess wearing a citation. |

**Decision trail.** D2 (doc 08) initially chose **A**. That was **reversed on 2026-09-09** in favour of **B**, on the evidence that dropping `Workflow → Person` leaves the graph in two disconnected components (Q5, R6b) — i.e. two graphs, not one. **B is now the chosen path.** `config/workflow-owners.yaml` is generated as a 92-row stub by `pipeline/gen_workflow_owners.py`; the pipeline reads it if present and omits the edges if absent, so it still blocks nothing.

---

## Node types — evidence table

### Tier 1 — strongly evidenced, build these

| Type | Instances | Source files | Earns its place? |
|---|---|---|---|
| **`Theme`** | **16** | `00-master/Team_Task___Workflow_Inventory` (`##` headings) | **Yes.** Closed, verbatim, every workflow has exactly one. |
| **`Workflow`** | **92** | same (`###` headings) | **Yes — this is the hub.** Carries `steps` (606 total, mean 6.6), `effort`, `alerts`. |
| **`Domain`** | **42** | `00-master/Domains_Courses Owners.xlsx!Sheet1` | **Yes, and it is the most important addition.** Without it, `Person` connects to nothing. |
| **`Person`** | **~28** | Owners sheet (owner, secondary, delivery POC) + `IAims` (8 with `IK-` IDs) | **Yes**, but see the name-variant problem in doc 02 — 38+ distinct strings for ~28 humans. |
| **`Program`** | **42** | `04-programs/CUR-*.pdf` filenames + content; cross-checked against `ALL-COURSES-COMPLETE.md` | **Yes.** Note it is **not** the same as `Domain` — see below. |
| **`Instructor`** | **~200–400** (UNKNOWN, needs Pass 1) | `Instructors Directory`, `SME Tracker`, `SME database`, `AgenticAI Training Plan`, `New Combined Schedule!Instructor Data`, curriculum sheets | **Yes**, kept separate from `Person`. |
| **`Module`** | **~150–300** (UNKNOWN, needs Pass 1) | `Data and Management.xlsx` (16 sheets), `Resource Collection Mastersheet` (14 sheets), program PDFs | **Yes.** Every curriculum sheet is Module → Resource → Instructor. |
| **`File`** | **74** | the corpus itself | **Yes.** Makes "cite your source" a single hop, per doc 04. |

### Tier 2 — weak, include with eyes open

| Type | Instances | Evidence | Verdict |
|---|---|---|---|
| **`Tool`** | **6** in the workflow inventory | degree test below | **DEMOTED to a property.** Fails the same test that demoted `Alert`. |

### Rejected

| Type | Why rejected |
|---|---|
| **`Alert`** | **335 clauses, 322 distinct.** Only **one** substantive clause repeats across workflows (*"ownership is unclear"*, 3×). The other "repeat" is the literal placeholder `TBD`, in **12 of 92 workflows (13%)**. As nodes: +322 nodes, each with exactly one edge — a 3× graph inflation that answers nothing a property can't. **Model as `Workflow.alerts: [string]`** and make them full-text searchable. |
| **`Automation`** | **No source.** The brief's "Automations" tab (owner, status, build type, priority) does not exist in this corpus. Adding the type would create an empty node class. **Drop it until the source file appears.** |

### `Tool` — the earns-its-place test, applied

Same test that demoted `Alert`: **a node type earns its place only if its instances have degree ≥ 2.** A degree-1 node adds a hop without enabling any traversal a property could not serve.

| Tool | Degree | Workflows |
|---|---|---|
| `Zoom` | **2** PASS | `2.4 New Instructor Onboarding`, `7.6 Live Class Test Setup` |
| `Uplevel` | **2** PASS | `8.3 Refund Analysis and Tracking`, `8.5 Learner Journey / Sales Call Analyzer` |
| `LinkedIn` | 1 fail | `2.2 Instructor Hiring and Evaluation` |
| `Discord` | 1 fail | `2.4 New Instructor Onboarding` |
| `GitHub` | 1 fail | `4.12 Weekly Agentic AI Module / Repository Update` |
| `Google Form` | 1 fail | `7.6 Live Class Test Setup` |

**6 nodes. 8 edges. 2 of 6 (33%) pass.** Compare `Alert`: 321 distinct clauses, **1** with degree ≥ 2 (**0.3%**).

`Tool` is ~100× better than `Alert` by pass-rate — **but it fails on absolute volume.** Eight edges across 92 workflows is a tag, not a relational layer, and *"what else uses Zoom?"* is answerable from a property by text match.

**Verdict: demote to `workflow.tools: [string]`,** exactly as with `alerts`. I am not applying a strict test to one type and waving another through.

**Promotion trigger:** if we later ingest Uplevel/Drive links from the 30 curriculum sheets as first-class `Resource` nodes, `Tool` gains real degree via `Resource → Tool`. Revisit then, not before.

*(Correction to my first draft: I said 5 tools and put Uplevel in workflows `4.8`/`4.15`. Both wrong — 6 tools, and Uplevel is in `8.3`/`8.5`.)*

### Should `Domain` and `Program` really be separate?

Yes, and this is the subtlest call in the taxonomy.

- **`Domain`** (42) is an *internal ownership and delivery unit*: `Backend`, `Cloud`, `SRE`, `Coding TC`, `Agentic AI - SWE`. It is what the owners sheet, the schedule sheets and the Slack-group sheet are keyed on.
- **`Program`** (42) is a *sellable product*: `Backend Engineering EdgeUP KYP`, `Cloud Architect Interview Preparation Program`.

They overlap but are **not** 1:1. `Backend` (domain) relates to *two* programs (`Backend Engineering EdgeUP KYP`, `Backend Interview Preparation Program`). And several domains (`Coding TC`, `SysD TC`, `Career Coaching`) have **no** program PDF at all.

**The join between them is by hand and it is lossy** — there is no shared key (doc 02, contradiction 10). Expect `Domain ↔ Program` to be the noisiest edge in the graph, and expect a review queue.

---

## Edge vocabulary — closed, 8 types

I dropped two of your seven, kept five, and added three. Each has a direction and a real example.

| Edge | From → To | Real examples |
|---|---|---|
| **`belongs_to`** | `Workflow` → `Theme` | `2.6 Instructor Performance and Rating Review` → `2. INSTRUCTORS`; `16.1 Cohort API Key Access & Cost Control` → `16. TECHNICAL / AI OPERATIONS` |
| **`owned_by`** | `Domain` → `Person` (and `Workflow` → `Person` **iff** you supply `workflow-owners.yaml`) | `Cloud` → `Animesh Kumar` (primary); `ML Switch-up (Adv ML)` → `Kalindi` |
| **`supported_by`** *(new)* | `Domain` → `Person` | `Backend` → `Simran Khemlani` (Delivery Team Member); `Cloud` → `Utkarsh Raj` (secondary owner). **Separates "accountable" from "assisting"** — the owners sheet has three distinct people-columns and collapsing them into `owned_by` would lose that. |
| **`part_of`** | `Module` → `Program`; `Program` → `Domain` | `Applied Cryptography` → `Security Engineering EdgeUP KYP`; `Backend Engineering EdgeUP KYP` → `Backend` |
| **`teaches`** | `Instructor` → `Module` | `Suresh Venkatesan` → `SQL Programming` (`Data and Management!Data Instructors`); `Anshaj Khare` → `Python for GenAI` (`AgenticAI Training Plan!M_SME_App. Agentic AI`) |
| **`uses_tool`** | `Workflow` → `Tool` | `2.4 New Instructor Onboarding & Training` → `Discord` (*"add instructor to Discord"*); `3.3 Technical / Demo Troubleshooting` → `Zoom` |
| **`depends_on`** | `Workflow` → `Workflow` | `3.6 Pre-Class → Live Class → TCS → ARS Delivery Orchestration` → `3.1 Live Class Readiness Management`; `8.2 Instructor Rating Communication` → `8.1 Weekly Ratings Reporting and Sharing`. **Low confidence — must be extracted conservatively or hand-curated.** |
| **`sourced_from`** *(new)* | *any node* → `File` | `92 Workflow` nodes → `File:Team_Task___Workflow_Inventory`; `Cloud` → `File:Domains_Courses Owners.xlsx`. **Every node gets at least one. This is the provenance edge.** |

**Dropped from your hypothesis:**
- **`triggers`** — it was meant for `Workflow → Alert`. With `Alert` demoted to a property, it has nothing to connect.
- **`automates`** — it was meant for `Automation → Workflow`. `Automation` has no source.

---

## Theme list — verbatim, exact count

Taken verbatim from `00-master/Team_Task___Workflow_Inventory`. **Nothing invented, nothing renamed.**

| # | Theme (verbatim) | Workflows |
|---|---|---|
| 1 | `PROGRAM STRATEGY & SALES ENABLEMENT` | 3 |
| 2 | `INSTRUCTORS` | 9 |
| 3 | `LIVE CLASS OPERATIONS` | 7 |
| 4 | `CONTENT / CURRICULUM` | 15 |
| 5 | `LEARNER SUPPORT & LEARNER EXPERIENCE` | 6 |
| 6 | `INTERVIEW PREPARATION & RETENTION` | 7 |
| 7 | `ASSESSMENTS & TESTING` | 7 |
| 8 | `OPS` | 5 |
| 9 | `LEARNERS` | 3 |
| 10 | `COHORT OPERATIONS` | 3 |
| 11 | `B2B CURRICULUM & CLIENT OPERATIONS` | 5 |
| 12 | `MASTERCLASS OPERATIONS` | 5 |
| 13 | `RESEARCH & BENCHMARKING` | 4 |
| 14 | `DOCUMENTATION & KNOWLEDGE MANAGEMENT` | 8 |
| 15 | `METRICS / QUALITY / CONTINUOUS IMPROVEMENT` | 4 |
| 16 | `TECHNICAL / AI OPERATIONS` | 1 |

**Exact count: 16 themes, 92 workflows.**

Two notes:
- The file's own footer says **91** — it is wrong by one (doc 02).
- Themes **9 `LEARNERS`** and **5 `LEARNER SUPPORT & LEARNER EXPERIENCE`** overlap heavily: workflow `9.2 Learner Issue and Support Analysis` vs `5.5 Learner Issue Investigation`, and `9.3 Learner Feedback and Experience Improvement` vs `5.6 Recurring Learner Issue Analysis`. **I am keeping both verbatim as instructed** — but flag that `coverage` queries will look duplicated, and a future merge is worth considering with the team.

---

## Ambiguities I hit, with a recommendation for each

| # | Ambiguity | Recommendation | Confidence |
|---|---|---|---|
| 1 | `Karthika S` (IAims IK-115) vs `Karthika Pai` (SME Tracker) | ✅ **RESOLVED by D3 — two different people.** Both enter `people.yaml` as separate canonical entries with a comment pinning the confirmation so no fuzzy pass re-merges them. There is also a **third**: `Karthika Saran` (15 rows, US/Canada instructor). | Confirmed |
| 2 | `KYP` vs `EdgeUP KYP` (`CUR-EM - KYP` vs `CUR-Enginnering Mnagement EdgeUP KYP`) | ✅ **RESOLVED by D5.** `KYP` is a **doctype**, joined by `has_doc`. The two files remain **two Programs** because EdgeUP is itself the product line. The collapse merges nothing — see the corrected program count below. | Confirmed |
| 3 | Filename typos (`Businees`, `Enginnering Mnagement`, `Backend␣␣`) | Normalise whitespace only; **do not spell-correct**. A corrected name won't match the source file and breaks citation. Record `label_raw` alongside. | 90% |
| 4 | Is `Masterclass` a Theme or a Domain? Both exist. | **Both, and they are different things** — theme 12 is the *work of running* masterclasses; `Coding Masterclass (DSA)` is a *delivery unit*. Keep separate; `Theme` and `Domain` never share an ID namespace. | 80% |
| 5 | `Instructor` vs `Person` — an internal staffer who also teaches | Keep separate types; allow **both** nodes for the same human, joined by a `same_as` note in `people.yaml`, not an edge. Merging them merges PII exposure classes. | 75% |
| 6 | `Domain` "Cadence" column contains `Discontinued` (r40) | Property on `Domain`, not a status node. Add `active: false`. | 90% |
| 7 | Which `IAims` quarter is current? 5 rubric sheets disagree on thresholds | **Do not ingest rubric thresholds in v1.** They are quarter-scoped and would present a stale number as fact. | 85% |
| 8 | Workflows 13% `Alerts: TBD` | Store as empty list, and have `validate.py` report *"12 workflows have no alert conditions"*. Do not store the literal string `TBD`. | 95% |
| 9 | Two near-duplicate file pairs (doc 01) | Ingest the newer of each pair; log the skip. | 85% |
| 10 | Theme 9 vs Theme 5 overlap | Keep verbatim; flag in `coverage`. | 90% |

---

## `taxonomy.yaml` — superseded by the real file

**The YAML formerly inlined here is withdrawn.** It had drifted from this
document and from doc 08: it still declared `tool` as a node type with
`expect: 19` (a figure appearing in no document), still carried a `uses_tool`
edge into a demoted type, wrote `expect: ~28` for `person` (which YAML parses as
**null**, not "approximately 28"), left `instructor` and `module` at `null` after
both had been measured, gave `owned_by` a list-valued source including
`workflow`, and gave `part_of` list-valued endpoints that permitted
`module → domain` and `program → program`.

**The authoritative file is now `config/taxonomy.yaml` (version 2).** It is the
single source of truth; `pipeline/lib/taxonomy.py` is the only module allowed to
read it, and a grep test fails the build on any type string written as a literal
elsewhere.

Summary of what version 2 declares:

| | Count |
|---|---|
| Node types | 9 — theme, workflow, person, domain, program, doctype, module, instructor, file |
| Edge types | 11 — all with a single fixed from-type and to-type |
| `tool` as a node type | removed; `workflow.tools: [string]` instead |
| `has_doc` (Program → Doctype) | added, per D5 |
| `workflow_owned_by` (Workflow → Person) | added, per the D2 reversal |
| `delivered_by` (Domain → Person) | added — the owners sheet's Delivery Team Member column was unmodelled |
| `sensitive` property | added, mandatory on every node, per D4/D9 |

**Corrected program count.** D5 does **not** reduce it. Stripping `KYP` from all
42 filenames merges **zero** pairs, because no two documents describe the same
product: the 42 split into 17 `EdgeUP`, 15 `Interview Preparation Program`, 7
`KYP`-only and 3 other, and `TPM EdgeUP KYP` / `TPM-KYP` are two products
precisely because D5 says EdgeUP *is* the product. Doc 08 Q1's statement that D5
"reduces the program count" is **withdrawn**. Program remains **42**; what D5
adds is 42 `has_doc` edges into 3 doctype nodes.
