# LATENCY — the measurement record

Measured 2026-09-18, against the real deployment, from a signed-in session.
This replaces the projection `DEPLOYMENT.md` carried from 2026-09-17.

**Read §0 before quoting any number here.** Two of the most useful claims in
this document are inferences, and one component of user-visible latency has no
measurement behind it at all.

---

## 0 · What is measured, what is inferred, what is unmeasured

The distinction is load-bearing. The previous projection was wrong in a way that
would have been caught by making it, and the next person reading this will
otherwise take I1 for a reading.

### Measured — direct readings

| # | Finding | Instrument |
|---|---|---|
| M1 | Function ran in `iad1`; now runs in `icn1`. Database is `ap-northeast-2` | `x-vercel-id: bom1::iad1::…` → `bom1::icn1::…`, 5 endpoints each |
| M2 | Server-side `ms` **before**: median **2,252** (n=23) | `guard.audit()` via `vercel logs` |
| M3 | Server-side `ms` **after, warm**: median **44.3** (n=18) | same |
| M4 | Cost is **flat with respect to rows returned**, before and after | see §2 |
| M5 | One request = **11.2 round-trip units**; the query is **1.1** of them | phase timing at a measured 147.3 ms RTT |
| M6 | Cold start: **5,708.7 ms** on iad1, **788.4 ms** on icn1 | first request on each deployment, n=1 each |
| M7 | Edge→function→edge: **~170 ms** (iad1) → **~117 ms** (icn1) | `/api/config`, which touches no database, minus the static page |
| M8 | A click issues **two sequential** requests | `public/index.html:664` + audit timestamps 2.55 s apart |

### Inferred — model output, not readings

- **I1. `iad1`↔Seoul ≈ 201 ms.** Derived as M2 ÷ M5. Never measured directly.
  It is corroboration that the model predicted the observation with a
  physically plausible constant — not an independent reading.
- **I2. The connect profile holds identically in every region.** M5 was measured
  on the *laptop→Seoul* path only. §3 shows this assumption was the one that
  broke.
- **I3. Client-side network per request.** M7 measures a curl round trip from
  one laptop on one connection, not a browser with keepalive. Treat ~117 ms as
  an order of magnitude.

### Unmeasured — no evidence in either direction

**Render and layout cost.** `expand()` calls `recompute()`, which re-runs the
force layout to its 366-frame freeze. Nothing in this document measures it. The
browser-side harness that would have (CDP against a signed-in tab) could not be
run: Chrome refused to expose a debugging port.

**So a good server number is not "the app is fast."** Server time per request
fell ~51x. What a user experiences is that, plus network, plus a render cost
this project has never measured. If the explorer still feels slow at 3,146
nodes, the render path is the untested half and nothing here bears on it.

---

## 1 · The change

`vercel.json` had no `regions` key, so functions ran in Vercel's default region
(`iad1`, Washington DC) while the database is in `ap-northeast-2` (Seoul). Every
statement crossed the Pacific.

```json
"regions": ["icn1"]
```

Hobby permits a **single** region, any region — multi-region is Pro and above.
So this pin is available on the current plan, and only this pin is.

## 2 · Before and after

Warm figures. The first request on each deployment is a cold start and is
excluded — it is reported separately in M6.

| endpoint | iad1 median | icn1 median (warm) | n (after) |
|---|---|---|---|
| `search` | 1,931.6 ms | **40.1 ms** | 3 |
| `node` (= provenance) | 2,362.8 ms | **49.8 ms** | 4 |
| `neighbourhood` d1 | 2,240.3 ms | **79.9 ms** | 2 |
| `me` | 2,274.4 ms | **40.8 ms** | 9 |
| **all warm requests** | **2,252 ms** (n=23) | **44.3 ms** (n=18) | — |

**~51x faster; ~2,208 ms saved per request.**

**The flatness survived the move**, which is the finding that identified the
cause in the first place. `node` returns 1 row and `neighbourhood` returns 64;
they differ by 30 ms. A cost that does not scale with work done is not query
cost — it is per-request overhead, and it was being multiplied by a
trans-Pacific round trip.

### What a click costs now

Two sequential requests (M8): `neighbourhood` then `node`.

| | server | + network (I3) | total |
|---|---|---|---|
| before | 4,603 ms | ~340 ms | **~4.9 s** |
| after | ~130 ms | ~235 ms | **~0.37 s** |

**Plus an unmeasured render cost in both columns.** See §0.

## 3 · The prediction, and where it failed

Before deploying, the predicted warm figure was **15–25 ms**, against
`DEPLOYMENT.md`'s projected ~2 ms.

**The measurement landed at 44.3 ms — outside the predicted range, about 1.8x
the upper bound.** The prediction was right about the mechanism and wrong about
the magnitude, and the two failures are worth separating:

- **The old projection was wrong about the mechanism.** It projected the
  server-side query time plus one round trip — "roughly 2 ms for a node or a
  depth-1 neighbourhood". But a request is not one round trip. It is ~11 (M5),
  because `request_connection` opens a fresh connection and issues two setup
  statements before the query. The projection was **right that the region
  dominated, and wrong about what the region was multiplying.**
- **The new prediction was wrong about the constant.** It assumed all 11.2 units
  were network, so in-region they would collapse to ~1.5 ms each. They did not,
  because some of that cost is CPU and does not shrink with distance: the TLS
  handshake, and SCRAM authentication, which is *deliberately* expensive
  (iterated PBKDF2). Connection setup has an irreducible floor that geography
  never touched. I2 was the faulty assumption.

Implied per-unit cost is now 44.3 ÷ 11.2 ≈ **4.0 ms**, and that number is a
blend of in-region network and fixed CPU rather than a round trip.

**The consequence for what comes next:** the remaining round-trip work
(pipelining the two setup statements, or reusing connections) is still ~90% of
each request by structure, but the absolute prize dropped from ~600 ms to
~12 ms. It is no longer worth the risk it carries — `request_connection` is
where "every request runs as `authenticated`" is enforced, and a reused
connection that fails to reset leaks one caller's claims into the next request.

## 4 · What would change this picture

- **Render and layout at 3,146 nodes.** The only unmeasured component, and now
  the largest unknown in user-visible latency. Needs a browser: resource timing
  plus a frame count around `recompute()`.
- **A direct `iad1`→Seoul RTT**, which would turn I1 into a reading. Only
  obtainable by running code in `iad1`, and no longer worth doing — the
  deployment moved.
- **Cold starts.** n=1 on each deployment. 788.4 ms is one sample, not a median.

## 5 · Method, so this can be repeated

```bash
vercel logs -p np-autopilot --since 45m -n 500 --json
```

Each event repeats its message ~10x in the CLI's `logs` array; dedupe on the
event `id` or every median is computed over duplicates. Split by `deploymentId`
to separate deployments rather than guessing from timestamps. Drop the first
request on a new deployment: it is a cold start and it is ~18x the warm median.

`guard.audit()`'s `ms` starts at the top of `do_GET` and is recorded **before**
the response is written. So it spans identify + connect + query, and excludes
both the network and the response write. It is a server-side number and must
not be quoted as what a user waits.
