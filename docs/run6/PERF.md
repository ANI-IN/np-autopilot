# Run 6: performance at real-data size (B5)

Measured on 2026-11-03 on this laptop, against `kb_b5`, a local clone of the real data. The clone holds 5,087 live records (3,087 current and 2,000 legacy), 6,941 relationships and 1,827 links. All requests were made as the local admin.

Other agents were running on the laptop during these measurements. A difference of up to about ±30 % between the before and after columns is machine load, not a code change. The real changes are the Data quality rows and the archived graph.

## Tools

All four are in `scripts/` and owned by B5.

- **`kb_realdata_profile.py --db kb_b5 [--explain]`** sends every request behind every screen, the "/" map's routes, and `GET /api/kb/graph`. It calls the real WSGI app in-process, so token checks, RLS and JSON encoding all run. It reports p50 and p95 over 7 runs. With `--explain`, it also runs EXPLAIN (ANALYZE) on every SELECT.
- **`kb_browser_profile.py`** uses real headless Chrome. It measures each screen's time to interactive from a cold page load, the JavaScript bytes loaded, graph expand times, and heap size after GC across 50 graph opens. Take the browser lock before running it.
- **`kb_perf.py` and `kb_explain.py`** work on 5,000 synthetic records and 15,000 synthetic relationships. They now cover the run-6 endpoints:
  - graph: a page of records, `archived=1`, focus at depth 1 and depth 2, and a hub with 600 relationships
  - outline, teaching and timeline
  - quality
  - duplicates, in the worst case

## Targets

| Target | Before | After | Met? |
|---|---|---|---|
| Every screen interactive in under 1.5 s | Data quality took **19.6 s** (B3 saw over 45 s under load). The graph of a record with 360 neighbours took 2.8 s. | Every list and report screen takes 0.21–0.88 s. Data quality takes 0.88 s cold and is cached after that. | **Yes, except the graph canvas** (see below) |
| Graph focus or expand under 500 ms | Expand: p50 92 ms, p95 133 ms. Server `graph?focus`: 119 ms. | Expand: p50 90 ms, p95 129 ms. Server: 118 ms. | **Yes** |
| List and search p95 under 150 ms, server side | 11–83 ms | 10–40 ms | **Yes** |
| List and search, as the browser sees it | n/a | A cold load of a whole page (app shell included) takes 0.28–0.40 s. Navigating within the app adds only the request time from the server table. | **Yes** |
| Zero console errors and zero unhandled rejections | A viewer on Settings got 2 × 403 errors (the members and sync tabs) | 0 in `tests/test_kb_console_run6.py` (admin and viewer). 0 across the browser pass on real data. | **Yes** |

**The one miss: opening the graph on a large neighbourhood takes 2.7 s.**

- The requests finish by 0.47 s: cytoscape loads first, then the neighbourhood, then the saved positions.
- The remaining ~2.3 s is the client-side layout of about 360 nodes in `public/kb/js/views/graph.js`. B2 owns that file and is rewriting it.
- **Recommendation for B2:** paint first with saved positions or a preset or concentric layout, and run the force layout after that, or cap its iterations.
- `kb_browser_profile.py --record <id>` measures this.

## Server side, every screen

Values are p50 / p95 in ms over 7 runs. KB is the response size.

| Screen | Request | KB | before p50 / p95 ms | after p50 / p95 ms |
|---|---|---|---|---|
| shell | `/api/kb/me` | 0 | 3.3 / 4.6 | 2.6 / 4.5 |
| shell | `/api/kb/types` | 18 | 4.4 / 4.8 | 3.6 / 4.0 |
| shell | `/api/kb/people` | 0 | 5.4 / 6.1 | 3.0 / 5.2 |
| shell | `/api/kb/counts` | 1 | 7.7 / 7.7 | 3.9 / 4.5 |
| shell | `/api/kb/sync` | 2 | 5.6 / 5.9 | 3.0 / 3.8 |
| shell | `/api/kb/changes?since=<n>` | 12 | 5.6 / 6.5 | 5.3 / 10.0 |
| dashboard | `/api/kb/dashboard` | 15 | 9.0 / 9.0 | 3.2 / 4.0 |
| records | `/api/kb/nodes?limit=100` | 80 | 34.2 / 49.7 | 10.9 / 11.4 |
| records | `/api/kb/views` | 0 | 5.9 / 6.0 | 2.0 / 2.8 |
| records | `/api/kb/tags` | 0 | 5.6 / 6.6 | 2.5 / 3.1 |
| records | `/api/kb/nodes?type=module&limit=100` | 17 | 12.7 / 19.2 | 7.6 / 10.1 |
| records | `/api/kb/nodes?type=instructor&sort=name&limit=100` | 18 | 10.9 / 11.7 | 5.8 / 7.0 |
| programs | `/api/kb/nodes?type=program&limit=100` | 0 | 8.4 / 14.2 | 4.2 / 5.1 |
| resources | `/api/kb/resources?limit=100` | 37 | 11.4 / 11.5 | 5.8 / 9.9 |
| outline | `/api/kb/outline` | 100 | 133.4 / 176.6 | 94.4 / 138.0 |
| graph | `/api/kb/graph` | 1062 | 195.7 / 198.7 | 166.2 / 184.6 |
| graph | `/api/kb/graph?legacy=all` | 812 | 162.4 / 167.8 | 186.5 / 233.2 |
| graph | `/api/kb/graph?archived=1` | — | 1,010–1,122 | 164–229 |
| graph | `/api/kb/graph?archived=1&legacy=all` | — | 1,206–1,408 | 153–156 |
| graph | `/api/kb/graph/positions` | 261 | 57.5 / 67.9 | 28.4 / 58.1 |
| graph | `/api/kb/nodes?type=program,course&sort=name&limit=20` | 0 | 10.3 / 10.5 | 9.3 / 15.8 |
| graph focus | `/api/kb/graph?focus=<id>&depth=1` | 185 | 119.0 / 127.6 | 118.3 / 119.3 |
| graph focus | `/api/kb/graph?focus=<id>&depth=2` | 192 | 111.3 / 117.9 | 127.8 / 142.4 |
| graph focus | `/api/kb/graph?focus=<id>&depth=2&archived=1` | — | 329–348 | 115–119 |
| teaching | `/api/kb/views/teaching` | 16 | 25.6 / 26.0 | 28.7 / 53.0 |
| timeline | `/api/kb/views/timeline` | 145 | 69.3 / 94.1 | 53.6 / 182.5 |
| activity | `/api/kb/activity?limit=50` | 91 | 13.1 / 17.4 | 8.6 / 11.2 |
| **quality** | **`/api/kb/quality`** | 12 | **29,041 / 30,850** | **52.6 / 63.6** |
| quality | `/api/kb/quality/sync` | 0 | 5.5 / 6.9 | 5.4 / 6.0 |
| **quality** | **`/api/kb/quality/duplicates`** | 10 | **27,569 / 28,412** | **5.3 / 8.8** |
| approvals | `/api/kb/proposals` | 0 | 5.4 / 6.8 | 5.4 / 8.1 |
| approvals | `/api/kb/flags?status=open` | 0 | 3.7 / 3.7 | 3.3 / 6.5 |
| archived | `/api/kb/archived?kind=records` | 11 | 61.7 / 74.4 | 45.2 / 51.6 |
| settings | `/api/kb/types?archived=1` | 18 | 5.8 / 6.4 | 4.1 / 7.3 |
| settings | `/api/kb/members` | 0 | 5.7 / 5.9 | 5.6 / 8.6 |
| settings | `/api/kb/tokens` | 0 | 3.8 / 4.1 | 2.8 / 6.2 |
| settings | `/api/kb/templates` | 0 | 3.8 / 4.1 | 3.1 / 6.3 |
| record | `/api/kb/nodes/<id>` | 78 | 43.4 / 47.0 | 49.0 / 58.9 |
| record | `/api/kb/nodes/<id>/completeness` | 1 | 12.7 / 13.3 | 10.1 / 10.5 |
| record | `/api/kb/nodes/<id>/impact` | 0 | 4.7 / 5.7 | 4.2 / 5.3 |
| record | `/api/kb/nodes/<id>/history` | 46 | 8.8 / 10.0 | 16.5 / 66.3 |
| search | `/api/kb/search?q=python` | 7 | 52.0 / 52.9 | 27.9 / 29.4 |
| search | `/api/kb/search?q=system%20design` | 7 | 73.6 / 82.6 | 30.9 / 39.3 |
| search | `/api/kb/nodes?q=data&limit=100` | 79 | 30.9 / 37.4 | 15.9 / 20.5 |
| map / | `/api/me` | 0 | 10.2 / 14.3 | 5.8 / 9.6 |
| map / | `/api/structure` | 621 | 385.4 / 575.5 | 247.9 / 371.8 |
| map / | `/api/overview` | 37 | 9.7 / 9.9 | 10.0 / 15.5 |
| map / | `/api/coverage` | 1 | 67.0 / 70.1 | 102.5 / 130.6 |
| map / | `/api/search?q=python` | 5 | 15.3 / 15.4 | 20.9 / 26.2 |
| map / | `/api/node?id=<id>` | 7 | 6.5 / 6.6 | 10.4 / 11.1 |
| map / | `/api/node?id=<id>&detail=1` | 8 | 7.5 / 8.2 | 13.3 / 15.5 |
| map / | `/api/neighbourhood?id=<id>` | 1 | 8.0 / 8.8 | 12.3 / 13.0 |
| map / | `/api/staffing?domain=<id>` | 1 | 4.2 / 6.3 | 4.6 / 8.6 |

The "/" map's routes still read the old tables on this branch, because B1 is moving them to kb. They should be measured again after B1 merges: run `kb_realdata_profile.py --only "map /"`.

### What was slow, and the fixes

**1. Data quality went from 29 s to 53 ms.** It takes 0.9 s on a cold load and is cached after that.

- **Cause:** `find_duplicate_nodes` compared every pair of same-type records. For the 2,733 topics alone, that is 3.7 M `similarity()` calls.
- **Why the trigram index did not help:** under RLS, the planner may not push the non-leakproof `%` operator into an index scan. EXPLAIN shows 25–37 s even with `%` and the GIN index.
- **Fix:** `web/lib/kb/duplicates.py` replaces it with a prefix-filtered similarity join (PPJoin) over the `show_trgm()` trigram sets. It runs as the caller, in one SELECT.
- **Same answer as before:** it returns exactly the same pairs and scores. On the real data, that is 2,954 pairs at threshold 0.6 and 9,388 at 0.4. `tests/test_kb_duplicates.py` checks it against the old SQL and against brute force.
- **Memory:** bounded, because only the top 200 pairs are kept, in a heap.
- **Caching:** results are cached per caller, keyed on the newest `kb.changes` id. This is the same pattern as `_cached`, so any write invalidates them.
- **Wiring:** the fix needs a one-function change in `web/lib/kb/service.py`, which is B1's file. It is in `docs/run6/patches/b5-service-find-duplicates.patch`; apply it with `git apply`. All the "after" numbers were measured with the patch applied.
- **Worst case:** on synthetic data where every name is alike, it takes 21 s uncached. The old SQL is quadratic there too. On the real data it takes 0.4–0.8 s.

**2. The graph with `archived=1` went from 1.0–1.4 s to 0.16–0.23 s.**

- **Cause:** `kb.edges` had only partial indexes (`where archived_at is null`). Any read that includes archived relationships therefore scanned `kb.edges` once per record. That covers the degree count, focus mode, history and delete impact.
- **Fix:** migration **0034** adds `edges_source_all_idx` and `edges_target_all_idx`.
- **Effect on focus:** focus at depth 2 with `archived=1` went from 340 ms to 117 ms.

**3. No other index was needed at this size.** After the fixes, every statement in the EXPLAIN output takes under 25 ms. The sequential scans that remain are on tables of about 5,000 rows, where a scan costs less than an index.

**4. No screen has an N+1 query pattern.** The record panel issues the most statements per request: about 10, and that number does not grow with the data.

### Environment finding: a 40 ms stall on large parameters (local only)

- **What happens:** on this laptop, every statement whose parameters exceed about 8 KB pays a fixed delay of about 42 ms. An example is `id = any(%s)` with more than about 300 uuids, which `graph.py` uses in its node and relationship queries.
- **Measurements:**
  - Below 200 uuids, a round trip takes 1 ms.
  - At 363 uuids it takes 44 ms, whatever the plan; the server's own execution is 2 ms.
- **Cause:** Docker Desktop's port forwarding (delayed ACK), not Postgres.
- **Impact:** about 90 ms of the ~118 ms that `graph?focus` takes.
- **Production:** this should not happen on Linux (Vercel to Supabase).
- **Change that would also help production:** keep the id list on the server. Select the nodes and relationships from the same `walk` or page CTE instead of sending the ids back as an array parameter. `graph.py` is lead-owned, so this is for the lead.

## Browser

Headless Chrome at 1536 px, a cold page load per screen, real data.

| Screen | Interactive ms before | after | JS loaded |
|---|---|---|---|
| dashboard | 255 | 286 | 354.2 KB |
| records | 379 | 396 | 354.2 KB |
| programs | 290 | 291 | 354.2 KB |
| courses | 293 | 256 | 354.2 KB |
| resources | 262 | 276 | 354.2 KB |
| outline | 614 | 426 | 354.2 KB |
| graph start | 239 | 243 | 354.2 KB |
| teaching | 324 | 300 | 354.2 KB |
| timeline | 429 | 371 | 354.2 KB |
| activity | 352 | 296 | 354.2 KB |
| **quality** | **19,566** | **879** | 354.2 KB |
| approvals | 310 | 280 | 354.2 KB |
| archived | 262 | 301 | 354.2 KB |
| guide | 274 | 232 | 354.2 KB |
| settings | 203 | 312 | 354.2 KB |
| settings-members | 228 | 211 | 354.2 KB |
| settings-sync | 270 | 269 | 354.2 KB |
| graph (a record with 360 neighbours, depth 1) | 2,798 | 2,709 | 780 KB (cytoscape is 425 KB and loads only here) |
| "/" map (to network idle) | 1,183 | 1,140 | 1,489 KB |

**Interactive** means no skeleton and nothing `aria-busy` is left, and the view has content.

- **Lazy loading works.** The graph library loads only on graph screens. Every other screen loads only the workspace's own 354 KB of modules.
- **The "/" map loads 1.49 MB of JavaScript.** In run 6 the map belongs to B1 and B2, so this is recorded here and was not changed.
- **Expand ×50** inside one open graph: p50 90 ms, p95 129 ms, max 171 ms.

### Memory over a long graph session: a leak in B2's and B1's files

- **Symptom:** opening the graph and leaving it 50 times, the heap after GC grew **9.3 → 38 → 70 → 102 → 133 → 165 MB**. That is about 3 MB per opening, and the memory is never released. Expanding 50 times within one graph does not grow the heap.
- **Cause:**
  - `viewGraph` registers `onLiveChange(...)` and `onPresence(...)` every time the graph opens (`public/kb/js/views/graph.js:722` and `:731`).
  - `live.js` and `realtime.js` keep their listeners forever and have no way to remove one.
  - Each listener's closure holds that opening's Cytoscape instance, which is never destroyed.
  - `detail.js` registers its listeners once, at module level, so it does not leak.
- **Fix:**
  - **B1, `public/kb/js/live.js`:** make `onLiveChange` return an unsubscribe function:

    ```js
    export function onLiveChange(fn) {
      listeners.push(fn);
      return () => {
        const i = listeners.indexOf(fn);
        if (i >= 0) listeners.splice(i, 1);
      };
    }
    ```

    Do the same for `onPresence` in `realtime.js`.
  - **B2, `graph.js`:** keep both unsubscribe functions. When the view is left, call them and `cy.destroy()`. The router replaces `#view` on navigation, so either check `!cyBox.isConnected` in the listener or use a router leave hook.
  - **Check:** `kb_browser_profile.py --record <id> --repeat 50` should then show a flat heap.
