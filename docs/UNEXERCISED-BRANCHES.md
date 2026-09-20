# UNEXERCISED BRANCHES — the deliberate pass

**2026-09-20.** Three branches that had never run against real data were found
by accident, one per week, each while doing something else:

| found | branch | how |
|---|---|---|
| ~2026-09-16 | `is_excluded_field` — one caller, two namespaces that never meet | an audit of what actually keeps contact data out |
| 2026-09-20 | pass 0's **export map** — every corpus file was already a binary | the registry sheet landing in the corpus folder |
| 2026-09-20 | pass 0's **shortcut follow** — the corpus contains zero shortcuts | checking whether D3 was safe to flip |

**None was found by looking.** So this is the looking: line coverage over a real
pipeline run, asking which branches have never executed against the actual
corpus. **Report only — nothing here is fixed.**

---

## How it was measured

`coverage` is not a dependency of this project and was not added. Instead a
filtered `sys.settrace` recorder (`scratchpad/cov/linecov.py`) records line
events **only** for frames whose file is under `pipeline/` — returning `None`
for every other frame, so Python stops issuing line events for openpyxl and
friends entirely. `trace --count` would have worked and would have taken
roughly an hour per pass.

The run was a full, real one — passes **01 → 05 plus `validate.py`**, against
the real 74-file corpus, in a **copy of the repository** under
`/private/tmp/.../reporun` so nothing in the working tree was touched. All six
exited 0.

**Executable lines come from the compiled code objects** (`co_lines()` over
every nested code object), not from an AST guess, so the denominator is what
CPython would actually execute.

### What this measurement is not

- It is **one run, one corpus**. A branch that fires only on a corpus we do not
  have is indistinguishable here from one that can never fire.
- It is **line coverage, not branch coverage**. `if a and b:` reached only via
  `a` false is recorded as covered.
- It covers **the build pipeline**. Query-time and admin code paths run in other
  processes and are listed separately below rather than called dead.

---

## 1 · Files never executed by a build run

Thirteen of twenty-eight. **Twelve of them are correct** — they are other
runtimes, not dead code: `00_fetch_drive.py` (pass 0, run separately),
`migrate.py`, `verify_migration.py`, `project_graph.py`, `grant_access.py`,
`curation.py`, `query.py`, `refresh.py` (the orchestrator), `gen_index.py`,
`gen_landing_stats.py`, `gen_workflow_owners.py`,
`check_no_payroll_committed.py`, `count_registry.py`.

**`pipeline/lib/resolve.py` deserves a note and not an accusation.** It is the
`Ambiguous` resolver — the module `STATE.md` calls load-bearing, because three
shipped bugs had the shape *several plausible targets, one chosen, no signal to
the caller*. It executes **zero lines during a build**. That is correct: its
callers are `pipeline/query.py` and `api/staffing.py`, both query-time. It is
recorded here because **`SCALE-PLAN.md`'s join is specified to be built on it**,
and the join will be the first build-time caller it has ever had.

---

## 2 · Coverage of the files a build does execute

| file | executable | ran | never | |
|---|---:|---:|---:|---|
| `lib/sources.py` | 103 | 103 | **0** | 100% |
| `05_render_html.py` | 141 | 141 | **0** | 100% |
| `lib/graphio.py` | 42 | 42 | **0** | 100% |
| `lib/render_logic.py` | 3 | 3 | 0 | 100% |
| `04_build_graph.py` | 396 | 388 | 8 | 98.0% |
| `03_resolve.py` | 278 | 270 | 8 | 97.1% |
| `lib/paths.py` | 20 | 19 | 1 | 95.0% |
| `02_extract.py` | 791 | 741 | **50** | 93.7% |
| `validate.py` | 314 | 265 | **49** | 84.4% |
| `lib/taxonomy.py` | 107 | 87 | 20 | 81.3% |
| `01_walk_corpus.py` | 260 | 211 | **49** | 81.2% |
| `lib/teaching.py` | 23 | 8 | 15 | 34.8% |
| `lib/db.py` | 44 | 11 | 33 | 25.0% |

`lib/db.py` at 25% is the pooler layer — only its module-level lines run in a
build, which is expected. **`lib/sources.py` at 100% is worth noticing**: the
allow-list that `A7B.md` identifies as the real contact-data control is the one
module with no unexercised line in it.

---

## 3 · The finding worth acting on: one branch is **unreachable**, not merely unexercised

`01_walk_corpus.py:126`

```python
if kind == "text":
    text = path.read_text(encoding="utf-8")
    return True, "", {"chars": len(text), ...}      # <- always returns
if kind == "png":
    return False, "image with no text layer — nothing to extract", {}
if suffix == ".docx" and kind == "text":            # <- can never be reached
    return False, "extension says .docx but magic bytes say plain text", {}
```

The second condition requires `kind == "text"`, and the first branch returns
unconditionally on exactly that. **No input reaches line 126.** This is dead
code, provable from the ordering rather than from one run's data.

It implements a documented trap. `CLAUDE.md`:

> **`A_sample_Mock_Session_Feedback_Documentation.docx` is not a docx.** It is
> plain UTF-8 with the wrong extension; `python-docx` raises on it. **Sniff
> magic bytes, never trust the extension.**

Measured: that file is in the corpus and starts `7c 20 2a 2a` (`| **INTR`), so
`kind` really is `text`.

**And the protection still works** — the file is read as text and never reaches
`python-docx`, because the *earlier* branch catches it. So:

> **The guarantee holds. The mechanism written down to hold it is unreachable.
> Something else holds it, and nothing relates the two.**

That is `A7B.md` question 3 exactly, and it is the fourth instance — the first
one found by looking rather than by accident. The cost today is only that the
mismatch is never *reported*: a corpus file with a lying extension is silently
treated as text rather than named. At 2,000 files from other people's Drives,
extensions will lie much more often.

---

## 4 · Branches that have never fired, by class

Counted rather than enumerated (`CLAUDE.md` §5). The full line list is in
`scratchpad/missed.json`.

### 4a · Error paths for inputs the corpus has never contained — `02_extract.py`

**Fourteen blocks**, all the same shape: `if not path.exists()` (×6),
`if sheet not in wb.sheetnames` (×5), `if hrow is None or <col> not in hdr`
(×3). Every declared `(file, sheet, column)` triple in `sources.py` has always
resolved.

**This is the set most likely to fire first at scale.** The registry's folders
are owned by fourteen-plus accounts who rename and move things; a declared sheet
going missing is normal traffic there and has never happened here.

### 4b · Junk heuristics that have never rejected anything — `02_extract.py`

Six rejection reasons never returned: `"empty"`, `"single character"`,
`"shorter than 3 characters"`, `"longer than 40 characters"`,
`"contains a digit"`, and the `DOMAIN_LABELS` and status-row skips.

Worth reading against `CLAUDE.md` §4, which converted six name-shape *filters*
into *flags* after they were found to drop ~330 real people. These are the
survivors, and they have never fired — which is consistent with them being
correctly narrow, and is also what a rule that cannot fire looks like.

### 4c · Three of six `review` assignment sites — `02_extract.py`

`rec["review"] = why` at **L325, L374, L410** never executed. **L216 and
L776/777 did**, and the flag does reach the graph: **97 of 3,146 nodes carry
`review`** — 79 single-token, 8 >4 tokens, 8 comma/semicolon, 1 name collision.

So the retain-and-flag mechanism works; three of its six entry points have never
been used. Not "review never fires" — a narrower and more useful claim.

### 4d · Exception handlers — `01_walk_corpus.py`

Four never fired: `except OSError` (×2), `except json.JSONDecodeError`,
`except Exception`. A corpus file has never been unreadable and the manifest has
never been corrupt.

### 4e · The manifest delta has never printed a line

`01_walk_corpus.py:263 / 266 / 269` — the `+ added`, `~ changed`, `- removed`
loops. **Zero iterations, ever.** Every run has had an identical file set.

**`links.xlsx` was about to be the first `+` line in the project's history**, and
is now excluded instead. The next genuinely added corpus file will be the first
time this output path runs.

### 4f · Pass 1's exclusion skip has never fired

`01_walk_corpus.py:217` — `if rel in excluded: skipped.append(rel)`.

`DECISIONS.md` §A.7a is careful that pass 0 and pass 1 are **two layers against
a bug in one pass**, not two independent layers, because both read the same
list. Measured, it is narrower still: **pass 0 excludes at fetch time, so the
excluded file never reaches the cache, so pass 1's check has nothing to skip and
has never executed.** The second layer is real code that has never run.

### 4g · `validate.py` — almost every FAIL branch

**Fourteen `r.add(FAIL, ...)` sites never executed**: `provenance`,
`sensitive-flag`, `cadence-collision`, `endpoint-type` (×2), `wildcard-edge`,
`count-vs-expect`, `absolute-path`, `excluded-file`, `excluded-field`,
`excluded-column`, `duplicate-id`, `curation-version` (×2), `hand-provenance`,
`quarter-map`.

For a healthy graph that is the expected result, and `validate.py` already has
the `NOT EXERCISED` tracker precisely because **a check that has never failed
and a check that cannot fail print the same thing** (instances 2 and 3). This is
the measured version of that tracker's warning, over every category at once.

`excluded-column` is the one `CLAUDE.md` §2 explicitly says must stay at zero —
so its never-firing is the *desired* state, and it is the one entry in this list
that should not be read as a gap.

### 4h · Smaller ones worth naming

- `03_resolve.py:147` — the **`not_same_as` pin suppression** has never
  suppressed a pair, in code added days ago to honour those pins.
- `03_resolve.py:140` — the `middle_name_variant` close-match branch.
- `04_build_graph.py:486` — `if leaked: "the split would now withhold EVIDENCE
  edges"`, a warning about the public/sensitive split that has never triggered.
- `04_build_graph.py:265` — `if not m or not i: unmatched_pairs += 1`.
- `lib/taxonomy.py` — every `raise KeyError(unknown node/edge type)` path, and
  **`property_scopes()` / `property_scope()` entirely**, which run at projection
  time rather than build time.
- `02_extract.py:967` — `if not rejected: "HARD FAIL — empty rejection log. The
  checks are not working."` A meta-guard that only fires when everything else
  is broken; never fired, which is the point of it.

---

## 5 · What this predicts for 2,000 files

The unexercised branches are not randomly distributed. **They cluster in exactly
the code that handles inputs a single, stable, single-owner corpus never
produces**:

1. a declared file or sheet that is missing or renamed (§4a — fourteen blocks);
2. a file that cannot be read or decoded (§4d);
3. a manifest that differs from the last run (§4e);
4. a label shaped unlike anything seen so far (§4b).

**Every one of those is normal traffic in a multi-owner Drive**, which is what
the registry is. So the least-tested code in the pipeline is the code the
scale-up will exercise first, and it will exercise it on day one.

---

## 6 · The question this adds to `A7B.md`

Three instances were found by accident and a fourth by looking. The catalogue's
questions are all asked of a guard you are already looking at; this one is asked
of the whole program:

> **Which branches have never executed against real data — and of those, which
> are unreachable rather than merely unexercised?**

The two answers need different responses. *Unexercised* is a gap in the data,
and the honest move is usually to leave it and note it. *Unreachable* is a bug
that no amount of new data will surface, and §3 is one: a documented protection
whose implementation cannot run, in a project that has written that protection
into `CLAUDE.md` as a rule for future sessions.

**The measurement is cheap.** One traced run, no new dependency, about ten
minutes including the copy. It is worth repeating whenever the corpus shape
changes — and the corpus shape is about to change by two orders of magnitude.
