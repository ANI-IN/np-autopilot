// The DEFAULT VIEW's labels, on the REAL graph (owner review 2026-09-30:
// "every other module has no label"). Runs public/index.html's own layout and
// label placer, headless, on a structure payload built by
// web/lib/data.py::pack_structure from the merged graph, at several window
// sizes and with the side panel open; prints what was drawn as JSON.
//
//   node eval/default_view_labels.mjs <structure.json>
//
// tests/test_default_view_labels.py builds the payload and asserts: every
// current domain, current module and current instructor has a visible label,
// in FULL, inside the canvas area, overlapping no other label.
import {readFileSync} from 'node:fs';

const payload = JSON.parse(readFileSync(process.argv[2], 'utf8'));

// ---- a DOM just rich enough for the page to load and lay out ----------------
const el = (id) => ({id, style:{}, _html:'', dataset:{}, value:'', checked:false,
  classList:{add(){}, remove(){}, toggle(){}, contains(){return false}},
  set innerHTML(v){this._html=v}, get innerHTML(){return this._html},
  textContent:'', addEventListener(){}, appendChild(){}, setAttribute(){},
  querySelectorAll(){return []}, querySelector(){return null}, focus(){}, blur(){},
  getBoundingClientRect(){
    // the header's bottom and the view switch's top, as the page lays them out
    if(id==='hdr') return {top:10, bottom:120, height:110};
    if(id==='vbar') return {top:globalThis.innerHeight-76, bottom:globalThis.innerHeight-40};
    return {top:0, bottom:0, height:0};
  },
  getContext(){return ctx}, width:0, height:0});
// measureText follows the font actually set, so label widths are realistic
let font = '11px sans-serif';
const ctx = new Proxy({}, {
  get:(t,k)=>{
    if(k==='font') return font;
    if(k==='measureText') return (s)=>{ const px=parseFloat((font.match(/([\d.]+)px/)||[0,11])[1]);
      const bold=/^(600|700|bold)/.test(font); return {width:String(s).length*px*(bold?0.6:0.56)}; };
    return ()=>{};
  },
  set:(t,k,v)=>{ if(k==='font') font=v; return true; }});
const store = new Map();
globalThis.document = {
  getElementById:(id)=>{ if(!store.has(id)) store.set(id, el(id)); return store.get(id); },
  createElement:(tag)=>el('created-'+tag), head:{appendChild(){}}, body:el('body'),
  querySelectorAll:()=>[], addEventListener(){}, readyState:'complete', activeElement:null};
globalThis.window = {devicePixelRatio:1};
// a HISTORY with real push/replace/back/forward semantics, over `location`
globalThis.location = {search:'', pathname:'/', hash:''};
const HIST = {entries:[''], i:0, pushes:0};
const qOf = u => { const k=String(u).indexOf('?'); return k<0?'':String(u).slice(k); };
globalThis.history = {
  pushState(s,t,u){ HIST.entries=HIST.entries.slice(0,HIST.i+1); HIST.entries.push(qOf(u)); HIST.i++; HIST.pushes++;
                    location.search=qOf(u); },
  replaceState(s,t,u){ HIST.entries[HIST.i]=qOf(u); location.search=qOf(u); }};
globalThis.queueMicrotask = globalThis.queueMicrotask || (f=>Promise.resolve().then(f));
globalThis.addEventListener = ()=>{};
globalThis.performance = {now:()=>Date.now()};
let rafFn = null; globalThis.requestAnimationFrame = (f)=>{rafFn=f};
const mk = ()=>{const m=new Map();return {getItem:k=>m.has(k)?m.get(k):null,
  setItem:(k,v)=>m.set(k,String(v)), removeItem:k=>m.delete(k)}};
globalThis.sessionStorage = mk(); globalThis.localStorage = mk();
globalThis.fetch = async()=>({ok:false, status:404, json:async()=>({})});
globalThis.innerWidth = 1440; globalThis.innerHeight = 900;
const quiet = console.log; console.log = ()=>{};   // the page narrates its layout

const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
(0,eval)(blocks[0]);
globalThis.window.__NP_NO_BOOT = true;
// The page's top-level const/let (D, state, cam) are invisible to a later
// indirect eval; an accessor appended to the SAME evaluation reaches them.
// Harness only — the page is not changed.
(0,eval)(blocks[1]+'\n;globalThis.__T={get D(){return D},get state(){return state},get cam(){return cam},get TYPES(){return TYPES},get DEFAULT_TYPES(){return DEFAULT_TYPES},get A(){return A},get idx(){return idx},get VIEWMETA(){return VIEWMETA},get SPRING(){return SPRING},get DRAGGED(){return DRAGGED},set DRAGGED(v){DRAGGED=v},get E(){return E},get FITMODE(){return FITMODE}};');
const run = (src)=>(0,eval)(src);

// the real payload, decoded by the page's own decoder, merged by its own merge
globalThis.__PAYLOAD = payload;
run(`(()=>{const dec=decodeStructure(globalThis.__PAYLOAD);
        window.__NP.counts=globalThis.__PAYLOAD.counts||{};
        mergeGraph(window.__NP.data,{nodes:dec.nodes,edges:dec.edges},1e9);})()`);

function settle(){ for(let i=0;i<400&&rafFn;i++){ const f=rafFn; rafFn=null; f(); } }
const want = run(`(()=>{const M=model(), ins=currentInstructors();
  const cur=D.nodes.filter(n=>(n.t==='module'&&!n.legacy)||(n.t==='instructor'&&ins.has(n.id))
                              ||(n.t==='domain'&&(M.cur.get(n.id)||[]).length));
  return cur.map(n=>({id:n.id,t:n.t,l:n.l}));})()`.replace(/\bD\./g,'__T.D.'));

const out = {want: want.length, views: []};
for(const [w,h,panel] of [[1440,900,false],[1440,900,true],[1280,720,false],
                          [1366,768,false],[1920,1080,false],[1024,700,false]]){
  globalThis.innerWidth=w; globalThis.innerHeight=h;
  run('size()');
  document.getElementById('right').style.display = panel ? 'block' : 'none';
  run(`__T.state.place=null; __T.state.sel=null; __T.state.types=new Set(__T.DEFAULT_TYPES); __T.state.listMode=false; recompute(true,'labels test')`);
  settle(); run('fit()'); rafFn && settle();
  run('draw()');
  const labels = run('window.__NP_LABELS') || [];
  const clip = run('clipArea()');
  const byId = new Map(labels.map(l=>[l.id,l]));
  const missing=[], cut=[], outside=[];
  for(const n of want){
    const l = byId.get(n.id);
    if(!l){ missing.push(n.l); continue; }
    if(!l.full) cut.push(n.l);
    if(l.x0<clip.x0-1||l.x1>clip.x1+1||l.y0<clip.y0-1||l.y1>clip.y1+1) outside.push(n.l);
  }
  const must = labels.filter(l=>want.some(n=>n.id===l.id));
  let overlaps=0; const pairs=[];
  for(let i=0;i<must.length;i++)for(let j=i+1;j<must.length;j++){
    const a=must[i], b=must[j];
    if(Math.min(a.x1,b.x1)-Math.max(a.x0,b.x0)>0.5&&Math.min(a.y1,b.y1)-Math.max(a.y0,b.y0)>0.5){
      overlaps++; pairs.push(a.text+' / '+b.text);}
  }
  out.views.push({size:`${w}x${h}${panel?' +panel':''}`, drawn:labels.length,
                  missing, cut, outside, overlaps, pairs, zoom:+run('__T.cam.k').toFixed(3),
                  view:run(`({shown:__T.A.length, fit:__T.FITMODE, types:[...new Set(__T.A.map(n=>n.t))].join(','),
                    x:[Math.round(Math.min(...__T.A.map(n=>n.tx))),Math.round(Math.max(...__T.A.map(n=>n.tx)))],
                    y:[Math.round(Math.min(...__T.A.map(n=>n.ty))),Math.round(Math.max(...__T.A.map(n=>n.ty)))]})`)});
}
// WHAT THE DEFAULT MAP HOLDS, and what the chips do to it (owner review 2026-09-30)
globalThis.innerWidth=1440; globalThis.innerHeight=900; run('size()');
document.getElementById('right').style.display='none';
const census=()=>run(`(()=>{const c={},g={};for(const n of __T.A){const gh=(__T.VIEWMETA.get(n.id)||{}).ghost;
    if(gh)g[n.t]=(g[n.t]||0)+1; else c[n.t]=(c[n.t]||0)+1;}
  const e={};for(const x of __T.E){const a=__T.A.find(n=>n.id===x.s)||{t:'group'},b=__T.A.find(n=>n.id===x.t)||{t:'group'};
    const k=[a.t,b.t].sort().join('-');e[k]=(e[k]||0)+1;}
  return {nodes:c,ghosts:g,edges:e,list:__T.state.listMode};})()`);
run(`__T.state.place=null; __T.state.sel=null; __T.state.listMode=false; __T.state.types=new Set(__T.DEFAULT_TYPES); recompute(true,'census')`);
out.defaultMap=census();
run(`__T.state.types=new Set(['slide_deck','module']); recompute(true,'decks+modules')`);
out.decksModules=census();
// the chip HANDLER itself: from the default map, clicking "Decks" removes decks
run(`__T.state.types=new Set(__T.DEFAULT_TYPES); __T.state.listMode=false; recompute(true,'reset'); toggleType('slide_deck')`);
out.afterDeckChip=census();
run(`__T.state.types=new Set(['class_session']); recompute(true,'sessions only')`);
out.sessionsOnly=census();
out.sessionsOnly.clusterLabels=run(`[...__T.VIEWMETA.values()].filter(i=>i.clusterLabel).length`);
// SPRINGS: drag a module 120 units; its neighbours follow; on release all go home
run(`__T.state.types=new Set(__T.DEFAULT_TYPES); recompute(true,'springs')`);
for(let i=0;i<400&&rafFn;i++){const f=rafFn;rafFn=null;f();}
out.springs=run(`(()=>{
  const m=__T.A.find(n=>n.t==='module'); const nb=__T.E.filter(e=>e.s===m.id||e.t===m.id).map(e=>e.s===m.id?e.t:e.s);
  const o=__T.idx.byId.get(nb[0]); const home=[o.x,o.y];
  __T.DRAGGED=m; m.x=m.tx+120; m.y=m.ty;
  for(let i=0;i<40;i++)springStep();
  const pulled=Math.hypot(o.x-home[0],o.y-home[1]);
  __T.DRAGGED=null; __T.SPRING.set(m.id,{vx:0,vy:0});
  let frames=0; while(__T.SPRING.size&&frames<600){springStep();frames++;}
  return {neighbours:nb.length,pulled:+pulled.toFixed(1),settledIn:frames,
          home:Math.hypot(o.x-home[0],o.y-home[1])<0.3&&Math.hypot(m.x-m.tx,m.y-m.ty)<0.3};})()`);
// ---- THE URL (owner review 2026-09-30): one view, never a pile -------------
const tick = () => new Promise(r=>setTimeout(r,0));
const consistency = () => run(`(()=>{
  const bad=[];
  const tc=document.getElementById('tchips').innerHTML||'';
  const pressed=new Set([...tc.matchAll(/data-t="([^"]+)" aria-pressed="true"/g)].map(m=>m[1]).filter(t=>t!=='*'&&t!=='#list'));
  const want=new Set(__T.TYPES.filter(t=>__T.state.types.has(t)));
  if(pressed.size!==want.size||[...want].some(t=>!pressed.has(t)))bad.push('chips '+[...pressed]+' vs types '+[...want]);
  const allOn=tc.indexOf('data-t="*" aria-pressed="true"')>=0;
  if(allOn!==allTypesOn())bad.push('All chip '+allOn+' vs default '+allTypesOn());
  const cr=document.getElementById('crumbs').innerHTML||'';
  const showing=/Showing: |List: /.test(cr);
  if(__T.state.view==='graph'&&showing===allTypesOn())bad.push('breadcrumb says '+(showing?'Showing':'the map')+' but types default='+allTypesOn());
  const st=(document.getElementById('stat').innerHTML||'').match(/<b>([0-9,]+)<.b> things shown/);
  if(__T.state.view==='graph'&&(!st||Number(st[1].replace(/,/g,''))!==__T.A.length))bad.push('count '+(st&&st[1])+' vs drawn '+__T.A.length);
  return bad;})()`);
const urlOk = u => { const q=new URLSearchParams(u); return !q.has('open')&&q.getAll('focus').length<=1&&q.getAll('at').length<=1
  &&!(q.get('focus')||'').includes(',')&&!(q.get('at')||'').includes(','); };
const sig = () => run(`JSON.stringify({ids:__T.A.map(n=>n.id).sort().join('|').length+':'+__T.A.length,sel:__T.state.sel||null,
  place:__T.state.place?(__T.state.place.id||__T.state.place.key):null,view:__T.state.view,types:[...__T.state.types].sort().join(',')})`);
run(`__T.state.place=null; __T.state.sel=null; __T.state.types=new Set(__T.DEFAULT_TYPES); __T.state.view='graph';
     __T.state.listMode=false; recompute(true,'url test')`);
history.replaceState(null,'','?'+run('urlFor()')); HIST.entries=[location.search]; HIST.i=0; HIST.pushes=0;
const pick = run(`(()=>{const mods=__T.D.nodes.filter(n=>n.t==='module'&&!n.legacy).map(n=>n.id);
  const ins=[...currentInstructors()].filter(id=>{const o=__T.idx.byId.get(id);return o&&o.t==='instructor'}).slice(0,6);
  const dom=__T.D.nodes.filter(n=>n.t==='domain'&&(model().cur.get(n.id)||[]).length).map(n=>n.id);
  return {mods, ins, dom};})()`);
const clicks = [
  ['module 0', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[0])}))`],
  ['module 1', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[1])}))`],
  ['Esc', `clearFocus()`],
  ['instructor 0', `activate(__T.idx.byId.get(${JSON.stringify(pick.ins[0])}))`],
  ['module 5', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[5])}))`],
  ['chip decks off', `toggleType('slide_deck')`],
  ['module 7', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[7])}))`],
  ['All (the map)', `toggleType('*')`],
  ['legacy domains group', `activate([...__T.VIEWMETA.values()].map(i=>i.n).find(n=>n.t==='group'&&/Legacy domains/.test(n.l)))`],
  ['crumb: Map', `goPlace(null,'crumb')`],
  ['domain hub', `activate(__T.idx.byId.get(${JSON.stringify(pick.dom[0])}))`],
  ['module in domain', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[0])}))`],
  ['another module in domain', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[1])}))`],
  ['crumb: Map', `goPlace(null,'crumb')`],
  ['only instructors', `onlyType('instructor')`],
  ['instructor 1', `activate(__T.idx.byId.get(${JSON.stringify(pick.ins[1])}))`],
  ['All (the map)', `toggleType('*')`],
  ['who teaches what', `setView('matrix',true)`],
  ['back to the map', `setView('graph',true)`],
  ['module 9', `activate(__T.idx.byId.get(${JSON.stringify(pick.mods[9])}))`],
];
out.url={steps:[],back:[],forward:[],fresh:[],oldLink:null};
const recorded=new Map();
for(const [name,js] of clicks){
  run(js); await tick(); settle();
  const u=location.search, s_=sig();
  recorded.set(u,s_);
  out.url.steps.push({name,url:u,ok:urlOk(u),bad:consistency(),roundTrip:('?'+run('urlFor()'))===u||(u===''&&run('urlFor()')==='')});
}
out.url.pushes=HIST.pushes; out.url.entries=HIST.entries.length;
// BACK through every step, then FORWARD again
const back=()=>{HIST.i--; location.search=HIST.entries[HIST.i]; run('applyUrl()'); settle();};
const fwd=()=>{HIST.i++; location.search=HIST.entries[HIST.i]; run('applyUrl()'); settle();};
while(HIST.i>0){ back(); const u=location.search;
  out.url.back.push({url:u,bad:consistency(),same:recorded.has(u)?recorded.get(u)===sig():null,ok:urlOk(u)}); }
while(HIST.i<HIST.entries.length-1){ fwd(); const u=location.search;
  out.url.forward.push({url:u,bad:consistency(),same:recorded.has(u)?recorded.get(u)===sig():null}); }
// A SHARED LINK: each URL applied from scratch reproduces the same view
for(const [u,s0] of recorded){ run(`__T.state.sel=null; __T.state.place=null; __T.state.types=new Set(['module']); recompute(true,'reset')`);
  location.search=u; run('applyUrl()'); settle(); out.url.fresh.push({url:u,same:sig()===s0,bad:consistency()}); }
// AN OLD LINK: ?open=a,b,c keeps only the last item and is rewritten
location.search='?open='+[pick.mods[0],'map:legacy-domains',pick.mods[3]].join(',')+'&focus=';
run('applyUrl()'); settle();
out.url.oldLink={url:location.search,sel:run('__T.state.sel'),want:pick.mods[3],ok:urlOk(location.search)};
// THE MAP IS 2D ONLY (owner, 2026-11-07): an old ?dim= link opens the 2D map and
// the address is rewritten without it
out.dimLinks=['3d','2d'].map(d=>{ location.search='?dim='+d+'&view=matrix'; run('applyUrl()'); settle();
  return {dim:d, url:location.search, view:run('__T.state.view'), hasDim:'dim' in run('__T.state')}; });
console.log = quiet;
console.log(JSON.stringify(out));
