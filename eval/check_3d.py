#!/usr/bin/env python3
"""The 3D map, in a real browser with a GPU — what CI cannot run.

    python3 eval/check_3d.py [http://127.0.0.1:8765]

Against the local review server (eval/local_server.py). Every page is served
with the PRODUCTION Content-Security-Policy from vercel.json, so a bundle that
needed 'unsafe-eval' or a CDN would fail here. Checks, each printed with its
numbers:

  1. the 3D view loads (lazily) and renders the full default graph, with no
     CSP violation and no page error;
  2. a chip filters it in place (decks off: no visible decks, sessions stay);
  3. focus: the neighbourhood lights up, the panel opens, the camera moves;
  4. no WebGL -> the 2D map, with a note;
  5. prefers-reduced-motion: no drift, no auto-rotate;
  6. a hidden tab pauses rendering;
  7. frame time on the full default graph, and first render 3D vs 2D;
  8. a SLOW machine (requestAnimationFrame throttled by a busy-wait to well
     under 30 fps): 3D switches to 2D with the note, "Try 3D anyway" forces
     3D and it stays, and the choice survives a reload.
Exit 1 on any failed check.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipeline.lib import taxonomy                                        # noqa: E402

def _end(role: str) -> str:
    return taxonomy.edge_endpoints(taxonomy.edge_for_role(role))[1]


DECK, SESSION = _end("module_deck"), _end("module_session")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
GPU = ["--use-angle=metal", "--enable-gpu"] if sys.platform == "darwin" else ["--enable-gpu"]
CSP = [h["value"] for r in json.loads((REPO / "vercel.json").read_text())["headers"]
       for h in r["headers"] if h["key"].lower() == "content-security-policy"][0]
VIOLATIONS = """window.__CSP=[];document.addEventListener('securitypolicyviolation',
  e=>window.__CSP.push(e.violatedDirective+' '+e.blockedURI));"""
FPS = """()=>new Promise(res=>{const ts=[];function f(t){ts.push(t);if(ts.length<181)requestAnimationFrame(f);
  else{const d=ts.slice(1).map((x,i)=>x-ts[i]).sort((a,b)=>a-b);
  res({fps:+(1000/(d.reduce((a,b)=>a+b)/d.length)).toFixed(1),p95_ms:+d[Math.floor(d.length*.95)].toFixed(1)})}}
  requestAnimationFrame(f)})"""
#: a slow machine: every animation-frame callback busy-waits 45 ms first
THROTTLE = """(()=>{const raf=window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame=cb=>raf(t=>{const e=performance.now()+45;while(performance.now()<e);cb(t);});})();"""
failures: list[str] = []


def wait_until(pg, expr, timeout=30000):
    """Poll with evaluate(): Playwright's wait_for_function uses eval() in the
    page, which the production CSP (correctly) refuses."""
    waited = 0
    while waited < timeout:
        if pg.evaluate(f"() => !!({expr})"):
            return
        pg.wait_for_timeout(200); waited += 200
    raise TimeoutError(expr)


def check(name, ok, detail):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail}")
    if not ok:
        failures.append(name)


def page(browser, **kw):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2, **kw)
    def with_csp(route):
        resp = route.fetch()
        headers = dict(resp.headers)
        if "text/html" in headers.get("content-type", ""):
            # the review server's sign-in stub is an inline script the real
            # site never has: allow exactly that script, by its hash, and
            # nothing else — any other block still shows as a violation
            import base64, hashlib, re
            body = resp.text()
            m = re.search(r"<script>(/\* NP-LOCAL-PREVIEW-STUB.*?)</script>", body, re.S)
            csp = CSP
            if m:
                h = base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode()
                csp = csp.replace("script-src 'self'", f"script-src 'self' 'sha256-{h}'", 1)
            headers["content-security-policy"] = csp
            route.fulfill(status=resp.status, headers=headers, body=body)
            return
        route.fulfill(response=resp, headers=headers)
    ctx.route("**/*", with_csp)
    ctx.add_init_script(VIOLATIONS)
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    return ctx, pg, errs


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(args=GPU)
        # 1 + 7: load, render, first render, frame time
        ctx, pg, errs = page(b)
        pg.goto(BASE + "/")
        wait_until(pg, "window.__NP_3D&&window.__NP_3D.on&&window.__NP_3D.nodes>0")
        first3d = pg.evaluate("performance.now()")
        pg.wait_for_timeout(2500)
        s = pg.evaluate("window.__NP_3D")
        check("3D loads under the production CSP", s["on"] and s["nodes"] > 500 and not pg.evaluate("window.__CSP.length"),
              f"{s['nodes']} nodes, {s['links']} links, {s['labelsPlaced']} labels; bundle {s['loadMs']:.0f} ms; "
              f"CSP violations {pg.evaluate('window.__CSP')}; errors {errs[:2] or 'none'}")
        fr = pg.evaluate(FPS)
        check("60 fps on the full default graph", fr["fps"] >= 55,
              f"{fr['fps']} fps, p95 frame {fr['p95_ms']} ms, label overlay {s['labelMs']:.2f} ms/frame")
        # 2: chips
        pg.evaluate(f"toggleType('{DECK}')"); pg.wait_for_timeout(800)
        c = pg.evaluate("()=>{const v=[...V3.nodes.values()];return {decks:v.filter(n=>n.t===%r&&!n.ghost).length,"
                        "sessions:v.filter(n=>n.t===%r).length,list:state.listMode,on:V3.on}}" % (DECK, SESSION))
        check("a chip filters the 3D graph in place", c["decks"] == 0 and c["sessions"] > 100 and c["on"] and not c["list"], c)
        pg.evaluate(f"toggleType('{DECK}')"); pg.wait_for_timeout(500)
        # 3: focus
        before = pg.evaluate("(()=>{const p=V3.G.camera().position;return [p.x,p.y,p.z]})()")
        pg.evaluate("()=>{const n=D.nodes.find(x=>x.t==='module'&&x.dom==='backend'&&String((x.p||{}).sequence)==='3');focus3D(n.id);}")
        pg.wait_for_timeout(1800)
        f = pg.evaluate("""(()=>{const p=V3.G.camera().position;return {cam:[p.x,p.y,p.z],lit:V3.lit?V3.lit.size:0,
            panel:document.getElementById('right').style.display,title:document.getElementById('nl').textContent}})()""")
        moved = sum((a - b_) ** 2 for a, b_ in zip(before, f["cam"])) ** 0.5
        check("focus lights the neighbourhood, opens the panel, flies the camera",
              f["lit"] > 20 and f["panel"] == "block" and f["title"] == "API Design" and moved > 50,
              f"lit {f['lit']}, panel {f['panel']}, '{f['title']}', camera moved {moved:.0f}")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(600)
        check("Esc returns to the whole graph", pg.evaluate("!state.sel&&!V3.lit"), "focus cleared")
        # 6: hidden tab pauses
        pg.evaluate("()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});"
                    "document.dispatchEvent(new Event('visibilitychange'))}")
        n0 = pg.evaluate("V3.frame.n"); pg.wait_for_timeout(800); n1 = pg.evaluate("V3.frame.n")
        check("a hidden tab pauses the 3D view", n1 - n0 <= 1, f"{n1 - n0} label frames while hidden")
        ctx.close()
        # 7b: first render, 2D for comparison
        ctx, pg, _ = page(b)
        pg.goto(BASE + "/?dim=2d")
        wait_until(pg, "window.__NP_STATE&&window.__NP_STATE.frozen&&window.__NP_LABELS&&window.__NP_LABELS.length>0")
        first2d = pg.evaluate("performance.now()")
        print(f"  info first render: 3D {first3d:.0f} ms, 2D {first2d:.0f} ms (navigation start -> map on screen)")
        ctx.close()
        # 4: no WebGL -> 2D
        ctx, pg, errs = page(b)
        ctx.add_init_script("""const g=HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext=function(t,...a){return /webgl/.test(t)?null:g.call(this,t,...a)};""")
        pg.goto(BASE + "/"); pg.wait_for_timeout(3500)
        fb = pg.evaluate("({dim:state.dim,on:V3.on,failed:V3.failed,banner:document.getElementById('banner').textContent})")
        check("no WebGL falls back to the 2D map with a note", fb["dim"] == "2d" and not fb["on"] and "WebGL" in (fb["banner"] or ""), fb)
        ctx.close()
        # 5: reduced motion
        ctx, pg, _ = page(b, reduced_motion="reduce")
        pg.goto(BASE + "/"); wait_until(pg, "window.__NP_3D&&window.__NP_3D.on")
        pg.wait_for_timeout(1500)
        rm = pg.evaluate("({drift:drift,autoRotate:V3.ctrl.autoRotate})")
        check("reduced motion: no drift, no auto-rotate", rm == {"drift": False, "autoRotate": False}, rm)
        ctx.close()
        # 8: a slow machine
        ctx, pg, _ = page(b)
        ctx.add_init_script(THROTTLE)
        pg.goto(BASE + "/"); wait_until(pg, "window.__NP_3D&&window.__NP_3D.on")
        wait_until(pg, "state.dim==='2d'", timeout=15000)
        sw = pg.evaluate("({dim:state.dim,on:V3.on,url:location.search,"
                         "banner:document.getElementById('banner').textContent,"
                         "fps:(()=>{const s=V3.stamps||[];return s.length>1?+(1000*(s.length-1)/(s[s.length-1]-s[0])).toFixed(1):null})()})")
        check("a throttled 3D view switches to 2D with the note",
              sw["dim"] == "2d" and not sw["on"] and "Switched to 2D for smoother performance" in sw["banner"]
              and "Try 3D anyway" in sw["banner"], sw)
        pg.click("#force3d"); pg.wait_for_timeout(6500)
        fo = pg.evaluate("({dim:state.dim,on:V3.on,forced:localStorage.getItem('np.force3d'),"
                         "banner:document.getElementById('banner').textContent})")
        check("'Try 3D anyway' forces 3D and it stays", fo["dim"] == "3d" and fo["on"] and fo["forced"] == "1"
              and "Switched" not in fo["banner"], fo)
        pg.goto(BASE + "/"); wait_until(pg, "window.__NP_3D&&window.__NP_3D.on"); pg.wait_for_timeout(6500)
        rl = pg.evaluate("({dim:state.dim,on:V3.on})")
        check("the forced choice survives a reload", rl == {"dim": "3d", "on": True}, rl)
        ctx.close()
        b.close()
    print("\n  " + ("all 3D checks passed" if not failures else f"FAILED: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
