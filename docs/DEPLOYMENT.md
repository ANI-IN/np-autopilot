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

Nothing in `api/` or `web/lib/` reads it. `tests/test_login_flow.py::test_no_api_
route_connects_as_owner_or_service_role` asserts that, matching the environment
READ rather than the string, so the check survives someone deleting the comment.

> **Corrected 2026-09-18 — the claim was true; the evidence cited for it was
> not.** Until that date this test scanned `web/` only, while every HTTP route
> lives in `api/` — eleven files it had never opened. So it was passing over the
> directory it was named for. The *claim* survives on independent evidence: a
> scan of the shipped bundle found **zero** service-role occurrences, and the
> variable is not set in the Vercel project at all. What did not survive is the
> test being the reason to believe it. The scan now covers both trees, and
> `DECISIONS.md` §A.7b instance 8 records the pattern — a guard whose scope is
> narrower than the rule it enforces, passing because it is looking in the wrong
> place. **A green test over the wrong directory is not weaker evidence than a
> green test over the right one; it is no evidence at all.** But the Supabase
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
`auth.users` row and proves the Workspace identity.

**Where the `hd` corroboration actually lives.** GoTrue nests non-standard OIDC
claims under `custom_claims`:

```
identity_data -> 'custom_claims' ->> 'hd'   <- where it IS
identity_data ->> 'hd'                      <- where the script first looked
```

The first version read only the second, found NULL, and refused with *"provider
hd=None, not 'interviewkickstart.com'"* — which reads as *this is not a Workspace
identity* when it meant *I looked in the wrong place*. It would have refused
every legitimate account.

**The refusal now distinguishes three states**, because they need different
responses: no Google identity row at all; an identity whose `hd` is in none of
the known locations (a storage-shape change — the account has already passed the
domain rule twice to exist); and an `hd` that is genuinely the wrong domain.
Only the third is an identity problem.

`tests/test_grant_access_reads_real_rows.py` reads the REAL `auth.identities`
rows rather than fixtures. That is the gap that let this through: every existing
auth test built its own tokens and its own rows, so GoTrue's schema was an
assumption shared by the code and its tests — §A.7a's "two checks sharing one
source of truth", where the source is a belief about someone else's schema. Revocation takes effect on
their next query, with no re-projection and no deploy; suspending the Workspace
account is what stops new tokens being issued.

---

## Latency — measured in region, 2026-09-18

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

### In region — no longer a projection

The function ran in `iad1` while the database sat in Seoul, because
`vercel.json` had no `regions` key. It is now pinned to `icn1`. Measured from
`guard.audit()` against the real deployment, warm, first-request cold starts
excluded:

| Endpoint | iad1 | **icn1 (warm)** |
|---|---|---|
| `search` | 1,931.6 ms | **40.1 ms** |
| `node` (= provenance) | 2,362.8 ms | **49.8 ms** |
| `neighbourhood` depth 1 | 2,240.3 ms | **79.9 ms** |
| `me` | 2,274.4 ms | **40.8 ms** |
| all warm requests | 2,252 ms (n=23) | **44.3 ms (n=18)** |

**The projection this replaces said ~2 ms, and it was wrong about the
mechanism.** It counted the query plus one round trip. A request is about
eleven: `request_connection` opens a fresh connection and issues two setup
statements before the query, and connection setup — TLS, and SCRAM, which is
deliberately CPU-expensive — has a floor that geography never touched. The
projection was right that the region dominated and wrong about what the region
was multiplying.

**These are server-side numbers.** `ms` is recorded before the response is
written, so it excludes the network and the response write. It is not what a
user waits, and **render and layout cost remains unmeasured** — see
`LATENCY-MEASUREMENT.md` §0, which separates measurement from inference
line by line.

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

## Two things that only failed in production

### The connection URL was parsed twice, by two different parsers

```
psycopg.OperationalError: failed to resolve host
  '2026@aws-0-ap-northeast-2.pooler.supabase.com'
```

Every authenticated request 500'd, and only on Vercel. The password contains a
literal `@`, correctly written `%40` in the URL. Local psycopg decodes it once
and connects. The psycopg vendored into the Vercel bundle decodes the netloc and
then re-splits it, so `...%402026@aws-0-...` became `...@2026@aws-0-...`, it took
the **first** `@`, and the host came out as `2026@aws-0-...`.

`pipeline/lib/db.py::params()` now splits the URL **once** and hands psycopg
discrete keywords — host, port, user, password, dbname. There is no string left
for a second parser to disagree about.

**This is the shape §C names about the IPv6-only direct connection, arriving by
a completely different route**, which is the part worth keeping: the lesson was
recorded about one hostname, and the failure mode is broader than that hostname.
`tests/test_db_connection_params.py` covers it, including the real configured
URL as a positive control.

### The CSP blocked Google's own assets

The page rendered correctly and the sign-in button simply did not appear:

```
Loading the stylesheet 'https://accounts.google.com/gsi/style' violates the
following Content Security Policy directive: style-src 'self' 'unsafe-inline'
```

**A CSP that blocks a dependency fails by producing a page that looks correct.**
Nothing throws; the browser omits what it was told not to load. Same shape as
A.7b, in a header.

Google Identity Services needs four directives, and they are **specific paths**
rather than the bare origin, since `accounts.google.com` also serves the whole
Google account UI:

| Directive | Source |
|---|---|
| `script-src` | `https://accounts.google.com/gsi/client` |
| `style-src` | `https://accounts.google.com/gsi/style` |
| `connect-src` | `https://accounts.google.com/gsi/` |
| `frame-src` | `https://accounts.google.com/gsi/` |
| `img-src` | `https://lh3.googleusercontent.com` (the account avatar) |

**And `Cross-Origin-Opener-Policy: same-origin-allow-popups`.** GSI's popup flow
calls `window.postMessage` on its opener; the default `same-origin` severs that
reference, so the popup completes the sign-in and the result never arrives.

Three tests cover this now, each with a negative control:
`test_csp_permits_everything_google_sign_in_actually_loads` against the list
above, `test_every_external_url_in_the_page_is_permitted_by_the_csp` derived
from the HTML so a new dependency cannot be added silently, and
`test_coop_allows_the_google_popup_to_talk_back`.

---

## After deploying, check these four

1. `/api/config` returns three non-empty values and no `error`.
2. A sign-in with an IK Workspace account reaches the graph.
3. A sign-in with a personal Google account **carrying an IK address** is
   refused, and the message names the `hd` claim. This is the case
   `email.endsWith()` accepts.
4. ~~Re-measure the table above in-region and replace the projection.~~
   **Done 2026-09-18** — see the latency section above and
   `LATENCY-MEASUREMENT.md`. Render cost is still unmeasured.
