#!/usr/bin/env python3
"""Graph page load time and frame rate at 500, 2,000 and 5,000 visible nodes
(run 3, B3). LOCAL ONLY: seeds synthetic records into the local database
(truncating the kb content tables before and after), starts the dev server,
and drives system Chrome headless.

For each size it seeds a hub record with N-1 neighbours (plus ~2N extra
relationships among them), opens #/graph/<hub>?limit=N with each renderer, and
records:
  load_ms   navigation start -> the graph drawn (neighbourhood fetched, laid out)
  fps_pan   frames per second while panning and zooming continuously for 3 s

    python scripts/kb_graph_perf.py [--sizes 500,2000,5000] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api"), str(REPO / "tests")]
os.environ.setdefault("SUPABASE_DB_URL_SESSION", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
os.environ.setdefault("SUPABASE_DB_URL_TRANSACTION", "postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres")

from kb_support import USERS, dev_server, ensure_users, owner, reset, token_for   # noqa: E402

FPS_JS = """async () => {
  const cy = window.__kbGraph.cy; let frames = 0; const t0 = performance.now();
  await new Promise((done) => { const step = (t) => { frames++; const k = (t - t0) / 3000;
      cy.viewport({ zoom: 0.25 + 0.5 * Math.abs(Math.sin(k * Math.PI * 2)), pan: { x: 400 * Math.sin(k * 7), y: 300 * Math.cos(k * 5) } });
      if (t - t0 < 3000) requestAnimationFrame(step); else done(); };
    requestAnimationFrame(step); });
  return frames / ((performance.now() - t0) / 1000);
}"""


def seed(n: int, rng: random.Random) -> str:
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'system', false)")
        tid = c.execute("select id from kb.node_types where key = 'topic'").fetchone()[0]
        rel = c.execute("select id from kb.edge_types where key = 'related'").fetchone()[0]
        ids = [r[0] for r in c.execute("insert into kb.nodes (type_id, name) select %s, 'Perf topic ' || g from generate_series(1, %s) g returning id",
                                       (tid, n)).fetchall()]
        hub, rest = ids[0], ids[1:]
        pairs = {(hub, x) for x in rest}
        while len(pairs) < (n - 1) * 3:
            a, b = rng.sample(rest, 2)
            if (b, a) not in pairs:
                pairs.add((a, b))
        with c.cursor() as cur:
            cur.executemany("insert into kb.edges (edge_type_id, source_id, target_id) values (%s, %s, %s) on conflict do nothing",
                            [(rel, a, b) for a, b in pairs])
        return str(hub)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="500,2000,5000")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    ensure_users()
    rows = []
    rng = random.Random(7)
    with dev_server() as base, sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        for n in [int(x) for x in a.sizes.split(",")]:
            reset()
            hub = seed(n, rng)
            for renderer in ("canvas", "webgl"):
                ctx = b.new_context(viewport={"width": 1536, "height": 900})
                sess = json.dumps({"access_token": token_for(USERS["editor"], ttl=3600), "expires_at": int(time.time()) + 3600,
                                   "user": {"email": "kbtest-editor@interviewkickstart.com"}})
                ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)})")
                page = ctx.new_page()
                page.goto(base + "/kb/#/")
                page.wait_for_selector("[data-testid=whoami]")
                t0 = time.perf_counter()
                page.goto(base + f"/kb/#/graph/{hub}?limit={n}&renderer={renderer}")
                page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=180000)
                load_ms = (time.perf_counter() - t0) * 1000
                shown = page.evaluate("() => window.__kbGraph.cy.nodes(':visible').length")
                fps = page.evaluate(FPS_JS)
                gl = page.evaluate("() => !!window.__kbGraph.webgl")
                rows.append({"nodes": n, "visible": shown, "renderer": renderer + ("" if (renderer == "webgl") == gl else " (fell back)"),
                             "load_ms": round(load_ms), "fps_pan_zoom": round(fps, 1)})
                print(rows[-1], flush=True)
                ctx.close()
        b.close()
    reset()
    print("| Nodes | Renderer | Visible | Load (ms) | FPS while panning/zooming |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['nodes']} | {r['renderer']} | {r['visible']} | {r['load_ms']} | {r['fps_pan_zoom']} |")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
