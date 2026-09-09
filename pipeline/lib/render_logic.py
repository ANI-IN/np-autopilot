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

// Edge cap: a node with more than CAP neighbours shows CAP, rest behind a click.
export function neighboursOf(index,id,cap,expanded){
  const all=index.adj.get(id)||[];
  const shown=(expanded)?all:all.slice(0,cap);
  return {shown,hidden:Math.max(0,all.length-shown.length),total:all.length};
}
"""
