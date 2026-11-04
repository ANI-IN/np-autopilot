#!/usr/bin/env bash
# The local test database: the Supabase CLI stack, brought to production's shape.
#
# Supabase's own Postgres image, auth schema (GoTrue's migrations), roles and
# RLS — so a DB test that passes here says something true about production. It
# is NOT a copy of production's DATA: no real identities, and the projection is
# whatever knowledge/ holds now. Tests that assert on production's own rows are
# marked production_only and skip here.
#
# Every URL below is the stack's fixed local default; nothing here can reach
# production, and tests/conftest.py refuses a production DSN regardless.
#
#   db/local/setup.sh          # start (first run pulls ~2 GB of images), then seed
#   db/local/setup.sh --stop   # stop; data is kept in the Docker volume
#
# Needs Docker (here: `colima start`) and Node for npx. docs/operations/testing.md §1.
set -euo pipefail

CLI="npx -y supabase@2.118.0"          # PINNED. Change deliberately, and re-run the suite.
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SESSION="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
TRANSACTION="postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres"
SHARED="b2c-courses-new-programs@interviewkickstart.com"

if [[ "${1:-}" == "--stop" ]]; then
    exec $CLI stop --workdir "$HERE"
fi

$CLI start --workdir "$HERE" | grep -viE 'key|secret|jwt|token' || true

cd "$REPO"
# The repo's own virtualenv if there is one (a Windows venv has no python3),
# else python3. Override with PYTHON=...
if [[ -n "${PYTHON:-}" ]]; then PY="$PYTHON"
elif [[ -x .venv/Scripts/python.exe ]]; then PY=.venv/Scripts/python.exe
elif [[ -x .venv/bin/python ]]; then PY=.venv/bin/python
else PY=python3; fi
export SUPABASE_DB_URL_SESSION="$SESSION" SUPABASE_DB_URL_TRANSACTION="$TRANSACTION"
scratch="$(mktemp -d)"
"$PY" pipeline/migrate.py up
# ALWAYS redirect these two, or a local projection overwrites public/stats.json
# and BUILD_LOG.md, which describe production. The freshness gate guards
# production projections; this one only ever writes the loopback stack above
# (the same override scripts/verify_all.sh and tests/conftest.py use).
NP_FRESHNESS_SKIP="local stack setup (db/local/setup.sh), never production" \
NP_LANDING_STATS="$scratch/stats.json" NP_BUILD_LOG="$scratch/BUILD_LOG.md" \
    "$PY" pipeline/project_graph.py
"$PY" pipeline/curation.py import
# The shared team mailbox, so the 0014 shared-account tests exercise the
# derivation instead of skipping. A bare auth.users row, as GoTrue would write;
# 0015's trigger gives it its member profile.
"$PY" - "$SESSION" "$SHARED" <<'PYEOF'
import sys, psycopg
with psycopg.connect(sys.argv[1], autocommit=True) as c:
    c.execute("""insert into auth.users (id, email, created_at)
                 select gen_random_uuid(), %(e)s::text, now()
                 where not exists (select 1 from auth.users where lower(email) = %(e)s::text)""", {"e": sys.argv[2]})
PYEOF
echo "local test database ready: $SESSION (transaction pooler: 6543)"
