# BUILD_LOG

Append-only. `pipeline/00_fetch_drive.py` writes a block here on every run; other
passes append their own. Never hand-edit an existing entry.

---

## 2026-09-09 — Part A, third round: exclusions recorded

No pipeline run. This entry records the ingestion exclusions agreed today, so the
decision is in the build record before the first build rather than after it.

### Files excluded from ingestion

| File | Sheets | Reason |
|---|---|---|
| `03-instructors/US Instructor Cost Analysis.xlsx` | 37 | Paycor HR payroll export — employee file numbers, work and personal emails, department, employment status including `Exited (Resigned)` / `Exited (Terminated)`, per-labour-code hourly rates for 5,387 distinct names. Misfiled HR record, not corpus material, answers no eval question. |

Corpus file count: **75 → 74**. Worksheet count: **374 → 337**.

> **Corrected.** An earlier version of this line read "74 → 73" and "374 → 337".
> The file count was wrong: the corpus holds **75** files, not 74. See the
> sheet-count resolution below for the cause.

### Field names excluded at extraction

Dropped from every sheet in the corpus, matched case-insensitively on the
normalised header:

```
learner_email        Email                Email Address        Email ID
Personal email       Work email           Alternate Email ID   Gmail ID
Phone                Phone No.            Mobile               LinkedIn
LinkedIn Profile     LinkedIn Profile URL LinkedIn Link        Discord ID
Discord Channel Link
```

Also dropped: any blank-headered column whose values are >30% email- or
phone-shaped. Each such drop is logged individually at build time with its file,
sheet and column index.

Retained: cohort counts, session titles, coach assignments, and learner/student
names.

### Known cost of the file exclusion

- 14 of the 25 internal `@interviewkickstart.com` addresses in the corpus occur
  **only** in the excluded file.
- `anshuman@interviewkickstart.com` → `Anshuman Bapna` (Rippling 1132) occurs
  **only** in the excluded file. Carried into `people.yaml` by hand, citing this
  file as out-of-corpus evidence.
- `Karthika Pai`'s payroll rows are gone; her identity as a person distinct from
  `Karthika S` now rests on the D3 confirmation plus her `SME Tracker` and
  `SME_Interview` name rows, since her email and LinkedIn are dropped as fields.

### Measurements taken this round

| Measure | Value | Method |
|---|---|---|
| Workflows in inventory | 92 across 16 themes | `##` / `###` heading parse |
| Instructor raw name rows | 1,509 | 5 rosters, header-driven positional read |
| Instructor distinct (normalised) | 1,098 | case + punctuation normalisation |
| Instructor in ≥ 2 rosters | 321 | — |
| Instructor junk rate | **23 / 1,098 = 2.1%** | heuristic (15) **+ hand audit (8 more)** |
| Module confirmed | 234 of 1,348 | appears in ≥ 2 files |
| Program docs | 42 → **42** after D5 KYP collapse | filename classification; zero merges |
| Person ceiling | **42** | 13 confirmed + 4 + 12 + 13 |
| Domains | 42 | owners sheet rows 2–43 |

Doc 08 Q2 reported 1,497 / 1,088 / 319 for the instructor figures from a slightly
different normalisation. The numbers above are the reproducible ones; reconcile
at B4 and adopt one, do not average.


---

## 2026-09-09 — Part A, fourth round: three corrections

### 1 · The 344 vs 374 worksheet discrepancy — RESOLVED. A corpus file changed.

Not a normalisation difference. I was wrong to suggest it might be, and wrong to
defer it to B4.

**`01-workflows/UpLevel Schedule Structure.xlsx` was added to the corpus during
this session.** 1,171,377 bytes, **30 worksheets**, mtime `2026-09-09 22:38` —
roughly six minutes after the inventory scan that produced the 344 figure and six
minutes before the count that produced 374.

```
374 (now) − 344 (doc 01) = 30 = exactly this file's sheet count
```

Both counts were correct when taken. Docs 01, 02, 06, 07 and 08 all cite 344 and
are correct **as of their timestamp**; they are now stale by one file. Corpus
totals: **75 files / 374 sheets**, or **74 / 337** after the payroll exclusion.

**This file has not been read by any scan.** It is not in the workflow, person,
instructor, module or program scan, and it postdates the sensitive full-row scan.
Its 30 sheets are entirely unexamined. Nothing in `taxonomy.yaml` accounts for
it.

**Process consequence.** The corpus is supposed to be read-only and it changed
under an active analysis. Pass 1 must record a manifest hash per file and fail
loudly when the set changes between passes, rather than silently re-measuring.

### 2 · Coverage matrix — 25 of 75 files have never been read by an entity scan

`Karthika Pai` was missed because her two source files sit outside every entity
scan. That is not a one-off. Full matrix in the round-four response; the summary:

| | Files |
|---|---|
| Total corpus | 75 |
| Touched by ≥1 entity scan (workflow / person / instructor / module / program) | 50 |
| **Touched by NO entity scan** | **25** |
| Touched by no scan of any kind | 15 |

The 25 include `AgenticAI Instructors Training Plan.xlsx` — which is the cited
source for eval **Q15** — plus `SME Tracker`, `SME_Interview_Demo Audit Rubrics`,
`Operational Metrics`, `UpLevel Schedule Structure` and all four `.docx` files.

**Therefore `Person = 42`, `Instructor = 1,098` and `Module = 234` are measured
over 50 of 75 files, not over the corpus.** They are floors, not counts. The
`expect` values in `taxonomy.yaml` carry this caveat and their tolerances are not
meaningful until B4 reads everything.

### 3 · Instructor junk rate — 2.1%, and the heuristic's recall is 65%

The **1.4%** figure quoted earlier was circular: it was the heuristic's own hit
count presented as the population rate, which is not comparable to Acceler's
externally-observed 8%. Corrected by hand audit.

- Random 50 of the 1,083 names the heuristic **passed** (seed `20260909`):
  **0 non-people**. One marginal (`Usha`, single token).
- Exhaustive audit of two weak classes among the passers found **8 real misses**:
  `Cloud`, `Database`, `Frontend` (single-token) and `Cloud Computing
  Architecture`, `Cloud Infrastructure`, `Frontend System Design`, `Full Stack`,
  `UI System Design`. **All 8 come from
  `Resource Collection Mastersheet!Indian Instructors`** — topic strings in the
  name column.

| | Value |
|---|---|
| Caught by heuristic | 15 |
| Missed, found by hand | 8 |
| **True junk** | **23 / 1,098 = 2.1%** |
| **Heuristic recall** | **15/23 = 65%** |

The earlier claim that the heuristic "catches 15/15" is withdrawn. The ≥1
threshold decision is unaffected — ≥2 would still remove 764 real people — but
`validate.py` gains two rules to close the gap (single-token names, and topic
words in a name field), and `Resource Collection Mastersheet` needs a
column-specific parser rather than a generic one.

---

## 2026-09-09 — Part A, fifth round: NP directory applied; three miss classes

### NP HR directory — out-of-corpus, authoritative, closed at 15

Hand-entered into `config/people.yaml` from a screenshot of the HR system. It is
**not a corpus file**, has no file node, and every entry carries
`origin: hand` with the directory named as `evidence`. It satisfies
`sources min_length: 1` and emits **no** `sourced_from` edge, so it can never be
presented as though a scan produced it.

**Emails are held as `work_email` (local part only, no `@`), not as aliases.**
Putting an address under `aliases` would carry it into the graph as a node label
variant under a key the excluded-fields rule does not match — i.e. it would
smuggle contact data past the D4 exclusion. `validate.py` now asserts no alias
value contains `@`, and that `work_email` reaches no node in `graph.json`.

### Person ceiling recomputed: **43**, of which 15 are NP

| Group | Count |
|---|---|
| `team: np` — the HR directory, closed | **15** |
| `team: other` — IAims names outside the directory | 14 |
| `team: delivery` — the 12 first-name-only, plus Simran Khemlani | 13 |
| Abhinav Rawat (`other`, one cell in the whole corpus) | 1 |
| **Total** | **43** |

Was 42. The delta is **+1 for Yash Mathur** and **−0 for Karthika Pai**, who was
never in the 42 (she was the reason for `tolerance: 2`). `expect` is now `null`
per the round-five instruction — 43 is recorded as the current floor.

Rakshit Kapoor stays counted: not on the directory, unresolved, but his IAims
trail runs into **Q1 2026**, so "former staff" does not fit. Swarup Yeole's trail
**stops at Q3 2025** — absent from Q42025, Q226 and Q1 2026 — which is consistent
with former staff. Both remain `team: other`, pending your call.

### THREE distinct miss classes, not one

`Karthika Pai` was the first. The other two are different failures and need
different fixes.

| # | Person | Why missed | Class | Fix |
|---|---|---|---|---|
| 1 | **Karthika Pai** | Her only sources — `SME Tracker`, `SME_Interview_Demo Audit Rubrics` — are outside **every** entity scan | **Coverage gap.** File never read. | Read all 75 files at B4 |
| 2 | **Yash Mathur** | 11 I-Aim rows in `IAims!Q226` (rows 104–114) with a **blank `ENo`**. The file WAS scanned; the rows were dropped. | **Key-dependent extraction miss.** | Never key on employee id — already reversed in R3; now also enforced by `validate.py` |
| 3 | **Vineet Patel / Bishal Biprodas Roy** | Found, but parked in "IAims employees who never appear in the owner sheet — in scope or not?" | **Classification miss.** Found and shelved. | `team` property; owner-sheet absence is not an out-of-scope signal |

**Class 2 is the worst of the three** because it is invisible: the file appears
in the coverage matrix as scanned, so no audit of *file* coverage would ever
surface it. An exhaustive re-read of the `Employee Name` column found **32
distinct values**, of which doc 08 accounted for 30. The two missing were
`Yash Mathur` and the string `Kalindi .`.

### `Kalindi .` is correct data

Doc 07 R3 listed `Kalindi .` as a corruption example ("a literal trailing
space-dot"). **Withdrawn.** It is her actual HR record, confirmed against the
directory. `label_raw` preserved; not flagged; not stripped.

### doctype folded into `program.family`

Cross-tabulating the 42 program documents:

| | EdgeUP | InterviewPrep | Standalone |
|---|---|---|---|
| **KYP** | 17 | 0 | 7 |
| **Curriculum** | 0 | 15 | 3 |

`doctype` is 100% determined by `family` for the 32 EdgeUP and InterviewPrep
programs and splits only inside the 10 Standalone ones. A 2-value type
predictable from an existing property for 76% of instances fails the same
earns-its-place test that demoted `Tool`. **Demoted to `program.doctype`; the
`doctype` node type and the `has_doc` edge are removed.** The previous
`doctype_vocabulary` (KYP / Interview Preparation Program / Program) was itself
wrong — two of its three values were product families duplicating `family`.

**Premise correction: not every program has a KYP document.** 24 of 42 do.

### Q15 reconciled — verified, but the taxonomy had a real gap

`AgenticAI Instructors Training Plan.xlsx` **was** read for eval verification and
**was not** in any entity scan. Re-read positionally today: `Preferred SMEs for
Each Topic` r3–r5 gives Anshaj Khare 4.73/4 and Kuldeep Singh 4.66/3; `M_SME_App.
Agentic AI` r3 gives the backup chain. Q15's key is exact and stands.

The gap: the `teaches` edge named this file as its source while the `instructor`
node type did not list it among its five rosters — an edge sourced from a file
its node type never read. **B4 blocker:** this workbook's 18 sheets must join the
instructor scan before any instructor count is final.

---

## 2026-09-09 — Part A, sixth round: M Prasad investigated; classifications settled

### M Prasad Khuntia — checked before classifying. Do NOT mark him former.

Asked to treat this as a possible third identity bug. **It is not one.**

**87 rows across 9 quarter sheets**, by `Employee Name`:

| Sheet | Rows | ENo |
|---|---|---|
| `Q226` | 1 | `IK-294` |
| `Q1 2026` | 10 | `IK-294` |
| `Q42025` | 11 | `IK-294` |
| `Q3 2025` | 11 | `IK-294` |
| `Q2 2025` | 12 | `IK-294` |
| `Q1 2025 on 5 Pointer Scale` | 10 | `IK-294` |
| `Q1 2025` | 10 | `IK-294` |
| `Q4 2024` | 11 | `IK-294` |
| `Q3 2024` | 11 | `IK-294` |

Every row: name `M Prasad Khuntia`, ENo `IK-294`. No blank, no variant spelling,
no second id. Nothing resembling the Yash Mathur failure.

**The IK-294 collision is real but tiny, and on the other side.** `Swarup Yeole`
carries `IK-282` on **48 of 49** rows and `IK-294` on **exactly one** row in
`Q3 2024`. A single stray cell, not a systematic collision, and it touches no
Prasad row. Doc 08's "IK-294 = two people" is literally true and materially
misleading; corrected here.

**Two corrections to my own earlier report, both of which weakened it:**

1. **9 sheets, not 13.** The 13 came from a loose substring match that also hit
   the owners workbook and `For Slack`.
2. **`Q1 2026` is NOT the current quarter.** `Q226` is the latest sheet in the
   workbook; `Q1 2026` is the one before it. My phrase "active current-quarter
   objectives" was wrong.

**What survives, and it is the part you asked about: the Q1 2026 rows hold up.**
A complete 10-objective set at 100% weightage. In `Q226` he has a name-and-ENo
row with no objectives.

**That bare row is not a departure signal.** Four people have that exact shape in
`Q226` — `Utkarsh Raj`, `M Prasad Khuntia`, `Deval Mahesh Purohit`,
`Tanmaya Kharyal` — and three of the four are on the current HR directory. It
means objectives not yet set.

**There is a departure trail in this workbook, and it has three stages:** full
objectives → name-only row → absent. `David Reed` and `Sweta Pandey` both
followed it (name-only in `Q1 2026`, gone from `Q226`). Prasad is at stage two,
which is ambiguous; the next quarter's sheet resolves it.

**Verdict: the corpus does not show a departure, and leans slightly against
one.** Left `status: unresolved` with this note. Over to you.

### Q226 quarter label — noted, not acted on

As asked, given Q19 found five contradictory quarter-scoped rubric versions in
this workbook.

- **56% copy-forward.** 73 of 131 distinct `(name, I-Aim Title)` pairs in `Q226`
  are identical to a pair in `Q1 2026`. Some recurrence is legitimate — ratings
  and NPS objectives repeat every quarter — so this is suggestive, not proof.
- **No date column anywhere in the sheet.** Headers are ENo, Employee Name,
  I-Aim Title, Rubrics, Metric Type, Metric Unit, Metric Target Type, Initial
  Value, Target Value, Weightage. **There is no in-sheet evidence of when any row
  was entered**, so backfill cannot be distinguished from live entry from the
  file alone.
- **Naming is inconsistent across sheets**: `Q1 2026` and `Q226` denote adjacent
  quarters in different formats, and the rubric sheets use a third (`Q126`,
  `Q325`, `Q425`). Any quarter-ordering logic must be written against an explicit
  map, never parsed from the sheet name.

No action taken.

### Classifications recorded

| Person | team | status |
|---|---|---|
| Swarup Yeole | `other` | `switched-teams` — still at IK, **not former** |
| Abhinav Rawat | `other` | `switched-teams`, flagged `evidence_strength: weakest-in-graph` |
| M Prasad Khuntia | `other` | `unresolved` — pending your investigation |

Recorded alongside Abhinav: a person who left NP *before* the corpus was
assembled leaves almost no trace, so single-cell provenance is the **expected**
shape for that class, not an anomaly to clean up.

### Yash Mathur severity downgraded

The blank `ENo` is normal HR lag for a recent joiner, not corrupt data. Reframed
in CLAUDE.md as a **permanent condition to handle** rather than a defect to fix:
key on name, keep `ENo` as secondary evidence, report-and-retain blank
identifiers. Karthika Pai — a file no scan ever read — remains the more serious
finding, because a coverage audit cannot even see the class Yash falls into but
at least bounds the class she falls into.

`file.expect` stays **74**, tolerance **2**. Not pre-raised; the tripwire is the
point.

## 2026-09-09 18:02:35Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 82 | skipped 1 | extracted 80 | failed 1
- Manifest diff: +81 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:03:11Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +74 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:03:41Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +1 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:04:04Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +74 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:04:15Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:10:09Z — 02_extract

- Candidates 6741 | rejected 303 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 4704 raw, 3411 distinct
    - module: 265 raw, 172 distinct
    - person: 1580 raw, 58 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:11:00Z — 03_resolve

- Nodes 3817 | alias merges applied 19 | fuzzy proposed 0 | applied 0

## 2026-09-09 18:11:11Z — 03_resolve

- Nodes 3817 | alias merges applied 19 | fuzzy proposed 0 | applied 0

## 2026-09-09 18:12:10Z — 02_extract

- Candidates 6813 | rejected 303 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 4704 raw, 3411 distinct
    - module: 265 raw, 172 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:12:17Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:12:33Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:12:33Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:12:35Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:12:35Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:13:26Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:13:26Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:13:42Z — 02_extract

- Candidates 6813 | rejected 303 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 4704 raw, 3411 distinct
    - module: 265 raw, 172 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:13:42Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:14:36Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:14:36Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:14:37Z — 04_build_graph

- Nodes 3871 | edges 7088
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 21
    - contains: 0
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:15:14Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:15:15Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:15:16Z — 04_build_graph

- Nodes 3871 | edges 7088
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 21
    - contains: 0
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:16:01Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:16:01Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:16:02Z — validate

- validate: 1 FAIL, 19 WARN, 8/16 categories exercised, 3871 nodes, 7088 edges

## 2026-09-09 18:16:29Z — 04_build_graph

- Nodes 3892 | edges 7088
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 21
    - contains: 0
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:16:49Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 3892 nodes, 7088 edges

## 2026-09-09 18:17:22Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:17:22Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:17:57Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:17:57Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:18:06Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 3892 nodes, 7088 edges

## 2026-09-09 18:22:37Z — 02_extract

- Candidates 6813 | rejected 303 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 4704 raw, 3411 distinct
    - module: 265 raw, 172 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:23:05Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:23:06Z — 04_build_graph

- Nodes 3892 | edges 7246
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 21
    - contains: 158
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:23:27Z — 04_build_graph

- Nodes 3892 | edges 7165
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 15
    - contains: 83
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:23:48Z — 04_build_graph

- Nodes 3892 | edges 7297
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 27
    - contains: 203
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:24:10Z — 04_build_graph

- Nodes 3892 | edges 7309
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 214
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:24:39Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 3892 nodes, 7309 edges

## 2026-09-09 18:24:46Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:24:46Z — 03_resolve

- Nodes 3818 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:24:49Z — 04_build_graph

- Nodes 3892 | edges 7309
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 214
    - teaches: 6
    - sourced_from: 6813

## 2026-09-09 18:25:09Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 3892 nodes, 7309 edges

## 2026-09-09 18:38:08Z — 02_extract

- Candidates 15656 | rejected 519 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5462 raw, 3486 distinct
    - module: 8350 raw, 484 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:38:39Z — 03_resolve

- Nodes 4205 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:39:05Z — 04_build_graph

- Nodes 4279 | edges 17023
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 397
    - teaches: 694
    - sourced_from: 15656

## 2026-09-09 18:39:31Z — 03_resolve

- Nodes 4205 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:39:31Z — 03_resolve

- Nodes 4205 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:39:34Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4279 nodes, 17023 edges

## 2026-09-09 18:40:07Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 76 | skipped 1 | extracted 74 | failed 1
- Manifest diff: +1 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 18:40:08Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4279 nodes, 17023 edges

## 2026-09-09 18:44:36Z — 02_extract

- Candidates 15403 | rejected 531 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:44:36Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:45:15Z — 02_extract

- Candidates 15403 | rejected 531 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:45:16Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:45:16Z — 04_build_graph

- Nodes 4255 | edges 16722
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 355
    - teaches: 688
    - sourced_from: 15403

## 2026-09-09 18:45:32Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:45:33Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:45:36Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4255 nodes, 16722 edges

## 2026-09-09 18:54:58Z — 02_extract

- Candidates 15403 | rejected 602 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:55:21Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:55:22Z — 04_build_graph

- Nodes 4255 | edges 17524
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 355
    - expert_in: 802
    - teaches: 688
    - sourced_from: 15403

## 2026-09-09 18:56:19Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:56:19Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:56:23Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4255 nodes, 17524 edges

## 2026-09-09 18:56:51Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:56:51Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:57:18Z — 02_extract

- Candidates 15403 | rejected 589 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 18:57:18Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:57:19Z — 04_build_graph

- Nodes 4255 | edges 17524
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 355
    - expert_in: 802
    - teaches: 688
    - sourced_from: 15403

## 2026-09-09 18:57:34Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4255 nodes, 17524 edges

## 2026-09-09 18:58:30Z — 05_render_html

- graph.html 427 KB | rendered 2338 nodes (1318 connected, 1020 isolated) and 2121 edges

## 2026-09-09 18:58:31Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 18:58:31Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:03:12Z — 02_extract

- Candidates 15403 | rejected 589 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:03:12Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:03:54Z — 02_extract

- Candidates 15403 | rejected 589 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5450 raw, 3486 distinct
    - module: 8109 raw, 459 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:03:54Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:03:55Z — 04_build_graph

- Nodes 4255 | edges 17524
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 355
    - expert_in: 802
    - teaches: 688
    - sourced_from: 15403

## 2026-09-09 19:03:57Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:03:57Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:04:50Z — 04_build_graph

- Nodes 4255 | edges 17524
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 355
    - expert_in: 802
    - teaches: 688
    - sourced_from: 15403

## 2026-09-09 19:06:10Z — 05_render_html

- graph.html 427 KB | rendered 2338 nodes (1318 connected, 1020 isolated) and 2121 edges

## 2026-09-09 19:06:11Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4255 nodes, 17524 edges

## 2026-09-09 19:06:12Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:06:12Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

---

## 2026-09-10 — B8 eval harness

**Honest score: 20/22 (91%). Zero fabrications.**

| kind | score |
|---|---|
| single-hop | 8/8 |
| multi-hop | 6/8 |
| single+observation | 2/2 |
| **correctly unanswerable** | **4/4 — no invention on any of Q17–Q20** |

### The first run scored 14/22, and the second scored 22/22. Neither was honest.

- **14/22** was real: 8 Component A questions failed because pass 2 extracted only
  workflow id/name/theme and never read `alerts`, `effort`, `steps` or `tools`
  from the inventory body. Fixed — all 92 workflows now carry them.
- **22/22 was not real.** The harness scored a question PASS on a *non-empty*
  result. Q13 returned 11 workflows where 3 are correct, and Q15 returned
  instructors with `rating: null`. Both were counted as passes. The harness now
  checks CONTENT against the documented answer, which is what produced 20/22.

### The two remaining failures are query problems, not data problems

The graph holds both answers; a loose substring query does not find them.

- **Q13** — querying `owner` over alert text returns **12** alerts. Only **3**
  (`5.5`, `8.4`, `14.1`) carry the clause *"ownership is unclear"*. The other 9
  are different clauses: *"no clear owner/workaround"*, *"has no systemic
  owner/action"*, *"corrective action has no owner/date"*.
- **Q14** — querying `drop` returns **3**. Only `11.5` is about an instructor
  dropping; `2.6` and `15.1` are about **rating** drops.

Not fixed by tightening the queries, deliberately: fitting a query to a known
answer would make the score meaningless. Recorded instead as a constraint on B9 —
**any skill must match clauses, not keywords**, or it will answer Q13 with 12
workflows and sound confident.

### The harness found a factual error in the answer key

Doc 06 Q14 asserted *"the corpus defines no 48-hour or any other threshold"*.
**False.** Workflow `2.7` carries the alert *"the session is within **72 hours**
and no instructor is confirmed"*. The key asserted a corpus-wide absence without
checking — the same failure mode the question exists to catch. Doc 06 corrected;
the question is now harder, not easier.

### Q15 verified against the graph, not the file

Asked specifically because Q15's answer was verified when `AgenticAI Instructors
Training Plan.xlsx` had been read for eval but never entity-scanned. Generalising
the pairing extractor then **dropped the ratings** — the edge existed, the
`avg_rating` did not, and dedup was discarding the one rating-bearing pair in
favour of an earlier pair from another sheet. Fixed; the graph now reaches
`Anshaj Khare` **with** the rating, not just the name.

## 2026-09-09 19:10:18Z — 05_render_html

- graph.html 827 KB | rendered 2338 nodes (1318 connected, 1020 isolated) and 2121 edges

## 2026-09-09 19:11:16Z — 05_render_html

- graph.html 827 KB | rendered 2338 nodes (1318 connected, 1020 isolated) and 2121 edges

## 2026-09-09 19:11:26Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:11:26Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:11:49Z — 05_render_html

- graph.html 827 KB | rendered 2338 nodes (1318 connected, 1020 isolated) and 2121 edges

## 2026-09-09 19:11:51Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:11:51Z — 03_resolve

- Nodes 4180 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:12:11Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4255 nodes, 17524 edges

## 2026-09-09 19:15:14Z — 02_extract

- Candidates 14405 | rejected 549 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5420 raw, 3479 distinct
    - module: 7141 raw, 453 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:15:14Z — 03_resolve

- Nodes 4167 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:15:15Z — 04_build_graph

- Nodes 4242 | edges 16502
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 802
    - teaches: 668
    - sourced_from: 14405

## 2026-09-09 19:16:00Z — 02_extract

- Candidates 14348 | rejected 606 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5420 raw, 3479 distinct
    - module: 7084 raw, 408 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:16:01Z — 03_resolve

- Nodes 4122 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:16:02Z — 04_build_graph

- Nodes 4197 | edges 16373
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 279
    - expert_in: 802
    - teaches: 668
    - sourced_from: 14348

## 2026-09-09 19:16:56Z — 02_extract

- Candidates 14353 | rejected 594 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5418 raw, 3477 distinct
    - module: 7091 raw, 410 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:17:35Z — 02_extract

- Candidates 14353 | rejected 594 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 5419 raw, 3478 distinct
    - module: 7090 raw, 409 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:17:35Z — 03_resolve

- Nodes 4122 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:17:36Z — 04_build_graph

- Nodes 4197 | edges 16380
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 281
    - expert_in: 802
    - teaches: 668
    - sourced_from: 14353

## 2026-09-09 19:18:22Z — 05_render_html

- graph.html 1656 KB | rendered 2280 nodes (1271 connected, 1009 isolated) and 2027 edges

## 2026-09-09 19:18:38Z — 05_render_html

- graph.html 1656 KB | rendered 2280 nodes (1271 connected, 1009 isolated) and 2027 edges


### Caveat on the 20/22 eval score — recorded at the owner's request

**These 22 questions were written alongside the graph, and several were
reclassified or corrected during the build.** Q10 and Q16 were re-labelled from
multi-hop to single-hop-plus-observation; Q17's expected answer was strengthened
after R2 was reclassified; Q14's answer key was found to be factually wrong and
corrected; Q21 and Q22 were written as replacements after the multi-hop count was
challenged.

**So 20/22 measures the question shapes we designed for, not unrehearsed
questions.** It says the graph reaches the facts we already knew were in it. It
does not say the graph answers what a teammate will actually ask.

**Next: five questions written fresh against the finished graph, which neither
party has seen answered.** That is the real test, and it comes after B9.

## 2026-09-09 19:19:16Z — 03_resolve

- Nodes 4122 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:19:17Z — 03_resolve

- Nodes 4122 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:19:46Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4197 nodes, 16380 edges

## 2026-09-09 19:25:06Z — 02_extract

- Candidates 29215 | rejected 594 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 12850 raw, 3488 distinct
    - module: 14521 raw, 895 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:25:23Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:25:30Z — 04_build_graph

- Nodes 4693 | edges 32529
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 347
    - expert_in: 802
    - teaches: 1889
    - sourced_from: 29215

## 2026-09-09 19:27:01Z — 05_render_html

- graph.html 2991 KB | rendered 2776 nodes (1847 connected, 929 isolated) and 3314 edges

## 2026-09-09 19:27:34Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:27:35Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:28:15Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4693 nodes, 32529 edges

## 2026-09-09 19:33:18Z — 02_extract

- Candidates 29215 | rejected 594 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 12850 raw, 3488 distinct
    - module: 14521 raw, 895 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:33:18Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:33:19Z — 04_build_graph

- Nodes 4693 | edges 32529
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 347
    - expert_in: 802
    - teaches: 1889
    - sourced_from: 29215

## 2026-09-09 19:33:55Z — 05_render_html

- graph.html 2991 KB | rendered 2776 nodes (1847 connected, 929 isolated) and 3314 edges

## 2026-09-09 19:33:56Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:33:56Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:34:02Z — validate

- validate: 0 FAIL, 18 WARN, 8/16 categories exercised, 4693 nodes, 32529 edges

## 2026-09-09 19:37:56Z — 05_render_html

- graph.html 2992 KB | rendered 2776 nodes (1847 connected, 929 isolated) and 3314 edges

## 2026-09-09 19:39:24Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:39:24Z — 03_resolve

- Nodes 4618 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:47:12Z — 02_extract

- Candidates 30904 | rejected 594 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 14539 raw, 3489 distinct
    - module: 14521 raw, 895 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 19:47:13Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:47:52Z — 04_build_graph

- Nodes 4694 | edges 34218
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 347
    - expert_in: 802
    - teaches: 1889
    - sourced_from: 30904

## 2026-09-09 19:49:23Z — 05_render_html

- graph.html 3125 KB | rendered 2777 nodes (1847 connected, 930 isolated) and 3314 edges

## 2026-09-09 19:49:27Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:49:28Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:49:35Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 4694 nodes, 34218 edges

## 2026-09-09 19:49:52Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 4694 nodes, 34218 edges

## 2026-09-09 19:52:34Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:52:48Z — 04_build_graph

- Nodes 4694 | edges 34218
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 347
    - expert_in: 802
    - teaches: 1889
    - sourced_from: 30904

## 2026-09-09 19:52:50Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:52:51Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:53:02Z — 05_render_html

- graph.html 3125 KB | rendered 2777 nodes (1847 connected, 930 isolated) and 3314 edges

## 2026-09-09 19:53:04Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 4694 nodes, 34218 edges

## 2026-09-09 19:53:18Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 4694 nodes, 34218 edges

## 2026-09-09 19:57:06Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:57:06Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:59:20Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:59:21Z — 03_resolve

- Nodes 4619 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 19:59:29Z — 05_render_html

- graph.html 3125 KB | rendered 2777 nodes (1847 connected, 930 isolated) and 3314 edges

## 2026-09-09 19:59:30Z — validate

- validate: 0 FAIL, 19 WARN, 8/16 categories exercised, 4694 nodes, 34218 edges

---

## 2026-09-10 — five fresh eval questions

**Written against the finished graph, on shapes it was not designed around,
covering staffing and coverage. Written before running, not tuned afterwards.**

| set | score |
|---|---|
| original 22 | **20/22 = 91%** |
| **fresh 5, first run** | **4/5 = 80%** |
| fresh 5, after a query fix | 5/5 |
| combined | 25/27 = 93% |

**The fresh set scored 11 points worse on first run, as predicted.**

### Q24 failed, and it was my query, not the graph

*"Which domains are we most exposed on — where one person teaches everything?"*
returned nothing. The graph holds the answer: **EM has exactly one instructor**
(Sreeram Murkuri), Security has two. My implementation carried an arbitrary
`>= 2 taught modules` filter, which excluded EM — the single most exposed domain,
and the whole point of the question.

**The question was not changed. The query defect it exposed was fixed**, and both
scores are recorded above so the difference is visible.

**This is the second time an arbitrary threshold I chose has hidden a correct
answer** — the first was the module `>= 2` cross-file rule. Worth stating as a
pattern: a threshold introduced for noise control silently becomes a filter on
truth, and only an unrehearsed question finds it.

### What the fresh five actually exercised

- **Q23** ranked Security instructors by recency with the decline window —
  `Bilal Zuberi`, last taught 2026-09-06, declined 3 of 29.
- **Q25** program → domain in reverse.
- **Q26** decline counts alongside `still_taught`, confirming availability and
  delivery coexist: `Hiro Onizuka` declined 9 and still taught.
- **Q27** the most recent class in the corpus: `Christopher Stires`, *Live
  Behavioral Interview Patterns*, 2026-09-09.

**Still 0 fabrications across all 27.** The four unanswerables remain 4/4.

## 2026-09-09 20:06:09Z — 02_extract

- Candidates 32624 | rejected 190 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15604 raw, 3817 distinct
    - module: 15176 raw, 918 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:06:23Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:06:24Z — 04_build_graph

- Nodes 5045 | edges 36305
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 345
    - expert_in: 835
    - teaches: 2225
    - sourced_from: 32624

## 2026-09-09 20:06:36Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:06:37Z — 04_build_graph

- Nodes 5045 | edges 36305
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 345
    - expert_in: 835
    - teaches: 2225
    - sourced_from: 32624

## 2026-09-09 20:06:38Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:06:39Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:08:07Z — 05_render_html

- graph.html 3325 KB | rendered 2993 nodes (2009 connected, 984 isolated) and 3681 edges

## 2026-09-09 20:08:39Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:08:40Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:08:46Z — validate

- validate: 0 FAIL, 212 WARN, 8/16 categories exercised, 5045 nodes, 36305 edges

---

## 2026-09-10 — threshold audit

**Convention adopted permanently: first-run score and post-fix score are BOTH
recorded, every time.**

### Six instructor filters were dominated by false positives

Sampling what each dropped was decisive:

| filter | dropped | what it excluded |
|---|---|---|
| sentence punctuation | 127 | `Dr. Raju Penmatcha`, `Chuhong Mai, PhD`, `Minh P. Vo` — credentials and initials |
| stopword | 9 | `Will Yao`, `Will Drevo`, `Will Carhart` — "will" is a stopword AND a first name |
| >4 tokens | 17 | `Satya Sai Shiva Rama Akula`, `Tanikella V S S Pavan Kumar` |
| single token | 156 | `Usha`, later proven a person by a Confirmation ID |
| contains a digit | 4 | `2- Prateek` |
| >40 characters | 9 | genuinely multi-name cells — the real signal is the newline |

**All six now FLAG instead of REJECT.** Instructor **3,488 → 3,817** (+329 real
people), rejections **594 → 190**, and 199 nodes carry a visible `review` flag.
`teaches` 1,889 → 2,225.

Kept as hard rejects only where the shape cannot be the thing: `@`/`http`, a
newline meaning several names in one cell, topic-vocabulary matches, numeric or
phone-shaped, column filler.

Full audit in `10-threshold-audit.md`. Rule recorded in `CLAUDE.md`.

### Restart-on-click instrumentation

The graph draws; the remaining report is restart-on-click, persisting in
incognito. Added a diagnostic that distinguishes the two possible causes, which
need opposite fixes:

- a `sessionStorage` **load counter** shown on the page — if it increments when
  you click, the page is genuinely reloading;
- a `beforeunload` listener that logs **"the page is navigating away"**;
- every `recompute()` logs its reason — a recompute re-scatters the layout and is
  **not** a reload.

If the counter stays at 1 while the graph re-scatters, it is a layout reset and
nothing is navigating.

## 2026-09-09 20:09:14Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:09:14Z — 03_resolve

- Nodes 4970 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:09:22Z — validate

- validate: 0 FAIL, 6 WARN, 8/16 categories exercised, 5045 nodes, 36305 edges

## 2026-09-09 20:09:34Z — 05_render_html

- graph.html 3325 KB | rendered 2993 nodes (2009 connected, 984 isolated) and 3681 edges

## 2026-09-09 20:09:35Z — validate

- validate: 0 FAIL, 6 WARN, 8/16 categories exercised, 5045 nodes, 36305 edges

## 2026-09-09 20:11:52Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:11:52Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:12:04Z — 04_build_graph

- Nodes 5049 | edges 36357
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 835
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:13:24Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:13:24Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:13:30Z — 05_render_html

- graph.html 3331 KB | rendered 2998 nodes (2020 connected, 978 isolated) and 3701 edges

## 2026-09-09 20:13:32Z — validate

- validate: 0 FAIL, 6 WARN, 8/16 categories exercised, 5049 nodes, 36357 edges

### Threshold audit, round two — the bias and the surviving rejections

**The filters had a shape.** Re-applying the six original rules to today's
3,817-name population, they would still exclude **336 people (8.8%)**:

- **84** for holding a **PhD, Dr, MD or Jr** — two thirds of everything the
  punctuation rule removed
- **28** for a **middle initial** (`Benjamin O. Tayo`, `Minh P. Vo`)
- **4 of 5** stopword hits were people named **Will** — the word is in the
  stopword list and is also a first name
- **22** for **long multi-part names**, disproportionately South Asian
- **195** single-token names

Noise removal that correlates with a category of person is not noise removal.
Recorded in `10-threshold-audit.md` and `CLAUDE.md`.

**The surviving 190 were re-audited by hand, and the principle did not hold —
three were false positives:** `EM`/`PM`/`V2` rejected as modules for being under
3 characters, `Shelby` dropped because the collision resolver treated a single
token as "not a person", and `JS and Web Development` classified a person name
because the topic vocabulary lacked `web` and `js`. All recovered; 190 → 185.

### Junk floor re-measured at the loosened population

| | then | now |
|---|---|---|
| population | 1,098 | **3,817** |
| confirmed non-people | 23 | **0** |
| floor | 2.1% | **0 found — see framing below** |

Random 50 (seed 20260910): **0 non-people**, including previously-rejected shapes
now admitted — `Arun K.`, `Matthew H.`, `Kwei-Herng "Henry" Lai`, `Romil`.
Exhaustive scan of all 199 flagged records plus a topic/filler sweep of the whole
population: **1 hit, `Danielle Class`, which is a real person whose surname
matched the audit regex** — a false positive of the audit, not a non-person.

**Stated the way it should be stated: "no non-people found in a sample of 50,
upper bound ~6% at 95% confidence."** Not 0.00%. A point estimate of zero from a
50-item sample is a claim the sample cannot support, and the old 2.1% was
likewise only "what I found" — both are floors on a search, not measurements of a
population.

## 2026-09-09 20:19:17Z — 05_render_html

- graph.html 3333 KB | rendered 2998 nodes (2020 connected, 978 isolated) and 3701 edges

## 2026-09-09 20:19:43Z — 05_render_html

- graph.html 3333 KB | rendered 2998 nodes (2020 connected, 978 isolated) and 3701 edges

## 2026-09-09 20:20:13Z — 05_render_html

- graph.html 3333 KB | rendered 2998 nodes (2020 connected, 978 isolated) and 3701 edges

## 2026-09-09 20:20:43Z — 04_build_graph

- Nodes 5049 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:21:10Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:21:11Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:21:17Z — 05_render_html

- graph.html 3362 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:21:21Z — validate

- validate: 0 FAIL, 6 WARN, 8/16 categories exercised, 5049 nodes, 36677 edges

---

## 2026-09-10 — restart-on-click: audit, fix, and the check that would have caught it

### The audit, which is where the bug was

**8 `recompute()` call sites — none is a click handler.** Clicking a node never
called it, so the re-scatter was never coming from there.

**1 `settle` write, and the bug beside it:**

```
232  const K = settle<90 ? 1 : 0.35     <-- forces NEVER reach zero
245  settle++                            increments forever
246  if(settle===90) fit()               fires exactly once
```

**The simulation never stopped.** `K` floored at `0.35`, so spring and repulsion
forces were applied on every frame forever. The layout was never settled, only
slowed — it drifted permanently.

**And `addEventListener('resize', () => { size(); fit() })` was undebounced.**
Opening the detail panel changes page layout and can add or remove a scrollbar,
which fires `resize`; `size()` clears the canvas and `fit()` jumps the camera. A
click could trigger it.

### The fix

- **Cooling schedule that reaches zero.** `alpha` decays at 0.985 to a floor of
  0.004, then the simulation **freezes** — measured at **366 frames**. Nothing
  moves again until a filter or data change.
- **Selection split from layout.** `select()` touches `state.sel` only. `openNode`
  asserts the simulation clock is unchanged and logs an error if it is not.
  Neither can call `recompute()`.
- **Debounced resize (150ms) that keeps the viewport** and never restarts the
  simulation.
- **Camera, selection and open panel preserved** across any legitimate recompute.

### The check that would have caught it

The old harness asserted arcs were painted — which passes even when the whole
graph has re-laid-out. It now asserts, after a simulated click:

```
click -> coords byte-identical : true
click -> sim clock unchanged   : true
filter toggle -> sim restarted : true     (the legitimate case still works)
```

The load counter and the `recompute()` reason log stay on the page. **If the
behaviour persists, that display says immediately it was the other cause.**

### Aliases applied

15 confirmed. `expert_in` **802 → 1,155 edges**, join rate **50% → 69%**, of which
**320 carry `via_alias: true`**. The staffing command surfaces them as a separate
`self_declared+via_alias` tier — visible on DABA (59), TPM (46), SRE (15 plus 5
`hr_record+via_alias`). Top unjoined remains exactly the ambiguous set: `ML` 157,
`Agentic AI` 64, `Product Management` 51.

## 2026-09-09 20:27:18Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 83 | skipped 1 | extracted 81 | failed 1
- Manifest diff: +7 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:27:51Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:27:51Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:27:52Z — 04_build_graph

- Nodes 5056 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:27:53Z — 05_render_html

- graph.html 3362 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:27:53Z — validate

- validate: 1 FAIL, 6 WARN, 9/17 categories exercised, 5056 nodes, 36677 edges

## 2026-09-09 20:28:02Z — validate

- validate: 1 FAIL, 6 WARN, 9/17 categories exercised, 5056 nodes, 36677 edges

## 2026-09-09 20:28:38Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -8 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:29:08Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:29:26Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:30:04Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:30:04Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:30:05Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:30:06Z — 05_render_html

- graph.html 3362 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:30:06Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges

## 2026-09-09 20:30:25Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:31:05Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:31:06Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:31:07Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:31:07Z — 05_render_html

- graph.html 3362 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:31:08Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges

## 2026-09-09 20:31:25Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:32:14Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:32:15Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:32:17Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:32:17Z — 05_render_html

- graph.html 3362 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:32:18Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges

## 2026-09-09 20:33:16Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:33:16Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

---

## 2026-09-10 — B10: refresh v1

### The delta line from a real run, not a template

```
REFRESH v1
  plugin version : 0.1.1
  graph hash     : a53462823ca26466

  01_walk_corpus.py      ok
  02_extract.py          ok
  03_resolve.py          ok
  04_build_graph.py      ok
  gen_index.py           ok
  05_render_html.py      ok

DELTA
  nodes 5056 -> 5048  (-8)
  edges 36677 -> 36677  (+0)

  version bumped 0.1.1 -> 0.1.2

VALIDATE
  RESULT: 0 FAIL, 6 WARN, 6 INFO — graph accepted with warnings

STOPPED FOR CONFIRMATION — nothing has been committed.
```

### Determinism holds — second run, no corpus change

```
  plugin version : 0.1.2
  graph hash     : a53462823ca26466

DELTA
  IDENTICAL — nodes and edges byte-identical to the previous build
  version unchanged at 0.1.2 (graph did not change)
```

**Definition of done met.** Determinism has not regressed since B5.

### The first refresh FAILED, and the check that caught it was the file count

```
[count-vs-expect] file: 82, expected 74 +/- 2
REFRESH ABORTED — validation failed. Nothing to commit.
```

Pass 1's `SKIP_DIRS` was missing `commands/` and `eval/`, so it had swept in 8 of
our own project files as corpus. **That is exactly what `file.expect` is for**,
and it is the first time a count check has caught a live regression rather than
documenting a known number.

Fixing it then triggered the manifest rule — 8 removals, a hard fail — which is
also correct. Added `--rebaseline` to accept a change **explicitly**, printing the
diff and writing it to BUILD_LOG. It must never be used to make an unexplained
diff go away.

### Version bump: automatic AND enforced

`validate.py` gained a `version-bump` category. It compares a content hash of
nodes+edges (meta excluded, so the timestamp does not perturb it) against
`knowledge/.version-lock.json`, and hard-fails if the content changed while
`plugin.json` did not:

> *graph.json content changed but plugin.json is still 0.1.2. Teammates would
> never receive this build.*

17 validation categories now, still all fault-injection tested.

### Module layer finding recorded

**671 of 922 modules (73%) connect only through `teaches`.** 351 `contains`
edges against 2,239 `teaches`, and `contains` is itself inferred. Hiding
instructors leaves 1,157 nodes / 627 edges / **772 components, 755 of them
singletons**. Recorded in `USING_THE_KG.md`: the module layer is a delivery
record that names modules, not curriculum structure.

### Held deliberately

- **Cloudflare Access** — documented in README, **nothing configured**.
- **Refresh v2 (nightly)** — needs pass 0, which needs Drive.
- **Load counter and recompute reason log** — permanent on the page.

## 2026-09-09 20:39:00Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:39:44Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:40:19Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:40:19Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:40:20Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:40:21Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:40:21Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges


---

# BASELINE — 2026-09-10. Regress against this.

| | |
|---|---|
| **graph content hash** | `a53462823ca26466fc5e6b3bf18615ec51bb96ed003249a866f7a29f4dc567e8` |
| plugin version | `0.1.4` |
| taxonomy version | `2` |
| nodes / edges | **5,048 / 36,677** |
| validate | **0 FAIL, 6 WARN**, 17 categories, all fault-injection tested |
| tests | **44 passing** |

## Final eval

| set | score |
|---|---|
| original 22 | **20/22 = 91%** |
| fresh 5 (written against the finished graph, never rehearsed) | **5/5 = 100%** |
| **combined** | **25/27 = 93%** |
| **fabrications** | **0** |
| correctly-unanswerable | **4/4** |

By kind: single-hop 8/8 · multi-hop 6/8 · single+observation 2/2 · fresh 5/5.

**The two failures are query problems, not data problems, and are left failing
deliberately.** Q13: searching alert text for `owner` returns 12 workflows where
only 3 carry the clause *"ownership is unclear"*. Q14: searching `drop` returns 3
where 2 are about **rating** drops. The graph holds both answers; tightening a
query against a known answer would make the score meaningless.

## Node and edge counts at baseline

| node | count | | edge | count |
|---|---|---|---|---|
| instructor | 3,817 | | sourced_from | 32,656 |
| module | 922 | | teaches | 2,239 |
| workflow | 92 | | expert_in | 1,155 |
| person | 43 | | contains | 351 |
| domain | 42 | | belongs_to | 92 |
| program | 42 | | owned/supported/delivered_by | 156 |
| theme | 16 | | covers | 28 |
| | | | depends_on / workflow_owned_by | **0, by design** |

## Render

Simulation cools to zero and **freezes at 366 frames**. Decorative drift is
paint-time only at 1.6px amplitude with a per-node phase; it never writes to
`node.x`. Verified by `eval/drive_dom.mjs`:

```
click -> coords byte-identical : true
click -> sim clock unchanged   : true
drift moves the PAINT          : true
drift leaves node.x/y UNTOUCHED: true
filter toggle -> sim restarted : true
```

## 2026-09-09 20:41:22Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:41:23Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:41:59Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 76 | skipped 1 | extracted 74 | failed 1
- Manifest diff: +1 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:42:31Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:42:32Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:42:32Z — 04_build_graph

- Nodes 5049 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:42:33Z — 05_render_html

- graph.html 3364 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:42:34Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5049 nodes, 36677 edges

## 2026-09-09 20:43:06Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -1 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract
    - REBASELINE accepted: 0 changed, 1 removed
        NEXT.md

## 2026-09-09 20:43:17Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:43:53Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:43:53Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:43:54Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:43:54Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:43:55Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges

## 2026-09-09 20:44:07Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:44:48Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:44:48Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:44:49Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:44:49Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:44:50Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges

## 2026-09-09 20:45:16Z — 01_walk_corpus

- Source: `local-folder`  **NOT DRIVE — pass 0 has never run**
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-09 20:45:56Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-09 20:45:56Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:45:57Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-09 20:45:57Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-09 20:45:58Z — validate

- validate: 0 FAIL, 6 WARN, 9/17 categories exercised, 5048 nodes, 36677 edges


**Baseline corrected after the final refresh.** Adding `NEXT.md` made it a corpus
file node — the same class as `commands/` and `eval/`, and **the count check
caught it a second time.** `OWN_DOCS` in pass 1 now lists every root-level
document of ours. Final hash `a53462823ca26466fc5e6b3bf18615ec51bb96ed003249a866f7a29f4dc567e8`, plugin `0.1.4`.

## 2026-09-09 20:45:59Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-09 20:46:00Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:31:16Z — 00_fetch_drive (ok)

- Account: `np-autopilot-drive-reader@np-autopilot.iam.gserviceaccount.com`
- Folder id: `1eBu4P3DtjazCS50dmvViuWsJxEMGiaQL`
- Location: `my_drive`
- Scope: `https://www.googleapis.com/auth/drive.readonly`
- Cache: `.drive-cache`
- Files seen: 75 | fetched: 75 | exported: 0 | skipped current: 0 | failed: 0

## 2026-09-16 18:49:23Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:49:54Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:49:55Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:49:55Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:49:56Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:49:56Z — validate

- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:51:43Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:52:14Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:52:14Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:52:15Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:52:15Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:52:16Z — validate

- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:52:39Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:53:10Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:53:10Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:53:11Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:53:11Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:53:12Z — validate

- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:53:44Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:54:14Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:54:15Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:54:15Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:54:16Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:54:16Z — validate

- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:55:40Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:56:12Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:56:12Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:56:13Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:56:13Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:56:14Z — validate

- validate: 1 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:56:48Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:57:23Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:57:23Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:57:24Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:57:25Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:57:25Z — validate

- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-16 18:59:20Z — 01_walk_corpus

- Source: `drive-cache`
- Found 75 | skipped 1 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-16 18:59:53Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-16 18:59:54Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-16 18:59:55Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-16 18:59:55Z — 05_render_html
- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-16 18:59:56Z — validate
- validate: 0 FAIL, 6 WARN, 10/18 categories exercised, 5048 nodes, 36677 edges

## 2026-09-17 07:28:21Z — 01_walk_corpus

- Source: `drive-cache`
- Found 74 | skipped 0 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-17 07:28:51Z — 02_extract

- Candidates 32656 | rejected 185 | blank identifiers retained 15
    - domain: 42 raw, 42 distinct
    - instructor: 15617 raw, 3817 distinct
    - module: 15195 raw, 922 distinct
    - person: 1652 raw, 63 distinct
    - program: 42 raw, 42 distinct
    - theme: 16 raw, 16 distinct
    - workflow: 92 raw, 92 distinct

## 2026-09-17 07:28:52Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-17 07:28:53Z — 04_build_graph

- Nodes 5048 | edges 36677
    - belongs_to: 92
    - depends_on: 0
    - workflow_owned_by: 0
    - owned_by: 55
    - supported_by: 58
    - delivered_by: 43
    - covers: 28
    - contains: 351
    - expert_in: 1155
    - teaches: 2239
    - sourced_from: 32656

## 2026-09-17 07:28:53Z — 05_render_html

- graph.html 3363 KB | rendered 2998 nodes (2096 connected, 902 isolated) and 4021 edges

## 2026-09-17 07:28:54Z — validate

- validate: 0 FAIL, 6 WARN, 12/20 categories exercised, 5048 nodes, 36677 edges

## 2026-09-18 15:11:38Z — 01_walk_corpus

- Source: `drive-cache`
- Found 74 | skipped 0 | extracted 73 | failed 1
- Manifest diff: +0 added, ~0 changed, -0 removed
    - FAILED `01-workflows/Taking Class Confirmation Template.png` — image with no text layer — nothing to extract

## 2026-09-18 17:05:59Z — validate

- validate: 0 FAIL, 6 WARN, 13/20 categories exercised, 5048 nodes, 36677 edges

## 2026-09-18 17:53:43Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-18 18:22:48Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0

## 2026-09-18 18:23:27Z — 03_resolve

- Nodes 4974 | alias merges applied 23 | fuzzy proposed 2 | applied 0
