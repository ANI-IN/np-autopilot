// Executes the SHIPPED inline scripts against a minimal DOM shim.
//
// Catches the class of bug that Node-level logic tests cannot: temporal dead
// zones, missing elements, exceptions in the render loop, NaN coordinates, a
// zero-size canvas, and nodes drawn outside the viewport.
//
// PORTED alongside the renderer (G2). Two things changed and neither is
// cosmetic:
//
//   * TARGET. Defaults to public/index.html — the hosted explorer. Pass a
//     path to run the offline build instead:
//         node eval/drive_dom.mjs knowledge/graph.html
//     Both are exercised in CI. The offline build is still shipped, so a
//     harness that only ran against the port would quietly stop covering it.
//
//   * THE DATA NO LONGER ARRIVES WITH THE PAGE. graph.html inlined the whole
//     graph; the port fetches neighbourhoods. So the harness now supplies a
//     `fetch` shim and asserts the things that only exist once data arrives
//     over a network: that merging is idempotent, that the client never asks
//     for the whole graph, and that a hostile label cannot reach innerHTML.
import {readFileSync} from 'node:fs';

const TARGET = process.argv[2] || 'public/index.html';
const PORTED = !TARGET.includes('graph.html');

const errors=[];
const el=(id)=>({id, style:{}, _html:'', _text:'', checked:false, value:'',
  dataset:{}, onclick:null, onchange:null,
  set innerHTML(v){this._html=v}, get innerHTML(){return this._html},
  set textContent(v){this._text=v}, get textContent(){return this._text},
  _h:{}, addEventListener(k,f){(this._h[k]=this._h[k]||[]).push(f)},
  querySelectorAll(){return []}, appendChild(){},
  getContext(){return ctx}, width:0, height:0});

let painted={arcs:0, lines:0, arcPts:[]};
const ctx=new Proxy({}, {get:(t,k)=>{
  if(k==='arc')return (x,y,r)=>{painted.arcs++; painted.arcPts.push([x,y,r])};
  if(k==='moveTo'||k==='lineTo')return ()=>{};
  if(k==='stroke')return ()=>{painted.lines++};
  if(k==='beginPath'||k==='fill'||k==='clearRect'||k==='setLineDash')return ()=>{};
  return ()=>{};
}, set:()=>true});

const store=new Map();
const canvas=el('c'); canvas.width=1600; canvas.height=900;
store.set('c',canvas);
globalThis.document={
  getElementById:(id)=>{ if(!store.has(id)) store.set(id, el(id)); return store.get(id); },
  createElement:(tag)=>el('created-'+tag),
  head:{appendChild(){}},
  querySelectorAll:(s)=>{
    if(s==='.ty') return ['theme','workflow','person','domain','program','module','instructor']
      .map(v=>{const e=el('ty-'+v); e.value=v; e.checked=true; return e});
    return [];
  }};
globalThis.window={};
globalThis.innerWidth=1600; globalThis.innerHeight=900;
globalThis.addEventListener=()=>{};
globalThis.performance={now:()=>Date.now()};
let rafFn=null, frames=0;
globalThis.requestAnimationFrame=(f)=>{rafFn=f};

// Storage shims. The port reads sessionStorage for the load counter and
// localStorage for the session; both must be present or the script dies at load.
const mkStore=()=>{const m=new Map();return{
  getItem:k=>m.has(k)?m.get(k):null, setItem:(k,v)=>m.set(k,String(v)),
  removeItem:k=>m.delete(k)}};
globalThis.sessionStorage=mkStore();
globalThis.localStorage=mkStore();

// ---- the network shim ----------------------------------------------------
// Records every URL, so the harness can assert what the client ASKS FOR, not
// only what it does with the answer.
const REQUESTS=[];
// A deliberately hostile label. Corpus labels come from spreadsheets edited
// outside this repo, and the page holds a session token.
const HOSTILE = '<img src=x onerror="window.__PWNED=1">';
const FIX = (() => {
  const nodes=[], edges=[];
  const types=['domain','program','module','person','instructor','workflow','theme'];
  for(let i=0;i<60;i++)
    nodes.push({id:'n'+i, type:types[i%types.length],
                label: i===7 ? HOSTILE : ('node '+i),
                label_raw: i===7 ? HOSTILE : null, props:{}});
  for(let i=1;i<60;i++)
    edges.push({source_id:'n'+(i-1), target_id:'n'+i,
                rel:(i%9===0?'expert_in':'covers'), props:{}});
  for(let i=0;i<12;i++)
    edges.push({source_id:'n'+i, target_id:'n'+((i*7+3)%60), rel:'teaches', props:{}});
  return {nodes,edges};
})();
function jsonResponse(body, ok=true, status=200){
  return {ok, status, json:async()=>body};
}
globalThis.fetch=async(url,opts)=>{
  REQUESTS.push({url:String(url), method:(opts&&opts.method)||'GET'});
  const u=String(url);
  if(u.startsWith('/api/neighbourhood')){
    // n3 returns a LARGER neighbourhood than anything fetched before it, so the
    // idempotence check downstream has something to add on its first call and
    // nothing to add on its second. Without that asymmetry the check passes on
    // a merge that does nothing at all.
    const n = u.includes('id=n3') ? 60 : 40;
    const ids = new Set(FIX.nodes.slice(0,n).map(x=>x.id));
    return jsonResponse({nodes:FIX.nodes.slice(0,n),
      edges:FIX.edges.filter(e=>ids.has(e.source_id)&&ids.has(e.target_id)),
      truncated:false, depth:1});
  }
  if(u.startsWith('/api/search'))
    return jsonResponse({results:FIX.nodes.slice(0,10), count:10});
  if(u.startsWith('/api/node'))
    return jsonResponse({node:{id:'n7', type:'person', label:HOSTILE,
                               label_raw:HOSTILE, props:{}},
      provenance:{corpus:[{origin:'corpus', file:HOSTILE, sheet:'Sheet1',
                           row_num:12, prop:'title'}],
                  hand:[{origin:'hand', prop:'title', evidence:HOSTILE,
                         entered_at:'2026-09-10'}],
                  hand_note:'Out-of-corpus evidence, entered by a person.'}});
  if(u.startsWith('/api/me')) return jsonResponse({email:'x@interviewkickstart.com', role:'member'});
  if(u.startsWith('/api/config')) return jsonResponse({google_client_id:'test', allowed_hd:'x'});
  return jsonResponse({}, false, 404);
};

// ---- load the shipped inline scripts -------------------------------------
const html=readFileSync(TARGET,'utf8');
const blocks=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
console.log(`target: ${TARGET}`);
console.log(`extracted ${blocks.length} inline script blocks`);

// ---- FIRST PAINT vs THE SIGN-IN GATE (port only) -------------------------
// The pre-paint check in block 0 decides, synchronously, whether the sign-in
// card is painted. It may ONLY hide the gate, and only for an unexpired token.
//
// A NEGATIVE CONTROL, per DECISIONS A.7b rule 1: "hide it whenever a value is
// present" and "hide it unconditionally" both pass the signed-in case. Only
// the expired and garbage cases can tell a correct check from those two, so
// they are asserted here beside the positive case rather than left implied.
if(PORTED){
  const gate = () => { const g = document.getElementById('gate');
                       g.style.display = ''; return g; };
  const sec = (d) => Math.floor(Date.now()/1000) + d;
  const cases = [
    ['no session at all',        null,                                              false],
    ['live token',               {access_token:'t', expires_at:sec(3600)},           true],
    ['EXPIRED token',            {access_token:'t', expires_at:sec(-3600)},          false],
    ['token expiring in 1s',     {access_token:'t', expires_at:sec(1)},              false],
    ['no access_token',          {expires_at:sec(3600)},                             false],
    ['corrupt JSON',             '!!not json!!',                                     false],
  ];
  for(const [name, val, wantHidden] of cases){
    localStorage.removeItem('np_session');
    if(val!==null) localStorage.setItem('np_session',
      typeof val==='string' ? val : JSON.stringify(val));
    const g = gate();
    try{ (0,eval)(blocks[0]); }catch(e){ errors.push('PRE-PAINT THREW ('+name+'): '+e.message); }
    const hidden = g.style.display==='none';
    const ok = hidden===wantHidden;
    console.log('  '+(ok?'ok  ':'FAIL')+'  '+name.padEnd(22)+
                ' gate '+(hidden?'hidden':'shown')+
                ' (want '+(wantHidden?'hidden':'shown')+')');
    if(!ok) errors.push('PRE-PAINT GATE: '+name+' -> gate '+
      (hidden?'hidden':'shown')+', expected '+(wantHidden?'hidden':'shown'));
  }
  // Leave no state behind: the real load below must start signed out.
  localStorage.removeItem('np_session');
  document.getElementById('gate').style.display='';
}


try{ (0,eval)(blocks[0]); console.log('  data block: OK'); }
catch(e){ errors.push('DATA BLOCK: '+e.message); }

// The port starts with an EMPTY graph and would fetch on boot. Seed it before
// the code block runs — `const D = window.__NP.data` captures this object — and
// tell it not to boot, so the network path is driven deliberately below rather
// than as a side effect of loading.
if(PORTED){
  globalThis.window.__NP_NO_BOOT = true;
  // Seed a SUBSET. Seeding all 40 made the idempotence check below vacuous:
  // expand() found every node already present, added nothing, and "added
  // nothing twice" passed without the merge path ever running. A check that
  // cannot observe the thing it names is the A.7b shape, so the fixture is
  // built so the first expand MUST add nodes and the second MUST NOT.
  const d = globalThis.window.__NP.data;
  const seed = FIX.nodes.slice(0, 6);
  d.nodes.push(...seed.map(n=>({id:n.id,l:n.label,t:n.type,d:0,iso:false,
    st:'',th:null,wid:null,eff:null,al:0,raw:n.label_raw,loaded:false})));
  const seedIds = new Set(seed.map(n=>n.id));
  d.edges.push(...FIX.edges.filter(e=>seedIds.has(e.source_id)&&seedIds.has(e.target_id))
    .map(e=>({s:e.source_id,t:e.target_id,r:e.rel})));
}

try{ (0,eval)(blocks[1]); console.log('  code block: OK (no throw at load)'); }
catch(e){ errors.push('CODE BLOCK THREW AT LOAD: '+e.constructor.name+': '+e.message); }

console.log('\n=== ERRORS AT LOAD ===');
if(!errors.length) console.log('  none');
errors.forEach(e=>console.log('  '+e));

// ---- drive the animation loop -------------------------------------------
if(rafFn){
  console.log('\n=== RENDER LOOP ===');
  let loopErr=null;
  try{ for(let i=0;i<200;i++){ painted={arcs:0,lines:0,arcPts:[]}; const f=rafFn;
        rafFn=null; f(); frames++; if(!rafFn) break; } }
  catch(e){ loopErr=e.constructor.name+': '+e.message; }
  console.log('  frames driven      :', frames);
  console.log('  error in loop      :', loopErr||'none');
  if(loopErr) errors.push('RENDER LOOP THREW: '+loopErr);
  console.log('  arcs on last frame :', painted.arcs);
  console.log('  strokes on last fr :', painted.lines);
  const bad=painted.arcPts.filter(([x,y])=>!Number.isFinite(x)||!Number.isFinite(y));
  console.log('  NaN/Inf coords     :', bad.length);
  if(bad.length) errors.push('NaN/Inf COORDINATES: '+bad.length);
  const onscreen=painted.arcPts.filter(([x,y])=>x>=0&&x<=1600&&y>=0&&y<=900);
  console.log('  arcs inside canvas :', onscreen.length, '/', painted.arcPts.length);
  if(painted.arcPts.length){
    const xs=painted.arcPts.map(p=>p[0]), ys=painted.arcPts.map(p=>p[1]);
    console.log('  x range            :', Math.round(Math.min(...xs)), '->', Math.round(Math.max(...xs)));
    console.log('  y range            :', Math.round(Math.min(...ys)), '->', Math.round(Math.max(...ys)));
  }
  if(!painted.arcPts.length) errors.push('NOTHING WAS PAINTED');
} else {
  console.log('\n=== RENDER LOOP NEVER STARTED — requestAnimationFrame was never called ===');
  errors.push('RENDER LOOP NEVER STARTED');
}

// ---- fire real interactions through the captured handlers ----------------
console.log('\n=== INTERACTION ===');
const cvh=canvas._h||{};
console.log('  handlers bound     :', Object.keys(cvh).join(', ')||'NONE');
function fire(kind, x, y){
  let threw=null, defaulted=true;
  const ev={clientX:x, clientY:y, deltaY:0, target:{value:''},
            preventDefault(){defaulted=false}};
  for(const f of (cvh[kind]||[])){ try{ f(ev) }catch(e){ threw=e.constructor.name+': '+e.message } }
  return {threw, preventDefaultCalled:!defaulted};
}
const pt = painted.arcPts[0] || [800,400];
let r1 = fire('click', pt[0], pt[1]);
console.log('  click on a node    : threw=' + (r1.threw||'no') +
            ', preventDefault=' + r1.preventDefaultCalled);
if(r1.threw) errors.push('CLICK THREW: '+r1.threw);
const right = store.get('right');
console.log('  panel opened       :', right.style.display==='block');
console.log('  panel title set    :', JSON.stringify((store.get('nl')||{}).textContent||''));
console.log('  connections listed :', ((store.get('nbrs')||{}).innerHTML||'').split('class="nb"').length-1);
let r2 = fire('dblclick', pt[0], pt[1]);
console.log('  double-click       : threw=' + (r2.threw||'no'));
let r3 = fire('wheel', 800, 400);
console.log('  wheel zoom         : threw=' + (r3.threw||'no'));
let r4 = fire('mousedown', 800, 400);
console.log('  mousedown (pan)    : threw=' + (r4.threw||'no') +
            ', preventDefault=' + r4.preventDefaultCalled);
// buttons: none may be type=submit (that was the reload cause)
const btns=[...html.matchAll(/<button([^>]*)>/g)].map(m=>m[1]);
console.log('  buttons in HTML    :', btns.length,
            '| without type=button:', btns.filter(b=>!b.includes('type="button"')).length);
if(btns.filter(b=>!b.includes('type="button"')).length)
  errors.push('A BUTTON WITHOUT type="button" — a submit button reloads the page');
console.log('  <form> elements    :', (html.match(/<form/g)||[]).length);
if((html.match(/<form/g)||[]).length) errors.push('A <form> ELEMENT CAN NAVIGATE');

// ---- SELECTION MUST NOT TOUCH LAYOUT -------------------------------------
// The previous check passed even when the whole graph had re-laid-out, which is
// exactly why it missed the restart. Assert the simulation clock is unchanged
// AND that every node coordinate is byte-identical after a click.
console.log('\n=== SELECTION vs LAYOUT ===');
function runFrames(n){ for(let i=0;i<n && rafFn;i++){ const f=rafFn; rafFn=null;
  painted={arcs:0,lines:0,arcPts:[]}; f(); } }
runFrames(600);
const st0 = globalThis.window.__NP_STATE || {};
console.log('  after 600 frames    : settle=' + st0.settle +
            ' alpha=' + (st0.alpha||0).toFixed(4) + ' frozen=' + st0.frozen);
if(!st0.frozen) errors.push('THE SIMULATION NEVER FROZE — it will drift forever');
const coordsOf = () => JSON.stringify(
  (globalThis.window.__NP.data.nodes||[]).map(n=>[n.id, n.x, n.y]));
const coordsBefore = coordsOf();
const stBefore = JSON.stringify(globalThis.window.__NP_STATE);
const clickPt = painted.arcPts[0] || [800,400];
fire('click', clickPt[0], clickPt[1]);
runFrames(1);
const coordsAfter = coordsOf();
const stAfter = JSON.stringify(globalThis.window.__NP_STATE);
const coordsSame = coordsBefore === coordsAfter;
const clockSame = stBefore === stAfter;
console.log('  click -> coords byte-identical :', coordsSame);
console.log('  click -> sim clock unchanged   :', clockSame);
if(!coordsSame){
  const b=JSON.parse(coordsBefore), a=JSON.parse(coordsAfter);
  const moved=b.filter((x,i)=>x[1]!==a[i][1]||x[2]!==a[i][2]);
  console.log('    ' + moved.length + ' nodes MOVED on a click — selection is touching layout');
  errors.push('SELECTION MOVED THE LAYOUT: ' + moved.length + ' nodes');
}
if(!clockSame) errors.push('SELECTION ADVANCED THE SIM CLOCK: ' + stBefore + ' -> ' + stAfter);

// ---- DRIFT: must move the PAINT and not the DATA -------------------------
const paintA = JSON.stringify(painted.arcPts.slice(0,40));
const dataA = coordsOf();
let tick = Date.now();
globalThis.performance = {now: () => (tick += 400)};
runFrames(1);
const paintB = JSON.stringify(painted.arcPts.slice(0,40));
const dataB = coordsOf();
console.log('  drift moves the PAINT           :', paintA !== paintB);
console.log('  drift leaves node.x/y UNTOUCHED :', dataA === dataB);
if(paintA === paintB) errors.push('DRIFT IS DEAD: paint identical across time');
if(dataA !== dataB) errors.push('DRIFT WROTE TO node.x — the frozen layout moved');

// a legitimate recompute MAY restart the sim — prove the distinction holds
const rc = store.get('iso');
if(rc && rc.onchange){
  rc.checked = true;
  rc.onchange({target:rc});
  runFrames(1);
  const stR = globalThis.window.__NP_STATE;
  const restarted = (stR && stR.settle < st0.settle);
  console.log('  filter toggle -> sim restarted :', restarted);
  if(!restarted) errors.push('A FILTER TOGGLE DID NOT RESTART THE LAYOUT');
}

// ==========================================================================
// PORT-ONLY CHECKS. Everything above also runs against knowledge/graph.html.
// ==========================================================================
if(PORTED){
  console.log('\n=== THE NETWORK LAYER (port only) ===');

  // 1. ESCAPING. graph.html put labels straight into innerHTML, which was
  //    harmless in a local file. This page holds a session token.
  // Fetch n7 explicitly and WAIT. The double-click above also triggers a
  // fetch, but its promise settles at the first await in this section — so
  // reading the panel without this saw the pre-fetch state, n7 was absent, and
  // the panel fell back to the bare id. The escaping assertion then compared
  // "n7" against the hostile string and passed having tested nothing.
  await (0,eval)('expand("n7")');
  await (0,eval)('openNode("n7")');
  await new Promise(r=>setTimeout(r,0));
  const panel = (store.get('nl')||{}).textContent || '';
  const prov  = (store.get('files')||{}).innerHTML || '';
  const nbrs  = (store.get('nbrs')||{}).innerHTML || '';
  console.log('  panel textContent is                   :', JSON.stringify(panel).slice(0,70));
  console.log('  hostile label reached textContent (safe):', panel===HOSTILE);
  const rawTagInHtml = /<img\s/i.test(prov) || /<img\s/i.test(nbrs);
  console.log('  raw <img> in any innerHTML             :', rawTagInHtml);
  console.log('  window.__PWNED                         :', !!globalThis.window.__PWNED);
  if(rawTagInHtml) errors.push('UNESCAPED MARKUP REACHED innerHTML — a corpus label can run script');
  if(globalThis.window.__PWNED) errors.push('THE HOSTILE LABEL EXECUTED');

  // 2. PROVENANCE must render corpus and hand as DIFFERENT THINGS, not one
  //    list with a flag. This was invisible for the whole project once.
  const hasCorpus = prov.includes('prov-corpus');
  const hasHand   = prov.includes('prov-hand');
  console.log('  provenance renders corpus distinctly   :', hasCorpus);
  console.log('  provenance renders hand distinctly     :', hasHand);
  if(!hasCorpus || !hasHand)
    errors.push('PROVENANCE DOES NOT DISTINGUISH hand FROM corpus IN THE UI');

  // 3. MERGE IDEMPOTENCE. Offline the graph arrived once. Online the same
  //    neighbourhood can be fetched repeatedly, and duplicating a node would
  //    double its degree — which is drawn as node radius, so it would look
  //    like a finding.
  const before = globalThis.window.__NP.data.nodes.length;
  const beforeEdges = globalThis.window.__NP.data.edges.length;
  await (0,eval)('expand("n3")');
  const mid = globalThis.window.__NP.data.nodes.length;
  await (0,eval)('expand("n3")');
  const after = globalThis.window.__NP.data.nodes.length;
  const afterEdges = globalThis.window.__NP.data.edges.length;
  console.log('  nodes before/after 1st/2nd expand      :', before, mid, after);
  console.log('  edges before/after                     :', beforeEdges, afterEdges);
  // Both directions. "Added nothing twice" is also what a broken merge that
  // adds nothing at all would print.
  if(mid <= before)
    errors.push('MERGE ADDED NOTHING — the idempotence check below is vacuous');
  if(after !== mid) errors.push('MERGE IS NOT IDEMPOTENT: a repeat fetch added nodes');
  const ids = globalThis.window.__NP.data.nodes.map(n=>n.id);
  if(new Set(ids).size !== ids.length) errors.push('DUPLICATE NODE IDS AFTER MERGE');

  // 4. THE CLIENT MUST NEVER ASK FOR THE WHOLE GRAPH.
  const urls = REQUESTS.map(r=>r.url);
  console.log('  requests made                          :', urls.length);
  const unbounded = urls.filter(u=>u.startsWith('/api/neighbourhood') && !u.includes('limit='));
  const wholeGraph = urls.filter(u=>/\/api\/(graph|all|nodes)\b/.test(u));
  console.log('  neighbourhood calls without a limit    :', unbounded.length);
  console.log('  whole-graph endpoints requested        :', wholeGraph.length);
  if(unbounded.length) errors.push('A NEIGHBOURHOOD FETCH CARRIED NO ROW LIMIT');
  if(wholeGraph.length) errors.push('THE CLIENT ASKED FOR THE WHOLE GRAPH');

  // 5. The depth cap must be REACHABLE and must fail loudly, not truncate.
  const depths=[...new Set(urls.filter(u=>u.includes('depth='))
    .map(u=>+(u.match(/depth=(\d+)/)||[])[1]))];
  console.log('  depths requested                       :', depths.join(',')||'none');
  if(depths.some(d=>d>3)) errors.push('REQUESTED A DEPTH BEYOND THE SERVER CAP OF 3');

  // 6. No token may be put in a URL, where it would land in access logs.
  const leaked = urls.filter(u=>/token|jwt|bearer|apikey/i.test(u));
  console.log('  urls carrying anything token-shaped    :', leaked.length);
  if(leaked.length) errors.push('A TOKEN APPEARED IN A URL: '+leaked[0]);
}

console.log('\nstat line:', (store.get('stat')||{}).innerHTML || '(never set)');
console.log('\n=== RESULT ===');
if(errors.length){ console.log('  FAILURES:'); errors.forEach(e=>console.log('   - '+e)); }
else console.log('  all checks passed');
process.exit(errors.length?1:0);
