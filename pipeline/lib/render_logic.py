"""The graph.html interaction logic, as one string.

Inlined into the HTML (which must stay self-contained) AND written to
knowledge/_graph_logic.mjs so it can be executed headlessly by
eval/drive_render.mjs. One definition, two consumers — no drift.
"""

LOGIC = r"""
// ---- pure logic. No DOM, no canvas. Exercised directly by drive_render.mjs ----
export function buildIndex(D){
  const byId=new Map(D.nodes.map(n=>[n.id,n]));
  const adj=new Map();
  for(const n of D.nodes) adj.set(n.id,[]);
  for(const e of D.edges){
    if(adj.has(e.s)) adj.get(e.s).push({o:e.t,r:e.r,b:e.b,dir:'out'});
    if(adj.has(e.t)) adj.get(e.t).push({o:e.s,r:e.r,b:e.b,dir:'in'});
  }
  // lowercase search index built ONCE, not per keystroke
  // Index label + type + workflow id + status. Omitting the id meant searching
  // "8.2" returned nothing, which is the primary acceptance path.
  const idx=D.nodes.map(n=>({id:n.id,
    k:(n.l+' '+n.t+' '+(n.wid||'')+' '+(n.st||'')).toLowerCase()}));
  return {byId,adj,idx};
}

export function components(D,visibleIds){
  const adj=new Map();
  for(const id of visibleIds) adj.set(id,[]);
  for(const e of D.edges){
    if(adj.has(e.s)&&adj.has(e.t)){adj.get(e.s).push(e.t);adj.get(e.t).push(e.s);}
  }
  const seen=new Set(),comps=[];
  for(const id of visibleIds){
    if(seen.has(id))continue;
    const st=[id],c=[];
    while(st.length){const x=st.pop();if(seen.has(x))continue;seen.add(x);c.push(x);
      for(const y of adj.get(x)||[])if(!seen.has(y))st.push(y);}
    comps.push(c);
  }
  comps.sort((a,b)=>b.length-a.length);
  return comps;
}

export function search(index,q,limit){
  q=(q||'').trim().toLowerCase();
  if(!q)return [];
  const lim=limit||50, starts=[], contains=[];
  for(const r of index){
    const i=r.k.indexOf(q);
    if(i===0) starts.push(r.id);
    else if(i>0) contains.push(r.id);
    if(starts.length>=lim) break;
  }
  return starts.concat(contains).slice(0,lim);
}

export function visible(D,f){
  // f: {types:Set, themes:Set|null, showIso:bool, showHired:bool, degree:Map}
  return D.nodes.filter(n=>{
    if(!f.types.has(n.t))return false;
    if(!f.showHired&&n.st==='hired')return false;
    if(f.themes&&f.themes.size){
      if(n.t==='workflow'||n.t==='theme'){ if(!f.themes.has(String(n.th)))return false; }
      else return false;
    }
    if(!f.showIso&&(f.degree.get(n.id)||0)===0)return false;
    return true;
  });
}

export function degreeMap(D,ids){
  const d=new Map(); for(const id of ids) d.set(id,0);
  for(const e of D.edges){
    if(d.has(e.s)&&d.has(e.t)){d.set(e.s,d.get(e.s)+1);d.set(e.t,d.get(e.t)+1);}
  }
  return d;
}

// ---- FILE SEARCH. Files are NOT graph nodes — the 15,403 provenance edges
// stay undrawn. They are a separate result section with two hit kinds.
export function searchFiles(F,index,q,limit){
  q=(q||'').trim().toLowerCase();
  if(!q)return [];
  const out=[];
  for(const f of F){
    const nameHit=f.p.toLowerCase().includes(q);
    const ents=f.e.filter(x=>{const n=index.byId.get(x.i);
      return n&&(n.l+' '+n.t+' '+(n.wid||'')).toLowerCase().includes(q)});
    if(nameHit||ents.length){
      out.push({path:f.p, kind:nameHit&&ents.length?'both':(nameHit?'filename':'contains'),
                matched:ents.slice(0,6), matchedTotal:ents.length,
                total:f.e.length, drive:f.d||null});
      if(out.length>=(limit||20))break;
    }
  }
  // filename hits first — a direct name match is the stronger signal
  const rank={filename:0,both:0,contains:1};
  out.sort((a,b)=>rank[a.kind]-rank[b.kind]||b.matchedTotal-a.matchedTotal);
  return out;
}

export function entitiesOf(F,path){
  const f=F.find(x=>x.p===path);
  return f?f.e:[];
}

// Edge cap: a node with more than CAP neighbours shows CAP, rest behind a click.
export function neighboursOf(index,id,cap,expanded){
  const all=index.adj.get(id)||[];
  const shown=(expanded)?all:all.slice(0,cap);
  return {shown,hidden:Math.max(0,all.length-shown.length),total:all.length};
}
"""


# ---------------------------------------------------------------------------
# VIEW — DOM, canvas, camera, interaction. A plain string (NOT interpolated into
# an f-string), so JavaScript braces need no escaping. Values it needs from
# Python arrive via the window.__NP object the HTML defines before this runs.
# ---------------------------------------------------------------------------
VIEW = r"""
const D=window.__NP.data, F=window.__NP.files, C=window.__NP.colors;
const EXPERT=window.__NP.expert, LEFT=300, RIGHT=330, CAP=8;
const idx=buildIndex(D);
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
let W,H;function size(){W=cv.width=innerWidth;H=cv.height=innerHeight}
size();addEventListener('resize',()=>{size();fit()});
const t0=performance.now();

// ---- camera -------------------------------------------------------------
const cam={k:1,tx:0,ty:0};
const toScreen=(x,y)=>[x*cam.k+cam.tx, y*cam.k+cam.ty];
const toWorld=(sx,sy)=>[(sx-cam.tx)/cam.k, (sy-cam.ty)/cam.k];
function usable(){
  const rightOpen=document.getElementById('right').style.display==='block';
  return {x0:LEFT+20, x1:W-(rightOpen?RIGHT:0)-20, y0:20, y1:H-20};
}
function fit(pad){
  const P=usable(), nodes=A.filter(n=>n.x!==undefined);
  if(!nodes.length)return;
  let a=1e9,b=1e9,c=-1e9,d=-1e9;
  for(const n of nodes){a=Math.min(a,n.x);b=Math.min(b,n.y);c=Math.max(c,n.x);d=Math.max(d,n.y)}
  const gw=Math.max(c-a,1), gh=Math.max(d-b,1);
  const vw=P.x1-P.x0, vh=P.y1-P.y0;
  cam.k=Math.min(vw/gw, vh/gh)*(pad||0.92);
  cam.k=Math.max(0.05,Math.min(cam.k,4));
  cam.tx=P.x0+vw/2-((a+c)/2)*cam.k;
  cam.ty=P.y0+vh/2-((b+d)/2)*cam.k;
}
function centreOn(n,k){
  if(n.x===undefined)return;
  const P=usable();
  cam.k=k||Math.max(cam.k,1.1);
  cam.tx=P.x0+(P.x1-P.x0)/2-n.x*cam.k;
  cam.ty=P.y0+(P.y1-P.y0)/2-n.y*cam.k;
}

const state={types:new Set([...document.querySelectorAll('.ty')].map(e=>e.value)),
  themes:null,showIso:false,showHired:true,showDash:true,separate:false,
  sel:null,expanded:new Set()};
const allDeg=degreeMap(D,D.nodes.map(n=>n.id));
let A=[],E=[],anchors=new Map();

function recompute(refit){
  A=visible(D,{types:state.types,themes:state.themes,showIso:state.showIso,
    showHired:state.showHired,degree:allDeg});
  const ids=new Set(A.map(n=>n.id));
  E=D.edges.filter(e=>ids.has(e.s)&&ids.has(e.t)&&(state.showDash||e.r!==EXPERT));
  anchors=new Map();
  const comps=components({nodes:A,edges:E},A.map(n=>n.id));
  if(state.separate){
    // Shelf-pack by component size. Equal grid cells wasted most of the canvas
    // on 38 components where one holds half the nodes.
    const sorted=comps.slice().sort((a,b)=>b.length-a.length);
    const R=sorted.map(c=>Math.max(28,Math.sqrt(c.length)*13));
    const targetW=Math.sqrt(R.reduce((s,r)=>s+r*r*4,0))*1.25;
    let cx=0,cy=0,rowH=0;
    sorted.forEach((c,i)=>{
      const r=R[i];
      if(cx+r*2>targetW && cx>0){cx=0;cy+=rowH+30;rowH=0}
      for(const id of c) anchors.set(id,[cx+r,cy+r,c.length]);
      cx+=r*2+30; rowH=Math.max(rowH,r*2);
    });
  } else {
    for(const n of A) anchors.set(n.id,[0,0,A.length]);
  }
  for(const n of A){ if(n.x===undefined){const a=anchors.get(n.id)||[0,0];
    const s=state.separate?a[2]:A.length;
    const rad=Math.max(30,Math.sqrt(s)*10);
    n.x=a[0]+(Math.random()-.5)*rad;n.y=a[1]+(Math.random()-.5)*rad;n.vx=0;n.vy=0} }
  document.getElementById('stat').innerHTML=
    '<b>'+A.length+'</b> nodes / <b>'+E.length+'</b> edges / '+comps.length+
    ' components <span style="color:#6e7681">— currently visible</span>';
  if(refit!==false){settle=0}
}
recompute();

let settle=0;
function step(){
  const K=settle<90?1:0.35;
  for(const n of A){n.vx*=.85;n.vy*=.85;
    const a=anchors.get(n.id);
    if(a){n.vx+=(a[0]-n.x)*.006*K;n.vy+=(a[1]-n.y)*.006*K}}
  for(let i=0;i<A.length;i++){const a=A[i];
    for(let j=i+1;j<Math.min(A.length,i+12);j++){const b=A[j];
      const dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;
      if(d2<5000){const f=110/d2*K;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}}}
  for(const e of E){const a=idx.byId.get(e.s),b=idx.byId.get(e.t);
    if(!a||!b||a.x===undefined||b.x===undefined)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,f=(d-58)*.006*K;
    a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f}
  for(const n of A){n.x+=n.vx;n.y+=n.vy}
  settle++;
  if(settle===90)fit();
}
function draw(){
  ctx.clearRect(0,0,W,H);
  for(const e of E){const a=idx.byId.get(e.s),b=idx.byId.get(e.t);
    if(!a||!b||a.x===undefined)continue;
    const [ax,ay]=toScreen(a.x,a.y),[bx,by]=toScreen(b.x,b.y);
    if(Math.max(ax,bx)<LEFT-40)continue;
    const hot=state.sel&&(e.s===state.sel||e.t===state.sel);
    ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);
    if(e.r===EXPERT){ctx.setLineDash([3,4]);
      ctx.strokeStyle=hot?'rgba(0,194,209,.9)':'rgba(0,194,209,.22)'}
    else{ctx.setLineDash([]);
      ctx.strokeStyle=hot?'rgba(230,237,243,.85)':'rgba(139,148,158,.17)'}
    ctx.lineWidth=hot?1.8:1;ctx.stroke()}
  ctx.setLineDash([]);
  for(const n of A){if(n.x===undefined)continue;
    const [sx,sy]=toScreen(n.x,n.y);
    if(sx<-20||sx>W+20||sy<-20||sy>H+20)continue;
    const r=(n.iso?2:Math.min(3+Math.sqrt(n.d)*1.1,11))*Math.max(.55,Math.min(cam.k,1.6));
    ctx.beginPath();ctx.arc(sx,sy,r,0,7);
    ctx.fillStyle=C[n.t]||'#888';ctx.globalAlpha=n.iso?.4:1;ctx.fill();
    if(state.sel===n.id){ctx.globalAlpha=1;ctx.lineWidth=2.5;ctx.strokeStyle='#fff';ctx.stroke()}
    ctx.globalAlpha=1}
}
(function loop(){step();draw();requestAnimationFrame(loop)})();

// ---- interaction --------------------------------------------------------
function hit(sx,sy){const [wx,wy]=toWorld(sx,sy);let best=null,bd=1e9;
  for(const n of A){if(n.x===undefined)continue;
    const d=Math.hypot(n.x-wx,n.y-wy);if(d<bd){bd=d;best=n}}
  return bd<16/cam.k?best:null}
cv.addEventListener('wheel',ev=>{ev.preventDefault();
  const [wx,wy]=toWorld(ev.clientX,ev.clientY);
  cam.k=Math.max(0.05,Math.min(4,cam.k*(ev.deltaY<0?1.12:1/1.12)));
  cam.tx=ev.clientX-wx*cam.k;cam.ty=ev.clientY-wy*cam.k},{passive:false});
let drag=null;
cv.addEventListener('mousedown',ev=>{ev.preventDefault();drag={x:ev.clientX,y:ev.clientY,
  tx:cam.tx,ty:cam.ty,moved:false}});
addEventListener('mouseup',()=>{drag=null});
cv.addEventListener('mousemove',ev=>{
  if(drag){const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;
    if(Math.abs(dx)+Math.abs(dy)>3)drag.moved=true;
    cam.tx=drag.tx+dx;cam.ty=drag.ty+dy;tip.style.display='none';return}
  const n=hit(ev.clientX,ev.clientY);
  cv.style.cursor=n?'pointer':'grab';
  if(n){tip.style.display='block';tip.style.left=(ev.clientX+12)+'px';
    tip.style.top=(ev.clientY+12)+'px';
    tip.innerHTML='<b>'+n.l+'</b><br>'+n.t+(n.st?' &middot; '+n.st:'')+
      '<br>'+n.d+' relationships &middot; click to open, double-click to zoom'}
  else tip.style.display='none'});
cv.addEventListener('click',ev=>{ev.preventDefault();if(drag&&drag.moved)return;
  const n=hit(ev.clientX,ev.clientY);if(n)openNode(n.id);else closePanel()});
cv.addEventListener('dblclick',ev=>{ev.preventDefault();const n=hit(ev.clientX,ev.clientY);
  if(n){centreOn(n,1.6);openNode(n.id)}});
document.getElementById('fit').onclick=()=>fit();
document.getElementById('zin').onclick=()=>{cam.k=Math.min(4,cam.k*1.3)};
document.getElementById('zout').onclick=()=>{cam.k=Math.max(0.05,cam.k/1.3)};

// ---- panels -------------------------------------------------------------
function openNode(id){
  state.sel=id;const n=idx.byId.get(id);
  document.getElementById('right').style.display='block';
  document.getElementById('nl').textContent=n.l;
  document.getElementById('nt').textContent=n.t+(n.st?' · '+n.st:'')+
    (n.wid?' · workflow '+n.wid:'');
  const pr=[];
  if(n.eff)pr.push('<div class="src"><b>Effort:</b> '+n.eff+'</div>');
  if(n.al)pr.push('<div class="src"><b>Alerts:</b> '+n.al+' recorded</div>');
  pr.push('<button type="button" id="goto">centre on this node</button>');
  document.getElementById('nprops').innerHTML=pr.join('');
  const g=document.getElementById('goto'); if(g)g.onclick=()=>centreOn(n,1.6);
  const nb=neighboursOf(idx,id,CAP,state.expanded.has(id));
  document.getElementById('ncount').textContent=nb.total;
  document.getElementById('nbrs').innerHTML=nb.shown.map(x=>{
    const o=idx.byId.get(x.o);if(!o)return '';
    const dash=x.r===EXPERT?' <span class="dash">(declared)</span>':'';
    return '<div class="nb" data-id="'+x.o+'">'+o.l+
      '<div class="rel">'+x.r+' · '+o.t+dash+'</div></div>'}).join('')
    ||'<div class="src">no relationships</div>';
  document.getElementById('more').innerHTML=nb.hidden>0
    ? '<button type="button" id="exp">show '+nb.hidden+' more</button>' : '';
  const ex=document.getElementById('exp');
  if(ex)ex.onclick=()=>{state.expanded.add(id);openNode(id)};
  document.getElementById('files').innerHTML=(n.files||[]).map(f=>
    '<div class="src">'+f.f+(f.sh?' <b>!'+f.sh+'</b>':'')+(f.r?' r'+f.r:'')+'</div>'
  ).join('')||'<div class="src">none recorded</div>';
  for(const el of document.querySelectorAll('.nb'))
    el.onclick=()=>{const o=idx.byId.get(el.dataset.id);openNode(el.dataset.id);
      if(o&&o.x!==undefined)centreOn(o,Math.max(cam.k,1.2))};
}
function closePanel(){state.sel=null;document.getElementById('right').style.display='none'}
document.getElementById('close').onclick=closePanel;

function openFile(path){
  const ents=entitiesOf(F,path), f=F.find(x=>x.p===path);
  document.getElementById('right').style.display='block';
  document.getElementById('nl').textContent=path.split('/').pop();
  document.getElementById('nt').textContent='source file';
  const kinds={};ents.forEach(e=>{const n=idx.byId.get(e.i);if(n)kinds[n.t]=(kinds[n.t]||0)+1});
  document.getElementById('nprops').innerHTML=
    '<div class="src">'+path+'</div><button type="button" id="cp">copy path</button>'+
    (f&&f.d?'<div class="src">Drive: '+f.d+'</div>'
      :'<div class="src" style="color:#f0c674">Link inactive — the corpus is a '+
       'hand-exported local folder and browsers block file:// links from HTML. '+
       'Activates when pass 0 populates file.drive_url.</div>');
  document.getElementById('ncount').textContent=ents.length;
  document.getElementById('nbrs').innerHTML=
    (ents.length?'<div class="rel">'+JSON.stringify(kinds)+'</div>':'')+
    ents.slice(0,60).map(e=>{const n=idx.byId.get(e.i);if(!n)return '';
      return '<div class="nb" data-id="'+e.i+'">'+n.l+'<div class="rel">'+n.t+
        (e.sh?' · '+e.sh:'')+(e.r?' r'+e.r:'')+(e.pg?' p'+e.pg:'')+'</div></div>'}).join('')
    ||'<div class="src" style="color:#f0c674">This file yielded NO entities.</div>';
  document.getElementById('more').innerHTML=ents.length>60
    ?'<div class="src">'+(ents.length-60)+' more not shown</div>':'';
  document.getElementById('files').innerHTML='';
  const cp=document.getElementById('cp');
  if(cp)cp.onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(path);
    cp.textContent='copied'};
  for(const el of document.querySelectorAll('.nb'))
    el.onclick=()=>{const o=idx.byId.get(el.dataset.id);openNode(el.dataset.id);
      if(o&&o.x!==undefined)centreOn(o,Math.max(cam.k,1.2))};
}

// ---- search -------------------------------------------------------------
const res=document.getElementById('res'),fres=document.getElementById('fres');
let tq=null;
document.getElementById('q').addEventListener('input',ev=>{
  clearTimeout(tq);
  tq=setTimeout(()=>{
    const v=ev.target.value;
    const hits=search(idx.idx,v,40);
    res.innerHTML=hits.map(id=>{const n=idx.byId.get(id);
      return '<div class="hit" data-id="'+id+'"><i style="background:'+
        (C[n.t]||'#888')+'"></i><span>'+n.l+'</span><em>'+n.t+'</em></div>'}).join('')
      ||(v?'<div class="src">no node match</div>':'');
    for(const el of res.querySelectorAll('.hit'))
      el.onclick=()=>{const id=el.dataset.id,n=idx.byId.get(id);
        // A hit is useless if it is off-canvas: open AND move the view to it.
        if(n&&n.x===undefined){state.showIso=true;
          document.getElementById('iso').checked=true;recompute(false)}
        openNode(id);const m=idx.byId.get(id);if(m&&m.x!==undefined)centreOn(m,1.6)};
    const fh=searchFiles(F,idx,v,15);
    fres.innerHTML=fh.length?('<h2>Files ('+fh.length+')</h2>'+fh.map(f=>
      '<div class="hit fh" data-p="'+f.path+'"><i style="background:#8a94a6"></i>'+
      '<span>'+f.path.split('/').pop()+'</span><em>'+
      (f.kind==='filename'?'filename':f.kind==='both'?'name+'+f.matchedTotal:
       'contains '+f.matchedTotal)+'</em></div>').join('')):'';
    for(const el of fres.querySelectorAll('.fh')) el.onclick=()=>openFile(el.dataset.p);
  },120);
});

// ---- controls -----------------------------------------------------------
document.getElementById('th').onchange=e=>{
  state.themes=e.target.value?new Set([e.target.value]):null;
  for(const n of D.nodes)delete n.x;recompute()};
for(const el of document.querySelectorAll('.ty'))
  el.onchange=()=>{state.types=new Set([...document.querySelectorAll('.ty')]
    .filter(x=>x.checked).map(x=>x.value));recompute()};
document.getElementById('iso').onchange=e=>{state.showIso=e.target.checked;recompute()};
document.getElementById('hired').onchange=e=>{state.showHired=e.target.checked;recompute()};
document.getElementById('dash').onchange=e=>{state.showDash=e.target.checked;recompute(false)};
document.getElementById('sep').onchange=e=>{state.separate=e.target.checked;
  for(const n of D.nodes)delete n.x;recompute()};
"""
