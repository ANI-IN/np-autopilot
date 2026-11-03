# Vision and roadmap: from the NP knowledge base to IK's organisational memory

Written 2026-11-04 (run 6), from the code at this commit. Every claim names
the file it was checked in. Where the code does not do something, this says
so.

**The vision.** Interview Kickstart gets one place that holds what the
organisation knows: its programmes, courses, people, documents and processes.
Several sources feed it, each source's permissions still apply, and people
and Claude can both ask it questions.

**Where we are.** One team (New Programs) has a working, audited, editable
knowledge base (`kb.*`). It has one intake path (the NP Autopilot pipeline,
which reads one Drive folder), role-based access for IK accounts, lexical
search and an MCP server. That is a good core. It is not yet a memory for the
organisation. The rest of this document lists what is missing and orders the
work.

---

## 1. What the code does today (the parts that matter for the vision)

| Capability | Where | Fit for the vision |
|---|---|---|
| One store of record, `kb` schema, RLS on every table, triggers for version, audit and archive cascade | `db/migrations/0022_kb_schema.up.sql`, `0023_kb_rls.up.sql` | Good. Keep it. |
| One rulebook (validation, roles, optimistic locking, proposals) | `web/lib/kb/service.py`, `validate.py`, `typedefs.py` | Good. Every new entry point must go through it. |
| An append-only change feed (`kb.changes`, `kind`, `node_ids`) | `0032_kb_contracts.up.sql`, `docs/CONTRACTS.md` §2 | Good. This is what change tracking and indexing will read. |
| Configurable record and relationship types, enforced in the database | `0027_kb_custom_types.up.sql`, `web/lib/kb/typedefs.py` | Good. New sources add types, not code. |
| An incremental, conflict-aware sync from the pipeline's tables | `web/lib/kb/sync.py`, `kb.sync_map` / `kb.sync_runs` (`0030`), resume (`0033`), exclusions (`0037`) | The right pattern, wired to one source. See §3. |
| A schedule | pg_cron + pg_net calling `/api/cron/kb-sync` (`0031_kb_sync_schedule.up.sql`, `api/index.py`) | Enough for one hourly job. Not a job runner. |
| Search | `service.search`: `websearch_to_tsquery('simple', …)` on name/summary/body plus `pg_trgm` similarity on names; resources by `LIKE` on title/URL | Lexical only. See §4. |
| AI access | `mcp_server/kb_server.py` (21 tools, HTTP client of `/api/kb/*`, per-user `ikkb_` token, `actor_type='ai'`, archive/delete always a proposal) and `plugins/ik-knowledge-assistant/` | Good. Safe by construction. See §5. |

---

## 2. Architecture gaps (each checked in the code)

**G1. Single-tenant, single-domain, by design.** No `kb` table carries an
organisation or workspace id (grep `tenant|org_id|workspace_id` over
`db/migrations` finds nothing). `kb.memberships` has `user_id` as its primary
key (`0022`), so a person has one role for the whole knowledge base. Who may
sign in is one deployment variable, `NP_ALLOWED_HD`. For "one IK memory" this
is fine: IK is one tenant. The real limit is that roles cannot be scoped to a
department or a space. Do not add multi-tenancy (see §8).

**G2. The old tables are the intake.** The sync reads `public.nodes`,
`edges`, `node_sources`, `node_layout` and `files`
(`sync.desired_state(conn, M, source="public")`). Those tables are written by
`pipeline/project_graph.py`, which **replaces them all in one transaction**
(its docstring, DECISIONS §B.3). So the KB's freshness is set by the last time
someone ran the pipeline by hand. Nothing schedules passes 0 to 4 or the
projection: `.github/workflows/ci.yml` has no `schedule:`, and README calls
"Refresh v2 (nightly)" not built. The pg_cron job only moves already-projected
rows into `kb`. The docstring of `project_graph.py` also says replace-all must
become a set-diff on the day the projection runs on a schedule.

**G3. The sync is a one-way projection, and it can only handle one source.**
- It never writes back. That is correct: Drive is `drive.readonly`, and the
  corpus is read-only (CLAUDE.md §1).
- Source identity is not namespaced. `kb.sync_map`'s key is `(unit, key)`,
  where `key` is a projection id. Records carry `external_id = 'np:<id>'`.
  `sync_runs.trigger` allows only `cron|manual|cli`. There is one advisory
  lock (`LOCK_KEY = 7302026`). A second source would share the key space and
  the lock.
- What "current" and "legacy" mean is NP Autopilot's own logic, copied from
  `public/index.html` (`sync.np_categories`). Another source will need its own
  logic.

**G4. No job runner beyond pg_cron.** The schedule is one cron entry that
POSTs to a Vercel function (`0031`). The work is time-boxed by
`KB_SYNC_BUDGET_SECONDS` (default 10) under `maxDuration` 60 (`vercel.json`),
and it resumes from `kb.sync_runs.resume`. There is no queue and no
per-job retry with back-off. A failed run is retried only because the next
tick runs the whole diff again, and its errors are kept in
`kb.sync_runs.errors`. This works for one hourly job of about 25,000 units:
an unchanged run takes 2.3 s and a first import takes 5 batches
(`docs/run6/SYNC_TIMING.md`). It will not work for document extraction
(downloads, parsing, embeddings), which takes minutes per file and must run
outside a 60 s function.

**G5. Search is lexical, not semantic.** It uses full-text search with the
`simple` dictionary (no stemming, no synonyms), trigram similarity on names
only, and `LIKE` on resource titles and URLs (`service.search`,
`0022` indexes `nodes_name_trgm` and `resources_title_trgm`). There is no
pgvector and no embedding anywhere (grep `vector|embedding` finds nothing).
**The bigger fact: there is little text to search.** The sync brings in
names, mapped props and curation notes as `body` (`sync.py`, "curation
notes -> body"). A cited file becomes a "Source" link with only its name and
Drive URL (`docs/ARCHITECTURE.md`, "What the KB cannot supply"). Document
content never reaches `kb`. The content crawl (`pipeline/06_crawl_content.py`)
writes redacted text into the pipeline's cache, not into the KB.

**G6. Permissions are workspace roles, not taken from the source.** RLS
gives `viewer` read access to everything in `kb` (`0023`: "viewer: read
everything in kb"). `kb.role()` makes any signed-in IK profile a viewer.
Pass 0 does not request Drive permissions: its `fields` list has id, name,
mimeType, modifiedTime, size and md5Checksum (`pipeline/00_fetch_drive.py`).
Two things keep this safe today, and neither will grow with the KB:
(a) the corpus scope is one folder that is shared with a service account,
and extraction reads only 20 declared name columns (`pipeline/lib/sources.py`,
CLAUDE.md §2); (b) the sensitive half (`graph-sensitive.json`) is never
projected, because "the recruiting RLS path" does not exist
(`project_graph.py`). `06_crawl_content.py` warns that row C is shared
`anyone`, so "the account can read it" is not a permission model.

**G7. Change tracking stops at the KB.** `kb.changes` records every KB write.
Source-side change detection is coarse: pass 0 compares `modifiedTime` and
md5 file by file and lists the whole folder each time. Pass 1 treats a
changed file as a hard fail (CLAUDE.md §1). Nothing uses the Drive Changes
API page token.

**G8. Monitoring is a page, not an alert.** `kb.sync_runs` holds the run
log, and admins see a banner when the last run failed (`public/kb/js/app.js`,
"sync-banner"). Nothing pages anyone. A schedule that silently stops (Vault
secret rotated, pg_cron job removed) shows up as no new rows, and nothing
checks for that.

**G9. Backups are an operator command.** `scripts/dev_db.py backup` runs
`pg_dump` (public + kb) into the gitignored `backups/`, and it refuses
production. The legacy delete exports before it deletes
(`web/lib/kb/legacy_delete.py`). The repository has no documented, tested
restore for production. Whatever Supabase provides depends on the plan and
is not checked in.

**G10. Remote MCP is single-user.** The HTTP transport binds 127.0.0.1 and
uses one server-side token (`docs/MCP.md`, "Claude.ai (remote)"). Per-user
OAuth is designed (`docs/AI_ARCHITECTURE.md`) and not built.

---

## 3. A connector framework, built from the sync we already have

The sync already contains the hard parts of a connector. The work is to name
the interface, namespace the bookkeeping and add the two missing pieces
(source permissions and a source cursor). It is not a rewrite.

### The interface (one Python protocol, in `web/lib/kb/connectors/`)

```
class Connector:
    key: str                       # 'np_autopilot', 'gdrive', 'uplevel', 'atlassian'
    def config_check(conn) -> list[str]          # mapping vs kb types (today: sync.load_mapping)
    def changes(cursor) -> (items, new_cursor)   # incremental listing at the source
    def desired(items) -> Desired                # records, links, relationships, attachments
    def acl(items) -> {source_key: [principal]}  # who may see it AT THE SOURCE
    def classify(desired) -> {source_key: 'current'|'legacy'}   # source-specific rules
```

One shared engine (today's `sync.run`, made generic) does everything else.

### How today's sync maps onto it

| Engine step | Today (`web/lib/kb/sync.py`) | Change needed |
|---|---|---|
| Configuration | `config/kb-projection-mapping.yaml`, checked against `config/taxonomy.yaml` by `load_mapping` | One mapping file per connector. The same check. |
| Desired state | `desired_state()` reads the old tables | Becomes `NpAutopilotConnector.desired()`. Unchanged in behaviour. |
| Current vs legacy | `np_categories()` (NP's rules) | Becomes `classify()`, per connector. |
| Diff | `kb.sync_map`: `checksum` (source) and `kb_checksum` (what the sync last wrote) | Add a `source` column to the primary key, `(source, unit, key)`, and `external_id` prefix = connector key. One additive migration. |
| Write | phases `records → owners → links → relationships → attachments → removed`, batched, `actor_type='sync'` | Unchanged. Record the connector key in the run. |
| Edited in the KB and changed at the source | `conflict_at`, never overwritten, listed on Data quality | Unchanged. |
| Gone at the source | `removed_at`: a record is set to `needs_review`, never deleted; relationships and attachments are archived; `restored_at_source` when the row comes back | Unchanged. |
| Permanent exclusions | `kb.sync_exclusions` (`0037`): a `rule` or one `record` the sync must never create again | Add `source`. |
| Records made in the KB | no `sync_map` row, never touched | Unchanged. |
| One run at a time | advisory lock `LOCK_KEY`, a "running" run counts as dead after `STALE_MINUTES` (20) | One lock per connector (`hashtext(key)`). |
| Time budget and resume | `budget_seconds`, `kb.sync_runs.resume` (`0033`) | Unchanged. Add `source` to `sync_runs`. |
| Kill switch | `KB_SYNC_ENABLED` | Add a per-connector `enabled` flag in a `kb.connectors` table. |
| Source cursor | none (full diff every run) | `kb.connectors.cursor` (e.g. a Drive `startPageToken`). |
| Source permissions | none | `kb.source_acl`. See §3.2. |

### 3.1 Google Drive first, directly

A `gdrive` connector reads Drive itself instead of the pipeline's tables. It
uses the service account, `drive.readonly`, and the folders it is shared
with: the same rule as pass 0. It produces **documents as resources** (title,
URL, mime kind as in `sync._mime_kind`, modified time, owner reduced to a
domain as `06_crawl_content.py` D4 does) plus their text for search (§4). It
does **not** extract people or contact columns. The allow-list in
`pipeline/lib/sources.py` stays the only path for structured entities
(CLAUDE.md §2). The NP Autopilot connector keeps feeding programmes,
modules, instructors and roles until the pipeline is retired.

### 3.2 Permission propagation from the source

- Store `kb.source_acl(source, source_key, principal_type, principal)`, where
  principal is a user e-mail, a group e-mail, `domain:interviewkickstart.com`,
  or `anyone`. It is filled by `acl()` on each run (Drive
  `permissions.list`, which needs `fields=permissions(...)` in the listing).
- RLS on `kb.resources` and their text chunks: a row with an ACL is visible
  only when the caller's e-mail, one of their groups or the IK domain is
  listed. Admins get no bypass. Records built by hand keep today's role rule.
- Groups need Directory API read access (`admin.directory.group.readonly`)
  and a cached membership table, refreshed by a job. **Decision for the
  owner:** without group expansion, a file shared with a group is either
  hidden from everyone (safe, and the default) or shown to all of IK (not
  acceptable).
- `anyone`-shared files are **not** treated as IK-wide content by default.
  `06_crawl_content.py` shows why: a file shared with anyone is public, and
  that says nothing about whether it is in scope.

### 3.3 Background jobs and retries

Keep pg_cron as the clock. Add a small `kb.jobs` table (connector, kind,
payload, attempts, `next_attempt_at`, last error). Workers take jobs with
`for update skip locked`. Back-off is exponential and capped. After N
attempts a job is a dead letter, shown in Settings → Sync. The Vercel
function keeps doing the fast diff. **Extraction and embedding** run in one
worker outside Vercel (a scheduled GitHub Actions job or a small container),
because they need minutes and the Drive key. That same worker can schedule
passes 0 to 4 and the projection, which closes G2. Do this only after
`project_graph.py` switches to a set-diff, as its docstring requires.

### 3.4 Uplevel LMS and Atlassian, later

They are the same interface. Each needs, first, an API with read-only
credentials and a stated scope (the same rule as `drive.readonly`); second,
an ACL story (LMS: cohorts; Confluence: space permissions); third, a mapping
file. Do not start one until §3.1 and §3.2 have run in production for a month.

---

## 4. Search and semantic retrieval (pgvector), filtered by source permissions

- **Content first.** Embedding today's KB would mostly embed names, which
  trigram search already finds. Semantic search is useful once the Drive
  connector puts document text in `kb`.
- **Schema.** `kb.chunks(id, resource_id or node_id, ordinal, text, tokens,
  embedding vector(n), source, source_key)`. Supabase supports `pgvector`, and
  an HNSW index is enough at this scale. The text is redacted before storage,
  as `06_crawl_content.py` already does ("redaction applied to the text BEFORE
  it reaches disk").
- **Permissions in the query, not after it.** The chunk inherits its
  resource's `kb.source_acl`. RLS filters chunks before ranking, so a hidden
  document cannot shape results. `service.search` gains a hybrid mode:
  lexical score (today's) plus vector similarity, merged by rank.
- **Re-embed on change.** `kb.changes` `link.update` and `record.update`
  queue a job (§3.3). Store the embedding model in the row, so a model change
  is a planned backfill.
- **Not now:** an external vector database. It would hold a second copy of
  permissions outside RLS.

## 5. AI querying through the existing MCP server and plugin

The MCP server is already the right shape: a thin HTTP client, the caller's
own token, RLS as that user, retrieved text marked as data, `sources` on every
answer (`mcp_server/kb_server.py`, `docs/MCP.md`). Extend it, do not replace it:

1. Have `search_knowledge` call the hybrid search, and add
   `get_passages(query, k)`, which returns permitted chunks with their
   citation (file name + Drive link). The answer is built in Claude with the
   citations. The server does not generate answers.
2. Build per-user OAuth for remote use (G10), so a Claude.ai connector acts
   as each person, not as one token.
3. Keep `plugins/ik-knowledge-assistant/server/kb_server.py` byte-identical
   to `mcp_server/kb_server.py` (`tests/test_kb_plugin.py`).
4. Keep every AI write a proposal (archive/delete) or attributed
   `actor_type='ai'`.

## 6. Monitoring, backups and recovery

- **Alerting (G8).** A pg_cron check every 15 minutes covers three cases: the
  last finished run is older than 2 schedule intervals, the last run has
  `status = 'error'`, or the conflict count rose by more than X. It posts to
  one Slack webhook through pg_net (the secret goes in Vault, like
  `kb_sync_secret`). Later, the same rule covers each connector and the
  dead-letter queue.
- **Backups (G9).** Confirm and write down the production plan's backup and
  point-in-time recovery window. Add a weekly logical dump of `kb` to storage
  outside Supabase, with a **restore drill**: restore into the local stack and
  run `eval/kb_parity.py`-style counts. The audit log is append-only and is
  part of the dump.
- **Recovery runbooks.** Cover four cases: (a) a bad sync (`KB_SYNC_ENABLED=false`,
  then `select kb.sync_schedule_remove();`, then restore or archive by
  `actor_type='sync'` in a time window); (b) a bad map read (`NP_MAP_SOURCE=old`,
  `docs/ARCHITECTURE.md` "Rollback"); (c) a leaked token (revoke in Settings →
  API tokens); (d) a source ACL mistake (turn off the connector, purge its
  chunks).

---

## 7. Prioritised roadmap

Value: H/M/L for "IK can trust one memory and ask it questions". Effort is
for one engineer who knows this repository. Estimates are wider for items
that depend on access nobody has yet.

| # | Item | Value | Complexity | Effort (pd) | Depends on |
|---|---|---|---|---|---|
| 1 | Sync and schedule alerting (stale, failed, conflict spike) to one channel | **H**: today a stopped sync is invisible until someone looks | L | 1–2 | Slack webhook (owner) |
| 2 | Production backup check + weekly `kb` dump + one restore drill | **H**: the KB now holds edits that exist nowhere else | L | 2–3 | Production access (owner) |
| 3 | Schedule the intake: passes 0–4 + projection in one worker, after switching `project_graph.py` to a set-diff | **H**: without it, "hourly sync" copies a stale projection | M | 5–8 | Worker host + Drive key as a secret (owner) |
| 4 | Namespace the sync (`source` on `sync_map`, `sync_runs`, `sync_exclusions`; `kb.connectors`; one lock per connector) and move NP's code behind the connector interface | **M**: no user-visible change, and every later source needs it | M | 4–6 | none |
| 5 | `kb.jobs` with retries, back-off and dead letters; worker uses it | **M**: needed before any slow work (extraction, embedding) | M | 3–5 | 3, 4 |
| 6 | Drive connector: documents as resources + redacted text, incremental by Changes API cursor, same folder scope | **H**: the first time the KB holds what documents *say* | H | 10–15 | 4, 5 |
| 7 | Source ACLs (`kb.source_acl`, RLS on resources/chunks, group cache) | **H**: required before 6 goes beyond the NP folder; it is the main risk | H | 8–12 | 6; Directory API scope (owner decision) |
| 8 | Hybrid search: pgvector chunks + today's lexical score, RLS-filtered | **M**: real gain only once 6 exists | M | 5–8 | 6, 7 |
| 9 | MCP `get_passages` + hybrid `search_knowledge` | **M**: Claude answers from documents with citations | L | 2–3 | 8 |
| 10 | Per-user OAuth for remote MCP (Claude.ai connector) | **M**: lets non-engineers use it without a local server | M | 5–8 | none (can run in parallel) |
| 11 | Uplevel LMS connector | **M**: programme delivery data in one place | H | 10–20 | 4–7; API access and scope (owner) |
| 12 | Atlassian connector | **L–M**: valuable, but it duplicates what Confluence search already gives | H | 10–20 | 4–7; space permission mapping |

Order: 1–2 now (about a week, low risk). Then 3–5, which make the system
honest about freshness and ready for slow work. Then 6–7 together, because
content without permissions must not ship. Then 8–10. 11–12 come only when a
named team asks.

## 8. What not to build yet, and why

- **Multi-tenancy (org ids, per-tenant schemas).** IK is one organisation.
  Scoped roles, if anyone needs them, are a `space` on records, not tenancy.
- **Two-way sync or write-back to Drive.** The corpus is read-only, the scope
  is `drive.readonly`, and filename typos are citation keys (CLAUDE.md §1).
- **A general workflow engine (Airflow, Temporal, a message broker).** One
  `kb.jobs` table and one worker cover a few connectors at this volume.
- **Drive push notifications / real-time source webhooks.** Hourly is enough
  for the questions people ask. Webhooks need a public endpoint and renewal
  and add failure modes.
- **An external vector database.** It puts a copy of permissions outside RLS.
- **Widening entity extraction to more columns or files "while we're
  there".** That is the step that removes today's contact-data protection
  (CLAUDE.md §2). It is a separate decision with its own review.
- **Stored LLM-written summaries presented as facts.** Hand or AI content
  must stay attributed (`origin: hand`, `actor_type='ai'`) and never look
  like a scan result (CLAUDE.md, "Other traps").
- **Projecting the sensitive half (`graph-sensitive.json`).** Not until a
  recruiting role exists in RLS and the owner decides who sees hiring data.
