// Executes the SHIPPED inline scripts from graph.html against a minimal DOM shim.
// Catches the class of bug Node-level logic tests cannot: temporal dead zones,
// missing elements, exceptions in the render loop, NaN coordinates, zero-size
// canvas, and nodes drawn outside the viewport.
import {readFileSync} from 'node:fs';

const log=[], errors=[];
const el=(id)=>({id, style:{}, _html:'', _text:'', checked:false, value:'',
  dataset:{}, onclick:null, onchange:null,
  set innerHTML(v){this._html=v}, get innerHTML(){return this._html},
  set textContent(v){this._text=v}, get textContent(){return this._text},
  _h:{}, addEventListener(k,f){(this._h[k]=this._h[k]||[]).push(f)},
  querySelectorAll(){return []},
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
  querySelectorAll:(s)=>{
    if(s==='.ty') return ['theme','workflow','person','domain','program','module','instructor']
      .map(v=>{const e=el('ty-'+v); e.value=v; e.checked=true; return e});
    return [];
  }};
globalThis.window={};
globalThis.innerWidth=1600; globalThis.innerHeight=900;
globalThis.addEventListener=()=>{};
globalThis.performance={now:()=>Date.now()};
let frames=0, rafFn=null;
globalThis.requestAnimationFrame=(f)=>{rafFn=f};
// navigator is read-only in Node 22; the shipped code only touches navigator.clipboard

// pull the two inline <script> blocks out of the SHIPPED html
const html=readFileSync('knowledge/graph.html','utf8');
const blocks=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
console.log(`extracted ${blocks.length} inline script blocks from graph.html`);

try{ (0,eval)(blocks[0]); console.log('  data block: OK'); }
catch(e){ errors.push('DATA BLOCK: '+e.message); }

try{ (0,eval)(blocks[0]+'\n'+blocks[1]); console.log('  code block: OK (no throw at load)'); }
catch(e){ errors.push('CODE BLOCK THREW AT LOAD: '+e.constructor.name+': '+e.message); }

console.log('\n=== ERRORS AT LOAD ===');
if(!errors.length) console.log('  none');
errors.forEach(e=>console.log('  '+e));

// drive the animation loop by hand
if(rafFn){
  console.log('\n=== RENDER LOOP ===');
  let loopErr=null;
  try{ for(let i=0;i<200;i++){ painted={arcs:0,lines:0,arcPts:[]}; const f=rafFn; rafFn=null; f(); frames++; if(!rafFn) break; } }
  catch(e){ loopErr=e.constructor.name+': '+e.message; }
  console.log('  frames driven      :', frames);
  console.log('  error in loop      :', loopErr||'none');
  console.log('  arcs on last frame :', painted.arcs);
  console.log('  strokes on last fr :', painted.lines);
  const bad=painted.arcPts.filter(([x,y])=>!Number.isFinite(x)||!Number.isFinite(y));
  console.log('  NaN/Inf coords     :', bad.length);
  const onscreen=painted.arcPts.filter(([x,y])=>x>=0&&x<=1600&&y>=0&&y<=900);
  console.log('  arcs inside canvas :', onscreen.length, '/', painted.arcPts.length);
  if(painted.arcPts.length){
    const xs=painted.arcPts.map(p=>p[0]), ys=painted.arcPts.map(p=>p[1]);
    console.log('  x range            :', Math.round(Math.min(...xs)), '->', Math.round(Math.max(...xs)));
    console.log('  y range            :', Math.round(Math.min(...ys)), '->', Math.round(Math.max(...ys)));
  }
} else {
  console.log('\n=== RENDER LOOP NEVER STARTED — requestAnimationFrame was never called ===');
}

// ---- fire real interactions through the captured handlers ----
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
const before = {k:null};
let r1 = fire('click', pt[0], pt[1]);
console.log('  click on a node    : threw=' + (r1.threw||'no') +
            ', preventDefault=' + r1.preventDefaultCalled);
const right = store.get('right');
console.log('  panel opened       :', right.style.display==='block');
console.log('  panel title set    :', JSON.stringify((store.get('nl')||{}).textContent||''));
console.log('  connections listed :', ((store.get('nbrs')||{}).innerHTML||'').split('class="nb"').length-1);
console.log('  source files listed:', ((store.get('files')||{}).innerHTML||'').split('class="src"').length-1);
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
console.log('  <form> elements    :', (html.match(/<form/g)||[]).length);
console.log('  <a href> elements  :', (html.match(/<a href/g)||[]).length);
// state survives a click?
try{ const f=rafFn; rafFn=null; painted={arcs:0,lines:0,arcPts:[]}; f();
  console.log('  frame after click  : ' + painted.arcs + ' arcs still painted'); }
catch(e){ console.log('  frame after click  : THREW ' + e.message); }


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
// A drift that fails to move anything is dead decoration; a drift that moves
// node.x has re-introduced the bug. Assert both directions.
const paintA = JSON.stringify(painted.arcPts.slice(0,40));
const dataA = coordsOf();
let tick = Date.now();
globalThis.performance = {now: () => (tick += 400)};   // advance the clock
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
  runFrames(1);                       // state publishes on the next frame
  const stR = globalThis.window.__NP_STATE;
  console.log('  filter toggle -> sim restarted :', (stR && stR.settle < st0.settle));
}

console.log('\nstat line:', (store.get('stat')||{}).innerHTML || '(never set)');
process.exit(errors.length?1:0);
