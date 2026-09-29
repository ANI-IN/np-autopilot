# PERFORMANCE BASELINE — production, before B3

Measured on `np-autopilot.vercel.app` by `eval/measure_signed_in.py`,
2026-09-29, signed in. B3 compares against these.

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

## Not yet measurable

`/api/structure` does not exist in production, so it has no "before". It will
be reported as a new-view figure, not as an improvement.
