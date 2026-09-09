# 08 — Approved Decisions and Answers to Gate Questions

Recorded 2026-09-09, second round.

## Amendment log — 2026-09-09, third round

The header previously claimed docs 01–07 "have been patched to match". **They had
not been.** They have now been patched for real; the files changed are listed
below, and each change is marked in place in the target document.

| Doc | What was wrong | Now |
|---|---|---|
| **04** | Concluded the Acceler docs are "internally consistent" and that no "never make it public" statement exists. **Wrong source** — I quoted the repo's `CONTRIBUTING.md`, not the docs site, whose body had not loaded in my fetch. | Re-fetched and searched the rendered page. The Contribute section says verbatim *"Keep this repo private. Never make it public."*; five other sections say it is public. Claim withdrawn, evidence tabulated. |
| **05** | Summary table said `Tool` = 5 / "keep"; Tier 2 said 6 / demoted. Ambiguity 1 still 55% after D3; ambiguity 2 still 65% after D5. Structural section still read as an open recommendation. Inline `taxonomy.yaml` had drifted badly. | Table corrected to 6 / demoted. Both ambiguities marked resolved. Option B recorded as chosen via the D2 reversal. Inline YAML withdrawn and replaced by a pointer to `config/taxonomy.yaml` v2. |
| **06** | Composition claimed 8 multi-hop while the document's own annotations called Q10 a property lookup and Q16 a file observation. | Reclassified honestly: **6 multi-hop**, 2 single-hop + observation. Two verified replacements added (Q21, Q22) bringing the set to 8 true multi-hop of 22. Eval key re-verified against R5. |
| **07** | R3 recommended keying `people.yaml` on employee IDs — reversed by Q4. R16 said `$537M`. R2 described workflow ownership as undecided. | R3 rewritten to key on a curated slug, with the `IK-294` collision spelled out. R16 corrected to `$940M` and cross-referenced to doc 04. R2 updated: D2 reversed, stub generated. |
| **08** | This document. Q1 claimed D5 "reduces the program count". | **Withdrawn** — the KYP collapse merges zero pairs. Program stays 42. See below. |

### Corrections to this document

- **Q1 / D5 — program count.** The claim that `TPM EdgeUP KYP` and `TPM-KYP`
  "resolve to one product … rather than two Programs" is **withdrawn**. Stripping
  `KYP` from all 42 filenames merges nothing, because per D5 itself *EdgeUP is
  the product* — so `TPM EdgeUP` and `TPM` are two products. **Program = 42,
  unchanged.** D5's real effect is 42 `has_doc` edges into 3 doctype nodes.
- **Q4 — person ceiling.** 50 was wrong. Group (a)'s 12 strings collapse to **4**
  new humans (Deval, Uday, Prithika, Rakshit Kapoor); the other 8 strings merge
  into people already resolved. So **13 + 4 + 12 + 13 = 42**, not 50.
- **Q4 — `Karthika Pai` is missing from both lists.** Neither resolved nor
  unresolved. Cause and fix recorded in the third-round response; she is an
  instructor-side name and the Person scan never covered her sources.
- **D2 is reversed.** `config/workflow-owners.yaml` is being built.
- **D4 is narrowed.** `US Instructor Cost Analysis.xlsx` is excluded outright and
  learner contact fields are dropped at ingestion. See `README.md` → Exclusions.

---

**Original second-round record follows.**

---

## Part 1 — Decisions you made (now binding)

| # | Decision |
|---|---|
| D1 | **Automations = a wish list.** Nothing is built. Do **not** model automations as existing systems. Ingest the workflow inventory as-is; every workflow is understood to be work-in-progress. |
| D2 | **No `workflow-owners.yaml` for v1.** Domain-level ownership only. The command is named **`domain-owner`**, not `owner`, so it does not promise what it cannot deliver. `USING_THE_KG.md` must state that workflow-level ownership is out of scope for v1. |
| D3 | **`Karthika S` and `Karthika Pai` are two different people** — confirmed. Both go into `people.yaml` as separate canonical entries, each carrying a comment recording that this was confirmed, so no future fuzzy-match pass merges them. |
| D4 | **Ingest everything sensitive.** `US Instructor Cost Analysis.xlsx` in. Free-text judgement sheets in. Tag those nodes `sensitive: true`. **Strip instructor contact fields** (email/phone/LinkedIn/Discord) at extraction. |
| D5 | **KYP is a document type, not an entity.** EdgeUP is the product. Every program has its own KYP doc → model `KYP` as a **doctype**, joined to each program by a per-program edge. |
| D6 | **Scan every row of every file.** No sampling, no certification by header. Report what is found. |
| D7 | **Cloudflare Access: one rule** — email domain `@interviewkickstart.com`. Everyone in the company sees the full graph. **No per-node filtering in the HTML render.** |
| D8 | **`graph.html` renders everything**, including cost and rating data. Nothing excluded or redacted at render. |
| D9 | **Still tag `sensitive: true`**, and build the render filter as a **config flag defaulting to `off`**. The switch must exist even though it is not being used. |
| D10 | **Distribution: private repo + GitHub Organization + team.** Access managed centrally, not per-collaborator. `README.md` must state the **honest** first-time install cost — GitHub account → `gh auth login` → then the two plugin commands. **Do not claim "two commands" flat.** |
| D11 | **Offboarding note in README:** removing someone from the org stops *future updates* but does **not** remove the graph snapshot already sitting in their local plugin cache. |

### How D4 and D8 fit together
They are not in tension. Contact fields are dropped **at extraction**, so they never become node properties — there is nothing to redact at render time. Cost, rating and judgement data **do** enter the graph, are tagged `sensitive: true`, and **are rendered by default** per D8. The `sensitive` flag drives the default-off filter (D9) and nothing else in v1.

---

## Part 2 — Answers to the seven gate questions

### Q1 · Prove `Domain` (42) and `Program` (42) are disjoint

**They are disjoint. The matching 42/42 is coincidence.**

**Raw string intersection = 0.** Not one domain name equals a program name.

Under aggressive normalisation (lowercase, strip `EdgeUP`/`KYP`/`Interview Preparation Program`/`Engineering`/punctuation), only **14 of 42** domains find any program partner. That leaves:
- **28 of 42 domains with no program PDF at all**
- **20 of 42 programs with no domain**

**Five domains with no program:** `Coding Pathway` · `System Design Pathway` · `Coding TC` · `SysD TC` · `Career Coaching`
*(also: `Project- Up`, `India Masterclass`, `Extended Masterclass`, `Advanced ML Ops`, `FDE`, `GPM (Growth Product Management)`, `DABA`, `Flagship ML/ ML Program`, `ML Switch-up (Adv ML)`, …)*

**Five programs with no domain:** `Cloud Architect Interview Preparation Program` · `Full-Stack Interview Preparation Program` · `Advanced Machine Learning Program (with Agentic AI)` · `FastTrack_ (Self Paced) Ad. Machine Learning(with Agentic AI) KYP` · `v2 [New] AI Data Science Program`

**And the relationship is 1:N, not 1:1** — eight domains map to two programs each:

| Domain | Programs |
|---|---|
| `Backend` | `Backend Engineering EdgeUP KYP`, `Backend  Interview Preparation Program` |
| `Android` | `Android Engineering EdgeUP KYP`, `Android Engineering Interview Preparation Program` |
| `Frontend` | `Frontend Engineering EdgeUP KYP`, `Frontend Interview Preparation Program` |
| `iOS` | `iOS Engineering EdgeUP KYP`, `iOS Engineering Interview Preparation Program` |
| `Security` | `Security Engineering EdgeUP KYP`, `Security Engineering Interview Preparation Program` |
| `Test Engineering` | `Test Engineering EdgeUP KYP`, `Test Engineering Interview Preparation Program` |
| `Data Engineering` | `Data Engineering EdgeUP KYP`, `Data Engineering Interview Preparation Program` |
| `TPM` | `TPM EdgeUP KYP`, `TPM-KYP` |

A 1:1 renaming could not produce 28 orphans on one side, 20 on the other, and eight 1:2 fan-outs. **Confirmed disjoint; keep both types.**

**Revised per D5:** `KYP` becomes a **doctype**, so `TPM EdgeUP KYP` and `TPM-KYP` resolve to one product (`TPM`, EdgeUP) with **two KYP documents**, rather than two Programs. This reduces the program count and removes ambiguity #2 from doc 05.

---

### Q2 · Instance counts for `Instructor` and `Module`

I gave none before because I had not extracted them. Now measured across all 344 sheets. *(344 was correct when measured; the corpus is now **374 sheets / 75 files** after `UpLevel Schedule Structure.xlsx` was added mid-analysis — see BUILD_LOG round four.)*

#### `Instructor` — **1,088**

From five authoritative rosters, header-driven, positional read:

| Source | Name rows |
|---|---|
| `Instructors Directory.xlsx!Responses` | 650 |
| `SME database (For Ops + NP).xlsx!Master` | 538 |
| `New Combined Schedule.xlsx!Instructor Data` | 263 |
| `Resource Collection Mastersheet!Indian Instructors` | 24 |
| `Data and Management.xlsx!Instructor Details` | 22 |
| **Raw total** | **1,497** |
| **Distinct after case/punctuation normalisation** | **1,088** |

- **319** appear in more than one roster (cross-validated — good signal)
- **26** have case-only spelling variants (`ANKUR GUPTA`/`Ankur Gupta`, `Akhil Tomar`/`Akhil tomar`, …)

**A number I am deliberately not using: 7,506.** A naive scan of every column whose header matches `name|instructor|sme|primary|backup` yields 7,506 "plausible people" — but 5,387 of those come from the payroll file and 3,844 from `Operational Metrics`, i.e. employees, coaches and learners, not instructors. **Reporting 7,506 as the instructor count would be the exact failure mode we criticised in the reference implementation.** 1,088 is the defensible figure.

#### `Module` — **1,348 candidates / 234 confirmed**

| Measure | Count |
|---|---|
| Raw module-column values | 2,053 |
| After normalisation (stripping `Live Class`/`Assignment`/`Pre Class`/`Foundational`/`Alternative` resource-type suffixes) | **1,348** |
| **Appearing in ≥ 2 different files** (genuine modules, not one-offs) | **234** |

**Recommendation: build `Module` from the 234 cross-file-confirmed set in v1**, and route the remaining ~1,114 single-file candidates to a review queue. The long tail is dominated by row-level resource names, not module names.

Most frequent normalised modules: `online processing systems` (1,459 mentions), `sorting algorithms` (1,283), `recursion backtracking` (1,135), `batch processing systems` (575), `graphs and its variants` (490), `dynamic programming` (424), `multi agent orchestration` (181), `rag knowledge agents` (174).

---

### Q3 · `Tool` — justify or demote

**Demoted to a property.** Full working in doc 05; the summary:

The test that demoted `Alert` was **degree ≥ 2** — a degree-1 node adds a hop without enabling a traversal a property could not serve.

| | Nodes | Edges | Pass degree ≥ 2 |
|---|---|---|---|
| `Tool` | 6 | 8 | **2 (33%)** |
| `Alert` | 321 | 321 | **1 (0.3%)** |

`Tool` is ~100× better by pass-rate — **and still fails on absolute volume.** Eight edges across 92 workflows is a tag, not a relational layer, and only `Zoom` and `Uplevel` have any traversal value at all. *"What else uses Zoom?"* is answerable from a string property.

**Becomes `workflow.tools: [string]`.** Promotion trigger: if `Resource` nodes are added from the 30 curriculum sheets, `Tool` gains degree via `Resource → Tool` — revisit then.

*(Two errors corrected: there are 6 tools, not 5; Uplevel is in workflows `8.3`/`8.5`, not `4.8`/`4.15`.)*

---

### Q4 · `Person` — exact resolved count and the unresolved list

**62 raw person strings** across the owner sheet, the Slack-mapping sheet and all 17 `IAims` sheets.

**13 canonical people resolved from 25 strings:**

| Canonical | Variants |
|---|---|
| `Animesh Kumar` | `Animesh`, `Animesh Kumar` |
| `Adil Panwar` | `Adil`, `Adil Panwar` |
| `Shashi Bhushan Kumar` | `Shashi`, `Shashi Bhushan Kumar` |
| `M Prasad Khuntia` | `Prasad`, `M Prasad`, `M Prasad Khuntia` |
| `Utkarsh Raj` | `Utkarsh`, `Utkarsh Raj` |
| `Navdeep Singh` | `Navdeep`, `Navdeep Singh` |
| `Karthika S` | `Karthika`, `Karthika S` |
| `Srushith` | `Srushit`, `Srushith`, `Srusith` |
| `Swaroop` | `Swarup`, `Swaroop` |
| `Tanmaya` | `Tanmaaya`, `Tanmaya` |
| `Kalindi` | `Kalindi` (appears as `Kalindi .` in IAims) |
| `Simran Khemlani` | `Simran` |
| `Abhinav Rawat` | `Abhinav Rawat` |

**37 unresolved strings needing your confirmation.** Grouped by what I think is going on:

**(a) Almost certainly the long form of an already-resolved short name — confirm and merge:**
`Deval` + `Deval Purohit` + `Deval Mahesh Purohit` (all `IK-446`) · `Uday` + `Uday Mehtani` · `Srushith Kumar Donthoju` + `Donthoju Srushith Kumar` (name order reversed, `IK-418`/`IK-INT19`) · `Swarup Yeole` · `Tanmaya Kharyal` · `Prithika` + `Prithika K` · `Rakshit Kapoor`

**(b) Delivery-team first names with no long form anywhere — need surnames:**
`Abhishek` · `Anshuman` · `Harsha` · `Kunal` · `Muskan` · `Rupali` · `Sinchana` · `Sourish` · `Tamanna` · `Tushar` · `Pooja` · `Anmol`

**(c) `IAims` employees who never appear in the owner sheet — in scope or not?**
`Akshay Ginodia` · `Aman Arora` · `Amit Mishra` · `Bishal Roy` · `Harsh Arora` · `Harshita Tanwar` · `Rishabh Bhardwaj` · `Siddharth R G` · `Sidharth Sundaram` · `Sweta Pandey` · `Vartika Rai` · `Vineet Patel` · `David Reed`

*(Note `Siddharth R G` and `Sidharth Sundaram` — different spellings, probably different people. Flagged, not merged.)*

**Total `Person` estimate: 13 confirmed + 37 pending = up to 50**, against my earlier guess of ~28. The guess was low because I had only read the owner sheet, not all 17 `IAims` sheets.

**And the keying recommendation is reversed** — see doc 02. Key on a curated slug; keep IDs as evidence only.

> **CORRECTED 2026-09-09 — the "not unique" argument was thinner than it read.**
> This line originally said IDs are "not unique (`IK-294` = two people;
> `IK-INT30` = two people)". Both statements are literally true and materially
> misleading. Exhaustive check of every `ENo`→name mapping across all nine
> quarter sheets found **6** ids mapping to more than one name string:
>
> | ENo | Rows | What it actually is |
> |---|---|---|
> | `IK-418` | 60 | **Not a collision** — two spellings of `Donthoju Srushith Kumar` |
> | `IK-446` | 58 | **Not a collision** — two spellings of `Deval Mahesh Purohit` |
> | `IK-915` | 18 | **Not a collision** — `Prithika` / `Prithika K` |
> | `IK-294` | 88 | Real, and **one stray cell**: Prasad 87, Swarup Yeole 1 |
> | `IK-INT30` | 10 | Real, and **one stray cell**: Prithika 9, Rakshit Kapoor 1 |
> | `(BLANK)` | 13 | Not an id at all |
>
> So three of the six are alias pairs, and the two genuine collisions are single
> typos. **The keying decision stands regardless**, on two grounds that are
> structural rather than clerical:
>
> - **Blank ids.** `Yash Mathur` has 11 rows and *all eleven* are blank — normal
>   HR lag for a recent joiner, and every future joiner will present the same
>   way. This is sufficient on its own.
> - **Unstable ids.** `Animesh Kumar` carries `IK-INT16` and `IK-398` — an
>   intern-to-FTE renumber. Real, and it will recur.

---

### Q5 · Hop paths that exist, and how many multi-hop questions survive

#### ⚠ The structural consequence: the graph is in two disconnected components

With `Workflow → Person` gone, nothing joins the workflow world to the delivery world except `File` nodes.

**Component A — "how we work" (from the master file):**
```
Theme ←belongs_to— Workflow —depends_on→ Workflow
                   Workflow.{alerts, tools, effort, steps}   (properties)
```

**Component B — "what we run" (from the spreadsheets):**
```
Person ←owned_by— Domain —supported_by→ Person
                  Domain ←part_of— Program ←part_of— Module ←teaches— Instructor
                  Program —has_doc→ KYP (doctype)                     [per D5]
```

**The only bridge is `sourced_from → File`**, and it is a weak one: all 92 workflows share a single `File` node, so traversing A→B through it means passing through a hub with degree 92. That is not a meaningful path, it is a hairball.

**This is the real cost of D2**, and it is worth stating plainly: the graph answers "how do we do X" and "who runs Y" well, and cannot answer anything that crosses between them.

#### Surviving hop paths

| Path | Component | Example |
|---|---|---|
| `Workflow → Theme` | A | workflow 8.2 → OPS |
| `Workflow → Workflow` (`depends_on`) | A | 3.6 → 3.1 |
| `Theme → Workflow → alerts/effort/tools` | A | theme 2 → 9 workflows → alert text |
| `Domain → Person` (`owned_by` / `supported_by`) | B | Cloud → Animesh Kumar |
| `Person → Domain → Program → Module` | B | Animesh → Security → Security EdgeUP KYP → Applied Cryptography |
| `Instructor → Module → Program → Domain → Person` | B | Anshaj Khare → Python for GenAI → … |
| `Program → KYP doc` | B | per D5 |
| `* → File` | bridge | citation only |

#### Multi-hop eval questions: **8 of 8 survive**

| Q | Route | Component | Verdict |
|---|---|---|---|
| Q9 | theme → workflows → alert text | A | ✅ |
| Q10 | tools property → workflows | A | ✅ *(now a property lookup, not a hop)* |
| Q11 | person → alias → domains | B | ✅ |
| Q12 | domain → person; domain → program → module | B | ✅ |
| Q13 | alert clause → workflows | A | ✅ |
| Q14 | workflow → alerts | A | ✅ |
| Q15 | module → instructor → rating | B | ✅ |
| Q16 | tool property → workflows | A | ✅ *(second half is file observation, not traversal)* |

**All eight survive because none of them crosses A↔B.** That is partly luck and partly that I wrote the set after finding the ownership gap. Only **Q17** needed the missing edge — and it is already in the unanswerable set, which is now doctrinally correct given the `domain-owner` rename.

**The honest caveat:** a question like *"which domains are exposed by workflow 3.7 having no owner?"* is unanswerable and will stay unanswerable in v1. If that shape matters, D2 needs revisiting.

---

### Q6 · Reconcile the reference graph: 773 claimed vs 351 observed

**773 appears in no shipped artefact. It is a stale prose number.**

I tested the obvious hypothesis — that 773 was a pre-dedup candidate pool later merged to 351 — by downloading `knowledge/instr_candidates.json`:

| Artefact | Instructors |
|---|---|
| `knowledge/graph.json` `meta.instructors` | **351** |
| `knowledge/graph.json` actual instructor nodes | **351** |
| `knowledge/instr_candidates.json` | **351** |
| `plugin.json` description (prose) | 773 |
| `marketplace.json` entry description (prose) | 773 |
| Website | 773 |

Set comparison between the candidate pool and the graph: **intersection 351, in-graph-not-in-pool 0, in-pool-not-in-graph 0.** They are the *same set*. There was no 773→351 merge; the pool file is post-dedup.

**Conclusion:** 773 is a leftover from an earlier build, propagated into three hand-written descriptions and never regenerated. Same failure as `1,072 files` (actual 1,833) and `61 clients` (actual 32).

**So the 8% junk figure stands, and is if anything understated.** The 27 non-people are present in **both** the graph and the candidate pool — they were never filtered at any stage. Rate: **27/351 = 7.7%**.

**A related correction to my own doc 04:** I reported provenance as 15%. That counted the *presence* of the `sources` key. Counting non-empty values, **280 of 351 instructors have an empty source list** — real provenance is **71 of 2,314 nodes = 3%**.

---

### Q7 · How the plugin path rule constrains B3's corpus handling

**First, a precision point on the mechanism.** The documented rule is about **plugin component resolution** — manifest-declared paths for skills, commands, agents, hooks. Those are rejected with `"path escapes plugin directory"`, and the plugin then loads *without that component*. It is not an OS-level sandbox: a Python script a user runs via Bash has ordinary filesystem access.

**But your practical conclusion is right, and it comes from a second fact that bites harder:** the corpus is not inside the plugin, so **it is never copied into the plugin cache at install**. A teammate who installs `np-autopilot` gets `knowledge/`, `skills/` and `pipeline/` — and **no corpus**. Whatever the loader permits, the files are simply absent.

**Four constraints on B3:**

1. **Hard build-time / query-time separation.** `pipeline/01_walk_corpus.py` runs only on a maintainer's machine where the Drive folder is synced. **No skill and no query-time code path may read the corpus.** Everything a teammate needs must be baked into `knowledge/graph.json` and `knowledge/files.json` at build time. If a skill ever needs a fact, it goes into the graph — there is no fallback to "go read the file".

2. **`files.json` paths are citations, not handles.** A stored absolute path (`/Users/animesh/Desktop/NP-Autopilot-Corpus/...`) is meaningless on a teammate's machine and leaks the maintainer's home directory. **Store the corpus-relative path** (`00-master/Domains_Courses Owners.xlsx`) as the citation, plus `sheet`/`row` or `page`. Optionally store a Drive URL as the clickable form. Absolute paths, if kept at all, go in a build-local field that is not shipped.

3. **Corpus root comes from configuration, never a literal.** `NP_CORPUS_PATH` env var with a documented default, read in one place (`pipeline/lib/paths.py`). Never hardcoded, never in a skill, never in `plugin.json`. `${CLAUDE_PLUGIN_ROOT}` is for `knowledge/` only — and per the docs it is *ephemeral* and must never be written to.

4. **`setup` must diagnose the difference.** "Graph missing" (packaging problem) and "corpus missing" (expected on a teammate's machine, and fine) are different conditions with different fixes. `setup` should report graph counts and build date, and must **not** try to reach the corpus at all.

**Consequence for `01_walk_corpus.py`:** it takes the corpus root as an argument, asserts read-only, and emits only relative paths into `files.json`. That satisfies both the loader rule and the not-bundled reality.
