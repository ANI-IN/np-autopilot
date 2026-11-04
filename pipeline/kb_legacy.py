#!/usr/bin/env python3
"""The legacy step: archive the legacy domains and what belongs ONLY to them,
reversibly (web/lib/kb/legacy.py has the rules). Counts and ids only.

    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy.py plan       # what would be archived (no change)
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy.py archive    # archive (re-runnable); the sync then keeps applying it
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy.py restore    # one command restores everything (and stops the sync re-applying it)

Permanent deletion is not done here: it lives in pipeline/kb_legacy_delete.py
(owner-approved; for production see docs/operations/GO_LIVE.md step 6).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO / "pipeline"]
sys.path[:0] = [str(REPO), str(REPO / "web")]


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("plan", "archive", "restore"):
        raise SystemExit(__doc__)
    url = os.environ.get("SUPABASE_DB_URL_SESSION")
    if not url:
        raise SystemExit("SUPABASE_DB_URL_SESSION is not set")
    import psycopg
    from lib.kb import legacy
    with psycopg.connect(url) as conn:
        conn.execute("select set_config('kb.actor_type', 'sync', true)")
        if sys.argv[1] == "plan":
            p = legacy.plan(conn)
            out = {k: len(v) for k, v in p.items()}
            out["ids"] = {k: v for k, v in p.items() if k in ("kept_connected_to_current", "domains_with_current_connections")}
            conn.rollback()
        elif sys.argv[1] == "archive":
            out = legacy.archive(conn)
            conn.commit()
        else:
            out = legacy.restore(conn)
            conn.commit()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
