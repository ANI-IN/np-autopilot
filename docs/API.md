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
| `GET /dashboard` | viewer | counts per type, totals, 20 recent changes |
| `GET /search?q=&types=&limit=` | viewer | websearch FTS + trigram; resources by title/URL |
| `GET /changes?since=<audit id>` | viewer | change feed for collaboration (cursor) |
| `GET /nodes?type=&scope=&q=&status=&tag=&owner=&created_by=&sort=updated\|name&cursor=&limit=` | viewer | cursor pages: default 50, max 200 |
| `POST /nodes` | contributor | `{type, name, summary?, body?, status?, scope?: id \| {new:{type,name}}, resources?: [...], edges?: [{type, node_id, direction}], tags?}` — one transaction |
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
| `GET /members` · `POST /members/{user_id}` | admin | `{role}` |
| `GET /people` | viewer | members' `user_id, email, role` (owner names) |
| `GET /instructors?course=&q=` | viewer | |
| `GET /quality` | viewer | totals, completeness, orphans, `unowned`, `links` (checked/ok/needs-sign-in/broken + broken list), duplicates |
| `GET /quality/missing-resources?type=` · `/quality/duplicates?threshold=` · `/quality/link-candidates` | viewer | |
| `POST /quality/link-results` | editor | `{results: [{id, status, http?, redirected_to?}]}` ≤200; stores the last check per resource. The server never fetches a URL itself |

Tests: `tests/test_kb_api.py` (every family: success, 422, 403, 404, 409 conflict,
409 duplicate), `tests/test_kb_concurrency.py`.
