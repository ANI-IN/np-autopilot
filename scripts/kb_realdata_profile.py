#!/usr/bin/env python3
"""Profile every request behind every screen, the "/" map's routes and
GET /api/kb/graph AT REAL-DATA SIZE (run 6, B5).

Runs against a LOCAL clone of the real data (a `kb_*` database on
127.0.0.1:54322, e.g. kb_b5), through the real WSGI app in-process: token
verification, the request connection, RLS as the signed-in member, JSON
encoding. GET requests only: it never writes. Prints counts, ids and timings,
never record contents.

    python scripts/kb_realdata_profile.py --db kb_b5 [--runs 7] [--explain] [--only quality]

--explain additionally runs each KB request once through api/kb_routes.handle
with EXPLAIN (ANALYZE) on every SELECT it issues (scripts/kb_explain.py's
cursor proxy), and reports the slowest statements and every sequential scan
of a large table.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "scripts"), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]


def _configure(db_name: str) -> str:
    if not re.fullmatch(r"kb_[a-z0-9_]{1,40}", db_name):
        sys.exit("REFUSED: --db must name a local kb_* database")
    dsn = f"postgresql://postgres:postgres@127.0.0.1:54322/{db_name}"
    os.environ["SUPABASE_DB_URL_SESSION"] = dsn
    os.environ["SUPABASE_DB_URL_TRANSACTION"] = dsn
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("KB_REALTIME_ORIGIN", None)
    return dsn


def _ids(dsn: str) -> dict:
    """Representative ids (no names): the admin member, a busy record, a
    container, a map node, a domain query and a recent change id."""
    import psycopg
    with psycopg.connect(dsn) as c:
        q = lambda sql: (lambda v: None if v is None else str(v))((c.execute(sql).fetchone() or [None])[0])  # noqa: E731
        return {
            "user": q("select user_id from kb.memberships where role = 'admin' order by user_id limit 1"),
            "busy": q("""select n.id from kb.nodes n join kb.edges e on e.source_id = n.id or e.target_id = n.id
                         where n.archived_at is null and not n.is_legacy group by n.id order by count(*) desc limit 1"""),
            "container": q("""select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
                              where t.is_container and n.archived_at is null and not n.is_legacy order by n.id limit 1"""),
            "since": q("select greatest(coalesce(max(id), 0) - 50, 0) from kb.changes"),
            "map_node": q("select id from public.nodes where type = 'module' order by id limit 1"),
            "map_domain": q("select id from public.nodes where type = 'domain' order by id limit 1"),
        }


def requests(ids: dict) -> list[tuple[str, str, str]]:
    """(screen, path, query). The shell requests run on every screen."""
    b, c = ids["busy"], ids["container"]
    out = [
        ("shell", "/api/kb/me", ""), ("shell", "/api/kb/types", ""), ("shell", "/api/kb/people", ""),
        ("shell", "/api/kb/counts", ""), ("shell", "/api/kb/sync", ""),
        ("shell", "/api/kb/changes", f"since={ids['since']}"),
        ("dashboard", "/api/kb/dashboard", ""),
        ("records", "/api/kb/nodes", "limit=100"), ("records", "/api/kb/views", ""), ("records", "/api/kb/tags", ""),
        ("records", "/api/kb/nodes", "type=module&limit=100"),
        ("records", "/api/kb/nodes", "type=instructor&sort=name&limit=100"),
        ("programs", "/api/kb/nodes", "type=program&limit=100"),
        ("resources", "/api/kb/resources", "limit=100"),
        ("outline", "/api/kb/outline", ""),
        ("graph", "/api/kb/graph", ""), ("graph", "/api/kb/graph", "legacy=all"),
        ("graph", "/api/kb/graph/positions", ""),
        ("graph", "/api/kb/nodes", "type=program,course&sort=name&limit=20"),
        ("graph focus", "/api/kb/graph", f"focus={b}&depth=1"),
        ("graph focus", "/api/kb/graph", f"focus={b}&depth=2"),
        ("graph focus", "/api/kb/graph", f"scope={c}"),
        ("teaching", "/api/kb/views/teaching", ""), ("timeline", "/api/kb/views/timeline", ""),
        ("activity", "/api/kb/activity", "limit=50"),
        ("quality", "/api/kb/quality", ""), ("quality", "/api/kb/quality/sync", ""),
        ("quality", "/api/kb/quality/duplicates", ""),
        ("approvals", "/api/kb/proposals", ""), ("approvals", "/api/kb/flags", "status=open"),
        ("archived", "/api/kb/archived", "kind=records"),
        ("settings", "/api/kb/types", "archived=1"), ("settings", "/api/kb/members", ""),
        ("settings", "/api/kb/tokens", ""), ("settings", "/api/kb/templates", ""),
        ("record", f"/api/kb/nodes/{b}", ""), ("record", f"/api/kb/nodes/{b}/completeness", ""),
        ("record", f"/api/kb/nodes/{b}/impact", ""), ("record", f"/api/kb/nodes/{b}/history", ""),
        ("search", "/api/kb/search", "q=python"), ("search", "/api/kb/search", "q=system%20design"),
        ("search", "/api/kb/nodes", "q=data&limit=100"),
        ("map /", "/api/me", ""), ("map /", "/api/structure", ""), ("map /", "/api/overview", ""),
        ("map /", "/api/coverage", ""), ("map /", "/api/search", "q=python"),
    ]
    if ids.get("map_node"):
        out += [("map /", "/api/node", f"id={ids['map_node']}"),
                ("map /", "/api/node", f"id={ids['map_node']}&detail=1"),
                ("map /", "/api/neighbourhood", f"id={ids['map_node']}")]
    if ids.get("map_domain"):
        out.append(("map /", "/api/staffing", f"domain={ids['map_domain']}"))
    return out


class _App:
    def __init__(self, user_id: str):
        import kb_support
        os.environ["SUPABASE_JWT_SECRET"] = kb_support.TEST_JWT_SECRET
        import index
        self.app, self.token = index.app, kb_support.token_for(user_id)

    def get(self, path: str, query: str) -> tuple[int, int, float]:
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": query, "CONTENT_LENGTH": "0",
               "wsgi.input": io.BytesIO(b""), "HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        out = {}
        t0 = time.perf_counter()
        body = b"".join(self.app(env, lambda s, h: out.setdefault("s", int(s.split()[0]))))
        return out["s"], len(body), (time.perf_counter() - t0) * 1000


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def timings(app: _App, reqs, runs: int) -> list[dict]:
    rows = []
    for screen, path, query in reqs:
        st, size, first = app.get(path, query)
        ms = [app.get(path, query)[2] for _ in range(runs)]
        rows.append({"screen": screen, "request": path + ("?" + query if query else ""), "status": st,
                     "bytes": size, "first_ms": round(first, 1), "p50_ms": round(statistics.median(ms), 1),
                     "p95_ms": round(_pct(ms, 0.95), 1), "max_ms": round(max(ms), 1)})
        print(f"  {rows[-1]['p50_ms']:9.1f} {rows[-1]['p95_ms']:9.1f}  {st}  {screen:<12} {rows[-1]['request'][:90]}",
              file=sys.stderr)
    return rows


def explain(dsn: str, user_id: str, reqs) -> list[dict]:
    """EXPLAIN (ANALYZE) every SELECT behind each KB request."""
    from urllib.parse import parse_qs
    import kb_routes
    from kb_explain import Explaining
    from kb_support import as_user
    log: list[dict] = []
    for screen, path, query in reqs:
        if not path.startswith("/api/kb/"):
            continue
        parts = [p for p in path[len("/api/kb/"):].split("/") if p]
        params = {k: v[0] for k, v in parse_qs(query).items()}
        with as_user(user_id) as raw:
            conn = Explaining(raw, log)
            conn.label = path + ("?" + query if query else "")
            try:
                kb_routes.handle(conn, kb_routes.svc.Actor(user_id, "human"), "GET", parts, params, None)
            except Exception as exc:                                    # noqa: BLE001
                print(f"  {conn.label}: {type(exc).__name__}", file=sys.stderr)
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="kb_b5")
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--only", default="", help="comma list of screens")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    dsn = _configure(a.db)
    ids = _ids(dsn)
    if not ids["user"]:
        sys.exit("no admin member in that database")
    reqs = requests(ids)
    if a.only:
        keep = set(a.only.split(","))
        reqs = [r for r in reqs if r[0] in keep]
    rows = timings(_App(ids["user"]), reqs, a.runs)
    print(f"\n| Screen | Request | Status | KB | first ms | p50 ms | p95 ms |\n|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['screen']} | `{re.sub(r'[0-9a-f-]{36}|np:[^&]+', '<id>', r['request'])}` | {r['status']} | "
              f"{r['bytes'] / 1024:.1f} | {r['first_ms']} | {r['p50_ms']} | {r['p95_ms']} |")
    result = {"timings": rows}
    if a.explain:
        log = explain(dsn, ids["user"], reqs)
        print("\nslowest statements:")
        for x in sorted(log, key=lambda x: -x["ms"])[:20]:
            print(f"  {x['ms']:9.2f} ms  {re.sub(r'[0-9a-f-]{36}', '<id>', x['endpoint'])[:40]:<40} {x['sql']}")
        seq = [x for x in log if x["seq_scans"]]
        print(f"\nstatements with a sequential scan of a large table: {len(seq)}")
        for x in seq:
            print(f"  {re.sub(r'[0-9a-f-]{36}', '<id>', x['endpoint'])[:40]:<40} {', '.join(x['seq_scans'])}  ::  {x['sql'][:80]}")
        result["explain"] = log
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
