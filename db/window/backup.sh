#!/usr/bin/env bash
# Window step 1: back up what the projection replaces, and the curation tables.
#   WINDOW_DSN=<dsn> db/window/backup.sh <dir>        (dir: mode 700, outside
#   the repo and outside Desktop/Documents — R22)
# Read-only against the database. Writes: projection.dump (the 7 tables the
# projection TRUNCATEs; node_layout does not exist before 0021), curation.dump
# (reference — the projection never touches these), counts-before.txt.
set -euo pipefail
. "$(dirname "$0")/_guard.sh"
need_dsn; guard_dir "$1"; out="$(cd "$1" && pwd -P)"
t0=$SECONDS
pg_dump "$WINDOW_DSN" -Fc --data-only \
  -t public.nodes -t public.edges -t public.node_sources -t public.files \
  -t public.node_types -t public.edge_rels -t public.projection_meta \
  -f "$out/projection.dump"
pg_dump "$WINDOW_DSN" -Fc --data-only \
  -t public.people -t public.people_aliases -t public.domain_aliases \
  -t public.workflow_owners -t public.curation_notes -t public.curation_audit \
  -f "$out/curation.dump"
psql "$WINDOW_DSN" -At -F '	' -f "$(dirname "$0")/counts.sql" > "$out/counts-before.txt"
chmod 600 "$out"/*
echo "backup: $((SECONDS - t0)) s"
ls -l "$out" | awk 'NR>1 {print "  " $5 " B  " $9}'
