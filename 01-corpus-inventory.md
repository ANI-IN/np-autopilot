# 01 — Corpus Inventory (census)

**Corpus root:** `/Users/animesh/Desktop/NP-Autopilot-Corpus`
**Walked:** 2026-09-09 · read-only · zero writes to the corpus (verified: no file mtime changed)
**Method:** `find` + `file(1)` + `openpyxl` / `python-docx` / `PyMuPDF` structural probe. Script: `scratchpad/corpus_inspect.py`.

---

## Headline numbers

| Metric | Value |
|---|---|
| Files (excluding `.DS_Store`) | **74** |
| Total size | **78.4 MB** |
| Machine-readable without OCR | **73 of 74 (98.6%)** |
| Requires OCR / vision | **1** (`Taking Class Confirmation Template.png`) |
| Spreadsheet worksheets across all `.xlsx` | **344** | *(344 was correct when measured; the corpus is now **374 sheets / 75 files** after `UpLevel Schedule Structure.xlsx` was added mid-analysis — see BUILD_LOG round four.)*
| Non-blank spreadsheet rows | **153,793** |
| Subfolders | **7** |

> **Contradiction with the brief (1).** The brief says "roughly 50 files" in "one folder … I will sort them into subfolders." The corpus is **74 files** and is **already sorted** into seven numbered subfolders. There is **no `unsorted/` folder**, and there is an extra folder the brief does not mention: **`06-analysis`**.

---

## Full file table

| # | Path | Ext | Bytes | Modified | Extraction |
|---|------|-----|-------|----------|------------|
| 1 | `00-master/Domains_Courses Owners.xlsx` | .xlsx | 72,636 | 2026-09-02 | openpyxl |
| 2 | `00-master/IAims Setting Audit _ New Programs.xlsx` | .xlsx | 893,340 | 2026-09-02 | openpyxl |
| 3 | `00-master/Interview_Kickstart_-_Tools__Reviews___Acceler__B2B_` | (none) | 48,688 | 2026-09-09 | direct (UTF-8) |
| 4 | `00-master/TOOLS-REVIEWS-ACCELER-COMPLETE.md` | .md | 48,691 | 2026-09-02 | direct |
| 5 | `00-master/Team_Task___Workflow_Inventory` | (none) | 52,852 | 2026-09-09 | direct (UTF-8) |
| 6 | `01-workflows/DTC_session_Context__Domain_Techincal_coaching_session_` | (none) | 1,066 | 2026-09-09 | direct (UTF-8) |
| 7 | `01-workflows/Demo Calls for Hiring Instructors_SMEs.docx` | .docx | 8,717 | 2026-09-02 | python-docx |
| 8 | `01-workflows/Feedback_After_the_class_Template` | (none) | 1,970 | 2026-09-09 | direct (UTF-8) |
| 9 | `01-workflows/Instructor_Best_Practice___Zoom___Initial_Check_Template` | (none) | 1,511 | 2026-09-09 | direct (UTF-8) |
| 10 | `01-workflows/Instructor_Demo_Evaluation_Guide_Template` | (none) | 2,936 | 2026-09-09 | direct (UTF-8) |
| 11 | `01-workflows/RCA Template.xlsx` | .xlsx | 23,907 | 2026-09-02 | openpyxl |
| 12 | `01-workflows/SMEs_ Instructors Hiring Process at IK.docx` | .docx | 16,748 | 2026-09-02 | python-docx |
| 13 | `01-workflows/Taking Class Confirmation Template.png` | .png | 296,485 | 2026-09-02 | NO — needs OCR/vision |
| 14 | `02-curriculum/Data and Management.xlsx` | .xlsx | 711,697 | 2026-09-02 | openpyxl |
| 15 | `02-curriculum/Resource Collection Mastersheet (Software + System).xlsx` | .xlsx | 640,739 | 2026-09-02 | openpyxl |
| 16 | `03-instructors/A_sample_Mock_Session_Feedback_Documentation.docx` | .docx | 9,114 | 2026-09-09 | direct (**mislabelled** — plain text, not docx) |
| 17 | `03-instructors/AgenticAI Instructors Training Plan.xlsx` | .xlsx | 508,288 | 2026-09-09 | openpyxl |
| 18 | `03-instructors/IK_ US Instructor - Expectation Setting for Taking Classes.docx` | .docx | 40,386 | 2026-09-02 | python-docx |
| 19 | `03-instructors/Instructor_Onboarding_Steps_Template` | (none) | 8,455 | 2026-09-09 | direct (UTF-8) |
| 20 | `03-instructors/Instructors Directory.xlsx` | .xlsx | 438,764 | 2026-09-02 | openpyxl |
| 21 | `03-instructors/SME Tracker - Bullseye_IK.xlsx` | .xlsx | 912,485 | 2026-09-02 | openpyxl |
| 22 | `03-instructors/SME database (For Ops + NP).xlsx` | .xlsx | 340,301 | 2026-09-02 | openpyxl |
| 23 | `03-instructors/SME_Interview_Demo Audit Rubrics.xlsx` | .xlsx | 738,553 | 2026-09-02 | openpyxl |
| 24 | `03-instructors/US Instructor Cost Analysis.xlsx` | .xlsx | 23,217,148 | 2026-09-02 | openpyxl |
| 25 | `04-programs/ALL-COURSES-COMPLETE.md` | .md | 519,705 | 2026-09-02 | direct |
| 26 | `04-programs/CUR-Advanced Machine Learning Program (with Agentic AI)-010926-183244.pdf` | .pdf | 1,572,319 | 2026-09-02 | text layer |
| 27 | `04-programs/CUR-Android Engineering EdgeUP KYP-010926-182459.pdf` | .pdf | 922,757 | 2026-09-01 | text layer |
| 28 | `04-programs/CUR-Android Engineering Interview Preparation Program-010926-191048.pdf` | .pdf | 657,803 | 2026-09-02 | text layer |
| 29 | `04-programs/CUR-Backend  Interview Preparation Program-010926-190934.pdf` | .pdf | 682,579 | 2026-09-02 | text layer |
| 30 | `04-programs/CUR-Backend Engineering EdgeUP KYP-010926-182803.pdf` | .pdf | 927,104 | 2026-09-01 | text layer |
| 31 | `04-programs/CUR-Cloud Architect Interview Preparation Program-010926-191345.pdf` | .pdf | 657,169 | 2026-09-02 | text layer |
| 32 | `04-programs/CUR-Cloud Engineering EdgeUP KYP-010926-182946.pdf` | .pdf | 817,128 | 2026-09-01 | text layer |
| 33 | `04-programs/CUR-Data Analyst Businees Analyst EdgeUP KYP-010926-182205.pdf` | .pdf | 852,246 | 2026-09-01 | text layer |
| 34 | `04-programs/CUR-Data Analyst Business Analyst Interview Preparation Program-010926-190813.pdf` | .pdf | 656,114 | 2026-09-02 | text layer |
| 35 | `04-programs/CUR-Data Engineering EdgeUP KYP-010926-182054.pdf` | .pdf | 936,404 | 2026-09-01 | text layer |
| 36 | `04-programs/CUR-Data Engineering Interview Preparation Program-010926-190620.pdf` | .pdf | 1,066,230 | 2026-09-02 | text layer |
| 37 | `04-programs/CUR-Data Science EdgeUP KYP-010926-182130.pdf` | .pdf | 952,283 | 2026-09-01 | text layer |
| 38 | `04-programs/CUR-Data Science Interview Preparation Program-010926-190729.pdf` | .pdf | 709,320 | 2026-09-02 | text layer |
| 39 | `04-programs/CUR-EM - KYP-010926-190520.pdf` | .pdf | 631,184 | 2026-09-02 | text layer |
| 40 | `04-programs/CUR-Early Engineering Interview Preparation Program-010926-191212.pdf` | .pdf | 650,724 | 2026-09-02 | text layer |
| 41 | `04-programs/CUR-Embedded Engineering EdgeUP KYP-010926-182315.pdf` | .pdf | 885,867 | 2026-09-01 | text layer |
| 42 | `04-programs/CUR-Embedded Software Interview Preparation Program-010926-191318.pdf` | .pdf | 689,173 | 2026-09-02 | text layer |
| 43 | `04-programs/CUR-Enginnering Mnagement EdgeUP KYP-010926-182010.pdf` | .pdf | 886,660 | 2026-09-01 | text layer |
| 44 | `04-programs/CUR-FastTrack_ (Self Paced) Ad. Machine Learning(with Agentic AI) KYP-010926-183413.pdf` | .pdf | 793,781 | 2026-09-02 | text layer |
| 45 | `04-programs/CUR-Flagship Machine Learning Program (with Agentic AI)-010926-183307.pdf` | .pdf | 1,534,753 | 2026-09-02 | text layer |
| 46 | `04-programs/CUR-Forward Deployed Engineering Level-Up Program_ KYP - 2026-090926-113430.pdf` | .pdf | 716,224 | 2026-09-09 | text layer |
| 47 | `04-programs/CUR-Forward Deployed Engineering[FDE] Course _ KYP - 2026-090926-113424.pdf` | .pdf | 1,395,175 | 2026-09-09 | text layer |
| 48 | `04-programs/CUR-Forward Deployed Engineering[FDE] Upskilling Course _ KYP - 2026-090926-113428.pdf` | .pdf | 1,182,312 | 2026-09-09 | text layer |
| 49 | `04-programs/CUR-Frontend Engineering EdgeUP KYP-010926-182703.pdf` | .pdf | 939,997 | 2026-09-01 | text layer |
| 50 | `04-programs/CUR-Frontend Interview Preparation Program-010926-190849.pdf` | .pdf | 683,699 | 2026-09-02 | text layer |
| 51 | `04-programs/CUR-Full-Stack Interview Preparation Program-010926-191020.pdf` | .pdf | 682,139 | 2026-09-02 | text layer |
| 52 | `04-programs/CUR-Fullstack Engineering EdgeUP KYP-010926-182733.pdf` | .pdf | 932,028 | 2026-09-01 | text layer |
| 53 | `04-programs/CUR-Machine Learning EdgeUP KYP-010926-182241.pdf` | .pdf | 966,206 | 2026-09-01 | text layer |
| 54 | `04-programs/CUR-Machine Learning Interview Preparation Program-010926-190650.pdf` | .pdf | 681,544 | 2026-09-02 | text layer |
| 55 | `04-programs/CUR-PM-KYP-010926-190548.pdf` | .pdf | 631,631 | 2026-09-02 | text layer |
| 56 | `04-programs/CUR-Product Management EdgeUP KYP-010926-181940.pdf` | .pdf | 840,005 | 2026-09-01 | text layer |
| 57 | `04-programs/CUR-Security Engineering EdgeUP KYP-010926-182631.pdf` | .pdf | 918,648 | 2026-09-01 | text layer |
| 58 | `04-programs/CUR-Security Engineering Interview Preparation Program-010926-191534.pdf` | .pdf | 730,459 | 2026-09-02 | text layer |
| 59 | `04-programs/CUR-Site Reliability Engineering EdgeUP KYP-010926-182905.pdf` | .pdf | 837,438 | 2026-09-01 | text layer |
| 60 | `04-programs/CUR-Site Reliability Engineering Interview Preparation Program-010926-191417.pdf` | .pdf | 725,276 | 2026-09-02 | text layer |
| 61 | `04-programs/CUR-TPM EdgeUP KYP-010926-181847.pdf` | .pdf | 848,118 | 2026-09-01 | text layer |
| 62 | `04-programs/CUR-TPM-KYP-010926-190452.pdf` | .pdf | 687,650 | 2026-09-02 | text layer |
| 63 | `04-programs/CUR-Test Engineering EdgeUP KYP-010926-182838.pdf` | .pdf | 952,883 | 2026-09-01 | text layer |
| 64 | `04-programs/CUR-Test Engineering Interview Preparation Program-010926-191453.pdf` | .pdf | 695,097 | 2026-09-02 | text layer |
| 65 | `04-programs/CUR-iOS Engineering EdgeUP KYP-010926-182541.pdf` | .pdf | 925,647 | 2026-09-01 | text layer |
| 66 | `04-programs/CUR-iOS Engineering Interview Preparation Program-010926-191123.pdf` | .pdf | 666,615 | 2026-09-02 | text layer |
| 67 | `04-programs/CUR-v2 [New] AI Data Science Program-090926-113520.pdf` | .pdf | 1,796,285 | 2026-09-09 | text layer |
| 68 | `04-programs/Interview_Kickstart_-_Complete_Course_Reference` | (none) | 522,037 | 2026-09-09 | direct (UTF-8) |
| 69 | `05-operations/Discord Server List - NP team.xlsx` | .xlsx | 52,780 | 2026-09-02 | openpyxl |
| 70 | `05-operations/New Combined Schedule.xlsx` | .xlsx | 4,501,014 | 2026-09-02 | openpyxl |
| 71 | `05-operations/Operational Metrics.xlsx` | .xlsx | 7,741,646 | 2026-09-02 | openpyxl |
| 72 | `06-analysis/Domain Classes Poll Feedback 2026.xlsx` | .xlsx | 1,099,071 | 2026-09-02 | openpyxl |
| 73 | `06-analysis/Example RCA .xlsx` | .xlsx | 23,800 | 2026-09-02 | openpyxl |
| 74 | `06-analysis/MLSU_Gen AI_Agentic AI Classes Poll Feedback 2026.xlsx` | .xlsx | 1,845,106 | 2026-09-02 | openpyxl |

---

## Counts by extension

| Extension | Count | Notes |
|---|---|---|
| `.pdf` | 42 | All 8-page "KYP" program specs, all with a real text layer |
| `.xlsx` | 17 | The analytic core — 344 sheets, 153,793 rows |
| *(no extension)* | 8 | Google Docs exports; all UTF-8 Markdown-ish text |
| `.docx` | 4 | One is **mislabelled** (see below) |
| `.md` | 2 | Both are near-duplicates of no-extension files |
| `.png` | 1 | The single unreadable file |

## Counts by subfolder

| Subfolder | Files | What it holds |
|---|---|---|
| `04-programs` | 44 | 42 KYP program PDFs + 2 course-reference dumps |
| `03-instructors` | 9 | Instructor/SME directories, trackers, cost analysis |
| `01-workflows` | 8 | Process templates and SOPs |
| `00-master` | 5 | **The master workflow inventory + owner map + I-Aims** |
| `06-analysis` | 3 | Poll feedback, RCA example |
| `05-operations` | 3 | Schedule, metrics, Discord list |
| `02-curriculum` | 2 | Resource-collection mastersheets |

---

## Files I cannot read, and why

This is the short list the brief asked me to prioritise. **It is genuinely short.**

| File | Problem | Impact | Recommendation |
|---|---|---|---|
| `01-workflows/Taking Class Confirmation Template.png` | Binary image, 1964×1084 RGBA. No text layer. | Low — it is a *template* screenshot, likely a Discord/email confirmation message. Its content is probably duplicated in `Instructor_Best_Practice___Zoom___Initial_Check_Template`. | Record as `extraction_method: none, reason: image`. Do **not** OCR in v1. Revisit only if a query needs it. |

**Everything else extracts.** Two caveats that are *not* failures but will bite a naive walker:

1. **`03-instructors/A_sample_Mock_Session_Feedback_Documentation.docx` is not a `.docx`.** It has no `PK` zip magic — it is plain UTF-8 text with a `.docx` extension. `python-docx` raises on it. The walker **must sniff magic bytes, not trust the extension**, or it will log a false failure.
2. **Do not name a pipeline script `inspect.py`.** My first inspection run failed on *every* `.xlsx` and `.docx` with a confusing `circular import` / `getargspec` error. Cause: the script shadowed the stdlib `inspect` module that `openpyxl` and `python-docx` both import. This cost one run. Worth a line in `CLAUDE.md`.

---

## Duplicates, near-duplicates and stale copies

**No two files are byte-identical** (verified by md5 across all 74). But there are two near-duplicate *pairs*:

| Pair | Sizes | Difference |
|---|---|---|
| `00-master/Interview_Kickstart_-_Tools__Reviews___Acceler__B2B_` vs `00-master/TOOLS-REVIEWS-ACCELER-COMPLETE.md` | 48,688 B vs 48,691 B | Identical line/heading counts (1171 lines, 66 headings). Differ by **3 bytes** — the title uses a hyphen in one and an em-dash in the other. |
| `04-programs/ALL-COURSES-COMPLETE.md` vs `04-programs/Interview_Kickstart_-_Complete_Course_Reference` | 519,705 B vs 522,037 B | Same content family (both 857-char long lines, same TOC). ~2.3 KB apart. |

**Recommendation:** treat each pair as **one logical document with two exports**. If both are ingested, every entity in them doubles and the graph silently inflates. Handle with a near-duplicate check (normalised-text hash) in Pass 1, keep the newer mtime, and record the dropped twin in the build log. Do **not** delete either file — the corpus is read-only.

**Stale copies inside files** (not file-level, but worth flagging now): `IAims Setting Audit` contains both `Adil` and `Copy of Adil` sheets with the same content, and seven historical rubric sheets (`Q126`, `Q226`, `Q425`, `Q325`, `Q4 2024` …). Quarter-stamped sheets are history, not current state.

---

## Content-type guess per file group, with confidence

| Group | Files | My guess | Confidence |
|---|---|---|---|
| `00-master/Team_Task___Workflow_Inventory` | 1 | **The taxonomy skeleton** — 92 tasks, 16 themes, Workflow/Effort/Alerts | **99%** — read in full |
| `00-master/Domains_Courses Owners.xlsx` | 1 | **The only owner mapping in the corpus** — 42 domains → people | **99%** — read in full |
| `00-master/IAims Setting Audit` | 1 | Per-employee quarterly goals + rating rubrics; carries **employee IDs** | 95% |
| `04-programs/CUR-*.pdf` | 42 | Program specs ("KYP" = Know Your Program), 8pp each, templated | 90% |
| `03-instructors/*` | 9 | Instructor + SME directories, training trackers, **cost/comp** | 90% |
| `02-curriculum/*` | 2 | Module → resource → instructor mapping per domain | 90% |
| `05-operations/New Combined Schedule` | 1 | 62 sheets; class-by-class delivery schedule + confirmations | 90% |
| `05-operations/Operational Metrics` | 1 | 102 sheets; **mostly 2019–2024 historical** coaching metrics | 80% |
| `06-analysis/*` | 3 | Class-rating poll feedback + RCA worked example | 85% |
| `01-workflows/*` | 8 | Instructor-facing templates and hiring SOPs | 85% |

---

## ⚠ Files containing personal data, compensation, or performance ratings

**Flagged, not excluded.** Decision is yours (Appendix open question 1 and 2).

### Tier 1 — direct personal data of named individuals (external instructors/candidates)

| File | What it contains |
|---|---|
| `03-instructors/Instructors Directory.xlsx` | Full names, **personal Gmail addresses**, LinkedIn URLs, Discord IDs, bios, timestamps. Includes a LinkedIn-enrichment sheet with member identifiers. |
| `03-instructors/SME Tracker - Bullseye_IK.xlsx` | Candidate names, **emails, phone numbers**, employer, current role, interview stage, demo dates, **rejection reasons** ("Rejected, Re-applying" sheet), reviewer feedback |
| `03-instructors/SME database (For Ops + NP).xlsx` | SME master list, joiners **and exits** |
| `05-operations/New Combined Schedule.xlsx` | `Instructor Data` sheet: names, personal emails, **phone numbers**, country |
| `02-curriculum/Data and Management.xlsx` | `Instructor Details` sheet: names, Gmail, LinkedIn, topic expertise |
| `02-curriculum/Resource Collection Mastersheet` | `Indian Instructors` sheet: names, emails, LinkedIn, Discord links |

### Tier 2 — compensation and cost

| File | What it contains |
|---|---|
| `03-instructors/US Instructor Cost Analysis.xlsx` | **23.2 MB, 74,961 rows** — the single largest file. Sheets include `2025 - Hourly updated rates`, `2026 - Hourly Updated Rates`. This is **per-instructor pay-rate data**. |

### Tier 3 — performance ratings about named people

| File | What it contains |
|---|---|
| `00-master/IAims Setting Audit` | Named employees + employee IDs + quarterly goal attainment + `Manager's Ratings`, `People Effectiveness Score` |
| `03-instructors/AgenticAI Instructors Training Plan.xlsx` | Sheets literally titled **`WIP`** and **`Instructors`** containing free-text judgements against named instructors: *"Bad ratings"*, *"GenAI ratings are not good"*, *"Unresponsive"*, *"Resigned"* |
| `06-analysis/*Poll Feedback*.xlsx` | Per-class ratings attributable to a named instructor |
| `03-instructors/SME_Interview_Demo Audit Rubrics.xlsx` | Demo audit scores per candidate |

### ⚠ Tier 0 — LEARNER PERSONAL DATA AT SCALE (corrected 2026-09-09, second pass)

**My first-pass claim "no learner personal data found" was WRONG.** It was based on reading sheet headers, not rows. A full scan of all 344 sheets / 153,793 rows / 2,539,079 cells found:

| Measure | Count |
|---|---|
| **Distinct email addresses** | **8,001** |
| ...of which external/personal (non-`@interviewkickstart.com`) | **7,976** (7,313 are `gmail.com`) |
| Distinct phone numbers | **8,074** |
| Distinct LinkedIn URLs | **4,524** |
| Distinct email domains | 279 |

**The largest concentration is learner data, and it is explicit, not inferred:**

`05-operations/Operational Metrics.xlsx` — 20,338 email occurrences, 14,030 phone occurrences. Sheet **`Cohort Type Wise Coaching Raw D`** (12,986 rows) has these literal column headers:

```
country | slot_type | Category | slot_start | slot_end | start_time | end_time
        | learner | learner_email | Coach | Session_Title
```

Every row is a named learner, their personal email, the coach they met, and the session title — 12,986 coaching appointments from 2023 onward. Sheet **`Single cohort per student all w`** (9,789 rows) has a `Student Name` column against weekly activity.

**`03-instructors/US Instructor Cost Analysis.xlsx` is not what its filename says.** It is **HR payroll data exported from Paycor** (there are `Paycor Codes` and `Paycor Labour Codes` sheets). Column headers include:

```
BU | Employee File Number | Full Name | Email | Department | Employement Status | LWD
```

`Employement Status` values include **`Exited (Resigned)`** and **`Exited (Terminated)`**; `LWD` is last working day. Rates are per labour code (`50 - Live Class`, `51 - Coaching`, `52 - Onboarding`, `53 - Pre Live Session Prep`, `54 - Assignment-Test Review`, `55 - Mock`, `56 - Mock - Late Cancellation`). 4,697 email occurrences, 5,387 distinct names.

This is employee compensation **plus termination records**, not instructor invoicing.

**My recommendation** (yours to accept or override):
- **Exclude from the graph in v1:** `US Instructor Cost Analysis.xlsx` (comp), and the free-text judgement sheets `WIP` / `Instructors` / `Instructor<>Expertise` inside `AgenticAI Instructors Training Plan.xlsx`. Rating *aggregates* are fine; **written slurs about named people should not become queryable nodes**.
- **Include but strip contact fields:** instructor directories — keep name + expertise + domain, drop email/phone/LinkedIn/Discord. The graph needs *who teaches what*, not *how to contact them*.
- **The repo is private, which is necessary but not sufficient.** A private repo still ends up on laptops and in this session's context.

---

## Open questions from A1

1. Confirm `Single cohort per student all weeks` contains no learner names — or authorise me to scan it.
2. Are the SME cost sheets in scope for v1? (Brief's own open question 2.) My recommendation: **no**.
3. `06-analysis` is not in the brief's folder list. Confirm it is a first-class document type, not a staging area.
