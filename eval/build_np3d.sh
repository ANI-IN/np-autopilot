#!/usr/bin/env bash
# Rebuild public/vendor/np3d.min.js — the 3D map's vendored bundle.
# Self-hosted, no CDN; eval-free (the ngraph engine is stubbed out because it
# uses `new Function`, which the CSP refuses). Pinned versions:
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd -P)"; tmp="$(mktemp -d)"; cd "$tmp"
npm init -y >/dev/null
npm install --silent --no-audit --no-fund 3d-force-graph@1.80.1 three@0.186.1 esbuild@0.28.2
cp "$repo/eval/np3d-ngraph-stub.js" ngraph-stub.js
printf "export { default as ForceGraph3D } from '3d-force-graph';\nexport * as THREE from 'three';\n" > entry.js
npx esbuild entry.js --bundle --minify --format=iife --global-name=NP3D --legal-comments=eof \
  --alias:ngraph.forcelayout=./ngraph-stub.js --alias:ngraph.graph=./ngraph-stub.js \
  --outfile="$repo/public/vendor/np3d.min.js"
if grep -q 'new Function\|[^a-zA-Z_.]eval(' "$repo/public/vendor/np3d.min.js"; then
  echo "np3d.min.js contains eval/new Function — the CSP would refuse it" >&2; exit 1; fi
echo "built $(wc -c < "$repo/public/vendor/np3d.min.js") bytes"
