# Costing the untracking of `knowledge/graph.json`

**Report, not a proposal. Nothing changed.** 2026-09-18.

`knowledge/graph.json` being a tracked file has now decided three separate
questions — the LinkedIn scope, the contact-fields scope, and half the payroll
scoping — because "visible to `member`" means "in the public half" means "in a
file in the repository". Three decisions made by a packaging choice nobody
revisited.

**Headline: 2–3 days, not a week — and the week is a different decision.**

---

## 1 · What reads it, and what breaks

**One loader, twenty callers.** Everything goes through
`pipeline/lib/graphio.load_graph`, which is the good news: there is a single
place to change. It does `json.loads(path.read_text())` with **no guard for a
missing file**.

| | |
|---|---|
| pipeline modules reading it | **12** (`04_build_graph` writes it; `03_resolve`, `05_render_html`, `validate`, `project_graph`, `gen_index`, `gen_landing_stats`, `query`, `verify_migration`, `refresh` read) |
| test files reading it | **8** |
| of those with a skip guard | **1** (`test_sensitive_split`) |

**Measured, by hiding the file and running the suite:**

```
ERROR tests/test_staffing_tiers.py - FileNotFoundError
Interrupted: 1 error during collection
1 error in 0.42s
```

**The suite does not fail — it does not COLLECT.** `test_staffing_tiers.py` loads
the graph at import time, so pytest aborts before running anything. Today's
304 passing becomes **0 collected**.

**And CI cannot rebuild it.** `.github/workflows/ci.yml` runs `pytest` with no
corpus (gitignored) and no Drive key, so there is no path from a fresh checkout
to a built graph. **CI depends on the committed artefact absolutely**, and that
dependency is currently invisible because the artefact has always been there.

**Cost to fix:** a named error in `graphio.load_graph` ("no graph built; run
passes 1–4") plus skip guards on 8 test files, moving module-level loads into
fixtures. **Half a day**, and it is worth doing whether or not the file is ever
untracked — the current behaviour on a fresh clone is a stack trace.

## 2 · What the plugin ships instead

**The plugin does not need `graph.json`, and the design already says so.**
`DECISIONS.md` §E.1:

| In the plugin (thin client) | Behind the authenticated API |
|---|---|
| Command definitions, prompt text | All graph data **beyond the roster snapshot** |
| **A roster-only cached snapshot (`sensitive = false`)** | The hiring funnel, ratings, decline rates |

So the shipped artefact was never meant to be the 10 MB graph — it is a
roster-only subset. §E.1a records that **nothing has been built for this yet**,
which is why the full graph is what sits in the repo.

**This separates the two questions.** A roster-only snapshot is a smaller, public,
derived artefact that can stay **tracked** while `graph.json` is untracked. The
plugin keeps working. **Untracking does not force the Q5 hybrid.**

**What it does force is a scope decision on that snapshot**, because D11 makes it
unrevocable: whatever ships cannot be withdrawn from a laptop later. That is a
decision to record, not engineering — and it is smaller than the one currently
being made by default, since today the plugin path would carry the whole graph.

## 3 · What a fresh clone gets

Today, ~16.5 MB of build artefacts: `graph.json` 10 MB, `graph.html` 3.3 MB,
`_graph_files.json` 2.1 MB, `_graph_data.json` 1.1 MB.

**But the distribution premise is weaker than it looks.** Q4/§F: the repository is
private, personal, and **takes no collaborators** — there is no read-only tier and
the history carried the hiring funnel. So "what a fresh clone gets" today means
the owner's own machine. Nobody else can clone it, and the artefact is committed
for a distribution that cannot currently happen.

Three replacements, in increasing cost:

1. **Track the roster snapshot only.** Smallest change, matches §E.1, keeps a
   fresh clone useful, and shrinks the tracked payload by an order of magnitude.
2. **A release artefact** attached to a tag rather than committed to the tree.
   Keeps byte-exact distribution without putting it in every clone's history.
3. **Rebuild locally** — needs the corpus and the Drive key, so it is the owner's
   path only, not a collaborator's.

## 4 · Does the byte-identical rebuild guarantee survive?

**The guarantee survives. The diagnostic does not.**

`knowledge/.version-lock.json` already tracks `content_hash`, and it is committed
separately. So "rebuild and compare" still works as a **hash comparison** with the
graph untracked.

What is lost is the ability to see **what** changed. `test_build_is_reproducible`
exists because a rebuild produced a different hash and the diff showed exactly
three fields on 44 `teaches` edges had moved by seven days of calendar drift. A
hash says *different*. The committed artefact said *which three fields*. That
diagnosis is what produced `NP_AS_OF`, and it would not have been possible from a
hash.

The Drive reconciliation gate — *"rebuild from `.drive-cache` and compare to the
committed graph"* — is the same shape and has the same loss.

**Mitigation, and it is cheap:** track a **digest manifest** instead of the graph —
one line per node and edge, `id` plus a hash of its content, sorted. A rebuild
diff then names the rows that moved without carrying their values. Estimated a
few hundred KB against 10 MB, so roughly **5% of the size for most of the
diagnostic**. It also has a property the current artefact lacks: it is
diffable in a pull request.

## 5 · What this actually costs

| | |
|---|---|
| Named error + skip guards on 8 test files | **½ day** — worth doing regardless |
| Digest manifest + point the reconciliation gate at it | **1–1½ days** |
| Roster-only snapshot as the tracked artefact, and the scope decision on it | **1 day** |
| **Total to untrack `graph.json`** | **~2–3 days** |
| *Q5 hybrid (plugin → authenticated API), §E.1a* | *a week or more — and **not required** by any of the above* |

**So: this is a two-to-three day change that unblocks three decisions**, provided
the plugin keeps a tracked roster-only snapshot rather than the full graph. The
week-long piece is the Q5 hybrid, which untracking does not force and which
should be decided on its own merits.

**What I would not do:** untrack the file without the digest manifest. That trades
three unblocked decisions for the loss of the only tool that has ever diagnosed a
reproducibility failure, and the loss would not be noticed until the next one.
