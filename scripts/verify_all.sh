#!/usr/bin/env bash
# Phase-4 verification for the KB knowledge platform — re-runnable, LOCAL ONLY.
#
#   bash scripts/verify_all.sh                 # verify this checkout against the local stack
#   bash scripts/verify_all.sh --fresh-clone   # also: clean clone of the current branch -> install -> build checks
#   bash scripts/verify_all.sh --reset-db      # also: wipe the LOCAL Supabase DB, apply every migration from 0001
#   bash scripts/verify_all.sh --perf          # also: seed 5k/15k synthetic and measure p50/p95
#   bash scripts/verify_all.sh --load          # also: 25 simulated people for 2 minutes (conflicts, races, audit check)
#   bash scripts/verify_all.sh --skip-browser  # the suite without the 6 Playwright files: on a 16 GB laptop run
#                                              # those one file at a time (docs/operations/testing.md §3)
#
# Run from inside the repository (any subdirectory). Needs: git, Docker + the local
# Supabase stack (db/local/setup.sh), the .venv (Python 3.12), uv/uvx, Node, and the
# claude CLI (plugin validation). Works under Git Bash on Windows.
#
# TRUSTWORTHY BY CONSTRUCTION: a check PASSES only when its command ran and exited
# 0. A missing tool, a missing path, a repo root that is not this repository, or a
# command that could not run is a FAIL, never a silent skip. The previous version
# reported PASS for `cmd && ok || bad` chains whose tools were absent.
set -euo pipefail

FAIL=0
step() { printf '\n=== %s ===\n' "$*"; }
ok()   { printf 'PASS  %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; FAIL=1; }
die()  { printf 'FAIL  %s\nVERIFY: ABORTED\n' "$*"; exit 2; }

# esm_check DIR -> node --check every ES module under DIR (copied to .mjs: node
# parses a plain .js file as CommonJS, where `import` is a syntax error).
esm_check() {
  local dir="$1" tmp f n=0
  tmp="$(mktemp -d)"
  for f in "$dir"/js/*.js "$dir"/js/views/*.js; do
    [ -e "$f" ] || continue
    n=$((n + 1)); cp "$f" "$tmp/$n.mjs"
    node --check "$tmp/$n.mjs" || { echo "syntax error in $f"; rm -rf "$tmp"; return 1; }
  done
  rm -rf "$tmp"
  [ "$n" -gt 0 ] || { echo "no modules under $dir/js"; return 1; }
  echo "$n modules parse"
}

# check "<label>" cmd args...   -> PASS iff the command exits 0 (output shown on failure)
check() {
  local label="$1"; shift
  local out rc=0
  out="$("$@" 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ]; then ok "$label"; else bad "$label (exit $rc)"; printf '%s\n' "$out" | tail -20; fi
}
need_tool() { command -v "$1" >/dev/null 2>&1 || die "required tool not found on PATH: $1"; }
need_path() { [ -e "$REPO/$1" ] || die "required path missing: $1"; }

# --- repository root ---------------------------------------------------------
need_tool git
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "not inside a git repository (cwd: $(pwd)); run from the np-autopilot checkout"
SCRIPT_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# Compare physical paths (Git Bash may spell the same folder /c/... vs C:/...).
if [ "$(cd "$REPO" && pwd -P)" != "$SCRIPT_REPO" ]; then
  die "repo root resolves to $REPO, but this script lives in $SCRIPT_REPO; run it from inside that checkout"
fi
cd "$REPO"
for p in api/index.py web/lib/kb/service.py public/kb/js/app.js public/kb/guide.md db/migrations tests docs/baseline-failures.txt \
         mcp_server/kb_server.py plugins/ik-knowledge-assistant/server/kb_server.py; do
  need_path "$p"
done

FRESH=0; RESET=0; PERF=0; LOAD=0; NOBROWSER=0
for a in "$@"; do
  case "$a" in
    --fresh-clone) FRESH=1;; --reset-db) RESET=1;; --perf) PERF=1;; --load) LOAD=1;;
    --skip-browser) NOBROWSER=1;;
    *) die "unknown option: $a";;
  esac
done

for t in node uvx; do need_tool "$t"; done
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$REPO/.venv/Scripts/python.exe"
[ -x "$PY" ] || die "no virtualenv python at .venv/ (uv venv .venv -p 3.12 && uv pip install -p .venv -r requirements.txt)"
need_tool claude

export SUPABASE_DB_URL_SESSION="${SUPABASE_DB_URL_SESSION:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
export SUPABASE_DB_URL_TRANSACTION="${SUPABASE_DB_URL_TRANSACTION:-postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres}"
case "$SUPABASE_DB_URL_SESSION" in
  *@127.0.0.1:*|*@localhost:*) ;;
  *) die "REFUSED: verify_all.sh runs against the local stack only";;
esac
"$PY" -c "import os, psycopg; psycopg.connect(os.environ['SUPABASE_DB_URL_SESSION'], connect_timeout=5).close()" \
  >/dev/null 2>&1 || die "local database unreachable at 127.0.0.1:54322 (npx -y supabase@2.118.0 start --workdir db/local)"

if [ "$FRESH" -eq 1 ]; then
  step "fresh clone of $(git rev-parse --abbrev-ref HEAD) -> clean install -> build checks"
  need_tool uv
  TMP="$(mktemp -d)"
  check "clone" git clone -q --branch "$(git rev-parse --abbrev-ref HEAD)" "$REPO" "$TMP/clone"
  if [ -d "$TMP/clone" ]; then
    check "clean install (uv venv + requirements)" bash -c "cd '$TMP/clone' && uv venv -q .venv -p 3.12 && uv pip install -q -p .venv -r requirements.txt"
    CPY="$TMP/clone/.venv/bin/python"; [ -x "$CPY" ] || CPY="$TMP/clone/.venv/Scripts/python.exe"
    if [ -x "$CPY" ]; then
      check "python byte-compiles" "$CPY" -m compileall -q "$TMP/clone/api" "$TMP/clone/web" "$TMP/clone/mcp_server" "$TMP/clone/pipeline" "$TMP/clone/eval"
    else
      bad "fresh clone has no venv python"
    fi
    check "KB ES modules parse (clone)" esm_check "$TMP/clone/public/kb"
  fi
  rm -rf "$TMP"
fi

if [ "$RESET" -eq 1 ]; then
  step "fresh local database: reset, apply every migration, seed users"
  need_tool npx
  check "supabase db reset" npx -y supabase@2.118.0 db reset --workdir db/local --yes
  check "migrate up" "$PY" pipeline/migrate.py up
  # The projection step fails on main too (pre-existing, docs/project-history/audit.md); report, do not gate.
  if NP_FRESHNESS_SKIP="local verification, never production" NP_LANDING_STATS="$(mktemp)" NP_BUILD_LOG="$(mktemp)" \
       "$PY" pipeline/project_graph.py >/dev/null 2>&1; then ok "projection loads"; else echo "  NOTE projection failed (pre-existing on main, docs/project-history/audit.md)"; fi
  check "curation import" "$PY" pipeline/curation.py import
  check "kb migrations roll back to 0021" "$PY" pipeline/migrate.py down --to 0021
  check "kb migrations re-apply" "$PY" pipeline/migrate.py up
fi

step "static checks"
check "KB ES modules parse" esm_check public/kb
check "ruff (errors + pyflakes) on KB code" uvx -q ruff@0.14.0 check --select E9,F --target-version py312 \
  web/lib/kb api/kb_routes.py api/index.py mcp_server pipeline/kb_import_sheets.py pipeline/kb_admins.py \
  pipeline/lib/kb_sheets.py eval/kb_dev_server.py eval/kb_demo_server.py eval/kb_demo_seed.py \
  eval/kb_local_stack.py scripts/kb_perf.py scripts/kb_load.py scripts/kb_explain.py scripts/kb_graph_perf.py \
  scripts/kb_guide_shots.py scripts/deploy_bundle_size.py eval/kb_ui_sweep.py pipeline/kb_import_projection.py eval/kb_realdata_db.py \
  eval/kb_realdata_server.py eval/kb_realdata_check.py tests/kb_support.py tests/test_kb_*.py tests/test_db_pooling.py \
  pipeline/kb_legacy.py eval/kb_parity.py eval/kb_sync_proof.py scripts/dev_db.py eval/kb_screens.py
check "plugin server copy in sync" cmp mcp_server/kb_server.py plugins/ik-knowledge-assistant/server/kb_server.py
check "plugin validates (--strict)" claude plugin validate plugins/ik-knowledge-assistant --strict

step "security spot checks"
if grep -rInE 'SERVICE_ROLE|service_role|SUPABASE_JWT_SECRET|ANTHROPIC_API_KEY|eyJhbGciOi' public/ >/dev/null; then
  bad "a server-only key name or JWT is in public/"; else ok "no server key names in the browser bundle"; fi
if git ls-files --error-unmatch .env >/dev/null 2>&1; then bad ".env is tracked"; else ok ".env is not tracked"; fi
HIST="$(mktemp)"
git log -p > "$HIST" || die "git log failed"
[ -s "$HIST" ] || die "git log produced no output"
if grep -qE 'sk-ant-[A-Za-z0-9]|-----BEGIN (RSA )?PRIVATE KEY|ikkb_[A-Za-z0-9_-]{30,}' "$HIST"; then
  bad "a secret-shaped string is in git history"; else ok "no secret-shaped strings in history"; fi
rm -f "$HIST"
check "RLS enabled on every kb table, policies present" "$PY" - <<'EOF'
import os, psycopg, sys
with psycopg.connect(os.environ["SUPABASE_DB_URL_SESSION"]) as c:
    n = c.execute("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                  "where n.nspname='kb' and c.relkind='r'").fetchone()[0]
    off = c.execute("select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                    "where n.nspname='kb' and c.relkind='r' and not c.relrowsecurity").fetchall()
    nopol = c.execute("select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                      "where n.nspname='kb' and c.relkind='r' and not exists "
                      "(select 1 from pg_policies p where p.schemaname='kb' and p.tablename=c.relname)").fetchall()
    print("kb tables:", n, "without RLS:", off, "without policies:", nopol)
    sys.exit(1 if n == 0 or off or nopol else 0)
EOF
check "deploy guard: eval/ and tests/ never ship" "$PY" -m pytest -q -p no:cacheprovider tests/test_deploy_guard.py

step "full test suite (local DB, browser E2E, MCP, concurrency)"
LOG="$(mktemp)"
rc=0
# --color=no: with colour codes the FAILED/ERROR lines below would not match and a
# failing suite would compare as "no new failures".
IGNORE=()
if [ "$NOBROWSER" = 1 ]; then
  # Every file that drives a browser. Not a skip: they are reported as NOT RUN
  # below and must be run on their own, one file at a time.
  for f in $(grep -lE "playwright|page_as|chromium" tests/*.py); do IGNORE+=("--ignore=$f"); done
  echo "  NOTE: --skip-browser: NOT RUN here, run each on its own: ${IGNORE[*]//--ignore=/}"
fi
"$PY" -m pytest tests -q -p no:cacheprovider -rfE --color=no "${IGNORE[@]}" > "$LOG" 2>&1 || rc=$?
tail -1 "$LOG"
# pytest: 0 all passed, 1 some failed — anything else means the suite did not run properly.
if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
  bad "pytest could not run the suite (exit $rc)"; tail -30 "$LOG"
elif ! grep -qE '[0-9]+ passed' "$LOG"; then
  bad "pytest reported no passing tests"; tail -30 "$LOG"
else
  { grep -E '^(FAILED|ERROR) ' "$LOG" || true; } | sed 's/ - .*//' | LC_ALL=C sort -u > "$LOG.fail"
  # A summary that reports failures must yield their names, or the comparison is meaningless.
  if grep -qE '[0-9]+ (failed|error)' "$LOG" && [ ! -s "$LOG.fail" ]; then
    bad "pytest reported failures but none could be read by name"; tail -5 "$LOG"
  fi
  KBFAIL="$(grep -c 'test_kb_' "$LOG.fail" || true)"
  if [ "$KBFAIL" = "0" ]; then ok "all KB tests pass"; else bad "$KBFAIL KB test(s) failed"; grep test_kb_ "$LOG.fail"; fi
  LC_ALL=C sort -u docs/baseline-failures.txt > "$LOG.base"
  NEW="$(LC_ALL=C comm -13 "$LOG.base" "$LOG.fail")"
  if [ -z "$NEW" ]; then ok "no failures beyond the main baseline (docs/baseline-failures.txt, $(wc -l < "$LOG.base") entries)"
  else bad "new failures vs the main baseline:"; printf '%s\n' "$NEW"; fi
  FIXED="$(LC_ALL=C comm -23 "$LOG.base" "$LOG.fail" | wc -l)"
  echo "  baseline failures now passing: $FIXED"
fi
rm -f "$LOG" "$LOG.fail" "$LOG.base"

if [ "$PERF" -eq 1 ]; then
  step "performance (synthetic 5,000 nodes / 15,000 edges)"
  check "perf run" "$PY" scripts/kb_perf.py --runs 40
fi

if [ "$LOAD" -eq 1 ]; then
  step "concurrency: 25 simulated people, 2 minutes"
  check "load run (no duplicates, no orphans, every conflict a 409, audit = writes, no 5xx)" "$PY" scripts/kb_load.py --users 25 --seconds 120
fi

echo
if [ "$FAIL" -eq 0 ]; then echo "VERIFY: ALL PASS"; else echo "VERIFY: FAILURES ABOVE"; fi
exit "$FAIL"
