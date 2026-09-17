# One app or two? — the explorer and the plugin backend

**G3.** Two clients now want the same graph: the browser explorer (E3) and the
Claude Code plugin (§E). The question is whether they are one Vercel project
with two route namespaces, or two Vercel projects.

**Recommendation: ONE app, split at the route level, with a named trigger for
when to split it for real.** The argument below is the reasoning, including the
three arguments for two apps that are genuinely good.

---

## What the two clients actually differ in

| | Explorer (browser) | Plugin (Claude Code) |
|---|---|---|
| Who is at the keyboard | A person, interactively | A person, via an agent |
| Auth artefact | Google session, browser-held | A bearer token, machine-held |
| Traffic shape | Bursty, small, human-paced | Bursty, possibly parallel, agent-paced |
| Failure tolerance | Sees an error page | Must not get a *wrong* answer |
| Data reachable | Exactly what `np_role()` permits | **Exactly the same** |

**The last row is the whole argument.** These are two presentations of one
authorisation model. They are not two systems.

---

## Why one app

### 1. Splitting the process does not create a security boundary

This is the point most likely to be got wrong, because two apps *feel* safer.

Both apps would hold the same Supabase anon key, forward the same user JWT, and
reach the same database through the same RLS policies. The boundary that decides
whether recruiting data leaks is `np_role()` and the policies in migrations
0005–0008 — it lives in the database, and it is identical from both processes.
Two Vercel projects are two copies of one trust level, not two levels.

§A.7a already names this failure: *two guards that read the same source of truth
are one guard wearing two hats*. A second Vercel project is a second hat.

### 2. Two copies of the role boundary can drift; one cannot

The role check is `web/lib/guard.py`, and what a `member` may see is decided
there and in the RLS policies together. Split into two deployments and there are
two copies of the client-side half — shared by a library today, deployed
separately tomorrow, and divergent the first time someone patches an endpoint in
one project during an incident.

The consequence of that drift is not an outage. It is the explorer and the
plugin disagreeing about whether a caller may see the hiring funnel, and the
more permissive one being right by accident. **The sensitive split (D3) keeps
those rows out of the projection entirely precisely because that class of
mistake is unrecoverable once it has been served.** Adding a second place to
make it is the wrong direction.

### 3. Version skew between clients reading one projection

`project_graph.py` replaces the public projection wholesale in a single
transaction. Both clients read that shape. Two projects deploy independently, so
a projection change plus a two-project rollout has a window where one client
speaks the new shape and the other the old — and the plugin's failure mode in
that window is a *plausible wrong answer*, not an error. One deploy, one shape.

### 4. Secret configuration is the realistic failure, and it doubles

The service-role key never leaves server-side code. That rule is enforced by
where the variable is set, and two projects mean two environment configurations
to keep correct, in a system where a missing variable has already produced a
confident-looking wrong result (`NP_BUILD_LOG`, B2's "enumerated 0 files"). Two
of everything is two chances to set one of them wrong.

### 5. Same-origin, so the browser never holds a cross-origin token

One app means the explorer calls its own origin: no CORS policy to write, no
preflight, no `Access-Control-Allow-Origin` that someone later widens to `*`
while debugging. Two apps put an allow-list in front of the data, and an
allow-list is a thing people loosen under time pressure.

---

## The arguments for two apps, stated fairly

These are real. None of them is currently true, which is why the recommendation
stands — but each is a genuine trigger, not a strawman.

**1. Machine traffic starving the UI.** An agent can issue queries far faster
than a person. On one project they share a concurrency budget, so a loop in the
plugin degrades the explorer for everyone. *Not yet true:* the user population is
a handful of people at IK, and the heaviest query measured is 5.6 ms warm. It
becomes true the moment the plugin is used unattended or on a schedule.

**2. Blast radius of a deploy.** The explorer is the surface that will change
most often — it is a UI, and UIs get fiddled with. A bad explorer deploy takes
the plugin down with it. *Mitigated but not eliminated:* a Vercel rollback is
fast, and the plugin's failure is "cannot reach the graph", which is loud and
correct rather than silently wrong. This is a real cost of one app, accepted
knowingly.

**3. Genuinely different auth in future.** If the plugin ever needs a token type
the browser cannot produce — a service token for scheduled runs, say — the two
auth paths stop sharing code, and at that point they may as well stop sharing a
deployment. *Not yet true:* both verify a Google ID token against the same JWKS
with the same `hd` check, which is one implementation and one set of tests.

---

## The decision, and what would reverse it

**One Vercel project.** Inside it:

```
  /                 explorer (static, E3)
  /api/*            JSON, called by BOTH clients
  web/lib/guard.py  the single place a role is checked before data is served
```

The plugin and the explorer call the *same handlers*. Not parallel handlers
sharing a library — the same ones. That is what makes the role boundary
single-sourced rather than merely coordinated.

**Split into two when any of these becomes true, and not before:**

1. The plugin runs unattended or on a schedule, so machine traffic is no longer
   bounded by human patience.
2. A non-IK consumer needs the API, making the explorer's browser-session model
   and the API's token model genuinely different systems.
3. The explorer acquires write surfaces beyond curation (F1), giving it a
   materially larger blast radius than the read API.

**What must be true before a split, if it happens:** the role boundary moves
entirely into the database (it is already mostly there), so that two deployments
cannot disagree about it even if their application code drifts. Split the
presentation, never the authorisation.

---

## What this does not decide

- **Which region.** G4, and it needs measurement rather than argument: the
  database is in one region and a function in the wrong one pays the round trip
  on every query.
- **How the plugin obtains a token.** §E.2, still open — §D's four layers verify
  a token; nothing yet issues one to a CLI.
- **Whether the explorer ships at all before the Drive sharing question is
  answered.** That is the gate below, and it is not a technical one.
