# PRE-CRAWL DECISIONS — taken before the first crawl, not after

**Six decisions. 2026-09-20.** Each one silently changes what the corpus *is*,
and each becomes expensive to reverse once 2,000 files carry it.

They are recorded here together because they share a property: **two of the six
had already been decided by code that nobody decided.** Pass 0 follows shortcuts
today. Provenance would carry a file owner today. Neither was a choice; both are
defaults that were harmless at 75 files in one owned folder and stop being
harmless the moment the corpus is other people's Drives.

D6 was added after D1–D5, when the follow-up measurements found a single folder
holding 2.73 GiB of learner uploads. It is left in its arrival order rather than
folded in, because *"the first pass did not know the scale"* is part of what
this document records.

Evidence throughout is [`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md).

| | decision | status |
|---|---|---|
| **D1** | No person extraction from slide content, at any confidence | **decided — never** |
| **D2** | Fork A: a search index with a graph over a known subset | **confirmed as the design** |
| **D3** | Shortcuts: resolve and report, do not follow | **decided — reverses current behaviour** |
| **D4** | File-owner metadata: store the domain, never the address | **decided** |
| **D5** | The `SMEs consent` folder: do not ingest | **decided — and it is a taxonomy limit, not a privacy preference** |
| **D6** | `(File responses)` folders: declared skip, reported | **decided — added after measurement, see §D6** |

---

## D1 · No person extraction from slide content. At any confidence, with any flag.

**Decided. This is not a threshold and must never become one.**

`CLAUDE.md` §4 says a cutoff may rank or warn but must not silently exclude, and
that rule exists because two cutoffs hid correct answers and six name-shape
filters dropped ~330 real people with a bias that tracked PhDs and South Asian
naming patterns. **That rule does not apply here, and the difference matters.**

§4 governs what to do when you have *real records* and are deciding which to
keep. This is the opposite situation: the question is whether a
`Name, Role, Company` tuple on a slide **is a record at all**. Ranking a
fabrication produces a ranked fabrication. `review: true` on a person who does
not exist produces a flagged person who does not exist. Every mechanism the
project has for handling uncertainty assumes the thing is real and the doubt is
about its *value*; here the doubt is about its *existence*.

### The measurement that settles it

Four decks, four instructor-shaped tuples, structurally identical:

| deck | tuple | what it is |
|---|---|---|
| `Live Class Slides: API Design Class` | Julie Wilkins, Senior Product Manager, Amazon, MBA Temple | **template placeholder** |
| `Mike: API Design` | Mike Dolt, Software Engineer, Orby | real instructor |
| `Fundamentals of Agentic AI` | Samwel Emmanuel (Sam) | real instructor |
| `Fundamentals of Agentic AI` | Hannah Chen, Data Scientist, Bay Area, Grammarly ex-Uber | **icebreaker example persona** |
| `Project & Program Management` | Senad Cimic, Senior Engineering Leader, Amazon | real instructor |

The only thing separating Julie Wilkins from Mike Dolt is a sentence in the same
text box reading *"Replace it with Instructor Name"* — and the only thing
separating Hannah Chen from Samwel Emmanuel is knowing that
*"pop into the chat: Your Name / Role / Company"* is an icebreaker and the
filled-in values are the example.

**And `Hannah Chen` is also a rated instructor in the registry's own P2
workbook** — Python for Machine Learning, 4.52, 41 responses. Whether that is
the same person is unknown and is exactly the point: a name match merges a
structured, dated, counted row with a decoration on a slide, and attaches
`Grammarly, ex-Uber` — which the structured row never asserts — to a real
person's node.

A cheaper version of the same failure: `TBA` is a literal cell value in P2's
`Cohort Strength` column and `Instructor: TBA` is the API Design title slide.
Both produce an instructor named TBA.

### Where instructor attribution comes from instead

**The poll workbooks.** P1 and P2 give instructor name against a dated class,
with `Overall Average`, `Responses`, `# Students Attended` and `% attendance`.
That is the evidence shape this graph already trusts — a row, in a file, on a
date, with a count — and it is exactly what `node_sources` was built to cite.

**With its N, always.** `STATE.md` §10: a 4.9 from 3 responses and a 4.6 from
200 are not comparable, and an average without its N is the same failure as a
count without its floor.

> **What this costs, stated plainly:** instructors who appear *only* on a deck
> and never in a poll workbook will be missing from the graph. That is a
> coverage gap of the §2a(i) kind — the most serious kind — and it is accepted
> here deliberately, because the alternative is not "more coverage" but
> "coverage of unknown truth value". A missing instructor is findable by the
> tripwire query. A fabricated one is not findable at all.

---

## D2 · Fork A is the design

**Confirmed.** A content search index answers *which files*; the graph answers
*who teaches this*, over the curated subset it already covers; the join is
explicit about where it stops.

The inventory did not merely fail to contradict this — it made fork B measurably
worse than `SCALE-PLAN.md` estimated. B's premise is that entity extraction over
unread files is a cheaper route to the same graph. §7 shows the two-thirds of
that premise that fails: the files contain fabricated people, and they contain
them in the same shape as the real ones.

The seam stays visible. Where a topic maps to a module, say so and traverse;
where it does not, say *"these files mention it; no module in the graph matches
that name"* and stop.

### The regression test fork A already has, found by measurement

**`Backend - API Design` is an empty folder.** It sits in
`Data + Mangement → Backend`, created 2023-02-28, never filled — one of six
empty folders in that branch (`REGISTRY-INVENTORY.md` §10, M2).

Its name is **the canonical example query for this entire project**: *"search
API design and get back the files about it."* A content index that ranks on
titles or paths returns it, confidently, at or near the top. It contains
nothing.

> **This is fork B failing, in one folder, already present in the corpus — and
> it was found by measuring rather than by reasoning about relevance.** Not a
> fabricated fact; something milder and harder to notice: a confident answer
> with nothing behind it.

**Keep it visible, and make it the test.** When the crawler or the index gains
any ranking that considers a path or a title, `Backend - API Design` is the
fixture: the assertion is that searching *"API design"* either does not return
it, or returns it explicitly marked as holding no files. **An empty folder that
scores well on the query the system was built for is exactly the regression
nobody would think to write by hand** — so it is written down here, before the
code exists, with the folder id:

```
Backend - API Design   1XrmskJnsHkIBUDCRDBdMk3q8vk5cqoxd/11MkOWXXkkFNTzKmmA9TytJ6G_FA4kM5P
```

It has a sibling, `Backend - Data Modeling`, also empty — so the test has a
second case for free.

---

## D3 · Shortcuts: resolve and report, do not follow

**This reverses what pass 0 does today, and today's behaviour was never
decided.**

`00_fetch_drive.py:263-273` resolves a shortcut to its target and, when the
target is a folder, **recurses into it**:

```python
if tmime == FOLDER_MIME:
    out += walk(service, target, prefix / name, seen, drive_id)
    continue
f = {**f, "id": target, "mimeType": tmime}
```

At 75 files inside one folder owned by the B2C account, a shortcut could only
ever point somewhere already controlled. That is why this has never mattered.

**Measured in the registry: 7 shortcuts among 75 files — roughly 1 in 10.** Four
are in `Sys3: Embedded Software Engineering` alone, including
`Embedded Software Engineering Curriculum` and
`Embedded SW - Slides and Documents`; one in `1-supervised-learning-i` points at
`ml-curriculum.xlsx`. **Their targets may sit outside all three registry
folders**, and at 2,000 files across other people's Drives the current behaviour
means *the corpus boundary is defined by what other people happen to link to*.

Neither obvious option is acceptable on its own:

- **Follow** (today): silently widens the corpus past what the registry
  declares. The registry stops being the scope.
- **Skip**: silently drops real curriculum files. `Sys3`'s shortcuts are named
  like the most important documents in that folder.

**Decision: resolve the shortcut's metadata, record it as a pointer, and fetch
the target only if the target is independently inside a declared registry
folder.** So:

- the graph can still say *"this folder links to a curriculum document"*, which
  is the fact the shortcut actually encodes;
- the boundary stays the registry's, not a third party's;
- **the loss is reported, never silent** — every run prints
  `N shortcuts pointed outside the declared tree`, named. That is the §5
  discipline: a count, not an enumeration, unless somebody must act on each one.

The honest limitation: a target that is genuinely part of the curriculum and
lives outside the registry will not be fetched. **That is a gap the registry
owner can close by adding the folder to the registry** — which is the right
place for a scope decision, and the reason the registry exists.

---

## D4 · File-owner metadata: store the domain, never the address

At 2,000 files from many Drives, *"who owns this file"* is genuinely useful
provenance — it is how you tell an IK-authored deck from an instructor's own
copy. It is also **contact data collected by the act of citing a file**, and
`REGISTRY-INVENTORY.md` §5(iv) is the finding: `sources.py` is an allow-list
over `(file, sheet, column)`, and a file owner is none of those three.

Measured: files in the registry are owned by **at least 14 accounts, four of
them personal free-mail addresses** belonging to external instructors and SMEs.
`CONTACT-DATA.md` declined instructor email for all three populations. An owner
address is an instructor email.

**Decision: record `owner_domain`, never `owner`.**

`interviewkickstart.com` / `gmail.com` / `microsoft.com` answers the question
that actually matters at scale — *was this authored inside the company or
outside it?* — and is not a personal identifier. Where a file genuinely needs
attributing to a person, that goes through `config/people.yaml` as a curated
slug with recorded evidence, the way **every** person in this graph is already
keyed. `CLAUDE.md` §2a: never key people on an identifier that is not stable,
unique and present; an email address supplied by Drive metadata is none of the
three for this purpose.

**Enforceable, and cheaply:** no provenance field may contain `@`. That is a
derived assertion over stored rows, not a list of field names to remember, so a
new provenance column is covered by default — the instance-8 fix applied in
advance.

---

## D5 · The `SMEs consent` folder: do not ingest

**And the reason is a limit in the model, not a preference about privacy.**

### What the folder contains

`Agentic AI SMEs- Consent for Website/Brochures` — named SMEs by region and
role, with per-person usage restrictions written inline:

> `NImita - Only KYP and Brochures`
> `Laksham Kumar - only KYP with old company`

And `India Agentic AI SMEs list for Websites` — the same population with
LinkedIn profile URLs and employer strings.

### Is a licence-bearing assertion expressible today? No.

The graph has exactly three mechanisms for restricting a fact, and a consent
licence is none of them:

| mechanism | what it keys on | granularity |
|---|---|---|
| `property_scopes` | **property name** | global — `avg_rating` is public for everyone or sensitive for everyone |
| `nodes.sensitive` + `np_can_see_sensitive()` | **the node**, boolean | visible to a role, or not |
| `node_sources.origin` | **how the fact was made** (`corpus` / `hand`) | per provenance row |

A consent licence keys on none of those. It keys on **the purpose the fact is
put to** — website, brochure, KYP — and:

> **Every control in this system constrains the PRODUCER of a fact or the ROLE
> of the person reading it. A licence constrains the PURPOSE of the reader. That
> axis does not exist in the model.**

And it cannot simply be added, because a purpose is not something the system can
observe. A query would have to *declare* its purpose, and a declared purpose is
unverifiable — which is precisely **A7B instance 7**: a constraint keyed on a
value the caller controls is the caller's opinion, stored, with a constraint's
reputation. Migration 0008's shared-account CHECK failed in exactly that shape
and had to be rebuilt in 0014 so the database derived the value itself. Nothing
can derive "what is this answer going to be used for".

### And the restrictions are finer than any per-node flag

`Laksham Kumar - only KYP with old company` does not restrict the person. It
restricts **which employer value may be shown, and to the superseded one**. So
the licence varies per person, per property, *and per value*. A boolean on the
node cannot carry it; neither can a scope on the property name.

### What it would cost to build

A new `licence` axis on provenance; purpose threaded through every API call and
every query; an unverifiable purpose declaration at the boundary; and a UI that
renders *"this may appear in a brochure but not on the website"* in an explorer
that has one audience. The realistic outcome is that the licence is stored as
free text and enforced nowhere — **which is D4's contact strip exactly**: a
stated control that does not fire, cited everywhere as the thing keeping the
data safe.

### The concrete failure if it is ingested anyway

The restriction is written **in the same cell as the name**. A person-name
extractor pointed at that sheet produces a `person` node labelled:

```
NImita - Only KYP and Brochures
```

And `CLAUDE.md` §4 forbids dropping it — long multi-part names are exactly the
shape whose filtering was found to be 84-for-a-PhD, 22-for-a-South-Asian-name
biased. So the correct behaviour under the existing rules is to **retain** it,
flagged. The graph acquires a person whose name is their own consent
restriction, and the flag says the name looks odd, not that the record is a
permissions row.

### The decision

**Do not ingest `SMEs consent`, and do not ingest the LinkedIn roster beside
it.** Not "ingest the names and drop the restrictions" — that is the worst
option available, because it takes a document whose entire function is to
*limit* publication and turns it into a source that *populates* a graph, with
the limit stripped. The two people who asked for less would be the two the
system treats identically to everyone else.

Excluded the same way payroll is: `taxonomy.yaml -> excluded.files`, path-keyed,
with the cost written down. **And the cost is real** — the consent register is
the only record of which SMEs may be named publicly at all, so anyone building a
brochure or a website page still needs it. It stays a document a human reads.
That is the honest answer: *some emptiness is the right answer*, which is one of
the four claims the landing page already makes.

---

## D6 · `(File responses)` folders: a declared skip, not a size limit

**Added after the fact.** D1–D5 were taken from the first inventory pass; this
one comes from the follow-up measurements in `REGISTRY-INVENTORY.md` §10, and it
is here because the first pass had no idea of the scale.

One such folder — the Agentic AI SWE capstone — holds **60+ files totalling 2.73
GiB, and the listing was not exhausted.** Largest single file 535 MiB. Twelve
files over 50 MiB. **Roughly 49× the entire current corpus on disk** — 2.73 GiB
against 57.4 MiB for all 74 files — in one directory, and there are at least
seven more in folder A alone.

Four properties make these a category rather than a big folder:

1. **Drive generates them**, with a predictable name ending `(File responses)`,
   so they are identifiable without a heuristic.
2. **They contain third-party uploads** — `.zip` source archives and `.mov`
   screen recordings — which the pipeline cannot parse and which teach the graph
   nothing about a module.
3. **Every filename carries a learner's personal name**, because the form
   appends it. The exposure is in the **path**, so anything recording a relative
   path as provenance records it. This is a sixth shape, and §5's list did not
   have it.
4. **They contain exact duplicates**, so a naive crawl pays twice.

**Decision: skip them by name, and report the skip.**

The distinction that matters is *why* they are skipped. A size cap would also
exclude this folder, and would be wrong: it would drop the 17.66 MB deck that is
genuinely curricular, keep small learner uploads, and give no account of either.
**A declared skip says what category was excluded and prints the count; a
threshold silently drops whatever happens to be large.** That is `CLAUDE.md` §4
in a new place — a cutoff that excludes a correct answer, where the correct
answer is a teaching deck.

---

## What is enforced, and what is only written here

Being explicit, because `A7B.md` instance 9 is the failure of assuming a
document is a control.

| decision | enforced by | or only recorded |
|---|---|---|
| D1 no people from slides | — | **recorded only.** There is no extractor yet; the test belongs with the code that would violate it |
| D2 fork A | — | **recorded only.** A design direction is not a constraint |
| D3 shortcuts | — | **recorded only, and it contradicts running code.** `00_fetch_drive.py` follows shortcuts today |
| D4 owner domain | — | **recorded only.** The `@`-in-provenance assertion is specified above and not yet written |
| D5 consent folder | `config/taxonomy.yaml -> excluded.files` — **but only once those paths are in the registry crawl's scope**, which does not exist yet | partly |
| D6 `(File responses)` | — | **recorded only.** The skip belongs in the crawler, with the report line beside it |

**Five of six are prose, and prose is what instance 9 is about.** They are
recorded now because the decisions are cheap today and expensive later — not
because writing them down makes them true. Each becomes a test when the code it
governs is written, and the code must not be written without it.

The one thing that *is* enforced today is narrower and worth naming precisely:
the registry sheet itself is excluded (`tests/test_export_map_is_exercised.py`),
and pass 0's export path is exercised against a fake service so that
`CLAUDE.md` §0's "the export map has never fired" stops being a claim nothing
would notice becoming false.
