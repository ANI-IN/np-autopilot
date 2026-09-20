# SCALE — the 2,000-file direction

**Not a design. A statement of what the question requires, and four questions
recorded unanswered.** 2026-09-20.

Nothing here is built. Nothing here is decided. The point of writing it now is
that the next session will be tempted to start building, and the honest first
move is a measurement.

> **That measurement has now been taken — [`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md),
> 2026-09-20.** 37 folders of ≥187, 75 files, 5 decks. It does not answer Q1
> (2,000 is still unverified), it makes **Q3 the urgent one**, and it adds a
> constraint this document did not have: **people must not be extracted from
> slide content at all**, because four decks carry four instructor-shaped
> `Name, Role, Company` tuples and two of them are fictional. Read the
> inventory's §7 and §8 before acting on the four questions below.

---

## The question

> *Search "API design" and get back the files about it **and** the instructors
> who teach those modules.*

That is one sentence and **two retrieval problems, joined**:

| | half one | half two |
|---|---|---|
| **what** | the files about API design | the instructors who teach those modules |
| **how** | content search over documents **nobody has read** | graph traversal over a **curated subset** |
| **exists today?** | **no** | yes, over 74 files |
| **scales by** | indexing — more documents is more of the same | curation — more files is more human judgement |

**The second half already works and does not scale the way the first does.** The
graph answers "who teaches this module" from 74 files whose sheets and columns
were read, argued about, and declared one at a time in `sources.py`. The first
half does not exist at all: there is no content index, and 2,000 files cannot be
curated the way 74 were.

## The join is the alias problem, for the third time

The two halves meet at **topic string → module node**. A document says "API
design"; a module node is called something; those are matched by name.

This is exactly `ML` → five candidate domains, and `Agentic AI` → four that
differ only by an audience nobody recorded. It has the same three properties:

- **a name match with guaranteed misses** — the corpus writes the same thing
  many ways, and 20 of 35 contact-shaped headers slipped a matcher that used
  equality;
- **it needs an `Ambiguous` path**, because `lib/resolve.py` returns Ambiguous
  by default and three shipped bugs came from picking with no signal;
- **it is the third place a threshold could hide a correct answer** — after the
  module `>= 2` cross-file cutoff and the staffing `>= 2` taught-modules cutoff,
  both of which presented as noise control and were filters on truth.

**A relevance score is a threshold.** If the join ranks and cuts, it will hide
correct answers, and §4 says a cutoff must answer *"what would a correct answer
excluded by this look like?"* before it is allowed to filter.

---

## Four questions, recorded unanswered

Written down rather than guessed. Each needs a measurement.

### 1 · What breaks at 2,000 files?

Not "is it slower". **What stops being true.** Candidates, none verified:

- `expect`/`tolerance` in `taxonomy.yaml` is calibrated at 74 files with a
  tolerance of 2; the manifest rule treats an added file as normal traffic and a
  changed one as a hard fail.
- Pass 1 hashes every file on every run.
- `nodeBudget` caps the client at 1,200 and the projection is already 3,146.
- The 30,658 provenance rows came from 74 files.
- `graph.json` is 10 MB from 74 files and is a tracked file.

**Measure before assuming which of these is the wall.**

### 2 · What does "ingestion" mean for a file nobody has read?

Today ingestion means: a human opened the workbook, chose the sheet, chose the
column, and declared it in `sources.py`. That is why only **20 distinct columns**
have ever been read and why every node has provenance to a file, sheet, row and
column.

At 2,000 files that process does not run. So ingestion becomes something else —
and **what it becomes decides whether provenance survives**. A content index can
cite a file and an offset; it cannot cite a column nobody identified. Whether
"where did this come from" still has an answer is the question, not a detail.

### 3 · What replaces `sources.py`'s narrow inclusion as the real contact-data control?

**This is the urgent one, and it is already recorded in `CLAUDE.md` §2.**

D4's contact strip does not keep contact data out of the graph — it was inert for
months and is now a hardened backstop, not the control. What holds is that
extraction reads 20 declared columns. **Widening ingestion to 2,000 unread files
removes exactly that.**

The unread files are the worst ones for it: `Operational Metrics.xlsx` alone is
12,985 rows of `learner_email`, and the poll workbooks carry `Student Name` and
`Student Email`. **Any answer to question 2 that does not answer this one is
incomplete.**

### 4 · Which of the landing page's honesty claims survive?

The landing page makes four claims. Each was true of a 74-file curated graph:

| claim | survives at 2,000? |
|---|---|
| *A miss is not evidence of absence* | **stronger** — more so with an index |
| *Counts are floors, not totals* | probably still true, and harder to state |
| *Some emptiness is the right answer* | **unknown** — depends on whether the join admits it cannot match |
| *It refuses rather than guesses* | **the one at risk.** A relevance-ranked search that returns its best match has guessed |

**The page is a promise. If a claim stops being true, the page changes or the
feature does not ship.**

---

## The fork, stated plainly

There are two systems here and they are not variations of each other.

### A · A search index, with a graph over a known subset

Content search answers *which files*. The graph answers *who teaches this*, over
the curated subset it already covers. The join is explicit about its limits:
where a topic maps to a module, it says so and traverses; where it does not, it
says **"these files mention it; no module in the graph matches that name"** and
stops.

**Honest, useful, and admits the seam.** A user gets files always and instructors
when the join holds. The two halves keep their own provenance — an index cites a
file and an offset, the graph cites a file, sheet, row and column — and neither
pretends to the other's.

### B · A graph that guesses

Extract entities from 2,000 unread files, match topics to modules by similarity,
rank by relevance, return the best. **Cheaper, demos better, and is the failure
this project was built to avoid.** It reintroduces every pattern the record
warns about: a threshold that hides correct answers, a name match that picks with
no signal, and facts with no citable source. It would also be impossible to tell
from A when it is right, and indistinguishable from A right up to the moment
somebody staffs a domain from a guess.

> **A is the design. B is the thing to recognise on the way to A**, because B is
> what A degrades into under time pressure, one reasonable-looking shortcut at a
> time.

---

## What NOT to do first

Not an extractor. Not a registry reader. Not a schema.

**A content inventory**, in the shape of `01-corpus-inventory.md`: file types,
counts, and a representative sample of what is actually inside — because doc 01
exists in that form for a reason. Reading headers instead of rows gave the wrong
answer at 75 files, and it will give a more confident wrong answer at 2,000.

**DONE 2026-09-20 — [`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md).** Still do
not write the extractor. What it says to measure next, in order: the 16
`Live Class Content` module folders and the 17 under
`Uplevel Shared(SWEs + Common modules)`, because that is where the decks are and
the 8-of-75 deck ratio is the number most likely to be wrong; the five folders
in C untouched since 2023-02-28, to learn whether a third of that folder is
empty; and one `(File responses)` folder, to learn what learners uploaded.

Two decisions it says to take **before** the first crawl, because both silently
change what the corpus is and both are expensive to reverse at 2,000 files:
**what a shortcut means** (~1 file in 10; its target may sit outside all three
registry folders, so following widens the corpus past what the registry declares
and skipping drops curriculum files), and **whether file-owner metadata is
recorded** (it is contact data, it is collected by the act of citing a file, and
`sources.py` has no jurisdiction over it).
