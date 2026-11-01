# PROGRESS — autonomous run

T0 = Mon 2026-11-02 02:58 (local clock).

## Log

- [T+0:00] Phase 0 start. Cloned, branch `auto/knowledge-platform-20261102`. Python 3.12 + uv,
  Node 26, Docker 29 (daemon started), Supabase CLI via npx (pinned 2.118.0 in db/local/setup.sh),
  Chrome present (Playwright uses channel=chrome, no browser download).
- [T+0:03] Credentials (presence only): every Supabase/Google/Anthropic/Vercel variable MISSING
  from the environment → **DEGRADED MODE**. Local Supabase stack starting (realtime enabled in
  the local config only).

## Decisions

- D1. APPENDIX was not pasted (placeholder text only). The wrapper's must-ship list is the spec.
- D2. The repo is Python + static HTML, not a JS framework. See PLAN.md "Adaptation" table.
- D3. Authored knowledge lives in a new `kb` schema; the pipeline projection (`public.nodes`,
  replaced wholesale per build) is not touched, so the live Vercel app cannot break.
- D4. Did NOT read `~/Desktop/Keys.txt` or the Desktop DB-URL file. They are outside the repo,
  were not offered for this run, and the DB URL is the production session pooler by its name.
  Production is read-only for this run regardless; nothing needed it.

## Blockers

(none yet)
