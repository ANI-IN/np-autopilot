# CONTACT DATA — the D4 question, written before any extraction

**Status: recommended NO, 2026-09-18. Not built. Recorded rather than dropped,
because the reasoning is what makes the decision re-checkable if it is reopened.**

The trigger was small: the instructor panel could show a LinkedIn link. The data
exists — `01-corpus-inventory.md` counts **4,524 distinct LinkedIn URLs**
corpus-wide, in `Instructors Directory.xlsx`, `Data and Management.xlsx` and
`Resource Collection Mastersheet`. Nothing is in the graph because **D4 strips
contact fields (email / phone / LinkedIn / Discord) at extraction**.

> ### ⚠ CORRECTION, 2026-09-18 — D4's contact strip is not the control
>
> **Every document in this project describes D4's contact-field strip as the
> thing keeping email, phone, LinkedIn and Discord out of the graph. It is not,
> and it never was.**
>
> - `taxonomy.is_excluded_field` had **exactly one caller** —
>   `pipeline/validate.py` — and no extractor called it at all. Nothing stripped
>   anything "at extraction".
> - At that one call site it was matched against **derived property names**
>   (`pipeline_status`, `decline_rate`), while the 18 patterns describe
>   **spreadsheet headers** (`Personal email`, `LinkedIn Profile URL`). Two
>   namespaces that never meet, so the check could not fire. `validate.py`'s own
>   output has been printing `NOT EXERCISED: excluded-field` the whole time.
> - It matched by **equality**, so even in the right namespace `Student Email`,
>   `Phone Number`, `personal_email` and `Email (personal)` would all have
>   passed. Measured: 15 of 35 contact-shaped headers caught, **20 missed**.
>
> **What has actually kept contact data out is `pipeline/lib/sources.py`.**
> Extraction reads only declared `(file, sheet, column)` triples — **20 distinct
> columns, all name columns**, verified against the projected graph, which
> contains zero email addresses and zero LinkedIn URLs. That is an allow-list,
> it holds, and **it was chosen for coverage rather than for safety**.
>
> **The stated control fails open. The real one holds by accident.**
>
> Hardened 2026-09-18: matching is now normalised and substring-based rather
> than equality, and `validate.py` checks the raw `column` recorded in
> provenance — the namespace where a contact header would actually appear.
> The allow-list is now named as the control in
> `tests/test_exclusion_is_deny_by_default.py`. Full reasoning:
> `DECISIONS.md` §A.7b, "the control that never worked".


**This does not change the recommendation below** — it strengthens it. The
argument was never "a control already keeps this out"; it was that projecting
contact data for ~1,400 external people is a bad trade. Learning the control
was inert means the graph has been clean by the narrowness of extraction, not
by design, and widening extraction is exactly what was being proposed.


Adding the link reverses D4. This is what that reversal would actually mean.

---

## 1 · What it means at scale

It is not "add a link to a panel". It is projecting contact data for a
population, and the population is the problem:

| | |
|---|---|
| instructor nodes in the **public** graph | **1,915** |
| — of which `pipeline_status: roster` | **1,389** (73%) |
| — `hired` | 452 |
| — `lapsed` | 74 |
| instructor names readable during R18 | 3,817 |
| — of which **named hiring rejections** | **277** |
| — mid-pipeline candidates | 1,625 |

**73% of the instructors in this graph are roster entries, not people who teach
here.** They appear because a spreadsheet listed them. Projecting their contact
details creates a directory of several thousand external professionals, most of
whom have no relationship with Interview Kickstart beyond having once been on a
list — and a subset of whom were *rejected*.

D4 did not distinguish those groups because it stripped contact for all of them.
Any reversal has to draw a line D4 never needed to draw, and "instructor" as a
node type does not draw it: `roster`, `hired` and a rejected candidate are the
same type with different props.

## 2 · `acceler-presales-plugin` is the live case, and we are not the exception

`04-reference-review.md` §0 records it: a **public** repository, proprietary
licence, containing client names, deal sizes up to $537M, and **123 instructor
LinkedIn URLs**. Our own audit flagged it as third-party PII exposure, fetched
anonymously with no credential.

**What makes our situation different: less than it should, and the one
structural difference we had, we lost three weeks ago.**

- **R18.** This repository was world-readable for eight days. We are not a
  counterexample to acceler; we are the same failure mode with a shorter window
  and a remediation. Arguing "that could not happen here" is contradicted by the
  record.
- **`knowledge/graph.json` is committed and not gitignored.** Verified. The
  public half of the graph is *a file in the repository*. `graph-sensitive.json`
  is gitignored; `graph.json` is not. **Adding LinkedIn to the public graph
  reproduces acceler's shape exactly** — third-party contact data in a tracked
  file — and R18 is the proof that "the repo is private" is a property that can
  silently stop being true.

The honest difference is narrower: our sensitive half is withheld, our API is
behind Workspace sign-in and RLS, and we have an audit trail. None of those
protect a committed JSON file.

## 3 · D11 — the snapshot is unrevocable, so placement is forced

D11: *removing someone from the org stops future updates but does not remove the
graph snapshot already sitting in their local plugin cache.*

Contact data in a snapshot **outlives its deletion from the graph**. Revocation,
which `AUTH.md` describes as immediate and durable, stops being either.

So if this were ever done, the placement is not a choice: **API-only, never in
the snapshot.** That is consistent with §E.1 (cached snapshot + authenticated API
for anything sensitive) and it is the only defensible answer. It also removes
most of the convenience that motivated the request, since the plugin is where
people would want the link.

## 4 · Which role

Not `member`. `member` is every IK employee, and `STATE.md` holds the graph at
`member`-only while R18 is open.

`recruiting` is the only candidate — it already sees the hiring funnel. But note
what that implies: **the link would be visible for exactly the population where
it is least defensible** (candidates and rejections) and invisible for the one
where it is most ordinary (people who actually teach here). If the real need is
"contact an instructor we work with", `recruiting` is the wrong gate and
`member` is the unacceptable one.

Migration 0014's shared-account rule still applies: a shared mailbox cannot hold
`recruiting`, so this could never be read from the team account.

## 5 · Does the same argument admit email and phone?

D4 dropped all four together. Testing them separately:

- **Phone** — no. Direct personal contact channel, no analytic use.
- **Email** — no, and note the corpus holds **personal Gmail addresses**, not
  work addresses. That is someone's personal identity, not a professional one.
- **Discord** — no. Same as phone, plus it is a handle inside a community IK runs.
- **LinkedIn** — *weakly* distinguishable. It is a professional profile, usually
  self-published, and it is the only one of the four with a non-contact use:
  **identity resolution.**

**That distinction is about USE, not sensitivity**, and it points somewhere
better than projecting the URL. The genuine need LinkedIn could serve is telling
three different people called Karthika apart — and that need is met by using the
URL **as a key during extraction and never emitting it**. A disambiguation key
can be a salted hash, or simply consumed and discarded once the slug in
`config/people.yaml` is assigned.

So: if the argument for LinkedIn is contact, it admits email and phone and
should be refused with them. If the argument is disambiguation, **it does not
require projecting anything**, and D4 stands untouched.

One caveat against over-claiming "it's public anyway": `01-corpus-inventory.md`
records a **LinkedIn-enrichment sheet with member identifiers**. Enrichment data
is not a self-published profile, and treating it as one would be wrong on the
facts before it was wrong on the principle.

---

## Recommendation

**No. Do not extract or project LinkedIn, and leave D4 as it stands.**

Not because contact data is untouchable, but because the trade is bad on its own
terms: the benefit is a convenience link for a small number of signed-in staff,
and the cost is a directory of contact details for ~1,400 external people who
never asked to be in one, in a system whose public half is a committed file,
three weeks after that file was world-readable for eight days, with a snapshot
path that makes deletion ineffective.

**If disambiguation is the real requirement, say so and it can be built without
reversing anything** — LinkedIn as an extraction-time key, never an emitted
property. That is a small, contained change and it is the version I would
support.

**What would change this answer:** a stated need that only the projected URL can
meet, a population limited to people with a working relationship with IK
(`hired`, not `roster`), R18 closed, `graph.json` no longer tracked, and the
field API-only with `recruiting` gating. That is five conditions, and the fact
that it takes five is itself the finding.

---

## Revisited 2026-09-18 — LinkedIn approved in principle, scoped before building

The approval arrived as "LinkedIn", and that word covers three populations with
different answers. **Measured, not estimated:**

| | population | size | relationship to IK |
|---|---|---|---|
| **(1)** | NP staff in `people.yaml` | **20** | employees |
| **(2)** | instructors with ≥1 `teaches` edge | **497** (26% of 1,915) | have actually taught |
| **(3)** | all instructor nodes | **3,817** | includes 277 rejections, 1,625 mid-pipeline |

Of (2), **264 are also `cross_validated`** — cited in more than one file.

### (3) — No. Unchanged and not close.

277 named hiring rejections and 1,625 mid-pipeline candidates have no
relationship with IK and did not consent to a queryable profile. Nothing in the
original analysis moves.

### (1) — No, and the reason is not risk.

Twenty employees is the lowest-risk population here, and that is not an argument
for doing it. **No question has been stated that LinkedIn answers.** The graph
already carries `team`, `title` and `seniority` for these people, and they are
twenty colleagues the team can name. "Find their profile" is a directory lookup,
answered faster by Slack, and a knowledge graph that starts absorbing directory
lookups has stopped having a shape.

This is the Alert test applied to a property rather than a node type: data added
because it exists and is easy, not because a traversal needs it.

### (2) — The only arguable one, and my answer is still *not yet*. Here is the bind.

This is the population with a real question — *who is this instructor,
professionally* — and a real relationship. It is also, exactly,
**acceler's population**. `04-reference-review.md` §0 records them publishing
**123 instructor LinkedIn URLs** in a repository that turned out public, and our
own audit called it third-party PII exposure. **Population (2) is 497 — four
times acceler's, and the same kind.**

The bind is structural, not a matter of care:

- **Gate it safely** — `sensitive` scope, `recruiting`-only, never in the
  snapshot — and the people with the use case cannot see it. Staffing decisions
  are made by `member`. The gate that makes it defensible removes the reason for
  doing it.
- **Gate it usefully** — visible to `member` — and it lands in the **public half,
  which is `knowledge/graph.json`, a tracked file**. That is acceler's shape
  precisely, and R18 is the proof that "the repo is private" can stop being true
  without anyone noticing for eight days.

**D11 closes the third door.** Whatever reaches the plugin snapshot cannot be
withdrawn from a laptop later, so the snapshot is out regardless — which removes
the surface where the link would have been most convenient.

> **The blocker is not the data and not the population. It is that the public
> half of the graph is a tracked file.**

That single fact has now decided this question, the contact-fields question and
half of the payroll scoping. **Untracking `knowledge/graph.json` is the change
that would move all three**, and it is worth costing properly: what reads it
(tests, `gen_index.py`, the plugin snapshot), and what would have to change. If
that landed, (2) becomes an ordinary business-data question rather than a
structural one, and I would likely support it.

### What I would do instead, today

**LinkedIn as an extraction-time identity key that is never emitted.** It serves
the one need the URL genuinely meets — telling three people called Karthika
apart — reverses nothing, projects nothing, and is compatible with all three
populations because no row ever carries it. Small, contained, and I would support
it now.

### If (2) is approved anyway — how the reversal must be shaped

`tests/test_exclusion_is_deny_by_default.py::test_no_declared_extraction_column_is_a_contact_field`
asserts that **no column declared in `sources.py` may be a contact field**.
Declaring a LinkedIn column reverses that assertion by definition. It must
reverse **explicitly and by narrowing the rule**, never by exception:

1. **Not by deleting the test, and not by an exemption list.** An exemption list
   is the fail-open pattern the whole sweep was about — a new entry lands on the
   permissive side because somebody added it.
2. **The rule narrows to:** a contact column may be declared only if it appears
   in an explicit `contact_columns_approved` block naming **the approved
   population, the approver and the date**, and the property it produces is
   classified `sensitive` in `property_scopes`.
3. **The population restriction must be ENFORCED, not documented.** This is the
   part that would otherwise rot: a test asserting the emitted property appears
   on **no node outside the 497**. Without it, "instructors who have taught"
   becomes "all instructors" the first time somebody changes a join, and nothing
   would say so — which is how a 497-person decision silently becomes a
   3,817-person one.
4. **The two controls will contradict each other, and that is useful.**
   `excluded.field_patterns` denies `LinkedIn`; `sources.py` would declare it.
   `validate.py`'s `excluded-column` check fires on exactly that disagreement.
   **Resolve it deliberately** — do not let the allow-list silently win, because
   "the extractor declared it so it must be fine" is how the inert deny-list
   came to be trusted for months in the first place.

**Nothing extracted. Awaiting the population.**
