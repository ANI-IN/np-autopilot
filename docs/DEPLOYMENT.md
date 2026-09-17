# DEPLOYMENT — one Vercel project, and what holding the keys means

One project, per [ONE-APP-OR-TWO.md](ONE-APP-OR-TWO.md). The explorer and the
API are the same deployment and call the same handlers, so the role boundary is
single-sourced rather than coordinated.

---

## The shared account, and the key it can read

**The Vercel project sits under `b2c-courses-new-programs@interviewkickstart.com`,
a shared team account.** Recorded here rather than fixed, deliberately.

Whoever can sign into that account can read every environment variable in the
project, including **`SUPABASE_SERVICE_ROLE_KEY`** if it is set there — and that
key **bypasses RLS entirely**. `AUTH.md` names it as layer 1's only leak path:

> *"The database refuses unauthorised rows regardless of how the query arrived —
> leaks only via the service-role key, which is why nothing in the web app has
> it."*

Nothing in `api/` or `web/lib/` reads it (`tests/test_login_flow.py::test_no_api_route_connects_
as_owner_or_service_role` asserts that, matching the environment READ rather than
the string, so the check survives someone deleting the comment). But the Supabase
integration sets the variable in a linked Vercel project by default, and a
variable nothing reads is still a variable anyone with the account can copy.

**And it is the same attribution gap the shared-account CHECK addresses for
identity.** Migration 0008 stops a listed shared account holding `recruiting` or
`admin`, because an audit log that names an account cannot answer *"who looked up
this candidate?"*. The Vercel audit log has exactly that property: it shows which
**account** changed an environment variable or promoted a deployment, not which
**person** did. A shared account is several people.

**This is not closed by better logging.** It is a property of the identity, the
same one AUTH.md states for shared sign-ins. The honest mitigations are
organisational, not technical:

- Do not set `SUPABASE_SERVICE_ROLE_KEY` in the Vercel project at all. Nothing
  deployed needs it; the pipeline reads it from a local environment, and the web
  app connects as `authenticated`.
- If the Supabase integration adds it, remove it and confirm the app still works
  — it will, and that is the proof it was never needed.
- Rotating the key is the only response to a departure, because you cannot tell
  from the audit log whether a given person ever read it.

---

## Environment variables

**Server-side only.** These are read by functions under `api/` and never
reach the browser:

| Variable | What it is |
|---|---|
| `SUPABASE_DB_URL_TRANSACTION` | Transaction pooler, **port 6543**. Every web request. |
| `SUPABASE_JWT_SECRET` | Verifies Supabase access tokens on legacy (HS256) projects. Not needed if the project publishes JWKS. |
| `GOOGLE_OAUTH_CLIENT_ID` | The `aud` a Google ID token must carry. |
| `NP_ALLOWED_HD` | `interviewkickstart.com`. Deployment-level, never per request. |
| `NP_SHARED_ACCOUNTS` | Comma-separated local-parts flagged in the audit log. |

**Public by design** — served by `/api/config` so a preview deployment works
without an edit, and a rotation needs no rebuild:

| Variable | Why it is safe in a browser |
|---|---|
| `SUPABASE_URL` | Appears in every request the browser makes anyway. |
| `SUPABASE_ANON_KEY` | Grants nothing alone: every table is default-deny and `np_role()` returns `'none'` without a profile. |
| `GOOGLE_OAUTH_CLIENT_ID` | Published in the OAuth redirect regardless. |

**Never set in Vercel:** `SUPABASE_SERVICE_ROLE_KEY`, and
`SUPABASE_DB_URL_SESSION` (the session pooler connects as the owner — that is
for migrations, run from a laptop, not from a request).

**Never, under any circumstances, the direct connection.** `db.<ref>.supabase.co`
is IPv6-only on this project: it works on a laptop and fails on Vercel, which is
the worst possible failure distribution. `pipeline/lib/db.py::assert_not_direct`
refuses it at runtime and CI greps for it.

---

## Configuring Supabase Auth — the step that cannot be done from this repo

Migration 0007 installed `auth_before_user_created` and **nothing has ever
called it**. GoTrue invokes it, and GoTrue is configured in the dashboard, not
in SQL. Until these three are done, the hook is inert:

1. **Authentication → Providers → Google.** Enable it. Client ID and secret from
   the same Google Cloud OAuth client as `GOOGLE_OAUTH_CLIENT_ID`.
2. **Authentication → Hooks → Before User Created.** Point it at
   `pg-functions://postgres/public/auth_before_user_created`. Migration 0007
   already granted `execute` to `supabase_auth_admin` and revoked it from
   `authenticated` and `anon`.
3. **Authentication → URL Configuration.** Add the deployment origin.

**In Google Cloud Console**, the OAuth client needs the deployment origin as an
authorised JavaScript origin. Google Identity Services runs in the browser and
the origin is checked by Google, not by us.

**The hook is not what keeps a non-IK account out**, and the order of
verification is what makes that true: `/api/session` verifies the Google token
with `web/lib/auth.py` — `hd` included — **before** GoTrue is contacted. So the
domain rule holds even with the hook unwired, and the hook goes back to being
what AUTH.md calls it: defence in depth.
`tests/test_login_flow.py::test_a_refused_signin_never_reaches_gotrue` asserts
that ordering directly.

---

## Granting access

A session is not access. Signing in successfully with an IK Workspace account
yields `np_role() = 'none'` and zero rows, and `/api/me` says so in words
rather than presenting an empty canvas.

```
python3 pipeline/grant_access.py list                    # who exists, who waits
python3 pipeline/grant_access.py grant name@interviewkickstart.com
python3 pipeline/grant_access.py revoke name@interviewkickstart.com
```

`grant` requires the person to have signed in once — that is what creates the
`auth.users` row and proves the Workspace identity. Revocation takes effect on
their next query, with no re-projection and no deploy; suspending the Workspace
account is what stops new tokens being issued.

---

## Latency — measured, and what is still a projection

Measured 2026-09-17 from a laptop against `ap-northeast-2`, as `authenticated`
with a `member` profile, so every number includes RLS policy evaluation.
`EXPLAIN (ANALYZE)` separates server-side execution from the round trip.

| Endpoint query | Round trip from laptop | Server-side execution |
|---|---|---|
| `search` | 191.3 ms | **4.62 ms** |
| `node` | 149.3 ms | 0.22 ms |
| `provenance` | 150.5 ms | 0.53 ms |
| `neighbourhood` depth 1 | 151.1 ms | 0.67 ms |
| `neighbourhood` depth 2 | 154.4 ms | 0.99 ms |
| `neighbourhood` depth 3 | 181.5 ms | 4.87 ms |

**About 148 ms of every one of those is geography** and nothing in the code
changes it. E3's earlier figure of ~146 ms per statement was the same distance.

**In-region is a PROJECTION, not a measurement, and is labelled as such here
because the deployment has not happened.** With a Vercel function in the same
region as the database the round trip falls to roughly 1–3 ms, so the numbers
above become the server-side column plus that — roughly 2 ms for a node or a
depth-1 neighbourhood, and 5–7 ms for search or a depth-3 expansion. **This must
be re-measured against the real deployment before anyone quotes it.**

### What the measurement found

Search first measured **40.67 ms** of server-side execution while every other
endpoint was under 3 ms. A trigram index was the obvious fix and was wrong — it
changed nothing. The plan showed why:

```
Seq Scan on nodes  (actual time=11.553..40.578 rows=2)
  Filter: (((sensitive AND (np_role() = ANY ('{recruiting,admin}')))
           OR ((NOT sensitive) AND (np_role() <> 'none')))
          AND (label ~~* '%karthika%'))
  Rows Removed by Filter: 3144
```

The RLS predicate runs first and `np_role()` was called **once per row** —
3,146 lookups in `profiles` per search. Migration 0013 wraps every policy's call
as `(select np_role())`, which has identical meaning and becomes an InitPlan
evaluated once per statement.

| | before | after |
|---|---|---|
| search | 40.67 ms | 4.62 ms |
| neighbourhood depth 3 | 22.51 ms | 4.87 ms |
| all six together | 67.24 ms | **11.91 ms** |

The trigram index was reverted rather than left in place looking like a fix.
With the real cost gone the planner still chooses a sequential scan, and at
3,146 rows it is right to.

`tests/test_role_boundary.py::test_every_policy_evaluates_np_role_once_per_query`
locks the form in, because the two spellings mean the same thing: the next
policy will be written the natural way, every access test will pass, and it will
cost a table scan's worth of function calls with nothing to notice.

---

## Deploying

```
vercel login                      # interactive; must be run by a person
vercel link                       # into the shared account's scope
vercel env add ...                # the server-side variables above
vercel --prod
```

`vercel.json` already pins: `public` as the static root, `api/*.py` on
the Python 3.12 runtime with a 15-second cap, and a CSP with **no
`unsafe-inline` on `script-src`** — the page's two inline blocks are pinned by
SHA-256 hash, and `test_csp_pins_the_inline_scripts_by_hash` recomputes them, so
editing the HTML without updating the header fails in CI instead of shipping an
explorer whose scripts the browser silently refuses to run.

---

## After deploying, check these four

1. `/api/config` returns three non-empty values and no `error`.
2. A sign-in with an IK Workspace account reaches the graph.
3. A sign-in with a personal Google account **carrying an IK address** is
   refused, and the message names the `hd` claim. This is the case
   `email.endsWith()` accepts.
4. Re-measure the table above in-region and replace the projection.
