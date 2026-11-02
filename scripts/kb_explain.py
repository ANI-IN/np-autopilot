#!/usr/bin/env python3
"""EXPLAIN ANALYZE every query behind the list, search, neighbourhood,
dashboard and activity endpoints at the 5,000-record / 15,000-relationship
synthetic seed (run 3, Phase C). LOCAL ONLY: seeds with scripts/kb_perf.py's
seed, runs each endpoint once through the service layer AS A REAL ROLE (RLS
applies), and EXPLAINs every SELECT it issues. Reports each statement's
execution time, and every sequential scan of a large table. Truncates the kb
content tables afterwards unless --keep.

    python scripts/kb_explain.py [--keep] [--role editor]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "scripts"), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]

import kb_perf                                                          # noqa: E402  (sets the local DSNs)
from kb_support import USERS, as_user, ensure_users, owner, reset      # noqa: E402

BIG = {"nodes", "edges", "audit_log", "changes", "node_resources", "resources", "node_tags", "link_checks"}


class Explaining:
    """A cursor proxy: EXPLAIN (ANALYZE) each SELECT, then run it for real."""

    def __init__(self, conn, log):
        self.conn, self.log, self.label = conn, log, ""

    def cursor(self):
        outer = self

        class C:
            def __init__(self):
                self.cur = outer.conn.cursor()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.cur.close()

            def execute(self, sql, params=None):
                if sql.lstrip().lower().startswith(("select", "with")):
                    outer.conn.execute("savepoint ex")
                    plan = outer.conn.execute("explain (analyze, format json) " + sql, params).fetchone()[0][0]
                    outer.conn.execute("rollback to savepoint ex")
                    seqs = []

                    def walk(n):
                        if n.get("Node Type") == "Seq Scan" and n.get("Relation Name") in BIG and n.get("Actual Rows", 0) * n.get("Actual Loops", 1) > 200:
                            seqs.append(f"{n['Relation Name']} ({n.get('Actual Rows')} rows x {n.get('Actual Loops')})")
                        for k in n.get("Plans", []):
                            walk(k)
                    walk(plan["Plan"])
                    outer.log.append({"endpoint": outer.label, "ms": round(plan["Execution Time"], 2), "seq_scans": seqs,
                                      "sql": " ".join(sql.split())[:110]})
                return self.cur.execute(sql, params)

            def executemany(self, *a, **k):
                return self.cur.executemany(*a, **k)

            def __getattr__(self, k):
                return getattr(self.cur, k)
        return C()

    def execute(self, *a, **k):
        return self.conn.execute(*a, **k)

    def __getattr__(self, k):
        return getattr(self.conn, k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    from lib.kb import activity, service as svc, workspace as ws
    ensure_users()
    reset()
    data = kb_perf.seed(random.Random(42))
    with owner() as c:
        c.execute("analyze")
        mine = c.execute("select id from kb.nodes where name like 'Perf course%%' limit 5").fetchall()
        c.execute("update kb.nodes set owner_id = %s where id = any(%s)", (USERS["editor"], [r[0] for r in mine]))
    print(f"seed: {data['nodes']} records, {data['edges']} relationships")
    topic = data["ids"]["topic"][5]
    log: list[dict] = []
    for role in ("viewer", "editor", "admin"):
        with as_user(USERS[role]) as raw:
            conn = Explaining(raw, log)
            cases = {
                "list nodes": lambda: svc.list_nodes(conn, {"limit": 50}),
                "list nodes type+name": lambda: svc.list_nodes(conn, {"type": "topic", "sort": "name", "limit": 50}),
                "search": lambda: svc.search(conn, "consensus"),
                "neighbourhood d2": lambda: svc.neighbourhood(conn, str(topic), 2),
                "dashboard": lambda: (svc.dashboard(conn), ws.needs_attention(conn), ws.course_completeness(conn)),
                "counts": lambda: (svc.dashboard_totals(conn), ws.attention_counts(conn)),
                "activity": lambda: activity.activity(conn, {"limit": 50}),
                "activity filtered": lambda: activity.activity(conn, {"table": "nodes", "action": "insert", "limit": 50}),
                "history": lambda: activity.history(conn, str(topic)),
                "changes": lambda: activity.changes(conn, 1),
            }
            for name, fn in cases.items():
                conn.label = f"{role}: {name}"
                fn()
    worst = sorted(log, key=lambda x: -x["ms"])[:15]
    print("\nslowest statements:")
    for x in worst:
        print(f"  {x['ms']:8.2f} ms  {x['endpoint']:<30} {x['sql']}")
    seq = [x for x in log if x["seq_scans"]]
    print(f"\nstatements with a sequential scan of a large table: {len(seq)}")
    for x in seq:
        print(f"  {x['endpoint']:<30} {', '.join(x['seq_scans'])}  ::  {x['sql']}")
    per = {}
    for x in log:
        per[x["endpoint"]] = round(per.get(x["endpoint"], 0) + x["ms"], 1)
    print("\n| Endpoint (role: request) | Statements | DB time ms |\n|---|---|---|")
    for k, ms in per.items():
        print(f"| {k} | {sum(1 for x in log if x['endpoint'] == k)} | {ms} |")
    if a.json:
        Path(a.json).write_text(json.dumps(log, indent=2))
    if not a.keep:
        reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
