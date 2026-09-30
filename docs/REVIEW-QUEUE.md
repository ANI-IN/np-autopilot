# REVIEW QUEUE — 106 decisions, answer by ID

**Generated 2026-09-29 from the four review YAMLs; answers recorded below as
they arrived.** 68 of 89 rows are answered — MOD 18, INS 32, PPL 12, TOPv 3,
TOPm 3 — and the applied ones are merged by pass 8
(`pipeline/08_merge_graphs.py`) or pass 7 (the module labels). **38 remain
open**: TOPt 6, PPL 1 (PPL-12), DCK 14, NAM 16 and DUP 1 (added 2026-09-30,
queued for later by the owner). The tables below are the rows as first
generated, with a recommendation and an ID to answer by.

**Count convention.** A row is **answered** once the owner has decided it —
including "leave unresolved", which is a decision, not a pending question
(PPL-09 `Reginald`, 2026-09-30). A row is **open** only while it has no owner
answer. `docs/HANDOFF.md` §E uses the same convention.

**A recommendation is not a decision.** Where it says *needs owner knowledge*,
the evidence genuinely does not settle it and a guess would be the
picking-with-no-signal failure `lib/resolve.py` exists to refuse.

| group | rows | source |
|---|---:|---|
| `MOD` | 18 | `config/module-aliases-review.yaml` (MOD-17/18 added and answered 2026-09-30) |
| `TOPv` | 3 | `config/content-topic-review.yaml` |
| `TOPm` | 3 | `config/content-topic-review.yaml` |
| `TOPt` | 6 | `config/content-topic-review.yaml` |
| `PPL` | 13 | `config/mastersheet-people-review.yaml` (PPL-13 added 2026-09-30) |
| `DCK` | 14 | `config/deck-instructor-review.yaml` |
| `INS` | 32 | derived: both graphs (see below) |
| `NAM` | 16 | `config/instructor-name-review.yaml` (added 2026-09-30) |
| `DUP` | 1 | entered by hand (added 2026-09-30) |
| **total** | **106** | |


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

## NAM — instructor labels that are not one person's name

Added 2026-09-30 on the owner's instruction (origin: hand, Animesh Kumar):
queued for later, **not changed now**. From `config/instructor-name-review.yaml`,
generated by `pipeline/gen_name_review.py` over instructors with no role in the
current mastersheet. The rule (`pipeline/lib/name_review.py`) deliberately does
not match credentials, bracketed nicknames or initials (CLAUDE.md §4).

| id | label | shape | recommendation | source |
|---|---|---|---|---|
| NAM-01 | `2- Prateek` | enumerated | strip the list number; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-02 | `Agentic IP Instructors` | collective | not a person: take it out of the instructor type | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-03 | `Akshat Gupta (Aksh Tech Solutions LLP)` | annotated | move the note out of the name; keep label_raw | `03-instructors/SME database (For Ops + NP).xlsx` |
| NAM-04 | `Amrita Ray, Hemanth Pugaliya` | several | split into one instructor per name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-05 | `Ashish Kaila / JD Kelby` | several | split into one instructor per name; keep label_raw | `02-curriculum/Resource Collection Mastersheet (Software + System).xlsx` |
| NAM-06 | `Indian SME hiring` | collective | not a person: take it out of the instructor type | `02-curriculum/Resource Collection Mastersheet (Software + System).xlsx` |
| NAM-07 | `Instructor` | collective | not a person: take it out of the instructor type | `02-curriculum/Data and Management.xlsx` |
| NAM-08 | `Itamar, Reza S` | several | split into one instructor per name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-09 | `Lekshmi Pillai, Tania` | several | split into one instructor per name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-10 | `Nazeer Ahmed (yet to be trained)` | annotated | move the note out of the name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-11 | `PMs/TPMs` | collective, several | not a person: take it out of the instructor type; split into one instructor per name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-12 | `Prashant Patel (Software Solution Hub)` | annotated | move the note out of the name; keep label_raw | `03-instructors/SME database (For Ops + NP).xlsx` |
| NAM-13 | `Robert/Shelby/` | several | split into one instructor per name; keep label_raw | `02-curriculum/Resource Collection Mastersheet (Software + System).xlsx` |
| NAM-14 | `Thong/Alex` | several | split into one instructor per name; keep label_raw | `02-curriculum/Resource Collection Mastersheet (Software + System).xlsx` |
| NAM-15 | `Udit Mehrotra(Old content)` | annotated | move the note out of the name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |
| NAM-16 | `Yan Xu, Sean Zhu` | several | split into one instructor per name; keep label_raw | `03-instructors/AgenticAI Instructors Training Plan.xlsx` |

## DUP — likely duplicate identities, queued by hand

Added 2026-09-30 on the owner's instruction (origin: hand, Animesh Kumar):
**queued for later, no action now.** Not produced by a rule; each row is
entered by hand with its evidence, and nothing is merged until answered.

| id | labels | evidence | recommendation |
|---|---|---|---|
| DUP-01 | `Anshaj` · `Anshaj Khare` | both are older-sheet instructors named in `03-instructors/AgenticAI Instructors Training Plan.xlsx` and `05-operations/New Combined Schedule.xlsx`, and both teach `Python Fundamentals Crash Course`, `Python for GenAI` and `Fundamentals of Agentic AI`; `Anshaj Khare` is also in the Instructors Directory, the SME database and the interview audits | likely the same person: merge as an INS identity (canonical `Anshaj Khare`, alias `Anshaj`) when answered |

---

## ANSWERED — 2026-09-29, Animesh Kumar (origin: hand)

Recorded in `config/instructor-identity.yaml`. Hand-entered facts emit no
`sourced_from` edge and must never be presented as though a scan produced them.

| ids | answer |
|---|---|
| `INS-05` `INS-06` | **One person.** Canonical `Balaram Velaga` (the mastersheet spelling); `Balaram Velega` is an alias. Both spellings stay in `label_raw` and provenance — neither source is edited (§1). The merged instructor shows both modules. |
| `INS-08` `INS-30` | _Superseded 2026-09-30 — merged, see below._ **Unresolved by decision.** `Bill Ogden` / `William David Ogden` stay separate nodes, rendered **unconfirmed** in the matrix. Not a gap in review. |
| `INS-31` `INS-32` (with `PPL-06`, `PPL-01`) | _Superseded 2026-09-30 — merged, see below._ **Full names unknown — left unresolved by decision** (answered, not open; see the count convention above). `Konstantinos` and `Shelby` stay unresolved nodes and **keep their module attachments**, marked unconfirmed. Moving real modules onto an unconfirmed full name would attach them to a guess. |

Remaining open: 78 of 86.

### MOD-01…16 — answered 2026-09-29, applied by pass 8

Recorded in `config/module-merges.yaml`, applied by `pipeline/08_merge_graphs.py`.

| ids | answer |
|---|---|
| `MOD-02 03 05 06 07 08 09 10 11 13 16` | **merge** (bulk) — shared instructor and same programme family |
| `MOD-01` | **merge.** Legacy instructors stay a separate evidence tier and are never shown as mastersheet roles. _(Said the sheet cell was "blank in source"; it was a parser bug — corrected 2026-09-30.)_ |
| `MOD-12` | **merge** — distinctive label, no contradicting evidence |
| `MOD-14` | **merge**, and must never be joined with SD4/5 `Test Automation`. Asserted by `tests/test_module_merges.py` |
| `MOD-04` | **merge into SD2/2 (Frontend).** The legacy Full-Stack programme edges are kept with their provenance, marked **unconfirmed** — neither deleted nor asserted |
| `MOD-15` | legacy `Week 5 - Test Automation` **is** SD4/5; the two `… Class` rows map to its class and assignment-review **sessions**. Legacy instructors (Roland Kunkel, Ioan Moldovan) stay legacy-tier evidence on those sessions |

Remaining open: **62 of 86** — 26 `INS` bulk rows, `INS-08/30/31/32` answered as
deliberately unresolved, and the `TOPv` / `TOPm` / `TOPt` / `PPL` / `DCK` groups.

### INS bulk — answered 2026-09-29, applied by pass 8

26 exact full-name matches confirmed, with a safeguard run before every merge
and re-run on every build: a pair is excluded if `lib/resolve.py` calls the name
Ambiguous, or if the two nodes' **domain reach** is wholly disjoint.

**0 pairs excluded.** 17 pairs had domain evidence on both sides and every one
shared a family; 9 had evidence on one side only, which is *absence* of
evidence and is not treated as a conflict.

| | |
|---|---|
| duplicate instructor labels | **32 → 4** |
| excluded by the safeguard | **0** |
| still duplicated | `Bill Ogden`, `William David Ogden` (INS-08/30), `Konstantinos`, `Shelby` (INS-31/32) — all four by owner decision |

Remaining open: **36 of 86** — `TOPv` 3, `TOPm` 3, `TOPt` 6, `PPL` 10, `DCK` 14.

### PPL-11 — answered 2026-09-29, applied by pass 8

Recorded in `config/instructor-identity.yaml` (`bharath-anand`, `origin: hand`).

| id | answer |
|---|---|
| `PPL-11` | **`Bharath` (Test Engineering, primary) is Bharath Anand.** Merged: one `Bharath Anand` instructor node; `Bharath` stays in `label_raw` and provenance (§1). Verified in `knowledge/merged_graph.json` 2026-09-30 — no standalone `Bharath` node remains. |

Remaining open: **35 of 86** — `TOPv` 3, `TOPm` 3, `TOPt` 6, `PPL` 9
(PPL-02…05, 07…10, 12), `DCK` 14. The earlier "36" counted PPL-11 as open;
the earlier "Remaining open" lines above are the running count at the time
each answer landed.

### Checklist review — answered 2026-09-30, Animesh Kumar (origin: hand)

Identities recorded in `config/instructor-identity.yaml` and applied by pass 8
with the same rules as the bulk merge: every absorbed label stays in
`label_raw` / `merged_label_raw` and provenance (§1), the mastersheet and
legacy tiers are never merged into each other, and each entry is tagged
(`asserted_by`, `asserted_at`) and reversible by deleting it.

| ids | answer |
|---|---|
| `INS-31`, `PPL-06` | **`Konstantinos` is Konstantinos Pappas.** Merged. Supersedes the 2026-09-29 "left unresolved". |
| `INS-32`, `PPL-01` `PPL-07` `PPL-08` | **`Shelby` is Shelby Cohen.** Merged. Supersedes the 2026-09-29 answer. |
| `INS-08` `INS-30` | **`Bill Ogden` is William David Ogden.** Merged under the full name; `Bill Ogden` kept as an alias. |
| `PPL-10` | **`Faraaz` is Faraaz Sareshwala.** Merged. |
| `PPL-04` | **`Cathy` is Cathy Ma.** Merged. |
| `PPL-02` `PPL-03` `PPL-05` | **`Nisarg` is Nisarg Tanna.** Merged. |
| _(no row)_ | **`Robert K` is Robert Kreznarich.** Merged. Raised in the checklist review, not by the generator. |
| `PPL-09` | **`Reginald` stays unresolved** — a decision, not an open question. The node keeps its module attachment and is rendered **unconfirmed** (`identity_unconfirmed`) in the checklist and the matrix. |
| `TOPv-01…03`, `TOPm-01…03` | **The mastersheet name is the module label**; the folder name is kept as `label_raw` (the citation key). SD1/3 `Cloud Infrastructure` (folder `Cloud`), SD1/4 `JavaScript and Web Development` (folder `JavaScript and Web Dev`), SD4/5 `Test Automation` (folder `Test Automation Design Patterns`). Node ids are unchanged. Applied by pass 7. |

| | |
|---|---|
| duplicate instructor labels | **4 → 0** |
| identities flagged unconfirmed | **1** (`Reginald`) |

**New rows raised by these answers — OPEN.** Adopting the mastersheet names
made two row-B modules share a label with a legacy main-graph module. A shared
label is not a match (`CLAUDE.md` §2a(iii)); nothing is merged until answered.
`tests/test_module_merges.py` pins these two as the only duplicate module
labels.

| id | row-B module | legacy module | evidence | recommendation |
|---|---|---|---|---|
| `MOD-17` | SD1/3 `Cloud Infrastructure` (`mod_ab9e5ee393195cf2`, folder `Cloud`) | `Cloud Infrastructure` (`mod_a7301acdd24c0050`; 8 `teaches`, from `UpLevel Schedule Structure`, `New Combined Schedule`) | shared instructors: Faraaz Sareshwala, Jeff Wisman, Nikhil Kolekar | **merge** — the MOD bulk criterion (shared instructor, same family); legacy tier kept apart |
| `MOD-18` | SD1/4 `JavaScript and Web Development` (`mod_00ee7c30fff3dc36`, folder `JavaScript and Web Dev`) | `JavaScript and Web Development` (`mod_067e0cede10d31eb`; 3 `teaches`, same two files) | shared instructors: Ashish Kaila, Cathy Ma. The legacy tier also lists **Daniel Grundel** — consistent with the withdrawn Backup 3, and it stays legacy evidence | **merge**, same terms |

Remaining open: **23 of 88** — `MOD-17/18` 2, `TOPt` 6, `PPL-12` 1, `DCK` 14. Several `DCK`
rows name `Konstantinos` or `Shelby`; those identities are now settled, but
which instructor a deck belongs to is a separate question and the rows stay
open.

### Checklist review part 3 — 2026-09-30, Animesh Kumar (origin: hand)

| id | answer |
|---|---|
| `MOD-17` `MOD-18` | **Keep separate — not merged.** Recorded in `config/module-merges.yaml` (`kept_separate`). The two label pairs stay duplicated by decision, and `tests/test_module_merges.py` pins them as the only duplicate module labels. |

**New row — a PROPOSAL, not applied. The owner confirms or declines it.**

| id | proposal | evidence (live sheet `1setMmRv…`, fetched 2026-09-30, version 2736) | recommendation |
|---|---|---|---|
| `PPL-13` | `Reginald` → **Reginald Johnson** (reopens `PPL-09`, left unresolved 2026-09-30) | `Backend Engineering!D50`: week 4 *Cloud Native Design*, **Backup 2** = `Reginald`. `Backend Engineering!A66`: the Backend tab's instructor table lists `Reginald Johnson` — the only Reginald on any of the four in-scope tabs. | **confirm** — same tab, the only candidate; applied like the other first-name merges, alias kept, tiers apart |

Remaining open: **22 of 89** — `TOPt` 6, `PPL-12` 1, `PPL-13` 1, `DCK` 14.

### PPL-13 — confirmed 2026-09-30, Animesh Kumar (origin: hand), applied by pass 8

| id | answer |
|---|---|
| `PPL-13` (reopens `PPL-09`) | **`Reginald` is Reginald Johnson.** Merged (`config/instructor-identity.yaml`, `reginald-johnson`): alias kept in `merged_label_raw`, provenance unioned, tiers apart, tagged and reversible. SD3/4's confirmation re-bound — the rename was its only change (`config/owner-confirmations.yaml`). No identity is left unconfirmed. |

Remaining open: **21 of 89** — `TOPt` 6, `PPL-12` 1, `DCK` 14.

