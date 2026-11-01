#!/usr/bin/env bash
# Phase-4 verification for the KB knowledge platform — re-runnable, LOCAL ONLY.
#
#   scripts/verify_all.sh                 # verify this checkout against the local stack
#   scripts/verify_all.sh --fresh-clone   # also: clean clone of the current branch → install → build checks
#   scripts/verify_all.sh --reset-db      # also: wipe the LOCAL Supabase DB and apply every migration from 0001
#   scripts/verify_all.sh --perf          # also: seed 5k/15k synthetic and measure p50/p95
#
# Needs: Docker + the local Supabase stack (db/local/setup.sh), Python 3.12 + uv,
# Node (syntax check only), Chrome or `playwright install chromium`.
# Refuses to run if the configured database is not the loopback local stack.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
FRESH=0; RESET=0; PERF=0
for a in "$@"; do case "$a" in --fresh-clone) FRESH=1;; --reset-db) RESET=1;; --perf) PERF=1;; esac; done

PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$REPO/.venv/Scripts/python"
export SUPABASE_DB_URL_SESSION="${SUPABASE_DB_URL_SESSION:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
export SUPABASE_DB_URL_TRANSACTION="${SUPABASE_DB_URL_TRANSACTION:-postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres}"
case "$SUPABASE_DB_URL_SESSION" in
  *@127.0.0.1:*|*@localhost:*) ;;
  *) echo "REFUSED: verify_all.sh runs against the local stack only"; exit 2;;
esac

FAIL=0
step() { echo; echo "=== $* ==="; }
ok()   { echo "PASS  $*"; }
bad()  { echo "FAIL  $*"; FAIL=1; }

if [ $FRESH -eq 1 ]; then
  step "fresh clone of $(git rev-parse --abbrev-ref HEAD) → clean install → build checks"
  TMP="$(mktemp -d)"
  git clone -q --branch "$(git rev-parse --abbrev-ref HEAD)" "$REPO" "$TMP/clone" || bad "clone"
  ( cd "$TMP/clone" && uv venv -q .venv -p 3.12 && uv pip install -q -p .venv -r requirements.txt ) && ok "clean install" || bad "clean install"
  CPY="$TMP/clone/.venv/bin/python"; [ -x "$CPY" ] || CPY="$TMP/clone/.venv/Scripts/python"
  "$CPY" -m compileall -q "$TMP/clone/api" "$TMP/clone/web" "$TMP/clone/mcp_server" "$TMP/clone/pipeline" >/dev/null && ok "python byte-compiles" || bad "compileall"
  node --check "$TMP/clone/public/kb/kb.js" && ok "kb.js parses" || bad "kb.js syntax"
  rm -rf "$TMP"
fi

if [ $RESET -eq 1 ]; then
  step "fresh local database: reset, apply every migration, seed users"
  npx -y supabase@2.118.0 db reset --workdir db/local --yes >/dev/null 2>&1 || bad "supabase db reset"
  "$PY" pipeline/migrate.py up | tail -1 || bad "migrate up"
  # The rest of db/local/setup.sh's seeding, so the regression comparison is
  # like-for-like. (The projection step fails on main too — baseline, see HANDOFF.)
  NP_FRESHNESS_SKIP="local verification, never production" NP_LANDING_STATS="$(mktemp)" NP_BUILD_LOG="$(mktemp)"     "$PY" pipeline/project_graph.py >/dev/null 2>&1 || echo "  (projection failed — pre-existing, see docs/AUDIT.md)"
  "$PY" pipeline/curation.py import >/dev/null || bad "curation import"
  "$PY" -c "import os,psycopg; c=psycopg.connect(os.environ['SUPABASE_DB_URL_SESSION'],autocommit=True); c.execute(\"insert into auth.users (id,email,created_at) select gen_random_uuid(),'b2c-courses-new-programs@interviewkickstart.com',now() where not exists (select 1 from auth.users where lower(email)='b2c-courses-new-programs@interviewkickstart.com')\")" || bad "shared account seed"
  "$PY" pipeline/migrate.py down --to 0021 | tail -1 && "$PY" pipeline/migrate.py up | tail -1 \
    && ok "kb migrations roll back and re-apply" || bad "kb migration round trip"
fi

step "static checks"
node --check public/kb/kb.js && ok "kb.js parses" || bad "kb.js syntax"
uvx -q ruff@0.14.0 check --select E9,F --target-version py312 web/lib/kb api/kb_routes.py api/index.py \
  mcp_server pipeline/kb_import_sheets.py pipeline/kb_admins.py pipeline/lib/kb_sheets.py \
  eval/kb_dev_server.py scripts/kb_perf.py tests/kb_support.py tests/test_kb_*.py \
  && ok "ruff (errors + pyflakes) on KB code" || bad "ruff"
cmp -s mcp_server/kb_server.py plugins/ik-knowledge-assistant/server/kb_server.py && ok "plugin server copy in sync" || bad "plugin server copy drifted"
if command -v claude >/dev/null; then
  claude plugin validate plugins/ik-knowledge-assistant --strict >/dev/null 2>&1 && ok "plugin validates (--strict)" || bad "plugin validate"
fi

step "security spot checks"
if grep -rInE 'SERVICE_ROLE|service_role|SUPABASE_JWT_SECRET|ANTHROPIC_API_KEY|eyJhbGciOi' public/ >/dev/null; then bad "a server-only key name or JWT is in public/"; else ok "no server key names in the browser bundle"; fi
git ls-files --error-unmatch .env >/dev/null 2>&1 && bad ".env is tracked" || ok ".env is not tracked"
if git log -p | grep -qE 'sk-ant-[A-Za-z0-9]|-----BEGIN (RSA )?PRIVATE KEY|ikkb_[A-Za-z0-9_-]{30,}'; then bad "a secret-shaped string is in git history"; else ok "no secret-shaped strings in history"; fi
"$PY" - <<'EOF' && ok "RLS enabled on every kb table, policies present" || bad "RLS check"
import os, psycopg, sys
with psycopg.connect(os.environ["SUPABASE_DB_URL_SESSION"]) as c:
    off = c.execute("select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                    "where n.nspname='kb' and c.relkind='r' and not c.relrowsecurity").fetchall()
    nopol = c.execute("select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                      "where n.nspname='kb' and c.relkind='r' and not exists "
                      "(select 1 from pg_policies p where p.schemaname='kb' and p.tablename=c.relname)").fetchall()
    print("  kb tables without RLS:", off, " without policies:", nopol)
    sys.exit(1 if off or nopol else 0)
EOF

step "full test suite (local DB, browser E2E, MCP, concurrency)"
LOG="$(mktemp)"
"$PY" -m pytest tests -q -p no:cacheprovider > "$LOG" 2>&1
tail -1 "$LOG"
grep -E '^(FAILED|ERROR)' "$LOG" | sed 's/ - .*//' | sort > "$LOG.fail"
KBFAIL=$(grep -c 'test_kb_' "$LOG.fail" || true)
[ "$KBFAIL" = "0" ] && ok "all KB tests pass" || { bad "$KBFAIL KB test(s) failed"; grep test_kb_ "$LOG.fail"; }
if [ -f docs/baseline-failures.txt ]; then
  NEW=$(comm -13 docs/baseline-failures.txt "$LOG.fail" | grep -v test_kb_ || true)
  [ -z "$NEW" ] && ok "no regressions against the pre-run baseline (docs/baseline-failures.txt)" \
    || { bad "new failures vs baseline:"; echo "$NEW"; }
fi

if [ $PERF -eq 1 ]; then
  step "performance (synthetic 5,000 nodes / 15,000 edges)"
  "$PY" scripts/kb_perf.py --runs 40 | grep -v '"audit"'
fi

echo
[ $FAIL -eq 0 ] && echo "VERIFY: ALL PASS" || echo "VERIFY: FAILURES ABOVE"
exit $FAIL
