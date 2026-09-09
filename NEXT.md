# NEXT

Handover, ordered by value. Baseline to regress against is at the bottom of
`BUILD_LOG.md`: graph hash `a53462823ca26466`, plugin `0.1.2`, taxonomy `2`,
eval **25/27 with 0 fabrications**.

**Read `README.md` first — its limitations section is not boilerplate.**

---

## 1 · Pass 0 and the Drive migration — highest value by a distance

**Unblocks four things at once:**

- **The master spreadsheet question.** The brief's taxonomy derives from an "NP
  Autopilot" workbook with `Automations`, `All Tasks` and `To-Do & Working Notes`
  tabs. **It has never been located.** If it exists in Drive, `Owner` and
  `Automation` may return as node types and doc 05 is redone. Everything built
  so far assumes it does not exist — that assumption has never been tested.
- **Click-to-open a source file.** Currently impossible, not merely unbuilt:
  browsers block `file://` links from HTML. `file.drive_url` is a declared
  property sitting null. Populate it and the reverse-provenance panel becomes
  clickable.
- **Machine independence.** The corpus is a hand-export on one laptop. Nobody
  else can reproduce it, nobody can tell which files are stale.
- **Refresh v2**, which is gated on this.

**Cost:** ~1 hour of setup, all on your machine. Google Cloud project → enable
Drive API → **OAuth consent screen user type Internal** (External + Testing
expires the refresh token after 7 days and the pipeline dies with
`invalid_grant`) → Desktop app credentials → `config/drive.yaml`. Then
`python3 pipeline/00_fetch_drive.py`.

**Already built and never run.** It exports native Sheets/Docs/Slides rather than
downloading stubs, keeps every tab, exits non-zero on an empty enumeration, and
logs the authenticated account and folder id to BUILD_LOG on every run. The
404 troubleshooting list is in README.

**Risk if skipped:** every count stays a floor over a corpus one person exported
by hand, and the master-spreadsheet question stays open indefinitely.

---

## 2 · The 71 unread sheets — 4,572 rows

**127 of 374 worksheets have been read.** Of the 247 unread, 176 are deliberate
(37 payroll, 139 learner data). **71 sheets / 4,572 rows are a genuine blind
spot.**

Largest: **`New Combined Schedule!Class Confirmation Record`** (1,690 rows —
already read manually, it is the confirmation side of known classes, not a second
delivery log), then `Instructors Directory!Sheet13` (532),
`SME database!Sheet3` (440), four UpLevel Masterclass sheets, and the
`Data and Management` DS/ML/DE/PM curriculum sheets.

**Cost:** a few hours. Add each to `pipeline/lib/sources.py`, re-run, inspect the
delta.

**Why it matters more than the row count suggests:** **five times** in this
project, "the corpus doesn't have it" turned out to be "the extractor hadn't
looked there yet" — the 44 schedule sheets alone tripled `teaches` and gave every
core domain teaching evidence. **Assume the extractor before the corpus.**

---

## 3 · Three ambiguous alias sets — needs a human decision, not code

15 aliases are confirmed and applied. **Three sets failed the sibling-domain test
and are deliberately unjoined**, costing 272 `expert_in` edges:

| alias | claims | candidates |
|---|---|---|
| `ML` | **157** | Machine Learning (IP course) · Flagship ML/ ML Program · ML Switch-up (Adv ML) · Advanced ML Ops · Advanced ML Interview Prep |
| `Agentic AI` | 64 | Agentic AI - EM · - SWE · - TPM/Pm · India Agentic AI Bootcamp |
| `Product Management` | 51 | PM · GPM (Growth Product Management) |

**Cost:** minutes, once you decide. Add to `config/domain-aliases.yaml` with
`confirmed: true` and re-run.

**Do not let a future session resolve these by picking.** `pipeline/lib/resolve.py`
returns `Ambiguous` by default precisely to prevent it. Three separate bugs in
this project had exactly that shape. Options: map to one, map to all (which
over-connects), or add a rule using the instructor's other columns.

---

## 4 · Refresh v2 — nightly. **Gated on #1.**

**Cost:** half a day once pass 0 works.

**Build it with a service account**, with the Drive folder shared to its address
— not user OAuth. A headless job cannot complete a browser consent, and a job
tied to one person's account breaks when they leave. `00_fetch_drive.py` is
already structured so only `authenticate()` changes.

**What v1 already gives you:** `pipeline/refresh.py` runs all six passes,
validates, prints a delta, bumps the version and **stops without committing**.
The bump is enforced — `validate.py` hard-fails if `graph.json` changed while
`plugin.json` did not.

---

## 5 · Cloudflare deploy — **gated on the repo moving to an org**

Documented in README, **nothing configured**. Not urgent while the repo is
single-owner.

**The real cost is the move, not the deploy.** `ANI-IN/np-autopilot` is private
with no collaborators, so **no teammate can install anything today**. Moving it
changes the marketplace URL, which breaks `/plugin marketplace add` for anyone
already installed — and removing a marketplace auto-uninstalls its plugins, so
it is a remove-and-reinstall each.

**Move it before the second user, not after the tenth.**

**Before enabling Access, re-read `07-risks.md` R6.** The graph carries ratings
and written judgements about named individuals. The render already excludes
1,842 in-pipeline/rejected/lapsed instructors including **255 hiring rejections
about named external people**. Access control is not a substitute for that.

---

## Known-and-deliberate, do not "fix"

- **92 workflows with no owner.** Workflow-level ownership does not exist in NP.
  Blank is the correct final state. Never report it as a gap.
- **Android and iOS with zero teaching evidence.** They have no instructors —
  owner-confirmed, out-of-corpus. Not a data gap.
- **`depends_on` at zero.** No dependency evidence exists in the corpus.
- **14 programs unjoined to a domain.** Abbreviations and typos; joining them
  needs spell-correction, which R12 forbids.
- **Eval Q13 and Q14 failing.** Query problems, not data problems, left failing
  so the score stays honest.
