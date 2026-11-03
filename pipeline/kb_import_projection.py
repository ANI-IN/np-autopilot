#!/usr/bin/env python3
"""The projection (the original site's tables) -> the KB: the first import and
any manual sync from a laptop or CI. The engine is web/lib/kb/sync.py (the same
code the scheduled sync runs); the mapping is config/kb-projection-mapping.yaml;
docs/MIGRATION_MAPPING.md explains it.

    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_import_projection.py preview --as <admin email> [--report out.json]
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_import_projection.py apply   --as <admin email> [--report out.json]
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_import_projection.py apply   --operator      # a new database, no admin yet

preview runs everything and rolls back; apply commits, in batches, as a sync
run (kb.sync_runs, trigger 'cli'). Re-running is safe: only changes are
written; a record edited in the KB is flagged as a conflict, never overwritten.
Output: counts and ids only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# pipeline/lib would shadow web/lib (the KB service), as in kb_import_sheets.py.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO / "pipeline"]
sys.path[:0] = [str(REPO), str(REPO / "web")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["preview", "apply"])
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--as", dest="admin", help="e-mail of a KB admin; the run is attributed to them")
    who.add_argument("--operator", action="store_true",
                     help="no KB admin exists yet (a new database): run as the operator, i.e. the kb tables' owner "
                          "on the session pooler; attributed to 'Sync' with no person")
    ap.add_argument("--report", help="write the run's report (counts and ids only) as JSON here")
    a = ap.parse_args()
    url = os.environ.get("SUPABASE_DB_URL_SESSION")
    if not url:
        raise SystemExit("SUPABASE_DB_URL_SESSION is not set")
    import psycopg
    from lib.kb import sync
    with psycopg.connect(url, prepare_threshold=None) as conn:
        actor = None
        if a.admin:
            admin = conn.execute("""select p.user_id from public.profiles p join kb.memberships m on m.user_id = p.user_id
                                    where lower(p.email) = lower(%s) and m.role = 'admin' and m.archived_at is null""",
                                 (a.admin,)).fetchone()
            conn.rollback()
            if not admin:
                raise SystemExit("--as must name a KB admin (pipeline/kb_admins.py, or eval/kb_realdata_db.py admin locally)")
            actor = str(admin[0])
        out = sync.run(conn, trigger="cli", actor_id=actor, apply=a.mode == "apply", operator=a.operator)
    rep = out.pop("report", {})
    out["read"] = rep.get("read")
    out["rejected"] = len(rep.get("rejected", []))
    out["problems"] = {k: len(v) for k, v in rep.get("problems", {}).items()}
    print(json.dumps(out, indent=1, default=str))
    if a.report:
        Path(a.report).write_text(json.dumps({**out, "rejected_ids": rep.get("rejected"),
                                              "problem_ids": rep.get("problems")}, indent=1, default=str), encoding="utf-8")
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
