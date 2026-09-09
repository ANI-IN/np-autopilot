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

## The graph is two components BY DESIGN

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
