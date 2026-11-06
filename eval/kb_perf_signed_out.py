#!/usr/bin/env python3
"""Signed-out page-load measurements on a deployment (the DEV preview): how long the
workspace takes to download and start (it boots up to the sign-in gate), how many
JavaScript modules and bytes it fetches before that, and the map page's load.
Timings and counts only. Use before and after a deploy.

    python eval/kb_perf_signed_out.py --base https://np-autopilot-kb-dev.vercel.app --bypass "$VERCEL_BYPASS" --label before
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--bypass"); ap.add_argument("--label", default="run")
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args()
    out = {"label": a.label, "base": a.base, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "kb": [], "map": []}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for i in range(a.repeat):
            for page_name, path, ready in (("kb", "/kb/", "() => { const g = document.getElementById('gate'); return g && !g.hidden; }"),
                                           ("map", "/", "() => document.readyState === 'complete'")):
                ctx = b.new_context(viewport={"width": 1536, "height": 900},
                                    extra_http_headers={"x-vercel-protection-bypass": a.bypass} if a.bypass else None)
                pg = ctx.new_page()
                reqs = []
                pg.on("requestfinished", lambda r: reqs.append(r))
                t0 = time.monotonic()
                pg.goto(a.base + path)
                pg.wait_for_function(ready, timeout=60000)
                ms = round((time.monotonic() - t0) * 1000)
                pg.wait_for_timeout(300)
                js = [r for r in reqs if r.url.split("?")[0].endswith(".js")]
                size = 0
                for r in js:
                    try:
                        size += int((r.response().headers or {}).get("content-length") or 0)
                    except Exception:
                        pass
                out[page_name].append({"ms": ms, "js_files": len(js), "js_bytes_wire": size, "requests": len(reqs)})
                ctx.close()
        b.close()
    dest = Path(__file__).resolve().parent.parent / ".measure" / "perf"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"signed-out-{a.label}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in ("kb", "map"):
        runs = out[k]
        print(f"{a.label} {k:3}: cold {runs[0]['ms']} ms, median {statistics.median(r['ms'] for r in runs)} ms, "
              f"JS files {runs[-1]['js_files']}, JS bytes on the wire {runs[-1]['js_bytes_wire']}, requests {runs[-1]['requests']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
