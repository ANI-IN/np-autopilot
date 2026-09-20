# REGISTRY INVENTORY — what is actually in the three folders

**First task of the scale-up, done as a measurement.** 2026-09-20.
`SCALE-PLAN.md` said do this before building anything; `01-corpus-inventory.md`
is the shape being copied — counts and contents, not headers.

**Nothing was built. No extractor, no registry reader, no schema.** Everything
below is read-only reconnaissance through the Drive connector on the
`b2c-courses-new-programs@` account.

---

## 0 · The registry was found, not guessed

`STATE.md` §11 warned that the three folders are named nowhere in this
repository and said to ask rather than infer from directory names. Asking turned
out to be unnecessary: the registry is a real artefact and it is discoverable.

A spreadsheet titled **`links`**, id `1GNKvvv9LM36om6QJiDuyP01r-L3N19oJGBi1Yjcun5I`,
owned by `b2c-courses-new-programs@interviewkickstart.com`, created
**2026-09-20 10:02Z** and last modified 10:22Z. Two columns, `Folder | Link`,
five rows.

| # | Row label (verbatim) | id | kind |
|---|---|---|---|
| A | `Applied Agentic AI- Whole Content folder` | `1yHZYpbJTjfxumTMU5qNvfSuLXLImJpad` | folder |
| B | `Software+System Pod whole Content folder` | `19MxiYsE8B3T-O0VqnOF7gtU_7oxlRFJo` | folder |
| C | `Data + Mangement Content folder` *(sic)* | `1aVg_UbUCsuDxv9XXICIxbmpMbjUz5ETm` | folder |
| P1 | `Domain Classes Poll Feedback 2026` | `1CcifEPJzSxaqTCguM2e6iOXW9tnjRt75ZPoskN2M-LY` | spreadsheet |
| P2 | `MLSU/Gen AI/Agentic AI Classes Poll Feedback 2026` | `1zBDUysiidZFdfHVQcOmymv7ulYOz94t5q89rw6HrYDc` | spreadsheet |

Three folders, exactly as the brief said. **The registry is not folders-only** —
two of its five rows are individual workbooks, and both are the poll workbooks
`STATE.md` §10 already flagged as carrying `Student Name` and `Student Email`.
A reader that assumes "registry = list of folders" will mis-handle 40% of it on
the first run.

`Mangement` is misspelled in row C. Per `CLAUDE.md` §1 that string is the
citation key and must be carried as `label_raw`, not corrected.

### The registry sheet is inside the corpus folder, and that has consequences

`parentId` of `links` is `1eBu4P3DtjazCS50dmvViuWsJxEMGiaQL` — the folder in
`config/drive.yaml`, the existing 75-file corpus. Two things follow, both
testable on the next run and neither yet true:

- **The export map is about to fire for the first time.** `CLAUDE.md` says every
  file in that folder is already a binary and `EXPORT_MAP` has never been
  exercised. Measured today, `links` is the **only** native Google file among
  the corpus folder's direct children (the other seven are the `00-`…`06-`
  subfolders). `00_fetch_drive.py:103` maps `…google-apps.spreadsheet` →
  `.xlsx`, so pass 0 will export it. That sentence in `CLAUDE.md` becomes false
  the next time pass 0 runs, and the code path it describes as never-exercised
  gets its first real test on a file nobody wrote it for.
- **Pass 1 will ingest it as an added file.** `01_walk_corpus.py:261` prints
  added files as `REPORT ONLY — a new document is expected traffic` and takes
  them in. File count goes 74 → 75 in the cache; `file.expect` at 74 ± 2 still
  holds, but it holds with one slot left.

Neither is a defect. Both are a control being exercised for the first time by an
input that is a *configuration file*, not corpus material — and the graph will
acquire a `file` node for the registry itself unless something excludes it.

---

## 1 · Coverage of this inventory — read this before quoting any number below

**Measured: 37 folders opened, 75 files seen, 5 decks read in full or part.**
**Discovered but not opened: at least 150 further folders.**

| | count | basis |
|---|---|---|
| Folders opened | **37** | each one a `parentId` listing |
| Folders discovered | **≥187** | every folder named in those 37 listings |
| Folders discovered but NOT opened | **≥150** | 80% of what is known to exist |
| Files seen | **75** | non-folder children of the 37 |
| Depth reached | **5 levels** in three branches | A, B and C each sampled to a leaf |

**Every count in this document is a floor, and a much weaker floor than the
corpus figures are.** The corpus numbers are floors over 50 of 75 files — two
thirds. These are floors over 37 of ≥187 folders — one fifth, and the unopened
four fifths are not a random sample, because I opened the branches that looked
richest.

**The spec's "2,000+ files" is plausible and unverified.** 187 folders at an
observed 2–8 files per leaf would land in that range, but I did not count them
and the arithmetic is an estimate, not a measurement. Do not put 2,000 in a
document as though it were measured. What *is* measured: the tree is at least
five levels deep, and the widest single listing seen was 27 entries.

---

## 2 · The three folders are three different shapes

This is the finding that decides the per-folder-extractor question, and the
three rows do not agree.

### B · `Software+System Pod` — partitioned, regular, oldest

12 subfolders, **zero loose files at the top level**. Every one is a domain with
a code prefix: `SD1: Full Stack`, `SD2: Frontend`, `SD3: Backend Engineering`,
`SD4: Test Engineering`, `SD5: Android`, `SD5: iOS`, `Sys1: Security
Engineering`, `Sys2: AWS Cloud SA`, `Sys3: Embedded Software Engineering`,
`Sys4: SRE`, plus `B2B` and `Hiring Resources - Systems & Test`.

Note `SD5` is used twice — Android and iOS. The code is not a key.

Inside, the regularity **stops**. `SD3: Backend` is clean: five
`Module-N: <topic>` folders, a lesson-plan sheet, a foundation-slides folder.
`Sys3: Embedded` is 27 entries mixing module redevelopment, sales training
material, marketing collateral review, testimonials, meeting notes, an email
course and four shortcuts. Same registry folder, same level, same naming
convention at the top — completely different internal contract one level down.

### C · `Data + Mangement` — partitioned, regular, shallow

13 subfolders, zero loose files, all domain names, **11 of 13 owned by
`operations@interviewkickstart.com`**: `TPM`, `Data Engineering`,
`Product Management`, `Machine Learning`, `Engineering Management`,
`Data Analyst/ Business Analyst`, `PMM`, `iOS`, `Backend`,
`Switch-up - Machine Learning`, `Test Engineering`, `Fullstack`, `Frontend`.

Five of the thirteen have not been modified since **2023-02-28**, the day they
were created — `iOS`, `Backend`, `Fullstack`, `Frontend`,
`Switch-up - Machine Learning`. They may well be empty. I did not open them,
and that is exactly the kind of thing a full crawl must report rather than
average away.

`Machine Learning` is the most extractor-friendly thing in the whole registry:
six children, five of them `1-supervised-learning-i` … `5-deep-learning-ii`,
numbered, lower-case, hyphenated, consistent. One folder deep it is
`Live Class & Assignment` + `sme-resources` + `sl-i-lesson-plan`. That is a
schema.

### A · `Applied Agentic AI` — not partitioned, live, mixed

24 entries at the top: **8 spreadsheets, 14 subfolders, 2 shortcuts**, files and
folders side by side. The subfolders are not a partition of a subject — they are
a mix of content (`Live Class Content`, `Finalized Content 2.0`,
`Uplevel Shared(SWEs + Common modules)`, `Uplevel Shared(Tech Prof.)`), process
(`Drafts`, `Final_test`, `Forms & Submissions`, `Ratings & Feedback`), and
**people-data** (`Hiring`, `SMEs consent`).

`Final_test` is empty. `[Do not Use]Evolution of GenAI` and `[Do not use]`
appear as folder names at two different levels — a human-readable tombstone that
no crawler will respect.

This is the folder the request is actually about, and it is the one with no
schema.

> **The three registry rows are one label for three different data contracts.**
> Anything written as "the registry crawler" will be correct for C, approximately
> correct for B, and wrong for A.

---

## 3 · File types — 75 files across the 37 folders opened

| type | count | where it concentrates |
|---|---|---|
| Google Sheets | **28** | trackers, curricula, ratings, form responses |
| Google Docs | **23** | JDs, competitor research, NPS comms, handbooks, SME lists |
| PDF | **7** | 6 of them one folder: `SD3/Backend Foundation Slides` |
| Google Slides | **4** | the actual teaching decks |
| `.pptx` | **4** | the actual teaching decks |
| Google Forms | **2** | assignment + capstone submission |
| Shortcuts | **7** | see below |

**Slides are the rarest thing in the registry and the whole point of the
request.** 8 of 75 files seen are decks. The request — *"what those files
actually teach"* — is asking about roughly a tenth of the corpus by count, while
the other nine tenths are spreadsheets and docs about programme administration.
That ratio may not hold in the 150 unopened folders; `Live Class Content`'s 16
module folders and `Uplevel Shared`'s 17 are exactly where decks would live and
I opened two of them.

**The 7 shortcuts are a scope hole.** `application/vnd.google-apps.shortcut`
resolves to a target that may sit **outside all three registry folders**. Four
are in `Sys3: Embedded` alone (`Embedded Software Engineering Curriculum`,
`Embedded SW - Slides and Documents`, `Instruction_Overview`,
`Embedded Software Engineering Plan`); `1-supervised-learning-i` holds one to
`ml-curriculum.xlsx`. A crawler that follows them silently widens the corpus
past what the registry declares; one that skips them silently drops curriculum
files. **Neither is the obvious default and the registry does not say which.**

**Ownership is dispersed.** Files seen are owned by at least 14 accounts, and
**four of them are personal `@gmail.com` addresses belonging to instructors and
SMEs, not `@interviewkickstart.com` accounts.** The addresses themselves are
deliberately not reproduced here — see the note at the end of this section.
This matters more than it looks; §5(iv).

---

## 4 · Are the folders consistent enough for per-folder extractors?

**For C: yes, for about half of it.** `Machine Learning`'s numbered module
folders have a repeating internal shape. `Data Engineering` looks similar
(`2. Data Modelling`, two interview-question banks). One extractor per domain
folder is a defensible unit of work there.

**For B: no, but for an interesting reason.** The *top* level is beautifully
regular and the level below is not. An extractor scoped to
`19MxiYsE8B3T…/SD3: Backend Engineering` would work; the identical extractor
pointed at `Sys3: Embedded Software Engineering` would meet sales collateral and
testimonials. **The consistency is one level higher than the folder that would
name the extractor** — which means per-folder extractors for B are really
per-*module*-folder extractors, and there are far more of those.

**For A: no.** There is no repeating unit. `Live Class Content` has 16
module-shaped children and `Finalized Content 2.0` has 7 audience-shaped ones
(`SWEs`, `PMs/TPMs`, `EMs`, `Notes`, `Comms`, `Floater sessions`,
`Curriculum sheets + Forms + Submissions`) — two different partitions of the same
course, both live, in one folder.

> **Per-folder extractors are viable for a minority of the registry and the
> minority is not the part anyone is asking about.** The Agentic AI folder is
> the one driving this request and it is the one with no repeating shape.

---

## 5 · Contact data, learner records and payroll-shaped sheets — all three present

The answer to *"does any of this contain contact data"* is **yes, in five
distinct shapes, four of which `sources.py`'s column allow-list has no
jurisdiction over.** This is the most important section of this document.

### (i) Learner records with personal email — confirmed, in folder A

`Agentic AI: SWE Capstone - Final Project Submission (Responses)`
(`1WTLDHrghWwoWat0y0WljiNvt-MhL5Fm5DPmhEQ1nous`), four levels down
A → `Forms & Submissions` → `Project Submissions - US` → `SWEs`.

Columns, verbatim: `Timestamp, Email Address, Please enter your name, Select your
capstone project (1 or 2)., Please enter your Capstone Project Name, Please
upload your project files for evaluation…, Deployed link of your Project`.

Rows carry real learner names against personal Gmail addresses. This is a Google
Form response sheet — **the contact column is generated by the form, not
authored**, so it is named `Email Address` every time and appears in every such
sheet by construction. There are at least **6 more form-response folders** in
folder A alone (`Assignment Submission Form (File responses)`,
`SWEs&DEs Pathway Registration form`, `Topic Expertise form`,
`Topic Expertise form - TA`, `Tech. Prof. Pathway registration`, and
`Project Submissions - US`'s other four audience folders).

`(File responses)` folders hold **learner-uploaded files**. Their contents are
whatever a student submitted.

### (ii) A LinkedIn URL list of named instructors — confirmed, in folder A

`India Agentic AI SMEs list for Websites`
(`1IQRl1aiGvQZhC3UFU9LETQY70FFmokgx-ileOJhiwvc`, 2.27 MB), in A → `SMEs consent`.

It is a roster of named SMEs grouped `SWEs` / `PMs/TPMs` / `EMs`, each entry a
name, a **LinkedIn profile URL**, and a current-and-former employer string.
Thirteen distinct people in the snippet alone.

**`CONTACT-DATA.md` declined LinkedIn for all three populations and that decision
is on record.** It was declined when the only route in was a declared column in
`sources.py`. Here it is the document's entire content — a generic extractor that
reads docs at all ingests it, and no column allow-list is involved because there
are no columns.

### (iii) A consent register — and this one changes the shape of the problem

`Agentic AI SMEs- Consent for Website/Brochures`
(`1xG_eAsrqk81gOLc6n9HhZQ4O9cxmOUahb2lCxvFNmcE`), same folder. Names by region
and role, with **per-person usage restrictions written inline**:

> `NImita - Only KYP and Brochures`
> `Laksham Kumar - only KYP with old company`

This is a record of what each named SME agreed may be published about them, and
two of them agreed to less than the others. **Ingesting the names while dropping
the restriction is worse than not ingesting at all** — it produces a graph that
asserts a person's affiliation without the condition attached to it, and the
condition is the thing that makes publishing it lawful.

Nothing in the current taxonomy can carry "this fact may be used for brochures
but not the website". That is not a property; it is a per-fact licence.

### (iv) Instructor names in file metadata — a channel with no control at all

**Four personal Gmail addresses appear as `owner` on files in the registry** —
as metadata, not as cell values. They belong to external instructors and SMEs.
The files are `IK-API-Design-presentation-RK-v3.pptx`, `Shelby's Copy of …`
(the same deck), `sl-i-lesson-plan` in `1-supervised-learning-i`, and an
`Assignment` folder under `2. Fundamentals of Agentic AI`. **The addresses are
not written into this document** — see the note at the end of this section.

And instructor names are in **filenames**: `Mike: API Design`,
`Tilo's notes by Robert`, `M5.1 - Concurrency in Practice - Yannis.pdf`,
`Build Your Advanced Agent(Low-code)-Arun`,
`Copy for Omkar - Agentic AI 2.0 Detailed Topic list`.

> **`sources.py` is an allow-list over `(file, sheet, column)`. A file owner is
> none of those three.** Any crawler that records provenance at all records the
> owner, because that is how you cite a file in someone else's Drive. The
> control that `A7B.md` identified as the real one — narrow column inclusion —
> does not reach this channel, and never did; it simply never had to, because
> every file in the current corpus is owned by the same account.

This is a **fourth instance of the A7B question 3 shape**: the guarantee holds
today for a reason nobody wrote down (single-owner corpus), and the change that
removes it looks like progress (crawl other people's Drives).

### (v) Payroll-shaped — not found, and that is a floor not a clearance

No cost, rate or hours sheet turned up in the 37 folders opened. Folder A has a
`Hiring` subfolder containing JDs and a `Content shared for Demo - Hiring`
folder; `Hiring Resources - Systems & Test` in B holds `SME JDs` and
`SME Hiring Assignments`. Those are hiring-funnel-shaped, which R18 makes the
project's most expensive category — but they are not payroll.

**I did not open 150 folders. "No payroll found" means "not in the fifth I
looked at."**

### A note on this document, and a gap it exposed

**The first draft of this file reproduced the four personal email addresses
verbatim.** They were redacted before it was committed. Names are in scope for
this project — it is a graph of named instructors, and this document names
`Mike Dolt` and `Senad Cimic` from deck slides — but email addresses and
LinkedIn URLs are the two categories `CONTACT-DATA.md` explicitly declined, and
a document arguing that the registry leaks contact data is not an exemption from
that.

**Nothing in the repository would have stopped it.**
`tests/test_no_payroll_committed.py` is the content-keyed layer — it exists
precisely because path rules are walked past by a rename or a copy — but its
`SIGNATURES` are payroll strings. It has no notion of a contact identifier. So:

> **The content-keyed commit guard covers payroll and not contact data, and the
> only thing that has kept email addresses out of tracked files is that nobody
> has had a reason to type one in.** Building for 2,000 files from other
> people's Drives is that reason: every finding about contact data is written up
> by quoting the contact data.

That is an A7B question-3 answer — the guarantee held for a reason nobody wrote
down — and unlike the four in §5 it is about *this repository*, not the corpus.
It is recorded here rather than fixed, because the fix is a new signature class
in `check_no_payroll_committed.py` and that deserves its own change with its own
negative control.

---

## 6 · Five decks, written out

The request was to say what a sample actually teaches, so that feasibility can
be judged rather than assumed. Four were read end to end; the fifth is 17.6 MB
and only its front matter came back.

### 1 · `Live Class Slides: API Design Class` — B / SD3 Backend / Module-3: API Design

Native Slides, 32 KB, owner `shashi@`.

Teaches: the API technology landscape, split external (REST, GraphQL) vs
internal (gRPC, Thrift, RMI, SOAP, CORBA, DCOM), with SOAP/CORBA/DCOM marked
out of fashion. Fielding's six REST constraints, one slide each — client-server,
uniform interface (CRUD URIs, HATEOAS), stateless (JWT rather than sessions),
layered system, cacheability (`expires-at`), code-on-demand. Spec-driven
development: OpenAPI/Swagger, RAML, enabling TDD. A 40-minute interview
structure in four 10-minute blocks — requirements, design, access patterns, then
improvisation — with the line *"you are ready to interview if 40 minutes feels
too short"*. Then a worked eBook-shop case study: functional and non-functional
requirements, resource modelling (pluralised nouns), endpoint design for
categories, a five-option comparison for cart add/remove with option 3a
recommended, and a checkout section whose whole point is that
`POST /shopping-cart/{id}/do-checkout` is wrong because `do-checkout` is a verb.
Closes on bearer-token authorization, three URL/header versioning schemes,
expressing complex queries as JSON, and the limits of HTTP for a chat app
(polling vs websockets vs webhooks).

Eleven slides are placeholders reading `Tilo's page N notes for <section>`.

**Instructor attribution: unusable.** Title slide says `Instructor: TBA`. The
bio slide reads *"Introduction – Julie Wilkins, Senior Product Manager, Amazon
(Corporate Projects, Logistics), MBA – Temple University, BA – Louisiana State
University"* and is immediately followed, on the same slide, by
*"Replace it with Instructor Name/background/related photographs to introduce to
learners."*

### 2 · `Mike: API Design` — same folder

Native Slides, 1.44 MB, owner `shashi@`.

The same skeleton, substantially expanded. Adds industry anchors (Google's
Stubby becoming gRPC in 2015, Meta and Thrift, Netflix using gRPC
backend-to-backend, Facebook originating GraphQL in 2012) and a live job-market
count — *"5 jobs posted in the last 24 hours with gRPC experience preferred; 13
with GraphQL: Apple, GEICO, Experian; 50+ with REST: Apple, Target, BambooHR."*
Two worked selection examples: an analytics endpoint aggregating across systems
→ GraphQL; article comments → REST, with the full four-verb endpoint list spelled
out. Expands the four 10-minute blocks into their own slides, with example
clarifying questions for a logout endpoint, three auth schemes, and a security
note to use non-enumerable GUIDs rather than `GET /accounts/1`.

**Instructor attribution: present and apparently real.** *"Introduction – Mike
Dolt, Software Engineer, Orby, BS – Odesa National Polytechnic University."*

Also carries `operations@interviewkickstart.com` in the class-setup slide —
a contact address in deck body text, in a file whose only PII-shaped field would
otherwise be the owner.

### 3 · `M1: Database Design Class: Backend Curriculum` — B / SD3 / Backend Foundation Slides / M1

Native Slides, 1.18 MB. **The file is named "Database Design Class" and slide 1
says "Fundamentals of Database Systems".** Title and filename disagree, which is
the normal case, not an anomaly.

Teaches: database families with worked detail — relational (schema vs instance,
Oracle/MySQL/SQL Server), NoSQL, cloud (RDS, Azure SQL, Cloud SQL), **columnar**
(with an actual serialisation walk-through showing row-order vs column-order
bytes and how duplicate values compress), graph (Neo4j, ArangoDB, Cosmos),
document (MongoDB, BSON as a JSON superset), and time-series (InfluxDB, Druid,
Graphite). SQL fundamentals: declarative vs imperative, relations and tuples,
SELECT, projection-vs-selection, WHERE, aggregations with GROUP BY, ORDER BY,
JOINs, and materialised vs non-materialised views with the trade-off stated
(faster vs always current). Data organisation: OLAP vs OLTP, ETL, star schema
(fact + dimension tables), snowflake schema with pros and cons, BCNF and 3NF.
Internals: clustered vs non-clustered indexes, hash vs tree index structures,
query-processing stages (parser/algebrizer → optimizer → execution engine),
cardinality statistics and cost estimation. Management: server- and
database-level permissions, roles, `FLUSH PRIVILEGES`, table partitioning,
triggers (DDL/DML/LOGON), ACID, lock-based and optimistic concurrency control,
two-phase locking, deadlocks. Then MongoDB specifically: CRUD methods by name,
aggregation pipelines vs single-purpose methods, per-document write atomicity
and the multi-document transactions API that exists because of it, and
`explain("executionStats")`. Ends with four sample interview questions, two
labs and two demos.

No instructor named anywhere in the deck.

### 4 · `Fundamentals of Agentic AI_Revised_SWEs.pptx` — A / Live Class Content / 2. Fundamentals of Agentic AI

`.pptx`, **17.66 MB**, owner `donthoju.srushith@`.

**Only the front matter was retrievable — the connector truncates at this
size, and I am reporting what came back rather than characterising the rest.**
What came back: a real instructor greeting (*"Welcome to Fundamentals of
Angentic AI - I'll be your instructor: Samwel Emmanuel (Sam)"* — the typo is
in the source); class structure (Sunday 4-hour live class, MCQ and coding
assignment, some classes with pre/post videos); the IK support scaffolding
(UpLevel for resources, Wednesday technical coaching, Discord, TAs in the live
class, support tickets); a "Success Hacks" slide; and a timed segment table.
Embedded speaker notes are included in the extraction and read as instructions to
the instructor (*"While explaining, plz mention that these pre videos are
mandatory…"*).

**The teaching content proper — what Fundamentals of Agentic AI covers — was not
in the retrievable portion.** At 17.66 MB this is the single largest file
encountered, and the type most likely to be a rich deck. **Whatever ingests
this registry must have an answer for files too large to read in one pass, and
right now the biggest deck in folder A is the one we know least about.**

### 5 · `Project & Program Management` — C / Engineering Management / Leadership Workshops Slides

Native Slides, 840 KB, owner `adil.panwar@`.

Teaches EM behavioural interview preparation, not a technical subject. Five
competencies, ten questions. **Project Planning & Execution** — most complex
project managed; on-time-and-budget delivery. **Prioritization & Goal Setting** —
competing priorities; technical debt vs features. **Risk & Change Management** —
risk approach; deciding with limited information; scope creep.
**Delegation & Team Coordination** — effective delegation.
**Accountability & Ownership** — a project that failed; delivering under tight
constraints.

Every question carries the same two slides: five or six *"common variations"* of
how it gets asked, then seven to ten *"key points to cover"*, then a
`Mini Mock & Feedback` slide. The key points name real frameworks — RACI,
OKR/KPI, RICE/WSJF/MoSCoW, critical path and buffers, WIP limits, SPI/CPI,
burn-down and burn-rate, pre-mortems, assumption logs, stage gates with
kill/continue criteria, error budgets, MTTR.

**Instructor attribution: present, detailed, apparently real.** *"Senad Cimic —
Engineering Leader, Engineering Leadership Coach, Senior Engineering Leader at
Amazon. Led multifunctional global organizations across US and IN. Managed orgs
up to 65+ engineers. 350+ interviews as an Amazon Bar Raiser. Previously: Snap
Inc."*

**And one genuinely useful structural signal.** Slide 3 lists the six leadership
workshops: Leadership & People Management, Cross-Functional Collaboration,
Technical Leadership, Roadmap & Strategic Thinking, Project & Program
Management, Culture & Team Building. Those are **exactly** the six sibling
subfolders of `Leadership Workshops Slides`, measured independently. The deck
declares its own taxonomy and the filesystem agrees with it. That is a
corroboration of the kind the corpus graph already knows how to use — two
independent routes to the same fact.

---

## 7 · The fabrication hazard, measured rather than argued

`SCALE-PLAN.md` flagged option 5 — LLM extraction of what a deck teaches — as the
riskiest, citing acceler's 27 fake instructors from comma-split slide bullets.
**The five decks turn that from an analogy into a measurement.**

Four decks, four instructor-attribution shapes, **structurally identical on the
slide**:

| deck | name on the bio slide | what it actually is |
|---|---|---|
| API Design Class | `Julie Wilkins`, Senior Product Manager, Amazon, MBA Temple | **template placeholder**, labelled as such on the same slide |
| Mike: API Design | `Mike Dolt`, Software Engineer, Orby | real instructor |
| Fundamentals of Agentic AI | `Samwel Emmanuel (Sam)` | real instructor |
| Fundamentals of Agentic AI | `Hannah Chen`, Data Scientist, Bay Area, Grammarly ex-Uber | **icebreaker example persona** on the "pop into the chat" slide |
| Project & Program Management | `Senad Cimic`, Senior Engineering Leader, Amazon | real instructor |

`Julie Wilkins` and `Hannah Chen` are `Name, Role, Company` tuples on teaching
decks in the registry. So are `Mike Dolt` and `Senad Cimic`. **An extractor
cannot tell them apart from shape, position, or surrounding text** — the Julie
Wilkins slide is only distinguishable because a human wrote *"Replace it with
Instructor Name"* in the same text box, and the Hannah Chen slide is only
distinguishable if you know that "pop into the chat: Your Name / Role / Company"
is an icebreaker prompt and the filled-in values are the example.

### And then the collision

`Hannah Chen` also appears in the registry's **own P2 workbook**, as a rated
instructor:

```
Live Class, ML Switchup Live Class, ML SwitchUp, Python for Machine Learning,
…, Hannah Chen, Oct 1 2023, 4.52, 41 responses, 58 attended, 70.69%, Webinar
```

**I do not know whether these are the same person.** That is precisely the
point. One occurrence is a structured row with a date, a rating and a response
count — the kind of evidence this graph is built on. The other is decoration on
a slide, carrying an employer (`Grammarly, ex-Uber`) that the structured row
does not assert. A name-matching join takes them as one node and attaches the
slide's employer to the rated instructor. **A person acquires a CV line from a
PowerPoint template.**

There is a second, cheaper version of the same failure in the same workbook:
`TBA` appears as a literal cell value in the `Cohort Strength` column, and
`Instructor: TBA` is the title slide of the API Design deck. Both produce an
instructor named TBA.

> **The registry contains, today, the exact input that produced acceler's 27
> fake instructors — and it contains a real instructor with the same name as one
> of the fakes.** The failure is not hypothetical and it is not avoidable by
> being careful with commas.

---

## 8 · What this does to `SCALE-PLAN.md`'s four questions

### Q1 · What breaks at 2,000 files

Not answered — 2,000 is still unverified. But three things break earlier than
the plan assumed, and all three are structural rather than volumetric:
**shortcuts** have no defined behaviour and appear at a rate of ~1 per 10 files;
**`(File responses)` folders** hold third-party uploads of unknown type; and
**a 17.66 MB deck could not be read in one pass**, which means size limits bite
at the *content* layer long before they bite at the crawl layer.

### Q2 · What ingestion means for a file nobody has read

The inventory sharpens this into a fork the plan did not state. Metadata-only
file nodes (option 1) are **strictly safe here** and would already answer *"which
files mention API design"* poorly but honestly. Full-text search (option 2) is
safe for the decks and **unsafe for the response sheets**, because indexing
`Agentic AI: SWE Capstone (Responses)` puts learner emails in an index.
So option 2 is not one decision — it needs a per-file classification first,
which is option 3 wearing option 2's clothes.

### Q3 · What replaces `sources.py`'s narrow inclusion

**This is now the urgent one, and it is worse than recorded.** §5 found five
contact-data shapes, and only the first — a column in a spreadsheet — is the
shape `sources.py` was ever an allow-list over. Form-response sheets generate
their contact column automatically; a LinkedIn roster has no columns at all;
a consent register carries restrictions that no node property can express; and
**file-owner metadata is collected by the act of citing the file**.

A column allow-list cannot be extended to cover four of those five. The control
has to move, not widen.

### Q4 · Which landing-page honesty claims survive

*"It refuses rather than guesses"* was already the one at risk. §7 shows the
refusal has to happen at a place the plan did not identify: **not at the
topic→module join, but at the person-extraction step inside a document**, where
a real instructor and a template persona are the same shape. If the system
extracts people from decks at all, it guesses, and no ranking discipline
downstream repairs that.

---

## 9 · Recommendation

**`SCALE-PLAN.md`'s fork A — a search index with a graph over a known subset —
survives contact with the data. Fork B is worse than the plan estimated.**

Three things I would put in front of any build decision:

1. **Do not extract people from slide content. At all.** Not ranked, not
   flagged, not `review: true`. §7 is a measured demonstration that the
   distinction an extractor would have to make is not present in the artefact.
   Instructor attribution already has a structured route — the poll workbooks
   name instructors against dated classes with response counts — and that route
   is the one the graph already trusts.

2. **Classify before reading, and make the classifier's failure mode "skip".**
   The registry's contents fall into obviously different privacy classes — a
   module deck, a form-response sheet, a consent register — and the class is
   usually legible from the parent folder and the file's own name. That is
   option 3, and it is the only option that has an answer for the form-response
   folders.

3. **Answer the shortcut and file-owner questions before the first crawl, not
   after.** Both silently change what the corpus *is*: shortcuts change its
   boundary, owner metadata changes what it contains. Both are one-line
   decisions that become expensive to reverse once 2,000 files carry them.

**What I would measure next**, in priority order: the 16 `Live Class Content`
module folders and the 17 under `Uplevel Shared(SWEs + Common modules)`, because
that is where the decks are and the deck count above (8 of 75) is the number
most likely to be wrong; the five 2023-dormant folders in C, to find out whether
a third of that folder is empty; and one `(File responses)` folder, to find out
what learners actually uploaded.

**All three were then measured — §10.**

---

## 10 · The three follow-up measurements

Taken 2026-09-20, immediately after the above. Two confirmed a suspicion; the
third found something larger than expected.

### M1 · The deck ratio is wrong, and wrong in a knowable direction

**Decks sit one to three levels below where the first pass stopped.** The path to
an actual deck in folder A runs:

```
Live Class Content
  └── 3. Build Your First AI Agent - Coding
        └── 1. Sunday Live Class Content
              └── Build_Your_First_AI Agent_ Live Class Slides.pptx   (12.76 MB)
```

and in `1. Python for GenAI` it is one level deeper still —
`Live class slides & Notebooks` → `1. Live Class Slides & Notebook`. The first
pass reached the module folder and stopped, which is exactly why decks looked
rare.

So **8 of 75 was a floor over the wrong stratum**, not a sample of the
population. The module folders are also more consistent than folder A's top
level suggested — each carries some arrangement of live-class slides, an
assignment or a `No Assignment.txt`, drafts, and a `[Do not use]` or
`[DoNotUse]` tombstone. That is a repeating unit, and it is the first one found
in folder A.

**Not re-estimated here.** Counting decks properly means opening the 16 module
folders and the 17 under `Uplevel Shared` to their leaves, which was not done.
What is now known is the *direction* of the error and the reason for it.

### M2 · The dormant folders are empty — all of them

The five folders in C untouched since 2023-02-28:

| folder | children |
|---|---|
| `iOS` | **0** |
| `Fullstack` | **0** |
| `Frontend` | **0** |
| `Switch-up - Machine Learning` | **0** |
| `Backend` | 2 subfolders — `Backend - API Design`, `Backend - Data Modeling` |
| └ both of those | **0** |

**Six folders, zero files.** Nearly 40% of folder C's top level is empty
scaffolding created on one afternoon in February 2023 and never filled.

Worth noting for the join: **`Backend - API Design` is an empty folder whose name
is the spec's own example query.** A content index that ranks on titles and paths
would surface it for *"API design"* and it contains nothing. That is the fork-B
failure in its mildest possible form — not a fabricated fact, just a confident
answer with nothing behind it — and it is already present in the corpus.

### M3 · One form-responses folder is 2.73 GiB, and every filename is a person

`Agentic AI: SWE Capstone - Final Project Submission (File responses)`, four
levels into folder A:

| | |
|---|---|
| Files listed | **60**, and the listing was **not exhausted** — a continuation token remained |
| Total size of those 60 | **2.73 GiB** |
| Largest single file | **535 MiB** (a `.mov` screen recording) |
| Median file | 0.34 MiB |
| Files over 50 MiB | **12** |
| Types | `.zip` source archives and `.mov` recordings, almost exclusively |

**Every filename carries a learner's personal name** — the Drive form appends the
respondent's name to the upload. So the contact-adjacent data is not in a cell,
not in a column, and not in file-owner metadata: **it is in the path**. Anything
that records a file's relative path as provenance records it.

Three further observations:

- **The folder's own name contains an email address**, because the form question
  text became the folder title.
- **There are exact duplicates** — two files of 151,484,833 bytes with the same
  name, and two of 239,825,506 — so a naive crawl pays for them twice.
- **None of it is parseable or curricular.** Zip archives and QuickTime
  recordings teach the graph nothing about a module; they are student work.

> **This single folder is ~49× the entire current corpus on disk** — 2.73 GiB
> against 57.4 MiB for all 74 files, and the listing was not exhausted, so 49×
> is itself a floor. It is one of at least seven form-response folders in folder A
> alone. `CACHE-EXPOSURE.md` §4 costed removing the cache as a rewrite; this
> measurement says the cache question is not mainly about *re-fetching*, it is
> about whether the crawler ever descends into a directory like this at all.

**The pre-crawl decision M3 forces**, and it is not one of the five already
recorded: a crawl needs a rule for `(File responses)` folders specifically. They
are generated by Drive, named predictably, contain third-party uploads, carry
personal names in every path, and hold no curricular content. Skipping them is
the only defensible default — but it must be a **declared** skip that reports
what it skipped, not a size limit that silently drops big files and happens to
catch these.

### One more thing M3 turned up, and it is D4's stated gap arriving early

A folder inside the registry — `Emmanuel's Copy Of Content`, under
`3. Build Your First AI Agent - Coding` — is owned by an address at a **personal
company domain**, not `@interviewkickstart.com` and not a free-mail provider.

`PRE-CRAWL-DECISIONS.md` D4 names exactly this as what the new commit-guard's
contact class does **not** catch: *"a personal address at a CORPORATE domain,
indistinguishable by shape from an institutional one."* It took one folder of
real measurement to produce an instance. The decision stands — store the owner's
domain, never the address — and this is the evidence that the backstop is a
backstop and not the control.

---

## Appendix · The 37 folders opened

A (17): root, `Live Class Content`, `Finalized Content 2.0`, `Hiring`,
`SMEs consent`, `Ratings & Feedback`, `Forms & Submissions`,
`Agentic 2.0 Transcripts`, `Agentic IP`, `Agentic AI 2.0`, `Drafts`,
`Uplevel Shared(SWEs + Common modules)`,
`Detailed Curriculum & Overview Docs. _Agentic AI`,
`Uplevel Shared(Tech Prof.)`, `Final_test` *(empty)*,
`…/2. Fundamentals of Agentic AI`, `…/Live Class Slides & Notebooks`,
`…/Project Submissions - US`, `…/Project Submissions - US/SWEs`.

B (11): root, `SD3: Backend Engineering`, `Sys3: Embedded Software Engineering`,
`Sys4: SRE`, `Hiring Resources - Systems & Test`, `SD3/Module-3: API Design`,
`SD3/Backend Foundation Slides`, `SD3/Backend Foundation Slides/M1`,
`SD3/Module-3/2. Live Class Slides`.

C (9): root, `TPM`, `Machine Learning`, `Engineering Management`,
`Data Engineering`, `ML/1-supervised-learning-i`,
`ML/1-supervised-learning-i/Live Class & Assignment`,
`EM/Leadership Workshops Slides`,
`EM/Leadership Workshops Slides/Project & Program Management`.

**150+ discovered folders remain unopened. Every count in this document is a
floor over the fifth that was measured.**
