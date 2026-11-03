# KB schema (`kb.*`) — migrations 0022–0037

The authored knowledge base lives in its own Postgres schema, `kb`. The pipeline's
projection tables in `public` (`nodes`, `edges`, `node_sources`, …) are untouched:
they are rebuilt wholesale from `graph.json` on every refresh, so app edits cannot
live there (DECISIONS §B.1). Nothing in `kb` references `public` except
`kb.role()` reading `public.np_role()` / `profiles`.

## Conventions (every mutable table)

`id uuid` · `created_by` · `updated_by` · `created_at` · `updated_at` ·
`version int` · `status` · `archived_at`.

- `kb.stamp()` (BEFORE trigger) sets authorship from the verified JWT `sub`
  (`kb.actor_id()`), and **bumps `version` itself** — a caller cannot set it.
- `kb.audit()` (AFTER trigger, SECURITY DEFINER) writes `before`/`after` JSON to
  `kb.audit_log` for every insert/update/delete, with `actor_type`
  (`human` | `ai` | `import` | `system`). Token hashes are stripped.
- Soft delete: `archived_at` + `status='archived'` (CHECK keeps them consistent).
  Hard delete: admin only, and only of an already-archived row (RLS).

## Tables

| Table | Purpose | Key constraints |
|---|---|---|
| `node_types` | configurable record types (`key`, label, colour, `is_container`) | key `^[a-z][a-z0-9_]{1,40}$` |
| `edge_types` | configurable relationship types (`allow_self`) | key shape |
| `edge_type_rules` | allowed (edge type, source type, target type) | unique triple; **no rule = no edges** |
| `nodes` | records: name, summary, body, `scope_id` (course/program), owner, props, import provenance | unique `(type, scope, kb.norm(name))` among live rows; name ≤300, no `@`/URL; not its own scope |
| `edges` | typed directed relationships, note, `archived_with` | unique live `(source, target, type)`; `kb.check_edge()` trigger: endpoints live (locked `FOR SHARE`), type rule exists, self-edge only if allowed |
| `resources` | reusable links (url, title, kind) | http(s) URL ≤2048; unique live normalised URL |
| `node_resources` | many-to-many attachment + note + position | unique live pair; `kb.check_attachment()` |
| `tags`, `node_tags` | tagging | unique normalised tag name |
| `memberships` | KB role per user (admin/editor/contributor/viewer) | |
| `api_tokens` | per-user MCP tokens: SHA-256 only, prefix, expiry, revocation | hash shape |
| `proposals` | archive/delete requests awaiting a human (from contributors and AI) | action/table/status enums |
| `audit_log` | before/after history | written only by trigger |
| `import_runs` | Sheets import runs and their reports (0024) | |

`kb.norm(t)` = trim, collapse whitespace, lowercase. Courses and programs are
node types with `is_container = true` (decision in docs/AUDIT.md §KB): they get
relationships, resources, history and search for free.

### Starting vocabulary (seeded by 0022; admins extend it in Settings)

Node types: `program`, `course`, `module`, `topic`, `instructor`, `process`.
Edge types and allowed pairs:

| Edge | Allowed source → target |
|---|---|
| contains | program→course, program→module, course→module, module→topic |
| covers | course→topic, module→topic |
| teaches | instructor→course, instructor→module |
| prerequisite | course→course, module→module, topic→topic |
| related | topic↔topic, course↔course, module↔module, process→process/course/program |

### The course shape, link health and owner names (0026)

- Node types `domain` (subject area), `week` (a week of a course), `session` (a live
  session). Added pairs: covers course/program→domain, session→topic; contains
  module→week, course→week, week→session; teaches instructor→session; related
  domain↔domain.
- Resource kinds widened: + `recording`, `assignment`, `solution`, `repo`.
- `kb.link_checks` — the LAST link-check result per resource (`status` ok |
  needs_auth | forbidden | broken | timeout | unreachable, `http_status`,
  `checked_at`, `checked_by`). Separate from `kb.resources` so recording a check
  never bumps a resource's version. Read: viewer; write: editor (RLS).
- `kb.people()` — SECURITY DEFINER; members' `user_id, email, role`, for viewers
  and up. Profiles and memberships stay self-only under RLS; this is the one
  narrow window, so owners and members can be shown by email.
- Down refuses while any record or resource uses the new types or kinds.

### Archive cascade (`kb.cascade_archive()`)

Archiving a node archives its live edges and attachments and records
`archived_with = <node id>`. Restoring brings back **exactly those** whose other
endpoint is live and that would not duplicate a live row — never one a person
archived deliberately. Records scoped under an archived course stay live (the
impact dialog says so).

### Concurrency

- Optimistic locking: every update is `… where id = $1 and version = $2`; 0 rows
  → 409 with the current record.
- Edge-vs-archive race: the edge trigger takes `FOR SHARE` on both endpoints, the
  archive takes the row lock; whichever commits second sees the other
  (`tests/test_kb_schema.py::test_concurrent_archive_and_edge_create_never_leave_an_orphan`).

## Indexes

Node type, scope, `(updated_at, id)` for cursor pages, GIN full-text on a
generated `tsvector` (name A, summary B, body C), GIN trigram on `name_norm`;
edge source/target partial indexes on live rows; resource URL uniqueness and
title trigram; audit `(table, row, id)`.

## RLS (0023) — enforced in the database

`kb.role()` = membership role, else `viewer` for anyone with an IK profile
(`public.np_role() <> 'none'`), else `none`. `kb.role_at_least(r)` compares ranks.

| Table(s) | select | insert | update | delete |
|---|---|---|---|---|
| nodes, edges, resources, node_resources, tags | viewer+ | contributor+ | contributor+ (archive/restore: editor+, via `kb.guard_archive()` trigger) | admin, archived rows only |
| node_tags | viewer+ | contributor+ | — | contributor+ |
| node_types, edge_types, edge_type_rules | viewer+ | admin | admin | admin |
| memberships | own row, or admin | admin | admin | admin |
| api_tokens | own | own (viewer+) | own | — |
| proposals | viewer+ | contributor+ (status pending) | editor+ | — |
| audit_log | viewer+ (token rows: admin or own) | **nobody** (trigger only) | nobody | nobody |
| import_runs | viewer+ | admin | admin | — |

`kb.resolve_token(hash)` (SECURITY DEFINER) returns the owner of a live,
unexpired, unrevoked token and stamps `last_used_at`; executable by
`authenticated` since 0025 so the web app can authenticate MCP calls without a
privileged connection.

Every policy is proven against the database directly in `tests/test_kb_rls.py`.

## Custom types, link kinds, reviews, templates, views (0027)

- **Record types** (`kb.node_types`) gain `plural`, `icon`, `fields` (JSON array
  of field definitions), `allowed_parents` (placement), `parent_required`,
  `default_status`, `owner_rule` (`creator` | `none`) and `is_core`. Labels are
  unique (case-insensitive) among live types.
- **Field definition**: `{key, label, kind, help, required, default, archived,
  options: [{value, label}] (selects), ref_types: [type keys] (reference)}`.
  Kinds: short_text, long_text, number, date, datetime, duration (minutes), url,
  single_select, multi_select, person, reference, checkbox.
- `kb.check_type_def()` (trigger) checks the shape, refuses a changed type key,
  and refuses dropping or re-keying a field: removing one means `archived: true`
  (hidden, data kept, restorable).
- `kb.check_node_props()` (trigger) validates every record's `props` against its
  type's live fields with `kb.field_value_error()`: options, references to the
  allowed types, members for person fields. **Required fields are enforced on
  INSERT only** (and not for imports): a field made required later flags existing
  records on Data quality instead of blocking them.
- **Relationship types** gain `cardinality` (many_to_many | one_to_many |
  many_to_one | one_to_one; enforced in `kb.check_edge()`) and `is_core`; new
  core type `sme` ("subject expert for"); new placement rules for Program >
  Course > Domain > Module > Week > Session; `kb.edges.position` orders children
  in the outline.
- **`kb.link_kinds`**: the service a URL lives on: key (permanent), label, icon,
  `patterns` (regular expressions, validated), `defaults` (e.g. default resource
  kind). Built in: Drive folder, Drive file, Doc, Sheet, Slides, UpLevel
  (`uplevel.interviewkickstart.com`, from the repo's own data), GitHub, YouTube /
  video, Recording, Live class link, Website. `kb.resources.link_kind` references
  it; existing resources were classified by the patterns.
- **Resource kinds** widened with the content types: kyp_slides, speaker_notes,
  live_class_link, assignment_brief, problem_statement, evaluation_criteria,
  question_bank, interview_guide, reading, reference_doc. Resources gain
  `owner_id` and `tags`.
- **Records** gain `review_status` (none | needs_review | approved) and `co_owners`.
- **Proposals** can be `create` (a contributor's new record; payload = the whole
  create body) and `type_change` (an editor's change to types, approved by an
  admin). **Contributors can no longer insert records directly**: the `nodes`
  INSERT policy requires editor (their creates are proposals).
- **`kb.flags`** ("flag as incorrect", assigned to the owner; resolved by the
  assignee, the flagger or an editor), **`kb.templates`** (structure of a course
  or program), **`kb.saved_views`** (personal or shared table views). All with RLS.
- Down refuses while any data uses what 0027 added.

## Palette and Realtime (0028)

Built-in type colours move to one accessible, non-purple palette (only rows
still holding their seed colour). `kb.audit_log` joins the `supabase_realtime`
publication (when it exists) so browsers can be told that something changed;
Realtime forwards changes through the subscriber's RLS.

## Activity, change feed, relationship review, graph layouts (0029, run 3)

- **Actors.** `kb.actor_type()` returns `system` when there is no verified user
  and no declared actor (a migration, psql, a fixture); it used to return
  `human` with a null id, which could only be shown as "Someone". Old rows of
  that shape are relabelled `system`. `kb.actor_emails(uuid[])` (viewer+,
  SECURITY DEFINER) names any profile that ever acted, including former
  members.
- **Append-only audit log.** Trigger `audit_log_immutable` refuses UPDATE and
  DELETE for every role that is not a superuser (on Supabase that is every
  role, `postgres` included). API roles also have no INSERT/UPDATE/DELETE
  grants. Locally, the demo seed and test resets clear the log with TRUNCATE
  (table owner only), which row triggers do not cover.
- **Who reads the audit log** (`audit_log_select`): admins every row; editors
  rows they made and rows about their scope, `kb.my_scope_ids()` = records they
  own or co-own, everything placed inside them (contains edges and `scope_id`,
  any depth) and the links they own; nobody else. A single record's history for
  any viewer+ goes through `kb.record_history(id, max)` (SECURITY DEFINER,
  checks the role): the record's own rows, its relationships, links and tags.
- **`kb.changes`**: the collaboration feed without content (id = audit id,
  table, row, action, version, actor). Written by `kb.audit()` with the audit
  row; readable by every member (api_tokens/memberships rows: admin or the
  actor). Realtime publishes `kb.changes` instead of `kb.audit_log`.
- **Relationship types.** `edge_types.review_status` (`reviewed` |
  `unreviewed`) and `merged_into`. Policies: admins do anything; editors may
  INSERT only unreviewed, non-core types, and rules only for unreviewed types
  they created; contributors and viewers cannot write types (they propose).
  Trigger `edge_types_check_name` refuses a label or inverse whose
  `kb.rel_stem()` (lower case, punctuation and spacing collapsed, plural and
  -ed/-ing/-es endings removed, word by word) matches any live type's label or
  inverse: "Teaches", "teach" and "taught by" all hit `teaches / taught by`.
- **`kb.graph_positions`** (layout, node_id, x, y): `layout` is `default` (the
  shared layout) or a saved view's id. Viewer+ read, contributor+ write. Layout
  only: never touches a record's version.
- Indexes for the activity filters: audit_log by actor, by table, and by the
  `source_id` / `target_id` / `node_id` / `resource_id` inside before/after.
- Down refuses while relationship types are unreviewed or merged, or saved
  layouts exist; otherwise restores 0028's audit function, policy and
  publication.

## Sync, owners, contracts, people, invites (0030–0037, runs 5–6)

From the `.up.sql` files; each has a `.down.sql`. 0036 is unused.

- **0030 — legacy flag, owners from roles, sync bookkeeping.**
  `kb.nodes` gains `is_legacy` (bool, set by import/sync only; hidden from
  default lists and counts), `owner_record_id` (the Primary's person record)
  and `co_owner_record_ids uuid[]` (Backups in order). New tables:
  `kb.person_accounts` (`node_id` PK → a person record, `email` unique
  case-insensitively, `user_id`, `linked_at`; triggers resolve the e-mail to an
  account and apply the record owners; a profile insert links on sign-in);
  `kb.sync_map` (PK `unit, key`; `unit` record | link | relationship |
  attachment; `kb_table`, `kb_id`, `checksum`, `kb_checksum`, `first_seen`,
  `last_seen`, `last_written`, `removed_at` (gone at source, flagged never
  deleted), `conflict_at`, `conflict_checksum`; editor+ read);
  `kb.sync_runs` (`id`, `started_at`, `finished_at`, `status` running | ok |
  error | skipped, `trigger` cron | manual | cli, `actor_id`, `counts`,
  `conflicts`, `errors`, `message`; admin read); `kb.legacy_archive`
  (`node_id`, `archived_at`, `reason`: what the legacy step archived, so it can
  be restored; editor+ read). `kb.actor_type()` learns `sync`.
- **0031 — the sync schedule.** `kb.sync_schedule_install(endpoint, cron =
  '0 * * * *')` and `kb.sync_schedule_remove()`: pg_cron + pg_net POST to
  `/api/cron/kb-sync` with the secret read from Vault (`kb_sync_secret`) when
  the job fires. Owner only; a no-op message where pg_cron is absent.
- **0032 — the schema behind docs/CONTRACTS.md.** `kb.node_types.shape`
  (round-rectangle | ellipse | diamond | hexagon | triangle | rectangle | tag |
  barrel; built-ins seeded) and `owner_expected` (bool); `kb.edge_types.color`
  (`#rrggbb`) and `line_style` (solid | dashed | dotted; built-ins seeded);
  `kb.changes.kind` and `kb.changes.node_ids uuid[]`, derived by `kb.audit()`
  through `kb.change_kind()` / `kb.change_node_ids()`. `kb.change_only()`
  triggers emit content-free change rows (no audit row) for `graph_positions`
  (`layout.update`), `person_accounts` (`owner.account`) and finished
  `sync_runs` (`sync.run`).
- **0033 — data flow and people.** The `domain` type gains a `slug` field (the
  map's SD1–SD4 codes; the sync fills it). `kb.landing_stats()` (SECURITY
  DEFINER, counts only, for the signed-out landing page). `kb.sync_runs.resume`
  (jsonb: where a time-boxed run stopped). `kb.proposals.action` adds `update`
  and `claim`. `kb.guard_contributor()` triggers on nodes, edges, resources and
  node_resources: a contributor's field edits, archives and restores must go
  through Approvals. `kb.person_accounts.linked_by` (admin | csv |
  sign_in_email | sign_in_name | claim); addresses readable by admins and the
  person only. Functions: `kb.person_name_key`, `person_name_of`,
  `auto_link_person` (on sign-in: by e-mail, else an unambiguous name),
  `link_me`, `person_candidates_for_me`, `claim_person`, `apply_claim`; the
  sign-in trigger `kb.profile_links_person()` is replaced.
- **0034 — performance indexes and two guards.** `edges_source_all_idx` and
  `edges_target_all_idx` (full, not partial: reads that include archived
  relationships). `kb.refuse_ai_admin()` triggers: an AI token cannot change
  memberships or person_accounts, nor delete nodes, edges or resources.
  `kb.keep_an_admin()` on memberships: a request can never leave the
  workspace without an admin.
- **0035 — member invites.** `kb.member_invites` (`id`, `email` lower-case
  `@interviewkickstart.com` only, `role` admin | editor | contributor | viewer,
  `status` pending | applied | revoked, `user_id`, `applied_at`, the standard
  authorship/`version`/`archived_at` columns; one pending invite per address;
  admin only, refused to AI). Applied at once if the account exists, else on
  first sign-in (`kb.apply_member_invite()` on `public.profiles`). `kb.audit()`
  drops the `email` column for this table. `kb.role()` counts a membership only
  for a caller with an IK profile.
- **0037 — sync exclusions.** `kb.sync_exclusions` (PK `unit, key`; `unit` rule
  | record, `reason`, `created_at`): rules the sync applies (key
  `np_legacy_domains_modules`) and source rows it must never create again,
  written by `web/lib/kb/legacy_delete.py`. Admins read; only the owner writes.
