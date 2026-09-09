# 06 — Evaluation Set (20 questions)

Every answer below is verified against the file cited. I read each one; none is inferred.

## Eval-key re-verification against R5 — 2026-09-09

R5 warns that blank cells shift the cadence column in `Domains_Courses
Owners.xlsx`. Five questions read that sheet — **Q3, Q7, Q8, Q11, Q12** — and Q8
depends on the cadence column directly. All five were re-read **positionally**
(`openpyxl`, index-addressed, blanks preserved as `None`) before freezing.

**Result: all five keys are CONFIRMED correct. No corrections needed.**

| Q | Reads | Positional re-read | Verdict |
|---|---|---|---|
| Q3 | Cloud, r18 | delivery `Sourish`, primary `Animesh`, secondary `Utkarsh, Shashi`, cadence `Every Week` | ✅ as keyed |
| Q7 | TPM r9 / EM r10 | `Every 3 weeks` / `Every Week`; both primary `Adil`, secondary `Animesh, Deval`, delivery `Tamanna` | ✅ as keyed |
| Q8 | cadence column, all 42 rows | `Advanced ML Ops` (r40) is the **only** row whose cadence is `Discontinued` | ✅ as keyed |
| Q11 | primary + secondary columns | `Animesh` primary on 10, secondary on 8, total 18 | ✅ as keyed |
| Q12 | Security, r21 | delivery `Anshuman`, primary `Animesh`, secondary `Utkarsh, Shashi`, cadence `Once a month` | ✅ as keyed |

**Why R5 did not bite.** R5 is a hazard of the *reading method*, not a defect in
the data. A parser that compacts non-empty cells shifts `Every Week` into the
owner column on row 8 (`Early Engineering`, blank secondary); an index-addressed
read does not. The blank-bearing rows — 8, 13, 14, 30, 33, 35, 39, 41, 42, 43 —
all resolve correctly when read positionally. **R5 should be restated as a
build-time constraint on the extractor, not as a caveat on the eval key**, and
`config/taxonomy.yaml` enforces it with the `cadence_vocabulary` guard: no
`Person` label may equal a cadence or stage string.

## Eval-key re-verification against the Q21 bug class — 2026-09-09

A second, distinct hazard from R5. R5 is **column shift** across cells, fixed by
positional reads. Q21 exposed **within-cell splitting**: `Deval, Srushith, , Adil`
contains a double comma, and a parser that splits and then indexes positionally,
or that trusts the token count, loses a name. R5's cadence-vocabulary guard is
**structurally blind to this** — it can only catch a wrong value landing in a
person field, never a right value silently vanishing.

Every multi-value owner cell in the sheet was re-tokenised. **32 cells hold more
than one name. Exactly 2 produce an empty token**, both the same string:

| Row | Domain | Column | Raw | Parsed |
|---|---|---|---|---|
| 36 | `Agentic AI - TPM/Pm` | Primary | `Deval, Srushith, , Adil` | Deval · Srushith · Adil |
| 37 | `Agentic AI - EM` | Primary | `Deval, Srushith, , Adil` | Deval · Srushith · Adil |

**Result for the four questions: all four CONFIRMED. No corrections.**

| Q | Cells read | Multi-value? | Empty token? | Verdict |
|---|---|---|---|---|
| Q3 | r18 Cloud — primary `Animesh`, secondary `Utkarsh, Shashi`, delivery `Sourish` | secondary only, 2 clean tokens | no | ✅ |
| Q7 | r9 TPM / r10 EM — secondary `Animesh, Deval` ×2 | secondary only, 2 clean tokens | no | ✅ |
| Q11 | primary + secondary columns, all 42 rows | **`Animesh` appears in no multi-value primary cell**; his 8 secondary cells are all clean `Animesh, Deval` | no | ✅ **10 primary / 8 secondary / 18 total stands** |
| Q12 | r21 Security — primary `Animesh`, secondary `Utkarsh, Shashi`, delivery `Anshuman` | secondary only, 2 clean tokens | no | ✅ |

The two defective cells touch only rows 36–37, which none of Q3/Q7/Q11/Q12 reads.
**Q21 is the only question in the set exposed to this bug, which is why it found
it.**

### Two further within-cell hazards found while checking

1. **`/` is also a separator.** `r28 Kunal/Abhishek` and `r29 Abhishek/ Rupali`
   are two people each. A comma-only split yields the phantom person
   `Kunal/Abhishek` and loses two real ones. Affects `delivered_by`, not the four
   questions above.
2. **`/` also appears inside a Domain label.** `r36 Agentic AI - TPM/Pm`. So the
   `/` rule must apply to **owner columns only** — splitting domains on `/` would
   invent a domain called `Pm`. These two facts are one row apart.

Both are now `validate.py` rules in `config/taxonomy.yaml`, together with a hard
fail on any multi-value cell that yields an empty token.

**One imprecision in Q8's key, corrected.** Its "wrong answer looks like" note
says `Coding TC`/`SysD TC` "show `NA`, which means *no cadence*". True, but
incomplete: **seven** rows have a genuinely **blank** cadence (13 `Coding
Pathway`, 14 `System Design Pathway`, 30 `Flagship ML/ ML Program`, 39 `Project-
Up`, 41 `AI Data Science Switch-up (DS 3.0)`, 42 `Advanced ML Interview Prep`, 43
`FDE`), which is different again from the literal `NA`. A passing answer must not
treat blank, `NA`, or `TBD` as discontinued.

**Composition — CORRECTED 2026-09-09.** The earlier line read *"8 single-hop ·
8 multi-hop · 4 correctly-unanswerable"*. That over-counted multi-hop by two: my
own annotations already conceded that **Q10** is a property lookup and **Q16**'s
second half is a file observation, not a traversal. Leaving them ticked as
multi-hop inflated the number the set exists to measure.

**Real composition of the 20: 8 single-hop · 6 multi-hop · 2 single-hop +
observation (Q10, Q16) · 4 correctly-unanswerable.**

Two genuine replacement traversals — **Q21** and **Q22** — are added below, so
the set now carries **8 true multi-hop questions out of 22**. Both were verified
by a positional re-read of the source sheet, not inferred.
**Coverage:** all 16 themes are touched by at least one question. Questions 19 and 20 probe contradictions found in A2.

**How to score.** A question passes only if the answer is correct **and** carries a citation to the right file. An uncited correct answer is a **fail** — the whole point is grounding. For Q13–Q16 the *only* passing answer is an explicit "not in the corpus"; a plausible-sounding invention is the worst outcome and should be scored **negative** in review even though the harness records it as a fail.

---

## A. Single-hop (8)

### Q1
**Question:** What is the alert condition list for *Class Reschedule / Cancellation Exception Management*?
**Expected:** Four conditions: only the live class is moved while linked TCS/ARS remains unchanged; instructor availability is assumed rather than confirmed; learners receive conflicting dates; the revised week creates a cohort conflict.
**Source:** `00-master/Team_Task___Workflow_Inventory` → workflow `3.7`
**Hops:** 1 · **Wrong answer looks like:** generic rescheduling advice, or inventing a notice period.

### Q2
**Question:** How much effort does *Instructor Hiring and Evaluation* take per candidate?
**Expected:** **1.5–2 hrs / candidate**
**Source:** same file → workflow `2.2`, `- Effort:` line
**Hops:** 1 · **Wrong answer looks like:** quoting the effort for `2.4 New Instructor Onboarding` (1–3 hrs / instructor) — adjacent row confusion.

### Q3
**Question:** Who is the primary owner of the **Cloud** domain, and who backs them up?
**Expected:** Primary **Animesh** (Animesh Kumar); secondary **Utkarsh, Shashi**; delivery team member **Sourish**; cadence **Every Week**.
**Source:** `00-master/Domains_Courses Owners.xlsx` → `Sheet1`, row 18
**Hops:** 1 · **Wrong answer looks like:** returning the SRE row (row 19, same owners, different delivery POC) or dropping the secondary owners.

### Q4
**Question:** Which theme contains the most workflows, and how many?
**Expected:** **`4. CONTENT / CURRICULUM`**, with **15**.
**Source:** `Team_Task___Workflow_Inventory` → `##`/`###` structure
**Hops:** 1 · **Wrong answer looks like:** `2. INSTRUCTORS` (9, the second largest), or repeating the file's wrong total of 91.

### Q5
**Question:** What are the steps in the *JD Creation* workflow?
**Expected:** Six steps: review the previous JD for reference → understand the specific course/module requirements → identify required technical skills, teaching experience and relevant expertise → create/update the JD → review and finalize → share with the relevant team for hiring.
**Source:** same file → workflow `2.1`
**Hops:** 1 · **Wrong answer looks like:** a plausible generic JD process not drawn from the file.

### Q6
**Question:** Which single workflow makes up the theme *TECHNICAL / AI OPERATIONS*, and what does it cover?
**Expected:** **`16.1 Cohort API Key Access & Cost Control`** — the only workflow in theme 16. Covers per-learner API keys, gateway/proxy routing, model allow-lists, rate limits, spend quotas, revocation.
**Source:** same file → theme `16`
**Hops:** 1 · **Wrong answer looks like:** claiming several workflows, or pulling in `4.12 Weekly Agentic AI Module / Repository Update`.

### Q7
**Question:** What cadence is set for the **TPM** domain, and how does it differ from **EM**?
**Expected:** TPM = **Every 3 weeks**; EM = **Every Week**. Both: primary **Adil**, secondary **Animesh, Deval**, delivery **Tamanna**.
**Source:** `Domains_Courses Owners.xlsx` → `Sheet1`, rows 9 and 10
**Hops:** 1 · **Wrong answer looks like:** treating them as identical because owners match.

### Q8
**Question:** Which domains are marked as no longer running?
**Expected:** **`Advanced ML Ops`** — cadence field reads **`Discontinued`** (row 40). It is the only one.
**Source:** `Domains_Courses Owners.xlsx` → `Sheet1`, row 40
**Hops:** 1 · **Wrong answer looks like:** "none", or listing domains with a blank cadence (`Coding TC`/`SysD TC` show `NA`, which means *no cadence*, not discontinued).

---

## B. Multi-hop (8)

### Q9
**Question:** Which workflows in the *INSTRUCTORS* theme have an alert about something being **pending**?
**Expected:** Exactly three — **`2.2`** (*demo/evaluation is pending*), **`2.4`** (*alumni training request is pending*), **`2.5`** (*training session is pending*). Verified by scanning all nine theme-2 alert lines.
**Source:** `Team_Task___Workflow_Inventory` → theme 2 alert lines
**Hops:** 2 (theme → workflows → alert text) · **Wrong answer looks like:** returning all 9 theme-2 workflows without filtering.

### Q10
**Question:** Which tools are named anywhere in the workflow inventory, and which workflow uses **Discord**?
**Expected:** **Six** tools: **Zoom, Uplevel, LinkedIn, Discord, GitHub, Google Form** — 8 tool→workflow links in total. Discord appears in exactly one workflow, **`2.4 New Instructor Onboarding & Training`** ("add instructor to Discord"), which is also its only alert mention. *(Tools are a property on Workflow, not nodes — see doc 05.)*
**Source:** same file, full-text
**Hops: 1 — RECLASSIFIED.** `tools` is a property on `Workflow` (doc 05, D-Q3), so this is a property scan, not a traversal. It stays in the set because it is a good scope test; it no longer counts toward the multi-hop total. · **Wrong answer looks like:** listing tools from elsewhere in the corpus (n8n, Jira, Zapier appear in *other* files but **not** in the workflow inventory) — a scope error.

### Q11
**Question:** Everything **Animesh** owns as primary — how many domains, and which?
**Expected:** **Primary owner on 10 domains** — Backend, Fullstack, Test Engineering, Android, iOS, Cloud, SRE, Frontend, Security, Embedded. **Secondary owner on a further 8** — Machine Learning (IP course), Data Science (IP course), Data Engineering, DABA, TPM, EM, PM, GPM. **18 domains total, 10 as primary.** Both spellings must resolve to one person (`Animesh` / `Animesh Kumar`, employee **IK-398**).
**Source:** `Domains_Courses Owners.xlsx` → `Sheet1` (primary column) + `For Slack` r019 + `IAims!Q42025`
**Hops:** 3 (person → alias resolution → domains) · **Wrong answer looks like:** counting `Animesh` and `Animesh Kumar` as two people; conflating primary with secondary; or reporting 18 without distinguishing the two roles.

### Q12
**Question:** For the **Security** domain — who owns it, what program covers it, and which module does the security programme start with?
**Expected:** Owner **Animesh** (secondary Utkarsh, Shashi; delivery Anshuman; cadence Once a month). Programs: **Security Engineering EdgeUP KYP** and **Security Engineering Interview Preparation Program**. First module: **Week 1 – Applied Cryptography**.
**Source:** `Domains_Courses Owners.xlsx!Sheet1` r21 → `04-programs/CUR-Security Engineering *.pdf` → `02-curriculum/Resource Collection Mastersheet!Security Engineering` (and `03-instructors/Instructor_Onboarding_Steps_Template`, which lists the same 7-week structure)
**Hops:** 3 (domain → person, domain → program → module)

### Q13
**Question:** Which workflows mention **ownership being unclear** as an alert, and what does that say about our process?
**Expected:** Three: **`5.5 Learner Issue Investigation`**, **`8.4 Cross-Channel Ticket Analysis`**, **`14.1 SOP Creation`**. It is the only substantive alert clause repeated across more than one workflow — an unresolved-ownership theme spanning learner support, ops and documentation.
**Source:** `Team_Task___Workflow_Inventory`, alert lines
**Hops:** 2 · **Wrong answer looks like:** returning the 12 near-identical "no clear owner" phrasings without noticing they are different clauses.

### Q14
**Question:** *"What breaks if an instructor drops shortly before a class?"* — what does the corpus actually say?
**Expected:** Two relevant places, **and no notice-period rule anywhere**. `11.5 B2B Instructor Scheduling & Session Confirmation` alert: *"there is no alternative if the instructor drops."* `3.7 Class Reschedule / Cancellation Exception Management` gives the recovery workflow. A good answer states plainly that **the corpus defines no 48-hour or any other threshold**.
**Source:** `Team_Task___Workflow_Inventory` → `11.5`, `3.7`
**Hops:** 2 · **Wrong answer looks like:** inventing a 48-hour policy because the question implies one. **This is the most important question in the set** — it is the brief's own example, and the honest answer is partial.

### Q15
**Question:** Who teaches **Python for GenAI**, and what is their average rating?
**Expected:** **Anshaj Khare — 4.73 across 4 classes**; **Kuldeep Singh — 4.66 across 3 classes**. Backup chain elsewhere in the same workbook: Anshaj Khare → Kuldeep → Hardik G → Shashank Gupta.
**Source:** `03-instructors/AgenticAI Instructors Training Plan.xlsx` → `Preferred SMEs for Each Topic`, cross-checked with `M_SME_App. Agentic AI`
**Hops:** 3 (module → instructor → rating)

**Verification status — reconciled 2026-09-09. The answer IS verified.** The
file was read for eval verification but was never included in any
entity-extraction scan; those are different passes and only the second one was
missing. Re-read positionally today to be certain:

- `Preferred SMEs for Each Topic` r3–r5 — `Python for GenAI` → **Anshaj Khare
  4.73 / 4 classes**, **Kuldeep Singh 4.66 / 3 classes**, Hardik Gupta 4.64 / 2.
- `M_SME_App. Agentic AI` r3 — backup chain **Anshaj Khare → Kuldeep → Hardik G
  → Shashank Gupta**.

Both match the key exactly. **Q15 stands.**

**But the taxonomy gap it exposed is real.** The `teaches` edge names this file
as its source while the `instructor` node type does not list it among the five
rosters — so as specified, the edge had a source the node type never read. That
is now recorded as a B4 blocker: this workbook has 18 sheets of instructor and
rating data and must be added to the instructor scan before any instructor count
is treated as final.

### Q16
**Question:** Which workflows would be affected if **Uplevel** (the learner platform) went down?
**Expected:** Exactly two workflows name Uplevel: **`8.3 Refund Analysis and Tracking`** and **`8.5 Learner Journey / Sales Call Analyzer & Next-Best Action`** — both use it as an *evidence source* (checking learner activity/progress), not as a delivery channel. A good answer also notes Uplevel links saturate `02-curriculum/*` (158 mentions), so curriculum delivery depends on it far more broadly than the workflow inventory implies — **while being explicit that this second half is an observation about file contents, not a graph traversal.**
*(Corrected: my first draft wrongly attributed Uplevel to `4.8`/`4.15`.)*
**Source:** `Team_Task___Workflow_Inventory` + `02-curriculum/Resource Collection Mastersheet`
**Hops: 1 + an observation — RECLASSIFIED.** The first half is a `workflow.tools` property scan; the second half is a full-text count over `02-curriculum/*`, which is a file observation and not a graph traversal at all. Counted as single-hop + observation, not multi-hop. · **Wrong answer looks like:** claiming a large number of workflows depend on it without evidence from the inventory.

---

### Q21  *(replacement traversal — genuine multi-hop)*
**Question:** Which domains does **Adil** own as primary, and which of them has **no program document** in the corpus?
**Expected:** **11 domains as primary** — Machine Learning (IP course), Data Science (IP course), Data Engineering, DABA, TPM, EM, PM, GPM (Growth Product Management), Agentic AI - TPM/Pm, Agentic AI - EM, Agentic AI - SWE. **Adil is secondary owner on zero domains.** Of the 11, **GPM (Growth Product Management)** and the three **Agentic AI** domains have no matching program PDF among the 42.
**Source:** `00-master/Domains_Courses Owners.xlsx!Sheet1` rows 4–7, 9–12, 36–38 (primary-owner column, read positionally) → `04-programs/*.pdf`
**Hops:** 2 (person → domain → program) · **Wrong answer looks like:** reporting 8 domains by stopping at row 12 and missing rows 36–38, where the primary cell reads `Deval, Srushith, , Adil` — the **double comma** yields a blank owner token and a naive split drops or mis-assigns Adil. This is R5's second failure mode, and it is the point of the question.

### Q22  *(replacement traversal — genuine multi-hop, with an honest absence)*
**Question:** One domain is marked discontinued. Who owned it, who delivered it, and what happened to its curriculum?
**Expected:** **`Advanced ML Ops`** (row 40, cadence `Discontinued` — the only such row). Primary owners **Kalindi** and **Karthika**; secondary **M Prasad**; delivery team member **Abhishek**. **It has no program document** — no PDF among the 42 matches it — so the honest answer is that the corpus records the ownership but says **nothing about what happened to the curriculum**. A good answer states that absence rather than reaching for a plausible program.
**Source:** `00-master/Domains_Courses Owners.xlsx!Sheet1` row 40 → `04-programs/` (absence verified across all 42 PDFs)
**Hops:** 2 (domain → person; domain → program, which terminates in an absence) · **Wrong answer looks like:** attaching `Advanced Machine Learning Program (with Agentic AI)` to it — a different product with a similar name.

---

## C. Correctly unanswerable — must return "not in the corpus" (4)

### Q17  *(the `domain-owner` command must decline this)*
**Question:** Who owns the *Instructor Rating Communication* workflow?
**Expected:** **NOT IN THE CORPUS.** Workflow `8.2` exists with full workflow, effort (30–60 min/week) and four alerts — but **no file assigns owners to workflows**. Ownership exists only at *domain* level. A good answer says so and offers the domain-level owner list instead.
**Source:** absence verified across all 74 files; `Domains_Courses Owners.xlsx` is domain-keyed
**Wrong answer looks like:** naming whoever owns a plausibly-related domain, or inferring from `IAims` objectives. **This is the brief's own example question, and it currently cannot be answered.** Per the v1 decision the command is named `domain-owner` precisely so it does not promise this.

### Q18
**Question:** Which automations have been built, who owns them, and what is their status?
**Expected:** **NOT IN THE CORPUS.** No automation register exists — no "Automations" tab, no status/priority/build-type fields anywhere in the 344 worksheets. *(344 was correct when measured; the corpus is now **374 sheets / 75 files** after `UpLevel Schedule Structure.xlsx` was added mid-analysis — see BUILD_LOG round four.)*
**Source:** absence verified corpus-wide
**Wrong answer looks like:** treating `16.1 Cohort API Key Access` or `4.12 Weekly Agentic AI Module Update` as "automations", or reciting the brief's own description of a file that isn't here.

### Q19 *(probes contradiction — rating thresholds)*
**Question:** What is the current minimum acceptable class rating for a new B2C course?
**Expected:** **NOT ANSWERABLE AS A SINGLE NUMBER.** `IAims Setting Audit` holds five rubric sheets that disagree: `Rubrics - Q126` says Rating 2 = **4.50–4.60**; `Updated Rubrics - Q226` says **4.50–4.59**; `New Rubrics - Q425` and `NewTilted Rubrics - Q325 Onward` say **4.50–4.55**. All agree Rating 1 is `< 4.50`. A good answer gives the `< 4.50` floor, names the quarter-by-quarter conflict, and asks which quarter applies.
**Source:** `00-master/IAims Setting Audit _ New Programs.xlsx` → 5 rubric sheets
**Wrong answer looks like:** confidently quoting one quarter's band as *the* threshold.

### Q20 *(probes contradiction — person identity)*
**Question:** How many classes has **Karthika** taught, and what does she own?
**Expected:** **AMBIGUOUS — REQUIRES DISAMBIGUATION.** `Karthika S` (employee **IK-115**) appears in `IAims` with ratings/NPS objectives and in `Domains_Courses Owners` as primary owner of ML Switch-up, Flagship ML, India ML and India Agentic AI. A separate string `Karthika Pai` appears in `SME Tracker!Q4-24` as a *hire*. **I cannot determine whether these are one person or two.** A good answer surfaces both and asks.
**Source:** `IAims!Q226`; `Domains_Courses Owners!Sheet1` r28/r30/r33/r34; `SME Tracker - Bullseye_IK.xlsx!Q4-24`

**UPDATED 2026-09-09 — the ambiguity is resolved, and the question gets harder.**
D3 confirms `Karthika S` and `Karthika Pai` are **two different people**. A full
corpus scan then found a **third**: **`Karthika Saran`** (15 rows — a US/Canada
instructor with her own Calendly link), plus the case variants `KARTHIKA .` and
`Karthika ` with a trailing space. The passing answer is now: **name all three,
state that `Karthika S` is the internal owner and that the other two are
external, and do not merge any of them.** The bare string `Karthika` in
`Domains_Courses Owners!Sheet1` resolves to `Karthika S`.
**Wrong answer looks like:** silently merging them into one person and summing their records — precisely the failure `people-review.yaml` exists to prevent.

---

## Theme coverage check

| Theme | Covered by |
|---|---|
| 1 PROGRAM STRATEGY | Q4 (structure) |
| 2 INSTRUCTORS | Q2, Q5, Q9, Q10 |
| 3 LIVE CLASS OPS | Q1, Q14 |
| 4 CONTENT / CURRICULUM | Q4, Q16 |
| 5 LEARNER SUPPORT | Q13 |
| 6 INTERVIEW PREP | Q4 (count) |
| 7 ASSESSMENTS | Q4 (count) |
| 8 OPS | Q13, Q17 |
| 9 LEARNERS | Q4 (count) |
| 10 COHORT OPS | Q4 (count) |
| 11 B2B | Q14 |
| 12 MASTERCLASS | Q4 (count) |
| 13 RESEARCH | Q4 (count) |
| 14 DOCUMENTATION | Q13 |
| 15 METRICS | Q19 |
| 16 TECHNICAL / AI OPS | Q6 |

**Honest note:** themes 1, 6, 7, 9, 10, 12 and 13 are only touched via structural counting (Q4), not by a substantive question. If you want deeper coverage there, I would add 4–6 more questions after the first build shows what the graph can actually reach. I did not pad the set to look better.
