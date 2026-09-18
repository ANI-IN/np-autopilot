# CONTACT DATA — the D4 question, written before any extraction

**Status: recommended NO, 2026-09-18. Not built. Recorded rather than dropped,
because the reasoning is what makes the decision re-checkable if it is reopened.**

The trigger was small: the instructor panel could show a LinkedIn link. The data
exists — `01-corpus-inventory.md` counts **4,524 distinct LinkedIn URLs**
corpus-wide, in `Instructors Directory.xlsx`, `Data and Management.xlsx` and
`Resource Collection Mastersheet`. Nothing is in the graph because **D4 strips
contact fields (email / phone / LinkedIn / Discord) at extraction**.

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
