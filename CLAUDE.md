# CLAUDE.md — np-autopilot

Read this before touching the pipeline. Three rules that have already cost time.

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

**Two miss classes, not one.** A file can be unread (Karthika Pai), *or* read
with rows silently dropped (Yash Mathur — 11 I-Aim rows, blank `ENo`, dropped by
an id-keyed read). A coverage audit only catches the first. **Never key people on
employee IDs** — they are not unique (`IK-294`, `IK-INT30` each map to two
people), not stable (`Animesh Kumar` has two), and sometimes absent. Key on a
curated slug in `config/people.yaml`; IDs are evidence only.

---

## 3 · Never name a script `inspect.py`

It shadows the stdlib `inspect` module, which both `openpyxl` and `python-docx`
import. Every spreadsheet and Word file then fails with a misleading
`circular import` error that looks like a data problem. One run was lost to this.

The same applies to any stdlib name in `pipeline/`: `types.py`, `io.py`,
`copy.py`, `csv.py`, `json.py`, `logging.py`, `platform.py`, `select.py`,
`token.py`.

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
