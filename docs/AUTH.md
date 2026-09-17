# AUTH — identity, the domain rule, and what the audit log can actually tell you

Four layers, built in the order that fails safe. DECISIONS §D argued them; this
records what was built, what each one does NOT do, and the one question about
shared accounts that has no technical answer.

---

## The four layers

| # | Layer | Where | What it does | Where it leaks |
|---|---|---|---|---|
| 1 | **RLS** | `db/migrations/0005`, `0006` | The database refuses unauthorised rows regardless of how the query arrived | Only via the service-role key — which is why nothing in the web app has it |
| 2 | **Token verification** | `web/lib/auth.py` | Signature against Google's JWKS, `aud`, `iss`, `exp`, `email_verified`, and the **`hd` claim** | A stolen valid token, until it expires |
| 3 | **Signup hook** | `db/migrations/0007` | A non-IK identity never becomes a row | Signup path only; cannot retro-reject an existing account |
| 4 | **Route guard** | `web/lib/guard.py` | A clear 401 and the audit record | A matcher that silently stops matching — which is why it is last |

**Built in that order deliberately.** Layer 1 went in before anything could
reach the database over HTTP, so there was never a window where the application
was the only thing protecting the data.

---

## Why `email.endsWith()` is not sufficient

Stated in DECISIONS §D and now enforced in code with a test per case.

A Google account can carry an `@interviewkickstart.com` address **without
belonging to the Workspace**. The `hd` (hosted domain) claim is what
distinguishes a real Workspace identity from a consumer account that happens to
use the address — and it is only meaningful on a token whose **signature and
audience were verified server-side**.

`tests/test_auth_google.py::test_ik_email_with_no_hd_is_rejected` is that exact
token: a correctly signed token with an IK email and no `hd`. `endsWith` accepts
it. We reject it.

Every rejection has its own test, all offline against a locally generated key —
an auth test that needs the internet is an auth test that gets skipped in CI:

signature not from Google · wrong `aud` · wrong `iss` · expired ·
`email_verified` false · `hd` absent · `hd` wrong · `hd` ours but email
elsewhere · unknown `kid` · `alg: none` · missing required claim · garbage

**Magic links are weaker and are not used.** A magic link proves control of a
mailbox at a moment in time; it does not prove current membership of the
organisation, so an ex-employee with a forwarding alias stays authenticated.
Workspace revocation is immediate.

---

## The role boundary

Two roles. DECISIONS §D calls the lower one `viewer`; the E3 brief calls it
`member`. **Same role — `member` is the name in the code**, and `viewer` should
be read as an alias for it.

| Role | Sees |
|---|---|
| `member` | The public graph — 3,146 nodes, 4,021 traversable edges |
| `recruiting` | Additionally the hiring funnel, ratings and decline rates |
| `admin` | As `recruiting`; reserved for curation writes, which do not exist yet |
| *(no profile)* | **Nothing.** `np_role()` returns `'none'` and every policy fails closed |

**Proved against synthetic rows before real ones exist** (E1). Once the 277 real
rejections land, testing a deny policy would mean risking exposure of the rows
the policy exists to hide. `tests/test_role_boundary.py` inserts three
unmistakably fabricated `ZZ-SYNTHETIC` records, proves `member` sees zero and
`recruiting` sees exactly them, proves a role change takes effect **without a
re-projection**, and asserts the fabricated set is gone afterwards.

**Grants, not just policies.** Supabase's bootstrap grants ALL on `public` to
`anon` and `authenticated`. Until migration 0006, a member's `UPDATE` returned
*"NO ERROR, rowcount 0"* — RLS held, but silently, and one permissive policy
away from real. `anon` now holds nothing and `authenticated` holds `SELECT`
only, so a write raises rather than quietly affecting no rows.

---

## Shared accounts — the honest answer

**The question.** The Drive folder is owned by
`b2c-courses-new-programs@interviewkickstart.com`, a shared team account. If
people sign in as it, several humans resolve to one identity.

**Are shared accounts permitted?** Technically, yes — nothing prevents it, and
a Workspace shared mailbox produces a valid token with the right `hd`. It would
pass all four layers.

**What that costs, stated plainly:**

> **When someone signs in as a shared account, the audit log identifies an
> ACCOUNT, not a person.** The §E.4 question — *"who looked up this named
> candidate?"* — cannot be answered for that session. It can only answer *"which
> account did"*, and a shared account is several people.

This is not a gap to be closed later by better logging. It is a property of the
identity: the token carries one `sub`, and no amount of instrumentation
downstream recovers which human was at the keyboard.

**What is implemented:** `NP_SHARED_ACCOUNTS` lists known shared local-parts.
Identities matching it are flagged `shared_account: true` on every audit line,
so a reader can tell which records are attributable to a person and which are
not. It is a **configured list**, not detection — Google does not tell us, and
an unlisted shared mailbox is indistinguishable from a personal one.

**ENFORCED, as of migration 0008.** A listed shared account cannot hold
`recruiting` or `admin`:

```sql
alter table profiles add constraint shared_accounts_stay_member
    check (not (is_shared_account and role in ('recruiting', 'admin')));
```

A constraint someone has to consciously drop is a better record than a rule
someone has to remember. `member` reads a graph with no personal hiring data,
where "which account" is adequate; `recruiting` reads named hiring outcomes about
external people, which is exactly where an unattributable access log stops being
acceptable. The curation service refuses a shared actor as well, so the rule
holds at both layers.

**Its limit, and it must not be over-claimed: this defends against the
CONFIGURED list only.** Shared-account *detection* does not exist — Google does
not tell us which mailboxes are shared — so an unlisted shared account is
indistinguishable from a personal one and passes the check. Keeping
`NP_SHARED_ACCOUNTS` current is an operational task, not something the database
can do for you.

---

## Granting and revoking access

**Grant:** insert a row in `profiles` with the verified `email_domain` and a
role. There is no self-service signup path into a role — layer 3 permits an
account to exist; a profile is what gives it data.

**Revoke:** delete the profile row. Effective on the next query, with no
re-projection and no deploy, which E1 proves in both directions.

**Revoke at source:** suspending the Google Workspace account stops new tokens.
An already-issued ID token stays valid until it expires (typically one hour), so
profile deletion is the immediate control and Workspace suspension is the
durable one. Do both.

---

## Audit

Every request writes one JSON line: timestamp, subject, email,
`shared_account`, endpoint, **the parameters**, row count, duration.

The parameters matter. §E.4: *"log the query, not just the fact of access"* —
"who looked up this named candidate" is the question you will actually be asked,
and an access log that records only endpoint names cannot answer it.

**Not yet built, and named so it is not mistaken for done:**

- **READS** go to stdout, which Vercel captures. Not yet a table.
- **WRITES are now a real table** — `curation_audit`, with RLS and *no policy*,
  so it is unreachable by `authenticated` entirely. Every curation write records
  actor, before-value, after-value and a mandatory reason. Writes were the point
  at which stdout stopped being adequate: a lost read log is a missing answer, a
  lost write log is an unattributable change.
- There is still no retention policy.

---

## What is NOT built

- **No web login flow.** The app takes a Bearer token; obtaining one is
  Google's standard flow and is not wired up. Every verification path behind it
  is built and tested.
- **No Supabase Auth session exchange.** Layer 3's hook is installed and
  exercised directly; GoTrue is not yet configured to call it.
- **No `recruiting` data.** Zero sensitive rows are projected (D3 scope), and
  the real projection stays out until R18 is resolved.
- **No curation writes.** `people`, `domain_aliases` and `workflow_owners` have
  no policy at all, so `authenticated` reaches none of them.
