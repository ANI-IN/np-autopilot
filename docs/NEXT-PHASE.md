# NEXT PHASE — the whole New Programs job, as reusable plugins

**A PLAN. Nothing here is built.** Asked for by the owner on 2026-09-30
(origin: hand, Animesh Kumar): *the graph must cover everything the New
Programs team does, and the main product is a set of REUSABLE PLUGINS.*
Scope to add: **Workflows & SOPs · Program operations · Team & ownership ·
Metrics & feedback (always with N)**. First plugins, one per job: **Staff a
class · Prep a module · Run a workflow · Program/ops answers.**

Order of work agreed first: **launch the curriculum release now, expand the
scope next.** Nothing below touches the release in flight (B4, the paused
window).

The inventory in §1 was taken read-only on 2026-09-30 from `.drive-cache/`
(pass 0's mirror, fetched 2026-09-16: 74 files, 337 worksheets + the excluded
payroll file's 37 = 374), the live Resource Collection Mastersheet export
(version 2736, 14 tabs) and the row-B crawl. Every "not found" names what was
opened (CLAUDE.md §6). No value from a contact, learner or pay column is
reproduced here — only headers, counts and shapes.

---

## Owner direction, 2026-09-30 (origin: hand, Animesh Kumar) — after the launch

Stated in the handoff request after the window; **direction for the plan, not
answers to §4.4**, which stay open. Where it goes beyond §1–§4 below, it wins.

- **Team & ownership**: internal **`team_member`** nodes, sourced from a
  **Keka export or a maintained sheet** (neither is in the corpus today);
  **`reports_to`** between team members; **`owns` with a role** (what a person
  owns, and in what capacity). The UI gains a **Team tab** and a **"who owns
  what" matrix**, the ownership counterpart of Who teaches what.
- **All pods, with `pod` as the top level** of the graph. Order: **System Pod
  next**, then **Agentic AI**, then **Data & Management**. (Today's release
  covers row B only: SD1–SD4.)
- **Workflows & SOPs, programme operations, metrics & feedback (always with
  N)** — as §1.A, §1.B, §1.D.
- **The MCP query layer plus four job plugins**: Staff a class · Prep a
  module · Run a workflow · Program/ops answers — as §3.
- **Distribution via a GitHub org and a separate, clean plugins repo** — as
  §3.4.
- **Improvement by observation** (the team reports issues and ideas; weekly
  triage; small releases through preview → promote; a changelog on the site):
  `docs/HANDOFF.md` §F.

## 0 · Where we start

| | today |
|---|---|
| Graph | 8,496 public nodes / 12,189 edges projected (new build, local; production still on the old 3,146) |
| Scope areas already present | workflows (92) + themes (16) as inert lookup records; domain ownership (`owned_by` 55, `supported_by` 58, `delivered_by` 43); people (a floor, CLAUDE.md §2); `teaches` 2,239 with `class_dates` from the schedule; decline rates as instructor properties |
| Query surfaces | the web API (`api/index.py` → `web/lib/data.py`, Google Workspace sign-in → Supabase JWT → RLS roles `member`/`recruiting`/`admin`) and a Claude Code plugin (`.claude-plugin/plugin.json` v0.1.9: 5 commands reading `knowledge/graph.json` from the repo; `skills/` empty; **no MCP server**) |
| Distribution | `ANI-IN/np-autopilot`, **private, one collaborator**. Nobody else can install anything. Its history carries the hiring funnel (DECISIONS §F.2), so a collaborator today is a recruiting-tier grant |

---

## 1 · Source inventory

Legend — **Read today**: what `pipeline/lib/sources.py` declares now.
**Readable**: *now* (cached, service account can fetch) · *share* (needs a
Viewer grant to the service account) · *missing* (not found anywhere the
account can see). **Privacy**: *none* · *staff* (staff/instructor names) ·
*contact* (addresses, phones, LinkedIn, invite/Zoom links) · *learner* (any
student-level row) · *ratings* (performance data about a named person) ·
*HR* (objectives, pay, gender, address). **Control** is the column-level
declaration proposed; CLAUDE.md §2 applies to every row — declare columns,
never sheets, never a contact column, and every new file gets a per-tab scope
yaml (as `config/mastersheet-scope.yaml`) where an undeclared tab fails the build.

### 1.A Workflows & SOPs

| source (path : tab) | holds | read today | readable | privacy | control |
|---|---|---|---|---|---|
| `00-master/Team_Task___Workflow_Inventory` (Markdown) | 16 themes, 92 workflows: task, → steps, effort, alerts. **No owner, status or priority field** | yes → `theme`, `workflow` | now | none | as today |
| `config/workflow-owners.yaml` (hand) | 92 rows, **0 confirmed** | read, emits 0 `workflow_owned_by` | — | staff | owner fills it (§5) |
| `01-workflows/SMEs_ Instructors Hiring Process at IK.docx` | hiring SOP; a "Teams / POC summary" table | no | now | contact (2 addresses) | new `sop` node → workflows 2.x; strip addresses; POC table → §1.C by name/role only |
| `01-workflows/Demo Calls for Hiring Instructors_SMEs.docx` | demo-call SOP | no | now | none | `sop` node |
| `03-instructors/IK_ US Instructor - Expectation Setting for Taking Classes.docx` | weekly class cadence (live class, TCS…) | no | now | none | `sop` node; also §1.B delivery format |
| `03-instructors/Instructor_Onboarding_Steps_Template` | onboarding steps, pod structure | no | now | contact (1) | `sop` node, strip the address |
| `01-workflows/Instructor_Demo_Evaluation_Guide_Template` | interview script | no | now | staff/candidate first names | `sop` node; **no people extracted from it** (D1 rule) |
| `01-workflows/Instructor_Best_Practice___Zoom___Initial_Check_Template` | a Slack template | no | now | an instructor handle | `sop` node; the handle stays text |
| `01-workflows/Feedback_After_the_class_Template` | 8-section class-feedback rubric | no | now | none | `sop` node; it is the rubric behind §1.D |
| `01-workflows/DTC_session_Context__Domain_Techincal_coaching_session_` | DTC format (typo load-bearing) | no | now | none | `sop` node |
| `01-workflows/RCA Template.xlsx : Internal Evaluation` | class RCA template | no | now | none | `sop` node for workflow 15.1 |
| `01-workflows/UpLevel Schedule Structure.xlsx : Domain Resource Collections` | how to build a schedule | no (other tabs are) | now | none | `sop` text |
| `01-workflows/Taking Class Confirmation Template.png` | image | no | **needs OCR** | unknown | defer |
| **"NP Autopilot – The AI Operating System for New Programs"** (Automations / All Tasks / To-Do & Working Notes) | the brief's "single most important file" (`02-content-analysis.md:11`) | — | **missing** | — | §5 item 1 |

### 1.B Program operations (cohorts, schedules, delivery log, status)

| source | holds | read today | readable | privacy | control |
|---|---|---|---|---|---|
| `05-operations/New Combined Schedule.xlsx : Combined Schedule Mastersheet` | 5,604 rows, 4,462 dated **2025-11-02 → 2027-07-21** (includes planned classes): Date, Class Type, Course Order, Class Topic, Start/End, Instructor Name, Confirmation Status, reminder/email tracking | Instructor/Topic/Date only | now | staff | **the delivery log.** Declare Date, Class Type, Course Order, Class Topic, Start/End, Instructor Name, Confirmation Status. A future date is a *planned* row: flagged, never filtered (§4 of CLAUDE.md) |
| same : 44 per-domain tabs (+ `… DTC` twins) | same schema, 13–985 rows each; `Agentic AI PMTPM` adds Cohort | 3 columns | now | staff | as above. **Extractor gap found:** `Agentic AI - SWE` heads its date column `Dat`, so `SCHEDULE_DATE_COL="Date"` has been missing its dates; `Machine Learning DTC` / `MLSwitchUp DTC` have a blank date header |
| same : `Class Confirmation Record` | 1,689 (1,529 confirmed / 160 declined) | yes → instructor properties | now | ratings-adjacent (availability) | as today, recruiting tier |
| same : `Last Class Date` | 44 domains, last scheduled class | no | now | none | `programme.last_class_date` → status |
| same : `US Holiday` | 11 no-class dates | no | now | none | calendar facts |
| same : `Sunday Monitors` | 45: Topic, Monitor, Cohorts, **Zoom links** | no | now | staff + contact | declare Monitor, Topic, Cohorts; **never the Zoom columns** |
| same : `Dashboard` | derived KPIs | no | now | none | recompute, don't ingest |
| same : `Sheet (2)`, `Copy of Sheet (2)` | Students, Student HubSpot IDs, profile URLs | no | now | **learner** | **exclude by name** |
| same : `Instructor Data` | Name, Email (262), Phone (119) | Name | now | contact | as today |
| same : 9 empty template tabs | 0 rows | — | — | — | reported as empty, not "no data" |
| `01-workflows/UpLevel Schedule Structure.xlsx`, 26 per-domain template tabs | the cohort **template**: Activity/Resource Type, Topic, When, Start/End, Where, Active | `Topic (For)` only | now | none | declare When, Activity Type, Resource Type → a template-week schedule (a *plan*, never delivery evidence) |
| same : `Resource Collections for FT Mas`, `…for Fast T` | Instructor, Video, Slides, **Assignee Delivery**, Status | partly | now | staff | production status; Assignee → §1.C |
| `00-master/Domains_Courses Owners.xlsx : Sheet1` | cadence, stage per domain | yes | now | staff | as today |
| `03-instructors/AgenticAI Instructors Training Plan.xlsx : SME Roster`, `SME Roster - IND`, `Training_tracker`, `WIP_Training_Status` | weekly SME roster grid; training status | SME / Instructor columns | now | staff (Comments are judgements) | roster → staffing-by-week; training status → ops status; Comments stay out |
| live mastersheet `Training Sheet` | 21: Name, **Email (4)**, Course, POD, Training Topic/Date/Status, Average Rating (2 values) | **no** (excluded in the scope yaml) | now | contact + ratings | needs an owner amendment of `mastersheet-scope.yaml`: Name, Course, POD, Topic, Date, Status only; never Email; the 2 ratings recruiting tier with N |
| live mastersheet `Interview Repo` | 29 rows, Backend/Cloud "Week N – module" → 30 question-bank links | **no** (HANDOFF §D.8 "later release") | now | probably none — **check link targets first** | declare module + link columns after the check |
| `05-operations/Operational Metrics.xlsx` (102 tabs) | 2018–2021 cohort ops | no (excluded) | now | **learner** (73 tabs email-shaped, many headerless; 46 LinkedIn) | out of scope for B (pre-NP). See §1.D for the one usable tab |

### 1.C Team & ownership

| source | holds | read today | readable | privacy | control |
|---|---|---|---|---|---|
| `00-master/Domains_Courses Owners.xlsx : Sheet1` | domain → Delivery member, Primary / Secondary NP owners | yes → `owned_by`/`supported_by`/`delivered_by` | now | staff | as today |
| same : `For Slack` | staff × 8 product channels, "Created" row | people only, **no edge** | now | staff | `member_of` (person → product/domain) **after the owner confirms it means ownership, not just channel membership** |
| `config/people.yaml` (hand) | 20 curated people, `team` np/delivery/other/former | yes | — | staff | as today; the identity key |
| `config/workflow-owners.yaml` (hand) | 92 workflow rows, 0 confirmed | read, 0 edges | — | staff | **the owner fills it** — the only process-ownership source that exists |
| NCS `Delivery POC` | 7: Name, **Email ID**, Course Order Assigned | no | now | contact | `delivery_poc_for` (person → programme), Name + Course Order only |
| UpLevel RC tabs `Assignee Delivery` | 242 filled | no | now | staff | `assigned_to` (resource collection → person) |
| `Sunday Monitors` `Monitor`, P2 `TA Missed` `Monitor` | class monitors | no | now | staff | `monitors` role edge |
| `00-master/IAims Setting Audit _ New Programs.xlsx` (17 tabs, ~1,500 rows Q3 2024 → Q2 2026) | per person: I-Aim Title, rubric, metric, target, weightage, **Achievement, Rating** | Employee Name only (person nodes; blank ENo retained) | now | **HR** | the richest "who is accountable for what". Proposed `objective` node (I-Aim Title, quarter) → `responsible_for`, **admin role only**; **never** Achievement or Rating; Weightage only if the owner says so |
| `03-instructors/SME database (For Ops + NP).xlsx : Master` | 542: Designation, Program, **Reporting Manager, Functional Leader**, Department … and personal email, phone, **gender, address, pay** | Full Name, Program | now | **HR + contact** | an org chart: Reporting Manager, Functional Leader, Department **only with owner approval**; never pay, gender, address, contact |
| `03-instructors/SME Tracker - Bullseye_IK.xlsx : Tracker - All roles` | 2,255 candidates; **Onboarding PM**, **Interviewer** | Name (funnel) | now | contact + recruiting | Onboarding PM / Interviewer as staff-role edges, recruiting tier |
| `03-instructors/SME_Interview_Demo Audit Rubrics.xlsx` (5 tabs) | **Interviewer Name** per candidate | SME Name | now | recruiting | interviewer → staff role, recruiting tier |
| **task / automation / process ownership** | — | — | **missing** | — | **§5 item 1.** Nothing in the corpus says who owns a task or an automation |

### 1.D Metrics & feedback (always with N)

| source | holds | read today | readable | privacy | control |
|---|---|---|---|---|---|
| **P1** `06-analysis/Domain Classes Poll Feedback 2026.xlsx : Live Class Poll` (corpus copy, 2026-09-02) | 1,070 sessions 2026-01-02 → 08-30: Domain, Class, Cohorts, Instructor, Date, **Overall Average, Responses (N), # Students Attended** | **no** (`PERSON_EXCLUSIONS`; D2a deferred P1/P2) | copy now | ratings | aggregate to instructor × module (via an `Ambiguous` class→module join) and domain × quarter; **Responses travels with every average**; recruiting tier |
| **P2** `06-analysis/MLSU_Gen AI_Agentic AI Classes Poll Feedback 2026.xlsx : Data` (+ `Agentic_AI_…`, `MLSU_…` polls) | 2,789 combined rows: Date, Instructor, Topic, Rating, Response, Attendance | no | copy now | ratings | as P1; `Data` is the cleanest single table |
| P2 : **`T.A Ratings`**, **`TA RAW`** | Student Name (1,018 / 560), Student Email (457) | no | now | **learner + contact** | **exclude by name**; TA ratings only via a pre-pass that aggregates TA × week with N and never declares a student column |
| P2 : `Instructor Insight`, `Topic Fit`, per-person tabs | **Risk Label, Fit Label**, z-scores | no | now | ratings (judgements) | **never ingest the labels**; recompute averages with N from the raw rows |
| **live** P1 / P2 (native Sheets, modified 2026-09-28 / 09-30 — newer than the copies) | as above | — | **share** | ratings | Viewer to the service account, fetched like the live mastersheet into `~/.config/np-autopilot/`, with a scope yaml that names the excluded tabs |
| `05-operations/Operational Metrics.xlsx : Domain Classes Feedback Tracker` | 491 rows, **2021**: per session Number of Ratings, Rating, Attendees, Instructor (foundation / live / coaching / review) | no | now | ratings, **no learner columns** | historical ratings that already carry N; labelled 2021 |
| same : `Coaching Metrics*` | slots, bookings, utilisation, no-shows per coach | no | now | ratings-adjacent | aggregates only |
| same : `Cohort Type Wise Coaching Raw D` | 12,985 rows, **learner, learner_email** | no | now | **learner + contact** | exclude (or a pre-pass counting coach × cohort_type that never declares learner columns) |
| `03-instructors/AgenticAI Instructors Training Plan.xlsx : Preferred SMEs for Each Topic` | module, SME, avg rating, **classes** | yes → `teaches.avg_rating`/`classes` (sensitive) | now | ratings | as today — it already carries N |
| `06-analysis/Example RCA .xlsx` | an example RCA | no | now | none | example only |
| IAims `Achievement` / `Rating` | HR ratings | no | now | **HR** | **never** |

**Attendance** stays out until "0 attended" can be told from "not recorded"
(STATE §10) — the poll columns do not distinguish them.

### 1.E Privacy hot spots (worst first)

1. `03-instructors/Instructors Directory.xlsx : Responses` — PAN-card uploads, bank details, cancelled cheques (219 each), phones, emails. Read today: Full Name, Domain only. **Must stay that way.**
2. `SME database : Master` — gender, address, pay rates, personal contact.
3. `Operational Metrics.xlsx` — 12,985 `learner_email` rows and 73 tabs with **headerless** email columns (a header deny-list does not catch them; the >30 %-email-shaped rule does).
4. P2 `T.A Ratings` / `TA RAW` — student names and emails.
5. NCS `Sheet (2)` — student HubSpot ids and profile URLs.
6. SME Tracker — 2,195 emails, 2,237 LinkedIn, hiring judgements; two tabs whose *header rows* are a candidate's data.
7. IAims — objectives, achievement and rating of named NP staff.
8. Access links: Discord invite links (23), Zoom links (Sunday Monitors), live-mastersheet `Indian Instructors` (Discord channel links).
9. **Open owner decision already on file:** `sources.py` still reads the corpus copy's `Indian Instructors` / `Instructor(FullStack)` tabs that the live-sheet scope excludes (HANDOFF §D.7).

**The control does not change, it widens.** Today the narrowness of
extraction is what keeps contact data out (CLAUDE.md §2), and every row above
is a chance to declare the wrong column. Every new source lands with (a) its
column declarations, (b) a per-tab scope yaml naming excluded tabs, (c) the
existing deny-by-default test extended to it, and (d) `validate.py`'s
`excluded-column` still at zero.

---

## 2 · Model

New types follow DECISIONS §A.6: one row in the type lookup each, no DDL. All
keyed on names/curated slugs, never employee ids (CLAUDE.md §2a).

### 2.1 New node types

| type | area | key | properties (public unless marked) | from |
|---|---|---|---|---|
| `sop` | A | file | kind (hiring, demo, onboarding, class, feedback, RCA, DTC), drive_url, sections | the 10 SOP files |
| `class_delivery` *(edge time series, not a node — see 2.2)* | B | — | — | — |
| `cohort` | B | (programme, cohort label) | start, region (US/India), status | NCS `Cohort`, UpLevel templates, `Cohorts` columns |
| `schedule_template` | B | (domain, template tab) | weeks, activity counts | UpLevel Schedule Structure |
| `holiday` | B | date | label | NCS `US Holiday` |
| `objective` | C | (person, quarter, title) | title, metric type, target direction — **admin only** | IAims |
| `automation`, `task` | C | — | — | **blocked: source missing (§5)** |

### 2.2 New edges (and how they join what exists)

| edge | from → to | area | evidence / properties |
|---|---|---|---|
| `documents` | sop → workflow | A | hand-confirmed mapping (an SOP names no workflow id) |
| `workflow_owned_by` | workflow → person | A/C | **exists, 0 edges**; filled from `workflow-owners.yaml` |
| `delivered_on` *(edge time series)* | instructor → module | B | one edge per class: date, class type, course order, confirmation status, planned/held. **Per-module needs an `Ambiguous` topic→module join** (sessions carry topic strings) — unresolved rows reported, never guessed |
| `runs` | cohort → programme | B | |
| `follows` | cohort → schedule_template | B | |
| `delivery_poc_for` | person → programme | C | NCS Delivery POC |
| `monitors` | person → cohort / domain | C | Sunday Monitors, TA Missed |
| `assigned_to` | module (resource collection) → person | C | UpLevel `Assignee Delivery` |
| `member_of` | person → domain | C | For Slack — **only if the owner confirms the meaning** |
| `responsible_for` | person → objective | C | IAims, admin only |
| `reports_to` | person → person | C | SME database — **only with owner approval** |
| `rated` *(edge time series)* | instructor → module / domain | D | per (instructor, module-or-domain, quarter): average, **responses (N)**, sessions, source; recruiting tier. **Never without N; never a band across quarters** (STATE §10) |

Everything joins what exists: instructors and people (curated identities),
modules (row-B `(domain, sequence)` or legacy label), domains (with the
legacy/current distinction the UI now shows), programmes. A delivery or rating
row that cannot be joined is **reported and retained**, never dropped (§4).

### 2.3 What the UI gains — the left-side categories

Today's flat type list becomes five groups (each a chip group in the header
and a section in the legend):

| group | types |
|---|---|
| **Curriculum** | domain, programme, module, programme week, session, assignment, review, deck, topic, curriculum doc, code repo |
| **Delivery** | instructor, class deliveries (time series), cohort, schedule template, holiday |
| **Operations** | workflow, theme, SOP |
| **Team** | person, ownership edges (domain, workflow, programme POC, monitor), objective (admin) |
| **Metrics** | ratings with N (recruiting), confirmations/declines (availability, recruiting) |

A member sees Curriculum, Delivery, Operations and Team (minus objectives);
Metrics appears only for `recruiting`/`admin` — the same RLS that already
hides sensitive rows.

---

## 3 · Plugin architecture for reuse

### 3.1 One read-only query layer — an authenticated MCP server

```
 Claude Code plugins ─┐                      ┌─ /api/* (REST, the website)
                      ├─► /api/mcp  ─┐       │
 claude.ai / Desktop ─┘   (MCP, HTTP) ├─► web/lib/queries.py ─► Postgres (RLS)
                                     │   one function per question
                    guard.identify ──┘   same guard, same audit, same role
```

- **One implementation of every question** (`web/lib/queries.py`, grown out of
  today's `web/lib/data.py`). The REST routes the website calls and the MCP
  tools are two thin adapters over the same functions — so the website and
  every plugin give the same answer, with the same citations, under the same
  RLS. No plugin ever reads a file of graph data again.
- **Read-only by construction**: the MCP endpoint connects through the
  existing request connection (`authenticated` role, RLS on), plus the
  read-only guard proven on 2026-09-30 (`NP_DB_READ_ONLY`, SET after connect).
  Curation writes stay on the website, audited, admin-only.
- **Hosted where the API already is** (Vercel function `/api/mcp`, Streamable
  HTTP transport). No new infrastructure.
- **Authentication**: the MCP authorization flow (OAuth 2.1) with our own
  sign-in as the authorization server — Google Workspace, `hd =
  interviewkickstart.com`, then the Supabase session the website already
  mints. Claude Code / Desktop handle the browser step; no token is pasted by
  hand. (Fallback if that slips: a short-lived personal token issued after a
  website sign-in — simpler, weaker; **your decision, §4.4**.)
- **Every tool returns citations**: file, tab, row, Drive link — or
  `origin: hand` with who and when. A tool never returns a number without its
  N, and never states "not in the corpus" without naming what it read.

**Tools (v1)** — each maps to a question the team asks:

| tool | answers |
|---|---|
| `search(q, types?)` | find anything by name, current before legacy |
| `module_brief(module)` | sessions, links, folders, current decks (historical flagged), topics, assignments |
| `staffing(module \| domain, role?)` | who teaches it, role, tier (mastersheet / older sheets), gaps |
| `instructor(name)` | roles, modules, availability (recruiting), corroboration |
| `schedule(domain?, from, to, instructor?)` | planned and held classes (after §1.B) |
| `workflow(name)` | steps, tools, effort, alerts, SOP, owner |
| `owner_of(domain \| workflow \| programme)` | ownership with source |
| `metrics(instructor \| module \| domain, period)` | average **with N** (recruiting only) |
| `coverage()` | what the graph has read and what it has not |

### 3.2 Small plugins, one per job

Each plugin is a folder of commands and skills, **no data, no scripts that
read files** — it calls the MCP tools. Shared conventions (citation format,
"say N", "say what was not read") live in one `np-core` skill every plugin
depends on.

| plugin | commands | skill (what it knows) | inputs | outputs | example questions |
|---|---|---|---|---|---|
| **np-staff-a-class** | `/staff <module> [date]`, `/cover <instructor> <date>` | staffing rules: primary → backups in order; availability is not quality; never recommend from ratings without N | module or class; date | ranked candidates with role, tier, availability, citation; the gap if none | "Who can teach API Design on 12 Oct if Robert is out?" · "Which SD4 modules have no backup 2?" |
| **np-prep-a-module** | `/prep <module>`, `/links <module>` | the row-B chain (pre-class → class → assignment → review → practice), historical vs current files | module | a prep sheet: sessions with Uplevel + Drive folder links, current decks, topics with slide numbers, assignments, who teaches it | "Everything I need for Cloud Native Design this week" · "Which decks are current for API Testing?" |
| **np-run-a-workflow** | `/workflow <name>`, `/sop <topic>` | the 92 workflows, their SOPs, tools and owners | workflow name or task | steps, SOP link, tools, effort, alerts, owner (or "no owner recorded") | "How do we onboard a new SME?" · "What's the RCA process after a bad class?" |
| **np-program-ops** | `/ops <domain>`, `/schedule <domain> <week>`, `/owner <thing>` | programme status, cohorts, schedule templates, ownership | domain, week, cohort | status, next classes, owner, last class date, holidays | "When is SD1's last class?" · "Who owns Agentic AI - EM?" · "What runs in SD3 week 11?" |

**"Run a workflow" is guidance, not management.** DECISIONS §G closed
workflow *management* (status, assignee, run history) as out of scope: it is a
write-side application with its own source of truth. The plugin tells you how
to run a workflow and who owns it; tracking runs would be reopening §G — a
decision, §4.4.

### 3.3 Versioning

- **Plugins**: semver each, in one marketplace (`.claude-plugin/marketplace.json`
  listing all four plus `np-core`). A breaking change to a command's inputs is
  a major. `CHANGELOG.md` per plugin.
- **The MCP API**: tools versioned by schema (`schema_version` in every
  response); additive changes only within a major; a removed or renamed field
  is `/api/mcp/v2`, with v1 kept for one release. Each plugin declares the
  minimum API version it needs; `np-core` checks it at start and says so
  plainly if the server is older.
- **The graph**: every response carries the projection's `content_hash` and
  `projected_at`, so an answer can be tied to the data it came from.

### 3.4 Distribution — why nobody can install today, and the fix

Today: `ANI-IN/np-autopilot` is private with one collaborator, and its history
contains the hiring funnel (DECISIONS §F.2) — so **adding anyone to that repo
grants recruiting-tier data**, whatever the plugin does. The current plugin
also *ships the graph* in the repo (`knowledge/graph.json`), which D11 already
warned about: a removed user keeps the snapshot.

**Proposed (D10, done properly):**

1. **A GitHub Organization** (e.g. `interviewkickstart-np`) with a team
   `np-plugins-readers`. Access is managed on the team, not per person.
2. **A NEW repository `np-autopilot-plugins`** in the org, private, **with no
   history from this one**: only the plugin folders, `marketplace.json` and
   docs. No data, no pipeline, no corpus. The team gets read access.
3. **Data never travels with a plugin.** It comes from `/api/mcp` under the
   user's own sign-in, and RLS decides what they see. Removing someone from
   the Workspace or the team cuts them off at the next request — which D11
   could not promise for a cached graph.
4. This repository stays private to you (and the §F.2 history rewrite stays a
   separate decision, no longer blocking distribution).
5. **Honest install cost** in the README (D10): a GitHub account in the org →
   `gh auth login` → `/plugin marketplace add interviewkickstart-np/np-autopilot-plugins`
   → `/plugin install np-staff-a-class@…` → the first MCP call opens a browser
   for Google sign-in. Four steps and a sign-in, not "two commands".

**What that needs from you**: create the org (or say which existing IK org to
use) and make me an owner of it; say who is in the first team; confirm the new
repo name. A free org plan is enough for private repos with a team.

---

## 4 · Phasing

Effort is in focused working days for one engineer with this assistant, from
the start of each phase; ranges, not promises. Each phase ends with an
**owner acceptance** like the module checklist: a generated checklist of every
fact in the area, each with its source, ticked by the owner — plus eval
questions that must answer correctly with citations before the plugin ships.

| phase | ships | accuracy check | effort |
|---|---|---|---|
| **0 · Foundation** (after the launch) | `web/lib/queries.py`; `/api/mcp` with OAuth sign-in, read-only guard, audit; `np-core`; the org + plugins repo; `coverage()` | the website and MCP return identical answers for the existing eval questions (a diff test); a member cannot see a recruiting field through MCP (canary, like the RLS ones) | 5–8 |
| **1 · Prep a module + Staff a class** (curriculum data already accepted) | `np-prep-a-module`, `np-staff-a-class` over today's graph | the accepted module checklist *is* the check; 10 staffing eval questions (incl. the EM single-instructor case) answered correctly | 3–5 |
| **2 · Program ops (read side)** | delivery log from NCS (planned vs held), cohorts, schedule templates, last class date, holidays; `schedule()`, `/ops`, `/schedule`; the `Dat` header fix | delivery checklist per domain: class counts by month vs the NCS Dashboard; every unjoined topic→module row listed; planned rows never counted as held | 6–10 |
| **3 · Workflows & SOPs + ownership** | SOP nodes, `documents` mapping, workflow owners, delivery POCs, monitors, assignees; `np-run-a-workflow`, `/owner` | owner ticks the workflow-owner file (92 rows) and the SOP→workflow map; every ownership edge shows its source | 4–6 (+ owner time for the 92 rows) |
| **3b · Tasks & automations** | `task`, `automation`, owners, status | **blocked on the missing "NP Autopilot" sheet (§5)**; if tracking is wanted, that is §G reopened — scope it then | — |
| **4 · Metrics with N** | `rated` time series from live P1/P2 (+ 2021 tracker as historical); `metrics()` for recruiting/admin; TA ratings only via the aggregating pre-pass | every average shows N; a spot-check of 20 averages against the source sheet; a test that no learner column is declared (extending the deny-by-default test to the new files); attendance stays out | 5–8 |
| **5 · Objectives (optional)** | IAims titles → `objective`, admin only | owner decides whether at all; a test that Achievement/Rating are never read | 2–3 |

**Order rationale.** Phase 0 is what makes anything installable; Phase 1
reuses data you have already accepted, so the first plugins are right on day
one; operations before metrics, because the delivery log is the join key the
ratings need (session → module), and metrics carry the most privacy risk.

### 4.4 Decisions only you can make

1. **Distribution** (§3.4): approve the org + a separate history-free plugins repo; name the org, the first team members, and who else is an org owner.
2. **MCP sign-in**: OAuth through our Google sign-in (recommended) or personal tokens.
3. **Who sees what**: is `member` (every IK Workspace user, auto-granted) the right audience for delivery logs and ownership, or should plugin access be a narrower role?
4. **Metrics audience and form**: recruiting/admin only (recommended), per instructor × module × quarter with N; confirm TA ratings are wanted at all.
5. **IAims objectives**: in (admin only, titles only) or out.
6. **Org chart** from the SME database (Reporting Manager, Functional Leader): in or out.
7. **`For Slack`**: does membership mean ownership?
8. **Workflow management** (§G): stays closed (guidance only), or reopened as its own project.
9. **Mastersheet `Training Sheet` / `Interview Repo`**: amend the live-sheet scope to read the declared columns.
10. **HANDOFF §D.7**: the corpus-copy `Indian Instructors` tabs still read by `sources.py`.

---

## 5 · What I need from you

**Files to share (Viewer to the service account, or a link):**

1. **The "NP Autopilot – The AI Operating System for New Programs" spreadsheet** (Automations / All Tasks / To-Do & Working Notes). Not found in the corpus folder, not in any of the 17 cached workbooks' 337 sheet names or the live mastersheet's 14 tabs, and a Drive title search under the B2C account returned no spreadsheet — which says what that account can see, not all of Drive. It is the only possible source for tasks, automations and their owners (Phase 3b).
2. **Live P1 and P2 poll sheets** (`Domain Classes Poll Feedback 2026`, `MLSU_Gen AI_Agentic AI Classes Poll Feedback 2026`) — newer than the corpus copies (Phase 4).
3. **The live New Combined Schedule**, if the corpus copy (2026-09-16) is not the one ops works in (Phase 2).
4. Optional: `Taking Class Confirmation Template.png` as text, if it matters.

**Access:** the GitHub org (create it or name it, make me an owner), the
first team's members; a Google Cloud OAuth client for the MCP sign-in in
project `np-autopilot` (same consent screen, Internal).

**Your time:** the 92-row `workflow-owners.yaml` (Phase 3) and the SOP →
workflow map; the per-phase acceptance checklists.

**Decisions:** §4.4, items 1–4 before Phase 0 starts; the rest before their phase.
