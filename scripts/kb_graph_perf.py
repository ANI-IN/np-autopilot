#!/usr/bin/env python3
"""Graph page load time and frame rate at 500, 2,000 and 5,000 records
(run 3, B3; run 6, B2: real-data-shaped graphs and the whole-graph overview).

LOCAL ONLY. Two ways to run it:

1. Synthetic (default): seeds records into the LOCAL TEST database named by
   NP_TEST_DSN (or SUPABASE_DB_URL_SESSION), truncating the kb content tables
   before and after, starts eval/kb_dev_server.py, drives Chrome headless.

     NP_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:54322/kbtest_b2 \
       python scripts/kb_graph_perf.py [--sizes 500,2000,5000] [--scenarios hub,tree] [--json out.json]

   Scenarios (records = N):
     hub   one hub with N-1 neighbours (+ ~2N relationships among them), opened as
           #/graph/<hub>?limit=N&bundle=0 -- every record drawn (the run-3 measurement;
           a page without bundling ignores bundle=0, so it also measures the old page)
     tree  shaped like the real data (docs/run6/GRAPH_PERF.md): domains > modules >
           weeks / sessions, ~88 % topics under modules, instructors teaching modules,
           themes > processes, team members. Opened as the whole-graph overview #/graph
           (default: satellites bundled) and #/graph?expand=all (every record drawn).

2. Real data, read only: --base http://localhost:8772 --email ... --password ...
   signs in on a running eval/kb_realdata_server.py and measures the overview
   (#/graph) and its fully expanded form. Nothing is seeded or deleted; prints
   counts and timings only.

Measured per row:
  load_ms      navigation -> the graph drawn (fetched, laid out, first frame)
  drawn        records drawn (not bundled away)
  fps_labels   frames per second panning + zooming for 3 s at zoom 0.5-1.2
  fps_far      the same at zoom 0.2-0.45 (labels mostly hidden)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]
if os.environ.get("NP_TEST_DSN"):
    os.environ.setdefault("SUPABASE_DB_URL_SESSION", os.environ["NP_TEST_DSN"])
    os.environ.setdefault("SUPABASE_DB_URL_TRANSACTION", os.environ.get("NP_TEST_DSN_TRANSACTION") or os.environ["NP_TEST_DSN"])

FPS_JS = """async ([z0, z1]) => {
  const cy = window.__kbGraph.cy; let frames = 0; const t0 = performance.now();
  const c = cy.elements(':visible').boundingBox(); const cx = (c.x1 + c.x2) / 2, cyy = (c.y1 + c.y2) / 2;
  await new Promise((done) => { const step = (t) => { frames++; const k = (t - t0) / 3000;
      const z = z0 + (z1 - z0) * Math.abs(Math.sin(k * Math.PI * 2));
      cy.viewport({ zoom: z, pan: { x: cy.width() / 2 - cx * z + 400 * Math.sin(k * 7), y: cy.height() / 2 - cyy * z + 300 * Math.cos(k * 5) } });
      if (t - t0 < 3000) requestAnimationFrame(step); else done(); };
    requestAnimationFrame(step); });
  return frames / ((performance.now() - t0) / 1000);
}"""

DRAWN_JS = "() => window.__kbGraph.cy.nodes(':visible').filter((n) => !n.hasClass('gbox') && !n.hasClass('ghead')).length"


def _types(c):
    return {k: i for k, i in c.execute("select key, id from kb.node_types").fetchall()}, \
           {k: i for k, i in c.execute("select key, id from kb.edge_types").fetchall()}


def seed_hub(n: int, rng: random.Random) -> str:
    from kb_support import owner
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        nt, et = _types(c)
        ids = [r[0] for r in c.execute("insert into kb.nodes (type_id, name) select %s, 'Perf topic ' || g from generate_series(1, %s) g returning id",
                                       (nt["topic"], n)).fetchall()]
        hub, rest = ids[0], ids[1:]
        pairs = {(hub, x) for x in rest}
        while len(pairs) < (n - 1) * 3:
            a, b = rng.sample(rest, 2)
            if (b, a) not in pairs:
                pairs.add((a, b))
        with c.cursor() as cur:
            cur.executemany("insert into kb.edges (edge_type_id, source_id, target_id) values (%s, %s, %s) on conflict do nothing",
                            [(et["related"], a, b) for a, b in pairs])
        return str(hub)


def seed_tree(n: int, rng: random.Random) -> None:
    """Real-data proportions (kb_realdata, current records, run 6): 4 domains, 20
    modules, 20 weeks, 134 sessions, 2,733 topics, 25 instructors, 16 themes,
    92 processes, 43 team members (3,087 records)."""
    from kb_support import owner
    share = {"domain": 4, "module": 20, "week": 20, "session": 134, "instructor": 25, "theme": 16, "process": 92, "team_member": 43}
    k = n / 3087
    cnt = {t: max(1, round(v * k)) for t, v in share.items()}
    cnt["topic"] = max(1, n - sum(cnt.values()))
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        nt, et = _types(c)
        ids: dict[str, list] = {}
        for t in ("domain", "module", "week", "session", "topic", "instructor", "theme", "process", "team_member"):
            ids[t] = [r[0] for r in c.execute(
                "insert into kb.nodes (type_id, name) select %s, %s || ' ' || g from generate_series(1, %s) g returning id",
                (nt[t], "Perf " + t.replace("_", " "), cnt[t])).fetchall()]
        edges, scope = [], []
        for i, m in enumerate(ids["module"]):
            d = ids["domain"][i % len(ids["domain"])]
            edges.append((et["contains"], d, m))
        for kind, rel in (("week", "contains"), ("session", "contains"), ("topic", "covers")):
            for i, x in enumerate(ids[kind]):
                m = ids["module"][i % len(ids["module"])]
                edges.append((et[rel], m, x)); scope.append((m, x))
        for i, x in enumerate(ids["process"]):
            edges.append((et["contains"], ids["theme"][i % len(ids["theme"])], x))
        for ins in ids["instructor"]:
            for m in rng.sample(ids["module"], min(3, len(ids["module"]))):
                edges.append((et["teaches"], ins, m))
        with c.cursor() as cur:
            cur.executemany("insert into kb.edges (edge_type_id, source_id, target_id) values (%s, %s, %s) on conflict do nothing", edges)
            cur.executemany("update kb.nodes set scope_id = %s where id = %s", scope)


def measure(page, url: str, renderer: str) -> dict:
    t0 = time.perf_counter()
    page.goto(url)
    page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=240000)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    load_ms = (time.perf_counter() - t0) * 1000
    drawn = page.evaluate(DRAWN_JS)
    fps = page.evaluate(FPS_JS, [0.5, 1.2])
    fps_far = page.evaluate(FPS_JS, [0.2, 0.45])
    gl = page.evaluate("() => !!window.__kbGraph.webgl")
    return {"renderer": renderer + ("" if (renderer == "webgl") == gl else " (canvas: fell back)"), "load_ms": round(load_ms),
            "drawn": drawn, "fps_labels": round(fps, 1), "fps_far": round(fps_far, 1)}


def table(rows: list[dict]) -> None:
    print("| Scenario | Records | Renderer | Drawn | Load (ms) | FPS, zoom 0.5-1.2 | FPS, zoom 0.2-0.45 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['scenario']} | {r['records']} | {r['renderer']} | {r['drawn']} | {r['load_ms']} | {r['fps_labels']} | {r['fps_far']} |")


def launch(p):
    return p.chromium.launch(channel="chrome", headless=True, args=["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])


def synthetic(a) -> list[dict]:
    from playwright.sync_api import sync_playwright
    from kb_support import USERS, dev_server, ensure_users, reset, token_for
    ensure_users()
    rows = []
    rng = random.Random(7)
    renderers = a.renderers.split(",")
    with dev_server() as base, sync_playwright() as p:
        b = launch(p)
        for scenario in a.scenarios.split(","):
            for n in [int(x) for x in a.sizes.split(",")]:
                reset()
                hub = seed_hub(n, rng) if scenario == "hub" else seed_tree(n, rng)
                urls = ([("hub", f"#/graph/{hub}?limit={n}&bundle=0")] if scenario == "hub"
                        else [("tree overview", "#/graph?x=1"), ("tree, all expanded", "#/graph?expand=all")])
                for label, route in urls:
                    for renderer in renderers:
                        ctx = b.new_context(viewport={"width": 1536, "height": 900})
                        sess = json.dumps({"access_token": token_for(USERS["editor"], ttl=3600), "expires_at": int(time.time()) + 3600,
                                           "user": {"email": "kbtest-editor@interviewkickstart.com"}})
                        ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)})")
                        page = ctx.new_page()
                        page.goto(base + "/kb/#/")
                        page.wait_for_selector("[data-testid=whoami]")
                        row = {"scenario": label, "records": n, **measure(page, base + "/kb/" + route + f"&renderer={renderer}", renderer)}
                        rows.append(row)
                        print(row, flush=True)
                        ctx.close()
        b.close()
    reset()
    return rows


def realdata(a) -> list[dict]:
    from playwright.sync_api import sync_playwright
    if urlparse(a.base).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("local servers only")
    rows = []
    with sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={"width": 1536, "height": 900})
        page = ctx.new_page()
        page.goto(a.base + "/local-login")
        page.fill("#email", a.email)
        page.fill("#password", a.password)
        page.click("#submit")
        page.wait_for_url("**/kb/**", timeout=60000)
        page.wait_for_selector("[data-testid=whoami]", timeout=60000)
        for label, route in (("real data overview", "#/graph?x=1"), ("real data, all expanded", "#/graph?expand=all"),
                             ("real data, legacy too", "#/graph?legacy=all")):
            for renderer in a.renderers.split(","):
                row = {"scenario": label, "records": None, **measure(page, a.base + "/kb/" + route + f"&renderer={renderer}", renderer)}
                row["records"] = page.evaluate("() => window.__kbGraph.total || null")
                rows.append(row)
                print(row, flush=True)
                page.goto(a.base + "/kb/#/")
        b.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="500,2000,5000")
    ap.add_argument("--scenarios", default="hub,tree")
    ap.add_argument("--renderers", default="canvas,webgl")
    ap.add_argument("--base", default="", help="a running local real-data server: measure it read-only")
    ap.add_argument("--email", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    rows = realdata(a) if a.base else synthetic(a)
    table(rows)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
