# ACCURACY STANDARD

**Owner decision, Animesh Kumar, 2026-09-29. origin: hand.**

Four requirements. Every one of them has something that runs.

## 1 · Faithful to the source

What the graph says is what the corpus says. Typos are load-bearing and are
never corrected (`CLAUDE.md` §1); `label_raw` keeps the original whenever a
display label differs. **Enforced by:** `pipeline/validate.py`,
`tests/test_module_merges.py` (every absorbed label survives).

## 2 · Nothing guessed

Ambiguity is returned, never resolved by picking (`pipeline/lib/resolve.py`).
A threshold may rank or warn and may never silently exclude (`CLAUDE.md` §4).
Where a fact is absent the UI says which kind is missing and why.
**Enforced by:** `docs/REVIEW-QUEUE.md` (nothing merges without an answer),
the `confirmed: false` review YAMLs, and the source-links "no *kind*: *reason*"
rendering.

## 3 · The mastersheet re-derivation diff is ZERO

Every module's programme week, sessions, instructors by role and assignment are
re-derived by reading the workbook independently — `eval/mastersheet_rederive.py`
does NOT import `pipeline/lib/mastersheet.py` — and diffed against the graph.
**Required result: 0 unexplained differences.** Currently 0 across 20 modules.
**Enforced by:** `tests/test_mastersheet_rederivation.py`, including a mutation
that injects an instructor and asserts the diff catches it.

## 4 · Owner acceptance before deploy

`docs/ACCEPTANCE-CHECKLIST.md` is generated per module with every link, and the
owner ticks each module against the mastersheet. **Phase D does not start until
the owner confirms it.**

---

**Why this is written down.** Three of the four were already true in practice
and none of them was stated anywhere, which is how a standard quietly becomes
whatever the last commit did.
