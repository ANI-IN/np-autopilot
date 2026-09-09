# 04 — Reference Implementation Review: `acceler-presales-plugin`

**What I examined**
- The documentation site: https://acceler-atlas.vercel.app
- The repository: **`voldemortuk/acceler-presales-plugin`** — found via `gh search repos`
- I downloaded and analysed their actual `knowledge/graph.json` (2.8 MB, 2,314 nodes, 12,263 edges) rather than trusting the prose.

## Public or private? — settled

The brief notes their docs contradict themselves. **The repository is public.** Verified two ways:

```
$ gh api repos/voldemortuk/acceler-presales-plugin --jq '.full_name, .private'
voldemortuk/acceler-presales-plugin
false
```

and the README states: *"This repo is the marketplace, and it's public — anyone can install directly from it."* Created 2026-06-25, last pushed 2026-09-09, 2 MB.

**Note the licence though:** `"license": "Proprietary · Acceler / Interview Kickstart"`. Public repo, proprietary licence, and it contains client names, deal sizes and instructor LinkedIn URLs. That is an internal-exposure question for whoever owns it — not ours to fix, but worth telling you, since **this is your own company's data sitting in a public repo** (accounts like `Deloitte`, `Lytx`, `e&`, deal sizes up to `$537M`).

---

---

## 0. EXPOSURE FINDING — `acceler-presales-plugin` is world-readable and contains third-party PII

I under-weighted this in the first pass. Full evidence, since I fetched from it.

### Repo visibility, as I observed it

| Check | Result |
|---|---|
| Anonymous HTTPS GET of the repo page | **HTTP 200** |
| Anonymous raw GET of `knowledge/graph.json` | **HTTP 200** |
| GitHub API `private` | **`false`** |
| GitHub API `visibility` | **`public`** |
| Forks / stars | 0 / 0 |

The raw fetch used **no credential** — not my `gh` token, not a cookie. Anyone on the internet can clone it. I downloaded the 2.8 MB `knowledge/graph.json` this way and analysed it locally.

### On the "docs contradict themselves" point — **CORRECTED 2026-09-09**

**My earlier conclusion here was wrong, and it was wrong because I read the wrong
source.** I quoted `CONTRIBUTING.md` *from the repository* and concluded the
documents were "internally consistent". The brief's claim was about **the docs
site**, which I did not read to the bottom — `WebFetch` returned only the SPA
shell, and I did not notice that the body had not loaded.

I have now fetched the rendered page (`curl` + strip, 33,332 characters of text)
and searched it exhaustively. **The site contradicts itself, on one page, seven
times.**

**Contribute → "Conventions that keep this from breaking"** — verbatim:

> **`knowledge/` holds confidential data** — client names, instructor
> LinkedIn/PII, pricing. **Keep this repo private. Never make it public.**

The overview section agrees:

> Both plugins distributed via the same **private** Git marketplace (see
> Contribute, below)

**And the same page says the opposite in five places:**

| # | Section | Verbatim |
|---|---|---|
| 1 | `03 · Setup & Update` | "The plugin ships from a **public GitHub marketplace** … Anyone can install directly from it; no invite, no collaborator access" |
| 2 | `03 · Setup & Update` → Prerequisites | "**The repo is public**, so there's no invite or collaborator step to install" |
| 3 | `03 · Setup & Update` → troubleshooting | "the repo is public so this is almost always a local git/GitHub CLI auth issue, not an access problem" |
| 4 | `07 · FAQ & Troubleshooting` | "**The repo is public**, so this almost always means a local git/GitHub CLI issue, not access" |
| 5 | `08 · Resources` | "Plugin repo **(source of truth, public)**" |

So the tally on one page is **5 "public" against 2 "private"**, and the two
halves sit in adjacent sections describing the same repository.

**Both halves also contradict `CONTRIBUTING.md` in the repo**, which is a third
position again — it says the repo is public *and* that this was deliberate:

> "**This repo is public.** `knowledge/` contains client names, instructor
> LinkedIn/PII, and pricing data that is now openly readable and clonable by
> anyone — that was a deliberate call to allow install without collaborator
> access."

**Three documents, three positions:** the docs site's Contribute section says
keep it private; the docs site's Setup/FAQ/Resources sections say it is public
and that this is fine; `CONTRIBUTING.md` says it is public and that the exposure
was a knowing trade-off.

**What is actually true: the repo is public.** `gh api … --jq '.private'`
returns `false`, and an anonymous, credential-free `GET` of
`knowledge/graph.json` returns HTTP 200.

**Why this matters more than a documentation nit.** The Contribute section is the
page a contributor reads *before adding data*, and it tells them the repository
is private. Someone following it would add client or PII data to a repo they had
been told was access-controlled, which is world-readable. That is a live
mechanism for making the exposure worse, and it strengthens rather than weakens
the case for **D10** — an Organization + team, so that the access model is a fact
about the repo rather than a claim in prose.

**Withdrawn:** my earlier sentences "I did **not** find a 'never make this
public' statement", "the documents are **internally consistent**", and "not a
contradiction". All three are false. The statement exists, verbatim, in the
Contribute section.

### What is actually in the file I read

| Category | Count in `knowledge/graph.json` |
|---|---|
| Total nodes | 2,314 |
| **Named individuals** (instructor nodes) | **351** |
| **Distinct LinkedIn profile URLs** | **123** |
| **Named client / account nodes** | **33** — including `Lytx`, `B2B Deloitte AI For Leaders`, `Yettel Serbia`, `B2B Nucleus Masterclass`, `B2B Cornerstone Sales Team`, and multiple `e&` engagements |
| File nodes carrying `price_bands` | 1,832 |
| **Distinct monetary values** | **237**, of which **47 at `$__M` scale** — largest present: **`$940M`, `$888M`, `$750M`, `$700M`, `$670M`, `$600M`** |
| Clean email addresses (regex-matchable) | 0 |
| **De-manglable email addresses** | **1** |

### The single worst node

One `instructor` node is a survey respondent's spreadsheet row that lost its CSV quoting:

- **`label`** — a named individual, their personal Gmail address (the `@` replaced by a space during parsing, so it evades a naive scan but is trivially reconstructable), their employer (**Amazon**) and seniority (**SDE**)
- **`role`** — their verbatim survey answers, including tenure (`5-10 years`) and a response about **layoffs at their employer** (`"No, my team did not layoff anyone in Q1, 2023"`)
- **`sources`** — `Misc/Copy of Copy of Market Survey - Mentor Responses`

A person who answered a market survey is now a permanently published graph node with their email, employer, seniority and opinions about their employer's layoffs. They did not consent to that, and the "Copy of Copy of" in the source path suggests nobody intended it either.

**Not our scope to remediate, and I am not touching their repo.** Reported because it is your company's data, because it directly justifies D10, and because I fetched from it during this research and you are entitled to know exactly what I pulled.

---

## 1. The five pipeline scripts

**They are not in the repository.** `USING_THE_KG.md` says *"From this folder:"* and lists them, but `knowledge/` contains only outputs. So the pipeline is undocumented beyond these one-line descriptions:

| Script | Stated role |
|---|---|
| `build_corpus.py` | *"Pass 1 — only when new files are added (re-walks the drive)"* |
| `build_graph.py` | *"Pass 2 — classify + extract tools/topics/pricing"* |
| `parse_pool.py` | *"instructor sources → pool"* |
| `merge_instructors.py` | *"merge + topic classification + augment graph"* |
| `build_html.py` | *"render graph.html"* |

**Mapped against the brief's five passes:**

| Brief | Acceler equivalent | Gap |
|---|---|---|
| `01_walk_corpus` | `build_corpus.py` | same |
| `02_extract` | `build_graph.py` | same |
| `03_resolve` | `merge_instructors.py` (people only) | **Resolution is people-only and fused with extraction** |
| `04_build_graph` | fused into `build_graph.py` + `merge_instructors.py` | **No distinct assembly step** |
| `05_render_html` | `build_html.py` | same |
| `validate.py` | **none** | **No validation step exists** |

**Their extract/resolve boundary is exactly where the brief says not to put it** — `merge_instructors.py` does "merge + topic classification + augment graph" in one pass. The consequences are visible in their output (below).

---

## 2. Node types and how they map to their domain

From `graph.json` (`meta` block plus my own count):

| Node type | Count | Role in their domain |
|---|---|---|
| `file` | 1,833 | **Every source file is a node.** This is how they carry provenance. |
| `instructor` | 351 | Who can deliver |
| `tool` | 40 | Tech mentioned (Claude, RAG, n8n, LangChain…) |
| `client` | 33 | B2B accounts — the spine of their queries |
| `topic` | 30 | Subject taxonomy |
| `doctype` | 14 | Proposal / costing / curriculum / assessment |
| `program` | 13 | Product line (AI Builder, AI for Leaders…) |
| **Total** | **2,314** | |

**Edge types — 8, all hyphenated:**

| Edge | Count |
|---|---|
| `covers-topic` | 5,950 |
| `belongs-to` | 1,833 |
| `is-a` | 1,833 |
| `covers` | 1,634 |
| `expert-in` | 450 |
| `uses` | 414 |
| `engages` | 77 |
| `proposed-for` | 72 |

Edge shape is minimal: `{source, target, rel, weight}`.

**The domain mapping is clean and worth copying:** a pre-sales question is *"find the closest precedent"*, so `client` is the hub, `file` is the evidence, and `topic`/`tool` are the search facets. Ours is different — our hub is `Workflow`, not an account — but the *pattern* (one hub type, files as evidence, facets for search) transfers directly.

---

## 3. Repo and plugin layout

```
acceler-presales-plugin/            ← marketplace root AND plugin 1 root
├── .claude-plugin/
│   ├── plugin.json                 ← acceler-presales v0.6.3
│   └── marketplace.json            ← "acceler-local", 2 plugins
├── commands/                       ← 9 flat .md files
├── skills/                         ← 7 skills, <name>/SKILL.md
├── knowledge/                      ← graph.json, files.json, INDEX.md, USING_THE_KG.md
├── samples/                        ← 3 .docx proposals
├── setup.sh
└── post-sales/                     ← plugin 2, nested
    ├── .claude-plugin/plugin.json  ← acceler-post-sales v0.2.0
    ├── commands/                   ← 4
    └── skills/                     ← 3
```

**They split into two plugins inside one repo and one marketplace** (`source: "./"` and `source: "./post-sales"`), versioned independently (0.6.3 / 0.2.0). The second plugin has **no `knowledge/` folder** — it does not query the graph. This is direct evidence for the §1.3 amendment in doc 03.

**Their `marketplace.json` uses a stale schema URL** (`anthropic.com/claude-code/marketplace.schema.json`); the current one is `code.claude.com/schemas/marketplace.json`. Harmless (ignored at load) but a sign the manifest has not been revisited.

---

## 4. Failure modes their documentation warns about — and the ones it doesn't

### Warned explicitly

**The taxonomy-in-two-places problem — the exact one the brief cites.** From `USING_THE_KG.md`:

> *"Topic taxonomy lives in `build_graph.py` (`TOPICS`) and must stay in sync with `CANON` in `merge_instructors.py`. Instructor topic guards (HR/TA, etc.) live in `merge_instructors.py` (`classify_topics`, `HR_PROFESSION`)."*

So the brief's B2 hard rule is validated by their own documentation — **and they did not solve it.** They documented the hazard and left a manual sync obligation across two files (arguably three). This is the single strongest argument for `pipeline/lib/taxonomy.py` plus the grep test.

Also warned: manual regeneration required before republishing; independent plugin versions mean *"updates don't always ship together"*; and a marketplace-swap gotcha — *"Don't uninstall or remove the old marketplace first (that auto-uninstalls the plugin)."*

### Not warned about — but present in the shipped artefact

**a) Freeform extraction invented people.** 351 `instructor` nodes. **27 (7.7%) are not people** — the same 27 appear in `instr_candidates.json`, so they were never people at any stage of their pipeline.** They are slide bullets split on a comma into "name" + "role":

| `label` (became the person's name) | `role` |
|---|---|
| `Workflows are powerful` | `but they have boundaries.` |
| `They can t handle branching logic` | `one agent can complete a task, but it can't s…` |
| `AI doesn t read your mind` | `it follows your instructions.` |
| `We're no longer automating tasks` | `we're building intelligent systems` |
| `Customers got responses in seconds` | `not hours?` |
| `Note for instructor` | `Spend some time going through the Zapier inte…` |
| `Severity of the Issue` | `Critical` |
| `Nahid Hasan Nhasan.ikickstart gmail.com Amazon FAANG` | `II,9,9,5-10 years,"No, my team did not layoff…` |

The last one is a **CSV row that lost its quoting** — an email and employment history mashed into a node ID. These are live in a public repo today.

**This is what the brief's B4 rejection log and B6 validation exist to prevent**, and it is the most valuable thing I found. It is not a hypothetical failure mode; it is 8% of one node type in a shipped graph.

**b) Provenance is 3%, not 15%.** *(Corrected.)* The `sources` key is present on all 351 instructors, but **280 of them carry an empty list**. Nodes with a genuinely non-empty source: **71 of 2,314 (3%)**. `client`, `topic`, `tool`, `program`, `doctype` nodes are bare: `{id, label, type, count}`. There is **no way to ask "why is this topic in the graph?"** Their answer is indirect — traverse to `file` nodes. Workable, but it means a wrong entity cannot be traced to the row that produced it.

**c) Thin nodes.** 225 of 351 instructors (64%) have neither `linkedin` nor `expertise` — name and nothing else.

**d) Counts drift between artefacts.** Four different numbers for the same graph:

| Source | Files | Clients | Instructors |
|---|---|---|---|
| `graph.json` `meta` (ground truth) | 1,833 | 32 | 351 |
| `knowledge/INDEX.md` (auto-generated) | 1,833 | 32 | — |
| `knowledge/instr_candidates.json` (the instructor pool) | — | — | **351** |
| `plugin.json` description (hand-written) | **1,072** | **61** | **773** |
| Website | **1,072** | **61** | **773** |

**Reconciliation of 773 vs 351 — I chased this down.** The hypothesis that 773 is a pre-dedup candidate pool is **wrong**: I downloaded `knowledge/instr_candidates.json`, and it holds **exactly 351** instructors — the identical set to the graph (intersection 351, symmetric difference 0). **773 appears in no shipped artefact.** It exists only in three pieces of hand-written prose (`plugin.json` description, the marketplace entry description, and the website). It is a stale number from an earlier build that was never regenerated.

**The auto-generated file stayed correct; the hand-written ones drifted ~70%.** Strong support for the brief's decision to auto-generate `INDEX.md` — and an argument for keeping counts *out* of hand-written prose like `plugin.json` descriptions entirely.

**e) `USING_THE_KG.md` references files that do not exist:** `graph.html` (not in repo) and `instructors.json` (repo has `instr_candidates.json` and `instructor_delivery_flags.json`). The usage guide has drifted from the artefact it describes.

**f) Ambiguous edge vocabulary.** `covers` (1,634) and `covers-topic` (5,950) coexist; `belongs-to` and `is-a` both fire exactly 1,833 times (once per file). Nothing in the naming says which to use when.

---

## 5. What to copy, what to do differently

### Copy

1. **`file` as a first-class node type.** Elegant provenance, and it makes "show me the source" a single hop. Adopt it.
2. **One hub type per domain.** Theirs is `client`; ours is `Workflow`.
3. **Small, flat edge shape** — `{source, target, rel}`. Add provenance, keep it flat.
4. **`INDEX.md` + `USING_THE_KG.md` split** — auto-generated digest vs hand-written traversal guide. The brief already specifies this; their experience proves the auto-generated half is the half that survives.
5. **Two plugins in one repo/marketplace when the second needs no graph.** Cheap, proven.
6. **`self-contained graph.html`** as the shareable artefact — their `USING_THE_KG.md` leads with it.

### Do differently

1. **Split extract from resolve, as the brief specifies.** Their fused `merge_instructors.py` is where the 27 fake instructors survived — there was no separate pass that could have rejected them.
2. **Closed vocabulary with a rejection log.** Nothing in their pipeline could say *"'Workflows are powerful' is not a person"*. Ours must, and must log it.
3. **Provenance on every node, not 15%.** Non-negotiable if we want citations in answers.
4. **A `validate.py` step.** They have none. Every one of (a)–(f) above is machine-detectable: junk-name heuristics, orphan checks, count reconciliation, dangling doc references.
5. **Single-source taxonomy.** They documented the two-places hazard; we eliminate it (B2).
6. **Never hand-write counts.** Their `plugin.json` description is 70% wrong. Generate the description or omit the numbers.
7. **Deterministic IDs.** Theirs are `I:workflows are powerful` — derived from raw label, so any label change silently creates a new node and orphans the old edges. The brief's hash-of-normalised-name-plus-type is better.
8. **Do not ship a proprietary internal graph in a public repo.** Ours stays private, as decided.

### One thing to reconsider

Their `count` field on every node is doing real work — `client` nodes carry a file count that drives the INDEX digest. Cheap, and useful for ranking search results. Worth adding to ours.
