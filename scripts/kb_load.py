#!/usr/bin/env python3
"""Concurrency and load check (run 3, Phase C). LOCAL ONLY.

N simulated people (default 25: 5 editors, 15 contributors, 5 viewers) run a
mixed read/write workload for D seconds (default 120) through the real WSGI app
(token verification, RLS, triggers), including:
  - same-record conflicts: everyone edits the same three "hot" records with the
    version they last read, so most of those saves must come back 409;
  - parallel graph edits: everyone saves positions in the shared layout;
  - relationship races: everyone tries to create the same few relationships.

Afterwards it checks: no duplicate records or relationships, no live
relationship pointing at an archived record, every rejected save a 409 (no
5xx), and one audit row for every successful write. It prints p50/p95 per
endpoint and the error rate. It truncates the kb content tables before and
after, and removes its synthetic people.

    python scripts/kb_load.py [--users 25] [--seconds 120] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]
os.environ.setdefault("SUPABASE_DB_URL_SESSION", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
os.environ.setdefault("SUPABASE_DB_URL_TRANSACTION", "postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres")

from kb_support import USERS, Client, ensure_users, owner, reset      # noqa: E402

LOAD_NS = "np-kb-load/"


def people(n: int) -> list[tuple[str, str]]:
    roles = (["editor"] * max(1, n // 5) + ["viewer"] * max(1, n // 5))
    roles += ["contributor"] * (n - len(roles))
    out = []
    with owner() as c:
        for i, r in enumerate(roles):
            uid = str(uuid.uuid5(uuid.NAMESPACE_URL, LOAD_NS + str(i)))
            email = f"kbload-{i:02d}@interviewkickstart.com"
            c.execute("insert into auth.users (id, email, created_at) values (%s, %s, now()) on conflict (id) do nothing", (uid, email))
            c.execute("insert into profiles (user_id, email, email_domain, role) values (%s, %s, 'interviewkickstart.com', 'member') "
                      "on conflict (user_id) do nothing", (uid, email))
            if r == "viewer":
                c.execute("delete from kb.memberships where user_id = %s", (uid,))
            else:
                c.execute("insert into kb.memberships (user_id, role) values (%s, %s) on conflict (user_id) do update set role = excluded.role", (uid, r))
            out.append((uid, r))
    return out


def drop_people(n: int) -> None:
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, LOAD_NS + str(i))) for i in range(n)]
    with owner() as c:
        c.execute("delete from kb.memberships where user_id = any(%s::uuid[])", (ids,))
        c.execute("delete from profiles where user_id = any(%s::uuid[])", (ids,))
        c.execute("delete from auth.users where id = any(%s::uuid[])", (ids,))


def seed() -> dict:
    ed = Client(USERS["editor"])
    s, course = ed.post("/api/kb/courses", {"name": "Load Course"})
    assert s == 201, course
    mods = [ed.post("/api/kb/nodes", {"type": "module", "name": f"Load module {i}", "parents": [course["id"]]})[1] for i in range(20)]
    topics = [ed.post("/api/kb/nodes", {"type": "topic", "name": f"Load topic {i}"})[1] for i in range(40)]
    return {"course": course, "mods": mods, "topics": topics, "hot": mods[:3]}


def one_connection_per_person() -> None:
    """Production model: on Vercel each instance serves ONE request at a time
    over its own warm connection (web/lib/data.py keeps one per process; the
    local dev server serialises API calls with a lock for the same reason).
    Here each simulated person is such an instance: a thread-local warm
    connection, never shared between threads."""
    from lib import data as _data
    local = threading.local()

    def warm():
        c = getattr(local, "conn", None)
        if c is None or c.closed:
            local.conn = _data._db.connect(_data._db.TRANSACTION)
        return local.conn

    def discard():
        c, local.conn = getattr(local, "conn", None), None
        if c is not None:
            try:
                c.close()
            except Exception:                                          # noqa: BLE001
                pass
    _data._warm_connection = warm
    _data._discard = discard


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=25)
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    ensure_users()
    reset()
    Client(USERS["viewer"])                       # imports the app (and web/lib/data.py)
    one_connection_per_person()
    crowd = people(a.users)
    world = seed()
    with owner() as c:
        audit0 = c.execute("select coalesce(max(id), 0) from kb.audit_log").fetchone()[0]

    lat: dict[str, list[float]] = defaultdict(list)
    status: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    writes = defaultdict(int)           # successful audited writes by kind
    lock = threading.Lock()
    deadline = time.time() + a.seconds

    def call(cl, label, method, path, body=None, query=""):
        t0 = time.perf_counter()
        s, out = cl.call(method, path, body, query)
        ms = (time.perf_counter() - t0) * 1000
        with lock:
            lat[label].append(ms)
            status[label][s] += 1
        return s, out

    def worker(uid: str, role: str, seed_: int):
        rng = random.Random(seed_)
        cl = Client(uid)
        seen_version = {}
        mine = 0
        while time.time() < deadline:
            r = rng.random()
            m, t = rng.choice(world["mods"]), rng.choice(world["topics"])
            if r < 0.18:
                call(cl, "GET /nodes (list)", "GET", "/api/kb/nodes", query="limit=50&sort=updated")
            elif r < 0.28:
                call(cl, "GET /search", "GET", "/api/kb/search", query="q=load%20" + rng.choice(["module", "topic", "1", "2"]))
            elif r < 0.38:
                call(cl, "GET /nodes/{id}/neighbourhood", "GET", f"/api/kb/nodes/{world['course']['id']}/neighbourhood", query="depth=2")
            elif r < 0.44:
                call(cl, "GET /dashboard", "GET", "/api/kb/dashboard")
            elif r < 0.50:
                call(cl, "GET /counts", "GET", "/api/kb/counts")
            elif r < 0.54:
                call(cl, "GET /activity", "GET", "/api/kb/activity", query="limit=50")
            elif r < 0.62:
                h = rng.choice(world["hot"])
                s, n = call(cl, "GET /nodes/{id}", "GET", f"/api/kb/nodes/{h['id']}")
                if s == 200:
                    seen_version[h["id"]] = n["version"]
            elif r < 0.74 and role != "viewer":
                # same-record conflict: save with the version last read (often stale)
                h = rng.choice(world["hot"])
                ver = seen_version.get(h["id"], 1)
                s, out = call(cl, "PATCH /nodes/{id}", "PATCH", f"/api/kb/nodes/{h['id']}", {"version": ver, "summary": f"edit by {uid[:6]} {rng.random():.6f}"})
                if s == 200:
                    with lock:
                        writes["node_update"] += 1
                    seen_version[h["id"]] = out["version"]
                elif s == 409:
                    seen_version[h["id"]] = (out.get("current") or {}).get("version", ver)
            elif r < 0.82 and role != "viewer":
                # relationship race: everyone tries the same few pairs
                pm, pt = world["mods"][rng.randrange(3)], world["topics"][rng.randrange(3)]
                s, _ = call(cl, "POST /edges", "POST", "/api/kb/edges", {"type": "covers", "source_id": pm["id"], "target_id": pt["id"]})
                if s == 201:
                    with lock:
                        writes["edge_insert"] += 1
            elif r < 0.90 and role != "viewer":
                # parallel graph edits in the shared layout
                call(cl, "POST /graph/positions", "POST", "/api/kb/graph/positions",
                     {"layout": "default", "positions": [{"node_id": m["id"], "x": rng.uniform(-500, 500), "y": rng.uniform(-500, 500)},
                                                         {"node_id": t["id"], "x": rng.uniform(-500, 500), "y": rng.uniform(-500, 500)}]})
            elif role in ("editor", "contributor"):
                mine += 1
                s, _ = call(cl, "POST /nodes", "POST", "/api/kb/nodes", {"type": "topic", "name": f"Load new {uid[:6]} {mine}"})
                if s == 201:
                    with lock:
                        writes["node_insert"] += 1
                elif s == 202:
                    with lock:
                        writes["proposal_insert"] += 1
            else:
                call(cl, "GET /nodes (list)", "GET", "/api/kb/nodes", query="limit=50&sort=name")

    threads = [threading.Thread(target=worker, args=(uid, role, i)) for i, (uid, role) in enumerate(crowd)]
    t0 = time.time()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    elapsed = time.time() - t0

    checks = {}
    with owner() as c:
        checks["duplicate_relationships"] = c.execute("""select count(*) from (select 1 from kb.edges where archived_at is null
            group by edge_type_id, source_id, target_id having count(*) > 1) x""").fetchone()[0]
        checks["duplicate_records"] = c.execute("""select count(*) from (select 1 from kb.nodes where archived_at is null
            group by type_id, coalesce(scope_id, '00000000-0000-0000-0000-000000000000'::uuid), name_norm having count(*) > 1) x""").fetchone()[0]
        checks["orphan_relationships"] = c.execute("""select count(*) from kb.edges e join kb.nodes s on s.id = e.source_id
            join kb.nodes t on t.id = e.target_id where e.archived_at is null and (s.archived_at is not null or t.archived_at is not null)""").fetchone()[0]
        aud = dict(c.execute("""select table_name || '_' || action, count(*) from kb.audit_log where id > %s
            and table_name in ('nodes', 'edges', 'proposals') group by 1""", (audit0,)).fetchall())
    # creates with placement also write a contains edge: count only the load's own writes
    checks["audit_node_updates"] = (aud.get("nodes_update", 0), writes["node_update"])
    checks["audit_node_inserts"] = (aud.get("nodes_insert", 0), writes["node_insert"])
    checks["audit_edge_inserts"] = (aud.get("edges_insert", 0), writes["edge_insert"])
    checks["audit_proposals"] = (aud.get("proposals_insert", 0), writes["proposal_insert"])
    patch = status["PATCH /nodes/{id}"]
    checks["rejected_saves_all_409"] = all(k in (200, 409, 403) for k in patch)
    total = sum(sum(v.values()) for v in status.values())
    errors5 = sum(n for v in status.values() for k, n in v.items() if k >= 500)

    rows = []
    for label in sorted(lat):
        xs = sorted(lat[label])
        p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]
        rows.append({"endpoint": label, "n": len(xs), "p50_ms": round(statistics.median(xs), 1), "p95_ms": round(p95, 1),
                     "statuses": dict(sorted(status[label].items()))})
    result = {"users": a.users, "seconds": round(elapsed, 1), "requests": total, "rps": round(total / elapsed, 1),
              "error_rate_5xx": round(errors5 / max(total, 1), 5), "checks": checks, "endpoints": rows}
    print(f"{a.users} users, {elapsed:.0f} s, {total} requests ({total / elapsed:.1f}/s), 5xx: {errors5}")
    print("| Endpoint | Requests | p50 ms | p95 ms | Statuses |")
    print("|---|---|---|---|---|")
    for x in rows:
        print(f"| {x['endpoint']} | {x['n']} | {x['p50_ms']} | {x['p95_ms']} | {x['statuses']} |")
    print(json.dumps(checks))
    ok = (checks["duplicate_relationships"] == 0 and checks["duplicate_records"] == 0 and checks["orphan_relationships"] == 0
          and checks["rejected_saves_all_409"] and errors5 == 0
          and all(x[0] == x[1] for k, x in checks.items() if k.startswith("audit_")))
    print("LOAD:", "PASS" if ok else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=2, default=str))
    reset()
    drop_people(a.users)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
