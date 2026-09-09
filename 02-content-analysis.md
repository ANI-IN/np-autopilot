# 02 — Content Analysis

Read order as instructed: master file first, in full, then everything else.

---

## ⚠ First, the biggest finding: the master file is not what the brief describes

The brief says:

> The single most important file is a spreadsheet, **NP Autopilot - The AI Operating System for New Programs**, with three tabs: **Automations**, **All Tasks**, **To-Do & Working Notes**.

**No such file exists in the corpus.** There is no file with that name, no `.xlsx` with those three tabs, and no `Automations` or `To-Do` tab anywhere in the 344 worksheets I enumerated. *(344 was correct when measured; the corpus is now **374 sheets / 75 files** after `UpLevel Schedule Structure.xlsx` was added mid-analysis — see BUILD_LOG round four.)*

What exists instead is `00-master/Team_Task___Workflow_Inventory` — a **52 KB extensionless UTF-8 Markdown document** (a Google Docs export), 599 lines. It is unmistakably the intended skeleton: it is titled *"CONTEXT: Team Task & Workflow Inventory"*, it enumerates the recurring tasks, and it has exactly the field structure the brief describes for "All Tasks".

**But its field set is different from the brief's:**

| Brief says "All Tasks" has | Actually present? |
|---|---|
| Theme | ✅ Yes — as `##` section headings |
| Step-by-step workflow | ✅ Yes — `- Workflow:` on every task |
| Hours-per-cycle estimate | ✅ Yes — `- Effort:` on every task |
| Explicit "⚠ Alert if" condition | ✅ Yes — `- Alerts:` on every task (though not written as "⚠ Alert if") |
| **Owner** | ❌ **Absent. Zero owner assignments.** |
| Status / Priority / Build type (from "Automations") | ❌ **Absent — no Automations tab exists** |

The document's own field key confirms it — there are exactly four fields:

> - **Task** — the work / responsibility
> - **Workflow** — the step-by-step process (→ = next step)
> - **Effort** — typical time, weekly WIP estimate
> - **Alerts** — conditions that mean the task is off-track or needs escalation

I verified by counting: `- Workflow:` appears **92** times, `- Effort:` **92** times, `- Alerts:` **92** times. The strings `Owner:`, `Status:`, `Priority:`, `Automation` appear **zero** times as field labels. The word "owner" occurs 12 times, but only *inside* workflow prose and alert text ("identify owner", "ownership is unclear") — never as an assignment.

**Consequence, and it is a big one:** the node type `Owner` and the node type `Automation` from your hypothesis have **no source in the master file**. `Owner` is rescued from a different file (below). `Automation` is not rescued at all. See doc 05.

### Second finding: the master file miscounts itself

Its last line reads:

> `END OF CONTEXT — 91 tasks across 16 themes.`

There are **92** tasks. I counted `###` headings (92), and summed per-theme counts (3+9+7+15+6+7+7+5+3+3+5+5+4+8+4+1 = 92). The self-reported 91 is wrong by one. Trivial in itself, but it tells you the footer is hand-maintained and already drifting — which is the argument for auto-generating `INDEX.md`.

---

## 2.1 Themes and workflows — verbatim

Taken verbatim from `00-master/Team_Task___Workflow_Inventory`. Theme names are reproduced exactly as written, including the ampersands, the slashes and the ALL-CAPS.


### Theme 1. PROGRAM STRATEGY & SALES ENABLEMENT  _(3 workflows)_

- `1.1` Program Persona / Target Audience Definition
- `1.2` Market Opportunity / Jobs / Salary Research
- `1.3` Orientation / Sales Deck Content Refresh

### Theme 2. INSTRUCTORS  _(9 workflows)_

- `2.1` JD Creation
- `2.2` Instructor Hiring and Evaluation
- `2.3` Strong NP Leads: Identify the Most Suitable Instructor
- `2.4` New Instructor Onboarding & Training
- `2.5` Instructor Training and Module Readiness
- `2.6` Instructor Performance and Rating Review
- `2.7` AMA / Technical Coaching / Assignment Review Instructor Assignment
- `2.8` Session Context Briefing for New / Replacement Instructor
- `2.9` SME Cost Analysis & Monthly Report

### Theme 3. LIVE CLASS OPERATIONS  _(7 workflows)_

- `3.1` Live Class Readiness Management
- `3.2` Live Class Issue Resolution
- `3.3` Technical / Demo Troubleshooting
- `3.4` Post Class Quality Review
- `3.5` Live Session Improvement
- `3.6` Pre-Class → Live Class → TCS → ARS Delivery Orchestration
- `3.7` Class Reschedule / Cancellation Exception Management

### Theme 4. CONTENT / CURRICULUM  _(15 workflows)_

- `4.1` New Curriculum / Module Development
- `4.2` Existing Module Revamp
- `4.3` Curriculum Outline / Rough Draft Creation
- `4.4` SME Curriculum Review
- `4.5` Curriculum QA
- `4.6` Curriculum Gap Analysis
- `4.7` Ticket Analysis for Content Gaps
- `4.8` Video Timestamping and Resource Curation
- `4.9` SME Discussion & Outline Development
- `4.10` Emerging Technology Curriculum Research
- `4.11` GenAI Market / Competitive Research
- `4.12` Weekly Agentic AI Module / Repository Update
- `4.13` Module Goal / Overview / Roadmap Packaging
- `4.14` Capstone / Project Guidance & Rubric Session Design
- `4.15` KYP Updation & Maintenance

### Theme 5. LEARNER SUPPORT & LEARNER EXPERIENCE  _(6 workflows)_

- `5.1` Learner Profile / Resume Analysis
- `5.2` Program / Domain Recommendation
- `5.3` Learning Path Guidance
- `5.4` Learner to SME Mapping
- `5.5` Learner Issue Investigation
- `5.6` Recurring Learner Issue Analysis

### Theme 6. INTERVIEW PREPARATION & RETENTION  _(7 workflows)_

- `6.1` Interview Preparation Support
- `6.2` Interview Experience Documentation
- `6.3` Interview Round Guide Development
- `6.4` Interview FAQ Development
- `6.5` Resume Template Development
- `6.6` Interview Ticket Analysis
- `6.7` Retention / Refund Issue Analysis

### Theme 7. ASSESSMENTS & TESTING  _(7 workflows)_

- `7.1` Pre-Assessment Design
- `7.2` Post-Assessment Design
- `7.3` Question Bank Development
- `7.4` Question Bank Clustering
- `7.5` Assessment Difficulty Calibration
- `7.6` Live Class Test Setup
- `7.7` Assessment QA

### Theme 8. OPS  _(5 workflows)_

- `8.1` Weekly Ratings Reporting and Sharing
- `8.2` Instructor Rating Communication
- `8.3` Refund Analysis and Tracking
- `8.4` Cross-Channel Ticket Analysis
- `8.5` Learner Journey / Sales Call Analyzer & Next-Best Action

### Theme 9. LEARNERS  _(3 workflows)_

- `9.1` Low-Rated Class Learner Outreach
- `9.2` Learner Issue and Support Analysis
- `9.3` Learner Feedback and Experience Improvement

### Theme 10. COHORT OPERATIONS  _(3 workflows)_

- `10.1` New Program Readiness
- `10.2` Cohort Setup
- `10.3` Module Scheduling

### Theme 11. B2B CURRICULUM & CLIENT OPERATIONS  _(5 workflows)_

- `11.1` B2B Client Requirement Analysis
- `11.2` B2B Module Customization
- `11.3` B2B Delivery Tracking
- `11.4` B2B Quality Monitoring
- `11.5` B2B Instructor Scheduling & Session Confirmation

### Theme 12. MASTERCLASS OPERATIONS  _(5 workflows)_

- `12.1` Masterclass Topic Identification
- `12.2` Masterclass Planning
- `12.3` Masterclass Content Development
- `12.4` Masterclass Delivery Support
- `12.5` Masterclass Performance Review

### Theme 13. RESEARCH & BENCHMARKING  _(4 workflows)_

- `13.1` Requirements + JD Analysis
- `13.2` Competitive Curriculum Research
- `13.3` Technology Benchmarking
- `13.4` Free Resource Research

### Theme 14. DOCUMENTATION & KNOWLEDGE MANAGEMENT  _(8 workflows)_

- `14.1` SOP Creation
- `14.2` Workflow Documentation
- `14.3` Learner Guide Creation
- `14.4` Technical Guide Creation
- `14.5` GitHub / Repository Documentation
- `14.6` Repository Cleanup
- `14.7` Instructor Teaching Guide Creation
- `14.8` AMA / Technical Coaching Context Note

### Theme 15. METRICS / QUALITY / CONTINUOUS IMPROVEMENT  _(4 workflows)_

- `15.1` Class Rating Analysis
- `15.2` NPS / Learner Feedback Analysis
- `15.3` Recurring Ticket Analysis
- `15.4` Continuous Improvement Review

### Theme 16. TECHNICAL / AI OPERATIONS  _(1 workflows)_

- `16.1` Cohort API Key Access & Cost Control


**Totals: 16 themes, 92 workflows.**

> **Count for the record: 16 themes, 92 workflows.** The brief says "roughly 80 workflows"; the file's own footer says 91; the truth is 92.

---

## 2.2 Every person appearing as an owner, with spelling variants

**Source: `00-master/Domains_Courses Owners.xlsx` — this is the only file in the corpus that assigns ownership.** Sheet `Sheet1` maps 42 domains/programs to a Delivery Team Member, a Primary Owner, Secondary Owners and a Cadence.

This is where person-name duplication is going to hurt. Here is every distinct spelling I found, grouped by who I believe they are:

| Canonical (proposed) | Variants found | Evidence |
|---|---|---|
| Animesh Kumar | `Animesh`, `Animesh Kumar` | `Owners!Sheet1` uses short form; `Owners!For Slack` r019 and `IAims!Q42025` (ENo **IK-398**) use full form |
| Adil Panwar | `Adil`, `Adil Panwar` | `Owners!Sheet1` short; `For Slack` r019 full; `IAims!Q226` r040 (**IK-254**) full |
| Shashi Bhushan Kumar | `Shashi`, `Shashi Bhushan Kumar` | `Owners!Sheet1` short; `IAims!Q226` (**IK-013**) full |
| M Prasad Khuntia | `Prasad`, `M Prasad`, `M Prasad Khuntia` | All three occur. `Owners!Sheet1` r028 `M Prasad`; `For Slack` r002 `Prasad`; `IAims!Q1 2026` (**IK-294**) full |
| Utkarsh Raj | `Utkarsh`, `Utkarsh Raj` | `Owners!Sheet1` short; `For Slack` r003 full; `IAims!Q226` r039 (**IK-250**) full |
| Navdeep Singh | `Navdeep`, `Navdeep Singh` | `Owners!Sheet1` r029/r041 short; `IAims!Q226` (**IK-271**) full |
| Karthika S | `Karthika`, `Karthika S`, `Karthika Pai` (?) | `IAims!Q226` (**IK-115**) = `Karthika S`. `SME Tracker!Q4-24` contains `Karthika Pai` — **may be a different person**. UNKNOWN. |
| Kalindi | `Kalindi`, `Kalindi .` | `IAims!Q226` (**IK-113**) literally reads **`Kalindi .`** — a trailing space-dot. No surname anywhere. |
| **Srushith** ⚠ | `Srushit`, `Srushith`, `Srusith` | **Three spellings, all in the same file.** `Owners!Sheet1` r036/r037 `Srushith`; r043 `Srusith`; `For Slack` r002 `Srushit`, r004 `Srushith` |
| **Swaroop** ⚠ | `Swarup`, `Swaroop` | `Owners!Sheet1` r029 `Swarup`; `For Slack` r012 `Swaroop` |
| **Tanmaya** ⚠ | `Tanmaaya`, `Tanmaya` | `Owners!Sheet1` r042 `Tanmaaya`; `For Slack` r006 `Tanmaya` |
| Uday | `Uday` | consistent |
| Deval | `Deval` | consistent |
| Pooja | `Pooja` | consistent |
| Anmol | `Anmol` | consistent |
| Abhinav Rawat | `Abhinav Rawat`, `Abhinav` | `For Slack` r008 full; `SME Tracker!Hiring Requirements` uses `Abhinav`, `Abhinav/Vartika` |
| Rakshit Kapoor | `Rakshit Kapoor` | consistent |
| David Reed | `David Reed` | consistent |

**Delivery Team Members** (a distinct role column, also people): `Simran` (= `Simran Khemlani`, per `New Combined Schedule!Delivery POC`), `Rupali`, `Tamanna`, `Kunal`, `Sourish`, `Anshuman`, `Abhishek`, `Tushar`, `Sinchana`, `Harsha`, `Muskan`, `Utkarsh`, `Kalindi`, `Karthika`.

**Counts:** ~18 distinct people in owner/secondary-owner roles, ~14 in delivery-team roles, with overlap. **Roughly 25–30 distinct internal people, expressed in at least 38 distinct strings.**

### Why this is the number-one risk
Three separate spellings of *Srushith* exist **inside one spreadsheet**. Fuzzy matching would probably catch `Srushit`/`Srushith`/`Srusith` — but it would **also** merge `Swarup`/`Swaroop` correctly and might merge `Karthika S`/`Karthika Pai` **incorrectly**. That last one is a genuine ambiguity I cannot resolve from the files.

**⚠ CORRECTION — I was wrong about employee IDs.** My first draft called the `IAims` employee numbers "the only stable identifiers in the corpus" and recommended keying `people.yaml` on them. A full scan of all 17 `IAims` sheets proves they are **neither unique nor stable**.

**One ID → two different people:**

| ID | Names sharing it |
|---|---|
| `IK-294` | `M Prasad Khuntia` (9 sheets) **and** `Swarup Yeole` (`Q3 2024`) |
| `IK-INT30` | `Rakshit Kapoor` **and** `Prithika` (both `Q3 2025`) |

**One person → two or more IDs:**

| Person | IDs |
|---|---|
| `Animesh Kumar` | `IK-398`, `IK-INT16` |
| `Srushith Kumar Donthoju` / `Donthoju Srushith Kumar` | `IK-418`, `IK-INT19` |
| `Swarup Yeole` | `IK-282`, `IK-294` |
| `Uday Mehtani` | `IK-614`, `IK-INT23` |
| `Vineet Patel` | `IK-1037`, `IK-INT42` |
| `Rakshit Kapoor` | `IK-INT29`, `IK-INT30` |
| `Prithika` / `Prithika K` | `IK-915`, `IK-INT30` |
| `Sweta Pandey` | `IK 445`, `IK-445` (space instead of hyphen) |

There is also a fill-down artefact: `Karthika S` reads as `IK-115`…`IK-121` and `Prithika K` as `IK-915`…`IK-922` across consecutive rows — the ID increments while the name stays fixed.

**Revised recommendation:** key `people.yaml` on a **hand-curated canonical name slug**, as the brief originally proposed. Record employee IDs as *evidence* in an `employee_ids: []` list, never as the key. The `IK-INT*` prefix appears to mark interns/contractors — useful as a property, useless for disambiguation.

### Data-quality landmines in the owner sheet
- Row 36 and 37 read `Deval, Srushith, , Adil` — a **double comma with an empty element**. A naive split on `,` yields a blank owner.
- Row 8 (`Early Engineering`) has **no Secondary Owner**, so the cell is blank. Any parser that skips blank cells will shift `Every Week` into the Secondary-Owner column. **The extractor must read cells positionally, never by compacting non-empty values.** I hit exactly this bug in my own inspection dump.
- Row 40 (`Advanced ML Ops`) has cadence `Discontinued` — a status masquerading as a cadence.
- Rows 13/14 (`Coding Pathway`, `System Design Pathway`) have a Delivery Team Member but **no owner at all**.

---

## 2.3 The shape of the Alert conditions

The brief asks whether these are conditions, thresholds, deadlines, or something else. I extracted all of them: **335 alert clauses** across 92 workflows (splitting on the `→` separator the document uses). Distribution of clauses per workflow: most have 3–5, one has 8, twelve have only 1.

**They are overwhelmingly state predicates about a gap or absence — not thresholds.** Measured:

| Shape | Clauses matching | Share |
|---|---|---|
| **Absence / gap** ("no", "not", "missing", "unclear", "without", "unavailable") | 153 | 46% |
| **Timeliness / deadline** ("pending", "delayed", "not within the expected timeline", "approaching", "stale") | 39 | 12% |
| **Recurrence** ("the same … again", "repeats", "recurring", "across cohorts") | 25 | 7% |
| **Contradiction** ("disagree", "mismatch", "conflict", "differ") | 16 | 5% |
| **Ownership gap** ("no clear owner", "ownership is unclear") | 12 | 4% |
| **Numeric threshold** (contains a digit or `<`/`>`) | **1** | **0.3%** |

Examples of each shape, verbatim:

- **Absence/gap:** *"required skills/experience are not clearly defined"* · *"the identified gap has no clear owner"* · *"setup steps are not tested from a clean environment."*
- **Timeliness:** *"alumni training request is pending"* · *"instructor requirement is not identified within the expected timeline"* · *"request is approaching the interview date without an assigned instructor"*
- **Recurrence:** *"the same issue recurs across cohorts"* · *"the same learner complaint appears across multiple sessions"*
- **Contradiction:** *"deck and code repo disagree"* · *"US and India salary/job figures are mixed"*
- **Numeric threshold:** essentially none. The single hit is incidental.

**This matters for the design.** Your hypothesis treats `Alert` as a node type, implicitly like a rule that can fire. But these are **not machine-evaluable rules** — they are *human-readable risk statements*. Nothing in the corpus can compute "is ownership unclear?".

**Where the real thresholds live:** `00-master/IAims Setting Audit`, in the rubric sheets. Those *are* numeric and *are* evaluable — e.g. `New Courses - B2C or B2B: Rating 1 < 4.50 | Rating 2: 4.50–4.55 | … | Rating 5: 4.72+`, and NPS bands `Rating 1: < 45`. There are **five** rubric sheets with **different thresholds per quarter** (Q126, Q226, Q325-onward, Q425, "Updated Q226") — the numbers changed between quarters. That is a versioning problem, not a taxonomy problem, but it means "what is the rating threshold" has **no single answer** without a quarter.

---

## 2.4 Entities the taxonomy must represent, per file

| File / sheet | Entities it contributes |
|---|---|
| `Team_Task___Workflow_Inventory` | **Theme (16), Workflow (92), Alert text (335 clauses), Effort estimate (92)** |
| `Domains_Courses Owners!Sheet1` | **Domain (42), Person-as-owner, Person-as-delivery-POC, Cadence, Program-type (IP/SU/Skillup/Switchup)** |
| `Domains_Courses Owners!For Slack` | Person ↔ curriculum-area mapping; Slack-group provisioning status |
| `IAims Setting Audit` (17 sheets) | **Employee (with `IK-` IDs), Objective/I-Aim, Rating rubric + numeric thresholds, Quarter** |
| `04-programs/CUR-*.pdf` (42) | **Program (42)**, and inside each: modules, target audience, tools, outcomes |
| `ALL-COURSES-COMPLETE.md` | Course catalogue — 1,660 headings; programs, modules, durations |
| `Instructors Directory.xlsx` | **Instructor** + contact + bio + expertise |
| `SME Tracker - Bullseye_IK.xlsx` (17 sheets) | **SME/candidate**, hiring requisition, **Topic/Course**, Domain, priority (P0/P1), interview stage |
| `SME database (For Ops + NP)` | SME roster, joiners/exits |
| `AgenticAI Instructors Training Plan` (18 sheets) | **Instructor ↔ Module** assignment (1st/2nd/3rd/4th backup), training status, per-module average rating |
| `Data and Management.xlsx` (16 sheets) | **Module**, **Resource** (pre-class/live/assignment), Drive/Uplevel links, **Module ↔ Instructor (primary/backup)** |
| `Resource Collection Mastersheet` (14 sheets) | Same shape for Software/Systems domains; plus `Training Sheet` (person, POD, training topic, status, rating) |
| `New Combined Schedule.xlsx` (62 sheets) | **Class session** (date, type, topic, times), **Instructor**, confirmation status, **Cohort**, Zoom links, **Monitor** (a staffing role) |
| `Operational Metrics.xlsx` (102 sheets) | Time-series coaching/completion metrics, 2019–2026 |
| `06-analysis/*Poll Feedback*` | Per-class **Rating**, response rate, attendance, instructor/topic legend |
| `Discord Server List` | **Tool/Channel** (Discord servers) |
| `01-workflows/*` templates | Process artefacts: demo evaluation guide, feedback template, RCA template, onboarding steps |

**New entity types the data contains that your hypothesis does not name:**
`Domain` (42 — and it is *not* the same as `Program`), `Cohort`, `Class Session`, `Resource`, `Rating`, `Objective/I-Aim`, `Rubric threshold`, `Quarter`, `Requisition` (open/hired/delta), `Training record`, `Pod`.

---

## 2.5 Contradictions between files — surfaced, not resolved

1. **Brief vs corpus — the master file.** Brief describes a 3-tab spreadsheet ("NP Autopilot – The AI Operating System"). Corpus has a 4-field Markdown doc. No Automations tab, no To-Do tab, **no owner column**.
2. **Master file vs itself.** Footer claims *"91 tasks"*; there are 92.
3. **Brief vs corpus — file count and folders.** "~50 files, one folder, to be sorted, with `unsorted/`" vs 74 files already in 7 folders, no `unsorted/`, plus an unmentioned `06-analysis`.
4. **`Srushith` spelled three ways within `Domains_Courses Owners.xlsx`** (`Srushit`, `Srushith`, `Srusith`).
5. **`Swarup` vs `Swaroop`** — same file, two sheets.
6. **`Tanmaaya` vs `Tanmaya`** — same file, two sheets.
7. **`Karthika S` (IAims IK-115) vs `Karthika Pai` (SME Tracker Q4-24).** Same person or two people? **Unresolved — I need you to tell me.**
8. **Rating thresholds disagree across quarters.** `New Courses - B2C or B2B` Rating-2 band is `4.50–4.59` in *Updated Rubrics Q226*, `4.50–4.60` in *Rubrics Q126*, and `4.50–4.55` in *New Rubrics Q425* and *NewTilted Q325 Onward*. Three different definitions of the same band.
9. **Duplicate rubric sheets.** `Adil` and `Copy of Adil` in `IAims` hold the same content — which is current?
10. **Program naming disagrees between sources.** The PDFs use `EdgeUP KYP` / `Interview Preparation Program`; the owners sheet uses `IP` / `SU` / `Skillup` / `Switchup`; `ALL-COURSES-COMPLETE.md` uses marketing names ("Agentic AI Mastery Program for Software Engineers 2026"). **No shared key.** Mapping `Backend Engineering EdgeUP KYP` → owners-sheet row `Backend` requires a judgement call.
11. **Filename typos create false distinct programs.** `CUR-Data Analyst **Businees** Analyst EdgeUP KYP` vs `CUR-Data Analyst Business Analyst Interview Preparation Program`; `CUR-**Enginnering Mnagement** EdgeUP KYP` vs `CUR-EM - KYP`; `CUR-Backend␣␣Interview Preparation Program` (double space).
12. **`EM` appears as both `CUR-EM - KYP` and `CUR-Enginnering Mnagement EdgeUP KYP`; `PM` as both `CUR-PM-KYP` and `CUR-Product Management EdgeUP KYP`; `TPM` likewise.** Are `KYP` and `EdgeUP KYP` two products or two versions of one? **Unresolved.**
13. **Instructor status contradicts across files.** `AgenticAI Instructors Training Plan!WIP` lists `Michael Savafi` under bad ratings while `M_SME_Adv.GenAI` lists `Mickael Savafi` as a 3rd-choice instructor for *GenAI Breakthough* — two spellings, two implied statuses.
14. **`Huzaifa` (sheet `2.0 US SMEs Training`) vs `Huzefa` (sheets `WIP`, `Instructors`)** — one marked "Unresponsive".
15. **Delivery POC email mismatch.** `New Combined Schedule!Delivery POC` row for `Anshuman` carries the email `somya@interviewkickstart.com`. Name and address disagree.

---

## Open questions from A2

1. **Where is the real "NP Autopilot" spreadsheet?** Is `Team_Task___Workflow_Inventory` its successor, or is a 3-tab sheet missing from the sync? **This is the one that blocks the most.**
2. **Do workflow owners exist anywhere?** If not, `Owner` can only attach to `Domain`, and "who owns instructor rating communication" is **unanswerable**. See doc 05 for the workaround I propose.
3. `Karthika S` vs `Karthika Pai` — same person?
4. `KYP` vs `EdgeUP KYP` — two products or two versions?
5. Which `IAims` quarter is authoritative for "current" thresholds?
