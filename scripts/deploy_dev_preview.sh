#!/usr/bin/env bash
# Deploy the knowledge platform to a Vercel PREVIEW wired to the DEV database
# (docs/operations/dev-deploy.md). Never Production, never the production database.
#
#   bash scripts/deploy_dev_preview.sh            # checks, deploy (preview), smoke tests
#   bash scripts/deploy_dev_preview.sh --check    # the checks only; deploys nothing
#
# Needs: the Vercel CLI, logged in (`vercel login`, or VERCEL_TOKEN), the project
# linked (`vercel link`), and the Preview variables of docs/operations/dev-deploy.md set for
# THIS branch. Needs DEV_SUPABASE_URL (environment or .env) to know the dev
# project. Prints no secret, URL of a database, host or IP from any env file.
#
# REFUSES, before anything is deployed:
#   - any argument naming production (--prod, --target=production, ...);
#   - a branch other than auto/knowledge-platform-20261102;
#   - Preview variables for this branch that name the production project
#     (yqmzjgzhxhihnpbgqmeh), or that do not name the dev project;
#   - a database URL that is not the transaction pooler (port 6543);
#   - the service-role key or the session pooler URL among the variables;
#   - a deployment the CLI reports as anything but a preview.
set -euo pipefail

BRANCH="auto/knowledge-platform-20261102"
PROD_REF="yqmzjgzhxhihnpbgqmeh"
CHECK_ONLY=0
die() { echo "REFUSED: $*" >&2; exit 1; }

for a in "$@"; do
  case "$a" in
    --check) CHECK_ONLY=1 ;;
    *prod*|*Prod*|*PROD*) die "this script never deploys to Production ($a)" ;;
    *) die "unknown argument: $a" ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
command -v vercel >/dev/null || die "the Vercel CLI is not installed (npm i -g vercel)"
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || die "check out $BRANCH first"

# The dev project's ref, from DEV_SUPABASE_URL (environment, else .env). Not printed.
DEV_URL="${DEV_SUPABASE_URL:-}"
if [ -z "$DEV_URL" ] && [ -f .env ]; then
  DEV_URL="$(grep -E '^DEV_SUPABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')"
fi
DEV_REF="$(printf '%s' "$DEV_URL" | sed -nE 's#^https://([a-z0-9]{20})\.supabase\.co/?$#\1#p')"
[ -n "$DEV_REF" ] || die "DEV_SUPABASE_URL is missing or not https://<ref>.supabase.co"
[ "$DEV_REF" != "$PROD_REF" ] || die "DEV_SUPABASE_URL names the production project"

TOKEN_ARGS=()
[ -n "${VERCEL_TOKEN:-}" ] && TOKEN_ARGS=(--token "$VERCEL_TOKEN")

# Pull the Preview variables of THIS branch into a private temp file; inspect, then delete.
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
vercel env pull "$TMP" --environment=preview --git-branch="$BRANCH" --yes "${TOKEN_ARGS[@]}" >/dev/null 2>&1 \
  || die "could not read the Preview variables for $BRANCH (vercel login / vercel link?)"
val() { grep -E "^$1=" "$TMP" | head -1 | cut -d= -f2- | sed -E 's/^"(.*)"$/\1/'; }

grep -q "$PROD_REF" "$TMP" && die "a Preview variable for $BRANCH names the production project"
for v in SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_DB_URL_TRANSACTION GOOGLE_OAUTH_CLIENT_ID NP_ALLOWED_HD KB_SYNC_SECRET; do
  [ -n "$(val "$v")" ] || die "$v is not set for Preview / $BRANCH (docs/operations/dev-deploy.md, step 2)"
done
case "$(val SUPABASE_URL)" in *"$DEV_REF"*) ;; *) die "SUPABASE_URL is not the dev project" ;; esac
case "$(val SUPABASE_DB_URL_TRANSACTION)" in *"$DEV_REF"*) ;; *) die "SUPABASE_DB_URL_TRANSACTION is not the dev project" ;; esac
case "$(val SUPABASE_DB_URL_TRANSACTION)" in *:6543/*) ;; *) die "SUPABASE_DB_URL_TRANSACTION must be the transaction pooler (port 6543)" ;; esac
[ -z "$(val SUPABASE_SERVICE_ROLE_KEY)" ] || die "SUPABASE_SERVICE_ROLE_KEY must never be set in Vercel"
[ -z "$(val SUPABASE_DB_URL_SESSION)" ] || die "SUPABASE_DB_URL_SESSION must never be set in Vercel"
S="$(val KB_SYNC_SECRET)"; [ "${#S}" -ge 24 ] || die "KB_SYNC_SECRET must be at least 24 characters"; unset S
echo "checks passed: Preview variables for $BRANCH point at the dev project, transaction pooler, no service key"
[ "$CHECK_ONLY" = 1 ] && exit 0

# The preview's functions run next to the DEV database, not where production runs.
# vercel.json pins icn1 because production's database is in Seoul; the DEV project is
# in eu-west-1, so from icn1 every query crossed Asia to Europe (~1 s per request,
# 6-7 s to sign in; measured 2026-11-07). --regions applies to this deployment only;
# vercel.json and production are unchanged.
REGION="${DEV_PREVIEW_REGION:-dub1}"
case "$REGION" in [a-z][a-z][a-z][0-9]) ;; *) die "DEV_PREVIEW_REGION must be a Vercel region id like dub1" ;; esac

# Deploy: a preview (no --prod, explicit --target=preview).
OUT="$(vercel deploy --target=preview --regions "$REGION" --yes "${TOKEN_ARGS[@]}" 2>/dev/null)" || die "vercel deploy failed"
URL="$(printf '%s\n' "$OUT" | grep -Eo 'https://[a-z0-9.-]+\.vercel\.app' | tail -1)"
[ -n "$URL" ] || die "no deployment URL in the CLI output"
TARGET="$(vercel inspect "$URL" "${TOKEN_ARGS[@]}" 2>&1 | grep -iE '^\s*target' | head -1 || true)"
case "$TARGET" in *production*|*Production*) die "the CLI reports a production deployment: stop and investigate" ;; esac
echo "deployed (preview): $URL"

# A fixed alias, so the preview's address stays the same across deploys (the project
# has no Git connection, so Vercel gives no per-branch URL). A preview alias, never a
# production domain: the name must end in .vercel.app and must not be the project's own.
ALIAS="${DEV_PREVIEW_ALIAS:-np-autopilot-kb-dev.vercel.app}"
case "$ALIAS" in
  np-autopilot.vercel.app) die "$ALIAS is the production domain" ;;
  *.vercel.app) ;;
  *) die "DEV_PREVIEW_ALIAS must be a *.vercel.app name" ;;
esac
vercel alias set "$URL" "$ALIAS" "${TOKEN_ARGS[@]}" >/dev/null 2>&1 || die "could not point $ALIAS at the preview"
echo "alias: https://$ALIAS -> this preview"

# Smoke tests (docs/operations/dev-deploy.md, step 4). A protected preview answers 401 to
# anonymous requests unless VERCEL_BYPASS (Protection Bypass for Automation) is set.
H=()
[ -n "${VERCEL_BYPASS:-}" ] && H=(-H "x-vercel-protection-bypass: $VERCEL_BYPASS")
code() { curl -s -o /dev/null -w '%{http_code}' "${H[@]}" "$@"; }
fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok   $1 ($2)"; else echo "  FAIL $1: got $2, want $3"; fail=1; fi; }
check "/api/config answers"                  "$(code "$URL/api/config")" 200
check "/kb/ is served"                       "$(code "$URL/kb/")" 200
check "/api/kb/me needs a session"           "$(code "$URL/api/kb/me")" 401
check "/api/cron/kb-sync refuses no secret"  "$(code -X POST "$URL/api/cron/kb-sync")" 401
check "/local-login does not exist"          "$(code "$URL/local-login")" 404
check "the alias serves /kb/"                "$(code "https://$ALIAS/kb/")" 200
RAN="$(curl -s -o /dev/null -D - "${H[@]}" "https://$ALIAS/api/config" | tr -d '\r' | sed -nE 's/^[Xx]-[Vv]ercel-[Ii]d: ([a-z0-9:]+).*/\1/p' | awk -F'::' '{print $(NF-1)}')"
check "functions run in $REGION"             "$RAN" "$REGION"
[ "$fail" = 0 ] || die "smoke tests failed (above)"
echo "smoke tests passed. Next: docs/operations/dev-deploy.md step 5 (Google sign-in) and step 6 (the schedule)."
