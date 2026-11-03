/* Graph layouts (run 6, B2). Pure functions over plain data -- no Cytoscape,
   no DOM -- so the Graph page and the "/" map arrange records the same way,
   and so they can be tested without a browser.

   Input nodes: [{id, type, label, scope, rank, degree, bundle?: {anchor}}]
                rank = RANK[type] (style.js) for the hierarchy, null otherwise
   Input edges: [{source, target}]
   Output: Map id -> {x, y}

   hierarchy  Program > Course > Domain > Module > Week > Session in rows; each
              record's satellites (topics, people, links, custom types, bundles)
              in a small grid under it; a parent centred over its children;
              many leaf children wrap into a grid; separate trees are packed
              in shelves; records outside the hierarchy below it, by type.
              Every slot is wider than the widest label, so labels never
              overlap at 1:1.
   radial     rings of hop distance around the focused record.
   grouped    one region per group (type, program, ...), packed in shelves.
*/
export const SLOT_W = 156;      // > label max width (130) + padding: labels in a row never touch
export const CELL_H = 64;       // node + label + gap
const ROW_GAP = 48, TREE_GAP = 72, LEAF_WRAP = 5;

const byName = (a, b) => (a.label || '').localeCompare(b.label || '') || (a.id < b.id ? -1 : 1);

/* Who hangs off whom. Structural records get a parent of a higher level (the
   nearest level among their neighbours, their scope first among equals); every other record gets an
   anchor: its deepest structural neighbour, else its scope, else its most
   connected neighbour (strictly "bigger" than itself, so chains end). */
export function structure(nodes, edges) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const nb = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => { if (nb.has(e.source) && nb.has(e.target) && e.source !== e.target) { nb.get(e.source).push(e.target); nb.get(e.target).push(e.source); } });
  const deg = (id) => nb.get(id).length;
  const bigger = (a, b) => deg(a) > deg(b) || (deg(a) === deg(b) && a < b);
  const parent = new Map(), anchor = new Map();
  nodes.forEach((n) => {
    if (n.bundle) { anchor.set(n.id, n.bundle.anchor); return; }
    const near = nb.get(n.id).map((id) => byId.get(id));
    // the nearest level wins; among equals, the record's scope, then by name
    const pick = (list) => list.sort((a, b) => (b.rank - a.rank) || ((b.id === n.scope) - (a.id === n.scope)) || byName(a, b))[0];
    if (n.rank !== null && n.rank !== undefined) {
      const best = pick(near.filter((m) => m.rank !== null && m.rank !== undefined && m.rank < n.rank));
      if (best) parent.set(n.id, best.id);
      return;
    }
    const st = pick(near.filter((m) => m.rank !== null && m.rank !== undefined));
    if (st) { anchor.set(n.id, st.id); return; }
    if (n.scope && byId.has(n.scope) && n.scope !== n.id) { anchor.set(n.id, n.scope); return; }
    const big = near.filter((m) => !m.bundle && bigger(m.id, n.id)).sort((a, b) => (deg(b.id) - deg(a.id)) || (a.id < b.id ? -1 : 1))[0];
    if (big) anchor.set(n.id, big.id);
  });
  // a satellite of a satellite sits in the block of the record its chain ends at
  const owner = new Map();
  const ownerOf = (id, seen) => {
    if (owner.has(id)) return owner.get(id);
    const a = anchor.get(id);
    if (!a || !byId.has(a) || (seen && seen.has(a))) { owner.set(id, null); return null; }
    const s = seen || new Set(); s.add(id);
    const up = anchor.has(a) ? ownerOf(a, s) || a : a;
    owner.set(id, up); return up;
  };
  nodes.forEach((n) => { if (anchor.has(n.id)) ownerOf(n.id); });
  return { parent, anchor, owner, byId };
}

function gridSize(n, maxCols) {
  if (!n) return { cols: 0, rows: 0 };
  const cols = Math.max(1, Math.min(n, maxCols || Math.max(2, Math.ceil(Math.sqrt(n * 2.2)))));
  return { cols, rows: Math.ceil(n / cols) };
}

export function hierarchy(nodes, edges, opts) {
  opts = opts || {};
  const { parent, owner, byId } = structure(nodes, edges);
  const pos = new Map();
  const sats = new Map();                       // block owner -> satellites
  nodes.forEach((n) => { const o = owner.get(n.id); if (o) { if (!sats.has(o)) sats.set(o, []); sats.get(o).push(n); } });
  sats.forEach((list) => list.sort((a, b) => (a.bundle ? 1 : 0) - (b.bundle ? 1 : 0) || (a.type < b.type ? -1 : a.type > b.type ? 1 : 0) || byName(a, b)));
  const kids = new Map();
  const isStruct = (n) => n.rank !== null && n.rank !== undefined;
  nodes.forEach((n) => { const p = parent.get(n.id); if (p) { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(n); } });
  kids.forEach((l) => l.sort((a, b) => (a.rank - b.rank) || byName(a, b)));
  const satBlock = (id) => { const s = sats.get(id) || []; const g = gridSize(s.length, s.length > 12 ? undefined : 3); return { w: g.cols * SLOT_W, h: g.rows * CELL_H, g, s }; };
  const isLeaf = (n) => !kids.has(n.id) && !sats.has(n.id);

  // Bands: one per rank present, plus their heights (node + satellite block, or leaf grids).
  const bandH = {};
  const need = (r, h) => { bandH[r] = Math.max(bandH[r] || 0, h); };
  // Width of a subtree, memoised; leaf children of one rank wrap into a grid.
  const width = new Map(), items = new Map();
  const measure = (n) => {
    if (width.has(n.id)) return width.get(n.id);
    width.set(n.id, SLOT_W);                    // cycle guard
    const sb = satBlock(n.id);
    need(n.rank, CELL_H + sb.h);
    const list = [];
    const ch = kids.get(n.id) || [];
    const byRank = {};
    ch.forEach((c) => { (byRank[c.rank] = byRank[c.rank] || []).push(c); });
    Object.keys(byRank).sort((a, b) => a - b).forEach((r) => {
      const leaves = byRank[r].filter(isLeaf), rest = byRank[r].filter((c) => !isLeaf(c));
      if (leaves.length >= LEAF_WRAP) {
        const g = gridSize(leaves.length, Math.max(3, Math.ceil(Math.sqrt(leaves.length))));
        need(Number(r), g.rows * CELL_H);
        list.push({ grid: leaves, g, w: g.cols * SLOT_W });
      } else rest.unshift(...leaves);
      rest.forEach((c) => list.push({ node: c, w: measure(c) }));
    });
    items.set(n.id, list);
    const w = Math.max(SLOT_W, sb.w, list.reduce((s, it) => s + it.w, 0));
    width.set(n.id, w);
    return w;
  };
  const roots = nodes.filter((n) => isStruct(n) && !parent.has(n.id)).sort((a, b) => (a.rank - b.rank) || byName(a, b));
  roots.forEach(measure);
  const ranks = Object.keys(bandH).map(Number).sort((a, b) => a - b);
  const bandY = {}; let y = 0;
  ranks.forEach((r) => { bandY[r] = y; y += bandH[r] + ROW_GAP; });
  const treeH = y;

  const placeSats = (n, cx, top) => {
    const sb = satBlock(n.id);
    sb.s.forEach((s, i) => { const c = i % sb.g.cols, r = Math.floor(i / sb.g.cols);
      pos.set(s.id, { x: cx - sb.w / 2 + SLOT_W / 2 + c * SLOT_W, y: top + CELL_H + r * CELL_H }); });
  };
  const place = (n, x0, dy) => {
    const w = width.get(n.id);
    const list = items.get(n.id) || [];
    const total = list.reduce((s, it) => s + it.w, 0);
    let x = x0 + (w - total) / 2;
    const centres = [];
    list.forEach((it) => {
      if (it.grid) {
        const r = it.grid[0].rank;
        it.grid.forEach((c, i) => { const cc = i % it.g.cols, rr = Math.floor(i / it.g.cols);
          pos.set(c.id, { x: x + SLOT_W / 2 + cc * SLOT_W, y: dy + bandY[r] + rr * CELL_H }); });
        centres.push(x + it.w / 2);
      } else { place(it.node, x, dy); centres.push(pos.get(it.node.id).x); }
      x += it.w;
    });
    const cx = centres.length ? (Math.min(...centres) + Math.max(...centres)) / 2 : x0 + w / 2;
    pos.set(n.id, { x: cx, y: dy + bandY[n.rank] });
    placeSats(n, cx, dy + bandY[n.rank]);
  };

  // Shelf-pack the trees: aim for a landscape whole rather than one long row.
  const area = roots.reduce((s, r) => s + width.get(r.id), 0) * Math.max(treeH, CELL_H);
  const shelfW = Math.max(SLOT_W * 6, Math.sqrt(area * (opts.aspect || 1.6)));
  let sx = 0, sy = 0;
  roots.forEach((r) => {
    const w = width.get(r.id);
    if (sx > 0 && sx + w > shelfW) { sx = 0; sy += treeH + TREE_GAP; }
    // a tree only needs the bands from its own rank down
    place(r, sx, sy - bandY[r.rank] + (ranks.length ? bandY[ranks[0]] : 0));
    sx += w + TREE_GAP;
  });
  let bottom = roots.length ? sy + treeH + TREE_GAP : 0;
  const maxW = Math.max(shelfW, SLOT_W * 6);

  // Outside the hierarchy: records with no parent and no anchor (and their satellites), by type.
  const loose = nodes.filter((n) => !isStruct(n) && !owner.get(n.id) && !pos.has(n.id))
    .sort((a, b) => (a.type < b.type ? -1 : a.type > b.type ? 1 : 0) || (b.degree || 0) - (a.degree || 0) || byName(a, b));
  let lx = 0, ly = bottom, rowH = 0, lastType = null;
  loose.forEach((n) => {
    const sb = satBlock(n.id), w = Math.max(SLOT_W, sb.w), h = CELL_H + sb.h;
    if (lastType !== null && n.type !== lastType && lx > 0) { lx = 0; ly += rowH + ROW_GAP; rowH = 0; }
    if (lx > 0 && lx + w > maxW) { lx = 0; ly += rowH; rowH = 0; }
    pos.set(n.id, { x: lx + w / 2, y: ly });
    placeSats(n, lx + w / 2, ly);
    lx += w; rowH = Math.max(rowH, h); lastType = n.type;
  });
  // anything left (cycles among anchors): a final row
  let fx = 0; const fy = ly + rowH + ROW_GAP;
  nodes.forEach((n) => { if (!pos.has(n.id)) { pos.set(n.id, { x: fx + SLOT_W / 2, y: fy }); fx += SLOT_W; } });
  return pos;
}

/* Rings of hop distance around `focus`; each ring ordered by its parent's angle
   so lines cross less. Unreached records form an outer ring. */
export function radial(nodes, edges, focus) {
  const ids = new Set(nodes.map((n) => n.id));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const nb = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => { if (ids.has(e.source) && ids.has(e.target)) { nb.get(e.source).push(e.target); nb.get(e.target).push(e.source); } });
  const root = ids.has(focus) ? focus : (nodes.slice().sort((a, b) => (nb.get(b.id).length - nb.get(a.id).length))[0] || {}).id;
  const pos = new Map();
  if (!root) return pos;
  const dist = new Map([[root, 0]]), from = new Map(); const q = [root];
  while (q.length) { const c = q.shift(); nb.get(c).slice().sort().forEach((x) => { if (!dist.has(x)) { dist.set(x, dist.get(c) + 1); from.set(x, c); q.push(x); } }); }
  const maxD = Math.max(0, ...dist.values());
  const rings = [];
  nodes.forEach((n) => { const d = dist.has(n.id) ? dist.get(n.id) : maxD + 1; (rings[d] = rings[d] || []).push(n); });
  pos.set(root, { x: 0, y: 0 });
  const angle = new Map([[root, 0]]);
  let radius = 0;
  for (let d = 1; d < rings.length; d++) {
    const ring = rings[d] || []; if (!ring.length) continue;
    ring.sort((a, b) => ((angle.get(from.get(a.id)) || 0) - (angle.get(from.get(b.id)) || 0)) || (a.type < b.type ? -1 : 1) || byName(a, b));
    // the circumference fits every label: SLOT_W per record
    radius = Math.max(radius + 200, (ring.length * SLOT_W) / (2 * Math.PI));
    ring.forEach((n, i) => { const a = (2 * Math.PI * i) / ring.length - Math.PI / 2; angle.set(n.id, a); pos.set(n.id, { x: radius * Math.cos(a), y: radius * Math.sin(a) }); });
  }
  void byId;
  return pos;
}

/* One region per group key, packed in shelves; inside a region the records sit
   in a grid ordered by level, then name. `regions` comes back for the boxes. */
export function grouped(nodes, keyOf, labelOf) {
  const groups = new Map();
  nodes.forEach((n) => { const k = keyOf(n) || '__other'; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); });
  const keys = [...groups.keys()].sort((a, b) => (a === '__other') - (b === '__other') || String(labelOf(a)).localeCompare(String(labelOf(b))));
  const pos = new Map(), regions = new Map();
  const PAD = 24, HEAD = 34;
  const sizes = keys.map((k) => { const g = gridSize(groups.get(k).length); return { k, g, w: g.cols * SLOT_W + 2 * PAD, h: g.rows * CELL_H + HEAD + PAD }; });
  const area = sizes.reduce((s, x) => s + x.w * x.h, 0);
  const shelfW = Math.max(SLOT_W * 6, Math.sqrt(area * 1.6));
  let x = 0, y = 0, rowH = 0;
  sizes.forEach(({ k, g, w, h }) => {
    if (x > 0 && x + w > shelfW) { x = 0; y += rowH + TREE_GAP; rowH = 0; }
    const list = groups.get(k).sort((a, b) => ((a.rank === null || a.rank === undefined ? 9 : a.rank) - (b.rank === null || b.rank === undefined ? 9 : b.rank)) || byName(a, b));
    list.forEach((n, i) => pos.set(n.id, { x: x + PAD + SLOT_W / 2 + (i % g.cols) * SLOT_W, y: y + HEAD + CELL_H / 3 + Math.floor(i / g.cols) * CELL_H }));
    regions.set(k, { x1: x, y1: y, x2: x + w, y2: y + h, n: list.length });
    x += w + TREE_GAP; rowH = Math.max(rowH, h);
  });
  return { pos, regions };
}
