/* The NP Autopilot map at "/" in the knowledge base's visual language (run 6,
   B2). An adapter over style.js and layouts.js for public/index.html, which is
   a classic script: it loads this with a dynamic import() (CSP script-src
   'self' allows it; no build step).

     const L = await import('/kb/js/graph/map.js');
     const lang = await L.mapLanguage(window.__NP.api, token);   // GET /api/kb/types
     Object.assign(window.__NP.colors, lang.colors);              // node colours by map type
     lang.edgeColor('teaches')                                     // a relationship's colour
     L.homePositions(nodes, edges)                                 // the hierarchy layout

   The map keeps its own type keys (docs/architecture/contracts.md §5: its response shapes
   are frozen); MAP_TYPE says which knowledge base type each one is. A map type
   without a match keeps the map's own colour. */
import { RANK, looks, nodeLook, edgeLook } from './style.js';
import { hierarchy } from './layouts.js';

export const MAP_TYPE = { program: 'program', course: 'course', domain: 'domain', module: 'module', program_week: 'week',
  class_session: 'session', content_topic: 'topic', instructor: 'instructor', person: 'team_member', workflow: 'process', theme: 'theme' };

/* The map's look from the type metadata: colours, shapes and hierarchy levels by
   map type, relationship colours and dashes by relationship key. */
export function mapLook(meta) {
  const L = looks(meta);
  const colors = {}, shapes = {}, ranks = {};
  Object.entries(MAP_TYPE).forEach(([mt, kt]) => {
    if (!L.node[kt]) return;
    const k = nodeLook(L, kt);
    colors[mt] = k.color; shapes[mt] = k.shape; ranks[mt] = k.rank;
  });
  // the map draws on a dark ground: the same hues, lifted toward white for contrast
  const onDark = {}; Object.entries(colors).forEach(([k, c]) => { onDark[k] = lighten(c, 0.35); });
  return {
    colors, onDark, shapes, ranks, home: homePositions,
    edgeColor: (key) => edgeLook(L, key).color,
    edgeDash: (key) => edgeLook(L, key).dash,          // null = solid, else [dash, gap] for setLineDash
    edgeColorOnDark: (key) => lighten(edgeLook(L, key).color, 0.35),
    looks: L,
  };
}

/* Mix a #rrggbb colour with white by t (0..1). */
export function lighten(hex, t) {
  const h = String(hex || '').replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(h)) return hex;
  const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).map((v) => Math.round(v + (255 - v) * t));
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
}

export async function mapLanguage(apiBase, token) {
  const r = await fetch((apiBase || '/api') + '/kb/types', { headers: token ? { Authorization: 'Bearer ' + token } : {} });
  if (!r.ok) throw new Error('types ' + r.status);
  return mapLook(await r.json());
}

/* Home positions for the map's records: the same hierarchy as the Graph page
   (Program > Course > Domain > Module > Week > Session rows, satellites under
   their record). nodes: [{id, t, label}], edges: [{s, t}] in the map's shape. */
export function homePositions(nodes, edges) {
  return hierarchy(nodes.map((n) => { const kt = MAP_TYPE[n.t] || n.t; const r = RANK[kt];
    return { id: n.id, type: kt, label: n.label || n.l || '', scope: null, rank: r === undefined ? null : r, degree: 0 }; }),
  edges.map((e) => ({ source: e.s, target: e.t })));
}
