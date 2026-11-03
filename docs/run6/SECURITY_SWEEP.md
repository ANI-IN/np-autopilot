# Run 6 — security sweep (F5) and the admin panel's access rules (F4)

Every check below says what was looked at (file:line, at the commit of this
branch), what was found, and what changed. "Test" names the test that keeps it
true. Nothing here was run against production or any remote; the tests are for
the local database (tests/kb_support.py).

## 1. Who gets in: IK accounts only, checked on every request

| Check | Evidence | Result | Fix |
|---|---|---|---|
| Sign-in is restricted to the Workspace | `web/lib/auth.py:115` `verify_google_token` verifies signature, `iss`, `aud`, `exp`, `email_verified`, then `hd` (`:175`) and the address; `db/migrations/0007`/`0016` hook refuses a non-`hd` identity before the user row exists; `0015` creates a profile only for the IK domain | Sound, but it is a SIGN-IN gate only. A data request carried a Supabase token, and `verify_supabase_token` (`auth.py:245`) never looked at the address: a valid session for any other address (an account whose e-mail was changed after sign-up, a mis-set hook in a new project) reached every route. RLS still returned nothing without a profile, but the routes answered 200. | **Fixed.** `auth.py:47` `DomainRefused`, `:59` `require_allowed_domain`: exactly one `@`, the domain exactly `ALLOWED_HD`. `web/lib/guard.py:63` `identify()` applies it on EVERY request, so every route behind it is covered: the KB API, the map's routes (which read the KB), `/api/kb/changes`. `api/index.py:110` `_refused` answers 403 (valid session, wrong domain) or 401 (no valid session). |
| `NP_ALLOWED_HD` | `auth.py:37`, `api/config.py` | Deployment-only, never per request. The DB side uses the literal (0015, 0035), the same value. | None. |
| The KB API token path (`ikkb_…`, MCP) | `api/index.py:310` `_identify_kb_token` → `kb.resolve_token` (`0023:156`, granted `0025:8`) | The token carries no address; it acts as its owner under RLS. A membership row granted its role to ANY uuid (`kb.role()`, `0023:19`), profile or not. | **Fixed in the database** (0035 §2): `kb.role()` counts a membership only when `np_role() <> 'none'`, i.e. the caller has a profile, and `profiles.domain_is_ik` guarantees the domain. Test: `test_kb_access_sweep.py::test_an_api_token_of_an_account_without_an_ik_profile_reads_nothing`, `::test_a_membership_grants_nothing_without_an_ik_profile`. |
| `NP_SHARED_ACCOUNTS` / shared mailboxes | `auth.py:82` (flag in the audit line), `0014` (`profiles.is_shared_account`), `0008` (`shared_accounts_stay_member`), `pipeline/kb_admins.py:53` (refuses KB admin to a shared account) | `set_role` and the new invitations do not refuse a KB role to a shared mailbox. Not changed: the project's own operator account is the listed shared mailbox (0014), and refusing it a KB role could lock the operator out. | **Owner decision needed**: whether a shared mailbox may hold a KB editor/admin role. If not, a `before insert or update` trigger on `kb.memberships` reading `profiles.is_shared_account` closes it for every path. |
| `/api/stats` stays public | `api/index.py:412`, `kb.landing_stats()` (`0033:31`) | **Decision: stays public.** The landing page shows these numbers before sign-in, exactly as the static `public/stats.json` it replaced always did. It returns aggregate counts only (records, relationships, links, files, counts per type key, the last sync date, the change-feed head), through a definer function that reads no row content, and no identity is attached. The type keys are the workspace's vocabulary, not data. | Test: `test_kb_access_sweep.py::test_the_public_and_secret_routes` asserts the exact key set and that every value is a count. |
| `/api/config` stays public | `api/config.py` | The Supabase URL, the anon key (grants nothing: default-deny RLS), the Google client id, the allowed domain. | Test asserts no other key. |

## 2. The route matrix

`tests/test_kb_access_sweep.py` derives the routes, so a new one is covered or
fails the test: `api/index.py` READS/WRITES plus every `path == "/api/…"` case
in `app()`; `api/kb_routes.py`: every path word its dispatcher compares
(`head`, `rest`, `sub`, `action`, the type-ops tables), each of which must be
called by an entry in `KB_ROUTES` (about 150 method/path pairs). Every route is
called as anonymous, a genuine session outside the domain (which even holds a
misconfigured admin membership), viewer, contributor, editor and admin:

- anonymous → 401; outside the domain → 403, on every identified route;
- a role below the route's minimum → 403 (404 only for a route about a random
  id that is looked up first: never 2xx);
- at or above the minimum → never 401/403, never 5xx;
- `/api/cron/kb-sync` → 401 for every user token, an admin's included; its
  secret still opens it; `/api/session` → 400 for an empty body for everyone.

The minimum roles in the table are the `require()` calls of the service
(every service function that has one checks it first; verified with an AST
scan while writing the table) and the RLS of 0023.

## 3. Database functions

| Check | Evidence | Result |
|---|---|---|
| `authenticated` / `anon` cannot execute owner-only SECURITY DEFINER functions | listed live from `pg_proc` (schemas kb and public, `prosecdef`, not triggers, not extension members) in `test_kb_access_sweep.py::_definer_functions` | Allowed for `authenticated`, each with its reason: `np_role`, `kb.role`, `kb.resolve_token`, `kb.people`, `kb.my_scope_ids`, `kb.record_history`, `kb.actor_emails`, `kb.landing_stats`, `kb.link_me`, `kb.person_candidates_for_me`, `kb.claim_person`, `kb.apply_claim` (each checks the role itself). Owner-only and asserted NOT executable: `kb.apply_person_owner`, `kb.person_name_of`, `kb.auto_link_person`, `kb.sync_schedule_install/remove`, `auth_before_user_created`. Any new definer function fails the test until it is classified. |
| Pinned `search_path` on every definer function | 0022–0035 | Sound (also B5's audit). The new 0035 functions pin it. |

## 4. Headers, CORS, rate limits

| Check | Evidence | Result | Fix |
|---|---|---|---|
| Page headers | `vercel.json` `headers` (`/(.*)`): HSTS 2 years + preload, `nosniff`, `x-frame-options: DENY`, `referrer-policy: no-referrer`, CSP with `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'none'`, `object-src 'none'`, hashes for the two inline scripts | Sound. `style-src 'unsafe-inline'` remains (Google Identity Services and the element styles need it; no `innerHTML` takes data: B5). `connect-src` gets the Realtime origin only through `scripts/kb_csp_origin.py`. | None. |
| API response headers | `api/index.py` (was: content-type, nosniff, referrer-policy only) | The API relied on vercel.json for HSTS, framing and CSP; a local server or a preview with a different header rule served JSON without them. | **Fixed.** `api/index.py:100` `SECURITY_HEADERS` on every response, the 304 included: CSP `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, `x-frame-options: DENY`, HSTS, nosniff, no-referrer. The sweep asserts them on every response. |
| CORS | `grep -ri access-control api web` | No CORS header anywhere: the browser's same-origin rule refuses every cross-origin read, and no route answers a preflight. | Kept that way on purpose (`api/index.py:98`); the sweep fails if any response grows an `access-control-*` header. |
| Rate limits on writes | `api/index.py` | **Decision: no in-process limiter.** On Vercel every request may land on a fresh or a different instance, so a per-process counter limits nothing an attacker cannot bypass by concurrency, and it would throttle a real editor's bulk work on a warm instance. What bounds writes today: every write needs a verified IK session or a revocable token, is attributed and audited; bodies are capped (`MAX_BODY` 16 KB curation, `KB_MAX_BODY` 512 KB, negative lengths refused at `:355`); bulk endpoints cap their batch (500 records per bulk edit, 200 link results, 5000 graph positions); the database pooler caps connections; GoTrue rate-limits sign-ins and token refreshes; Vercel's platform absorbs volumetric abuse. If a limit is ever needed it belongs at the edge (a Vercel Firewall rate-limit rule on `/api/kb/*` POST/PATCH/DELETE), not in the function. | Documented here. |

## 5. Secrets and tokens

| Check | Evidence | Result | Fix |
|---|---|---|---|
| Cron/sync secret | `web/lib/kb/sync_api.py:29` | `hmac.compare_digest`, minimum 24 characters, no secret → nothing opens, no header → refused. Sound. | Test: `test_the_cron_secret_is_compared_in_constant_time_and_has_a_minimum_length`. |
| MCP tokens hashed | `service.py:1515` (SHA-256), `0022` (`token_hash` only), `0032:125` (the audit drops `token_hash`) | Sound. | Test asserts the hash, and that neither the token nor its hash reaches the audit log. |
| MCP tokens scoped | `index.py:310` (KB routes only; the map's routes never accept them), `actor_type 'ai'`; `0034` `refuse_ai_admin` (roles, sign-in links, deletes); `service.py:1523` (no minting) | `add_edge_rule` did not refuse the AI (B5 audit A1b). | **Fixed** `service.py:208`. Invitations: refused in the service and by `refuse_ai` on `kb.member_invites` (0035). |
| MCP tokens expire and are revocable | `service.py:1525`, `kb.resolve_token` checks `revoked_at`/`expires_at` | `{"expires_in_days": null}` made a token that never expired (B5 audit A10, left open). | **Fixed** `service.py:1525`: 1–365 days, always. Test: `test_mcp_tokens_are_hashed_scoped_expiring_and_revocable`. |
| Secrets never reach the browser | `tests/test_login_flow.py::test_nothing_the_browser_can_fetch_mentions_a_secret` (service role, JWT secret, JWT literal), `db/window/check_function_map.py`, `tests/test_deploy_guard.py` | The browser check did not cover the cron secret, the database DSN variables, the Drive key or a Google client secret; no response body was ever checked for secret VALUES. | **Extended**: `test_nothing_the_browser_can_fetch_names_a_server_secret` (those names, `postgres://`), and the sweep asserts that no API response body, in any role, contains the cron secret, the JWT secret or either DSN. A 500 never returns exception text (`index.py`, unchanged). |

## 6. Admin panel (F4)

| Check | Evidence | Result |
|---|---|---|
| Add by IK e-mail before the first sign-in | `service.py:1611` `invite_member`, `:1597` `_ik_email` (server side: exactly one `@`, domain exactly `ALLOWED_HD`); `0035` `email_is_ik` CHECK (database side) | New. Settings → Members (`public/kb/js/views/settings.js` `membersTab`). |
| Applied on the first sign-in | `0035` `kb.apply_member_invite` on `public.profiles` insert/e-mail change: the same place 0030/0033 link person records on sign-in. Never fails a sign-up (a problem is a warning). An account that has already signed in gets the role at once (`kb.member_invites_resolve`). | New. Test: `tests/test_kb_members_run6.py`. |
| How `kb.memberships` and profiles / `np_role` relate | `profiles.role` (member/recruiting/admin) is the MAP's role; `kb.memberships.role` is the KB role; `kb.role()` = the membership, else viewer for anyone with a profile, else none (now: none without a profile, whatever the membership) | Documented in 0035's header. |
| Change role, remove, withdraw | `set_role`, `workspace.remove_member`, `set_invite_role`, `revoke_invite` | Audited (memberships and member_invites are audited tables; Activity labels them "Role: …"). |
| The last admin | `0034` `kb.keep_an_admin` (update/delete), `workspace.remove_member`, and 0035's invitation trigger (an invitation to the last admin's own address cannot demote them) | The tab disables demoting/removing the last admin and says why; the server's own sentence is shown if anyone tries anyway. |
| No address in the append-only log | `0035` `kb.audit()` drops `email` for `member_invites` (as it drops `token_hash` for `api_tokens`) | Test asserts no `@` in any invitation or membership audit row. |
| Role descriptions | `service.py:1557` `ROLE_HELP`, served with `GET /api/kb/members`, shown in the tab | Written from what the service and RLS enforce. |

## 7. One service layer (F4)

The sync from the original site's tables (`web/lib/kb/sync.py`) had its own
copies of the record rules. It now calls the API's:

| Rule | Shared function | Sync call site | API call site |
|---|---|---|---|
| Record name (empty, over 300, an e-mail or URL) | `validate.py:46` `name_problem` | `sync.py:183` | `validate.name()` → every create/rename |
| Typed field values | `service.py:245` `field_errors` (→ `kb.field_value_error`, the trigger's own function, one query for many records) | `sync.py:400` `field_problems` (the bad value is left out and reported as `field_value_rejected`; the record is kept) | `service.validate_props` |
| Relationship type rules | `service.py:226` `edge_rules`, `:237` `edge_rule_problem` (the trigger's sentence) | `sync.py:510`, `:791` | `service.create_edge` (before the insert; the trigger stays the backstop) |

On valid data nothing changes: the same records, the same props, the same
relationships (the rule set is the one `typedefs.all_types` gave the sync).
On invalid data the sync used to fail its whole batch inside the trigger (a
bad field value) or carried its own wording; now it refuses with the API's
sentence. Test: `tests/test_kb_one_validation.py`.

## Not done here

- Shared mailboxes and KB roles: owner decision (section 1).
- B5 audit items in other streams' code that are not security findings
  (A5, A6, A8, A12) are untouched.
