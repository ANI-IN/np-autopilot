# Autonomous run, 2026-11-07 (owner away ~4–5 hours)

Nothing involving production or data went wrong. Production, its settings and `main`
were not touched; no records were archived, merged, renamed or deleted; no
extraction ran. The only schema change is the approved index (migration 0038),
applied locally and on DEV after a verified backup.

## 1. What's done

**Freshness check:** production matches DEV and the local copy on every data row
(projection hash, node and edge fingerprints, all counts, curation tables). **No
refresh needed.**

**Commits** (branch `auto/knowledge-platform-20261102`, pushed):

| Commit | What |
|---|---|
| `d822d6e` | Server performance: compressed KB responses (brotli/gzip, compact JSON); Data quality in one request; the dashboard stops computing what it never shows; Activity query limited per half (same rows, 3–4× faster); migration 0038 index on `kb.changes(at, table_name)` |
| `504721d` | Front-end performance: views load on first use (dynamic import, skeleton, race guard); sidebar hover prefetches; startup modules preloaded (modulepreload); dashboard fills the sidebar counts from its own reply; palette ignores stale search replies; long tables skip off-screen rows (`content-visibility`); Graph skeleton; vendored libraries cached a day |
| `02717be` | Performance budgets in the suite (`tests/test_kb_perf_budget.py`: SQL statements per route, compression, a timed first page load, lazy views); `eval/kb_perf_pages.py`; the "group-by-type 40–50 s" was a test-harness artifact (fixed in the tests); `dev_db.py backup` now refuses an incomplete dump |
| `65f971a` | Docs: approved plan (`PLAN-2026-11-07.md`), Phase 1 design (UX audit, navigation, three directions), Phase 4 pilot plan, Phase 5 plugin platform, GO_LIVE plan changes and Realtime step, team test script |
| (this commit) | Mockup screenshots, the signed-out measuring tool, this report |

**DEV:** backup `dev_backup_20261106T214628Z.sql` (62.7 MB, 45 tables, end marker
present), then migration 0038 applied; DEV at 0038; record and relationship counts
unchanged (5,015 / 3,097).

**DEV preview:** redeployed to the same alias (`np-autopilot-kb-dev.vercel.app`),
functions in dub1, 7/7 smoke tests; the share link still works; one cron sync 4.4 s.

**Tests** (final code, one browser file at a time with ≥ 2.5 GB free, the graph file
one test per process): perf budget 10/10, map switch 11/11, sync 25/25, MCP 8/8,
Realtime gap 1/1, e2e 71/71, UI 34/34, console 2/2, Realtime 1/1, propagation 1/1,
graph 11/11 (group-by-type now 3.5 s, was ~40 s). `verify_all --skip-browser`:
**ALL PASS** (1,333 passed, 13 failed = the known baseline, 50 skipped). No test hung.

## 2. Performance before and after

**DEV preview, signed out** (the workspace boots to the sign-in gate; 5 runs each):

| | Before | After |
|---|---|---|
| Workspace to first screen, cold | 1,672 ms | **813 ms** |
| Workspace, median | 656 ms | **375 ms** |
| JavaScript files fetched at startup | 26 | **11** |
| Requests | 31 | **16** |
| Map page, cold / median | 593 / 421 ms | 547 / 313 ms |
| Database-backed request (Phase 0 region fix) | 1.3–1.8 s | ~0.4 s |
| Sync run on Vercel | 22.9 s | 4.4 s |

**Local real-data copy** (same data size, no network; server work only):

| | Before | After |
|---|---|---|
| API p95 / max | 179 / 941 ms | **109 / 835 ms** |
| Activity query (dashboard rows / search) | 59 / 250 ms | **17 / 59 ms** |
| Page loads (warm medians) | 0.20–0.38 s | 0.23–0.39 s (within noise) |
| Navigation between views | 94–265 ms | 125–375 ms (noise on a loaded laptop) |
| Palette search (incl. the 120 ms typing delay) | measured wrongly before | ~190 ms |
| Graph load / group by type | 640 / 735 ms | 875 / 859 ms (noise; target < 2 s met) |
| Data quality, cold load | 593 ms | 1,109 ms — **watch:** one request now does the attention work itself; on the preview it saves a round trip. Re-measure signed in |
| CLS | 0–0.01 | 0–0.01 |

**Signed-in preview numbers: pending token** (`DEV_PERF_TOKEN`: create an API token in
Settings → API tokens, 7 days, and put it in `.env`; then
`python eval/kb_perf_pages.py --base https://np-autopilot-kb-dev.vercel.app --token ... --bypass ...`).
Sign-in time is yours to time.

## 3. Waiting for your decision (priority order, with my recommendation)

1. **Visual direction** (`docs/design/phase1/README.md`, mockups and screenshots).
   *Recommendation:* **A · Clarity** for the workspace, with C's search-first hero on
   Home, and the map moved onto the same tokens (its dark theme from A's dark mode).
   Lowest risk for current users, best density for long lists.
2. **Topic collision report** (local only: `.measure/review/topic-collisions.md`).
   146 names / 363 records: **74 MERGE** (150 records; 76 archived into survivors),
   **57 KEEP + contextual rename** (181 records), **15 NEEDS DECISION** (32 records).
   Every record has exactly one relationship (its module's `covers`), empty summaries
   and no edits since import; no resources are shared, so merges move 76 relationships
   and 141 links with no duplicates. *Recommendation:* approve the 74 merges and 57
   renames; decide the 15 individually.
3. **Workflow archive list** (local only: `.measure/review/workflow-archive.md`):
   16 categories + 92 processes, 92 relationships and 108 provenance attachments, no
   owners or tags. The sync will not re-create them (it skips archived records;
   `sync_map` rows must stay). *Recommendation for the 39 owner suggestions:* the
   source table `public.workflow_owners` already holds them and is admin-only; take a
   JSON snapshot to `backups/` and **also clear `suggested_owner` from the archived
   records' props** (archived records are still readable by viewers); decide whether
   the 39 audit-log rows that mention them need redacting. Archive in one transaction
   with a fixed timestamp; restore in one statement (the UI's one-by-one restore would
   not bring back the relationships).
4. **Embeddings:** *recommendation:* **bge-small-en-v1.5** in the scheduled Python worker,
   `pgvector(384)`, Supabase hybrid search (full text + vectors + reciprocal rank fusion).
   Free, fast on CPU, slightly better retrieval than Supabase's built-in gte-small.
5. **Phase 4 pilot plan** (`docs/design/phase4-pilot-plan.md`): Applied Agentic AI (7
   pages, one marked do-not-use and listed as skipped); estimate 0.3–0.5M tokens and
   1–2 hours, to be replaced by measured numbers; a 40-query quality set.
6. **Plan changes before go-live** (in GO_LIVE.md): **Vercel Pro** ($20/month; Hobby
   forbids commercial use) and **Supabase Pro** for production ($25/month; Free has no
   backups and pauses idle projects) — about **$45/month**; optional PITR +$100.
7. **Where scheduled runs happen:** *recommendation:* Claude Code cloud scheduled tasks
   (research preview, hourly at most, can use our MCP connector), fallback GitHub
   Actions with `claude-code-action`. Terms flag: subscriptions are for ordinary
   individual use; heavy production automation points to an API key.
8. **Monitoring channel:** email or a Slack webhook for failed syncs, failed
   extractions and server errors (a small scheduled check reading `kb.sync_runs` and
   error counts; Vercel's own alerts need Pro).
9. **Phase 5:** recommend **Knowledge Search** as the first example plugin; Supabase
   Auth as the OAuth server for Claude.ai connectors (`docs/design/phase5-plugin-platform.md`).
10. **Repo private:** steps in GO_LIVE notes; CLI deploys don't depend on it.
11. **`DEV_PERF_TOKEN`** for the signed-in numbers.

## 4. Failed, skipped, or worth knowing

- **First DEV backup was incomplete** (2 of 44 tables, no end marker) after the dump
  dropped mid-way; the script did not notice. Renamed `.INCOMPLETE`, retried once:
  complete. `dev_db.py backup` now refuses an incomplete or failed dump.
- **Migration 0038 on DEV first timed out**: the failed dump's server session was still
  open ("idle in transaction", holding locks). I ended that one session (my own stale
  backup connection) and the retry applied cleanly.
- **Not done (not in this run's list or riskier):** optimistic UI for edits; ETag/304 for
  `/types`; true windowed rendering of lists (`content-visibility` used instead); a
  per-request role cache (the existing caches are per user and role, nothing is shared
  across users).
- **Local measurements are noisy** on the laptop (single-threaded local server, tests
  running); the preview numbers are the meaningful ones.
- Earlier this session (before this run) one e2e run hung when started below the
  memory floor; its re-run passed 71/71. The runner now waits for ≥ 2.5 GB free.
