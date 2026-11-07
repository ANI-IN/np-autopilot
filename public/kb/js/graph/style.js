/* The graph's visual language, in one place (run 6, B2). Pure: no imports, no
   DOM state, so both graphs share it -- the knowledge base Graph page and the
   NP Autopilot map at "/" (which loads it with a dynamic import()).

   Input is the type metadata from GET /api/kb/types (docs/architecture/contracts.md §3):
     node_types[]  key, label, plural, icon, color, shape, is_container
     edge_types[]  key, label, color, line_style
   Output:
     looks(meta)            {node: {key: look}, edge: {key: look}} for any renderer
     cyStyle(meta, tok)     Cytoscape style rules (per type and per relationship)
     legendShape(shape, c)  a 14px SVG of a node shape, for legends
     iconUri(markup)        a white icon as a data: URI, for a node's background
   An unknown or custom type without metadata gets a neutral "generic" look. */

/* The hierarchy the default layout shows, top to bottom (run C, 2026-11-07: Program > Course > Module,
   a module's live sessions below it). Every other type is a satellite of the record it hangs off:
   topics, people, links, custom types, and DOMAINS, which classify records instead of containing them. */
export const RANK = { program: 0, course: 1, module: 2, session: 3 };

/* Contract shape names -> Cytoscape shapes (rounded where Cytoscape has one). */
const CY_SHAPE = { 'round-rectangle': 'round-rectangle', ellipse: 'ellipse', diamond: 'round-diamond', hexagon: 'round-hexagon',
  triangle: 'round-triangle', rectangle: 'rectangle', tag: 'round-tag', barrel: 'barrel' };
const SIZE = [48, 42, 36, 28];                  // by rank; satellites 24
const FONT = [15, 14, 13, 12];                  // labels of higher levels stay legible further out
const NEUTRAL = '#64748b';

/* Shown or not, from the classes alone: Cytoscape's ':visible' lags behind a
   class change made in the same tick (style is recomputed lazily). */
const OFF = ['hidden', 'bundled', 'folded'];
export function isShown(e) {
  if (e.isNode()) return !OFF.some((c) => e.hasClass(c));
  return !e.hasClass('hidden') && !e.hasClass('lod') && isShown(e.source()) && isShown(e.target());
}

export function cyShape(shape) { return CY_SHAPE[shape] || 'ellipse'; }

export function looks(meta) {
  const node = {}, edge = {};
  (meta.node_types || []).forEach((t) => {
    const r = RANK[t.key];
    node[t.key] = { label: t.label, plural: t.plural || t.label, color: t.color || NEUTRAL, shape: t.shape || 'ellipse', cyShape: cyShape(t.shape),
      icon: t.icon || 'box', rank: r === undefined ? null : r, size: r === undefined ? 24 : SIZE[r], font: r === undefined ? 11 : FONT[r],
      strong: r !== undefined && r <= 2 };
  });
  (meta.edge_types || []).forEach((t) => {
    edge[t.key] = { label: t.label, color: t.color || NEUTRAL, style: t.line_style || 'solid',
      dash: t.line_style === 'dashed' ? [6, 4] : t.line_style === 'dotted' ? [1.5, 3] : null };
  });
  return { node, edge, generic: { color: NEUTRAL, shape: 'ellipse', cyShape: 'ellipse', icon: 'box', rank: null, size: 24, font: 11 } };
}

/* A record type's look, falling back to the generic one. */
export function nodeLook(L, key) { return L.node[key] || L.generic; }
export function edgeLook(L, key) { return L.edge[key] || { label: key, color: NEUTRAL, style: 'solid', dash: null }; }

/* Cytoscape rules. `tok(name, fallback)` reads a design token (colours follow
   the theme); `icons` maps an icon name to a data: URI (optional). */
export function cyStyle(meta, tok, icons) {
  const L = looks(meta);
  const text = tok('--text', '#18181b'), bg = tok('--bg', '#ffffff'), faint = tok('--text-3', '#71717a');
  const accent = tok('--accent', '#1d4ed8'), strong = tok('--border-strong', '#d4d4d8'), warn = tok('--warn', '#a16207');
  const rules = [
    { selector: 'node', style: { 'background-color': NEUTRAL, shape: 'ellipse', width: 24, height: 24, label: 'data(label)',
      'font-size': 11, 'font-family': 'Inter, system-ui, sans-serif', 'font-weight': 400, color: text,
      'text-valign': 'bottom', 'text-halign': 'center', 'text-margin-y': 5, 'text-max-width': 130, 'text-wrap': 'ellipsis',
      'text-background-color': bg, 'text-background-opacity': 0.85, 'text-background-padding': 2,
      'min-zoomed-font-size': 7, 'background-width': '58%', 'background-height': '58%', 'background-clip': 'none',
      'border-width': 0, 'transition-property': 'opacity', 'transition-duration': 0 } },
    { selector: 'edge', style: { width: 1.2, 'line-color': strong, 'target-arrow-color': strong, 'target-arrow-shape': 'triangle', 'arrow-scale': 0.7,
      'curve-style': 'bezier', opacity: 0.6, label: 'data(label)', 'font-size': 10, color: faint, 'text-rotation': 'autorotate', 'text-opacity': 0,
      'text-background-color': bg, 'text-background-opacity': 0.9, 'text-background-padding': 2, 'min-zoomed-font-size': 7 } },
  ];
  Object.entries(L.node).forEach(([key, k]) => {
    const st = { 'background-color': k.color, shape: k.cyShape, width: k.size, height: k.size, 'font-size': k.font, 'font-weight': k.strong ? 600 : 400 };
    if (k.strong) st['text-max-width'] = 200;
    if (icons && icons[k.icon]) st['background-image'] = icons[k.icon];
    rules.push({ selector: 'node[type = "' + key + '"]', style: st });
  });
  Object.entries(L.edge).forEach(([key, k]) => {
    const st = { 'line-color': k.color, 'target-arrow-color': k.color, 'line-style': k.style === 'solid' ? 'solid' : k.style };
    if (k.dash) st['line-dash-pattern'] = k.dash;
    rules.push({ selector: 'edge[type = "' + key + '"]', style: st });
  });
  rules.push(
    // states: legacy and archived records read as "not current"
    { selector: 'node.legacy', style: { 'background-opacity': 0.45, 'border-width': 1.5, 'border-style': 'dashed', 'border-color': faint } },
    { selector: 'node.archived', style: { opacity: 0.5, 'border-width': 1.5, 'border-style': 'dotted', 'border-color': faint } },
    { selector: 'edge.legacy', style: { opacity: 0.35 } },
    // bundles: many satellites of one type behind one bubble; groups: a box per category
    { selector: 'node.bundle', style: { width: 'data(size)', height: 'data(size)', 'background-opacity': 0.18, 'border-width': 1.5,
      'border-color': 'data(color)', 'background-color': 'data(color)', 'background-image': 'none', 'font-weight': 600, 'font-size': 11 } },
    // the hierarchy's own lines run as a tree (orthogonal, downward)
    { selector: 'edge.tree', style: { 'curve-style': 'taxi', 'taxi-direction': 'downward', 'taxi-turn': 28, 'taxi-turn-min-distance': 6, 'arrow-scale': 0.6 } },
    { selector: 'edge.bundle-edge', style: { width: 'data(w)', opacity: 0.45, 'target-arrow-shape': 'none' } },
    { selector: 'node.gbox', style: { shape: 'round-rectangle', 'background-color': faint, 'background-opacity': 0.04, 'border-width': 1, 'border-color': strong,
      width: 'data(w)', height: 'data(h)', label: '', events: 'no', 'z-compound-depth': 'bottom', 'background-image': 'none' } },
    { selector: 'node.ghead', style: { shape: 'round-rectangle', width: 'data(w)', height: 22, 'background-opacity': 0, label: 'data(label)',
      'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': 14, 'font-size': 12, 'font-weight': 600, color: faint,
      'text-max-width': 'data(w)', 'text-background-opacity': 0, 'background-image': 'none', 'min-zoomed-font-size': 5 } },
    { selector: 'node.collapsed', style: { width: 'data(size)', height: 'data(size)', 'border-width': 2, 'border-color': 'data(color)',
      'background-color': 'data(color)', 'background-opacity': 0.22, 'font-weight': 600, 'background-image': 'none' } },
    // semantic zoom: zoomed out, the hierarchy's labels grow (labels.js keeps them apart)
    // zoomed out: the top of the hierarchy keeps a constant on-screen size (graph.js lod())
    { selector: 'node.farlabel', style: { 'font-size': 'data(fz)', 'text-max-width': 'data(fw)', 'text-margin-y': 4,
      'font-weight': 600, 'text-opacity': 1, 'text-background-opacity': 0.92, 'min-zoomed-font-size': 0 } },
    // reading aids
    { selector: 'node.center', style: { 'border-width': 3, 'border-color': text } },
    { selector: 'node.nolabel', style: { 'text-opacity': 0 } },
    { selector: 'node.hover', style: { 'text-opacity': 1, 'z-index': 20, 'text-background-opacity': 1 } },
    // relationships across the hierarchy stay faint until a record at either end is hovered or selected
    { selector: 'edge.cross', style: { opacity: 0.16 } },
    { selector: 'edge.hover-near, edge.sel-near', style: { opacity: 0.9 } },
    { selector: 'edge.hover, edge:selected, edge.focus-edge', style: { 'text-opacity': 1, opacity: 1, width: 2 } },
    { selector: 'edge.hover, edge:selected', style: { 'line-color': accent, 'target-arrow-color': accent } },
    { selector: 'node:selected', style: { 'border-width': 3, 'border-color': accent, 'underlay-color': accent, 'underlay-opacity': 0.12, 'underlay-padding': 6, 'text-opacity': 1 } },
    { selector: 'node.found', style: { 'underlay-color': warn, 'underlay-opacity': 0.35, 'underlay-padding': 10, 'text-opacity': 1 } },
    { selector: 'node.dim', style: { opacity: 0.14, 'text-opacity': 0 } },
    { selector: 'edge.dim', style: { opacity: 0.06 } },
    { selector: 'edge.lod', style: { display: 'none' } },
    { selector: 'node.connect-src', style: { 'border-width': 4, 'border-color': warn } },
    { selector: 'node.presence', style: { 'border-width': 3, 'border-style': 'dashed', 'border-color': tok('--ok', '#15803d') } },
    { selector: 'node.ghost', style: { width: 1, height: 1, opacity: 0, label: '' } },
    { selector: 'edge.ghost', style: { 'line-style': 'dashed', 'line-color': accent, 'target-arrow-color': accent, width: 2, label: '', opacity: 1 } },
    { selector: '.hidden, .bundled, .folded', style: { display: 'none' } },
  );
  return rules;
}

/* A 14px legend swatch of a contract shape, filled with the type colour. */
const PATHS = { hexagon: 'M4 1h6l3 6-3 6H4L1 7z', 'round-rectangle': 'M3 3h8a2 2 0 012 2v4a2 2 0 01-2 2H3a2 2 0 01-2-2V5a2 2 0 012-2z',
  rectangle: 'M1 3h12v8H1z', ellipse: 'M7 1a6 6 0 110 12A6 6 0 017 1z', tag: 'M1 3h9l3 4-3 4H1z',
  barrel: 'M3 1h8c1.5 2 1.5 10 0 12H3C1.5 11 1.5 3 3 1z', diamond: 'M7 1l6 6-6 6-6-6z', triangle: 'M7 1l6 12H1z' };
export function legendShape(shape, color) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 14 14'); svg.setAttribute('class', 'legend-shape'); svg.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS(NS, 'path');
  p.setAttribute('d', PATHS[shape] || PATHS.ellipse); p.setAttribute('fill', color);
  svg.appendChild(p);
  return svg;
}
/* A 14x6 legend swatch of a relationship line (colour and dash). */
export function legendLine(look) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 18 6'); svg.setAttribute('class', 'legend-edge'); svg.setAttribute('aria-hidden', 'true');
  svg.dataset.color = look.color; svg.dataset.line = look.style;
  const l = document.createElementNS(NS, 'line');
  l.setAttribute('x1', '1'); l.setAttribute('y1', '3'); l.setAttribute('x2', '17'); l.setAttribute('y2', '3');
  l.setAttribute('stroke', look.color); l.setAttribute('stroke-width', '2');
  if (look.style === 'dashed') l.setAttribute('stroke-dasharray', '4 2.5');
  if (look.style === 'dotted') { l.setAttribute('stroke-dasharray', '1 2.5'); l.setAttribute('stroke-linecap', 'round'); }
  svg.appendChild(l);
  return svg;
}

/* Icons for node backgrounds: the Lucide sprite's <symbol> markup, stroked
   white, as standalone SVG data: URIs (CSP img-src allows data:). */
export function iconUri(symbolInner, viewBox) {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="' + (viewBox || '0 0 24 24') +
    '" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' + symbolInner + '</svg>';
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}
export async function loadIcons(names, spriteUrl) {
  const out = {};
  try {
    const txt = await (await fetch(spriteUrl || '/vendor/lucide-sprite.svg')).text();
    const doc = new DOMParser().parseFromString(txt, 'image/svg+xml');
    new Set(names).forEach((n) => {
      const s = doc.getElementById('i-' + n);
      if (s) out[n] = iconUri(Array.from(s.childNodes).map((c) => new XMLSerializer().serializeToString(c)).join('').replace(/ xmlns="[^"]*"/g, ''), s.getAttribute('viewBox'));
    });
  } catch (e) { /* icons are decoration; shapes and colours still say the type */ }
  return out;
}
