#!/usr/bin/env python3
"""Seed ~5,000 SYNTHETIC KB nodes and ~15,000 edges into the LOCAL database and
measure p50/p95 latency of list, search and neighbourhood requests through the
real WSGI app (token verification + RLS included). LOCAL ONLY: refuses any
non-loopback DSN, and truncates the kb content tables before and after.

    python scripts/kb_perf.py [--runs 40] [--keep]
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]

import os                                                              # noqa: E402

os.environ.setdefault("SUPABASE_DB_URL_SESSION", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
os.environ.setdefault("SUPABASE_DB_URL_TRANSACTION", "postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres")

from kb_support import USERS, Client, ensure_users, owner, reset      # noqa: E402

COUNTS = {"program": 50, "course": 150, "module": 800, "topic": 4000}


def seed(rng: random.Random) -> dict:
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        ids = {}
        for t, n in COUNTS.items():
            rows = c.execute(
                "insert into kb.nodes (type_id, name, summary) "
                "select (select id from kb.node_types where key = %s), %s || ' ' || g, "
                "'synthetic perf record ' || g || ' about ' || (array['graphs','caching','queues','sorting','consensus'])[1 + g %% 5] "
                "from generate_series(1, %s) g returning id", (t, f"Perf {t}", n)).fetchall()
            ids[t] = [r[0] for r in rows]
        et = {k: c.execute("select id from kb.edge_types where key = %s", (k,)).fetchone()[0]
              for k in ("contains", "covers", "related")}
        pairs = set()
        for p in ids["program"]:
            for cid in rng.sample(ids["course"], 3):
                pairs.add((et["contains"], p, cid))
        for m in ids["module"]:
            pairs.add((et["contains"], rng.choice(ids["course"]), m))
            for t in rng.sample(ids["topic"], 3):
                pairs.add((et["covers"], m, t))
        hub = ids["topic"][0]
        for t in ids["topic"][1:601]:
            pairs.add((et["related"], hub, t))                 # one 600-edge hub
        while len(pairs) < 15000:
            a, b = rng.sample(ids["topic"], 2)
            pairs.add((et["related"], a, b))
        with c.cursor() as cur:
            cur.executemany("insert into kb.edges (edge_type_id, source_id, target_id) values (%s,%s,%s) "
                            "on conflict do nothing", list(pairs))
        total = c.execute("select (select count(*) from kb.nodes), (select count(*) from kb.edges)").fetchone()
    return {"ids": ids, "hub": hub, "nodes": total[0], "edges": total[1]}


def timed(fn, runs):
    out = []
    for _ in range(runs):
        t0 = time.perf_counter()
        s, body = fn()
        out.append((time.perf_counter() - t0) * 1000)
        assert s == 200, body
    out.sort()
    return {"p50": round(statistics.median(out), 1), "p95": round(out[int(len(out) * 0.95) - 1], 1),
            "max": round(out[-1], 1), "runs": runs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=40)
    ap.add_argument("--keep", action="store_true", help="leave the synthetic data in place")
    args = ap.parse_args()
    rng = random.Random(42)
    ensure_users()
    reset()
    t0 = time.perf_counter()
    data = seed(rng)
    print(f"seeded {data['nodes']} nodes, {data['edges']} edges in {time.perf_counter() - t0:.1f}s")
    with owner() as c:
        c.execute("analyze kb.nodes; analyze kb.edges")
    api = Client(USERS["viewer"])
    import io
    import contextlib
    sink = io.StringIO()                          # the per-request audit line goes to stdout
    topics = data["ids"]["topic"]
    cases = {
        "list: first page (updated)": lambda: api.get("/api/kb/nodes", "limit=50"),
        "list: type=topic sorted by name": lambda: api.get("/api/kb/nodes", "type=topic&sort=name&limit=50"),
        "list: text filter q=caching": lambda: api.get("/api/kb/nodes", "q=caching&limit=50"),
        "search: full text 'consensus'": lambda: api.get("/api/kb/search", "q=consensus"),
        "search: fuzzy 'perf topik 12'": lambda: api.get("/api/kb/search", "q=perf%20topik%2012"),
        "neighbourhood: depth 1, random topic": lambda: api.get(f"/api/kb/nodes/{rng.choice(topics)}/neighbourhood", "depth=1"),
        "neighbourhood: depth 2, random topic": lambda: api.get(f"/api/kb/nodes/{rng.choice(topics)}/neighbourhood", "depth=2"),
        "neighbourhood: depth 1, 600-edge hub (capped 300)": lambda: api.get(f"/api/kb/nodes/{data['hub']}/neighbourhood", "depth=1"),
        "node detail: hub": lambda: api.get(f"/api/kb/nodes/{data['hub']}"),
        # run 6 (B5): the one graph read API and the screens behind it
        "graph: first page (2,000 records)": lambda: api.get("/api/kb/graph"),
        "graph: archived=1 (degree counts archived edges)": lambda: api.get("/api/kb/graph", "archived=1&limit=500"),
        "graph focus: depth 1, random topic": lambda: api.get("/api/kb/graph", f"focus={rng.choice(topics)}&depth=1"),
        "graph focus: depth 2, random topic": lambda: api.get("/api/kb/graph", f"focus={rng.choice(topics)}&depth=2"),
        "graph focus: depth 1, 600-edge hub": lambda: api.get("/api/kb/graph", f"focus={data['hub']}&depth=1"),
        "outline": lambda: api.get("/api/kb/outline"),
        "who teaches what": lambda: api.get("/api/kb/views/teaching"),
        "programme timeline": lambda: api.get("/api/kb/views/timeline"),
        "data quality (cached duplicates after the first)": lambda: api.get("/api/kb/quality"),
    }
    results = {}
    with contextlib.redirect_stdout(sink):
        for name, fn in cases.items():
            fn()                                   # warm
            results[name] = timed(fn, args.runs)
        s, hubnb = api.get(f"/api/kb/nodes/{data['hub']}/neighbourhood", "depth=1")
    print("\n| Request | p50 ms | p95 ms | max ms | runs |\n|---|---|---|---|---|")
    for name, r in results.items():
        print(f"| {name} | {r['p50']} | {r['p95']} | {r['max']} | {r['runs']} |")
    # Uncached duplicate detection over the synthetic names, once: the seed names
    # every record "Perf <type> <n>", so nearly every same-type pair is similar
    # (the worst case for any similarity join; the real data is far kinder).
    from lib.kb import duplicates
    duplicates._CACHE.clear()
    with contextlib.redirect_stdout(sink):
        t0 = time.perf_counter()
        api.get("/api/kb/quality/duplicates")
    print(f"| duplicates, uncached, worst case (all names alike) | {(time.perf_counter() - t0) * 1000:.0f} | | | 1 |")
    print(f"\nhub neighbourhood: returned {len(hubnb['nodes'])} of total {hubnb['total']} (truncated={hubnb['truncated']})")
    if not args.keep:
        reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
