# CLAUDE.md — np-autopilot

Read this before touching the pipeline. Three rules that have already cost time.


## Built from Drive — pass 0 is live as of 2026-09-16

`pipeline/00_fetch_drive.py` runs against the real folder with a **service
account**, scope `drive.readonly`, no domain-wide delegation. The key lives
outside the repo and is named by path through `NP_DRIVE_SA_KEY`; pass 0 refuses
to read one from inside the repo. Pass 1 prefers `.drive-cache/` and falls back
to `NP_CORPUS_PATH` with a loud banner.

**The three-tab "NP Autopilot" master spreadsheet is NOT in that folder.**
Established by listing all 374 worksheets across 18 workbooks and searching for
`Automations`, `All Tasks` and `To-Do & Working Notes` — no match, and none on a
fuzzy search. So `Owner` and `Automation` are not imminent node types.

**That is a statement about this folder**, which is the corpus scope we have
defined and all the service account can see. It is not a statement about all of
Drive. If the workbook turns up elsewhere, doc 05 is still redone.

**Pass 0's stated rationale was not what mattered.** It was written to export
native Google files, which sync as unreadable URL stubs — and there are none in
this folder. All 75 files are already binaries, the export map has never fired,
and that is why the hand-export matched byte for byte. The real value is that
**the laptop is out of the loop**: the corpus is now reproducible by anyone with
the key, and staleness is detectable.

**Coverage did not improve.** 127 of 374 worksheets have been read by an entity
scan. Fetching from Drive fixed reproducibility, not coverage — every count is
still a floor (§2).

---

## 1 · The corpus is READ-ONLY

`/Users/animesh/Desktop/NP-Autopilot-Corpus` mirrors a live Google Drive folder.

- **Never write, move, rename or delete a corpus file.** Not to fix a typo, not
  to normalise a filename, not to split a workbook.
- Filename typos (`Businees`, `Enginnering Mnagement`, `Backend␣␣`) are **load-
  bearing** — they are the citation key back to the source. Correcting one breaks
  provenance. Keep `label_raw` and let a join fail visibly instead.
- Pipeline scripts open workbooks `read_only=True`, and Drive access is scoped
  `drive.readonly`. Do not widen either.
- The corpus root comes from `NP_CORPUS_PATH` via `pipeline/lib/paths.py`. Never
  hardcode it, never put it in a skill or in `plugin.json`.

**It has already changed under an active analysis.** `UpLevel Schedule
Structure.xlsx` (30 sheets) appeared mid-session and moved the worksheet count
344 → 374. Pass 1 hashes a manifest: a **changed or removed** file is a hard
fail; an **added** file is reported in the delta and ingested.

---

## 2 · Coverage caveat — the counts are floors

**25 of 75 corpus files have never been read by an entity-extraction scan.**

`person`, `instructor` and `module` carry `expect: null` in
`config/taxonomy.yaml` for this reason. Their measured values — 43, 1,098, 234 —
are **floors over 50 of 75 files**, not counts. Do not wire them into an
assertion, quote them in prose, or put them in a `plugin.json` description. The
reference implementation shipped counts that were ~70% wrong because someone
hand-wrote them once and never regenerated them.

Unread files that certainly contain entities: `SME Tracker - Bullseye_IK.xlsx`,
`SME_Interview_Demo Audit Rubrics.xlsx`, `AgenticAI Instructors Training
Plan.xlsx` (18 sheets, and the source for eval Q15), `Operational Metrics.xlsx`,
`UpLevel Schedule Structure.xlsx`.

---

## 2a · The three ways a person disappears

All three have happened in this corpus. They need different fixes, and only the
first is caught by auditing file coverage.

### (i) Coverage gap — a file no scan ever read  ← **most serious**

`Karthika Pai` exists only in `SME Tracker - Bullseye_IK.xlsx` and
`SME_Interview_Demo Audit Rubrics.xlsx`. Both sit outside every entity scan, so
nothing that read the corpus could have found her. 25 of 75 files are in this
state. **This is the one that hides unknown quantities** — you cannot estimate
what is missing from files you have not opened.

### (ii) Key-dependent extraction miss — file read, rows dropped

`Yash Mathur` has 11 I-Aim rows in `IAims!Q226` with a **blank `ENo`**. The file
was scanned. An id-keyed read dropped him.

**The blank ENo is normal HR lag for a recent joiner, not corrupt data.** Every
new joiner will present exactly this way, so this is a **permanent condition to
handle**, not a defect to clean up. Consequences:

- **Key person extraction on NAME.** `ENo` is secondary evidence only, never the
  identity, and never a filter.
- **A blank identifier is reported and the row RETAINED.** Never silently
  dropped. `validate.py` reports every person row with a blank identifier.
- Severity is **lower than (i)**: he was missing mostly because he had just
  joined, not because extraction is broadly unreliable. The mechanism is real;
  the blast radius is one recent joiner at a time.

### (iii) Classification miss — found, then shelved

`Vineet Patel` and `Bishal Biprodas Roy` were both extracted, then parked under
"IAims employees who never appear in the owner sheet — in scope or not?" Absence
from the owner sheet is not an out-of-scope signal. The `team` property
(`np` / `delivery` / `other`) exists so this question has an answer instead of a
holding pen.

### Recurring risk: the newest team member is the most likely to be missing

Yash Mathur was caught only because an HR directory happened to be available.
**There will not always be one.** A recent joiner has: no `ENo` yet, few or no
corpus rows, no domain ownership, and no history in older sheets — every signal
the pipeline leans on is weakest exactly when the person is newest.

Two standing mitigations:

- `validate.py` reports any person row with a blank identifier rather than
  dropping it.
- Coverage must be able to answer **"who appears in an objectives sheet but has
  no other corpus presence?"** That query is the tripwire for this class, and it
  works without an HR directory.

**Never key people on employee IDs.** Not unique (`IK-294` and `IK-INT30` each
map to two people), not stable (`Animesh Kumar` has two), and sometimes absent.
Key on a curated slug in `config/people.yaml`; IDs are evidence only.

---

## 3 · Never name a script `inspect.py`

It shadows the stdlib `inspect` module, which both `openpyxl` and `python-docx`
import. Every spreadsheet and Word file then fails with a misleading
`circular import` error that looks like a data problem. One run was lost to this.

The same applies to any stdlib name in `pipeline/`: `types.py`, `io.py`,
`copy.py`, `csv.py`, `json.py`, `logging.py`, `platform.py`, `select.py`,
`token.py`.

---

---

## 4 · Thresholds may rank or warn. They must not silently exclude.

Two cutoffs have already hidden correct answers, and **both were found by an
unrehearsed question, not by review**:

- module `>= 2` cross-file — presented as noise control, it was a filter on truth.
- staffing `>= 2` taught modules — hid **EM**, the domain with exactly one
  instructor and the entire point of the question being asked.

A third audit then found that **six name-shape filters were dominated by false
positives**, silently dropping ~330 real people: `Dr. Raju Penmatcha` and
`Chuhong Mai, PhD` for punctuation, `Will Yao` and `Will Drevo` because "will" is
in the stopword list, `Usha` for being one token.

**Before adding any numeric cutoff, answer this: what would a correct answer
excluded by it look like?** If that question has an answer, the cutoff must not
filter.

- **Rank** — put it on the node as a confidence property (`cross_validated`).
- **Warn** — retain the record and flag it (`review`).
- **Exclude only** when the shape cannot be the thing at all: an `@` in a name, a
  newline meaning several names in one cell, a phone number as a module.

**And the bias, not just the count.** Re-applied to today's population, the six
rules would still exclude 336 people — **84 of them for holding a PhD, Dr or MD,
28 for a middle initial, 4 of 5 stopword hits for being named Will, and 22 for
long multi-part names that are disproportionately South Asian.** Noise removal
that correlates with a category of person is not noise removal.

Full audit in `10-threshold-audit.md`.

---

## 5 · Validation output must stay readable or it stops being read

Converting six filters to flags was a correctness fix. It took validation from
**19 warnings to 212**, because every retained record printed its own line — and
buried the two findings that actually mattered.

**A buried finding gets ignored until someone reverts the fix that buried it.**
That is the real cost, and it is worse than the noise.

**Count, do not enumerate.** One line reading *"199 nodes retained with a shape
flag: 99x single-token, 71x comma or semicolon, 23x >4 tokens"* carries the same
information and leaves the report scannable. Enumerate only what a human must act
on individually.

Before landing a change that increases validation output, check the total. If it
grows by an order of magnitude, aggregate.

---

## 6 · Assume the extractor before you assume the corpus

**Every "the corpus doesn't have it" conclusion in this project eventually became
"the extractor hadn't looked there yet." Five times.**

| I concluded | it was actually |
|---|---|
| no workflow-to-person link | true, but the person scan had never read `For Slack` — `Abhinav Rawat` was missing entirely |
| `teaches` only reaches Agentic AI | 44 of 62 sheets in a file I had opened held the whole class delivery log |
| `UpLevel Schedule Structure` is probably nothing | 26 per-domain schedules and the best module evidence in the corpus |
| doc 05's `Suresh Venkatesan` example must be wrong | it was right; the sheet had never been opened |
| the module layer is thin | 671 of 922 modules were reachable, just not by the edge I was looking at |

Before writing "not in the corpus" in any answer, doc or commit message: **name
the sheets you actually read.** If you cannot, you have found a gap in the
extractor, not in the data.

---

## Other traps

- **`A_sample_Mock_Session_Feedback_Documentation.docx` is not a docx.** It is
  plain UTF-8 with the wrong extension; `python-docx` raises on it. **Sniff magic
  bytes, never trust the extension.**
- **Read cells positionally.** Never compact out blanks — that shifts
  `Every Week` into the owner column (R5).
- **Multi-value cells split on `,` and `/`.** An empty token is a hard fail
  (`Deval, Srushith, , Adil`). Apply `/` to **owner columns only** — the domain
  `Agentic AI - TPM/Pm` is one label, one row away from `Kunal/Abhishek`, which
  is two people.
- **Junk heuristics apply to `person` and `instructor` labels only.** As global
  rules they reject the taxonomy's own vocabulary: theme 15 is 46 characters,
  theme 14 is exactly 40, and 10 of 16 themes plus 27 of 92 workflows contain
  `/`, `&`, `→` or parentheses.
- **`taxonomy.yaml` is the single source of truth.** `pipeline/lib/taxonomy.py`
  is the only module that reads it; a grep test fails the build on any type
  string written as a literal elsewhere.
- **Hand-entered facts carry `origin: hand`** and never emit a `sourced_from`
  edge. They must never be presentable as though a scan produced them.
