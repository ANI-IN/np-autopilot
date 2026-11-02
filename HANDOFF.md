# HANDOFF — knowledge platform, run 2 (demo → team-ready), 2026-11-02

1. Branch `auto/knowledge-platform-20261102`, pushed; **nothing merged to main, nothing deployed**; everything ran locally.
2. The KB workspace at `/kb/` is redesigned end to end on a documented design system (Inter, Lucide, one deep-blue accent, light/dark).
3. **Custom record types** with fields (12 kinds), placement rules and safe-change rules, enforced in the database (migration 0027).
4. **One-step New record**: placement with nested inline creates, relationships, links (Drive, UpLevel, GitHub…), people, tags and fields in one transaction.
5. Complete CRUD with an **Archived** page and typed-name permanent delete; bulk edit and bulk archive; undo on removals.
6. **Outline** (drag to reorder), **flags/reviews**, **templates**, **completeness**, **saved views**, optional **Realtime + presence**.
7. In-app **Guide** (`public/kb/guide.md`, one editable file) with screenshots of the real UI.
8. `scripts/verify_all.sh` now fails loudly (proven); a deploy guard proves the demo login can never ship.
9. Regression vs `main`: the same 43 pre-existing failures by name; **no new failures** (details below).
10. **D7 (real data) is BLOCKED**: there is no `backups/` folder. Two migrations to add to the list: **0027, 0028**.

## Open the app now

The local Supabase stack and the demo server are **running**.

- URL: **http://localhost:8765/local-login**
- Sign in: `demo-admin@interviewkickstart.com` / `ik-demo-local` (admin). Also
  `demo-editor@interviewkickstart.com` (editor) and
  `demo-contributor@interviewkickstart.com` (contributor), same password. These
  users exist only in the local Supabase; production keeps Google sign-in.
- Reset the demo data: `.venv/Scripts/python eval/kb_demo_seed.py`.
- Stop everything: docs/DEMO.md, "Stop".

## 5-minute leadership demo

1. **Dashboard (30 s).** Real numbers: records by type, completeness by course,
   what needs attention, who changed what.
2. **Outline (1 min).** Sidebar → Outline → Expand all: program › course › module ›
   week › live session, with link counts and completeness. Drag a module to
   reorder it. Hover a course → **Add** → Module (quick-add).
3. **One-step New record (1.5 min).** Press **c**. Type *Module*, name it, and
   under **Placement** type a course that does not exist → **Create course "…"**,
   then place that new course in a program. Add a relationship ("covers" → a new
   topic) and paste an UpLevel and a GitHub link: each is recognised with its
   icon. **Create**: everything appears at once; **Undo** is in the toast.
4. **Custom type (1 min).** Settings → Record types → **New record type**: "Case
   Study" with a required *Difficulty* (Easy, Medium, Hard) and *Minutes*. The
   form preview updates as you type. Create it, then New record → Case Study.
5. **Collaboration and safety (1 min).** Open the same record as demo-editor in a
   private window: "demo editor is viewing / is editing" appears live. Save in
   one window, then in the other → "This record changed since you opened it".
   Archive a record (it shows what goes with it) → **Archived** → Delete
   permanently (type the name).
6. **Guide (10 s).** Sidebar → Guide: what teammates read first.

## What changed (before → after)

Screenshots: `docs/redesign/before/<width>-<screen>.png` →
`docs/redesign/after/<width>-<screen>.png` at 1440, 1280 and 1024 (for example
`1440-dashboard.png`, `1440-records.png`, `1440-record-detail.png`,
`1440-graph.png`, `1440-outline.png`, `1440-new-record.png`,
`1440-type-editor.png`, `1024-record-detail.png`). Inventory with the before and
after CRUD matrices: `docs/INVENTORY.md`. Design system and the technology
decision: `docs/DESIGN_SYSTEM.md`.

## Status of every item

| Item | Status | Evidence |
|---|---|---|
| A1 trustworthy `verify_all.sh` | VERIFIED | set -euo pipefail; repo root from git, checked against the script's own checkout; every tool and path required; FAILS (exit 2) from a wrong cwd, a foreign repo, with a missing tool, a bad option, and a missing path (it caught the deleted `kb.js` before it was updated) |
| A2 regression vs `main` | VERIFIED | worktrees of both against the same stack: identical 43 failing names (= `docs/baseline-failures.txt`); docs/TEST_RESULTS.md |
| A3 leftovers deleted | VERIFIED | `main_results.txt`, `verify_main.sh` removed |
| B inventory | VERIFIED | docs/INVENTORY.md (before and after), 42 before screenshots + 6 dialogs |
| C1 design system + redesign | VERIFIED | docs/DESIGN_SYSTEM.md; every screen rebuilt; contrast computed from tokens; dark mode; no horizontal scroll at 1024px (10 screens, tested); every control has an accessible name (9 screens + the form, tested) |
| C2 custom types | VERIFIED | 0027 triggers; tests/test_kb_types.py (10); browser "Case Study" end to end (type → record → filter and field columns → ⌘K → CSV → graph); MCP `list_types` and create with props; Sheets import of custom fields; rule misfits on Data quality |
| C3 one-step New record | VERIFIED | tests/test_kb_workspace.py (11); browser: nested inline course, 2 relationships, 3 links (Drive, UpLevel, GitHub reused), rollback with the field highlighted, duplicate warning, disallowed pairs not offered, contributor proposal, draft restore and close confirmation, Undo, prefill from the open record |
| C4 complete CRUD + delete flow | VERIFIED | matrix in docs/INVENTORY.md; browser: archive → Archived → typed delete (audited); bulk owner, tag, status, placement, archive; undo on relationship and link removal |
| C5 Guide | VERIFIED | `public/kb/guide.md`; screenshots captured from the real UI; "How this works" links from empty states and forms; every step it describes is exercised by a browser test |
| D1 Outline | VERIFIED | browser: expand, drag reorder (persisted), quick-add; copy as text |
| D2 Realtime + presence | VERIFIED locally | tests/test_kb_realtime.py: two people, "is editing", update delivered over the socket in under 3 s; polling fallback exercised by the whole E2E suite (Realtime off there). Production needs owner step 5 |
| D3 Flag and review | VERIFIED | browser: a viewer flags → the owner sees "Assigned to you" → resolves; `flagged` filter |
| D4 Templates | VERIFIED | API and browser: save a course as a template → New record "Start from" → 3 records with name substitution, links not copied |
| D5 Completeness | VERIFIED | API tests; shown on the dashboard, outline, record and resource panels with what is missing |
| D6 Saved views | VERIFIED | browser: save, share, tab visible to another user; bulk owner change from the view |
| D7 Real-data rehearsal | **BLOCKED** | `backups/` does not exist. Unblock: place `backups/ik_workbook.xlsx` and/or `backups/prod_data.sql` (gitignored) and run D7 |
| D8 Deployment guard | VERIFIED | tests/test_deploy_guard.py (8): `.vercelignore`, function `excludeFiles`, routes, `public/`, shipped Python, prebuilt output, the Guide ships, the CSP origin script |

## Final verification

`bash scripts/verify_all.sh --fresh-clone --reset-db` (13:29–13:45): **VERIFY: ALL PASS**.

- Fresh clone of the branch → clean `uv` install → Python byte-compiles → all KB ES modules parse: PASS.
- `supabase db reset` → every migration 0001–0028 → KB rolled back to 0021 → re-applied: PASS
  (the projection step fails exactly as on `main`; pre-existing, docs/AUDIT.md).
- Lint, plugin copy in sync, `claude plugin validate --strict`, no server keys in `public/`,
  `.env` untracked, no secret-shaped strings in history, RLS on every kb table, deploy guard: PASS.
- Full suite: **1156 passed, 22 failed, 21 errors, 53 skipped**; all 43 failures/errors are the
  `main` baseline by name; **0 new**; all KB tests pass. (The Realtime test skipped there because
  the reset removed the demo users; it passes after reseeding: 1 passed.)
- KB tests by file: API 34, schema 16, RLS 11, concurrency 3, import 7, MCP 8, plugin 5,
  types 10, workspace 11, browser E2E 47, Realtime 1, deploy guard 8.

## New migrations to add to the dev → production list

Run 1 added 0022–0026. Run 2 adds:

- **0027_kb_custom_types**: type fields and rules, link kinds, flags, templates,
  saved views, proposals for creates and type changes; contributors' record
  INSERT tightened to editor (their creates become proposals).
- **0028_kb_palette_realtime**: non-purple type colours; `kb.audit_log` in the
  `supabase_realtime` publication.

Both are additive, and both downs refuse while data uses what they added. They
were tested on a fresh local database: `verify_all.sh --reset-db` applies every
migration from 0001, rolls the KB back to 0021 and re-applies.

## Decisions to review (PROGRESS.md D15–D24)

- **D19 contributors' creates are proposals**, enforced by RLS. This changes run
  1's role model (contributors created directly); editors approve in Approvals.
- **D17 vanilla ES modules**, no framework or build step.
- **D21 link kind vs resource kind**: where a link lives (Drive, UpLevel…) is
  separate from what it is (KYP slides, solution…).
- **D23 Realtime is opt-in** per deployment via `KB_REALTIME_ORIGIN`.
- **D18 accent**: no IK brand colour exists in the repo, so a deep blue.

## ACTION REQUIRED FROM OWNER

1. **Review the PR** `auto/knowledge-platform-20261102` → `main`. Nothing was merged.
2. **Apply migrations 0022–0028 to the dev Supabase project**, backup first:
   ```bash
   export SUPABASE_DB_URL_SESSION=<dev session pooler URL>
   mkdir -p backups && pg_dump "$SUPABASE_DB_URL_SESSION" --schema=public --schema=kb > backups/pre-kb-$(date +%F).sql
   python pipeline/migrate.py status && python pipeline/migrate.py up
   ```
   Then production the same way after a dev smoke test. Rollback:
   `python pipeline/migrate.py down --to 0021`.
3. **Bootstrap admins**: each signs in once at `/`, then
   `ADMIN_EMAILS=a@interviewkickstart.com,b@… python pipeline/kb_admins.py`.
4. **Vercel preview** of the branch pointed at the dev database; open `/kb/`.
5. **Optional live updates**: run
   `KB_REALTIME_ORIGIN=https://<ref>.supabase.co python scripts/kb_csp_origin.py`,
   commit the vercel.json change, and set the same `KB_REALTIME_ORIGIN` in the
   Vercel project (docs/DEPLOYMENT.md). Without it the app polls.
6. **Sheets import**: share the workbook read-only with the service account; dry
   run `KB_SHEETS_ID=<id> NP_DRIVE_SA_KEY=<path> python pipeline/kb_import_sheets.py --as you@… --report /tmp/dry.json`;
   adjust `config/kb-sheets-mapping.yaml` (it can now fill custom fields with `props:`).
7. **D7**: provide `backups/ik_workbook.xlsx` and/or `backups/prod_data.sql` (kept
   local, gitignored) for the real-data rehearsal.
8. **Brand colour**: if IK has an official accent, replace `--accent` in `public/kb/kb.css`.

## How to run

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt
npx -y supabase@2.118.0 start --workdir db/local
python pipeline/migrate.py up                # through 0028
python eval/kb_demo_seed.py                  # demo users + fictional data
python eval/kb_demo_server.py 8765           # http://localhost:8765/local-login
bash scripts/verify_all.sh [--fresh-clone] [--reset-db] [--perf]
```
MCP: docs/MCP.md (now with `list_types`); plugin `ik-knowledge-assistant` 0.2.0.
Run 1's handoff (M1–M10) is in git history (commit 597b0e1 and earlier).
