#!/usr/bin/env bash
# Build the prebuilt deploy artifact from a DIRECTORY THAT ALREADY EXCLUDES
# EVERYTHING IN .vercelignore, then prove the function map cites nothing the
# upload would leave out.
#
#   db/window/build_artifact.sh <git ref> <stats.json>   -> /tmp/np-deploy-<sha>
#
# WHY (2026-09-30, window step 4): `vercel build` wrote a function whose file
# map pointed at 1,050 project files, *.md and docs/ among them; `vercel deploy
# --prebuilt` then uploaded the project HONOURING .vercelignore, and Vercel
# failed on the first missing one (ENOENT readlink 01-corpus-inventory.md).
# The rehearsal had built the artifact but never deployed it — "prebuilt
# deploy was never exercised against Vercel" (docs/operations/risk-register.md R23).
#
# Pruning uses git's own matcher on .vercelignore (gitignore semantics,
# `!README.md` included), in a throwaway repository inside the artifact.
set -euo pipefail
ref="${1:?usage: build_artifact.sh <git ref> <stats.json>}"
stats="${2:?usage: build_artifact.sh <git ref> <stats.json>}"
repo="$(cd "$(dirname "$0")/../.." && pwd -P)"
sha="$(git -C "$repo" rev-parse --short "$ref")"
D="/tmp/np-deploy-$sha"
rm -rf "$D" "$D.build.log"
mkdir -m 700 "$D"
git -C "$repo" archive "$ref" | tar -x -C "$D"

# -- prune what the upload will exclude ---------------------------------------
(
  cd "$D"
  git init -q .
  git ls-files --others --ignored --exclude-from=.vercelignore -z > .pruned
  n=$(tr -cd '\0' < .pruned | wc -c | tr -d ' ')
  xargs -0 rm -f < .pruned
  rm -rf .git .pruned
  find . -type d -empty -not -path "./.vercel*" -delete
  echo "pruned: $n files excluded by .vercelignore"
)

# -- build ----------------------------------------------------------------------
mkdir -m 700 "$D/.vercel"
cp "$repo/.vercel/project.json" "$D/.vercel/"
cp "$stats" "$D/public/stats.json"
(
  cd "$D"
  vercel pull --yes --environment=production > /dev/null 2>&1
  rm -rf .vercel/python .vercel/output
  vercel build --prod > "$D.build.log" 2>&1
)
# The pulled env file holds production secrets; the function never needs it.
rm -f "$D/.vercel/.env.production.local"
echo "built: $D"
python3 "$repo/db/window/check_function_map.py" "$D"
