# PERFORMANCE BASELINE — production, before B3

Measured on `np-autopilot.vercel.app` by `eval/measure_signed_in.py`,
2026-09-29, signed in. B3 compares against these.

## BASELINE — production, pre-deploy, 2026-09-29

`python3 eval/measure_signed_in.py --phase pre`, signed in, 5 cold loads,
20 samples per endpoint. **This is what B3 is measured against.**

### Cold load — median (min–max) over 5 loads, each in a fresh context

| | median | range |
|---|---:|---|
| TTFB | **64 ms** | 62–67 |
| first contentful paint | **220 ms** | 196–232 |
| DOMContentLoaded | **147 ms** | 132–163 |
| load event | **148 ms** | 133–164 |
| settled (networkidle) | **1,202 ms** | 1,172–**5,533** |
| document transfer | 33,399 bytes | (88,995 decoded) |

The settled range carries one 5.5 s outlier against a tight 1.17–1.20 s for the
other four. The median is the figure; the outlier is recorded rather than
dropped, because a 5 s settle happened once and will happen again.

### Payload per call

| | bytes |
|---|---:|
| `/` | 88,995 |
| `/api/overview` | 35,204 |
| `/stats.json` | 512 |
| `/api/me` | 179 |

### Latency, signed in, 20 samples

| endpoint | p50 | p95 | bytes | status |
|---|---:|---:|---:|---:|
| `/api/overview` | **334 ms** | **447 ms** | 35,204 | 200 |
| `/api/search?q=api` | **273 ms** | **372 ms** | 1,601 | 200 |
| `/api/config` | **218 ms** | **394 ms** | 429 | 200 |
| `/api/node` | **322 ms** | **506 ms** | 617 | 200 |
| `/api/structure` | — | — | — | 404 — not served (new endpoint) |

`/api/structure` has no "before". It will be reported as a new-view figure, not
as an improvement.

### What this baseline is NOT

`/api/overview` returns 35,204 bytes for ~60 nodes. The structure view returns
3,307 nodes and 4,970 edges, so B3's payload target is not "smaller than
35 KB" — it is a payload roughly 55x the node count under 150 KB brotli.
(3,307 measured 2026-09-29 on the local projection, and from
`knowledge/merged_graph.json`. The 3,308 first written here was copied from a
B2 comment in `public/index.html` that was correct when written, before PPL-11
merged `Bharath` into `Bharath Anand` — it was already stale when it was copied.) The
comparison that matters is bytes per node, and time to a settled layout.

## Superseded — two runs that produced no usable table

Both attempts produced no usable latency table, for two different reasons, and
both are recorded because the second was caused by the fix for the first.

**Run 1 — the timed requests were unauthenticated.** A bare `fetch(ep)` from
`page.evaluate`; the app sends the token as an `Authorization` header from page
memory, not a cookie. Every timed request was a 401 at a plausible-looking
219 ms.

**Run 2 — the token check read the wrong scope.** `public/index.html` declares
`let SESSION = null` at the top level of a classic script, which lives in the
global LEXICAL environment and NOT on `window`. The check asked for
`window.SESSION`. Verified against the real production page, signed out:

```
typeof window.SESSION  ->  "undefined"
bare SESSION           ->  null (declared)
```

So it was false whether or not anyone was signed in, and it reported "no access
token in the page" on a page that had signed in automatically in two seconds.
The app itself reads the bare name; the script now does too.

Cold-load numbers from those runs are NOT a baseline either: TTFB was 207 ms in
one and 1,230 ms in the other with nothing deployed between them. A single cold
sample is noise. The script now takes five cold loads, each in a fresh context,
and reports **median and range**.

## Superseded — the single-sample figures

## Valid, and kept as the baseline

| | value |
|---|---|
| TTFB | **207 ms** |
| first contentful paint | **320 ms** |
| settled (networkidle) | **1,839 ms** |
| document transfer | 33,399 bytes (88,995 decoded) |
| `/stats.json` | 512 bytes |
| `/api/config` | 429 bytes |

## INVALID, and discarded — the latency table

The first run reported `/api/overview` at p50 219 ms, `/api/search` at 216 ms,
and "no id returned by overview". Every one of those requests was a **401**.

The timed loop issued a bare `fetch(ep)` from `page.evaluate`. This app keeps
the Supabase access token in **page memory** and sends it as an `Authorization`
header — it is not a cookie — so Playwright's saved storage state authenticated
nothing. The 54-byte bodies were `{"error":"unauthorised"}`, and the table was
measuring the auth rejection path at a plausible-looking 219 ms.

Caught by the corpus owner reading the byte column, not by the script.

### What now prevents it

- The timing loop runs inside one `page.evaluate` that reads the token itself
  and sends it as a header. The token never crosses into the Python process, so
  nothing can print or store it.
- `invalid_measurements()` fails the run on any non-200, or any data response
  under 200 bytes (`/api/config` is exempt — four settings is legitimately
  small).
- A missing `/api/node` id fails the run rather than printing a dash.
- The page is checked for a token BEFORE anything is timed, so an
  unauthenticated page says so instead of throwing inside the loop.
- `tests/test_measurement_is_authenticated.py` replays the exact bad run —
  401/54 bytes, verbatim — and asserts it is rejected.

## Which run is which — stated, never inferred

`eval/measure_signed_in.py` requires `--phase`:

| flag | `/api/structure` | the other four |
|---|---|---|
| `--phase pre` | probed and reported (`not served (new endpoint)`), never required | **strict** |
| `--phase post` | timed and **required** | **strict** |

There is no default. Inferring "this must be a pre-deploy run because
`/api/structure` 404s" would make the script relax its own checks exactly when
the endpoint it guards had broken — a guard that switches itself off at the
moment it matters. `invalid_measurements()` raises on any phase it was not
given.

The relaxation is scoped to the unshipped endpoint and to nothing else: in
`--phase pre`, a 401 on `/api/overview` still fails the run, and a missing
`/api/node` id still fails it in both phases.

## Not yet measurable

`/api/structure` does not exist in production, so it has no "before". It will
be reported as a new-view figure, not as an improvement.

---

# COLD STARTS — investigated, measured, mostly fixed

The 5.5 s settled outlier and the earlier ~1.2 s TTFB both look like serverless
cold starts. Four candidate causes were measured; two were real.

## 1. Every request opened a new database connection — THE BIG ONE

`request_connection` called `db.connect()` per request and closed it in the
`finally:`. Measured from a laptop to `ap-northeast-2`:

| | median | range |
|---|---:|---|
| new connection each request | **1,624 ms** | 1,590–2,119 |
| reused connection | **712 ms** | 705–1,574 |
| after collapsing the setup to one round trip | **591 ms** | 583–598 |

**1,624 → 591 ms, a 64% cut.** Those are laptop-to-Seoul numbers; the function
runs in `icn1`, next to the database, so the absolute figures will be far
smaller — but the structure is the point: one connect amortised over a warm
instance instead of one per request. The cold-start premium (the first request
on a new instance, which still pays the connect) measured **1,131 ms**.

A Vercel Python function serves one request at a time per instance, so a
module-level connection is not shared concurrently.

**What makes it safe is the rollback, not the caching.** Both pieces of
per-request state are transaction-local, so the `finally:` rollback is the only
thing between one caller and the next.
`tests/test_warm_connection_isolation.py` asserts a second request cannot
inherit the first's identity, that an *unidentified* request sees nothing after
an identified one, that the error path still clears, and that the reset is a
rollback and never a commit.

## 2. Two round trips before any query ran

`set_config('request.jwt.claims', …)` then `SET LOCAL ROLE` — two statements,
two round trips, on every request. `set_config('role', …, true)` is what `SET
LOCAL ROLE` does, so both now go in one statement. Worth ~120 ms per request
from here; one RTT in-region.

## 3. The router imported every endpoint at cold start

A cold start serving `/api/overview` also paid for `session` → `gotrue` →
`urllib.request`, and for `curate`. The route table is now a set of names and
the module is imported when it is served.

| | median | range |
|---|---:|---|
| before | 80.9 ms | 79.5–144.4 |
| after | **56.2 ms** | 54.9–60.9 |

A dead `from http.server import BaseHTTPRequestHandler` in `api/session.py`,
unused since the per-file handler shells were removed, accounted for ~4 ms of
that.

`tests/test_lazy_route_table.py` asserts, in a fresh interpreter, that
importing the router loads none of them and that serving one route loads only
that one — and that `identify()` still runs BEFORE the module is loaded, which
it did not after the first attempt.

## 4. Bundle size and region — NOT the problem, no action

- Deployed bundle after `excludeFiles`: **1.43 MB**. Not a cold-start factor.
- `regions: ["icn1"]` is already co-located with Supabase's `ap-northeast-2`.

## Not done, and it is the owner's call

Raising the function's `memory` setting gives a Vercel function proportionally
more CPU, which shortens interpreter start and connection setup. It is a
billing decision, not a technical one, so it is recorded here rather than
applied.
