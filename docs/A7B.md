# A.7b — silence that looks like success

**The most valuable thing this project produced, and the part most likely to
outlive it.** Extracted from `DECISIONS.md` §A.7b so it can be read on its own;
that section now points here.

Ten instances of one failure, a named observation about which rules get tested,
and one open question. None of the ten was found by looking for it. Every one
was found by a test that existed for another reason, by a real person being
refused, or by someone asking a question nobody had asked before.

---

## The three questions, in the order they get asked

Most of what follows is history. These are the part you use.

### 1 · Is this guard's scope DERIVED from the rule, or written down beside it?

*(Instance 8.)* A written-down scope is a second source of truth about a rule's
reach, and it rots like any other duplicated fact — silently, and in the
direction of passing. `test_taxonomy_single_source` read four directories while
its rule said *anywhere*, and was green for months with five literals sitting in
`web/lib/`.

**Ask it of:** every ignore file, every path list, every `SKIP_DIRS`, every
allow-list. The answer "we list them" is the finding.

### 2 · What in the PROGRAM would fail if this documented constraint stopped being true?

*(Instance 9.)* If the answer is nothing, the document is describing an
intention, not a control — and the next person will trust it as a control.
`STATE.md` said `--scope full` was blocked by R18; R18 appeared nowhere in
`project_graph.py`. The program's own blocker was a hardcoded claim that had
been false since the policy it described was built.

**Ask it of:** every "never", "must" and "always" in `CLAUDE.md`, `STATE.md`,
`AUTH.md` and the risk register. A sweep of 24 such constraints found **five
with no test**.

### 3 · When a guarantee HOLDS, do we know which mechanism holds it — and is it the one we think?

*(The control that never worked.)* The hardest of the three, because nothing is
failing. D4's contact strip was cited everywhere as the thing keeping email and
LinkedIn out of the graph. It had one caller, matched two namespaces that never
meet, and could not fire. What actually held was `sources.py`'s narrow column
list — **chosen for coverage, not for safety**, and therefore removable by an
improvement that looks like progress.

**Ask it of:** anything you are about to widen, speed up, or generalise. A
guarantee can be true for a reason nobody wrote down.

---

## The observation that predicts where to look

> **The constraints with the best stories behind them are the least likely to
> have a test, because the story feels like the safeguard.**

Of the five documented constraints found with no enforcement, **four were in
`CLAUDE.md` or `STATE.md`** — the documents most read and least executable — and
**three of those four encoded a bug that had already happened**. A rule that
arrives with a war story gets written vividly, retold, and cited; the vividness
stands in for enforcement. The dull invariant nobody has a bug to attach to is
the one somebody bothered to put in code, because nothing else would have held
it.

The uncomfortable corollary: **`CLAUDE.md` is the most-read document in this
project and the least connected to anything that runs.** Every rule in it should
be read as *"this has a test"* or *"this is a hope"*, and until the sweep of
2026-09-18 nobody had asked which.

---

## How the ten divide

| | shape | instances |
|---|---|---|
| **Returns nothing** | absence and success are the same value | 1–6 |
| **Enforces a lie** | the check runs, correctly, over a value that is false | 7 |
| **Scope narrower than the rule** | enforces correctly over a subset, reports as though over everything | 8 |
| **Lives in prose, not the program** | a constraint no code implements, or one hardcoded and never re-checked | 9 |
| **Never worked at all** | the stated control is inert; something else holds the guarantee by coincidence | 10 |

---

> **A guard that fails by returning "nothing happened" is indistinguishable
> from the absence it was written to detect.**

Nine instances now, and they are not nine bugs — they are one bug wearing
nine costumes. Six fail by returning nothing; the seventh enforces a lie; the
eighth enforces correctly over a scope smaller than the rule it claims. Naming it is worth more than the individual fixes, because every one
of them was caught by a test that existed for another reason entirely. None was
caught by the guard itself, by review, or by reading the code.

| # | The guard | How it failed | Why nobody saw it |
|---|---|---|---|
| 1 | `refresh.py`'s version-bump decision | `--no-bump` WROTE the lock, so the next run compared the graph against a lock that already described it | "No bump needed" and "a bump was silently swallowed" print the same line |
| 2 | The `origin: hand` provenance test | An unconditional INFO made the category always "exercised" | A green category and a category that ran zero assertions are the same green |
| 3 | The excluded-file check | Same shape, same unconditional INFO | Same |
| 4 | The `BEFORE DELETE` trigger | Returned `NEW`, which is NULL on DELETE, cancelling every delete | `rowcount 0` for "cancelled" and for "the row was not there" |
| 5 | `people_aliases` write grants (§A.7a, closed in 0012) | Grant with no service trigger: a member's write returned rowcount 0 | RLS "held" — but silently, and one permissive policy away from real |
| 6 | `grant_access.py`'s `hd` corroboration | Read `identity_data ->> 'hd'`; GoTrue nests non-standard claims under `custom_claims`, so it was always NULL | "This account is not a Workspace identity" and "I looked in the wrong place" printed the same refusal |

Instance 4 was found because a *teardown* could not clean up. Instance 5 was
found because a test was rewritten to derive its rule rather than list names.
Instance 6 was found because a **real person was refused** — it would have
refused every legitimate account, and no test caught it because every auth test
built its own rows and none had ever seen one GoTrue wrote. Not one of the three
was found by looking for this pattern.

**What would catch the sixth.** Three rules, in decreasing order of how much
they actually buy:

1. **Every guard needs a negative control.** A test that breaks the thing the
   guard watches and asserts the guard turns RED. Not once, informally, during
   development — committed, beside the positive case. Instances 2 and 3 had
   passing tests the whole time. `tests/test_curation_notes.py` is written this
   way deliberately: delete a note, corrupt a note, drop a row, change a field,
   add a stray row — five mutations, five assertions that the check fails.
   Migration 0012 was verified the same way, by rolling it back and watching the
   test go red.

2. **A guard must not take its evidence from the thing it is checking.** This
   caught a sixth today, before it shipped. The comment round-trip asks "did the
   reasoning survive?" and answers it by comparing `extract_notes(file)` against
   the rendered export — but both sides run `extract_notes`. Version 1 of that
   function handled only comment blocks *before* a row, so it never saw the
   Karthika merge guard, and the check would have reported **PRESERVED**: it
   compared what it extracted to what it rendered, and agreed with itself about
   a note neither side had. The closed loop is broken by
   `test_every_comment_line_in_the_sources_is_accounted_for`, which counts `#`
   lines in the raw file — evidence from outside the function — and fails if any
   is unaccounted for.

3. **Make absence and success textually distinguishable at the point they
   occur.** `rowcount 0` is the recurring culprit because it is the same value
   for "refused", "cancelled", "not found" and "already in that state". Where
   the distinction matters, raise instead of returning: `curation_service` reads
   the row back and says *"is at version 7, not 5 — YOUR WRITE DID NOT HAPPEN"*,
   and migration 0006 revoked the grants so that an unauthorised write raises
   rather than quietly affecting nothing.

**What none of this closes.** Rule 1 is only as good as the mutations someone
thought to write; a guard can still be blind to a failure mode nobody imagined.
The honest position is that this pattern is now *cheaper to find* — it has a
name, a table of precedents, and a test-writing habit attached — not that it
has been eliminated.

---

#### The seventh is a different animal: a constraint that enforced a lie

The six above all fail by **returning nothing**. This one did not. It ran, it
was correct, and it was worthless:

> **A CHECK keyed on a value the caller controls is not a constraint; it's the
> caller's opinion, stored, with a constraint's reputation.**

Migration 0008 added:

```sql
check (not (is_shared_account and role in ('recruiting', 'admin')))
```

The shared team mailbox signed in, and
`grant_access.py grant … --role recruiting` **succeeded**. Both layers were
inert at once, for a single reason:

- The script consulted `NP_SHARED_ACCOUNTS`. That variable was set in Vercel and
  never in the laptop environment the script runs in. An empty list means no
  account is shared, so there was nothing to refuse.
- The CHECK is keyed on `is_shared_account` — and the script had just written
  `false`. **The constraint evaluated perfectly over a value that was already a
  lie.**

The A.7b trigger is in the first bullet: an unset variable made *"no shared
accounts exist"* indistinguishable from *"I was never told which accounts are
shared"*, and the permissive reading won. But the second bullet is the new part
and the more dangerous one, because a passing constraint is *evidence* — it is
the thing you point at when asked whether the rule is enforced.

**Migration 0014** moves the list into a `shared_accounts` table and DERIVES the
flag with a `before insert or update` trigger that overwrites whatever the
caller passes. The database now computes the value its own constraint depends
on. Tests run with `NP_SHARED_ACCOUNTS` explicitly unset — the condition that
produced the failure — and include the positive control that a normal account is
*not* flagged, so a trigger that flagged everyone could not pass.

#### The question this forces, and a first pass at answering it

**Which other constraints in this schema validate a value the application
supplies, rather than one the database derives?**

Surveyed across all 29 CHECK constraints in `public`. Most are **shape** checks
— `id_is_sha256`, `label_nonempty`, `local_part_has_no_domain` — and those are
fine: they constrain the value itself, and there is nothing else they could
check. The exposed class is **conditional** checks of the form *"if X then Y"*,
where `X` is a discriminator the application supplies. Get `X` wrong and the
rule silently does not apply.

| Table | Constraint(s) | Discriminator the app supplies |
|---|---|---|
| `node_sources` | `corpus_names_a_file`, `hand_has_evidence`, `hand_names_no_file` | **`origin`** |
| `domain_aliases` | `confirmed_names_a_confirmer`, `confirmed_needs_a_domain` | `confirmed` |
| `workflow_owners` | `confirmed_has_an_owner` | `confirmed` |
| `people` | `np_has_title_and_seniority`, `non_np_has_neither` | `team` |
| `curation_audit` | `delete_has_before`, `insert_has_after`, `update_has_both` | `action` |
| `profiles` | `shared_accounts_stay_member` | `is_shared_account` — **closed by 0014** |

**`node_sources.origin` is the one that matters**, because it guards this
project's most load-bearing prohibition: *a hand-entered fact must never be
presentable as though a scan produced it* (§A.5, `CLAUDE.md`). And `origin` is
not derivable — only the producer knows how a row was made.

What IS available is to constrain the pairing in **both** directions, so a
mislabel contradicts itself. Three of the four implications exist:

```
corpus -> file IS NOT NULL        ✓ corpus_names_a_file
hand   -> file IS NULL            ✓ hand_names_no_file
hand   -> evidence IS NOT NULL    ✓ hand_has_evidence
corpus -> evidence IS NULL        ✗ MISSING
```

So a hand-entered fact mislabelled `origin: corpus`, carrying its evidence
string, passes every constraint today. Measured: **0 of 30,628 corpus rows carry
evidence**, so the invariant holds in the data — it is simply not enforced. The
missing half is one line:

```sql
alter table node_sources add constraint corpus_carries_no_evidence
    check (origin <> 'corpus' or evidence is null);
```

Recorded rather than applied, because it is a schema change and belongs in a
migration with its own verification pass. **The general rule it illustrates:
where a constraint depends on a discriminator, constrain the discriminator's
other implications too — a lie that has to stay consistent across four columns
is much harder to tell by accident than one stored in a single boolean.**

#### The eighth is a third animal: a guard whose SCOPE is narrower than its rule

Instances 1–6 fail by returning nothing. The seventh runs correctly over a value
that is a lie. This one is neither:

> **It enforces correctly, over a subset, and reports as though it had covered
> everything. The check is right. The question it was asked is smaller than the
> question everyone believes it answered.**

`tests/test_taxonomy_single_source.py` enforces the rule in `CLAUDE.md`:
*"a grep test fails the build on any type string written as a literal
elsewhere."* Its scope was:

```python
SEARCH_GLOBS = ("pipeline/**/*.py", "tests/**/*.py", "commands/**/*.md", "skills/**/*.md")
```

`web/` and `api/` are not in that list. The rule says *anywhere*; the guard read
four directories. It was green the whole time **five literals sat in
`web/lib/`**, and it only ever fired because a sixth was written into a file
that happened to be inside the list. Had that literal been written one directory
over, nothing would have objected.

**Why this is worth a separate name.** The first six are found by asking *"could
this check pass while doing nothing?"* — and this one does something, visibly,
on every run. The seventh is found by asking *"does the value this depends on
mean what it says?"* — and here every value is honest. The question that finds
this one is different:

> **Is the set of things this check looks at derived from the rule, or written
> down beside it?**

A written-down scope is a second source of truth about the rule's reach, and it
rots exactly like any other duplicated fact — silently, and in the direction of
passing.

**The fix is the same shape as §A.7a's.** Do not list what to check; derive it,
and state the exclusions instead. The scan is now every `.py` in the repository
minus a `NOT_SOURCE` deny-list, so a new directory is covered by **default** and
losing coverage requires adding a name on purpose. `test_the_scan_actually_
reaches_the_shipped_web_code` is the negative control: a test that the scan
*finds* things was never the gap — it found plenty — so the control asserts it
**reaches the directories whose absence was the bug**.

Where an exemption is genuinely right — the eval harness asserts expected
*answers* that happen to equal vocabulary values, and resolving those through
`taxonomy.vocabulary()` would make the eval agree with the taxonomy instead of
with a known-correct answer — it is written inline as
`# taxonomy-literal-ok: <reason>`, and a marker with no reason is itself an
offence. An exemption with no cost is a hole.

##### The survey this forces: which other checks write their scope down?

Every path-scoped check in the repository, and whether it would catch a
violation in `web/` or `api/`:

| Check | Scope as written | Reaches `web/` · `api/`? | Verdict |
|---|---|---|---|
| `test_taxonomy_single_source` | 4 globs → **derived deny-list** | no · no → **yes · yes** | **was instance 8 — fixed** |
| `test_no_api_route_connects_as_owner_or_service_role` | `web/` only | yes · **no** | **was instance 8 — fixed.** `STATE.md` cites this as proof no API route holds the service-role key; it had never opened the eleven files in `api/` |
| `test_every_api_route_goes_through_the_guard_or_is_the_session_route` | `web/api/` | **neither — that directory does not exist** | **INERT. Scans zero files** and has since the WSGI consolidation moved routes to `api/`. Worse than instance 8: not a narrow scope, an empty one. It also tests for `serve(`, the per-file shell `api/index.py` deleted — so re-pointing it at `api/` would make it pass on `index.py`'s *docstring*, which mentions `serve(...)` while describing its removal. That is the "USES, not MENTIONS" trap its own sibling test was written to avoid. **Needs a rewrite against the current architecture, not a new path.** |
| `test_nothing_the_browser_can_fetch_mentions_a_secret` | `public/` | n/a | correct — `public/` *is* the rule's subject |
| `test_build_log_isolation` | `pipeline/` | n/a | correct — only pipeline passes write build logs |
| `test_pipeline_docs` | `pipeline/` | n/a | correct — the rule is about pipeline scripts |
| `test_no_root_json_is_silently_ignored` | `REPO.glob("*.json")` | n/a | correct — the rule is explicitly about **root** `.json` |

**Three of seven had a scope that did not match their rule; two were fixed here
and one needs its own change.** The four that are correct share a property worth
copying: their scope *is* the rule's subject, so there is no gap to drift.

#### The ninth: a constraint that lives in the prose and not in the program

Found 2026-09-18, re-checking whether `--scope full` was still blocked.

`STATE.md` said the blocker was **R18**. The program said the blocker was a
missing **`recruiting` RLS path**. Measured, both were false:

| claim | where | truth |
|---|---|---|
| "blocked while R18 is open" | `STATE.md`, prose | R18 appears nowhere in `project_graph.py`. The program never implemented it |
| "the recruiting RLS path does not exist yet" | `project_graph.py`, a hardcoded `sys.exit` | `nodes_recruiting_select` and `np_can_see_sensitive()` both exist, and `edges` / `node_sources` gate on node visibility. The path is complete |

Two different failures that arrive at the same place:

> **A constraint stated in documentation that the program does not implement,
> and a constraint hardcoded in the program that nobody re-checked. In both, the
> claim outlived the condition that made it true — and in both, the claim is
> what a reader trusts.**

**Why this is not instance 7.** Seven is a check that RUNS, correctly, over a
value that is a lie. This is a check that never existed (the prose), and one that
exists but evaluates nothing (the hardcode). Nothing is computed in either case,
so there is nothing that could notice the world had changed.

**And why it is worse than being merely stale.** A hardcoded refusal is wrong in
whichever direction the world moves. It blocked correct work here. Had the policy
been **dropped** instead of added, the same line would have waved the projection
through — because it asserts a conclusion rather than checking one, it cannot be
wrong in a safe direction.

**The fix is the rule already established in A.7a and instance 8: derive, do not
assert.** `_missing_recruiting_path()` now queries `pg_policies` and `pg_proc`
and refuses on what is actually absent, so it stops refusing when the path is
built and starts again if someone drops it. The remaining refusal is honest about
what it is — a **decision** that has not been taken, pointing at
`docs/INGEST-SCOPE-REVERSAL.md`, whose approval block is blank.

**The question this adds to the list:** for any constraint a document asserts,
*what in the program would fail if it stopped being true?* If the answer is
nothing, the document is describing an intention, not a control — and it should
say so, or the control should be built.

#### The story is not the test

Instance 9 asked: *for every constraint these documents assert, what in the
program would fail if it stopped being true?* Run as a sweep over `STATE.md`,
`DECISIONS.md`, `AUTH.md` and `07-risks.md` — 113 constraint-shaped statements,
54 naming a concrete artefact, **24 distinct system constraints, of which five
had no test**.

The five are not a random five, and that is the observation:

| unenforced constraint | where | had a story |
|---|---|---|
| workbooks open `read_only=True` | `CLAUDE.md` §1 | the corpus is a live Drive mirror |
| no pipeline script shadows a stdlib module | `CLAUDE.md` §3 | **`inspect.py` cost a full run** |
| employee ids are evidence, never the key | `CLAUDE.md` §2a | **`IK-294` maps to two people** |
| `profiles.domain_is_ik` still exists | `AUTH.md` | the domain rule lives in the database |
| `pipeline/` never runs on Vercel | `STATE.md` | — |

> **The constraints with the best stories behind them were the least likely to
> have a test, because the story feels like the safeguard.**

Four of the five sit in `CLAUDE.md` or `STATE.md` — the documents most read and
least executable — and three of those four encode a bug that **already
happened**. A rule that arrived with a war story gets written down vividly,
retold, and cited; and the vividness is what stands in for enforcement. Nobody
writes a test for the thing everybody remembers.

**Why this is not instance 9 restated.** Nine is about a single claim outliving
its condition. This is about *which* claims that happens to: it predicts where to
look. The rule with no story — a dull invariant nobody has a bug to attach to —
is the one somebody bothered to assert in code, because nothing else would have
held it. The memorable rule is load-bearing in prose and unsupported in fact.

**The corollary, and it is uncomfortable:** `CLAUDE.md` is the most-read document
in this project and the least connected to anything that runs. Every rule in it
should be read as *"this has a test"* or *"this is a hope"*, and until this sweep
nobody had asked which. The five are now in
`tests/test_documented_constraints_are_enforced.py` — and the vercelignore one
failed immediately, because five scripts added since it was written were being
uploaded to Vercel. That list was hand-written, so a new file was included by
default: instance 8 again, in a third place.

#### The control that never worked, and the substitute that worked by coincidence

The sharpest case in this catalogue, because all three parts failed in different
ways and the sum reported success.

**The stated control did not exist.** D4 says *"strip instructor contact fields
(email/phone/LinkedIn/Discord) at extraction"*. Every document repeats it.
`taxonomy.is_excluded_field` had **exactly one caller** — `validate.py` — and no
extractor called it at all. Nothing stripped anything at extraction, ever.

**At its one call site it could not fire.** It matched the 18 patterns, which are
spreadsheet HEADERS (`Personal email`, `LinkedIn Profile URL`), against node
**property keys**, which are derived names (`pipeline_status`, `decline_rate`).
Two namespaces that never meet. And it compared by equality, so even in the right
namespace `Student Email`, `Phone Number`, `personal_email` and
`Email (personal)` all passed. Measured across every first-row header in the
corpus: **15 of 35 contact-shaped headers caught, 20 missed.**

**The machine had been saying so.** `validate.py` prints a NOT EXERCISED list —
built for exactly this, after instances 2 and 3 — and it has been naming
`excluded-field` on every run. The output was correct and nobody read it. A
report that says a check never ran is only a control if somebody looks.

**Something else was holding.** `pipeline/lib/sources.py` declares extraction as
`(file, sheet, column)` triples. Only **20 distinct columns have ever been read**,
all of them name columns, and the projected graph contains **zero** email
addresses and zero LinkedIn URLs. That is a real allow-list and it is the reason
the graph is clean — **and it was written for coverage, not for safety.** Nobody
chose it as a privacy control; it is one by side effect.

> **A stated control that fails open, a real control that holds by accident, and
> nothing in the system relating the two.**

**And the part that should stop a reader.** `CLAUDE.md` §2 treats narrow coverage
as a defect: 25 of 75 files unread, counts are floors, and reading the rest is on
the roadmap as progress. **That work removes the only thing that has been
holding.** The files still unread are the worst ones for it —
`Operational Metrics.xlsx` holds 12,985 rows of `learner_email`; the poll
workbooks queued for session extraction carry `Student Name` and `Student Email`.

So the next planned improvement would have been the first real test of the
contact strip, and the strip would have failed — while the coverage metric went
up and validate.py reported the same green it always had. **A success metric that
moves in the same direction as the risk, with no control between them.**

**What this adds to the list.** Instance 8 asks whether a guard's scope matches
its rule. Instance 9 asks what would fail if a documented constraint stopped
being true. This asks a third thing:

> **When a guarantee holds, do we know WHICH mechanism is holding it — and is
> that the one we think?**

A guarantee can be true for a reason nobody wrote down, and then a change that
looks like progress removes it. The tell here was available and ignored: the
guard's own category tracker said it had never run, while the property it
allegedly enforced was observably true.

**Closed 2026-09-18.** Matching is normalised and substring-based; `validate.py`
checks the raw `column` recorded in provenance, which is the namespace that
carries the risk; the allow-list is named as the control and asserted in
`tests/test_exclusion_is_deny_by_default.py`; and `CLAUDE.md` §2 now carries the
warning at the point where somebody proposes widening coverage, rather than in a
risk register they have no reason to open.

#### OPEN QUESTION — which of our outputs does nobody read?

Not a tenth instance. A question the catalogue has not asked, recorded because
the next instance is more likely to be found in something we print and skip than
in something we never wrote.

**The tracker worked.** `validate.py` has printed

```
NOT EXERCISED: [... 'excluded-field' ...]
```

on every run since the tracker was built — which was built *because of* instances
2 and 3, where an unconditional INFO made a category always look exercised. It
did exactly its job, in plain language, for months. **The guard reported its own
uselessness continuously and nobody read the line.**

So the failure was not in the check, the tracker, or the wording. It was
downstream of the output entirely, and no amount of making the check better
would have caught it.

**And the uncomfortable part.** §5 of `CLAUDE.md` says validation must stay
scannable — count, do not enumerate — because converting six filters to flags
took the report from 19 warnings to 212 and buried the two findings that
mattered. *"A buried finding gets ignored until someone reverts the fix that
buried it."* That discipline is correct and this project would be worse without
it.

It is also what let one NOT EXERCISED line sit unread inside an aggregate. **Both
are true.** Aggregation is what makes a report readable and what makes one line
inside it invisible, and "aggregate less" is not the answer — that is just the
212-warning report again.

**One observation that might be a thread, offered without confidence.** There may
be a difference between two things §5 currently treats alike:

- aggregating **instances of a known category** — *"199 nodes retained with a
  shape flag: 99x single-token, 71x comma or semicolon"* — where the count IS the
  information and the reader already knows what it means;
- aggregating a **status** — *"these categories did not run"* — which is not a
  measurement of the data but a statement about the instrument, and which reads
  as furniture precisely because it is identical on every run.

Which suggests a cheap thing to look for: **the lines in our output that have not
changed in months.** A line that says the same thing every run is, by
construction, one nobody is reading — and it is either a passing check (fine) or
a standing failure nobody has noticed (this). `BUILD_LOG.md` keeps the history to
answer that, and nobody has looked.

**What we do not know**, and should not pretend to: whether the fix is a
different report, a different channel for status-vs-measurement, a diff against
the previous run, or an alert that fires only on change. All four have the same
failure mode as the thing they would replace. Left open deliberately.

