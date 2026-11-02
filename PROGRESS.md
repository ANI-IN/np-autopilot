# PROGRESS — autonomous run

T0 = Mon 2026-11-02 02:58 (local clock). Mode: **DEGRADED** (no Supabase dev
project, Google, LLM or Vercel credentials in the environment; local Supabase stack
via Docker used for everything).

## Log

- [T+0:00] Phase 0 start. Cloned, branch `auto/knowledge-platform-20261102`. Python 3.12 + uv,
  Node 26, Docker 29 (daemon started), Supabase CLI via npx (pinned 2.118.0), Chrome present.
- [T+0:03] Credentials (presence only): all Supabase/Google/Anthropic/Vercel vars missing → DEGRADED.
- [T+0:08] Baseline (no DB): 892 pass / 12 fail / 187 skip — all 12 are Windows-environment failures.
- [T+0:12] Local DB seeded; `project_graph.py` FAILS on a fresh DB (`corpus_names_a_file`) — pre-existing.
- [T+0:15] M1+M2 done | tests: 27 pass / 0 fail | VERIFIED | kb schema 0022, RLS 0023
- [T+0:18] Baseline (DB, main): 998 pass / 22 fail / 21 error / 50 skip → docs/baseline-failures.txt
- [T+0:18] M3 done | tests: 29 pass / 0 fail | VERIFIED | service + /api/kb
- [T+0:34] M4-M6 done | tests: 13 E2E pass / 0 fail | VERIFIED | UI, conflict dialog, graph
- [T+0:36] M7 done | tests: 3 pass / 0 fail | VERIFIED | 20 parallel creates 283 ms, no dupes/orphans
- [T+0:39] M8 done | tests: 6 pass / 0 fail | VERIFIED (fixture) / live Sheets UNTESTED (no creds)
- [T+0:45] M9 done | tests: 6 pass / 0 fail | VERIFIED incl. live `claude -p` retrieval through the server
- [T+0:48] M10 done | `claude plugin validate --strict` pass, 5 tests | VERIFIED
- [T+0:55] Stretch: data-quality dashboard + CSV export (tests pass). E2E now runs under production CSP.
- [T+1:00] Perf (5,000 nodes / 15,000 edges): see docs/TEST_RESULTS.md.
- [T+1:05] Phase 4: verify_all.sh — clone, reset-DB migrations, lint, plugin, security, RLS all PASS; full-suite step stopped by the low-memory reaper (not re-run, per the reaper notice). Handoff written.
- [re-run] `bash scripts/verify_all.sh`: full suite 1089 pass / 22 fail / 21 error / 50 skip — all failures baseline, no regressions, VERIFY: ALL PASS.
- [demo, 2026-11-02] Local demo: migration 0026 (domain/week/session types,
  resource kinds, kb.link_checks, kb.people()), owner shown and editable in the
  record panel, Data quality lists unowned records and broken links, demo server
  with a local-only sign-in page, re-runnable fictional seed. Fixed: Settings →
  Roles showed other members as uuids (profiles are self-only under RLS); the
  tests' reset() left kb.import_runs behind, failing the import test on a re-run.
  KB tests: 95 pass, incl. 14 browser E2E.

- [run 2 T+0:00 11:44] Run 2 start (demo -> team-ready). docs/SPEC.md absent; backups/ absent.
- [T+0:10] A1 verify_all.sh rewritten (set -euo pipefail, git root, every tool/path/exit checked) | proven: wrong cwd, foreign repo, missing tool, bad option all FAIL (exit 2) | VERIFIED
- [T+0:10] A3 main_results.txt, verify_main.sh deleted | VERIFIED
- [T+0:12] D8 tests/test_deploy_guard.py (6 tests: .vercelignore, excludeFiles, routes, public/, shipped python, prebuilt output) | 6 pass | VERIFIED
- [T+0:20] A2 main vs branch by failing NAME: identical 43 = baseline; branch +95 passes, 0 new failures | VERIFIED
- [T+0:20] B inventory: docs/INVENTORY.md, 42 before screenshots (1440/1280/1024) + 6 dialogs | VERIFIED
- [T+0:30 12:14] Backend for C2/C3/C4/D1/D3-D6 (0027, typedefs.py, workspace.py, routes, MCP list_types) | 108 KB API tests pass (+21 new) | VERIFIED (API); UI next. Commit 11633a1
- [T+1:25 13:10] C1 redesign (tokens, components, every screen rebuilt as ES modules; Inter + Lucide self-hosted), C3 one-step New record sheet, C4 UI (Archived, typed delete, bulk bar, undo), C5 Guide page, D1 Outline, D2 Realtime client + presence (polling fallback), D3 flags UI, D4 templates UI, D5 completeness UI, D6 saved views | E2E 32/32 twice (14 updated + 18 new) | VERIFIED; 0028 palette + realtime publication

## Decisions

- D1. APPENDIX was not pasted (placeholder only). The wrapper's must-ship list is the spec.
- D2. Repo is Python + static HTML, not a JS framework → vanilla JS UI, Cytoscape, Python MCP SDK
  (PLAN.md "Adaptation").
- D3. Authored knowledge in a new `kb` schema; the projection (`public.nodes`, rebuilt per build)
  is untouched → the live app cannot break.
- D4. Did NOT read `~/Desktop/Keys.txt` or the Desktop DB-URL file: outside the repo, not offered
  for this run, and the URL is the production pooler by its name.
- D5. Auth: kept production Google SSO (already domain-restricted). Did not add email/password
  login: it would weaken the verified-`hd` model. Local tests use real HS256 verification with a
  test-only secret.
- D6. Realtime → RLS-scoped change feed polled every 4 s (CSP `connect-src 'self'`, no
  supabase-js). Realtime + presence → ROADMAP.
- D7. MCP server is an HTTP client of /api/kb with per-user `ikkb_` tokens (migration 0025 lets
  `authenticated` call the definer function) — no DB credential on user machines.
- D8. Skills live in `plugins/ik-knowledge-assistant/skills/`, NOT repo-root `skills/`: the repo
  root is the `np-autopilot` plugin (marketplace source `./`), which would auto-load root skills.
- D9. Courses/programs are container node types; resources a separate many-to-many table.
- D10. Import duplicates against app records are flagged, never adopted automatically.
- D11. Test users are `kbtest-<role>@interviewkickstart.com` (not `synthetic-…`, which
  `test_role_boundary` counts).

- D12. Demo sign-in is a page in the eval/ demo server (never deployed), using the
  LOCAL Supabase Auth's password grant; tokens are then verified by the
  production code path. No change to production login.
- D13. Link health is checked by the client (MCP `check_broken_links`) and only
  RECORDED by the server (`POST /quality/link-results`, editor+). The server
  never fetches user-supplied URLs (no SSRF surface on Vercel).
- D14. Link results live in `kb.link_checks`, not on `kb.resources`, so a check
  never bumps a resource's version and causes a spurious edit conflict.

- D15. docs/SPEC.md does not exist in the repo; the run-2 brief is the specification.
- D16. backups/ does not exist (it is gitignored) -> D7 real-data rehearsal BLOCKED.
- D17. Frontend stays vanilla JS with no build step, split into ES modules (CSP script-src 'self'
  allows same-origin modules). A framework would add a toolchain the repo and Vercel setup do
  not have, for a UI of ~10 screens; see docs/DESIGN_SYSTEM.md.
- D18. No IK brand colour is recorded anywhere in the repo -> restrained deep blue accent.
- D19. Contributors' record creates become proposals (brief C3). Enforced in the database:
  0027 tightens kb.nodes INSERT to editor+. Contributors still edit, connect and attach.
- D20. UpLevel link kind uses uplevel.interviewkickstart.com, found in the repo's own data
  (tests/test_source_links.py, docs/ACCEPTANCE-CHECKLIST.md), not guessed.
- D21. Link kind (the service: Drive, GitHub, UpLevel...; configurable, URL-pattern detected)
  and resource kind (what it is: KYP slides, recording, solution...) are separate dimensions.

- D22. Hover actions fade by opacity, not visibility, so they stay keyboard-reachable.
- D23. Realtime is opt-in per deployment: /api/kb/realtime returns a socket config only when
  KB_REALTIME_ORIGIN (the origin also in the CSP connect-src) is set; otherwise the page polls.
  The local demo derives the origin from `supabase status`.
- D24. Type colours: one accessible, non-purple palette (0028 moved the seeded colours; admin
  choices are kept). Dark mode lightens icon colours with color-mix for contrast.

## Blockers (each with the unblock step) — see HANDOFF.md "Action required"

- Live Sheets import: needs `KB_SHEETS_ID` + `NP_DRIVE_SA_KEY` with the sheet shared read-only.
- Shared DB migration: needs a dev Supabase project URL (SUPABASE_ENV=dev) or owner-run commands.
- Vercel preview: needs VERCEL_TOKEN or the Git integration on this branch.
