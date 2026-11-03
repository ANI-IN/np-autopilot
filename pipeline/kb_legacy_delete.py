#!/usr/bin/env python3
"""The owner-approved PERMANENT deletion of the legacy domains and legacy
modules (run 6 resume, R3). Rules: web/lib/kb/legacy_delete.py. Counts only.

    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy_delete.py plan
        what would go (no change)
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy_delete.py delete
        export every affected row to backups/legacy_deleted_<db>_<date>.json
        (gitignored: real data), THEN delete in one transaction
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_legacy_delete.py restore <export.json>
        put every exported row back (same ids) and switch the sync exclusions off

Refuses production unless NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION=yes (GO_LIVE.md
step; never set in this repo's runs).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO / "pipeline"]
sys.path[:0] = [str(REPO), str(REPO / "web")]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("plan", "delete", "restore") or (sys.argv[1] == "restore") != (len(sys.argv) == 3):
        raise SystemExit(__doc__)
    url = os.environ.get("SUPABASE_DB_URL_SESSION")
    if not url:
        raise SystemExit("SUPABASE_DB_URL_SESSION is not set")
    from pipeline.lib import db
    if db.production_reason(url) and os.environ.get("NP_ALLOW_LEGACY_DELETE_ON_PRODUCTION") != "yes":
        raise SystemExit("REFUSED: this is production; see docs/GO_LIVE.md (legacy deletion step)")
    import psycopg
    from lib.kb import legacy_delete as ld
    with psycopg.connect(url) as conn:
        if sys.argv[1] == "restore":
            data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            out = ld.restore(conn, data)
            conn.commit()
        else:
            p = ld.plan(conn)
            if sys.argv[1] == "plan":
                out = {"current_domains_kept": len(p["current_domains"]), "domains": len(p["domains"]),
                       "modules": len(p["modules"]), "detached_and_flagged": len(p["orphans"]),
                       "links_flagged": len(p["lone_links"]), "expertise_links": p["expertise_links"]}
                conn.rollback()
            else:
                data = ld.export(conn, p)
                dbname = (urlparse(url).path or "/db").strip("/") or "db"
                dbname = "dev" if db.production_reason(url) is None and "pooler" in (urlparse(url).hostname or "") else dbname
                path = REPO / "backups" / f"legacy_deleted_{dbname}_{datetime.now():%Y%m%d_%H%M%S}.json"
                ld.write_export(data, path)
                check = json.loads(path.read_text(encoding="utf-8"))        # the file must read back before anything is deleted
                if len(check["tables"]["nodes"]) != len(p["domains"]) + len(p["modules"]):
                    raise SystemExit("REFUSED: the export does not hold every record; nothing deleted")
                out = ld.delete(conn, p, data)
                conn.commit()
                out["export"] = str(path.relative_to(REPO))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
