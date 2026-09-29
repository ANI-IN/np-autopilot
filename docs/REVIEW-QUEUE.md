# REVIEW QUEUE — 86 decisions, answer by ID

**Generated 2026-09-29 from the four review YAMLs. Nothing here is applied.**
Every row is `confirmed: false` in its source file; this document is the same
rows in one place, with a recommendation and an ID to answer by.

**A recommendation is not a decision.** Where it says *needs owner knowledge*,
the evidence genuinely does not settle it and a guess would be the
picking-with-no-signal failure `lib/resolve.py` exists to refuse.

| group | rows | source |
|---|---:|---|
| `MOD` | 16 | `config/module-aliases-review.yaml` |
| `TOPv` | 3 | `config/content-topic-review.yaml` |
| `TOPm` | 3 | `config/content-topic-review.yaml` |
| `TOPt` | 6 | `config/content-topic-review.yaml` |
| `PPL` | 12 | `config/mastersheet-people-review.yaml` |
| `DCK` | 14 | `config/deck-instructor-review.yaml` |
| `INS` | 32 | derived: both graphs (see below) |
| **total** | **86** | |


## MOD — row-B module labels that collide with an existing module node

A collision is not a match. Row-B modules are keyed on (domain, sequence); the existing 922 are keyed on their label. **Recommendation: needs owner knowledge** for every row — only someone who knows both curricula can say whether they are the same module.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `MOD-01` | full-stack 1 | `Databases` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-02` | full-stack 2 | `API Design and Implementation` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-03` | full-stack 5 | `UI System Design` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-04` | frontend 2 | `UI & DOM` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-05` | frontend 3 | `Frontend System Design` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-06` | frontend 4 | `Leveling Up with Advanced JavaScript and CSS` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-07` | backend 1 | `Database Design` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-08` | backend 2 | `Object Modeling` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-09` | backend 3 | `API Design` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-10` | backend 4 | `Cloud Native Design` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-11` | backend 5 | `Concurrency` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-12` | testing 1 | `Quality Engineering Foundations` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-13` | testing 3 | `API Testing` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-14` | testing 4 | `Automation Testing` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-15` | testing 5 | `Test Automation Design Patterns` | collides with an existing label-keyed module | needs owner knowledge |
| `MOD-16` | testing 6 | `Cloud Testing` | collides with an existing label-keyed module | needs owner knowledge |

## TOPv — module label variants across folder shapes

The module's identity is (domain, sequence), so a variant is a DISPLAY choice. **Recommendation: confirm the mastersheet's label** — it is the maintained roster, the folders are where files happen to sit.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `TOPv-01` | full-stack 3 | `Cloud`, `Cloud Infrastructure` | folder naming differs | confirm the mastersheet label |
| `TOPv-02` | full-stack 4 | `JavaScript and Web Dev`, `JavaScript and Web Development` | folder naming differs | confirm the mastersheet label |
| `TOPv-03` | testing 5 | `Test Automation Design Patterns`, `Test Automation` | folder naming differs | confirm the mastersheet label |

## TOPm — mastersheet label differs from the folder label

Direct evidence for the same question, from the roster itself.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `TOPm-01` | full-stack 3 | folder `Cloud` vs sheet `Cloud Infrastructure` | mastersheet row | confirm the mastersheet label |
| `TOPm-02` | full-stack 4 | folder `JavaScript and Web Dev` vs sheet `JavaScript and Web Development` | mastersheet row | confirm the mastersheet label |
| `TOPm-03` | testing 5 | folder `Test Automation Design Patterns` vs sheet `Test Automation` | mastersheet row | confirm the mastersheet label |

## TOPt — lesson-plan TAB names that look like a module

A tab name matching a module label is a name match with guaranteed misses. Ambiguous rows list every candidate rather than ranking.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `TOPt-01` | backend | tab `Concurrency Lesson Plan` | → `Concurrency` (seq 5) | confirm |
| `TOPt-02` | testing | tab `API Testing Automation` | → `API Testing` (seq 3) | confirm |
| `TOPt-03` | testing | tab `Automation Testing Lesson Plan` | → `Automation Testing` (seq 4) | confirm |
| `TOPt-04` | testing | tab `Performance Testing Lesson Plan` | → `Performance Testing` (seq 2) | confirm |
| `TOPt-05` | testing | tab `Quality Engineering Foundations` | → `Quality Engineering Foundations` (seq 1) | confirm |
| `TOPt-06` | frontend | tab `Frontend` | → `Frontend System Design` (seq 3) | confirm |

## PPL — instructor names needing a decision

A first-name-only cell proposed against that tab's own instructor table. `lib/resolve.py` returns Ambiguous by default; nothing is merged.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `PPL-01` | full-stack  | `Shelby` (primary) | → `Shelby Cohen` | confirm |
| `PPL-02` | full-stack  | `Nisarg` (backup_2) | → `Nisarg Tanna` | confirm |
| `PPL-03` | full-stack  | `Nisarg` (backup_1) | → `Nisarg Tanna` | confirm |
| `PPL-04` | full-stack  | `Cathy` (backup_1) | → `Cathy Ma` | confirm |
| `PPL-05` | full-stack  | `Nisarg` (primary) | → `Nisarg Tanna` | confirm |
| `PPL-06` | backend  | `Konstantinos` (primary) | → `Konstantinos Pappas` | confirm |
| `PPL-07` | backend  | `Shelby` (backup_2) | → `Shelby Cohen` | confirm |
| `PPL-08` | backend  | `Shelby` (backup_1) | → `Shelby Cohen` | confirm |
| `PPL-09` | backend  | `Reginald` (backup_2) | → `Reginald Johnson` | confirm |
| `PPL-10` | backend  | `Faraaz` (primary) | → `Faraaz Sareshwala` | confirm |
| `PPL-11` | testing  | `Bharath` (primary) | → `Bharath Anand` | confirm |
| `PPL-12` | testing  | `(none)` (table) | row held contact data and no name; scrubbed and NOT  | reject — no name to resolve |

## DCK — deck filename → instructor

A filename hint checked against the module's own instructors. D1 forbids people from slide CONTENT; a filename is weaker evidence than the sheet, not stronger.

| id | module | subject | evidence | recommendation |
|---|---|---|---|---|
| `DCK-01` | backend 1 | `[Copy Sep 2023} New Databases Live Class` → `Ashish Kaila` | token `Ashish`, session class | confirm |
| `DCK-02` | backend 1 | `New Database Design Live Class - Konstan` → `Konstantinos` | token `Konstantinos`, session class | confirm |
| `DCK-03` | backend 5 | `IK-backend-concurrency-presentation-v5 -` → `Faraaz` | token `Faraaz`, session class | confirm |
| `DCK-04` | full-stack 2 | `Copy of API Design&Impl - Live Class by ` → `Shelby` | token `Shelby Copy`, session class | confirm |
| `DCK-05` | frontend 3 | `Frontend - Module 3 - System Design - Ev` → `Evgeny Vinnik` | token `Evgeny Vinnik`, session class | confirm |
| `DCK-06` | full-stack 2 | `API Design&Impl - Live Class by Shelby C` → `Shelby` | token `Shelby Copy`, session class | confirm |
| `DCK-07` | full-stack 5 | `UI System Design - Live Class Slides - A` → `Ashish Kaila` | token `Ashish`, session class | confirm |
| `DCK-08` | testing 4 | `IK's Copy of Live Class Slides: Automati` → `Hetal Modi` | token `Hetal Modi`, session class | confirm |
| `DCK-09` | testing 6 | `Cloud Testing - Live Class - Azeem` → `Azeem Ghumman` | token `Azeem`, session class | confirm |
| `DCK-10` | frontend 3 | `Frontend - Module 3 - System Design- Ada` → `Adam Toth` | token `Adam Toth`, session class | confirm |
| `DCK-11` | frontend 3 | `Frontend System Design - by Adam.pptx` → `Adam Toth` | token `Adam`, session class | confirm |
| `DCK-12` | full-stack 4 | `JS and WebD - Live Class by Ashish` → `Ashish Kaila` | token `Ashish`, session class | confirm |
| `DCK-13` | full-stack 5 | `UI System Design - Live Class Slides - A` → `Adam Toth` | token `Adam Toth`, session class | confirm |
| `DCK-14` | testing 1 | `Fundamentals of Test Eng. Live Class Sli` → `Bill Ogden` | token `Bill Ogden`, session class | confirm |

## INS — instructors with the same label in both graphs

Same label, **different id**, in `knowledge/graph.json` (label-keyed, 1,915
instructors) and `knowledge/content_graph.json` (mastersheet-keyed, 38). A
shared label is evidence, not identity — `CLAUDE.md` §2a(iii) and
`lib/resolve.py`. **Nothing is merged automatically.**

`main graph` counts modules reached by `teaches`; `rowB` lists the mastersheet
modules and the role the sheet gives. A person who teaches nothing in the main
graph is not absent from it — they are present with no `teaches` edge.

**Bulk confirmation is offered for exact full-name matches only** (26 rows).
Answer `INS bulk: confirm` to take all of them, or answer any row individually
to pull it out of the bulk set. The six marked **individual** are excluded from
bulk by construction and each needs its own answer.

| id | label | main graph | rowB (mastersheet) | recommendation |
|---|---|---|---|---|
| `INS-01` | `Adam Toth` | teaches 3 | SD1/5 UI System Design [backup_1]; SD2/2 UI & DOM [backup_1]; SD2/3 Frontend System Design [primary] | bulk-confirmable |
| `INS-02` | `Ashish Kaila` | teaches 10 | SD1/4 JavaScript and Web Dev [backup_1]; SD1/5 UI System Design [backup_3]; SD2/4 Leveling Up with Advanced JavaScript and CSS [backup_1]; SD3/1 Database Design [backup_3] | bulk-confirmable |
| `INS-03` | `Azeem Ghumman` | teaches 3 | SD4/6 Cloud Testing [backup_1] | bulk-confirmable |
| `INS-04` | `Balaji Santhanam` | teaches 2 | SD4/6 Cloud Testing [primary] | bulk-confirmable |
| `INS-05` | `Balaram Velaga` | teaches 0 | SD4/2 Performance Testing [backup_1] | **individual** — see note |
| `INS-06` | `Balaram Velega` | teaches 4 | — (in the instructor table, no module row) | **individual** — see note |
| `INS-07` | `Bharath Anand` | teaches 0 | SD4/1 Quality Engineering Foundations [backup_1]; SD4/2 Performance Testing [primary] | bulk-confirmable |
| `INS-08` | `Bill Ogden` | teaches 2 | SD4/1 Quality Engineering Foundations [primary] | **individual** — see note |
| `INS-09` | `Cathy Ma` | teaches 2 | SD1/4 JavaScript and Web Dev [primary]; SD1/5 UI System Design [backup_2] | bulk-confirmable |
| `INS-10` | `Daniel Grundel` | teaches 2 | SD1/4 JavaScript and Web Dev [backup_3] | bulk-confirmable |
| `INS-11` | `David Prorok` | teaches 2 | SD2/2 UI & DOM [primary] | bulk-confirmable |
| `INS-12` | `Dominique Canlas` | teaches 3 | SD2/1 JS Language & Libraries [primary] | bulk-confirmable |
| `INS-13` | `Evgeny Vinnik` | teaches 4 | SD2/1 JS Language & Libraries [backup_1]; SD2/3 Frontend System Design [backup_1]; SD2/4 Leveling Up with Advanced JavaScript and CSS [primary] | bulk-confirmable |
| `INS-14` | `Faraaz Sareshwala` | teaches 4 | SD1/3 Cloud [primary] | bulk-confirmable |
| `INS-15` | `Hetal Modi` | teaches 6 | SD4/2 Performance Testing [backup_2]; SD4/4 Automation Testing [primary]; SD4/5 Test Automation Design Patterns [backup_1] | bulk-confirmable |
| `INS-16` | `Jeff Wisman` | teaches 3 | SD1/3 Cloud [backup_2]; SD3/4 Cloud Native Design [backup_1] | bulk-confirmable |
| `INS-17` | `Konstantinos Pappas` | teaches 5 | SD1/4 JavaScript and Web Dev [backup_2] | bulk-confirmable |
| `INS-18` | `Nikhil Kolekar` | teaches 9 | SD1/3 Cloud [backup_3]; SD3/2 Object Modeling [backup_2] | bulk-confirmable |
| `INS-19` | `Nisarg Tanna` | teaches 0 | — (in the instructor table, no module row) | bulk-confirmable |
| `INS-20` | `Reginald Johnson` | teaches 7 | — (in the instructor table, no module row) | bulk-confirmable |
| `INS-21` | `Robert Kreznarich` | teaches 7 | SD1/2 API Design and Implementation [backup_1]; SD3/1 Database Design [backup_1]; SD3/2 Object Modeling [backup_1]; SD3/3 API Design [primary]; SD3/5 Concurrency [backup_1] | bulk-confirmable |
| `INS-22` | `Rodrigo Salazar` | teaches 2 | SD4/3 API Testing [primary] | bulk-confirmable |
| `INS-23` | `Rushi Vyas` | teaches 0 | — (in the instructor table, no module row) | bulk-confirmable |
| `INS-24` | `Sanjay Dhar` | teaches 5 | SD3/4 Cloud Native Design [primary]; SD4/6 Cloud Testing [backup_2] | bulk-confirmable |
| `INS-25` | `Sergey Togulev` | teaches 6 | SD4/1 Quality Engineering Foundations [backup_2]; SD4/5 Test Automation Design Patterns [primary] | bulk-confirmable |
| `INS-26` | `Shelby Cohen` | teaches 0 | — (in the instructor table, no module row) | bulk-confirmable |
| `INS-27` | `Sindhu Singh Dua` | teaches 0 | SD4/1 Quality Engineering Foundations [primary]; SD4/4 Automation Testing [backup_1] | bulk-confirmable |
| `INS-28` | `Thong Tran` | teaches 2 | — (in the instructor table, no module row) | bulk-confirmable |
| `INS-29` | `Tilo Dickopp` | teaches 12 | SD3/2 Object Modeling [primary]; SD3/3 API Design [primary] | bulk-confirmable |
| `INS-30` | `William David Ogden` | teaches 0 | — (in the instructor table, no module row) | **individual** — see note |
| `INS-31` | `Konstantinos` | teaches 1 | SD3/1 Database Design [primary] | **individual** — first name only |
| `INS-32` | `Shelby` | teaches 1 | SD1/2 API Design and Implementation [primary]; SD3/1 Database Design [backup_2]; SD3/3 API Design [backup_1] | **individual** — first name only |

### Notes on the six individual rows

**`INS-05` / `INS-06` — `Balaram Velaga` and `Balaram Velega`.** Both labels
exist in the MAIN graph, one letter apart. `Velaga` teaches 0 and holds the
rowB module; `Velega` teaches 4 and holds none. This is very likely one person
spelled two ways, which makes it a defect in the main graph that the content
crawl exposed rather than a cross-graph join. Per `CLAUDE.md` §1 a typo is
load-bearing and is never corrected in place — so the answer needed is which
spelling is the person, with the other recorded as an alias.

**`INS-08` / `INS-30` — `Bill Ogden` and `William David Ogden`.** Bill is a
conventional short form of William, so these may be one person under two names.
An exact-label match would never pair them, and a nickname table would pair
`Bill`/`William` along with false positives. Owner knowledge decides.

**`INS-31` / `INS-32` — `Konstantinos` and `Shelby`.** First-name-only forms
that carry the rowB module rows, while the full-name nodes `Konstantinos
Pappas` (`INS-17`) and `Shelby Cohen` (`INS-26`) carry none. The same pair is
already open as `PPL-06` and `PPL-01`; answering those settles these, and the
two must be answered consistently or the module rows attach to a different
node from the instructor record.
