# KB schema (`kb.*`) — migrations 0022–0028

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
