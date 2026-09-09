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
