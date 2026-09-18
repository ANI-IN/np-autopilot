# "Ingest everything in the folder" — scoping the reversal, before extraction

**Status: NOT APPROVED, NOT BUILT. 2026-09-18.** Written to R6's standard — the
record must show a decision taken with **corrected facts in front of the person
approving it**, because D7 was decided against an exposure that turned out to be
understated. Nothing here is extracted, projected or fetched. The approval
fields at the end are deliberately blank.

---

## The scoping answer: "everything" should cover (1), not (2)

They are not one decision extended. They differ in **population**, **lawful
basis**, and **whether a question has been stated** — and only the third is a
matter of taste.

| | (1) Cost Analysis | (2) Contact fields |
|---|---|---|
| people | ~5,387 | ~8,001 emails / 8,074 phones / 4,524 LinkedIn, corpus-wide |
| who they are | IK workforce, current and former | **dominated by learners — customers** |
| relationship to IK | employment | purchase / enrolment |
| what it adds | pay, employment status, termination, last working day | an identifier, and in one sheet a behavioural profile |
| lawful basis available | contract / legitimate interest, existing HR regime | **new purpose; none established** |
| question it answers | "what does delivery cost" — stated | **none stated** |

**Measured, this repository, today:**

- `taxonomy.yaml → excluded.files` contains **exactly one entry**:
  `03-instructors/US Instructor Cost Analysis.xlsx`. So (1) is a one-line change
  and (2) is not — (2) is `excluded.field_patterns`, an 18-pattern list covering
  `learner_email`, `Email`, `Phone`, `Mobile`, `LinkedIn`, `Discord ID` and
  variants, applied to **every file**.
- The payroll file is **22 MB**, present in the local corpus folder, **absent
  from `.drive-cache/`** — pass 0's purge is holding.
- `Operational Metrics.xlsx` has **102 sheets**; four carry a contact column:
  **`Cohort Type Wise Coaching Raw D` — 12,985 rows carrying `learner_email`**,
  plus `MOS Zaps` (1,218) and two 49-row supplementary sheets. So within this one
  file ~14,300 rows carry an email, and 91% of them are learners.

---

## What (2) actually means, since you asked before confirming

**It is not "add contact fields to instructors". It is building a queryable
directory of ~8,000 people, most of whom are your customers, keyed to their
behaviour.**

The `Cohort Type Wise Coaching Raw D` sheet is the clearest case: `learner`,
`learner_email`, `Coach`, `Session_Title`, 12,985 rows. Projected, that is not a
contact field — it is **a profile**: who this person is, who coached them, what
they were coached on, when. A graph is the shape that makes exactly that
joinable, which is the point of a graph and the problem here.

**Three specific consequences:**

1. **`knowledge/graph.json` is committed and not gitignored.** Verified. The
   public half of the graph is a tracked file. Anything projected there lands in
   the repository by default — and **R18 is the proof that "the repo is private"
   can silently stop being true**, eight days, three weeks ago.
2. **D11 makes it unrevocable.** A snapshot in a local plugin cache survives
   deletion from the graph. Learner email in a snapshot cannot be recalled.
3. **No traversal is enabled.** Throughout this project a type earns its place by
   answering a question the graph could not otherwise answer. `learner_email`
   answers none: the learner is already identified by `learner`. An email is an
   identifier, not an analytic attribute. **This is the Alert mistake at PII
   scale** — nodes and properties added because the data exists, not because a
   question needs them.

### DPDP / GDPR, stated plainly and not as boilerplate

- **Purpose limitation.** Learner contact data was collected to deliver a course.
  Loading it into an internal knowledge graph for staff querying is a **new
  purpose**, not a continuation of the old one. DPDP §6 notice-and-consent is
  tied to the purpose given; GDPR Art 5(1)(b) is the same rule.
- **Data minimisation** (GDPR 5(1)(c)) cuts directly against "no exceptions" as a
  design principle. "Everything" is the opposite test.
- **Learners are Data Principals and IK is the Data Fiduciary.** Employment data
  about IK's own staff sits in a regime that already exists. Customer data
  entering a new system does not.
- **Erasure.** A DPDP/GDPR erasure request must reach every copy. D11 says a
  snapshot copy is unreachable. That is not a compliance gap to manage; it is a
  commitment the architecture cannot currently honour.

**My recommendation on (2): no.** Not "later", not "gated" — the population is
wrong and no question has been stated. If a specific need exists, name the
question and it can almost certainly be met with the pseudonymous `learner` key
that is already extracted, without an email ever entering the graph.

---

## If you confirm (1) only — what the record must contain

Reversing (1) is defensible. It is your workforce, your data, and "what does
delivery actually cost" is a real question the graph cannot answer today. But
**it reverses more than D4.**

### It reopens R17, which was not about extraction

R17 is titled *"an excluded file must never reach the disk, not merely never
reach the graph."* The exclusion was previously enforced at pass 1 — two passes
after pass 0 had already downloaded the bytes — and **23 MB of HR payroll data
sat in `.drive-cache/`** until pass 0 was changed to purge it. That purge is
currently holding.

So reversing (1) means the file returns to disk on every run, on a laptop, inside
a directory protected by **one line** (`.gitignore:87 03-instructors/`). R18 is
the precedent for a one-line protection silently ceasing to hold.

`tests/test_fetch_time_exclusion.py` also records that pass 0 and pass 1 both read
the same `taxonomy.yaml` list, so they are **two layers against a bug in one
pass, not two independent layers** (§A.7a). Removing the entry defeats both at
once.

### Conditions I would require before extraction

1. **`scope: sensitive` only.** Never projected into the public half. ~~Today
   `project_graph.py --scope full` is refused while R18 is open.~~ **That
   sentence was wrong** — R18 appears nowhere in `project_graph.py`, and it is
   the same stale claim later named as §A.7b instance 9. Corrected below under
   "Condition 1 is not a fifth condition": this is the mechanism the other four
   rest on, and it is now enforced by `property_scopes` rather than promised.
2. **`recruiting` role only, never `member`.** Migration 0008/0014 already
   prevents a shared account holding `recruiting`, so it can never be read from
   the team mailbox.
3. **Never in the plugin snapshot.** API-only, per D11 and §E.1.
4. **A stated retention position for the cached copy** — R17's question. If the
   bytes must land on disk, say where, for how long, and what deletes them.
5. **Field-level minimisation even within the file.** "The file is in" should not
   mean every column is. Pay rate answers the cost question; *termination reason*
   and *last working day* do not, and they are the most sensitive columns present.

---

## Sequencing note — this is the fourth widening request

Recorded because the previous one asked me to watch for exactly this.

Payroll → everything in the folder → contact fields → now both together. Each was
argued on utility, which is the right test for a feature and the wrong one for a
scope decision: utility is monotonic in data, so "would this be useful?" always
answers yes and the boundary only ever moves one way.

**What makes this instance different from the previous three is that the
mechanism is now visible:** the default placement is the permissive one. A new
field lands in `graph.json` — a tracked file — unless someone actively marks it
sensitive. So widening defaults toward exposure and requires an act of memory not
to. That is the §A.7b permissive-reading failure, applied to policy.

**The mitigation is cheap and I would take it before either reversal:** make a
newly projected field require an explicit `scope` classification before it
projects, the way a taxonomy type already requires a declaration. Widening stays
possible; it stops being the default.

---

## On record before approval, regardless of what comes back

Added 2026-09-18 after enumerating the file's actual columns. Both are the kind
of thing that only looks obvious afterwards.

### (1) contains a slice of (2)

**`US Instructor Cost Analysis.xlsx` carries 4,697 email occurrences**, across
`Email`, `Personal email`, `Work email` and `Email id` columns. Contact data for
the same 5,387 people is *inside the file being approved*.

So **approving (1) without field-level minimisation partially reverses (2)** —
the decision explicitly declined on the grounds that an email is an identifier,
not an analytic attribute, and that no question had been named for it. Nothing
about approving a payroll file announces that it also carries the thing you just
refused. Minimisation is not an optimisation here; it is what keeps the two
decisions from collapsing into one.

The request was made as *"instructor pay rates"*. The file is payroll disputes
against named people (`Amount Overpaid`, `Amount should have been paid`,
`Overpaid Hours`), sick leave, legal names, legal entity, compensation grade job
code, Rippling identifiers from a second HR system, and those 4,697 emails.
**Nobody approved that description, because nobody had it** — which is precisely
the condition R6 exists to prevent, and the reason this section is here rather
than in a commit message.

### Condition 1 is not a fifth condition

`nodes_recruiting_select` keys on `sensitive`. A row that is not marked sensitive
is readable by every `member`, whatever anyone intended. So **"sensitive scope
only" is the mechanism that makes "recruiting only" true** — declining it does
not leave four conditions standing, it silently voids one of the four.

Two corrections to how condition 1 was originally written, for the record: it
said *"blocked in any case until R18 closes"*, which was the same stale R18 claim
later named as §A.7b instance 9 — **in this document**. And it is no longer a
promise: `config/taxonomy.yaml -> property_scopes` refuses a `sensitive`
property on a public row at projection time.

### Accepted scope and conditions, pending the approval block

- **Scope: (1) only.** (2) declined; reasoning kept in `CONTACT-DATA.md` and above.
- **All five conditions accepted**, condition 1 included.
- **Field-level minimisation, as agreed.** KEEP: the 18 labour codes, `Base Rate`,
  `Hourly Rate`, `Hours Amount`, and a person key. DROP: `LWD`,
  `Employement Status`, every email column, `Amount Overpaid` /
  `Amount should have been paid` / `Overpaid Hours`, `SICK`, `Legal last name`,
  `Legal entity name`, `Compensation grade job code`, `Badge Number`,
  `Rippling profile number`. If someone later needs `LWD` or employment status,
  they name the question.

### What replaces R17

R17's rule was *"an excluded file must never reach the disk, not merely never
reach the graph"*. This reversal retires it: the file reaches the cache. What
stops it reaching git is no longer one layer.

- **Before:** `.gitignore:87 03-instructors/` and `taxonomy.yaml ->
  excluded.files`. Both keyed on the PATH, and pass 0 and pass 1 read the same
  list — **one layer wearing two hats** (§A.7a). A rename, a move, a `git add -f`
  or a copy into another directory walks past all of it.
- **Now, additionally:** `pipeline/check_no_payroll_committed.py`, keyed on
  **content**. It reads neither `.gitignore` nor `taxonomy.yaml` and does not
  know the file's name, so it fires on the workbook renamed, moved, or pasted
  into a new file. Run in CI as its own job; usable as a pre-commit hook.
- **That is two layers, and they fail independently** — which is the property the
  previous pair did not have.

---

## Approval — to be completed by the approver, not by me

R6 requires the record to show who decided, when, and against which facts.

```
Scope approved      :  (1) only  /  (1) and (2)  /  neither
Approved by         :
Date                :
Facts reviewed      : this document, revision of 2026-09-18
Conditions accepted :  1  2  3  4  5   (list any declined, with reason)
```

**Nothing is extracted, fetched or projected until this block is filled in.**
