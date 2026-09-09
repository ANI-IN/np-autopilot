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
