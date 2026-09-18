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
| **API** | `/api/config` 200; `/api/{search,node,neighbourhood,coverage,staffing,aliases,me}` all **401 unauthenticated**; `/api/session` 401/400/403 on bad input |
| **Sign-in** | Works end to end. Google Workspace → `/api/session` → GoTrue → Supabase session → RLS |
| **Security headers** | All six present on the deployed response: CSP (no `unsafe-inline` on `script-src`, inline blocks pinned by SHA-256), HSTS, `x-frame-options: DENY`, nosniff, no-referrer, permissions-policy. Plus `Cross-Origin-Opener-Policy: same-origin-allow-popups` |
| **Service-role key** | **Zero occurrences** in the shipped bundle, and the variable is not set in the Vercel project at all |

### Verified locally only — do NOT describe these as production-verified

- **In-region latency.** `DEPLOYMENT.md` carries a **projection**, not a
  measurement. See §4.
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
| Migrations | **0001–0014 applied.** `python3 pipeline/migrate.py status` |
| Profiles | `animesh.kumar@…` = `member`; `b2c-courses-new-programs@…` = `member`, `is_shared_account=true` (correctly capped — it cannot hold `recruiting` or `admin`) |

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

python3 pipeline/migrate.py status          # migrations 0001-0014
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

### In-region latency — still a projection

Measured from a laptop, as `authenticated` with a `member` profile so RLS is
included:

| Endpoint query | Round trip (laptop) | Server-side |
|---|---|---|
| `search` | 191.3 ms | **4.62 ms** |
| `node` | 149.3 ms | 0.22 ms |
| `provenance` | 150.5 ms | 0.53 ms |
| `neighbourhood` d1 / d2 / d3 | 151 / 154 / 182 ms | 0.67 / 0.99 / 4.87 ms |

~148 ms of each is geography. **The in-region figures in `DEPLOYMENT.md` are a
projection and must be replaced with measurements.** The audit line from
`guard.audit()` records `ms` per request, so `vercel logs --since 1h` on a
signed-in session yields real numbers with no new instrumentation.

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

### 1. The sign-in flash

Reloading shows the sign-in page for about a second before redirecting to the
graph. The session exists; the page renders before it is checked. **Resolve the
session before first paint rather than after.** In `public/index.html`, `boot()`
runs after `recompute(true,'initial')` and the gate is visible in the initial
HTML.

### 2. The empty default view

The graph shows nothing until you search. Decide what a useful default is — the
42 domains, the largest connected component, or a chosen starting node — and
load it without a query. **State the choice and the reason**; "show everything"
is not available at 3,146 nodes, and `nodeBudget` caps the client at 1,200.

### 3. Speed — measure before changing anything

It is slow in a way the 4.62 ms server-side numbers say it should not be.
**Measure first:** per-endpoint in-region timings from the audit log
(`vercel logs --since 1h`, which carries `ms`), then the browser's own timings.
The cause could be the round trip, the payload, the render, or cold starts.

> **The precedent that makes this rule non-negotiable:** `coverage` once
> measured 1,610 ms. That was cold buffers, not the plan. Warm it was 18.8 ms.
> Optimising the first number would have chased the wrong thing.

**Leading hypothesis, recorded but NOT acted on:** `vercel.json` has **no
`regions` key**, so the function runs in Vercel's default region (`iad1`,
Washington DC) while the database is in **ap-northeast-2 (Seoul)**. That is a
trans-Pacific round trip on every statement. A region pin (`"regions": ["icn1"]`)
was present briefly and was removed during deploy debugging on a wrong
hypothesis. **Confirm by measurement before restoring it** — that is the whole
point of this item.

### 4. Auto-grant `member` on first sign-in

**This reverses part of Q3's default and must be recorded as a reversal in
`AUTH.md` with the reasoning**, because it changes what "a profile grants
access" means. Today `AUTH.md` says *"layer 3 permits an account to exist; a
profile is what gives it data"*, and `/api/me` tells a signed-in user with no
profile exactly that.

New rule: any verified `@interviewkickstart.com` Workspace account gets `member`
automatically, with no administrator step. **Conditions, all mandatory:**

- `recruiting` and `admin` stay **manual** and stay off the auto path.
- The shared-account rule from migration 0014 still applies.
- **A test proves a non-IK identity still gets nothing.**

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
