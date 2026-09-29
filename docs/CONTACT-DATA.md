# CONTACT DATA — the D4 question, written before any extraction

**Status: PARTIALLY REVERSED by the corpus owner, 2026-09-29. See §R at the end
— the original recommendation and its reasoning are left standing above it,
unedited, because a reversal is only re-checkable against what it reversed.**

**Original status: recommended NO, 2026-09-18. Not built. Recorded rather than
dropped, because the reasoning is what makes the decision re-checkable if it is
reopened.**

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

---

# §R · REVERSAL — the Resource Collection Mastersheet instructor tables

**Approved 2026-09-29. This reverses the 2026-09-18 recommendation for ONE
source and leaves it standing for every other.**

## What changed, and what did not

The 2026-09-18 decision said no to instructor contact data for all three
populations. The reasoning above is unchanged and still applies to the decks,
the documents, the file-owner metadata and the row-B content crawl.

What is approved is narrower: **the instructor tables in
`02-curriculum/Resource Collection Mastersheet (Software + System).xlsx`**, on
the `Full Stack Engineering`, `Frontend Engineering`, `Backend Engineering` and
`Test Engineering` tabs. Those tables have a `Contact #`, an `Email id` and a
`Linkedin` column, authored deliberately as a roster.

**Why this source and not the others.** Every population in the original
decision was reached by inference — a name on a slide, an address in a file's
owner metadata, a URL in a document's body. This is a column, in a table, with
a header, maintained as a roster. It is the evidence shape `node_sources` was
built to cite, and the one the extractor can be pointed at deliberately rather
than sweeping up.

## Conditions, each enforced by something that runs

| condition | enforced by |
|---|---|
| the three contact columns go ONLY into the sensitive half | they are declared `sensitive` in `taxonomy.yaml -> property_scopes`, and `project_graph.py::_refuse_unclassified_properties` REFUSES to project a sensitive property on a row without `sensitive: true`. They therefore live on a `sensitive: true` node, which `graphio.split_graph` writes to `graph-sensitive.json` — gitignored |
| never in `knowledge/graph.json` or anything git-tracked | `tests/test_no_contact_data_in_tracked_files.py` scans every tracked file for an address, a phone or a LinkedIn URL |
| admin-only when projected | the `recruiting` RLS path, unchanged — `nodes_recruiting_select` keys on `sensitive` |
| name, years, company, designation, past companies may be public | `mastersheet.split_instructor_row()` returns the two sets separately, and a test asserts no public field carries an `@` or a profile URL |
| the content-crawl redaction is untouched | it governs deck and document TEXT, which this is not. `redact.py` is unchanged by this reversal |
| `sources.py`'s allow-list is extended EXPLICITLY | the new columns are named there one at a time; `tests/test_exclusion_is_deny_by_default.py` still fails on an undeclared contact column |
| the payroll / contact CI guard still passes without blanket exemptions | `check_no_payroll_committed.py` is unchanged, and no blanket exemption is added for this source |

## What the parser found while implementing it

**One row in `Test Engineering` has an email and a LinkedIn URL pasted into the
NAME column, and no name at all.** A column map says where a field *should*
be; it does not say what a cell *contains*. So `split_instructor_row` scrubs
contact tokens out of public fields into the private side and flags the row,
and `is_unusable()` reports a row that scrubbing leaves nameless rather than
ingesting it or dropping it silently. Found by the test, not by reading.

## What this does NOT approve

- anything of this kind from decks, documents or unstructured text
- file-owner addresses (D4 stands: the owner is stored as a DOMAIN)
- the LinkedIn roster in `SMEs consent` (D5 stands, and it is a modelling
  limit rather than a privacy preference)
- publishing any of it — the sensitive half is not projected at all today, and
  `--scope full` still refuses

```
Approved by:            Animesh Kumar
Date:                   2026-09-29
Scope:                  Resource Collection Mastersheet instructor tables,
                        four domain tabs, that source only
Sensitive fields:       the three contact columns named in §R
Public fields:          name, years of experience, current company,
                        current designation, past tier-1 companies
```

---

# §L · LABEL CHECK — narrowed from "any @ or any http" to an address and a URL

**Approved by Animesh Kumar, 2026-09-29.** Implemented by
`db/migrations/0018_label_rejects_addresses_not_words.{up,down}.sql`.

## What the old check did, and why it had to change

`0002_graph_schema.up.sql` constrained every node label with:

```sql
check (label !~ '@' and lower(label) !~ 'http')
```

The name says what it is for — a label must not carry contact data. The test
was the *character* `@` and the *substring* `http`. Against the 75-file corpus
that cost nothing: no label in it contained either, so the check never fired
and never had to be right.

The row-B content graph has 5,811 nodes and **116 fail it**:

| what | count | example |
|---|---:|---|
| contains `http`, but it is the PROTOCOL | 104 | `HTTP Methods and Error Codes` |
| contains `http`, and it is a real URL | 10 | `Given: https://reqres.in/api/users/2` |
| contains `@`, and it is a MENTION | 2 | `Introduction to Cloud Testing: @Tim` |

By type: 44 `file`, 31 `content_topic`, 27 `live_class`, 12 `slide_deck`.

A guard in this shape does not fail safe. Under it the only ways to project the
content graph are to drop 116 real nodes or to turn the constraint off, and
under a deadline it is the second. That is `CLAUDE.md` §4: a threshold may rank
or warn; it may exclude only when the shape **cannot be the thing at all**.
`HTTP Methods and Error Codes` plainly can be a topic.

## The narrowing

| | before | after |
|---|---|---|
| address | any `@` | `local@domain.tld` |
| link | any `http` | `https?://` |

This is **narrower**, so it is recorded here as a decision rather than made as a
refactor — the same reason §R exists.

## Negative controls

Verified against PostgreSQL before the migration was written, and they are the
acceptance test for it. Still **rejected**:

- `someone@example.org` — email shape
- `profile https://example.com/in/x` — URL scheme. (A LinkedIn profile
  URL is the case that matters in practice; it is described rather than
  written out, because a document about keeping addresses out of the repo
  should not be the thing that puts one in.)
- `Given: https://reqres.in/api/users/2` — a real URL in a real topic

Now **accepted**:

- `HTTP Methods and Error Codes` — the protocol, not a link
- `Common HTTP response codes used with REST:` — same
- `Introduction to Cloud Testing: @Tim` — a mention, not an address
- `Availability, Reliability, Scalability & Replication: @SURUCHI` — same

Measured effect: content labels rejected **116 → 10**; main-graph labels
rejected **0 → 0**.

## The ten that really do carry a URL are cleaned, never dropped

Pass 7 strips the URL from the label and keeps the original in provenance
(`label_raw` and the source record). The node survives and the citation back to
the file is intact. `CLAUDE.md` §1: a failed join is visible, a deleted node is
not.

## Three places, one rule

The same test now lives in the DB constraint (0018), in `pipeline/validate.py`,
and in pass 7's label cleaner. The constraint is the one that cannot be bypassed
by a code path that forgets, which is why it is the one written down here.

## What this does NOT approve

- It does not permit an address anywhere else. `property_scopes`, the
  node-level sensitive split and §R are all unchanged.
- It does not permit a URL in a label. Ten labels are cleaned, not admitted.
- It says nothing about `@` in any field other than `nodes.label`. Migration
  0017 still forbids `@` in every provenance column, and that stays broad on
  purpose: provenance records a file owner as a DOMAIN, so an `@` there is
  always wrong.
