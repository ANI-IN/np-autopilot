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
