// Drives the SHIPPED render logic (knowledge/_graph_logic.mjs — the identical
// string inlined into graph.html) against the real payload.
// Exercises: search, type/theme filters, component split, edge cap, click-through.
// Does NOT exercise: canvas painting, real mouse events, browser layout.
import {readFileSync} from 'node:fs';
import {buildIndex, components, search, visible, degreeMap, neighboursOf}
  from '../knowledge/_graph_logic.mjs';

const D = JSON.parse(readFileSync('knowledge/_graph_data.json','utf8'));
const FULL = JSON.parse(readFileSync('knowledge/graph.json','utf8'));
const ms = f => {const t=performance.now(); const r=f(); return [r, performance.now()-t];};
const line = s => console.log(s);

line('='.repeat(74));
line('DRIVING graph.html — shipped logic, real data');
line('='.repeat(74));
line(`render payload : ${D.nodes.length} nodes, ${D.edges.length} edges`);
line(`full graph.json: ${FULL.nodes.length} nodes, ${FULL.edges.length} edges`);

const [idx, tIdx] = ms(() => buildIndex(D));
line(`index build    : ${tIdx.toFixed(1)} ms  (once, not per keystroke)`);
const allDeg = degreeMap(D, D.nodes.map(n=>n.id));

// ---------- 1. search "8.2"
line('\n--- 1. typed "8.2" in the search box ---');
const [h1,t1] = ms(()=>search(idx.idx,'8.2',40));
line(`  ${h1.length} hits in ${t1.toFixed(2)} ms`);
h1.slice(0,4).forEach(id=>{const n=idx.byId.get(id);
  line(`    ${n.t.padEnd(10)} ${n.l}${n.wid?'   [workflow '+n.wid+']':''}`)});

// ---------- 2. search "rating"
line('\n--- 2. typed "rating" ---');
const [h2,t2] = ms(()=>search(idx.idx,'rating',40));
line(`  ${h2.length} hits in ${t2.toFixed(2)} ms`);
h2.slice(0,5).forEach(id=>{const n=idx.byId.get(id);
  line(`    ${n.t.padEnd(10)} ${n.l}`)});

// ---------- 3. search a person
line('\n--- 3. typed "Animesh" ---');
const [h3,t3] = ms(()=>search(idx.idx,'animesh',40));
line(`  ${h3.length} hits in ${t3.toFixed(2)} ms`);
h3.forEach(id=>{const n=idx.byId.get(id); line(`    ${n.t.padEnd(10)} ${n.l}  (${n.d} relationships)`)});

// ---------- 4. click a workflow -> follow to source file
line('\n--- 4. clicked workflow 8.2, then followed its connections ---');
const w82 = D.nodes.find(n=>n.wid==='8.2');
if(!w82){ line('  FAIL: workflow 8.2 not in the render payload'); }
else {
  line(`  opened: ${w82.l}`);
  line(`    type=${w82.t} effort=${w82.eff ?? '(none)'} alerts=${w82.al}`);
  const nb = neighboursOf(idx, w82.id, 8, false);
  line(`    connections: ${nb.total} total, ${nb.shown.length} shown, ${nb.hidden} behind "show more"`);
  nb.shown.forEach(x=>{const o=idx.byId.get(x.o);
    line(`      -> ${o.l}  [${x.r}, ${o.t}]`)});
  line(`    source files:`);
  (w82.files||[]).forEach(f=>line(`      ${f.f}${f.sh?' !'+f.sh:''}${f.r?' r'+f.r:''}`));
  const exp = neighboursOf(idx, w82.id, 8, true);
  line(`    after "show more": ${exp.shown.length} shown, ${exp.hidden} hidden`);
}

// ---------- 4b. click a domain -> owner -> source
line('\n--- 4b. clicked domain "Cloud", followed to its owner, then that owner\'s source ---');
const cloud = D.nodes.find(n=>n.t==='domain' && n.l==='Cloud');
const cn = neighboursOf(idx, cloud.id, 8, true);
line(`  ${cloud.l}: ${cn.total} connections`);
const owner = cn.shown.find(x=>x.r==='owned_by');
if(owner){ const o=idx.byId.get(owner.o);
  line(`    owned_by -> ${o.l} (${o.t})`);
  line(`    that person's source files:`);
  (o.files||[]).forEach(f=>line(`      ${f.f}${f.sh?' !'+f.sh:''}${f.r?' r'+f.r:''}`));
} else line('    FAIL: no owned_by edge reachable');

// ---------- 5. filter to one theme
line('\n--- 5. selected theme 2 (INSTRUCTORS) in the theme filter ---');
const [vis5,t5] = ms(()=>visible(D,{types:new Set(D.nodes.map(n=>n.t)),
  themes:new Set(['2']), showIso:false, showHired:true, degree:allDeg}));
line(`  ${vis5.length} nodes visible in ${t5.toFixed(2)} ms`);
const kinds={}; vis5.forEach(n=>kinds[n.t]=(kinds[n.t]||0)+1);
line(`  by type: ${JSON.stringify(kinds)}`);

// ---------- 6. hide instructors + expert_in
line('\n--- 6. unticked "instructor", unticked dashed expert_in ---');
const types = new Set(D.nodes.map(n=>n.t)); types.delete('instructor');
const [vis6,t6] = ms(()=>visible(D,{types, themes:null, showIso:false,
  showHired:true, degree:allDeg}));
const ids6=new Set(vis6.map(n=>n.id));
const e6 = D.edges.filter(e=>ids6.has(e.s)&&ids6.has(e.t)&&e.r!=='expert_in');
line(`  ${vis6.length} nodes, ${e6.length} edges in ${t6.toFixed(2)} ms`);

// ---------- 7. component separation
line('\n--- 7. component split (the "one ball" question) ---');
const visAll = visible(D,{types:new Set(D.nodes.map(n=>n.t)),themes:null,
  showIso:false,showHired:true,degree:allDeg});
const idsAll=new Set(visAll.map(n=>n.id));
const eAll=D.edges.filter(e=>idsAll.has(e.s)&&idsAll.has(e.t));
const [comps,t7]=ms(()=>components({nodes:visAll,edges:eAll},visAll.map(n=>n.id)));
line(`  ${comps.length} components in ${t7.toFixed(1)} ms`);
comps.slice(0,6).forEach((c,i)=>{
  const k={}; c.forEach(id=>{const n=idx.byId.get(id);k[n.t]=(k[n.t]||0)+1});
  line(`    #${i+1}  ${String(c.length).padStart(5)} nodes  ${JSON.stringify(k)}`)});

// ---------- 8. worst-case search on the FULL graph
line('\n--- 8. responsiveness at full graph.json scale ---');
const fullSlim={nodes:FULL.nodes.map(n=>({id:n.id,l:n.label,t:n.type})),edges:[]};
const [fidx,tf]=ms(()=>buildIndex(fullSlim));
line(`  index ${FULL.nodes.length} nodes: ${tf.toFixed(1)} ms`);
for(const q of ['a','e','rating','singh']){
  const [h,t]=ms(()=>search(fidx.idx,q,40));
  line(`  search ${JSON.stringify(q).padEnd(10)} -> ${String(h.length).padStart(3)} hits (capped 40) in ${t.toFixed(2)} ms`);
}

// ---------- 9. FILE SEARCH (added after the file-results request)
import {searchFiles, entitiesOf} from '../knowledge/_graph_logic.mjs';
const F = JSON.parse(readFileSync('knowledge/_graph_files.json','utf8'));
line('\n--- 9. typed "backend" — file results section ---');
const [fh,tf9] = ms(()=>searchFiles(F,idx,'backend',15));
line(`  ${fh.length} file hits in ${tf9.toFixed(2)} ms`);
fh.slice(0,6).forEach(f=>line(`    [${f.kind.padEnd(8)}] ${f.path}   (${f.matchedTotal} matching entities of ${f.total})`));
line('\n--- 10. clicked a file result -> reverse provenance ---');
const target = fh.find(f=>f.kind==='contains') || fh[0];
if(target){
  const ents = entitiesOf(F, target.path);
  const kinds={}; ents.forEach(e=>{const n=idx.byId.get(e.i); if(n)kinds[n.t]=(kinds[n.t]||0)+1});
  line(`  ${target.path}`);
  line(`    ${ents.length} entities sourced from it: ${JSON.stringify(kinds)}`);
  ents.slice(0,4).forEach(e=>{const n=idx.byId.get(e.i);
    line(`      ${n.t.padEnd(10)} ${n.l}${e.sh?'  !'+e.sh:''}${e.r?' r'+e.r:''}`)});
  line(`    drive_url: ${target.drive ?? '(null — link inactive until pass 0 runs)'}`);
}
line('\n--- 11. searched a filename directly, to see what it yielded ---');
for(const fname of ['UpLevel Schedule Structure','Taking Class Confirmation']){
  const hits = searchFiles(F,idx,fname,5);
  const h = hits[0];
  if(h){ const e=entitiesOf(F,h.path);
    const k={}; e.forEach(x=>{const n=idx.byId.get(x.i); if(n)k[n.t]=(k[n.t]||0)+1});
    line(`  ${h.path}`);
    line(`    yielded ${e.length} entities ${e.length?JSON.stringify(k):'<-- NOTHING'}`);
  } else line(`  ${fname}: no file hit`);
}
