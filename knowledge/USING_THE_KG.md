# Using the knowledge graph

Hand-written traversal guide. `INDEX.md` is auto-generated — counts live there,
never here.

---

## Read this before answering anything about people leaving

**This corpus is scoped to New Programs. It can only observe someone leaving
*New Programs*. It cannot tell you whether they left Interview Kickstart.**

The two look identical in the data. Someone who moves to another IK team stops
appearing in `IAims` objective sheets, drops off `Domains_Courses Owners.xlsx`,
and their trail ends — exactly like someone who resigned.

Confirmed cases where the corpus is misleading:

| Person | Corpus shows | Actually |
|---|---|---|
| `Swarup Yeole` | Trail stops after Q3 2025 | **Still at IK.** Switched teams. |
| `Abhinav Rawat` | One cell in 75 files | **Still at IK.** Switched teams before the corpus was assembled. |
| `M Prasad Khuntia` | Full objectives through Q1 2026, active | **Left the company.** Confirmed out-of-corpus. |

Note the last row: the corpus is wrong in **both directions**. It makes leavers
look present and movers look gone.

**Rules for any answer about departures or current staff:**

1. **Never say someone "left the company" from corpus evidence alone.** The
   corpus cannot support that claim. Say "no longer appears in New Programs
   records after `<quarter>`" and stop.
2. **`person.team` is the authority, not the trail.** `np`, `delivery`, `former`
   and `other` are set from the HR directory and from explicit confirmation.
   `former` can only ever come from out-of-corpus evidence.
3. **When `corpus_disagrees: true`, say so.** `M Prasad Khuntia` carries it. An
   answer marking him former must state that the basis is out-of-corpus and that
   the files lean the other way.
4. **Coverage must not report movers as gone.** A coverage query that flags
   people whose trail ended will return current IK employees. Filter on `team`,
   and label the result "left New Programs", never "left IK".

**Weak provenance is expected here, not a defect.** Someone who left NP before
the corpus was assembled leaves almost no trace — `Abhinav Rawat` is a single
cell in 75 files. That is the *correct* shape for that class of person. Do not
clean it up, and do not fuzzy-match it into someone better-evidenced; eight other
people named Abhinav exist in this corpus and every one is a different person.

---

## Quarters

Never parse a sheet name. Three conventions coexist and they conflict: `Q226` is
**2026 Q2** but `Q42025` is **2025 Q4** — the same digit position means different
things. Resolve through `quarter_vocabulary` in `config/taxonomy.yaml` and sort
on its `order` field only.

Latest quarter in the corpus: **`Q226` = 2026 Q2**.

---

## The graph is two components

`workflow_owned_by` is the only bridge, and it only carries edges for rows you
have confirmed in `config/workflow-owners.yaml`. Until then:

- **Component A** — `Theme` ← `Workflow` → `Workflow`, plus workflow properties
  (steps, effort, alerts, tools).
- **Component B** — `Person` ← `Domain` → `Program` → `Module` ← `Instructor`.

Questions that cross A↔B are unanswerable, and `sourced_from` is not a bridge:
all 92 workflows share one `File` node, so it is a degree-92 hub.

---

## Counts

`person`, `instructor` and `module` have no expected count. **25 of 75 corpus
files have never been read by an entity scan**, so any figure is a floor over
a subset. Never quote one as a total.

---

## What the edges mean — and what they do NOT

### `contains` (program → module) is INFERRED, not observed

**No file in this corpus pairs a program with a module on a row.** Not one.
Every `contains` edge is derived `program → domain → module`, because the
curriculum sheet name *is* a domain, and every edge carries `inferred: true`
with its `join_basis`. Read 397 edges as 397 inferences, not 397 observations.

**212 of 484 modules carry no `contains` edge at all.** They come from sheets
with no owner-sheet domain — the `M_SME_*` Agentic AI pathway sheets and the
instructor-expertise lists. They are unattached **on purpose**: a wrong join is
worse than a missing one (R12), and no domain in the 42 corresponds to them.
An unattached module is not a defect to fix.

### `depends_on` is ZERO, and no workflow-to-workflow reasoning is possible

Every workflow body was searched. One `N.M`-shaped hit, and it is a false
positive — the string `1.5-2 hrs` in an Effort line. Zero references by workflow
name. **There is no dependency evidence in this corpus.** Doc 08 Q5's `3.6 → 3.1`
example is withdrawn.

**Consequence, stated plainly: component A is 92 workflows pointing at 16 themes
and nothing else.** No ordering, no prerequisites, no "what breaks if this stalls".
Do not answer a sequencing question about workflows from this graph — the edges
that would support it do not exist. `workflow_owned_by` is the only edge that
will ever give component A internal structure, and it is filled by hand.

### `covers` joins 28 of 42 programs. These 14 have NO domain

Unjoined because they need spell-correction or abbreviation expansion, which R12
forbids. **They are not domain-less products** — do not report them that way:

- `Advanced Machine Learning Program (with Agentic AI)`
- `Cloud Architect Interview Preparation Program`
- `Data Analyst Businees Analyst EdgeUP KYP`
- `Data Analyst Business Analyst Interview Preparation Program`
- `Enginnering Mnagement EdgeUP KYP`
- `FastTrack_ (Self Paced) Ad. Machine Learning(with Agentic AI) KYP`
- `Flagship Machine Learning Program (with Agentic AI)`
- `Forward Deployed Engineering Level-Up Program_ KYP - 2026`
- `Forward Deployed Engineering[FDE] Course _ KYP - 2026`
- `Forward Deployed Engineering[FDE] Upskilling Course _ KYP - 2026`
- `Product Management EdgeUP KYP`
- `Site Reliability Engineering EdgeUP KYP`
- `Site Reliability Engineering Interview Preparation Program`
- `v2 [New] AI Data Science Program`

Each has an obvious human-readable domain (SRE, PM, EM, DABA, ML) that the
corpus does not spell the same way twice. The join is left undone rather than
forced.

### Instructors: the graph holds a hiring funnel, the render does not

`instructor` nodes carry `pipeline_status`. Only `roster` and `hired` are
renderable; `in_pipeline`, `rejected` and `lapsed` are tagged `sensitive: true`
and **excluded from the rendered graph** — 1,842 nodes, including 255 hiring
rejections about named external people. They remain in `graph.json` so coverage
can answer funnel questions. **Never surface a rejection to a general audience.**

Counting the funnel as its outcome is how the reference implementation published
773 instructors against a real 351.

---

## The graph is many components BY DESIGN

Not a limitation to work around. A description of how New Programs works.

- **Component A** — `Theme` ← `Workflow`. 16 themes, 92 workflows, and no
  internal structure: `depends_on` has no evidence and `workflow_owned_by` is
  empty.
- **Component B** — `Person` ← `Domain` → `Program` → `Module` ← `Instructor`,
  plus `Instructor` → `Domain`.

**They do not join, and they should not.** Ownership in NP attaches to
**domains**, not workflows: everyone does every kind of work, and each person
coordinates with SMEs across development, live class, ARS and RCA. There is no
per-workflow owner to record, so `workflow-owners.yaml` is 92 blank rows and that
is its correct final state.

**Answering "who owns workflow N":** return the **domain-level** owner with an
explanation. Never a workflow-level name — no such fact exists, and inventing one
is the worst failure this graph can produce.

**Coverage must not report 92 workflows as missing an owner.** That presents a
correct state as a defect and invites someone to fix it by making data up.
Coverage says workflow-level ownership is out of scope and points at domain
owners.

---

## `expert_in` is NOT teaching evidence

`expert_in` (instructor → domain) is a **declared subject field**. `teaches`
(instructor → module) is a **row-level pairing**. They are separate edge types on
purpose, so a staffing query can tell the two apart.

Every `expert_in` edge carries `basis`:

| basis | source | what it means |
|---|---|---|
| `self_declared` | `Instructors Directory!Responses` | **A Google Form signup.** Someone ticked a domain box. **Not verified capability, and not evidence they have ever taught anything.** 740 edges. |
| `hr_record` | `SME database!Master` | An HR roster assignment. 62 edges. |

**Never answer "who can teach X" from `expert_in` alone.** Nine out of ten of
these edges are someone's own form response. Use `teaches` for delivery history
and `expert_in` only to widen a shortlist, saying which is which.

**The join is lossy — 802 edges from 1,607 claims, a 50% rate.** The 803
unjoined claims are in `config/expert-in-review.yaml`; the largest is `ML` (153
claims), which the owner sheet spells `Machine Learning (IP course)`. Nothing is
spell-corrected to force a match (R12). Confirming a small number of aliases —
`ML`, `Technical Program Management`, `Product Management`, `Engineering
Management` — would recover most of the remainder, and that is a decision for a
human, not the pipeline.

---

## Alias-recovered `expert_in` edges are TWO inference steps, not one

Domain aliases (`config/domain-aliases.yaml`, hand-confirmed) only ever expand
`expert_in`. They add **zero** `teaches` edges. That matters, because
`expert_in` is already **92% `self_declared`** — someone's own form response.

So an alias-recovered edge carries **two** inference steps stacked:

1. the person **declared** a subject on a form (not verified capability), and
2. that declared string was **matched to a domain through a human-confirmed
   alias**, not because the two strings agree.

Every such edge carries **`via_alias: true`** and records the alias that matched
it. A staffing query must be able to tell these apart, and should rank:

```
teaches (row-level pairing)
  > expert_in basis=hr_record
    > expert_in basis=self_declared
      > expert_in basis=self_declared AND via_alias=true   ← weakest
```

**Never present an alias-recovered self-declared edge as evidence someone can
teach something.** It means: this person wrote a subject on a form, and we
decided that subject probably meant this domain.

**The sibling-domain test guards the second step.** An alias is only proposed
when exactly ONE domain could plausibly be meant. `ML` failed it — five domains
carry that name (`Machine Learning (IP course)`, `Flagship ML/ ML Program`,
`ML Switch-up (Adv ML)`, `Advanced ML Ops`, `Advanced ML Interview Prep`) — and
mapping it would have put 153 instructors on a possibly-wrong domain. It stays
unjoined, as does `Product Management` (PM vs GPM) and `Agentic AI` (four
domains).

---

## The graph has 36 components, not 2 — and component A is 16 stars

The earlier "two components" framing was wrong and is withdrawn everywhere.
Measured on the rendered subgraph:

| # | nodes | contents |
|---|---|---|
| 1 | **1,144** | domain 42 · person 26 · instructor 700 · module 348 · program 28 |
| 2 | 16 | theme 1 · workflow 15 |
| 3 | 10 | theme 1 · workflow 9 |
| 4 | 9 | theme 1 · workflow 8 |
| 5–17 | 2–8 each | one theme + its workflows |
| … | | 36 components in total |

**"Component A" is not one cluster of 92 workflows. It is SIXTEEN separate
star clusters, one per theme**, because a workflow's only edge is `belongs_to`
pointing at its theme. `depends_on` has no evidence and `workflow_owned_by` is
empty by design.

**The consequence, stated plainly:**

> From a workflow you can reach **its theme, and its sibling workflows under that
> theme. Nothing else.** There is no path from any workflow to any person,
> program, module or instructor. Not a long path — **no path**.

Two themes cannot even reach each other. Any question that starts at a workflow
and needs a person, a program or an instructor is unanswerable, and no amount of
traversal will find one.

---

## Staffing: teaching history now covers the core domains — CORRECTED 2026-09-10

An earlier build had **668 `teaches` edges, every one from the AgenticAI
workbook**. The graph had teaching evidence for Agentic AI and none for any
domain NP runs at scale. That is no longer true.

**`05-operations/New Combined Schedule.xlsx` is the class delivery log**, and
only one of its 62 sheets had ever been read. **44 more are per-domain class
schedules carrying `Instructor Name` against `Class Topic`** — who actually
taught what. Class-format suffixes (`Live Class`, `Assignment Review Class`,
`Test Review Session`) are stripped so the same module in two formats resolves
to one node.

**`teaches`: 668 → 1,889.** 369 instructors, 736 modules.

| domain | taught / modules |
|---|---|
| TPM | 36 / 43 |
| Fullstack | 11 / 17 |
| Security | 8 / 16 |
| Embedded | 8 / 18 |
| Backend | 7 / 21 |
| PM | 7 / 18 |
| Cloud | 5 / 13 |
| Data Engineering | 5 / 5 |
| Frontend | 4 / 6 |
| Test Engineering | 3 / 14 |
| EM | 1 / 14 |
| **Android** | **0 / 4** |
| **iOS** | **0 / 7** |

**Android and iOS have zero, and the reason is that THEY HAVE NO INSTRUCTORS** —
confirmed by the corpus owner on 2026-09-10 (`config/out-of-corpus-facts.yaml`).
It is a staffing fact about the business, **not a data gap**.

- **Never** list Android or iOS in a "domains with no teaching evidence" report.
- **Never** suggest someone go and find the missing file. There isn't one.
- Any answer stating this must say the basis is **out-of-corpus**.

**A withdrawn inference, recorded because the difference matters.** An earlier
build explained the zero by the owner sheet's `Video Only` cadence — no live
classes, nothing to log. That was wrong. `Video Only` is a real value in rows 16
and 17, but it is a separate observation, not the cause. One explanation implies
these domains are staffed but undocumented; the other says they are not staffed.

**Class dates are on the edge, as RAW EVIDENCE.** `teaches` carries
`class_dates`: every recorded date for that instructor/module pair, sorted and
deduplicated. 1,499 of 2,239 edges have dates, and some are future-only —
scheduled but never yet delivered.

`first_taught`, `last_taught`, `sessions_past`, `sessions_scheduled` and
`sessions_recorded` are **derived at read time** by `pipeline/lib/teaching.py`,
not stored. They used to be stored, computed against "today" at build time,
which made the graph deterministic within a day and not across days — and left a
cached plugin snapshot describing a July class as still "scheduled". Deriving
them means an answer is current whenever it is asked, and the graph itself
carries no clock-dependent value. See AUDIT §B.4.

A staffing answer should prefer recent delivery and must not present a scheduled
class as teaching history: `last_taught` is the latest date NOT in the future,
and is `null` for a pair that is only booked.

**A staffing answer must still lead with what is absent.** For a domain with no
`teaches` edges, say so first, before offering any `expert_in` name — those are
92% Google Form responses.

---

## Name resolution: ambiguity is the default return

Three separate bugs had one shape — several plausible targets, one chosen with no
signal to the caller:

| name | resolved to | should have been |
|---|---|---|
| `Agentic AI` | one of four Agentic AI domains | ambiguous (caught pre-ship) |
| `ML` | `ML Switch-up (Adv ML)` by prefix | ambiguous — 5 domains contain the token |
| `Data Science` | `AI Data Science Switch-up (DS 2.0)` | `Data Science (IP course)` |

**One rule now, in `pipeline/lib/resolve.py`, used everywhere.**

Stages run most-specific first and **stop at the first stage that yields any
candidate**. A looser later stage never rescues an ambiguous earlier one — that
would be picking.

1. exact
2. paren-stripped — `Data Science (IP course)` matches `data science`
3. **token** — for a single-token query only, whole-word match. `ML` appears as a
   token in five domain names, so it stops here as ambiguous rather than being
   caught by prefix.
4. prefix
5. substring

**More than one candidate at any stage returns `Ambiguous`, never
`candidates[0]`.** A caller must either get exactly one answer or handle the
ambiguity by asking. `test_ambiguity_is_returned_not_guessed` pins this.

**Aliases are a different mechanism and "no match" is their expected result** — an
alias exists precisely because the string does not resolve. The guard on an alias
is the **sibling-domain test** (`resolve.siblings`, word-boundary token sets, never
substrings). All 17 pending aliases pass it; `ML` and `Product Management` do not
and stay unjoined.

Two of the 17 are **redundant**: `System Design` and `DSA` already resolve
cleanly without an alias, to the same target. Confirming them is harmless but
unnecessary.

---

## The module layer hangs off INSTRUCTORS, not programs

Read this before treating modules as program-anchored. They are not.

| how a module is reached | modules | |
|---|---|---|
| by `teaches` (instructor → module) | **768** | 83% |
| by `contains` (program → module) | 198 | 21% |
| **only** by `teaches` | **671** | **73% — these vanish if instructors are hidden** |
| only by `contains` | 101 | |
| by neither | 53 | |

**351 `contains` edges against 2,239 `teaches` edges.** And `contains` is itself
inferred (program → domain → module) — there is no row-level program↔module
pairing anywhere in the corpus.

**Consequence, measured:** hide instructors in the render and the graph goes to
**1,157 nodes / 627 edges / 772 components, 755 of them singletons.** The module
layer shatters, because for three modules in four the only thing joining them to
anything is the person who taught them.

**So:**
- A question about what a *program* contains is answerable for **21%** of modules.
- A question about who *taught* a module is answerable for **83%**.
- Do not present the module layer as curriculum structure. It is a **delivery
  record** that happens to name modules.
