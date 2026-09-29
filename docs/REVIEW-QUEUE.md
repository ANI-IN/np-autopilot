# REVIEW QUEUE — 54 decisions, answer by ID

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
| **total** | **54** | |


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
