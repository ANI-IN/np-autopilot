#!/usr/bin/env python3
"""B3 before/after, LOCALLY: the same instrument both times.

Runs the real app (eval/local_server.py: only guard.identify stubbed) over the
local Supabase stack and measures:

  page       5 cold loads, each a fresh browser context: TTFB, first contentful
             paint, FIRST GRAPH FRAME (the structure view's first frame with
             its nodes) and SETTLED (the layout's own `frozen` flag — the
             simulation has stopped, not merely the network)
  cold start 5 fresh server PROCESSES: spawn -> ready, and the first
             /api/structure on the new process vs a warm one (the premium:
             endpoint import + first connect)
  bytes      /api/structure as sent, and its gzip-9 / brotli-11 equivalents,
             per node
  latency    p50/p95 over 20 samples per endpoint, after 2 warm-ups

LOCAL means laptop-to-Docker: no network, so absolute figures are far below
production's. The comparison is before vs after on this machine, not against
the production baseline's milliseconds.

    python3 eval/measure_local.py --label before --out <file.json>
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVER = [sys.executable, str(REPO / "eval" / "local_server.py")]
AUTH = {"Authorization": "Bearer local-harness", "Accept-Encoding": "br, gzip"}

try:
    import brotli
except ImportError:                                                    # pragma: no cover
    brotli = None


def spawn():
    t0 = time.perf_counter()
    p = subprocess.Popen(SERVER, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=REPO)
    line = p.stdout.readline()
    if not line.startswith("READY"):
        p.kill()
        raise SystemExit(f"server did not start: {line!r} {p.stderr.read()[-800:]}")
    return p, int(line.split()[1]), (time.perf_counter() - t0) * 1000


def get(base, path, extra=None):
    req = urllib.request.Request(base + path, headers={**AUTH, **(extra or {})})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body, status, headers = r.read(), r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        body, status, headers = e.read(), e.code, {k.lower(): v for k, v in e.headers.items()}
    return (time.perf_counter() - t0) * 1000, status, body, headers


def decoded(body, headers):
    enc = (headers.get("content-encoding") or "").lower()
    if enc == "br":
        return brotli.decompress(body)
    if enc == "gzip":
        return gzip.decompress(body)
    return body


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def endpoints(base, node_id):
    out = {}
    paths = {"/api/structure": "/api/structure",
             "/api/node": f"/api/node?id={node_id}",
             "/api/search?q=api": "/api/search?q=api",
             "/api/overview": "/api/overview",
             "/api/me": "/api/me",
             "/api/config": "/api/config"}
    for name, path in paths.items():
        for _ in range(2):
            get(base, path)
        samples, status, wire, headers = [], None, 0, {}
        for _ in range(20):
            ms, status, body, headers = get(base, path)
            samples.append(ms)
            wire = len(body)
        if status != 200:
            raise SystemExit(f"{name}: HTTP {status} — refusing to time an error")
        out[name] = {"p50": round(statistics.median(samples), 1),
                     "p95": round(pct(samples, .95), 1), "bytes_wire": wire,
                     "encoding": headers.get("content-encoding") or "identity"}
        etag = headers.get("etag")
        if etag:
            s304 = []
            for _ in range(20):
                ms, st, body, _h = get(base, path, {"If-None-Match": etag})
                s304.append(ms)
            out[name + " (If-None-Match)"] = {
                "p50": round(statistics.median(s304), 1),
                "p95": round(pct(s304, .95), 1), "status": st,
                "bytes_wire": len(body)}
    return out


def payload(base):
    _ms, status, body, headers = get(base, "/api/structure")
    raw = decoded(body, headers)
    obj = json.loads(raw)
    n = obj.get("n") or len(obj.get("nodes") or obj.get("ids") or [])
    out = {"nodes": n, "wire_bytes": len(body),
           "encoding": headers.get("content-encoding") or "identity",
           "json_bytes": len(raw), "gzip9_bytes": len(gzip.compress(raw, 9))}
    if brotli:
        out["brotli11_bytes"] = len(brotli.compress(raw, quality=11))
    for k in ("wire_bytes", "json_bytes", "gzip9_bytes", "brotli11_bytes"):
        if k in out:
            out[k.replace("_bytes", "_per_node")] = round(out[k] / n, 1)
    return out, obj


PROBE = """
(() => {
  window.__NP_MEASURE = {};
  const M = window.__NP_MEASURE;
  (function poll(){
    const s = window.__NP_STATE;
    if (s && s.nodes > 1000 && M.firstGraph === undefined) M.firstGraph = performance.now();
    if (s && s.nodes > 1000 && s.frozen && M.settled === undefined) M.settled = performance.now();
    if (M.settled === undefined) requestAnimationFrame(poll);
  })();
  try {
    const k = (window.__NP && window.__NP.sessionKey) || 'np_session';
    localStorage.setItem(k, JSON.stringify({access_token:'local', refresh_token:'local',
      expires_at: Math.floor(Date.now()/1000) + 86400}));
  } catch (e) {}
})();
"""


def page_loads(base, runs=5):
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for _ in range(runs):
            ctx = b.new_context(viewport={"width": 1500, "height": 950})
            ctx.add_init_script(PROBE)
            page = ctx.new_page()
            page.goto(base + "/", wait_until="load")
            page.wait_for_function("window.__NP_MEASURE && window.__NP_MEASURE.settled",
                                   timeout=120000, polling=100)
            nav = page.evaluate("""() => {
              const n = performance.getEntriesByType('navigation')[0];
              const fcp = performance.getEntriesByName('first-contentful-paint')[0];
              const s = performance.getEntriesByName(location.origin + '/api/structure')[0]
                     || performance.getEntriesByType('resource').find(r => r.name.includes('/api/structure'));
              return {ttfb: n.responseStart, fcp: fcp ? fcp.startTime : null,
                      firstGraph: window.__NP_MEASURE.firstGraph,
                      settled: window.__NP_MEASURE.settled,
                      structure_ms: s ? s.duration : null,
                      frames: window.__NP_STATE.settle};
            }""")
            rows.append({k: (round(v, 1) if isinstance(v, (int, float)) else v)
                         for k, v in nav.items()})
            ctx.close()
        b.close()
    summary = {}
    for k in ("ttfb", "fcp", "structure_ms", "firstGraph", "settled", "frames"):
        vals = [r[k] for r in rows if r[k] is not None]
        if vals:
            summary[k] = {"median": round(statistics.median(vals), 1),
                          "min": min(vals), "max": max(vals)}
    return {"runs": rows, "summary": summary}


def cold_starts(runs=5):
    rows = []
    for _ in range(runs):
        p, port, ready_ms = spawn()
        base = f"http://127.0.0.1:{port}"
        first, st, _b, _h = get(base, "/api/structure")
        warm = statistics.median(get(base, "/api/structure")[0] for _ in range(5))
        p.kill()
        p.wait()
        if st != 200:
            raise SystemExit(f"cold /api/structure: HTTP {st}")
        rows.append({"spawn_to_ready_ms": round(ready_ms, 1),
                     "first_structure_ms": round(first, 1),
                     "warm_structure_ms": round(warm, 1),
                     "premium_ms": round(first - warm, 1)})
    return {"runs": rows,
            "median": {k: round(statistics.median(r[k] for r in rows), 1)
                       for k in rows[0]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    proc, port, _ = spawn()
    base = f"http://127.0.0.1:{port}"
    try:
        size, obj = payload(base)
        if "ids" in obj:
            node_id = obj["ids"][0]
        else:
            node_id = obj["nodes"][0]["id"]
        lat = endpoints(base, node_id)
        pages = page_loads(base)
    finally:
        proc.kill()
        proc.wait()
    cold = cold_starts()
    result = {"label": a.label, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "payload": size, "latency": lat, "page": pages["summary"],
              "page_runs": pages["runs"], "cold_start": cold}
    Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("label", "payload", "page")}, indent=1))
    print("cold start (median):", cold["median"])
    for k, v in lat.items():
        print(f"  {k:<32} p50 {v['p50']:>8} ms  p95 {v['p95']:>8} ms  {v.get('bytes_wire')} B {v.get('encoding','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
