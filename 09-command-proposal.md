# 09 — B9 Command Proposal

Against measured edge counts, 2026-09-10. Every claim below is a number from
`graph.json`, not a design intention.

| edge | count | what it can carry |
|---|---|---|
| `teaches` | **1,889** | who taught what, **with dates** (1,294 dated) |
| `expert_in` | 802 | declared subject — 92% Google Form |
| `contains` | 347 | program → module, **all inferred via domain** |
| `belongs_to` | 92 | workflow → theme. The only workflow edge. |
| `supported_by` / `owned_by` / `delivered_by` | 156 | domain → person |
| `covers` | 28 | program → domain (28 of 42 programs) |
| `depends_on` / `workflow_owned_by` | **0** | no evidence / not how NP works |

---

## Verdict on the six commands in the original brief

| brief command | verdict |
|---|---|
| `setup` | **Keep as-is.** No traversal. Reports counts, build date, and the Drive-deferral warning. |
| `workflow` | **Keep, scoped to lookup.** 92 workflows × steps/effort/alerts/tools. One edge each. Not reasoning. |
| `owner` | **REPLACE with `domain-owner`.** 156 domain→person edges are real; workflow ownership does not exist (R2). The name must not promise what cannot be delivered. |
| `alerts` | **Fold into `workflow`.** 335 alert strings are a property scan, not a traversal. A separate command implies a capability that is not there — and the eval showed a naive keyword match returns 12 workflows where 3 are correct. |
| `precedent` | **DROP.** It was modelled on the reference implementation, whose hub is `client` with 77 `engages` edges. **We have no client node type and no engagement data.** Nothing to traverse. |
| `coverage` | **Keep, and promote it.** The strongest command in the set. |

**Two of six survive unchanged, one is renamed, one is folded in, one is dropped
outright.**

---

## Proposed commands

### 1. `staffing` — who can teach X *(the first real question)*

**Tiers are never merged, and absence leads.**

```
/staffing Backend

Backend — 7 of 21 modules have teaching history.

TAUGHT (teaches — someone actually ran the class)
  Tilo Dickopp        Object Modeling         last taught 2026-08-14, 6 sessions
                      New Combined Schedule.xlsx!Backend r118
  …

DECLARED — NOT evidence anyone has taught
  hr_record (8)       from SME database!Master, an HR roster field
  self_declared (50)  from Instructors Directory!Responses, a Google Form
```

Rules:
- **If a domain has zero `teaches`, say so first**, before any name.
- Name the **source sheet** on every `teaches` line.
- Order: `teaches` → `hr_record` → `self_declared` → `self_declared + via_alias`.
- Prefer recent delivery; **never present a scheduled class as history** (13 edges are future-only).
- **Android and iOS: state they have no instructors** (out-of-corpus, owner-confirmed). Do not report them as a data gap.

**Honest scope:** works for **11 of 13** module-bearing domains. 30 of 42 domains have no module path at all.

### 2. `coverage` — what is missing *(the strongest command)*

Every number below is live:

- 14 of 42 programs with no domain
- 262 of 453 modules with no program
- 243 modules with no instructor
- 1,020 isolated records
- 71 unread worksheets / 4,572 rows
- 0 domains without an owner

**Must NOT report:** 92 workflows "missing an owner"; Android/iOS as unstaffed.

### 3. `workflow` — lookup by id or name

Returns steps, effort, alerts, tools, theme, source row. Always appends:
*ownership is domain-level; there is no owner for this workflow, and no path from
it to any person, program or module.*

### 4. `domain-owner` — replaces `owner`

Primary, secondary and delivery POC for a domain, with the cadence and the source row.

### 5. `setup` — unchanged

---

## The first question a teammate asks

**"Who can teach X?"** — and as of today the graph answers it for most domains,
which was not true one round ago. Before the class delivery log was found there
were 668 `teaches` edges, all Agentic AI; a `staffing` command would have been
confidently useless outside GenAI.

**It is answerable, with two honest caveats:** 1,889 edges reach 369 of 3,488
instructors, so most instructors still have no delivery history; and the answer
for a thin domain leans on `expert_in`, which is mostly form responses. That is
why the tiering is not presentation — **it is the command's correctness
requirement.**
