# Project history

How the platform got here, in one page. The per-run reports, screenshots and
measurements that used to live in `docs/run6/`, `docs/redesign/`,
`docs/inventory/`, `docs/perf/` and `docs/archive/` were consolidated here and
deleted; git history keeps every one of them.

**The current state and the owner's next steps are in
[HANDOFF.md](HANDOFF.md)** (its top section is always the latest).

## Files in this folder

| File | What it is |
|---|---|
| [HANDOFF.md](HANDOFF.md) | The hand-over after each run; the top section is current |
| [PROGRESS.md](PROGRESS.md) | The timestamped log of every run, with each decision and how to reverse it |
| [RUN-2026-11-07-C.md](RUN-2026-11-07-C.md) | Run C: curriculum model, KYP import, sources, cleanup on DEV; status per definition-of-done item and decisions needed |
| [PLAN.md](PLAN.md) | The last run's plan and work-stream ownership |
| [PR_DESCRIPTION.md](PR_DESCRIPTION.md) | The pull request for `auto/knowledge-platform-20261102` → `main` |
| [audit.md](audit.md) | The September 2026 repository audit (the "AUDIT §n" references in tests) |
| [REGISTRY-INVENTORY.md](REGISTRY-INVENTORY.md) | The Drive registry inventory behind the content-crawl scope |
| [DOWNLOAD-DISABLED-FILES.md](DOWNLOAD-DISABLED-FILES.md) | The 49 curriculum files that can't be downloaded |
| [design/](design/) | Phase 0 design documents still cited as sources by `config/` and `eval/` |
| [decisions/](decisions/) | Decision records and plans that were proposed but not (yet) carried out |

## Timeline

### September 2026: the NP Autopilot map

- **2026-09-09:** first commit: taxonomy v2, `config/people.yaml`, and CLAUDE.md's rules.
- **Phase 0 (09-09/10):** a corpus census (374 sheets in 75 files) and a full row
  scan (153,793 rows, 2.54 M cells). Learner personal data and a payroll file
  were found and excluded. The master spreadsheet in the brief didn't exist, so
  the taxonomy was rebuilt from evidence.
- **Threshold audit (09-10):** two cut-offs were hiding correct answers. Since
  then, thresholds rank or warn and never exclude (CLAUDE.md §4).
- **2026-09-16:** pass 0 reads the live Drive folder (service account, `drive.readonly`).
- **2026-09-18:** server-side latency, median 2,252 ms → 44.3 ms warm; the cold
  start depends on the region (5.7 s in iad1, 0.8 s in icn1).
- **2026-09-20:** the registry inventory and six pre-crawl decisions; the content
  crawl is limited to 4 approved domains.
- **2026-09-29:** the layout moves from the browser (366 frames, about 6.4 s to
  settle) to projection time (migration 0021); the payload falls from 2.59 MB
  to a few hundred KB.
- **2026-09-30, the launch window:** production on `main` at migration 0021, with
  8,496 nodes, 12,189 edges and 3,707 layouts; `verify_migration` 54/54. `main`'s
  test baseline is 43 known failures (`docs/baseline-failures.txt`).

### November 2026: the knowledge platform (branch `auto/knowledge-platform-20261102`)

- **Runs 1–3 (11-02):** the `kb` schema (migrations 0022–0029) with RLS,
  versioning and an append-only audit log; the workspace at `/kb/`; the MCP server
  (21 tools) and the Claude plugin; a UI redesign.
- **Local rehearsal on a copy of production (11-03):** 5,741 records, 6,938
  relationships and 1,827 links imported; a second run created 0 (idempotent).
- **Run 5 (11-03):** parity with NP Autopilot's own rules, with no unexplained
  differences; owners from roles; a reversible legacy archive (874 records,
  restore exact); the scheduled sync; the DEV database (first import of 25,226
  units in 245 s, down from about 5 h, with set-based creation).
- **Run 6 (11-03/04):**
  - The `kb` schema becomes the single source of truth: the `/` map reads it
    through `web/lib/kb/npmap.py`.
  - Change propagation without Realtime: 26 operations, the slowest 2.55 s
    (limit 5 s), polling `/api/kb/changes` every 2.5 s.
  - Sync timing with the 10 s budget: no change 2.3 s; 100 changed rows 4.8 s;
    the full first import 43.2 s in 5 batches. Function `maxDuration` 15 → 60 s.
  - Data quality 29 s → 53 ms on the server (19.6 s → 0.88 s in the browser),
    with a trigram join that finds the same 2,954 pairs.
  - Archived graph 1.0–1.4 s → 0.16–0.23 s (edge indexes, migration 0034).
  - At 5,000 records the canvas graph took 13.8 s and ran at 1–2 FPS, which led
    to bundling and the hierarchy layout.
  - Graph memory: heap 9 → 165 MB became 6.0 → 9.6 MB over 50 openings; expand
    p95 48 ms; screens interactive in 0.26–0.74 s.
  - An independent audit found 19 issues (among them viewer 403s on Settings,
    the graph leak and tokens that never expired); all fixed.
  - Security sweep: IK accounts only, checked on every request; MCP tokens
    scoped, expiring and revocable.
  - **Permanent legacy deletion** (owner-approved), local and DEV: 946 records
    (42 domains, 904 modules), 3,844 relationships, 1,040 attachments and 1,133
    expertise links; migration 0037 keeps them out; the next sync created 0
    with 0 conflicts. Not run on production (GO_LIVE step 6).
  - Final verification: non-browser 1,336 passed with no new failures against
    `main`; browser tests one file at a time, all passing; the dashboard fits one
    screen at 1536×730 and 1920×1080.
- **Repository cleanup (11-04):** process logs moved here; outdated reports,
  screenshots and the archive folder removed; generated graph files untracked;
  documentation reorganised with diagrams ([docs/README.md](../README.md)).
