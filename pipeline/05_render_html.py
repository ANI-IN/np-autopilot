#!/usr/bin/env python3
"""Pass 5 — self-contained graph.html.

Render rules, all decided deliberately:

  * Connected core is shown BY DEFAULT. Isolated nodes are behind a toggle, and
    their COUNT IS IN THE LEGEND rather than discoverable only by clicking —
    the isolation is a real finding about the data, so it belongs on the face of
    the render.
  * Instructors with pipeline_status in_pipeline / rejected / lapsed are NOT
    rendered at all. 255 of them are hiring rejections about named external
    people. They stay in graph.json; this is a render filter.
  * expert_in edges are drawn dashed and labelled, because a self-declared form
    response must not look like teaching history.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import BUILD_LOG, KNOWLEDGE_DIR                # noqa: E402

OUT = KNOWLEDGE_DIR / "graph.html"

COLORS = {"theme": "#7c5cff", "workflow": "#4c8dff", "person": "#00b389",
          "domain": "#ff9500", "program": "#ff5c8a", "module": "#ffd23f",
          "instructor": "#00c2d1", "file": "#8a94a6"}


def main() -> int:
    g = json.loads((KNOWLEDGE_DIR / "graph.json").read_text(encoding="utf-8"))
    nodes, edges = g["nodes"], g["edges"]
    prov = taxonomy.edge_for_role("provenance")
    expert = taxonomy.edge_for_role("instructor_domain")

    renderable = [n for n in nodes
                  if n["type"] != "file"
                  and (n["type"] != "instructor" or n.get("renderable"))]
    keep = {n["id"] for n in renderable}
    redges = [e for e in edges
              if e["rel"] != prov and e["source"] in keep and e["target"] in keep]

    deg = defaultdict(int)
    for e in redges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    isolated = [n for n in renderable if deg[n["id"]] == 0]
    connected = [n for n in renderable if deg[n["id"]] > 0]

    slim = [{"id": n["id"], "l": n["label"][:70], "t": n["type"],
             "iso": deg[n["id"]] == 0, "d": deg[n["id"]],
             "st": n.get("pipeline_status", ""),
             "src": len({s.get("file") for s in n.get("sources", []) if s.get("file")})}
            for n in renderable]
    slim_e = [{"s": e["source"], "t": e["target"], "r": e["rel"],
               "b": e.get("basis", "")} for e in redges]

    counts = defaultdict(int)
    for n in renderable:
        counts[n["type"]] += 1
    ecounts = defaultdict(int)
    for e in redges:
        ecounts[e["rel"]] += 1

    payload = json.dumps({"nodes": slim, "edges": slim_e}, separators=(",", ":"))
    meta = g["meta"]
    legend = "".join(
        f'<span class="k"><i style="background:{COLORS.get(t,"#888")}"></i>'
        f'{t} <b>{counts[t]}</b></span>' for t in sorted(counts))
    erows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                    for k, v in sorted(ecounts.items(), key=lambda z: -z[1]))

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>NP Autopilot — knowledge graph</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
background:#0d1117;color:#e6edf3;overflow:hidden}}
#c{{position:fixed;inset:0}}
#panel{{position:fixed;top:0;left:0;width:320px;max-height:100vh;overflow-y:auto;
padding:16px;background:rgba(13,17,23,.94);border-right:1px solid #21262d}}
h1{{font-size:15px;margin:0 0 2px}}
.sub{{color:#8b949e;font-size:11px;margin-bottom:12px}}
.warn{{background:#2d1e00;border:1px solid #6b4b00;border-radius:6px;padding:9px;
margin:10px 0;font-size:11px;color:#f0c674}}
.k{{display:flex;align-items:center;gap:6px;font-size:11px;padding:1px 0}}
.k i{{width:9px;height:9px;border-radius:2px;display:inline-block}}
.k b{{margin-left:auto;color:#8b949e;font-variant-numeric:tabular-nums}}
h2{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#8b949e;
margin:14px 0 6px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
td{{padding:1px 0;color:#c9d1d9}} td:last-child{{text-align:right;color:#8b949e;
font-variant-numeric:tabular-nums}}
label{{display:flex;gap:7px;align-items:flex-start;font-size:11px;cursor:pointer;
padding:5px 0}}
input{{margin-top:2px}}
#tip{{position:fixed;pointer-events:none;background:#161b22;border:1px solid #30363d;
border-radius:5px;padding:6px 9px;font-size:11px;display:none;max-width:280px}}
.iso-note{{color:#f0c674;font-weight:600}}
</style></head><body>
<canvas id="c"></canvas><div id="tip"></div>
<div id="panel">
<h1>NP Autopilot</h1>
<div class="sub">built {meta['built_at'][:10]} &middot; taxonomy v{meta['taxonomy_version']}</div>

<div class="warn"><b>Built from a hand-exported local folder, not Google Drive.</b>
The three-tab NP Autopilot master spreadsheet has never been located. Counts for
person, instructor and module are floors, not totals.</div>

<h2>Nodes rendered</h2>
{legend}

<h2>Relationships</h2>
<table>{erows}</table>

<h2>View</h2>
<label><input type="checkbox" id="iso"><span>
<span class="iso-note">{len(isolated):,} nodes have no relationships</span> —
show them. They are real records that no file connects to anything.</span></label>
<label><input type="checkbox" id="hired" checked><span>
Include <b>hired</b> instructors ({sum(1 for n in renderable if n.get('pipeline_status')=='hired')})
alongside roster.</span></label>
<label><input type="checkbox" id="lbl" checked><span>Show labels on hover only</span></label>

<div class="warn" style="background:#0d2818;border-color:#1a5c36;color:#7ee2a8">
<b>{meta['render']['excluded_instructors']:,} instructors are excluded from this render.</b>
in_pipeline, rejected and lapsed — including hiring rejections about named
external people. They remain in graph.json for coverage queries.</div>

<div class="warn" style="background:#161b22;border-color:#30363d;color:#8b949e">
<b>Dashed edges are <code>expert_in</code></b> — a declared subject field, mostly
a Google Form response. Not evidence anyone has taught. Solid edges are observed
or inferred relationships.</div>
</div>
<script>
const D={payload};
const EXPERT={json.dumps(expert)};
const C={json.dumps(COLORS)};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
let W,H;function size(){{W=cv.width=innerWidth;H=cv.height=innerHeight}}size();addEventListener('resize',()=>{{size();draw()}});
const byId=new Map(D.nodes.map(n=>[n.id,n]));
D.nodes.forEach(n=>{{n.x=W/2+(Math.random()-.5)*600;n.y=H/2+(Math.random()-.5)*600;n.vx=0;n.vy=0}});
let showIso=false,showHired=true;
function active(){{return D.nodes.filter(n=>(showIso||!n.iso)&&(showHired||n.st!=='hired'))}}
function activeEdges(s){{const k=new Set(s.map(n=>n.id));return D.edges.filter(e=>k.has(e.s)&&k.has(e.t))}}
let A=[],E=[];
function refresh(){{A=active();E=activeEdges(A);}}
refresh();
function step(){{
  for(const n of A){{n.vx*=.86;n.vy*=.86;const dx=W/2-n.x,dy=H/2-n.y;n.vx+=dx*.0009;n.vy+=dy*.0009}}
  for(let i=0;i<A.length;i+=1){{const a=A[i];
    for(let j=i+1;j<Math.min(A.length,i+14);j+=1){{const b=A[j];
      let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;
      if(d2<9000){{const f=170/d2;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}}}}}}
  for(const e of E){{const a=byId.get(e.s),b=byId.get(e.t);if(!a||!b)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,f=(d-70)*.0055;
    a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f}}
  for(const n of A){{n.x+=n.vx;n.y+=n.vy}}
}}
function draw(){{
  ctx.clearRect(0,0,W,H);
  for(const e of E){{const a=byId.get(e.s),b=byId.get(e.t);if(!a||!b)continue;
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
    if(e.r===EXPERT){{ctx.setLineDash([3,4]);ctx.strokeStyle='rgba(0,194,209,.28)'}}
    else{{ctx.setLineDash([]);ctx.strokeStyle='rgba(139,148,158,.20)'}}
    ctx.lineWidth=1;ctx.stroke()}}
  ctx.setLineDash([]);
  for(const n of A){{ctx.beginPath();
    ctx.arc(n.x,n.y,n.iso?2:Math.min(3+Math.sqrt(n.d)*1.1,11),0,7);
    ctx.fillStyle=C[n.t]||'#888';ctx.globalAlpha=n.iso?.42:1;ctx.fill();ctx.globalAlpha=1}}
}}
(function loop(){{step();draw();requestAnimationFrame(loop)}})();
cv.addEventListener('mousemove',ev=>{{
  let best=null,bd=1e9;
  for(const n of A){{const d=Math.hypot(n.x-ev.clientX,n.y-ev.clientY);if(d<bd){{bd=d;best=n}}}}
  if(best&&bd<14){{tip.style.display='block';tip.style.left=(ev.clientX+12)+'px';
    tip.style.top=(ev.clientY+12)+'px';
    tip.innerHTML='<b>'+best.l+'</b><br>'+best.t+(best.st?' · '+best.st:'')+
      '<br>'+best.d+' relationships · '+best.src+' source file(s)'+
      (best.iso?'<br><span style="color:#f0c674">no relationships</span>':'')}}
  else tip.style.display='none'}});
document.getElementById('iso').onchange=e=>{{showIso=e.target.checked;refresh()}};
document.getElementById('hired').onchange=e=>{{showHired=e.target.checked;refresh()}};
</script></body></html>"""

    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print("=" * 78)
    print("PASS 5 — render graph.html")
    print("=" * 78)
    print(f"  rendered nodes    : {len(renderable):,}")
    print(f"    connected       : {len(connected):,}   (shown by default)")
    print(f"    isolated        : {len(isolated):,}   (behind a toggle, COUNT IN LEGEND)")
    print(f"  rendered edges    : {len(redges):,}")
    print(f"  excluded          : {meta['render']['excluded_instructors']:,} instructors "
          f"(in_pipeline / rejected / lapsed)")
    print(f"  file              : {OUT.relative_to(KNOWLEDGE_DIR.parent)}  {kb:.0f} KB, self-contained")
    print()
    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 05_render_html\n\n")
        fh.write(f"- graph.html {kb:.0f} KB | rendered {len(renderable)} nodes "
                 f"({len(connected)} connected, {len(isolated)} isolated) "
                 f"and {len(redges)} edges\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
