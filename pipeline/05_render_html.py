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
from pipeline.lib.render_logic import LOGIC                             # noqa: E402

OUT = KNOWLEDGE_DIR / "graph.html"

COLORS = {"theme": "#7c5cff", "workflow": "#4c8dff", "person": "#00b389",
          "domain": "#ff9500", "program": "#ff5c8a", "module": "#ffd23f",
          "instructor": "#00c2d1", "file": "#8a94a6"}


def main() -> int:
    g = json.loads((KNOWLEDGE_DIR / "graph.json").read_text(encoding="utf-8"))
    nodes, edges = g["nodes"], g["edges"]
    prov = taxonomy.edge_for_role("provenance")
    expert = taxonomy.edge_for_role("instructor_domain")

    BY = {n["id"]: n for n in nodes}
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

    def files_of(n):
        seen, out_f = set(), []
        for s in n.get("sources", []):
            f = s.get("file")
            if f and f not in seen:
                seen.add(f)
                out_f.append({"f": f, "sh": s.get("sheet"), "r": s.get("row")})
            if len(out_f) >= 4:
                break
        return out_f

    theme_of = {}
    for e in redges:
        if e["rel"] == taxonomy.edge_for_role("workflow_theme"):
            theme_of[e["source"]] = BY.get(e["target"], {}).get("theme_id")

    slim = [{"id": n["id"], "l": n["label"][:70], "t": n["type"],
             "iso": deg[n["id"]] == 0, "d": deg[n["id"]],
             "st": n.get("pipeline_status", ""),
             "th": n.get("theme_id", theme_of.get(n["id"])),
             "wid": n.get("workflow_id"),
             "eff": n.get("effort"), "al": len(n.get("alerts") or []),
             "src": len({s.get("file") for s in n.get("sources", []) if s.get("file")}),
             "files": files_of(n)}
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
    colors = json.dumps(COLORS)
    expert_js = json.dumps(expert)   # edge name from the single source, never a literal
    logic = LOGIC
    # same logic, written out so eval/drive_render.mjs executes the SHIPPED code
    (KNOWLEDGE_DIR / "_graph_logic.mjs").write_text(LOGIC, encoding="utf-8")
    (KNOWLEDGE_DIR / "_graph_data.json").write_text(payload, encoding="utf-8")
    meta = g["meta"]
    legend = "".join(
        f'<span class="k"><i style="background:{COLORS.get(t,"#888")}"></i>'
        f'{t} <b>{counts[t]}</b></span>' for t in sorted(counts))
    erows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                    for k, v in sorted(ecounts.items(), key=lambda z: -z[1]))

    themes = sorted(((n.get("theme_id"), n["label"]) for n in renderable
                     if n["type"] == "theme"), key=lambda z: z[0] or 0)
    theme_opts = "".join(f'<option value="{i}">{i}. {l}</option>' for i, l in themes)
    type_boxes = "".join(
        f'<label class="tf"><input type="checkbox" class="ty" value="{ty}" '
        f'{"checked" if ty != "instructor" else "checked"}>'
        f'<i style="background:{COLORS.get(ty,"#888")}"></i>{ty}'
        f'<b>{counts[ty]}</b></label>' for ty in sorted(counts))
    erows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                    for k, v in sorted(ecounts.items(), key=lambda z: -z[1]))

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>NP Autopilot — knowledge graph</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
background:#0d1117;color:#e6edf3;overflow:hidden}}
#c{{position:fixed;inset:0}}
.pane{{position:fixed;top:0;bottom:0;overflow-y:auto;padding:14px;
background:rgba(13,17,23,.95);border-color:#21262d}}
#left{{left:0;width:300px;border-right:1px solid #21262d}}
#right{{right:0;width:330px;border-left:1px solid #21262d;display:none}}
h1{{font-size:15px;margin:0 0 2px}}
.sub{{color:#8b949e;font-size:11px;margin-bottom:10px}}
.warn{{background:#2d1e00;border:1px solid #6b4b00;border-radius:6px;padding:8px;
margin:8px 0;font-size:10.5px;color:#f0c674;line-height:1.45}}
h2{{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:#8b949e;
margin:14px 0 6px}}
input[type=search],select{{width:100%;background:#0d1117;border:1px solid #30363d;
color:#e6edf3;border-radius:6px;padding:6px 8px;font-size:12px;font-family:inherit}}
input[type=search]:focus,select:focus{{outline:none;border-color:#4c8dff}}
.tf{{display:flex;align-items:center;gap:6px;font-size:11px;padding:2px 0;cursor:pointer}}
.tf i{{width:9px;height:9px;border-radius:2px}}
.tf b{{margin-left:auto;color:#8b949e;font-weight:400;font-variant-numeric:tabular-nums}}
label.ck{{display:flex;gap:7px;align-items:flex-start;font-size:11px;cursor:pointer;padding:4px 0}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
td{{padding:1px 0;color:#c9d1d9}} td:last-child{{text-align:right;color:#8b949e;
font-variant-numeric:tabular-nums}}
#res{{margin-top:6px;max-height:190px;overflow-y:auto}}
.hit{{padding:4px 6px;border-radius:5px;cursor:pointer;font-size:11.5px;
display:flex;gap:6px;align-items:center}}
.hit:hover{{background:#161b22}} .hit i{{width:7px;height:7px;border-radius:2px;flex:none}}
.hit span{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.hit em{{color:#8b949e;font-style:normal;margin-left:auto;font-size:10px;flex:none}}
#tip{{position:fixed;pointer-events:none;background:#161b22;border:1px solid #30363d;
border-radius:5px;padding:6px 9px;font-size:11px;display:none;max-width:290px;z-index:9}}
.nb{{font-size:11px;padding:3px 0;border-bottom:1px solid #161b22;cursor:pointer}}
.nb:hover{{color:#4c8dff}}
.rel{{color:#8b949e;font-size:10px}}
.dash{{color:#00c2d1}}
.src{{font-size:10px;color:#8b949e;word-break:break-all;padding:2px 0}}
button{{background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:5px;
padding:4px 8px;font-size:11px;cursor:pointer;font-family:inherit}}
button:hover{{border-color:#4c8dff}}
#close{{float:right}}
.iso-note{{color:#f0c674;font-weight:600}}
#stat{{font-size:10.5px;color:#8b949e;margin-top:8px;font-variant-numeric:tabular-nums}}
</style></head><body>
<canvas id="c"></canvas><div id="tip"></div>

<div class="pane" id="left">
<h1>NP Autopilot</h1>
<div class="sub">built {meta['built_at'][:10]} &middot; taxonomy v{meta['taxonomy_version']}</div>

<div class="warn"><b>Built from a hand-exported local folder, not Google Drive.</b>
The three-tab master spreadsheet has never been located. person / instructor /
module counts are floors, not totals.</div>

<h2>Search</h2>
<input type="search" id="q" placeholder="name or type — try 8.2, rating, Animesh" autocomplete="off">
<div id="res"></div>

<h2>Theme</h2>
<select id="th"><option value="">All themes (component A + B)</option>{theme_opts}</select>

<h2>Node types</h2>
{type_boxes}

<h2>View</h2>
<label class="ck"><input type="checkbox" id="iso"><span>
<span class="iso-note">{len(isolated):,} nodes have no relationships</span> — show them.</span></label>
<label class="ck"><input type="checkbox" id="hired" checked><span>Include <b>hired</b> instructors alongside roster</span></label>
<label class="ck"><input type="checkbox" id="dash" checked><span>Show dashed <b>expert_in</b> edges (declared, not taught)</span></label>
<label class="ck"><input type="checkbox" id="sep" checked><span>Separate disconnected components</span></label>
<div id="stat"></div>

<h2>Relationships</h2>
<table>{erows}</table>

<div class="warn" style="background:#0d2818;border-color:#1a5c36;color:#7ee2a8">
<b>{meta['render']['excluded_instructors']:,} instructors excluded from this render.</b>
in_pipeline, rejected and lapsed — including hiring rejections about named
external people. They stay in graph.json for coverage queries.</div>

<div class="warn" style="background:#161b22;border-color:#30363d;color:#8b949e">
<b>Dashed = <code>expert_in</code></b>, a declared subject field, mostly a Google
Form response. Not evidence anyone has taught.</div>
</div>

<div class="pane" id="right">
<button id="close">close</button>
<h1 id="nl"></h1><div class="sub" id="nt"></div>
<div id="nprops"></div>
<h2>Connections (<span id="ncount">0</span>)</h2>
<div id="nbrs"></div>
<div id="more"></div>
<h2>Source files</h2>
<div id="files"></div>
</div>

<script type="module">
{logic}

const D={payload};
const C={colors};
const EXPERT={expert_js};
const CAP=8;
const idx=buildIndex(D);
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
let W,H;function size(){{W=cv.width=innerWidth;H=cv.height=innerHeight}}size();
addEventListener('resize',size);
const t0=performance.now();

const state={{types:new Set([...document.querySelectorAll('.ty')].map(e=>e.value)),
  themes:null,showIso:false,showHired:true,showDash:true,separate:true,
  sel:null,expanded:new Set()}};
const allDeg=degreeMap(D,D.nodes.map(n=>n.id));
let A=[],E=[],anchors=new Map();

function recompute(){{
  A=visible(D,{{types:state.types,themes:state.themes,showIso:state.showIso,
    showHired:state.showHired,degree:allDeg}});
  const ids=new Set(A.map(n=>n.id));
  E=D.edges.filter(e=>ids.has(e.s)&&ids.has(e.t)&&(state.showDash||e.r!==EXPERT));
  // component-aware anchors: each disconnected component gets its OWN centre,
  // otherwise a single global centring force drags them into one ball.
  anchors=new Map();
  if(state.separate){{
    const comps=components({{nodes:A,edges:E}},A.map(n=>n.id));
    const cols=Math.ceil(Math.sqrt(comps.length))||1;
    comps.forEach((c,i)=>{{
      const cx=(0.5+(i%cols))/cols*W*0.86+W*0.09;
      const cy=(0.5+Math.floor(i/cols))/Math.ceil(comps.length/cols)*H*0.86+H*0.07;
      for(const id of c) anchors.set(id,[cx,cy,c.length]);
    }});
    document.getElementById('stat').textContent=
      A.length+' nodes / '+E.length+' edges / '+comps.length+' components';
  }} else {{
    for(const n of A) anchors.set(n.id,[W/2,H/2,A.length]);
    document.getElementById('stat').textContent=A.length+' nodes / '+E.length+' edges';
  }}
  for(const n of A){{ if(n.x===undefined){{const a=anchors.get(n.id)||[W/2,H/2];
    n.x=a[0]+(Math.random()-.5)*120;n.y=a[1]+(Math.random()-.5)*120;n.vx=0;n.vy=0;}} }}
}}
recompute();

function step(){{
  for(const n of A){{n.vx*=.85;n.vy*=.85;
    const a=anchors.get(n.id);if(a){{n.vx+=(a[0]-n.x)*.006;n.vy+=(a[1]-n.y)*.006}}}}
  for(let i=0;i<A.length;i++){{const a=A[i];
    for(let j=i+1;j<Math.min(A.length,i+12);j++){{const b=A[j];
      const dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;
      if(d2<5000){{const f=110/d2;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}}}}}}
  for(const e of E){{const a=idx.byId.get(e.s),b=idx.byId.get(e.t);
    if(!a||!b||a.x===undefined||b.x===undefined)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,f=(d-58)*.006;
    a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f}}
  for(const n of A){{n.x+=n.vx;n.y+=n.vy}}
}}
function draw(){{
  ctx.clearRect(0,0,W,H);
  for(const e of E){{const a=idx.byId.get(e.s),b=idx.byId.get(e.t);
    if(!a||!b||a.x===undefined)continue;
    const hot=state.sel&&(e.s===state.sel||e.t===state.sel);
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
    if(e.r===EXPERT){{ctx.setLineDash([3,4]);
      ctx.strokeStyle=hot?'rgba(0,194,209,.9)':'rgba(0,194,209,.22)'}}
    else{{ctx.setLineDash([]);
      ctx.strokeStyle=hot?'rgba(230,237,243,.85)':'rgba(139,148,158,.17)'}}
    ctx.lineWidth=hot?1.8:1;ctx.stroke()}}
  ctx.setLineDash([]);
  for(const n of A){{if(n.x===undefined)continue;
    const sel=state.sel===n.id;
    ctx.beginPath();ctx.arc(n.x,n.y,n.iso?2:Math.min(3+Math.sqrt(n.d)*1.1,11),0,7);
    ctx.fillStyle=C[n.t]||'#888';ctx.globalAlpha=n.iso?.4:1;ctx.fill();
    if(sel){{ctx.globalAlpha=1;ctx.lineWidth=2;ctx.strokeStyle='#fff';ctx.stroke()}}
    ctx.globalAlpha=1}}
}}
let frames=0,ready=null;
(function loop(){{step();draw();frames++;
  if(frames===120&&!ready)ready=performance.now()-t0;
  requestAnimationFrame(loop)}})();

function hit(x,y){{let best=null,bd=1e9;
  for(const n of A){{if(n.x===undefined)continue;
    const d=Math.hypot(n.x-x,n.y-y);if(d<bd){{bd=d;best=n}}}}
  return bd<14?best:null}}
cv.addEventListener('mousemove',ev=>{{const n=hit(ev.clientX,ev.clientY);
  if(n){{tip.style.display='block';tip.style.left=(ev.clientX+12)+'px';
    tip.style.top=(ev.clientY+12)+'px';
    tip.innerHTML='<b>'+n.l+'</b><br>'+n.t+(n.st?' &middot; '+n.st:'')+
      '<br>'+n.d+' relationships &middot; click to open'}}
  else tip.style.display='none'}});
cv.addEventListener('click',ev=>{{const n=hit(ev.clientX,ev.clientY);
  if(n)open(n.id);else close()}});

function open(id){{
  state.sel=id;const n=idx.byId.get(id);
  document.getElementById('right').style.display='block';
  document.getElementById('nl').textContent=n.l;
  document.getElementById('nt').textContent=n.t+(n.st?' · '+n.st:'')+
    (n.wid?' · workflow '+n.wid:'');
  const pr=[];
  if(n.eff)pr.push('<div class="src"><b>Effort:</b> '+n.eff+'</div>');
  if(n.al)pr.push('<div class="src"><b>Alerts:</b> '+n.al+' recorded</div>');
  document.getElementById('nprops').innerHTML=pr.join('');
  const nb=neighboursOf(idx,id,CAP,state.expanded.has(id));
  document.getElementById('ncount').textContent=nb.total;
  document.getElementById('nbrs').innerHTML=nb.shown.map(x=>{{
    const o=idx.byId.get(x.o);if(!o)return '';
    const dash=x.r===EXPERT?' <span class="dash">(declared)</span>':'';
    return '<div class="nb" data-id="'+x.o+'">'+o.l+
      '<div class="rel">'+x.r+' · '+o.t+dash+'</div></div>'}}).join('');
  document.getElementById('more').innerHTML=nb.hidden>0
    ? '<button id="exp">show '+nb.hidden+' more</button>' : '';
  const ex=document.getElementById('exp');
  if(ex)ex.onclick=()=>{{state.expanded.add(id);open(id)}};
  document.getElementById('files').innerHTML=(n.files||[]).map(f=>
    '<div class="src">'+f.f+(f.sh?' <b>!'+f.sh+'</b>':'')+(f.r?' r'+f.r:'')+'</div>'
  ).join('')||'<div class="src">none recorded</div>';
  for(const el of document.querySelectorAll('.nb'))
    el.onclick=()=>open(el.dataset.id);
}}
function close(){{state.sel=null;document.getElementById('right').style.display='none'}}
document.getElementById('close').onclick=close;

const res=document.getElementById('res');
let tq=null;
document.getElementById('q').addEventListener('input',ev=>{{
  clearTimeout(tq);
  tq=setTimeout(()=>{{
    const hits=search(idx.idx,ev.target.value,40);
    res.innerHTML=hits.map(id=>{{const n=idx.byId.get(id);
      return '<div class="hit" data-id="'+id+'"><i style="background:'+
        (C[n.t]||'#888')+'"></i><span>'+n.l+'</span><em>'+n.t+'</em></div>'}}).join('')
      ||(ev.target.value?'<div class="src">no match</div>':'');
    for(const el of res.querySelectorAll('.hit'))
      el.onclick=()=>{{open(el.dataset.id);
        const n=idx.byId.get(el.dataset.id);
        if(n&&n.x!==undefined){{}}}};
  }},120);
}});
document.getElementById('th').onchange=e=>{{
  state.themes=e.target.value?new Set([e.target.value]):null;
  for(const n of D.nodes)delete n.x;recompute()}};
for(const el of document.querySelectorAll('.ty'))
  el.onchange=()=>{{state.types=new Set([...document.querySelectorAll('.ty')]
    .filter(x=>x.checked).map(x=>x.value));recompute()}};
document.getElementById('iso').onchange=e=>{{state.showIso=e.target.checked;recompute()}};
document.getElementById('hired').onchange=e=>{{state.showHired=e.target.checked;recompute()}};
document.getElementById('dash').onchange=e=>{{state.showDash=e.target.checked;recompute()}};
document.getElementById('sep').onchange=e=>{{state.separate=e.target.checked;
  for(const n of D.nodes)delete n.x;recompute()}};
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
