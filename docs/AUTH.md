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

### Layer 0 — the Internal consent screen, in front of all of it

The Google Cloud OAuth consent screen is set to **Internal**, so Google itself
refuses any account outside `interviewkickstart.com` **before a token is ever
issued** — nothing reaches `web/lib/auth.py` to be checked. It is the earliest
and cheapest refusal in the system.

**It is not a replacement for the `hd` check, and must not be described as one.**
Two reasons, and the second is the one that matters:

1. It is a setting in a console, changeable by anyone with project access,
   with no signal in this repository when it changes. The `hd` check is code
   with tests.
2. **Internal bounds WHICH accounts can obtain a token. It does not verify what
   the token then claims.** `hd` still catches a Workspace account whose `email`
   claim disagrees with its hosted domain — that is
   `test_hd_ours_but_email_elsewhere`, and no consent-screen setting addresses
   it.

Read it as narrowing the population that can reach layer 2, not as doing layer
2's job.

**Recorded: the OAuth client secret was rotated on 17 September 2026** after
being exposed in a screenshot. **The Internal audience is what bounded the
impact** — a leaked client secret is exploitable by anyone who can complete the
consent flow, and Internal means that set is IK Workspace accounts rather than
the internet.

Same instinct as R18, and the same reason for writing it down: the exposure is
much smaller, and the record is the point. An exposure that was bounded by a
setting is only bounded for as long as the setting holds, and a rotation nobody
recorded is a rotation nobody can date if the question comes up later.

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

**ENFORCED, as of migration 0008 — and that enforcement was inert until 0014.**

The CHECK below is keyed on `is_shared_account`, a column the APPLICATION
supplied. `grant_access.py` computed it from `NP_SHARED_ACCOUNTS`, which was set
in Vercel and never in the laptop environment the script runs in. An empty list
means no account is shared, so the script refused nothing and wrote `false` —
and the constraint then held perfectly over a value that was already wrong.

Found by running the guard against the real shared mailbox after it signed in:
`grant --role recruiting` **succeeded**. Both layers were inert at once, for the
same reason.

**A CHECK constraint keyed on a value the caller controls is not a constraint.**
It is the caller's opinion, stored, with a constraint's reputation. And the
trigger for it is A.7b in a security control: an unset variable made *"no shared
accounts exist"* indistinguishable from *"I was never told which accounts are
shared"*, and the permissive reading won.

**Migration 0014 moves the list into the database** (`shared_accounts`) and
DERIVES the flag with a `before insert or update` trigger, overwriting whatever
the caller passes. The list is no longer something an environment can fail to
carry, and the constraint now depends on a value the database computes:

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

**One residual env-var dependency, stated rather than left implicit.**
`Identity.is_shared_account` in `web/lib/auth.py` still reads
`NP_SHARED_ACCOUNTS` to flag the audit line. That variable IS set in Vercel, and
the flag there is informational — the control is the database-derived column,
which no missing variable can disable. If the audit flag ever becomes
load-bearing it should read `profiles.is_shared_account` instead.

**Its limit, and it must not be over-claimed: this defends against the
CONFIGURED list only.** Shared-account *detection* does not exist — Google does
not tell us which mailboxes are shared — so an unlisted shared account is
indistinguishable from a personal one and passes the check. Keeping
`NP_SHARED_ACCOUNTS` current is an operational task, not something the database
can do for you.

---

## Granting and revoking access

**Grant:** `member` is now granted **automatically** at signup, by migration
0015. `recruiting` and `admin` are granted by inserting or updating a row in
`profiles`, via `pipeline/grant_access.py`, by an administrator.

**Revoke:** delete the profile row. Effective on the next query, with no
re-projection and no deploy, which E1 proves in both directions.

**Revoke at source:** suspending the Google Workspace account stops new tokens.
An already-issued ID token stays valid until it expires (typically one hour), so
profile deletion is the immediate control and Workspace suspension is the
durable one. Do both.

### REVERSAL — 2026-09-18, migration 0015

This document said, and `pipeline/grant_access.py` still says in its own words:

> *"There is no self-service signup path into a role — layer 3 permits an
> account to exist; a profile is what gives it data."*

**The second half of that sentence is no longer true for `member`, and the
first half was never quite the reason it was kept.** Recorded as a reversal,
with the reasoning, because it changes what a profile means.

**What changed.** An `after insert` trigger on `auth.users` writes a `member`
profile for any identity whose email domain is `interviewkickstart.com`. An IK
employee now signs in and reads the graph. Nobody runs a command.

**Why the old behaviour was wrong.** A colleague signed in, reached `/api/me`,
and was told they had no profile and therefore read nothing — until an
administrator noticed. The manual step read as a security control and was not
one: **layer 3 (migration 0007) had already refused every identity that is not
an IK Workspace account, before the user row existed at all.** What the manual
step actually gated was *membership of the company*, which layer 0 and layer 3
decide between them. It added a person to the loop without adding a decision.

**What it never gated, and still does not.** `recruiting` is the role that
reads the hiring funnel — 277 named rejections and 1,625 mid-pipeline
candidates. That was always manual and stays manual. `admin`, which can write
curation, likewise. The trigger writes the literal string `'member'`; there is
no expression in it that could evaluate to anything else and no input that
reaches the statement, so the auto path cannot be widened by data.

**This is not a self-service path.** Nothing the user calls grants anything.
The row appears as a consequence of GoTrue creating an account that layer 3 has
already vetted. There is no parameter, no request, and no role to ask for. The
distinction matters because a self-service path would be one an attacker could
*invoke*; this one can only be *triggered by succeeding at layer 3*.

**Why the schema and not `/api/session`.** Writing a profile from the session
route needs privileges the web app deliberately does not have. This document
names the service-role key as layer 1's only leak path, and the reason nothing
in the web app holds it. Granting the web app write access to `profiles` to
save an administrator a command would undo precisely that, in exchange for a
convenience. The database provisions its own row instead — the same argument as
migration 0014, where the database derives the value its own constraint depends
on rather than trusting a caller.

**What still holds, unchanged.**

- Layer 3 still refuses a non-Workspace identity at signup. The trigger checks
  the domain again anyway and skips rather than raising, because raising would
  abort GoTrue's signup transaction and turn a correctly-refused account into a
  500 — the wrong failure for the right reason.
- `profiles.domain_is_ik` still refuses a non-IK row outright.
- 0014 still derives `is_shared_account`, and 0008's
  `shared_accounts_stay_member` still caps a shared mailbox at `member` — which
  is what this grants, so the two agree by construction rather than by luck.
- **Revocation is unchanged and still immediate.** Deleting the profile is still
  the control. Note the asymmetry this introduces: a deleted profile is
  re-created only if the user is created again, which does not happen on a
  re-login — `auth.users` already holds the row. Deletion therefore still
  revokes durably. **If that ever stops being true, this reversal must be
  revisited**, because a grant that reinstates itself is not revocable.
- Rolling back 0015 stops future grants and **revokes nothing**, deliberately.

**Tested, not asserted.** `tests/test_auto_member_grant.py` covers the three
things the auto path must be incapable of — granting anything but `member`,
granting anything to a non-IK identity, and demoting an existing profile.
Verified by mutation: `on conflict do update` reddens exactly the demotion test,
and removing the domain guard reddens exactly the non-IK test. `on conflict do
nothing` and `do update` are one word apart, and "a new user gets member" passes
either way.

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

## The login flow (G1), and the seam it exposed

**Two tokens, with different jobs.** This was not a design preference; it was
forced by a defect that only appeared when the layers were joined:

`profiles.user_id` is `uuid`, `np_role()` resolves through `auth.uid()`, and
`auth.uid()` casts `request.jwt.claims ->> 'sub'` to `uuid`. A **Google subject
is a decimal string** — `117609876543210987654`. Setting it as `sub` does not
deny; it **raises**, inside every policy:

```
invalid input syntax for type uuid: "117609876543210987654"
```

So every authenticated request would have returned **500**. Each of the four
layers was tested and green. Nothing had ever exercised the join between layer 2
and layer 1.

| Token | Proves | Verified by | Presented |
|---|---|---|---|
| **Google ID token** | Workspace membership, via `hd` | `verify_google_token` | Once, at `/api/session` |
| **Supabase access token** | An established session, with a **uuid** `sub` | `verify_supabase_token` | Every data request |

Both verifications live in `web/lib/auth.py`. There is exactly one place that
turns a string into an identity, and `guard.py` only chooses which is
appropriate where. A Google token on a data route is refused with a message
naming `/api/session`, rather than 500ing inside a policy.

**Order: we verify before GoTrue is contacted.** The migration-0007 hook
enforces the same `hd` rule, so the reverse order would also refuse — but only
if the hook is configured in the dashboard, which no test in this repo can
assert. Verifying first means the refusal holds with the hook unwired, and the
hook is then genuinely what this document calls it: defence in depth.
`test_a_refused_signin_never_reaches_gotrue` measures that directly.

**`user_metadata` is never trusted.** GoTrue copies the provider's claims there
at signup, and `user_metadata` is writable by the user through the auth API — so
an `hd` read from a Supabase token is an attacker-controlled string.
`verify_supabase_token` therefore returns **no hosted domain at all** rather than
one that could have been set. The domain guarantee comes from the two places
that are not user-writable: the 0007 hook, and `profiles.email_domain` with its
CHECK constraint, written only from a Google token this code verified.

**Session lifetime.** Refresh happens *before* expiry rather than in reaction to
a 401, so a long look at one graph does not end in a bounce to the login screen.
Sign-out calls GoTrue's `logout?scope=global`, which **revokes** refresh tokens
server-side — clearing browser storage, which is what "log out" usually means in
a single-page app, would leave a copied refresh token working. The current access
token stays valid until it expires; that is a property of stateless JWTs and is
stated rather than papered over.

**The `hd` GoTrue stores is under `custom_claims`, and it is corroboration —
not the proof.** The proof that an account passed the domain rule is that it
exists: `/api/session` verified the claim before GoTrue was contacted, and the
0007 hook refuses to create a user without it. `grant_access.py` reads
`identity_data -> 'custom_claims' ->> 'hd'` as a second opinion, and reports a
missing value as a storage-shape question rather than as a failed identity —
because a guard that refuses on absent corroboration refuses everyone.

**A session is not access.** An IK Workspace member who signs in successfully
gets `np_role() = 'none'` and reads nothing. `/api/me` says so in words, because
"signed in and permitted nothing" is otherwise indistinguishable from "the
explorer is broken". Provisioning stays a deliberate act:
`pipeline/grant_access.py`, run by an operator against the session pooler —
`profiles` has no INSERT policy, so it cannot be done over the web app at all.

---

## What is NOT built

- **`recruiting` data.** Zero sensitive rows are projected (D3 scope), and the
  real projection stays out until R18 is resolved.
- **A table for READ audit.** Reads go to stdout, which Vercel captures. Writes
  are a real table (`curation_audit`). There is still no retention policy.
- **The GoTrue dashboard configuration.** The Google provider and the
  before-user-created hook are dashboard settings, not SQL, and migration 0007's
  hook **has still never been invoked**. `docs/DEPLOYMENT.md` lists the three
  steps. The domain rule does not depend on them.
- **Any deployment.** Nothing is live; `vercel login` is interactive.
