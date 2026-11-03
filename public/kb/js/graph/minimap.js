import { isShown } from './style.js';
/* Minimap (run 3, moved here in run 6). The records are drawn once into a
   cached layer when the graph changes; moving the view only redraws the
   viewport rectangle on top, so panning thousands of records stays cheap.
   Click or drag on it to move the view. */
export function createMinimap(cy, canvas, tok, isRecord) {
  let base = null, dirty = true, map = null, queued = false;
  function drawBase() {
    const W = canvas.width, H = canvas.height;
    base = base || document.createElement('canvas'); base.width = W; base.height = H;
    const ctx = base.getContext('2d'); ctx.clearRect(0, 0, W, H);
    const nodes = cy.nodes().filter(isShown).filter(isRecord);
    map = null; dirty = false;
    if (!nodes.length) return;
    const bb = nodes.boundingBox({ includeLabels: false }); const pad = 16;
    const sc = Math.min((W - 2 * pad) / Math.max(bb.w, 1), (H - 2 * pad) / Math.max(bb.h, 1));
    const ox = (W - bb.w * sc) / 2, oy = (H - bb.h * sc) / 2;
    const tx = (x) => ox + (x - bb.x1) * sc, ty = (y) => oy + (y - bb.y1) * sc;
    map = { tx, ty, sc, bb, ox, oy };
    if (nodes.length < 2500) {
      ctx.strokeStyle = tok('--border-strong', '#ccc'); ctx.lineWidth = 1; ctx.beginPath();
      cy.edges().filter(isShown).forEach((e) => { ctx.moveTo(tx(e.source().position('x')), ty(e.source().position('y'))); ctx.lineTo(tx(e.target().position('x')), ty(e.target().position('y'))); });
      ctx.stroke();
    }
    nodes.forEach((n) => { ctx.fillStyle = n.data('color') || '#64748b'; const s = n.hasClass('bundle') || n.hasClass('collapsed') ? 6 : 4; ctx.fillRect(tx(n.position('x')) - s / 2, ty(n.position('y')) - s / 2, s, s); });
  }
  function draw() {
    if (dirty) drawBase();
    const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (base) ctx.drawImage(base, 0, 0);
    if (!map) return;
    const ext = cy.extent(), W = canvas.width, H = canvas.height;
    ctx.strokeStyle = tok('--accent', '#1d4ed8'); ctx.lineWidth = 2;
    const x1 = Math.max(1, map.tx(ext.x1)), y1 = Math.max(1, map.ty(ext.y1)), x2 = Math.min(W - 1, map.tx(ext.x2)), y2 = Math.min(H - 1, map.ty(ext.y2));
    if (x2 > x1 && y2 > y1) ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  }
  function invalidate() { dirty = true; schedule(); }
  function schedule() { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; draw(); }); } }
  function moveTo(e) {
    if (!map) return;
    const r = canvas.getBoundingClientRect();
    const mx = (e.clientX - r.left) * (canvas.width / r.width), my = (e.clientY - r.top) * (canvas.height / r.height);
    const x = (mx - map.ox) / map.sc + map.bb.x1, y = (my - map.oy) / map.sc + map.bb.y1;
    cy.pan({ x: cy.width() / 2 - x * cy.zoom(), y: cy.height() / 2 - y * cy.zoom() });
  }
  let down = false;
  const onMove = (e) => { if (down) moveTo(e); };
  const onUp = () => { down = false; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  canvas.addEventListener('mousedown', (e) => { down = true; moveTo(e); window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp); });
  canvas.addEventListener('keydown', (e) => {
    const d = 80, k = e.key, p = cy.pan();
    if (k === 'ArrowLeft') cy.pan({ x: p.x + d, y: p.y }); else if (k === 'ArrowRight') cy.pan({ x: p.x - d, y: p.y });
    else if (k === 'ArrowUp') cy.pan({ x: p.x, y: p.y + d }); else if (k === 'ArrowDown') cy.pan({ x: p.x, y: p.y - d }); else return;
    e.preventDefault(); e.stopPropagation();
  });
  cy.on('add remove dragfree', invalidate);
  cy.on('viewport', schedule);
  return { invalidate, draw: schedule, get map() { return map; } };
}
