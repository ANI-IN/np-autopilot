#!/usr/bin/env python3
"""Measure the scheduled sync's time-boxed batches (run 6, B1) on a LOCAL
database: how many batches, and how long each takes, for

  none     no source change since the last run
  hundred  100 changed source rows (labels of 100 records, changed in a
           throw-away clone and nothing else)
  first    a full first import into an empty KB

Each scenario runs batches of KB_SYNC_BUDGET_SECONDS (default 10) until a run
completes, the way the cron route does (one batch per call; the next call
continues from the saved place). Counts and seconds only.

  python scripts/kb_sync_timing.py <scenario> --db kb_b1_timing [--budget 10]

LOCAL ONLY: refuses any database that is not on 127.0.0.1, and every scenario
that changes the source or empties the KB refuses to run on a database whose
name does not end in `_timing` (make one with `createdb -T kb_b1 kb_b1_timing`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web")]

CONTENT = ("node_tags", "node_resources", "edges", "nodes", "resources", "tags", "proposals", "import_runs",
           "graph_positions", "flags", "templates", "saved_views", "sync_map", "sync_runs", "legacy_archive")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=("none", "hundred", "first"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--budget", type=float, default=float(os.environ.get("KB_SYNC_BUDGET_SECONDS", "10")))
    ap.add_argument("--max-batches", type=int, default=200)
    a = ap.parse_args()
    if not a.db.replace("_", "").isalnum():
        raise SystemExit("bad database name")
    if a.scenario != "none" and not a.db.endswith("_timing"):
        raise SystemExit("REFUSED: this scenario changes data; use a throw-away clone named *_timing")
    url = f"postgresql://postgres:postgres@127.0.0.1:54322/{a.db}"
    import psycopg
    from lib.kb import sync
    with psycopg.connect(url, autocommit=True) as c:
        admin = c.execute("select user_id::text from kb.memberships where role = 'admin' and archived_at is null "
                          "order by created_at limit 1").fetchone()
        admin = admin[0] if admin else None
        if a.scenario == "hundred":
            ids = [r[0] for r in c.execute("""select n.id from public.nodes n where n.type = any(%s)
                                              and not n.sensitive order by n.id limit 100""",
                                           (list(sync.load_mapping()["types"]),)).fetchall()]
            c.execute("update public.nodes set label = label || ' (timing)' where id = any(%s)", (ids,))
            print(f"changed {len(ids)} source rows")
        if a.scenario == "first":
            c.execute("truncate " + ", ".join(f"kb.{t}" for t in CONTENT) + " cascade")
            print("emptied the KB content tables")
    batches = []
    for i in range(a.max_batches):
        with psycopg.connect(url) as conn:
            t = time.monotonic()
            out = sync.run(conn, trigger="cron", actor_id=admin, apply=True, budget_seconds=a.budget,
                           operator=admin is None)
            secs = time.monotonic() - t
        writes = sum(sum(out[k].values()) for k in ("created", "updated", "removed_at_source", "restored_at_source", "adopted"))
        batches.append({"batch": i + 1, "seconds": round(secs, 1), "partial": out["partial"], "writes": writes,
                        "stopped_in": (out.get("resume") or {}).get("phase")})
        print(json.dumps(batches[-1]))
        if not out["partial"]:
            break
    total = round(sum(b["seconds"] for b in batches), 1)
    print(json.dumps({"scenario": a.scenario, "budget": a.budget, "batches": len(batches), "total_seconds": total,
                      "max_batch_seconds": max(b["seconds"] for b in batches)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
