import { isShown } from './style.js';
/* Labels that never overlap (run 6, B2). After every layout and whenever the
   view settles, the visible labels inside the viewport are placed greedily in
   priority order (selected, found, the focused record and its neighbours,
   higher levels of the hierarchy, then the most connected); a label that would
   overlap one already placed, or another record's shape, is hidden (class
   `nolabel`, which keeps its box) and comes back on hover or focus. */
export function declutter(cy, opts) {
  const minPx = (opts && opts.minPx) || 7;
  const z = cy.zoom(), ext = cy.extent();
  const nodes = cy.nodes().filter(isShown).filter((n) => !n.hasClass('gbox') && !n.hasClass('ghost'));
  const keep = [], grid = new Map(), CELL = 120;
  const ok = (b) => isFinite(b.x1) && isFinite(b.x2) && isFinite(b.y1) && isFinite(b.y2) && b.x2 - b.x1 < 1e5 && b.y2 - b.y1 < 1e5;
  const cells = (b) => { const out = []; if (!ok(b)) return out; for (let x = Math.floor(b.x1 / CELL); x <= Math.floor(b.x2 / CELL); x++) for (let y = Math.floor(b.y1 / CELL); y <= Math.floor(b.y2 / CELL); y++) out.push(x + ':' + y); return out; };
  const hit = (b, self) => { for (const c of cells(b)) for (const o of grid.get(c) || []) if (o.self !== self && b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1) return true; return false; };
  const put = (b) => { keep.push(b); cells(b).forEach((c) => { if (!grid.has(c)) grid.set(c, []); grid.get(c).push(b); }); };
  const inView = nodes.filter((n) => { const p = n.position(); return p.x > ext.x1 - 320 && p.x < ext.x2 + 320 && p.y > ext.y1 - 320 && p.y < ext.y2 + 320; });
  // the hierarchy's shapes are obstacles too (a label may cross a satellite)
  inView.forEach((n) => { if (n.data('rank') === null || n.data('rank') === undefined) return;
    const b = n.boundingBox({ includeLabels: false, includeOverlays: false }); put({ x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2, self: n.id() }); });
  const score = (n) => (n.selected() ? 1e6 : 0) + (n.hasClass('found') ? 5e5 : 0) + (n.hasClass('center') || n.hasClass('focus') ? 2e5 : 0) +
    (n.hasClass('near') ? 1e5 : 0) + (n.hasClass('dim') ? -1e6 : 0) + (n.isParent() ? 0 : 0) + (10 - (n.data('rank') === undefined || n.data('rank') === null ? 9 : n.data('rank'))) * 1e3 + (n.degree(false) || 0);
  const shown = [], hidden = [];
  inView.sort((a, b) => score(b) - score(a)).forEach((n) => {
    if (n.hasClass('ghead') || !n.data('label')) return;
    const fs = parseFloat(n.pstyle('font-size').strValue) || 11;
    if (fs * z < minPx || n.hasClass('dim')) { hidden.push(n); return; }      // too small to read anyway
    const lb = n.boundingBox({ includeNodes: false, includeEdges: false, includeLabels: true, includeOverlays: false });
    if (!lb || !isFinite(lb.x1) || lb.w === 0) { shown.push(n); return; }
    const b = { x1: lb.x1, y1: lb.y1, x2: lb.x2, y2: lb.y2, self: n.id() };
    if (hit(b, n.id())) hidden.push(n); else { put(b); shown.push(n); }
  });
  cy.batch(() => { shown.forEach((n) => n.removeClass('nolabel')); hidden.forEach((n) => n.addClass('nolabel')); });
  return { shown: shown.length, hidden: hidden.length };
}

/* The visible, readable labels' boxes (rendered px, inside the viewport) -- for tests and checks. */
export function labelBoxes(cy, minPx) {
  const z = cy.zoom(), W = cy.width(), H = cy.height();
  return cy.nodes().filter(isShown).filter((n) => !n.hasClass('nolabel') && !n.hasClass('gbox') && !n.hasClass('ghead') && !n.hasClass('dim') && n.data('label') &&
    (parseFloat(n.pstyle('font-size').strValue) || 11) * z >= (minPx || 7))
    .map((n) => ({ id: n.id(), b: n.renderedBoundingBox({ includeNodes: false, includeEdges: false, includeLabels: true, includeOverlays: false }) }))
    .filter((x) => x.b.x2 > 0 && x.b.y2 > 0 && x.b.x1 < W && x.b.y1 < H);
}
