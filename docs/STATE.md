# STATE — working brief for a session with no memory

You are continuing `np-autopilot`: a knowledge graph over Interview Kickstart's
New Programs corpus, projected into Supabase Postgres, served by a Vercel web
app behind Google Workspace sign-in.

**Read this, then [`A7B.md`](A7B.md), then
[`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md), then
[`PRE-CRAWL-DECISIONS.md`](PRE-CRAWL-DECISIONS.md). In that order, before
anything else** — §11 repeats it with the reasoning.
[`SCALE-PLAN.md`](SCALE-PLAN.md) is the framing document and its four questions
are still open; the two above it are newer and narrow three of them.

Everything here is current as of 2026-09-20. Where a number is measured rather
than assumed, it says so.

**This document has been wrong twice, both times in the same way — a claim that
outlived its condition.** It said the graph had 5,048 nodes (the pipeline
graph's count, not the projection's), and it said `--scope full` was blocked by
R18 (a blocker that existed in prose and nowhere in the program). Both are
corrected below. Treat every number here as *measured on a date*, and the dates
matter.

---

## 1 · Where the system stands

### Live and verified against production

| | |
|---|---|
| **Explorer** | <https://np-autopilot.vercel.app> — 200, serves the graph UI |
| **API** | `/api/config` 200; `/api/{search,node,neighbourhood,overview,coverage,staffing,aliases,me}` all **401 unauthenticated**; `/api/curate` 405 on GET, 401 on POST; `/api/session` 401/400/403 on bad input |
| **Latency** | **44.3 ms** warm server-side median (n=18), from 2,252 ms. Functions pinned to `icn1`; the database is in `ap-northeast-2`. `LATENCY-MEASUREMENT.md` separates measured from inferred |
| **Tests** | **330 passing, 2 skipped**, measured 2026-09-20 (8m51s). One skip is the live-header check, opt-in via `NP_VERIFY_URL`. Both `drive_dom.mjs` targets green |
| **Sign-in** | Works end to end. Google Workspace → `/api/session` → GoTrue → Supabase session → RLS |
| **Security headers** | All six present on the deployed response: CSP (no `unsafe-inline` on `script-src`, inline blocks pinned by SHA-256), HSTS, `x-frame-options: DENY`, nosniff, no-referrer, permissions-policy. Plus `Cross-Origin-Opener-Policy: same-origin-allow-popups` |
| **Service-role key** | **Zero occurrences** in the shipped bundle, and the variable is not set in the Vercel project at all. That bundle scan is the evidence — not the unit test, which until 2026-09-18 scanned `web/` while the routes live in `api/` and so proved nothing. Now covers both; see `DEPLOYMENT.md` and [`A7B.md`](A7B.md) instance 8 |

### Verified locally only — do NOT describe these as production-verified

- **Render and layout cost.** Never measured, in any region. §4.
  (In-region *latency* is now measured — `LATENCY-MEASUREMENT.md`.)
- **The full test suite** (330 passing, ~9 min) runs against the real Supabase
  but from a laptop, not from Vercel.
- **Everything in `pipeline/`.** It has never run on Vercel and is not meant to.

### The data

| | |
|---|---|
| Graph in Postgres | **3,146 nodes / 4,021 edges** (public half only) |
| Provenance | 30,658 `node_sources` rows over **74 files** |
| Curation | 20 people, 15 confirmed aliases + 6 unresolved, 92 workflow owners, **45 `curation_notes`** |
| Sensitive | **Zero rows projected.** `--scope full` refuses — but **not for the reason this table used to give.** R18 appears nowhere in `project_graph.py`; the program's own blocker was a hardcoded claim that the `recruiting` RLS path was missing, and that path **exists** (`nodes_recruiting_select`, `np_can_see_sensitive()`). Both claims outlived their conditions. The refusal is now derived, and refuses on the real ground: the **decision** is unrecorded — `docs/INGEST-SCOPE-REVERSAL.md`, approval block blank. [`A7B.md`](A7B.md) instance 9 |
| Migrations | **0001–0016 applied.** `python3 pipeline/migrate.py status` |
| Drive links | **74 of 74** files resolve. The ids were in pass 0's manifest since the beginning and nothing carried them forward |
| Profiles | **4 rows, 3 of them ORPHANED** — the `auth` schema was emptied 2026-09-20 and the surviving profiles point at user_ids that no longer exist. One live `admin` (re-granted 2026-09-21). See §10 and `AUTH.md` §"The durability clause has fired". Previously 1 `admin`, 1 `member`. The shared account is `is_shared_account=true` and correctly capped — it cannot hold `recruiting` or `admin`. **`member` is now granted automatically** at signup (migration 0015); `recruiting` and `admin` stay manual |

### TWO GRAPHS, DIFFERENT COUNTS — this confusion has already cost three numbers

The most common mistake in this project's own documents is carrying a figure
from the **pipeline graph** into a statement about the **projection**. They are
not the same graph and never were.

| | Pipeline graph | Projection (what the web app sees) |
|---|---|---|
| Nodes | **5,048** | **3,146** |
| Edges | **36,677** (89% provenance) | **4,021** (no provenance at all) |
| As JSON | 11.0 MB (`graph.json`) | **526 KiB** in the shape the API returns |
| Includes | `file` nodes, `sourced_from` edges, 1,902 sensitive nodes | none of those |
| Described by | `AUDIT.md`, `DECISIONS.md` §"The measurements…", `README.md` | `STATE.md` §1, `LATENCY-MEASUREMENT.md`, `web/lib/data.py` |

**Three figures were wrong for exactly this reason**, found 2026-09-18 while
specifying the default view:

- **"largest connected component = 1,144"** — that is `AUDIT.md` §247, measured
  on the pipeline graph with provenance excluded. Measured on the projection it
  is **1,881** with declared-expertise edges, **1,317** without. Both exceed the
  client's `nodeBudget` of 1,200, which is what ruled it out as a default view.
- **"the traversable subgraph is 1.2 MB"** — pipeline node shape. The API's
  shape is **526 KiB**.
- **"shipping all 5,048 nodes"** (was in `public/index.html`) — the client can
  never receive 5,048. Sensitive rows are not projected at all.

### A fourth stale number, different cause, same lesson

**`05-taxonomy-proposal.md` §92 says the Uplevel/Drive resource links are "158
mentions across 30 curriculum sheets".** Measured 2026-09-18: **226 distinct
Drive/Docs URLs across 2 workbooks** — `Data and Management.xlsx` (150) and
`Resource Collection Mastersheet (Software + System).xlsx` (76). By kind:
presentation 59, document 59, spreadsheets 54, drive 50, file 4.

Not the two-graphs confusion — just a number written once and never
re-measured. It matters because that line is the **Tool promotion trigger**: it
is the evidence for whether `Resource` earns a node type, and the decision was
resting on a figure that was wrong by 43% and wrong about the shape (2
workbooks, not 30 sheets).

**Before quoting any count, say which graph it is about.** If a number comes
from a document in the left column and the sentence is about the explorer, it is
probably wrong.

---

## 2 · Account topology, and why it bites

Three different owners. Almost every operational surprise so far traces back to
this table.

| Thing | Lives under | Identifier |
|---|---|---|
| **GitHub** | `ANI-IN` (personal) | `ANI-IN/np-autopilot`, private, repo id `1374030791` |
| **Vercel** | `b2c-courses-new-programs@interviewkickstart.com` (shared) | project `np-autopilot`, `prj_Imn4VGzZLPgeRH0TaOiyJAGxrzNZ`, scope `b2c-courses-new-programs-4557s-projects` |
| **Supabase** | same shared account | ref `yqmzjgzhxhihnpbgqmeh`, region **ap-northeast-2 (Seoul)** |
| **Google Cloud OAuth** | same shared account | consent screen **Internal** |

### The consequences, in the order you will hit them

**1. Deploys only work from a `.git`-less copy.** The Vercel CLI tries to link
the GitHub repo, which is under a different account, and fails. The working
procedure is to copy the tree to `/tmp` without `.git` and deploy from there.
Deploying from the repo directory does not reliably produce a Ready deployment.

**2. `vercel ls` lies about status.** Deployments routinely report `UNKNOWN`
with duration `?` while being live and serving traffic. **Do not treat UNKNOWN
as failed.** Check the live URL instead:

```
curl -s -o /dev/null -w '%{http_code}\n' https://np-autopilot.vercel.app/api/config
```

A great deal of time was lost treating UNKNOWN as a deployment failure when the
site was already serving the new build.

**3. Dashboard "Redeploy" hits the Pro wall.** Redeploying from the Vercel web
UI is not available on this plan. Use the CLI.

**4. The shared account is several people.** Whoever can sign into it can read
every Vercel environment variable and promote deployments, and the Vercel audit
log names an **account, not a person**. This is the same attribution gap
migration 0008/0014 addresses for `recruiting`. It is recorded, not fixed —
`DEPLOYMENT.md` §"The shared account" explains why the mitigations are
organisational.

**5. Do not add collaborators** to the GitHub repo. §F of `DECISIONS.md`: there
is no read-only tier, and the history contained the hiring funnel.

### Local environment

Secrets live outside the repo:

```
~/.config/np-autopilot/env          # SUPABASE_DB_URL_SESSION / _TRANSACTION
~/.config/np-autopilot/drive-sa.json  # Drive service-account key, mode 600
```

Load them with `set -a && . ~/.config/np-autopilot/env && set +a`. **Never read
the service-account key into output, never echo it, never write it into the
repo.** Reference it by path only.

**`NP_SHARED_ACCOUNTS` is deliberately no longer read by `pipeline/`.** The list
lives in the `shared_accounts` table (migration 0014). See §5.

---

## 3 · Commands you will need

```bash
set -a && . ~/.config/np-autopilot/env && set +a

python3 -m pytest tests -q                  # 332 tests, ~9 minutes
node eval/drive_dom.mjs                     # hosted explorer harness
node eval/drive_dom.mjs knowledge/graph.html  # offline build harness

python3 pipeline/migrate.py status          # migrations 0001-0015
python3 pipeline/verify_migration.py --source supabase --scope public   # 32 checks
python3 pipeline/curation.py roundtrip      # determinism + losslessness + comments
python3 pipeline/curation.py check          # DRIFT: database vs YAML, no import
python3 pipeline/grant_access.py list       # who has access, who is waiting

vercel logs --since 1h --status-code 500    # runtime tracebacks
vercel logs --since 1h                      # audit lines carry per-request `ms`
```

**The test suite is slow because of geography** (~148 ms per statement to
Seoul), not because anything is wrong. If it stalls rather than runs slowly,
see §6.

---

## 4 · Long-running open items, each with its current state

### R18 — the repository was public for eight days

**Status: remediated. The GitHub package is closed; one Drive question
remains.** Found 2026-09-17; set private, then deleted and recreated (old id
`1363038448` → new `1374030791`). History rewritten. What was readable: 3,817
instructor names including **277 named hiring rejections** and 1,625
mid-pipeline candidates.

**Traffic calibration: ANSWERED 2026-09-18.** The repository page was never
opened in a browser during the window — all work went through the CLI. So the
0 clones / 0 views figure is **consistent with the recorded working method
rather than in tension with it**, and the damaging reading (an instrument
reporting zero for a session that certainly occurred, and therefore unreliable)
is withdrawn. **The ceiling is unchanged:** zero recorded traffic is still not
evidence of zero copies — the API misses automated fetches, and `git clone`
leaves no entry an owner can read. Treat the exposure as *unknown but not
demonstrably exploited*, never as *nobody accessed it*. `07-risks.md` R18.

**Also unanswered: whether the Drive folder was ever domain-wide.** It is
`Restricted` now. If it was previously domain-wide there is an exposure to
record; the R18-shaped record is written out ready to complete in
`CACHE-EXPOSURE.md` §0a. The window **end** is known and the **start** is not,
so it cannot be described as short.

### Check 3 of the post-deploy list — unrun

`DEPLOYMENT.md` ends with four checks. Three are done. **Check 3 is not:** sign
in with a personal Google account carrying an `@interviewkickstart.com` address
and confirm it is refused with a message naming the `hd` claim. This is the case
`email.endsWith()` accepts and we do not.

It is hard to exercise because the consent screen is **Internal**, so Google
refuses such an account before a token is ever issued (see `AUTH.md` layer 0).
That is a stronger outcome, not a substitute — layer 0 is a console setting with
no signal in this repo, and `hd` still catches a Workspace account whose email
claim disagrees.

### In-region latency — MEASURED 2026-09-18; render cost is not

Measured from a laptop, as `authenticated` with a `member` profile so RLS is
included:

| Endpoint query | Round trip (laptop) | Server-side |
|---|---|---|
| `search` | 191.3 ms | **4.62 ms** |
| `node` | 149.3 ms | 0.22 ms |
| `provenance` | 150.5 ms | 0.53 ms |
| `neighbourhood` d1 / d2 / d3 | 151 / 154 / 182 ms | 0.67 / 0.99 / 4.87 ms |

~148 ms of each is geography. **That is now closed.** `vercel.json` is pinned
to `icn1`; warm server-side median went **2,252 ms → 44.3 ms** (~51x). Full
record, with measured/inferred separated line by line, in
`LATENCY-MEASUREMENT.md`.

**What is still unmeasured is render and layout**, and it is now the largest
unknown in user-visible latency. The browser harness that would have measured it
never ran — Chrome refused to expose a debugging port. **Do not read the server
number as "the app is fast."**

### One unenforced schema invariant — recorded, not applied

`node_sources` constrains three of the four implications that keep a
hand-entered fact distinguishable from a scanned one. The fourth is missing:

```
corpus -> evidence IS NULL        <- not enforced
```

So a hand fact mislabelled `origin: corpus`, carrying its evidence string,
passes every constraint. Measured: **0 of 30,628 corpus rows carry evidence** —
the invariant holds in the data, it is simply not enforced. The fix is one
constraint in a new migration, written out in [`A7B.md`](A7B.md). It guards
§A.5's prohibition, which is the most load-bearing rule in the project.

### The three aliases — unresolved, deliberately

`ML` (153 claims), `Agentic AI` (64), `Product Management` (50), plus
`Applied Gen AI` (42), `Advanced Gen AI` (16), `Career` (13).

**Do not resolve them.** `lib/resolve.py` returns `Ambiguous` by default because
three shipped bugs had the same shape: several plausible targets, one chosen, no
signal to the caller. These need a program owner at IK.

**`Agentic AI` cannot be resolved from data at all**, and this is the important
one. The corroboration signal — do the people who wrote this alias also point at
the candidate domain by another route — is **0 of 64**. Not weak; absent. The
raw strings are role suffixes (`- EM`, `- SWE`, `- TPM/Pm`), which are not
discriminators. For `ML` it is 75 of 140 and for Product Management 4 of 51.
Waiting for better data will not help; only a human decision will.

The surface that presents them (`web/lib/curation_service.py::ambiguous_aliases`)
returns evidence and **deliberately no ranking**, because a UI that ranks
candidates reintroduces the picking one layer up.

---

## 5 · Decisions that must not be silently reversed

| # | Decision | Where |
|---|---|---|
| **Q1** | Drive ingestion is **live** — service account, `drive.readonly`, no delegation. Pass 0 ran: 75 files, 0 failures | `DECISIONS.md` §0 |
| **Q2** | **Split source of truth.** Curation authored in Postgres; the derived graph stays pipeline-built and is *projected* | §0, §B.1 |
| **Q3** | **Two roles from day one** — `member` (called `viewer` in §D) and `recruiting`. `admin` exists for curation writes | §0, §D |
| **Q4** | GitHub stays `ANI-IN/np-autopilot`, personal, **no collaborators** | §0, §F |
| **Q5** | Plugin model: cached snapshot + authenticated API for anything sensitive or write-shaped | §0, §E |
| **Q6** | **Workflow management is OUT OF SCOPE** | §G |

**Also load-bearing, and each was learned the hard way:**

- **Thresholds may rank or warn. They must not silently exclude.** Two cutoffs
  hid correct answers; six name-shape filters dropped ~330 real people, with a
  bias that correlated with holding a PhD and with South Asian naming patterns.
  `CLAUDE.md` §4.
- **The corpus is READ-ONLY.** Filename typos are load-bearing citation keys.
  Never widen the Drive scope.
- **Counts are floors, not totals.** 127 of 374 worksheets have been read by an
  entity scan. `person`, `instructor`, `module` carry `expect: null` for this
  reason.
- **Hand-entered facts carry `origin: hand`**, never emit `sourced_from`, and
  must remain **visibly distinct in any UI** from scanned facts.
- **Sensitive nodes are not projected at all**, and the refusal is now *derived*
  rather than asserted: `project_graph.py` queries `pg_policies`/`pg_proc` for the
  recruiting path, and refuses on the ground that actually holds — the **decision**
  is unrecorded (`INGEST-SCOPE-REVERSAL.md`, approval block blank). The old
  "while R18 is open" reason was never in the program.
- **D4's contact strip is NOT what keeps contact data out of the graph.** It was
  inert — one caller, wrong namespace, equality matching. What holds is
  `sources.py`'s allow-list: extraction reads 20 declared columns, all name
  columns. **The stated control fails open; the real one holds by accident**,
  and it was chosen for coverage rather than safety. Hardened 2026-09-19 — the
  pattern list is now an allow-list with substring matching and header
  normalisation, and `property_scopes` refuses an unclassified property at
  projection time. [`A7B.md`](A7B.md), "the control that never worked".
- **Never the direct `db.<ref>.supabase.co` connection.** IPv6-only on this
  project: works on a laptop, fails on Vercel. Refused at runtime and greped in
  CI.
- **Transaction pooler (6543) with `prepare_threshold=None`** for anything
  request-scoped; session pooler (5432) for migrations only.

---

## 6 · Traps that have already cost hours

- **A blocked `TRUNCATE` presents as a hung process, not an error.** If the test
  suite stalls, look for a session `idle in transaction` holding a lock —
  usually from a previously killed run. Terminate it; do not kill more runs.
- **`vercel ls` reporting UNKNOWN does not mean failed.** Check the live URL.
- **The local `.vercel/python` venv corrupts**, after which `vercel build` fails
  while `vercel deploy --prebuilt` happily uploads the *stale* output. `rm -rf
  .vercel/python` before rebuilding.
- **Never name a script after a stdlib module** in `pipeline/` — `inspect.py`
  cost a full run.
- **`/*.json` in `.gitignore` is deny-by-default at the repo root.** It once
  swallowed `vercel.json`, which would have deployed the app with no security
  headers while looking completely correct. `tests/test_gitignore_blast_radius.py`
  makes a repeat loud.

---

## 7 · Pointer map — which document answers which question

| Question | Read |
|---|---|
| **About to write or change a guard?** | [**`A7B.md`**](A7B.md) first — moved out of `DECISIONS.md` 2026-09-20. **Ten** instances of one failure pattern, the three questions that find the eleventh, and why the best-told instances are the least useful. Read it *before*, not after |
| **About to build for 2,000 files?** | [`SCALE-PLAN.md`](SCALE-PLAN.md). Four questions recorded unanswered, and the fork between a search index over a known subset and a graph that guesses |
| **What is actually in the registry folders?** | [`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md) — measured 2026-09-20. The three folders are three different data contracts; five shapes of contact data, four of which `sources.py` cannot reach; and a measured demonstration that instructor names on decks cannot be told from template placeholders |
| **About to write the crawler?** | [`PRE-CRAWL-DECISIONS.md`](PRE-CRAWL-DECISIONS.md) — five decisions taken 2026-09-20, **three of which reverse or constrain behaviour that already exists in code**. Read it before `00_fetch_drive.py` is touched |
| Why is the schema shaped this way? | `DECISIONS.md` §A |
| How does curation sync with Postgres? | §B, and `pipeline/curation.py` |
| What can run on Vercel, and why these poolers? | §C |
| How does auth work, and what does each layer NOT do? | `AUTH.md`, then §D |
| One app or two? | `ONE-APP-OR-TWO.md` |
| How do I deploy, and what is the shared-account risk? | `DEPLOYMENT.md` |
| What was exposed, and what is still unknown? | `CACHE-EXPOSURE.md`, `07-risks.md` R17/R18 |
| What does the pipeline do, end to end? | `docs/AUDIT.md`, `pipeline/README.md` |
| Why is this count a floor? | `CLAUDE.md` §2, §2a |
| What is the taxonomy and why? | `05-taxonomy-proposal.md`, `08-decisions-and-answers.md` |
| Why does a threshold rank instead of filter? | `10-threshold-audit.md`, `CLAUDE.md` §4 |

---

## 8 · The next phase — the agreed plan

**All five are DONE**, in the order agreed. Recorded 2026-09-18, finished
2026-09-19. Kept here rather than deleted because each entry records *why* the
thing was built the way it was, and three of them turned on a measurement that
contradicted the plan. What is open now is §10.

### 1. The sign-in flash — DONE 2026-09-18

Block 0 of `public/index.html` now resolves the session **synchronously before
first paint**: a `localStorage` read and an `expires_at` comparison. The check
may only ever HIDE the gate, and only on positive evidence of an unexpired
token — missing, corrupt, no `access_token`, throwing storage, expired all fall
through to the sign-in card. It grants nothing; `boot()` still verifies against
`/api/me`.

Six states are asserted in `eval/drive_dom.mjs`, not just the signed-in one:
"hide whenever a value is present" and "hide unconditionally" both pass the
positive case, so only the expired/expiring/no-token/corrupt cases distinguish a
correct check. Verified by mutation in both directions.

### 2. The empty default view — DONE 2026-09-18

**The choice: every domain, plus the people who own or deliver it.** 65 nodes,
98 edges, ~34 KiB, served by `/api/overview`.

**The reason.** It is the taxonomy's own top level, so expanding from it is the
natural traversal and every existing affordance works unchanged; it answers
"what are the areas and who runs them" in one screen; and at 65 nodes it
satisfies every §G2-preserved constraint without renegotiating one — 5% of
`nodeBudget`, `CAP = 8` is natural for one or two owners, and the cooling
schedule settles it immediately.

**Not the largest connected component**: measured at **1,881** nodes (1,317
without declared-expertise edges), both over the 1,200 budget. The 1,144 figure
that made it look viable was from the pipeline graph — see §1.

**`showIso` now defaults ON**, deliberately. Nothing in the default view is
isolated today, so it costs nothing; it exists so a domain that nothing points
at can never silently vanish from the landing page.

**Three domains have no owner** — Coding Pathway, India Masterclass, System
Design Pathway — and `/api/overview` **names them**. The original plan was to
let them appear as isolated nodes; measuring killed that, because every domain
has a *deliverer*, so once `delivered_by` is included nothing is isolated and
the gap renders identically to a healthy domain. That is the `A7B.md` shape, so
the count is derived from the edges instead.

**The endpoint is bounded and cannot be widened by a caller** — node type and
relations are module constants, it takes no parameters, and two tests fail if
that changes. `DECISIONS.md` §A.3a is the reasoning: A.3 made the provenance
join unwriteable *server-side*, but a bulk-download client routes around the
query layer entirely, so that is what "never ship the whole graph" now rests
on.

### 3. Speed — DONE for the server half, 2026-09-18

**Measured, then fixed, in that order.** The cost was flat with respect to rows
returned, which is what identified it as per-request overhead rather than query
cost. `vercel.json` is pinned to `icn1`: **2,252 ms → 44.3 ms** warm median.
`LATENCY-MEASUREMENT.md` is the record.

**The render half is untouched and unmeasured.** That is the remaining work on
this item, and it needs a browser.

> **The precedent that makes this rule non-negotiable:** `coverage` once
> measured 1,610 ms. That was cold buffers, not the plan. Warm it was 18.8 ms.
> Optimising the first number would have chased the wrong thing.

**The hypothesis held, and the arithmetic behind it did not.** The function did
run in `iad1` against a Seoul database. But the projection that a region pin
would yield ~2 ms was wrong about the mechanism: a request is ~11 round trips,
not one, because `request_connection` opens a fresh connection and issues two
setup statements before the query. Right about the region, wrong about what the
region multiplied. Hobby permits a single region, any region — multi-region is
Pro and above.

### 4. Auto-grant `member` on first sign-in — DONE 2026-09-18 (migration 0015)

An `after insert` trigger on `auth.users` writes a `member` profile for any
identity whose email domain is `interviewkickstart.com`. All three conditions
are met and tested, not argued: `recruiting`/`admin` stay manual (the trigger
writes the literal `'member'`), 0014's derivation and 0008's cap still apply,
and a non-IK identity gets nothing.

**Recorded as a reversal in `AUTH.md`**, because it changes what "a profile
grants access" means. The short version: the manual step read as a security
control and was not one — layer 3 had already refused every non-Workspace
identity before the user row existed. What it gated was membership of the
company, which layers 0 and 3 decide. It never gated `recruiting`, and that
stays manual.

**In the schema, not `/api/session`**, because writing a profile from the
session route needs privileges the web app deliberately does not have — and
`AUTH.md` names the service-role key as layer 1's only leak path.

**Verified by mutation**, the way 0012 and 0014 were: rolling 0015 back reddens
the three grant tests; `on conflict do update` reddens exactly the demotion
test; removing the domain guard reddens exactly the non-IK test. `do nothing`
and `do update` are one word apart and "a new user gets member" passes either
way.

**One asymmetry to keep in view.** Revocation is still immediate and still
durable: deleting a profile does not re-create it, because a re-login does not
re-create the `auth.users` row. **If that ever stops being true, this reversal
must be revisited** — a grant that reinstates itself is not revocable.

### 5. The sign-in page and the explorer UI — DONE 2026-09-18/19

**Landing page** (direction A of two, the graph-led one). Hierarchy from scale,
weight and space, because the CSP permits no external font and no icon set. The
hero is inline SVG in the explorer's own node-type colours, generated from
`stats.json` by largest-remainder apportionment so 60 circles carry the true
proportions — 36 instructor, 18 module, 2 workflow, one each of file, person,
domain, program. `theme` is 0.5% and rounds to zero even at 60; stated rather
than nudged.

**"What it will not tell you" gets the wider column and the larger type**,
because it is the section that earns the page. The two permanent sidebar panels
are gone — their content now appears where it triggers: the "not the whole
graph" note is a clause *on* the count it qualifies, and the "file search was not
carried over" note appears when somebody types a filename into a box that
matches labels.

**Six type-specific views**, shaped by the four properties the coverage report
identified rather than listing them. Relationships are grouped by relation with
per-edge detail. Hash routes, node only.

**Provenance is grouped by file**, collapsed, leading with *"cited in N files"* —
which is the cross-validated signal, and what a flat list of 152 rows buried.
The grouping is presentational only; §A.4 is why the duplicates must not be
deduped at source.

**The curation surface** (admin only): claims, sibling test, recorded reasoning,
candidates in the corpus owner's recorded order with `existing_expert_in_edges`
and `taught_modules` so blast radius is visible before the decision. No
recommended, no best, no score. The reasoning gates the button and is persisted
into the row, not only the audit table, because `curation.py export` writes the
table back to YAML and a decision whose reasoning lived only in the audit would
return as a bare mapping.

---

## 9 · What the four properties mean for any new view

Measured 2026-09-18. **Coverage decides the rendering**, and getting this wrong
is how a field becomes a lie.

| property | coverage | rule |
|---|---|---|
| `basis` on `expert_in` | **100%** (1,066 self-declared / 89 HR record) | state it every time |
| `inferred` on `contains` | **100%** — every program→module edge | state it every time |
| `cross_validated` on instructor | **100%** (746 true / 1,169 false) | state it every time |
| `review` | **3.4%** | **present-only, and NEVER a clean bill** |
| `avg_rating` on `teaches` | **1.7%** | present-only, **omitted** when absent — not dashed, not zeroed |

The `review` rule is the subtle one: 96.6% are unflagged because nobody looked,
not because they were checked and cleared. A "no issues" badge claims an
assessment the data cannot support. `avg_rating` is the same trap from the other
side — **a field rendered at low coverage reads as absence rather than as
not-extracted.**

---

## 10 · Open items from the current phase

### Approved, awaiting the approval block — payroll ingestion

`docs/INGEST-SCOPE-REVERSAL.md`. Scope is **(1) only** — the cost file, not
contact fields. The block is deliberately blank and **nothing is extracted until
it is filled in**; `project_graph.py --scope full` refuses and points at it.

Two things on record there that matter more than the scope: **the file contains
4,697 email occurrences**, so approving it without field-level minimisation
partially reverses a decision explicitly declined — and **condition 1 is not a
fifth condition**, because `nodes_recruiting_select` keys on `sensitive`, so
declining it voids recruiting-only rather than standing beside it.

Minimisation, agreed: keep the 18 labour codes, `Base Rate`, `Hourly Rate`,
`Hours Amount`, a person key. Drop everything else, including every email column.

### Declined and recorded — LinkedIn

`docs/CONTACT-DATA.md`. All three populations: the 20 NP staff (no question
stated), the 497 instructors who have taught (**four times acceler's 123**, and
the bind is structural), and all 3,817 (not close). The extraction-time identity
key was **also not built**, because checking showed it cannot reach the problem:
person resolution is explicit-alias-only, fuzzy proposes and never applies, and
the one real false-merge risk lives in a file with no LinkedIn column.

### Costed, not started — untracking `knowledge/graph.json`

`docs/UNTRACKING-GRAPH-JSON.md`. **2–3 days, not a week**, and the week is the Q5
hybrid which untracking does not force. **The digest manifest is a condition, not
a mitigation.** Deliberately not started: the type views and session extraction
change what the graph holds, and the diff should not be missing while that is in
flight.

### Queued, not next — session metrics as an edge time series

**Superseded as "next" by the fork A crawler (§11), not cancelled.** It is still
the best-specified unbuilt thing in the project, and the poll workbooks it
depends on are two of the registry's five rows — so the crawler and this item
now share a source, and doing the crawler first is what makes this cheaper.

4,046 sessions, 4,082 rated rows, 2023-10-01 → 2026-08-30. **Not a node type** —
that is +129% nodes for a leaf nothing traverses to, which is the Alert mistake.
**Exclude `T.A Ratings` and `TA RAW` explicitly**: they carry `Student Name` and
`Student Email`.

Per-class, per-instructor, per-domain and per-quarter are supported. **Per-module
is not** — sessions carry topic strings, not module ids, and that join needs an
`Ambiguous` path. **Attendance stays out** until it can distinguish "0 attended"
from "not recorded".

Quarterly: raw weighted average, response count, named rubric. **Never a band
across quarters** — five rubric sheets disagree, and Q19 is the eval question
written to catch exactly that fabrication. `config/quarters.yaml`, never a
sheet-name parse.

**Response count travels with every average.** A 4.9 from 3 responses and a 4.6
from 200 are not comparable; an average without its N is the same failure as a
count without its floor.

### UNATTRIBUTED — the `auth` schema was emptied, 2026-09-20

**Cause not established. Recorded rather than explained, because guessing at it
would be worse than leaving it open.**

Observed at 22:12Z: `auth.users`, `auth.identities`, `auth.sessions`,
`auth.refresh_tokens` and `auth.audit_log_entries` **all zero**, while `public`
was completely intact — 3,146 nodes, 4,021 edges, 30,658 provenance rows,
`profiles` still holding its rows. `auth.schema_migrations` still had all 82
GoTrue migrations.

**What it caused**, which is established: the next Google sign-in created a new
`auth.users` row with a new `user_id`, 0015's trigger granted it `member`, and
the previous `admin` profile became an orphan that `np_role()` can never return.
An administrator was reduced to `member` with no profile being edited. See
`AUTH.md` §"The durability clause has fired" — this is the condition that
section said must trigger a revisit of the auto-grant.

**What is known about the writes from this session**, stated so it can be ruled
in or out rather than assumed: every delete issued here was scoped — the GoTrue
probes deleted `where email = <probe address>` and reported their row counts,
and `tests/test_auto_member_grant.py` deletes only four synthetic UUIDs. No
unscoped delete against `auth` was run from this machine. That is not proof of
innocence; it is the evidence available.

**Three orphaned profiles remain and were deliberately NOT deleted** — they are
the only record of the prior state. `grant_access.py check` does not see them:
it looks for users without profiles, not profiles without users.

**Open questions for whoever knows the dashboard history:** was a user-delete,
a project restore, or an auth reset performed around 2026-09-20 21:50–22:15Z?

### The default view reads as truncated — wording, not the 65

**Not a proposal to change the node count.** 65 is specced and the reasoning in
§8 stands. This is about the sentence wrapped around it.

`public/index.html:736` renders, on first load:

```
65 of 65 fetched nodes / 98 edges / N components
  — what you have expanded to, not the whole graph
```

Three things work against it for a first-time visitor:

- **"65 of 65"** is an X-of-Y construction, which universally signals *a subset
  of a larger whole*. When the two numbers are equal the construction does no
  work and actively implies a cap that happens to be met.
- **"fetched"** is implementation vocabulary. To a reader it suggests a
  transfer limit rather than a designed view.
- **"what you have expanded to, not the whole graph"** describes a state the
  visitor has not entered — on first load they have expanded to *nothing*. The
  qualifier exists to stop the count being read as the whole graph, and on the
  first screen it instead reads as *you are seeing a fragment*.

> **The qualifier that prevents an overclaim is producing an underclaim.** The
> default view is complete and deliberate, and the sentence tells a first-time
> visitor it is neither. That is the same shape as §9's rule about low-coverage
> fields: a truthful qualifier in one state is misleading in another.

**Latent bug in the same line:** `comps.length + ' components'` has no
pluralisation, so a single-component view reads *"1 components"*.

**Not changed.** The wording is the owner's call; the analysis is the answer to
the question asked.

### Still open

- **R18 traffic calibration: CLOSED.** The Drive folder's prior visibility is
  still unanswered (`CACHE-EXPOSURE.md` §0a).
- **Check 3 of the post-deploy list** — still unrun. See §4.
- **The three aliases** — unresolved, deliberately. `Agentic AI` cannot be
  resolved from the data at all and now says so on the surface.
- **`A7B.md`'s open question** — which of our outputs does nobody read?

---

## 11 · The opening brief for the next session

**Read this document, then [`A7B.md`](A7B.md), then
[`REGISTRY-INVENTORY.md`](REGISTRY-INVENTORY.md), then
[`PRE-CRAWL-DECISIONS.md`](PRE-CRAWL-DECISIONS.md). In that order, before
anything else.** [`SCALE-PLAN.md`](SCALE-PLAN.md) is still the framing document
and its four questions are still open; the two documents above it are newer and
narrow three of them.

**Everything in this section is as of 2026-09-20.**

---

### The registry has been counted — rows A and B, 2026-09-20

`pipeline/count_registry.py`, `REGISTRY-INVENTORY.md` §11. Nothing fetched.

| | A | B | A+B |
|---|---:|---:|---:|
| Files | 8,079 | 3,498 | **11,577** |
| Size | 10.6 GiB | 31.5 GiB | **42.1 GiB** |
| Folders opened / discovered | 1,697 / 1,706 | **1,822 / 1,822** | 3,519 / 3,528 |
| Max depth | 10 | 15 | — |
| Decks | 4.2% | 18.6% | 8.5% |
| Shortcuts · failures · repeats | 10 · 1 · 0 | 21 · 18 · 0 | 31 · 19 · 0 |

**Every listing reached a terminal page. Row B's discovered and opened counts
are identical — "every discovered folder was opened". Row A's nine unopened are
all `(File responses)` D6 skips, named.** All 19 failures are dead shortcut
targets (HTTP 404), named individually. Zero folders reachable by two paths.

**"2,000+ files" was low by ~6×, for two of three rows.** And there is no single
deck ratio: it varies 4.4× between A and B, which falsifies the correction
`REGISTRY-INVENTORY.md` §10 made to its own §3. Both wrong figures are left
standing with pointers.

**Row C was NOT crawled**, by instruction. While verifying access the service
account could read C although it had never been shared with it. Cause,
established from the permission list: **C is shared `anyone` / reader — readable
by anyone with the link.** Every other registry row and the NP corpus is scoped
to the `interviewkickstart.com` domain. `anyone` propagates to contents.
`REGISTRY-INVENTORY.md` §12, including the bound on that claim (the ACL listing
available to a reader is incomplete).

> **The crawler must never use "can the account read it?" as a proxy for "is it
> in scope?"** For C that proxy's answer includes the public internet.

### Which branches have never run — `UNEXERCISED-BRANCHES.md`

Three unexercised branches were found by accident, one per week. The deliberate
pass — filtered `sys.settrace` over a real run of passes 01–05 plus `validate.py`,
in a copy of the repo, no new dependency — found the rest.

**One is unreachable rather than merely unexercised:** `01_walk_corpus.py:126`
tests `suffix == ".docx" and kind == "text"`, but the `kind == "text"` branch
above returns unconditionally. It implements a `CLAUDE.md` rule about a corpus
file that really is plain text with a `.docx` extension. **The protection works
anyway** — the earlier branch catches it — so the guarantee holds and the
mechanism written down to hold it cannot run. A7B question 3, first instance
found by looking.

The rest cluster in one place: code that handles a renamed sheet, an unreadable
file, a changed manifest, an unfamiliar label. **All four are normal traffic in
a multi-owner Drive**, so the least-exercised code is what the crawl hits first.
The manifest delta loops have printed zero lines ever, and pass 1's exclusion
skip has never fired because pass 0 excludes at fetch time.

### Your task: build the fork A crawler. D3 is already closed.

**D3 was closed first, deliberately, before the counter was written** — a
crawler built on a reader that follows shortcuts inherits the behaviour the
decision reverses. `00_fetch_drive.py:walk()` now records shortcuts and never
follows them; `report_shortcuts()` classifies them against the ids the walk
actually discovered. Six tests, mutation-verified. **Measured before the flip:
the existing corpus has zero shortcuts**, so it removed nothing already fetched.

What remains, roughly: the registry reader (five rows, **three folders and two
workbooks**), the crawl with D6's skip, the content index, and the join last.
**The join is the part to design slowly**; `SCALE-PLAN.md` explains why it is
the alias problem for the third time, and `lib/resolve.py` — which runs zero
lines in a build today — would be its first build-time caller.

**Two things the count changes about that plan.** At 11,577 files for two rows,
a serial crawl is ~30 minutes of wall clock and 3,553 API calls; the full
registry will be more. And **row B holds 31.5 GiB in 3,498 files** — the cache
question is no longer mainly about re-fetching, it is whether a local mirror is
something anyone wants at all.

---

### The registry, resolved

A spreadsheet titled **`links`**, `1GNKvvv9LM36om6QJiDuyP01r-L3N19oJGBi1Yjcun5I`,
owned by the B2C account, **living inside the corpus folder itself**. Five rows,
not three — *"the registry is a list of folders"* is wrong about 40% of it:

| | | id |
|---|---|---|
| A | Applied Agentic AI | `1yHZYpbJTjfxumTMU5qNvfSuLXLImJpad` |
| B | Software+System Pod | `19MxiYsE8B3T-O0VqnOF7gtU_7oxlRFJo` |
| C | Data + Mangement *(sic — load-bearing)* | `1aVg_UbUCsuDxv9XXICIxbmpMbjUz5ETm` |
| P1 | Domain Classes Poll Feedback 2026 | `1CcifEPJzSxaqTCguM2e6iOXW9tnjRt75ZPoskN2M-LY` |
| P2 | MLSU/Gen AI/Agentic AI Poll Feedback 2026 | `1zBDUysiidZFdfHVQcOmymv7ulYOz94t5q89rw6HrYDc` |

**The sheet itself is excluded from ingestion** (`taxonomy.yaml -> excluded.files`,
path **`links`**, not `links.xlsx` — pass 0 keys on the pre-export name and the
other spelling fails open silently).

**Measured: 37 folders opened of ≥187 discovered, 75 files, 5 decks.** Every
count in the inventory is a floor over a fifth of what is known to exist, and
**"2,000+ files" is still unverified** — do not repeat it as though it were
measured.

---

### The six pre-crawl decisions — and which of them anything enforces

Full reasoning in [`PRE-CRAWL-DECISIONS.md`](PRE-CRAWL-DECISIONS.md). The second
column is the one that matters, because `A7B.md` instance 9 is precisely the
failure of reading a document as a control.

| | decision | enforced by |
|---|---|---|
| **D1** | No person extraction from slide content — at any confidence, with any flag. Attribution comes from the poll workbooks, always with its response count | **nothing. Prose.** The extractor it governs does not exist yet |
| **D2** | Fork A — a search index with a graph over a known subset | **nothing. Prose.** A design direction is not a constraint |
| **D3** | Shortcuts: resolve and report, do not follow | **nothing — and running code does the opposite** |
| **D4** | Store `owner_domain`, never the owner address | **nothing. Prose.** The assertion (*no provenance field contains `@`*) is specified, not written |
| **D5** | Do not ingest `SMEs consent` | partly — the mechanism exists, but only bites once those paths are in the crawl's scope, which they are not |
| **D6** | `(File responses)` folders: skip by name, **report the skip** — never by a size cap | **nothing. Prose.** |

**Five of six are prose.** They are recorded now because the decisions are cheap
today and expensive at 2,000 files, not because writing them down makes them
true. **Each becomes a test when the code it governs is written, and that code
must not be written without it.**

**The two that will be argued with, so the reasons are here:**

- **D1 is not a threshold and must never be softened into one.** `CLAUDE.md` §4
  governs which *real records* to keep. This is the prior question — whether a
  `Name, Role, Company` tuple on a slide is a record at all. Ranking a
  fabrication yields a ranked fabrication. Four decks carry four such tuples;
  two are a template placeholder and an icebreaker example, and **one of the
  fabricated names is also a rated instructor in P2.**
- **D5 is a modelling limit, not a privacy preference.** A consent licence keys
  on the **purpose of the reader**; every control here keys on the producer or
  the viewer's role. A declared purpose is unverifiable — instance 7 exactly.

---

### The three follow-up measurements

- **The deck ratio (8 of 75) was measured at the wrong depth.** Decks sit one to
  three levels *below* where the pass stopped. Not re-estimated; the direction
  of the error and its cause are known. The module folders also repeat — the
  first repeating unit found in folder A.
- **The five 2023-dormant folders in C are empty — all of them**, plus two below
  `Backend`. Six folders, zero files, ~40% of that folder's top level. **One is
  named `Backend - API Design`** — an empty folder that path-matches the
  project's canonical example query. **That is the fork A ranking regression
  test**, written down with its id in `PRE-CRAWL-DECISIONS.md` §D2 before the
  code exists.
- **One `(File responses)` folder is 2.73 GiB across 60 files, listing not
  exhausted** — ~49× the whole corpus on disk (57.4 MiB), largest file 535 MiB,
  all `.zip` and `.mov`. **Every filename carries a learner's name**, so this is
  a **sixth contact shape and it lives in the path**. At least seven more such
  folders in folder A. Forced D6.

Also: a registry folder owned at a **personal company domain** — exactly the gap
D4 and the contact guard both state they do not catch. The backstop is a
backstop.

---

### Landed in code

- **The contact signature class**, `pipeline/check_no_payroll_committed.py`.
  Three families: payroll (unchanged); contact **column headers** with a density
  rule (data-shaped → 1, prose → 100 against a measured worst case of 10);
  contact **literal identifiers** — free-mail addresses and LinkedIn profile
  URLs — at **threshold one, anywhere**. Exemptions need `contact-ok: <reason>`,
  scoped exactly as `taxonomy-literal-ok` is; a bare marker is an offence.
  **Stated gap, deliberate:** corporate-domain addresses,
  `@interviewkickstart.com` (already tracked on purpose in
  `people-firstnames.yaml` with `evidence:`), phone numbers.
  **It is a backstop, not the control.**
- **The registry sheet excluded**, and **pass 0's export map exercised** for all
  four native types against a fake service, with the positive control that a
  binary still downloads (`tests/test_export_map_is_exercised.py`). Mutation-
  verified: the `links.xlsx` spelling reddens three tests.

**Why the guard exists at all is the thing to carry forward**, and it is now
`A7B.md` question 4: the payroll density rule was reused for contact data and
**would have waved through the actual near-miss** — four addresses in a Markdown
file. A header is a word; an address is a person. Alongside it, *measure with
the matcher you ship*: three figures in this project were honestly measured and
described something other than the claim they were put into.

---

### Still open

**`SCALE-PLAN.md`'s four questions.** Q3 — *what replaces `sources.py`'s narrow
inclusion as the real contact-data control* — is the urgent one, and the
inventory's §8 says why: five of the six contact shapes are outside the
allow-list's reach. Q1's "2,000 files" is unmeasured.

**Everything else that was open stays open and is listed in §10** — payroll
ingestion awaiting its approval block, untracking `graph.json`, session metrics,
R18's Drive-visibility question, post-deploy check 3, the three aliases, and
`A7B.md`'s open question. **None of them is a prerequisite for the crawler**,
and none was touched by this phase.
