# DECISIONS — architecture, options and tradeoffs

**Phase 0.5. No migrations, no schema, no tables created.** Written against
measurements from `graph.json` at `f30a5c6`, not from the existing docs.

Every recommendation below is argued, including the two schema positions you
handed me — I argue them rather than accept them, and one of them needs an
amendment the collision check forced.

---

## Status — updated 2026-09-17, after Phase C

| Item | State |
|---|---|
| §A.4 assertion-id collisions | **FIXED.** Grid column recorded, ordinal carried. 32,745 of 32,745 keys unique, 0 collisions. |
| §A.5 property-level provenance | **FIXED (minimal + `establishes`).** Hand sources reach the node and name which properties they justify. `hand-provenance` is now a falsifiable validate category. |
| §B.4 calendar-derived fields | **FIXED.** Edges store `class_dates`; the five derived values are computed at read time. Proven day-independent across three `NP_AS_OF` probes. |
| §F.2 sensitive split | **DONE**, and it covered three files, not one — `resolved.json` and `candidates.json` carried the same funnel and were committed. |
| §F.2 history rewrite | **PLANNED, NOT RUN.** `docs/HISTORY-REWRITE-PLAN.md`, awaiting four answers. |
| §G workflow management | **CLOSED — out of scope.** |
| Migration baseline | **FROZEN** at `0165f164e104d6ad`, `config/migration-baseline.yaml`. Verifier passes 32/32 file-against-file and fails on four injected migration mistakes. |
| Track 1 — Supabase connection | **STILL BLOCKED.** See §C.0. |

Two figures in this document were corrected by measurement and are noted where
they appear: components excluding provenance is **42** for the full graph (the
36 was the rendered subset), and the duplicate count is **1,687 distinct
colliding triples / 26,448 extra rows**.

---

## 0 · Decisions already taken

Recorded so the rest of this document can lean on them. **If any row misstates
what we agreed, that is my error — say so and I will correct it.**

| # | Question | Decision |
|---|---|---|
| Q1 | Drive ingestion | **Live.** Service account, folder shared to it, no delegation. Pass 0 ran successfully: 75 files, 0 failures. |
| Q2 | Source of truth | **Split.** Curation (people, aliases, workflow owners) authored in Postgres; derived graph stays pipeline-built and is *projected* into Postgres. |
| Q3 | Access tiers | **Two roles from day one.** `viewer` sees the roster graph; `recruiting` additionally sees the hiring funnel, ratings and decline rates. |
| Q4 | GitHub | **Stays `ANI-IN/np-autopilot`, personal, no org, 3–4 collaborators.** Consequences in §F. |
| Q5 | Plugin model | **Cached snapshot + authenticated API** for anything sensitive or write-shaped. |
| Q6 | Workflow management | **Still open.** Not designed for here — see §G. |

**Master spreadsheet: answered, negatively, with evidence.** I listed
`00-master` (5 files) and searched all **374 worksheets across 18 workbooks** in
the Drive folder. No sheet is named `Automations`, `All Tasks` or
`To-Do & Working Notes`; a fuzzy search for `automat`, `all task`,
`working note`, `to-do` and `todo` returns nothing.

That is a statement about **this folder**, which is the corpus scope we have
defined and the only thing shared with the service account. It is not a
statement about all of Drive. `Owner` and `Automation` are not imminent node
types — but per your instruction the design requirement stands regardless, and
§A.6 shows how it is met.

---

## The measurements everything below rests on

| | |
|---|---|
| Nodes | 5,048 |
| Edges, total | 36,677 |
| — of which `sourced_from` (provenance) | **32,656 — 89%** |
| **Traversable edges** | **4,021** |
| Traversable subgraph, as JSON | **1.2 MB** |
| Node records, as JSON | 5.4 MB (mostly `sources[]` arrays) |
| Average degree excluding provenance | 1.59 |
| Max degree (a `file` node) | 18,134 |
| Deepest real query | **3 hops**, max fan-out **42** |
| Distinct node property keys | 41 — only 5 on every node |
| Distinct edge property keys | 19 |

**The traversable graph is tiny.** 4,021 edges and 1.2 MB. Almost everything
that makes `graph.json` an 11 MB file is provenance. That single fact decides
more of this document than any preference about Postgres features.

---

## A · Graph storage in Postgres

### A.1 The options, against this graph

| Option | Verdict |
|---|---|
| **Normalised `nodes` / `edges` + recursive CTEs** | **Recommended.** 4,021 traversable edges and a 3-hop maximum. A recursive CTE over a table this size is measured in single-digit milliseconds. |
| **JSONB property bags** | **Recommended, but only for the property tail.** 41 property keys, of which 5 are universal and 29 appear on under 10% of nodes. Columns for the universal five, JSONB for the rest. |
| **`ltree` for hierarchies** | **Reject.** There is no hierarchy. The one tree-shaped relation is `workflow → theme`, which is a single level, and `contains` is a lossy inferred join, not containment. `ltree` would model a structure this corpus does not have. |
| **Apache AGE / pgRouting** | **Reject for v1.** A graph extension earns its place at traversal depths and fan-outs this data does not reach. It also may not be available on Supabase's managed platform — I could not verify, because I cannot connect yet (§C.0). Depending on an extension whose availability is unconfirmed, to solve a problem measured at 4,021 edges, is the wrong trade. |
| **pgvector alongside structural edges** | **Defer, and keep the door open.** There is a real use for it — "find me an instructor like this one", semantic search over 922 module labels — but it answers a question nobody has asked yet. The schema below does not preclude adding an embedding column later, and adding one is exactly the kind of change §A.6 is designed to make cheap. |

### A.2 Shape

Four tables. Deliberately not one table per node type.

```
nodes        (id, type, label, label_raw, sensitive, props jsonb, ...)
edges        (id, rel, source_id, target_id, props jsonb, ...)
assertions   (id, subject_kind, subject_id, prop, file, sheet, row, col, page,
              origin, ordinal, evidence, ...)
files        (path, sha256, sheet_count, parsed, drive_file_id, drive_url, ...)
```

`type` and `rel` are **text with a foreign key to a lookup table, never a
Postgres `enum`**. Adding a value to an enum is a DDL change that takes a lock;
adding a row to a lookup table is an insert. This is the §A.6 requirement
showing up in the very first design choice.

### A.3 Provenance in its own table — I agree, and here is the stronger reason

Your position was that provenance belongs in its own table. It does, and the
argument is stronger than separation-of-concerns:

**89% of all edges are provenance, and provenance is explicitly not a traversal
path.** `taxonomy.yaml` says so directly: *"Citation only, never a traversal
path. All 92 workflows share one file node, so this is a degree-92 hub, not a
bridge."* The top six nodes by degree are all `file` nodes, the largest at
**18,134**. Any traversal that forgets to exclude `sourced_from` does not return
a wrong answer slowly — it returns a catastrophically wrong answer, because it
walks through a file hub into every other entity that file mentions.

Keeping provenance in `edges` means every single traversal query carries a
`WHERE rel <> 'sourced_from'` that is load-bearing for correctness and trivially
forgettable. Moving it to `assertions` makes the dangerous join impossible to
write by accident. **That is the real argument: it is not tidier, it is
unforgettable.**

It also shrinks the hot table by an order of magnitude: `edges` becomes 4,021
rows instead of 36,677.

### A.4 Content-addressed assertion ids — I agree, with a correction the data forced

You asked for content-addressed assertion ids. I ran the collision check. The
result changes the recommendation slightly, and it is the kind of thing that
would have been found in production instead.

**`(source, target, rel)` is not a candidate key, and is not close.**

```
sourced_from edges                              32,656
distinct (source, target, rel)                   6,230
collisions                                     26,426
```

The duplication is correct: taxonomy requires one edge per entry in the node's
`sources` list, so a node cited from 40 rows of one file yields 40 edges. And
`expert_in` has 22 duplicate triples where the same instructor→domain pair is
asserted twice with a different `basis` — a Google Form response *and* an HR
record — which `/staffing` exists to keep apart.

**Adding full provenance coordinates almost works, but not quite:**

```
source entries across all nodes                 32,730
distinct (node, file, sheet, row, column, page) 32,724
remaining collisions                                 6
```

Six genuine collisions. All six are the same person appearing **twice in one
row** of a grid sheet:

```
Hardik Gupta      AgenticAI…xlsx  'Preferred SMEs for Each Topic'  row 18   x2
Hemant Pugaliya   AgenticAI…xlsx  'Preferred SMEs for Each Topic'  row 19   x2
Lekshmi Pillai    AgenticAI…xlsx  'M_SME_App. GenAI'               row 12   x2
Lekshmi Pillai    AgenticAI…xlsx  'M_SME_App. GenAI'               row 36   x2
Rizwan Ansary     Data and Management.xlsx  'Management  Instructors' row 24 x2
```

**Root cause:** `extract_pairings` reads ranked instructor *columns* but records
provenance with `column: None`. The coordinate that would disambiguate is being
dropped at extraction.

**So: content-addressed ids, yes — with two changes.**

1. **Fix the extractor to record the column.** This is the honest fix: the
   information exists and is being discarded, and it is independently useful
   (it is what tells you Hardik Gupta was listed as both primary and first
   backup for the same module).
2. **Include an `ordinal` in the key anyway.** Belt and braces. A content hash
   that is 99.98% unique is a hash that fails once a year, at 3am, on a row
   nobody is looking at. The ordinal costs one integer and removes the class of
   failure entirely.

Assertion id = `sha256(subject_id, prop, origin, file, sheet, row, col, page,
ordinal)`. Deterministic, so a rebuild produces the same ids and the projection
is a set-diff rather than a truncate-and-reload (§B.2).

### A.5 A gap the collision check exposed: `origin: hand` never reaches the graph

Not something I went looking for. While checking assertion keys I counted source
origins across the whole graph:

```
source entries by origin:   'corpus': 32,730      'hand': 0
```

`config/people.yaml` declares `origin: hand` sources for **all 15** NP staff,
citing the HR directory screenshot. **None reaches `graph.json`.**
`03_resolve.py` copies `title`, `seniority`, `status` and `corpus_disagrees`
from `people.yaml` onto the node — but not `sources`.

Why this matters more than it looks:

- `CLAUDE.md` states the rule as load-bearing: *"Hand-entered facts carry
  `origin: hand` and never emit a `sourced_from` edge. They must never be
  presentable as though a scan produced it."*
- `taxonomy.yaml` defines the two source shapes and restricts the hand shape to
  two config files. `validate.py` has no check for it. **Both are vacuous** —
  no node in the graph has ever had the shape.
- The concrete exposure: `Shashi Bhushan Kumar` carries
  `title: "Director, Product Management"` and `seniority: Director`, which came
  from a hand-entered HR screenshot, on a node whose only stated provenance is
  corpus spreadsheets. The graph currently presents a hand-entered fact as
  though a scan produced it. That is the exact failure the rule names.

**This is the decisive argument for assertions being attached to a *property*,
not just to a node.** A node-level `sources[]` array cannot express "the label
came from a spreadsheet row but the title came from a screenshot". The
`assertions` table has a `prop` column for precisely this, and `origin` is not
nullable.

I have **not** fixed the pipeline gap — it is a separate change and you said no
work beyond the two tracks. It should be scheduled before the migration, because
the migration will otherwise faithfully reproduce the omission.

### A.6 Adding a node type must not rewrite existing rows

Your requirement, and the design meets it:

| Change | Cost |
|---|---|
| Add a node type (`Owner`, `Automation`) | **Insert one row** into the type lookup. No DDL, no lock, no backfill. |
| Add an edge type | Insert one row into the rel lookup. |
| Add a property to one type | Nothing. It lands in `props jsonb`. |
| Promote a property to a column | `ADD COLUMN` (fast, no rewrite in PG11+) plus a backfill *of that column only*. |
| Add an embedding | `ADD COLUMN vector`, populated lazily. |

The thing that would break this is exactly what a relational instinct suggests:
a table per node type, or `type` as an enum. Both are rejected above.

### A.7 Validation: constraints vs application code vs triggers

The 17 `validate.py` categories do not all belong in the same place.

| Where | Which | Why |
|---|---|---|
| **DB constraints** | `duplicate-id` (PK), `endpoint-type` (FK + a check against the rel lookup), `absolute-path` (CHECK), non-empty provenance (FK from node to ≥1 assertion), `sensitive` NOT NULL | Structural. Cheap, always-on, cannot be bypassed by a buggy writer. |
| **Application / pipeline** | `junk-label`, `cadence-collision`, `count-vs-expect`, `components`, `blank-identifier`, `quarter-map`, `excluded-field`, `version-bump` | These are **policy with a message**. `validate.py`'s value is the sentence it prints, not the boolean. A CHECK constraint that fires "violates check constraint nodes_label_check" destroys the thing that makes these useful. |
| **Triggers** | **None.** | A trigger is invisible control flow that runs on someone else's write. The one job people reach for triggers for here — audit logging of mutations — is better done explicitly in the write-through layer, where it can record *who* and *why*, which a trigger cannot see. |

**Do not port `validate.py` into SQL.** Port its *structural* half into
constraints, keep the rest running against the built artefact where it can go on
printing sentences a human will read. CLAUDE.md §5 is about exactly this: the
report has to stay readable or it stops being read.

### A.8 Concurrent writes and locking

Two populations with genuinely different needs:

- **Derived graph** (nodes, edges, assertions): **single writer, no locking
  needed.** The pipeline is the only thing that writes it, a rebuild is atomic
  (§B.3), and no human edits these rows. Adding optimistic locking here would be
  ceremony against a race that cannot occur.
- **Curation tables** (people, aliases, workflow owners): **optimistic locking,
  `version` column, `UPDATE … WHERE version = $n`.** Two people resolving the
  `ML` alias differently at the same time is a real scenario, and last-write-wins
  would silently discard a decision. The `Ambiguous` discipline in
  `lib/resolve.py` exists because three separate bugs came from picking one
  candidate with no signal to the caller; a lost curation update is the same
  failure with a database underneath it.

A write-through service layer is needed regardless (§C.4), but for
*authorisation and audit*, not for locking.

---

## B · Sync between the pipeline and Supabase

### B.1 The decision

**Supabase is the source of truth for curation. The pipeline remains the source
of truth for everything derived.**

The argument against making Supabase canonical for the whole graph is
concrete, not aesthetic. The pipeline's strongest property is that a rebuild
over unchanged input is byte-identical — proven by
`tests/test_deterministic_ids.py`, enforced by the version lock, and it is what
makes "did the corpus change, or did I change?" answerable at all. That property
exists *because* nothing but the pipeline writes the derived graph. Let the web
app edit a node and it is gone, permanently, and with it the ability to trust
any future diff.

The argument against making Supabase a pure read replica is equally concrete:
three alias decisions (`ML`, `Agentic AI`, `Product Management` — 272 edges)
have been waiting on a human for a week because the only way to record one is to
edit a YAML file in a repo checkout. That is a workflow problem a UI fixes, and
those three files — `people.yaml`, `domain-aliases.yaml`, `workflow-owners.yaml`
— are the *only* files a human ever hand-edits.

So the split follows the existing seam rather than inventing one.

### B.2 A rebuild is a diff, not a reload

Because ids are content-addressed (§A.4), projecting a rebuild is:

```sql
BEGIN;
  -- stage, then three set operations against the live tables
  DELETE  … WHERE id NOT IN (SELECT id FROM staging)   -- gone from the corpus
  INSERT  … ON CONFLICT (id) DO UPDATE                 -- new or changed
COMMIT;
```

Rows that did not change are not touched, so `updated_at` stays meaningful and
an audit trail of graph mutations is worth keeping. A truncate-and-reload would
make every row look modified on every build and render the audit log useless.

### B.3 Failure semantics: a run that dies halfway

**One transaction, staged first.** The pipeline builds `graph.json` locally and
completely — it already does, and any pass failing aborts the run leaving the
previous artefact untouched — and only a *complete, validated* artefact is
projected. The projection loads into staging tables, then applies the diff in a
single transaction.

A pipeline crash therefore leaves Postgres on the last good build. There is no
partially-applied graph state, which matters because a half-applied graph is not
merely incomplete — it is *wrong in a way that looks fine*, with edges pointing
at nodes that were not inserted yet.

This preserves `refresh.py`'s existing semantics rather than replacing them.

### B.4 `NP_AS_OF` and the projection — and the better answer

You asked how a rebuild on a different day interacts with a diffed projection.
Badly, and it took a day to show up: **the date has already rolled from
2026-09-16 to 2026-09-17 during this session.**

The mechanism: `teaches` edges carry `last_taught`, `sessions_past` and
`sessions_scheduled`, computed by partitioning recorded class dates against
"today". Rebuilding the 2026-09-09 graph on 2026-09-16 moved **44 edges** across
that boundary, with every node and every edge key untouched.

Under §B.2, a nightly rebuild would therefore produce **44 spurious UPDATEs
every single night**, forever, against a corpus that had not changed. The audit
log fills with noise, `updated_at` stops meaning anything, and the one signal
worth having — *something actually changed* — is buried. This is CLAUDE.md §5 in
a different medium: a real finding drowned by volume.

**Should `NP_AS_OF` go in `.version-lock.json`? No — and the reason points at the
better fix.**

Pinning it in the lock makes the graph reproducible but *stale*: a build pinned
to 2026-09-09 would still be reporting a class as "scheduled" months after it was
taught. The lock would preserve the wrong answer faithfully.

**The right fix is to stop storing the derived values at all.** They are a
function of `(recorded dates, now)`, so:

- The pipeline emits the **raw class dates** on the edge — it already collects
  them — and stops emitting `sessions_past` / `sessions_scheduled` /
  `last_taught` as stored facts.
- The projection computes them **at query time**, in SQL, against `now()`.
  Always current, never drifting, and they vanish from the diff entirely.
- `NP_AS_OF` **stays** — but narrows to its real job: reproducing a historical
  `graph.json` byte-for-byte when you need to prove what a past build contained.
  It is a verification tool, not a production setting.

This also removes the derived values from the plugin snapshot, which is the one
place they genuinely go stale — a cached snapshot on a laptop currently reports
`sessions_scheduled` as of whenever it was built.

**Nothing in `.version-lock.json` changes.** It keeps hashing nodes+edges; once
the calendar-derived fields are no longer stored, that hash stops drifting daily
on its own.

---

## C · Vercel + Supabase runtime constraints

### C.0 Not yet verified — I cannot connect

**Re-checked 2026-09-17, after the env file was said to exist. It does not.**

`~/.config/np-autopilot/` contains exactly one file, `drive-sa.json` (mode 600).
There is no `env` beside it. I also re-checked the process environment, a login
shell (`zsh -lc`), an interactive shell (`zsh -ic`), `~/.zshenv`, `~/.zprofile`,
`~/.zshrc`, `~/.profile`, and looked for a dotenv file anywhere obvious. Nothing.

No Postgres client is installed either: `psql` is absent, and so are `psycopg`,
`psycopg2` and `asyncpg` (only `sqlalchemy` is present, which cannot connect on
its own).

So **AGE and pgvector availability remain unverified**, and the recommendation to
reject AGE for v1 still rests on the size argument alone — which is sufficient on
its own, but I would rather confirm than infer. The first thing I will run once
connected is `pg_available_extensions`.

**Consequently the following are reasoned, not measured**, and I have flagged
what I would verify first.

### C.1 Transaction-mode pooling: what it actually forbids

| Lost | Consequence here |
|---|---|
| Prepared statements | The driver must run in "simple query" mode. For `psycopg3`, `prepare_threshold=None`. This is the single most common cause of "works locally, fails on Vercel". |
| Session state | No `SET search_path`, no session GUCs, no temp tables surviving a statement. RLS via `SET LOCAL` inside a transaction is fine; `SET` outside one is not. |
| `LISTEN`/`NOTIFY` | Cannot be used for cache invalidation. Not needed if the plugin polls a version. |
| Advisory locks across statements | Irrelevant: the only writer that needs mutual exclusion is the pipeline, which does not run serverless. |
| Long transactions | A transaction held open across an `await` of an external call will exhaust the pool. |

**Never use `db.<ref>.supabase.co:5432`.** Noted and agreed — IPv6-only here, so
it works on your laptop and fails on Vercel, which is the worst failure
distribution there is. I would add a CI grep for that hostname, in the same spirit
as the service-role-key check.

### C.2 Which deterministic query paths survive, which need rewriting, which should not move

You asked for this plainly. `query.py` currently loads 11 MB at import, which is
fine for a CLI invoked once and untenable per-request.

| Path | Verdict |
|---|---|
| **`staffing()` tiering** | **Stays in Python. Do not turn it into SQL.** The tiering is not a sort — it is a partition into named evidence classes (taught / HR record / form response / alias-matched form response) that must never merge. `tests/test_staffing_tiers.py` asserts a name with teaching history never also appears in a declared tier. An `ORDER BY` expresses ranking; it cannot express "these are different kinds of evidence and merging them is the worst failure this system can produce". Fetch the domain's subgraph, tier in Python. |
| **`modules_of()`** | **Becomes SQL.** A 2-hop join (`domain ← covers ← program → contains → module`). Max fan-out 45 modules. A plain join or a small recursive CTE. |
| **`coverage()`** | **Becomes SQL, and wants to.** It is whole-graph aggregate counting — programs without a domain, modules without an instructor, isolated records. Doing this in Python requires the entire graph in memory; in SQL it is a handful of `LEFT JOIN … IS NULL` and `COUNT`. This is the one path that is strictly better as SQL. |
| **`find_domain()` / `lib/resolve.py`** | **Stays in Python, unchanged.** 42 labels, staged matching, and `Ambiguous` as the *default return*. Three shipped bugs came from collapsing ambiguity to one candidate. A SQL `LIKE` or trigram match returns rows; it has no way to return "this matches five things, ask which". Keep it as a pure function over a cached label list. |
| **`05_render_html.py` / `graph.html`** | **Never moves.** A build artefact. |
| **The pipeline itself** | **Never runs on Vercel.** Pass 0 alone took **4m 17s**, which exceeds the function timeout on most plans. It belongs on a worker or a scheduled local run. |

**The shape this produces:** Vercel functions do request-scoped reads and
delegate the two correctness-critical decisions — evidence tiering and name
ambiguity — to Python running over a small fetched subgraph. Neither becomes
SQL, because in both cases SQL's return shape cannot carry the distinction that
matters.

### C.3 Where heavy computation runs

| Work | Where | Why |
|---|---|---|
| Passes 0–5, validation | Local or a worker | Minutes, not seconds. Needs the corpus and the Drive key. |
| Projection into Postgres | Same worker, one transaction | Must be atomic with the build it came from. |
| Aggregate coverage counts | **Postgres** | Set operations over the whole graph. |
| Neighbourhood expansion, path finding | **Postgres**, recursive CTE, depth-capped | 4,021 edges; depth cap because a forgotten `sourced_from` exclusion is catastrophic, and the cap fails loudly instead. |
| Tiering, name resolution | **Vercel function, in Python/TS** | Return shape carries meaning SQL cannot. |
| Rendering the graph view | Browser, paginated | Never ship 5,048 nodes to the client. |

### C.4 Cold starts and the service layer

One typed data-access layer that every consumer goes through — web app,
pipeline projection, plugin API. Not for locking (§A.8) but for two things a
database cannot do for itself: **authorisation decisions that depend on who is
asking**, and **an audit record that knows *why* a mutation happened**.

Cold starts are a minor concern at this size; the pooler connection is the cost,
not the data. Keep the connection module-scoped so warm invocations reuse it,
and never hold a transaction open across an external call.

---

## D · Authentication and domain restriction

Requirement: verified `@interviewkickstart.com` only. Four layers, and they are
not interchangeable.

| Layer | What it does | Where it leaks |
|---|---|---|
| **1. Google Workspace OAuth, `hd` claim verified server-side** | The only layer that actually establishes organisational identity. | Leaks if `hd` is read from the client, or if the ID token's signature and `aud` are not verified. **Verify server-side against Google's JWKS.** |
| **2. Supabase auth hook rejecting non-matching domains at signup** | Stops a non-IK identity ever becoming a row. | Only covers the signup path. An account created before the hook existed stays valid. |
| **3. `profiles` table + RLS keyed off the verified domain and role** | The database refuses unauthorised rows regardless of what any API route does. | Leaks only via the service-role key, which is why that key never leaves server code. |
| **4. Middleware route protection** | Fast rejection, good UX. | **Defence in depth only.** A misconfigured matcher silently stops protecting. Never the only gate. |

**Stated plainly, as you asked:**

- **Email-claim string matching is not sufficient.** `email.endsWith("@interviewkickstart.com")` trusts a claim that may be unverified, and a Google account can carry an `email` in your domain without belonging to your Workspace. The `hd` claim, verified server-side on a signature-checked token, is what distinguishes the two.
- **Magic links to a domain are weaker than verified Workspace SSO.** A magic link proves control of a mailbox at a point in time. It does not prove current membership of the organisation, so an ex-employee with a still-forwarding alias remains authenticated. SSO revocation is immediate; mailbox control is not.
- **RLS is the only layer that protects the data if an API route is ever misconfigured.** Layers 1, 2 and 4 all live in application code. One route handler that forgets a check, one middleware matcher that stops matching, and 1–2–4 are bypassed together. RLS is enforced by Postgres on every query regardless of the path that reached it. **Default deny on every table from day one**, policies added deliberately.

**The two roles (Q3) are an RLS problem, not an application problem.** `viewer`
sees `sensitive = false`; `recruiting` additionally sees the 277 rejections, 1,625
in-pipeline candidates, 39 ratings and 136 decline rates. Today that boundary is
enforced by a *render filter* in `05_render_html.py` — which does not survive
contact with a queryable API, because the API answers questions the renderer
never asked. It has to become a policy.

Required test, both layers: a non-IK identity is rejected **at the API** and the
same query run **as that identity against the database** returns zero rows.

---

## E · Private plugin distribution

### E.1 What is and is not achievable

Stated plainly, because the requirement is not fully satisfiable as written:

- A "private" plugin means a private git repo. Every authorised user needs
  GitHub read access and working git credentials on their machine.
- GitHub's model is **per-user**, not per-machine or per-location. "2–3
  authorised locations" maps onto org teams (which you have declined, Q4) or onto
  named collaborators. It does not map onto machines or geography without device
  management, which is out of scope.
- **Plugin code on a user's machine enforces nothing.** Anyone who can clone can
  read every prompt, command and script. A check inside the plugin is a
  suggestion.

**Therefore the split:**

| In the plugin (thin client) | Behind the authenticated API |
|---|---|
| Command definitions, prompt text | All graph data beyond the roster snapshot |
| A roster-only cached snapshot (`sensitive = false`) | The hiring funnel, ratings, decline rates |
| Token acquisition + keychain storage | Every write |
| The `/staffing` tiering rules as *presentation* instruction | The tiering *computation* |
| **No secrets. No privileged logic.** | Every authorisation decision |

### E.2 Authentication from the plugin

**Device-code flow**, token in the OS keychain (`security` on macOS,
`libsecret`, Credential Manager). Never a shared key in the repo — a shared key
is unrevocable per-user and indistinguishable in an audit log.

- Short-lived access token, refresh token in the keychain.
- Token carries the user identity and role; the API re-derives the role
  server-side per request and never trusts a claim in the request body.

### E.3 Revocation, and the honest limit

| Action | Effect |
|---|---|
| Revoke the API token | Immediate. All sensitive data and all writes stop. |
| Remove the GitHub collaborator | Stops *future* plugin updates. |
| Snapshot already on their laptop | **Cannot be revoked.** |

The roster snapshot is unrevocable, which is precisely why the split in §E.1 puts
only `sensitive = false` data in it. That is the mitigation: make the unrevocable
part the part that does not matter.

### E.4 Auditing who queried what

Every API request logs `(identity, endpoint, parameters, row count, timestamp)`.
Two properties worth designing in now:

- Log the **query**, not just the fact of access. "Who looked up this named
  rejected candidate" is the question you will actually be asked.
- Keep the audit log in a table **no role can read via RLS** — service-role only.
  An audit log a user can edit is not an audit log.

---

## F · The personal-repo consequences (Q4)

You asked me to write these down rather than design around them.

### F.1 Collaborators get write access; there is no read-only tier

Correct, and unavoidable on a personal repo. The consequence you named is real:
`refresh.py`'s deliberate stop-before-commit becomes a **convention**, not a
gate. Any of the 3–4 collaborators can push a graph nobody reviewed.

**The cheapest mitigation that is not self-deception:**

Do not pretend to prevent it. **Detect it loudly.** Add a CI workflow that runs
on every push to `main` and fails if:

- `validate.py` reports any FAIL — this already catches the specific disaster
  (`graph.json` content changed while `plugin.json` did not, so no teammate
  receives the build); or
- `knowledge/graph.json` changed without `.version-lock.json` agreeing.

Why this and not branch protection: branch protection with a required status
check on a **private personal repo** requires a paid plan. If you have one,
enable it and this becomes a real gate — worth checking, it is a two-minute
answer and strictly better. If you do not, a local pre-push hook is *not* the
fallback: hooks are per-clone, opt-in and bypassable with `--no-verify`, so
relying on one is exactly the self-deception you asked me to avoid.

CI-that-fails-after-the-fact is honest: the bad push happened, and everyone
knows within a minute. That is a materially different thing from believing it
cannot happen.

### F.2 The committed history contains the hiring funnel

`knowledge/graph.json` is committed and contains **277 hiring rejections about
named external people**, 1,625 in-pipeline candidates, 39 per-instructor ratings
and 136 decline rates. Under Q3's two-role decision, **adding a collaborator
grants them `recruiting`-level data**, whether or not that is what you intended
by adding them.

There is no partial measure. Git history is not access-controlled by path.

**Option 1 — accept that the 3–4 collaborators are the recruiting role.**

Cost: zero. Requirement: it must be *true*. Ask, for each of the three or four
people, whether you would deliberately show them a spreadsheet of 277 named
external candidates you declined to hire. If yes for all, this is the right
answer and costs nothing.

**Option 2 — strip sensitive nodes from the committed artefacts before adding
anyone.**

This is a **history rewrite** — `git filter-repo` over every commit that touched
`knowledge/`, which is 20 of 26. I told you not to rewrite history, and this is
the exception, so here is the honest cost:

| Cost | Today | After collaborators join |
|---|---|---|
| Clones invalidated | **1 (yours)** | 4–5, each needing a fresh clone |
| Every commit SHA changes | Yes | Yes — and now other people's local branches are orphaned |
| Plugin marketplace installs broken | **0 installed** | one remove-and-reinstall each |
| Force-push to `main` required | Yes | Yes |
| Repo size | 27 MB → materially smaller | same |

**This is the cheapest it will ever be, by a wide margin.** One clone, zero
installs, one person to coordinate with — you. Every collaborator added
multiplies it.

**My recommendation: answer the Option 1 question first.** If all 3–4 are
genuinely recruiting-cleared, take Option 1 and move on; the rewrite buys
nothing. If even one is not, do the rewrite **this week**, before they are added.

**Independently of both, stop the bleeding.** Whichever you choose, future builds
should not keep committing the funnel. Split the artefact:

- `knowledge/graph.json` — `sensitive = false` only. Committed. This is what the
  plugin ships and what §E.1 says is safe to be unrevocable.
- `knowledge/graph-sensitive.json` — the funnel. **Gitignored**, projected into
  Postgres behind the `recruiting` RLS policy, never in git.

That change is cheap, needs no history rewrite, and means the exposure stops
growing while you decide about the past.

---

## G · Q6 — workflow management: CLOSED, out of scope

**Decided 2026-09-17: out of scope.** Recorded here rather than deleted, because
the reasoning is what makes the decision re-checkable if it is ever reopened.

The 92 workflows are inert lookup records: `steps`, `effort`, `alerts`, `tools`,
one `belongs_to` edge each. No owner (correctly — ownership is domain-level and
blank is the right final state), **no dependencies** (`depends_on` is 0 by
evidence, not omission), no status, no assignee, no due date, no run history.

"Managing" them requires all of that, and **none of it exists in the corpus.**
That is a new write-side application with its own schema and its own source of
truth, not a view over the knowledge graph. It should be phased separately, and
it is probably the largest single piece of work in the project.

The schema above does not block it: workflow state would be its own table
referencing `nodes.id`, which is exactly the §A.6 shape.

---

## H · What I recommend you decide next

1. **§F.2, Option 1 or 2.** Blocking for adding collaborators, and the cost only
   grows. One question: are all 3–4 recruiting-cleared?
2. **The property-level provenance gap (§A.5).** Schedule the pipeline fix before
   the migration, or the migration reproduces the omission faithfully.
3. **The extractor column fix (§A.4).** Small, and it removes 6 assertion-id
   collisions at the source rather than papering over them with an ordinal.
4. **Whether to stop storing calendar-derived edge fields (§B.4).** Changes what
   the migration projects, so it is cheaper to decide before than after.
5. **Q6 scope (§G).** Needed before the web app is planned, not before the schema
   is written.

---

*No migrations written. No tables created. `docs/DATABASE.md` follows your
approval of §A and §B.*
