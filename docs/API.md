# KB HTTP API — `/api/kb/*`

Served by the existing single WSGI entrypoint (`api/index.py::_serve_kb`) →
`api/kb_routes.py` (thin adapter) → `web/lib/kb/service.py` (all rules).

**Auth:** `Authorization: Bearer <token>` — a Supabase session token from the
browser sign-in, or a per-user KB API token (`ikkb_…`, MCP). Token callers act as
the token owner and are attributed `actor_type=ai`. Every request runs as the
`authenticated` role with the caller's claims, so RLS applies to every statement.

**Transactions:** one request = one transaction. Any refusal rolls everything back
(a multi-step create is atomic); success commits.

## Errors

| Status | `error` | Meaning / extra fields |
|---|---|---|
| 401 | `unauthorised` | no/invalid/expired/revoked token |
| 403 | `permission_denied` | role too low; `required_role`, `role` |
| 404 | `not_found` | |
| 409 | `version_conflict` | stale `version`; **`current`** = the record now (full detail) |
| 409 | `duplicate` | name/URL/edge exists; **`existing`** = that record |
| 422 | `validation_error` | `field`, sometimes `rule` |
| 202 | `approval_required` | the change was recorded as a proposal; `proposal_id` |

## Endpoints

| Method & path | Role | Notes |
|---|---|---|
| `GET /me` | any | `{user_id, role}` |
| `GET /types` · `POST /types/node` · `POST /types/rule` | viewer · admin · admin | node/edge types and allowed pairs |
| `GET /dashboard` | viewer | counts per type, totals, needs-attention lists and counts, completeness, 20 recent changes (empty below editor; run 3). Cached per caller until the next change |
| `GET /counts` | viewer | the sidebar's numbers: totals and `attention {counts, total}`, the same definition as the dashboard (run 3) |
| `GET /activity` | editor (admin: all; editor: own + scope, enforced by RLS) | `actor`, `action`, `table`, `source` (app, ai, import, sync, system), `record`, `from`, `to`, `q`, `cursor`, `limit`; `format=csv` returns `{filename, csv}`. Each item: actor_label, source, label, exists_now, changes [{field, before, after}] |
| `GET /nodes/{id}/history` | viewer | through `kb.record_history`; same item shape as `/activity` |
| `GET /changes?since=` | viewer | the collaboration feed (`kb.changes`), no row content |
| `GET /graph/positions?layout=&ids=` / `POST` `{layout, positions}` / `DELETE ?layout=` | viewer / contributor | saved graph layout; never changes records |
| `GET /types/edge-similar?label=&inverse_label=` | viewer | the existing relationship type a new name would duplicate, if any |
| `POST /types/edge` | admin: reviewed; editor: unreviewed + review proposal; contributor: 202 proposal | near-duplicate names: 409 with `existing` |
| `POST /types/edge/{key}/merge` `{into, flip, preview}` | admin | moves every relationship; `preview: true` only counts |
| `POST /proposals/{id}/approve` `{label, inverse_label, merge_into}` | admin for type changes | an edge-type review can rename or merge while confirming |
| `PATCH /tags/{id}`, `POST /tags/{id}/merge|archive|restore`, `GET /tags/{id}/impact` | editor | rename, merge, archive (returns the records it came off), restore onto them |
| `POST /members/{user}/remove` | admin | archives the membership (not yourself, not the last admin) |
| `PATCH /templates/{id}`, `POST /templates/{id}/restore` | editor | rename, restore |
| `POST /edges/{id}/retype` `{type, flip}` | contributor | archive + create in one transaction, note kept |
| `GET /me` | any | `admin_links` only for a verified admin (Back to NP Autopilot) |
| `GET /search?q=&types=&limit=` | viewer | websearch FTS + trigram; resources by title/URL |
| `GET /changes?since=<audit id>` | viewer | change feed for collaboration (cursor) |
| `GET /nodes?type=&scope=&q=&status=&tag=&owner=&created_by=&sort=updated\|name&cursor=&limit=` | viewer | cursor pages: default 50, max 200 |
| `POST /nodes` | editor (contributor: 202 proposal, validated first) | one transaction: `{type, name, summary, body, status, review_status, owner_id, co_owners, props, parents: [id or {new: {type, name, parent}}] (nested inline creates), scope (= first parent), edges: [{type, direction, node: id or {new}}], resources: [{resource_id} or {url, title, kind, link_kind, description, owner_id, tags, note}], instructors, smes, tags}`. Any failure rolls everything back and names the `field` (`parents.0`, `edges.1`, `resources.2`, `props.difficulty`). |
| `GET /nodes/{id}` | viewer | detail: `outgoing`, `incoming`, `resources`, `tags`, `children_count` |
| `PATCH /nodes/{id}[?force=1]` | contributor (force: editor) | **requires `version`** |
| `GET /nodes/{id}/impact` | viewer | live edges, attachments, scoped records |
| `POST /nodes/{id}/archive` · `/restore` | editor (contributor/AI → 202 proposal) · editor | |
| `POST /nodes/{id}/duplicate` | contributor | copy as draft: text, tags, resources (not edges) |
| `DELETE /nodes/{id}` | admin | archived rows only |
| `GET /nodes/{id}/history` | viewer | audit rows |
| `GET /nodes/{id}/neighbourhood?depth=1\|2&types=` | viewer | ≤300 nodes; `total`, `truncated` |
| `GET /nodes/{id}/validate` | viewer | course/program structure check |
| `POST /nodes/{id}/resources` | contributor | `{resource_id}` or `{url, title, kind}`; existing URL → reused |
| `POST /nodes/{id}/tags` · `DELETE /nodes/{id}/tags/{tag}` | contributor | |
| `/courses`, `/programs` (+ `/{id}`) | as `/nodes` | type fixed |
| `GET /edges?node=&type=&cursor=` · `POST /edges` | viewer · contributor | `{type, source_id, target_id, note?}` |
| `GET\|PATCH\|DELETE /edges/{id}` · `POST /edges/{id}/archive\|restore` | | as nodes |
| `GET /resources?q=&kind=&status=&cursor=` · `POST /resources` | viewer · contributor | duplicate URL → 409 with `existing` |
| `GET\|PATCH\|DELETE /resources/{id}` · `POST /resources/{id}/archive\|restore` | | as nodes |
| `POST /attachments/{id}/detach` | editor (contributor → proposal) | |
| `GET /proposals?status=` · `POST /proposals/{id}/approve\|reject` | viewer · editor (humans only) | approve executes the change |
| `GET /tokens` · `POST /tokens` · `POST /tokens/{id}/revoke` | own | raw token returned once |
| `GET /members` · `POST /members/{user_id}` | admin | `{role}`. GET also returns `invites` (pending) and `roles` (what each role can do) |
| `POST /members/invite` | admin | `{email, role}`: an @interviewkickstart.com address only (checked by the server and the database); applied now if they have signed in, else at their first sign-in (0035) |
| `POST /members/invites/{id}` · `POST /members/invites/{id}/revoke` | admin | change a pending invitation's `{role}`, or withdraw it |
| `GET /people` | viewer | members' `user_id, email, role` (owner names) |
| `GET /types[?archived=1]` | viewer | record types (fields, placement, record counts), relationship types (rules, cardinality), link kinds, resource kinds, field kinds, palette |
| `POST /types/node` / `PATCH /types/node/{key}` | admin (editor: 202 proposal) | safe changes only (docs/SCHEMA.md 0027); `replacements: {field: {old: new}}` for removed options in use; returns `warnings`, `converted_records` |
| `POST /types/node/{key}/archive`, `/restore`, `/duplicate` | admin (editor: proposal) | archive refused (409) while records use it; core types never archived |
| `POST /types/node/{key}/change-type` | admin (editor: proposal) | `{to, ids?, field_map: {old_key: new_key or null}}`; all or nothing |
| `POST /types/edge`, `PATCH /types/edge/{key}`, `POST /types/edge/{key}/archive` | admin (editor: proposal) | `{label, inverse_label, cardinality, allow_self, rules: [{source, target}]}`; narrowing reports, never deletes |
| `POST /types/link`, `PATCH /types/link/{key}`, `POST /types/link/{key}/archive` | admin (editor: proposal) | `{label, icon, patterns: [regex], defaults: {kind}}` |
| `GET /nodes/check-name?type=&name=&scope=` | viewer | `{exact, similar}` for the duplicate warning |
| `POST /nodes/bulk` | contributor | `{ids, set: {owner_id, status, review_status}, add_tags, remove_tags, add_parent}` |
| `POST /nodes/bulk-archive` | editor (contributor: proposals) | `{ids}` |
| `GET /nodes/{id}/completeness`, `/resources/{id}/completeness` | viewer | score and missing checks; for containers the subtree average and weakest items |
| `GET /nodes/{id}/delete-impact`, `/resources/{id}/delete-impact` | viewer | what a permanent delete removes with it |
| `GET /archived?kind=records,resources,relationships` | viewer | newest first |
| `GET /outline?root=`, `POST /outline/reorder` | viewer, contributor | tree from `contains`; `{parent_id, child_ids}` |
| `GET /flags?status=&target=`, `POST /flags`, `POST /flags/{id}/resolve` or `/dismiss` | viewer | assigned to the owner |
| `GET /templates`, `POST /templates`, `POST /templates/{id}/instantiate` or `/archive` | viewer, editor | `{source_id, name}`; `{name, parents}` |
| `GET /views`, `POST /views`, `PATCH` or `DELETE /views/{id}` | viewer (own) | `{name, shared, config}` |
| `PATCH /attachments/{id}` | contributor | `{note}`: the link's purpose on this record |
| `GET /realtime` | viewer | `{url, key}` only when `KB_REALTIME_ORIGIN` is configured; else `{}` (poll `/changes`) |
| `GET /instructors?course=&q=` | viewer | |
| `GET /quality` | viewer | totals, completeness, orphans, `unowned`, `links` (checked/ok/needs-sign-in/broken + broken list), duplicates |
| `GET /quality/missing-resources?type=` · `/quality/duplicates?threshold=` · `/quality/link-candidates` | viewer | |
| `GET /nodes?legacy=current\|only\|all` | viewer | run 5: legacy records (NP Autopilot's "older sheets") are left out unless asked for (`current`, the default) |
| `PATCH /nodes/{id}` `{owner_record_id, co_owner_record_ids}` | contributor | run 5: owners by role (P; B1-B3 in order); live instructor or team member records only (422 otherwise) |
| `POST /nodes/{id}/account` `{email}` · `DELETE /nodes/{id}/account` | admin | run 5: link a person record to a sign-in; resolves now or at their first sign-in, then they own what the record owns by role |
| `GET /views/teaching?domain=&role=&legacy=&q=` | viewer | run 5, "Who teaches what": `{instructors, columns, cells [{instructor_id, target_id, role, tier}], domains, counts}` |
| `GET /views/timeline` | viewer | run 5, "Programme timeline": programmes -> weeks -> modules with sessions and decks |
| `GET /quality/sync` | editor | run 5: `{conflicts, removed_at_source}` from the sync |
| `GET /sync` · `POST /sync/run` | admin (not the AI assistant) | run 5: the run log, `enabled`, `failing`; "Sync now" (one time-boxed run) |
| `POST /api/cron/kb-sync` (outside `/api/kb`) | `Authorization: Bearer $KB_SYNC_SECRET` only (no user session) | run 5: the scheduled run; 401 without the secret or with one shorter than 24 characters |
| `POST /quality/link-results` | editor | `{results: [{id, status, http?, redirected_to?}]}` ≤200; stores the last check per resource. The server never fetches a URL itself |

Tests: `tests/test_kb_api.py` (every family: success, 422, 403, 404, 409 conflict,
409 duplicate), `tests/test_kb_concurrency.py`.

## Run 6: the graph read API and the change-feed kinds

- `GET /api/kb/graph`: every graph's records and relationships, filtered and paged
  (`types`, `rels`, `legacy`, `archived`, `focus` + `depth`, `scope`, `limit`, `cursor`).
  Shape, paging rule and errors: docs/CONTRACTS.md §1.
- `GET /api/kb/changes?since=<id>`: each row now also carries `kind` (for example
  `record.archive`, `relationship.create`, `reltype.update`, `layout.update`, `sync.run`) and
  `node_ids` (the records to refresh). docs/CONTRACTS.md §2.
- `GET /api/kb/types`: node types carry `shape` and `owner_expected`; relationship types carry
  `color` and `line_style` (custom types get a distinct pair automatically). docs/CONTRACTS.md §3.
