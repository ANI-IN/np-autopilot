# STATE — working brief for a session with no memory

You are continuing `np-autopilot`: a knowledge graph over Interview Kickstart's
New Programs corpus, projected into Supabase Postgres, served by a Vercel web
app behind Google Workspace sign-in.

**Read this first, then the pointer map at the bottom before opening anything
else.** Everything here is current as of 2026-09-18. Where a number is measured
rather than assumed, it says so.

---

## 1 · Where the system stands

### Live and verified against production

| | |
|---|---|
| **Explorer** | <https://np-autopilot.vercel.app> — 200, serves the graph UI |
| **API** | `/api/config` 200; `/api/{search,node,neighbourhood,overview,coverage,staffing,aliases,me}` all **401 unauthenticated**; `/api/session` 401/400/403 on bad input |
| **Sign-in** | Works end to end. Google Workspace → `/api/session` → GoTrue → Supabase session → RLS |
| **Security headers** | All six present on the deployed response: CSP (no `unsafe-inline` on `script-src`, inline blocks pinned by SHA-256), HSTS, `x-frame-options: DENY`, nosniff, no-referrer, permissions-policy. Plus `Cross-Origin-Opener-Policy: same-origin-allow-popups` |
| **Service-role key** | **Zero occurrences** in the shipped bundle, and the variable is not set in the Vercel project at all. That bundle scan is the evidence — not the unit test, which until 2026-09-18 scanned `web/` while the routes live in `api/` and so proved nothing. Now covers both; see `DEPLOYMENT.md` and `DECISIONS.md` §A.7b instance 8 |

### Verified locally only — do NOT describe these as production-verified

- **Render and layout cost.** Never measured, in any region. §4.
  (In-region *latency* is now measured — `LATENCY-MEASUREMENT.md`.)
- **The full test suite** (260 passing, ~7 min) runs against the real Supabase
  but from a laptop, not from Vercel.
- **Everything in `pipeline/`.** It has never run on Vercel and is not meant to.

### The data

| | |
|---|---|
| Graph in Postgres | **3,146 nodes / 4,021 edges** (public half only) |
| Provenance | 30,658 `node_sources` rows over **74 files** |
| Curation | 20 people, 15 confirmed aliases + 6 unresolved, 92 workflow owners, **45 `curation_notes`** |
| Sensitive | **Zero rows projected.** `project_graph.py --scope full` is refused while R18 is open |
| Migrations | **0001–0015 applied.** `python3 pipeline/migrate.py status` |
| Profiles | `animesh.kumar@…` = `member`; `b2c-courses-new-programs@…` = `member`, `is_shared_account=true` (correctly capped — it cannot hold `recruiting` or `admin`) |

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

python3 -m pytest tests -q                  # 260 tests, ~7 minutes
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

## 4 · Open items, each with its current state

### R18 — the repository was public for eight days

**Status: remediated, one field unanswered.** Found 2026-09-17; set private,
then deleted and recreated (old id `1363038448` → new `1374030791`). History
rewritten. What was readable: 3,817 instructor names including **277 named
hiring rejections** and 1,625 mid-pipeline candidates.

**Unanswered: the traffic calibration field.** GitHub reported 0 clones/views
over the window. Whether the repo page was ever opened in a browser during it
decides what that zero means — if it was, the instrument recorded zero views for
a session that certainly occurred, making the zero **unreliable rather than
reassuring**. Both readings are written out in `07-risks.md` R18. Either way,
zero recorded traffic is not evidence of zero copies.

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
constraint in a new migration, written out in `DECISIONS.md` §A.7b. It guards
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
- **Sensitive nodes are not projected at all.** `member` role only while R18 is
  open.
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
| **About to write or change a guard?** | `DECISIONS.md` **§A.7b** first. Six instances of one failure pattern and what catches the seventh. Read it *before*, not after |
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

**In this order.** Recorded 2026-09-18; not started.

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
the gap renders identically to a healthy domain. That is the §A.7b shape, so
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

### 5. The sign-in page and the explorer UI

Make the sign-in page look like something IK would put in front of its team
rather than a bare card. Improve the explorer: better layout, clearer
affordances.

**Keep the provenance panel prominent — a hand-entered fact must stay visibly
distinct from a scanned one.** That distinction was invisible for the whole
project until the collision check surfaced it.

**Keep everything §G2 listed as preserved**, all of which carry solved bugs:

- the cooling schedule (`ALPHA_DECAY`, `ALPHA_MIN`) — the layout freezes at 366
  frames and must keep doing so
- selection split from layout — a click must not move a single coordinate
- debounced resize that never restarts the simulation
- `CAP = 8` with "show N more", disclosed
- paint-time decorative drift that never writes `n.x` / `n.y`

`eval/drive_dom.mjs` asserts every one of these against both renderers. Run it
before and after.
