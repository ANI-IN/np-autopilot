# PERFORMANCE BASELINE — production, before B3

Measured on `np-autopilot.vercel.app` by `eval/measure_signed_in.py`,
2026-09-29, signed in. B3 compares against these.

## No baseline yet — two runs, two failures

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
