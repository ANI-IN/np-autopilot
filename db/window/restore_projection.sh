#!/usr/bin/env bash
# ROLLBACK for window steps 5-7: put the pre-window graph back from backup.sh's
# projection.dump. The ONLY way back after 0021 — the old project_graph.py
# cannot TRUNCATE nodes once node_layout references it.
#   WINDOW_DSN=<dsn> db/window/restore_projection.sh <dir>
# ONE transaction: truncate the 8 projection tables (node_layout included, left
# empty — the old graph has no layout and the client simulates), then load the
# data back. Curation tables are not touched.
set -euo pipefail
. "$(dirname "$0")/_guard.sh"
need_dsn; guard_dir "$1"; in="$(cd "$1" && pwd -P)"
[ -s "$in/projection.dump" ] || { echo "REFUSED: no projection.dump in $in"; exit 2; }
t0=$SECONDS
pg_restore --data-only --no-owner -f - "$in/projection.dump" > "$in/restore.sql"
chmod 600 "$in/restore.sql"
{
  echo "begin;"
  echo "truncate node_layout, node_sources, edges, nodes, files, edge_rels, node_types, projection_meta restart identity;"
  grep -vE '^(SET transaction_timeout|SELECT pg_catalog.set_config\(.search_path)' "$in/restore.sql"
  echo "commit;"
} | psql "$WINDOW_DSN" -q -v ON_ERROR_STOP=1 > "$in/restore.log" 2>&1
psql "$WINDOW_DSN" -At -F '	' -f "$(dirname "$0")/counts.sql" > "$in/counts-restored.txt"
chmod 600 "$in"/*
echo "restore: $((SECONDS - t0)) s"
# The PROJECTION's own tables and hash must match the backup exactly. Other
# tables are reported, not compared: `profiles` changes whenever someone signs
# in, and curation is never touched by the projection or by this restore.
keys='^(content_hash|nodes|edges|node_sources|files|node_types|edge_rels)	'
if diff <(grep -E "$keys" "$in/counts-before.txt") <(grep -E "$keys" "$in/counts-restored.txt"); then
  echo "restored: the projection's counts and content hash match the backup"
else
  echo "RESTORE MISMATCH — see the diff above"; exit 1
fi
cur='^(people|people_aliases|domain_aliases|workflow_owners|curation_notes|curation_audit)	'
diff -q <(grep -E "$cur" "$in/counts-before.txt") <(grep -E "$cur" "$in/counts-restored.txt") >/dev/null \
  && echo "curation tables: unchanged" || echo "NOTE: curation counts differ from the backup — check before proceeding"
