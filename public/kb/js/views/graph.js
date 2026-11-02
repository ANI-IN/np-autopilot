/* Graph: a neighbourhood around one record (never the whole graph), shape and
   colour by type, legend + filter panel, minimap, fit, connect mode, and the
   same detail panel on selection. */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, toast, failToast, qs, setQuery, empty, errorBox, combobox, nodeSource,
  openDialog, closeDialog, can } from '../core.js';

const SHAPES = { program: 'round-hexagon', course: 'round-rectangle', domain: 'round-pentagon', module: 'ellipse', week: 'round-tag',
  session: 'barrel', topic: 'ellipse', instructor: 'round-diamond', process: 'round-triangle' };
const SHAPE_ICON = { 'round-hexagon': 'hexagon', 'round-rectangle': 'rect', 'round-pentagon': 'penta', ellipse: 'circle', 'round-tag': 'tag', barrel: 'barrel', 'round-diamond': 'diamond', 'round-triangle': 'tri' };

function legendShape(shape, color) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 14 14'); svg.setAttribute('class', 'legend-shape'); svg.setAttribute('aria-hidden', 'true');
  const paths = { hexagon: 'M4 1h6l3 6-3 6H4L1 7z', rect: 'M2 3h10a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V4a1 1 0 011-1z', penta: 'M7 1l6 4.5-2.3 7H3.3L1 5.5z',
    circle: 'M7 1a6 6 0 110 12A6 6 0 017 1z', tag: 'M1 3h9l3 4-3 4H1z', barrel: 'M3 1h8c1.5 2 1.5 10 0 12H3C1.5 11 1.5 3 3 1z', diamond: 'M7 1l6 6-6 6-6-6z', tri: 'M7 1l6 12H1z' };
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', paths[SHAPE_ICON[shape] || 'circle']); p.setAttribute('fill', color);
  svg.appendChild(p);
  return svg;
}

export function viewGraph(v, r) {
  const center = r.path[1];
  if (!center) {
    v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Graph' }), el('span', { class: 'sub', text: 'Pick a record to see what it connects to.' })));
    const body = el('div', { class: 'page-body', style: 'max-width:720px' });
    v.appendChild(body);
    body.appendChild(combobox({ testid: 'graph-start', placeholder: 'Start from any record…', source: nodeSource(), onChange: (n) => { if (n) location.hash = '#/graph/' + n.id + '?depth=2'; } }));
    const starts = el('div', { 'data-testid': 'graph-starts', style: 'margin-top:24px' });
    body.appendChild(starts);
    api('GET', '/nodes' + qs({ type: 'program,course', sort: 'name', limit: 20 })).then((p) => {
      if (!p.items.length) { starts.appendChild(empty('Nothing to show yet', 'Create a program or course and it appears here.', null, 'network')); return; }
      add(starts, [el('h3', { text: 'Programs and courses', style: 'margin-bottom:8px' }),
        el('div', { class: 'row', style: 'flex-wrap:wrap;gap:8px' }, p.items.map((n) => el('a', { class: 'btn', href: '#/graph/' + n.id + '?depth=2', 'data-testid': 'graph-start-chip' }, typeIcon(n.type), n.name)))]);
    }).catch(() => {});
    return;
  }
  if (typeof window.cytoscape !== 'function') { v.appendChild(errorBox({ message: 'The graph library did not load. Reload the page.' })); return; }
  const depth = r.q.depth === '2' ? 2 : 1;
  const hidden = {};
  let connectFrom = null;
  const info = el('span', { class: 'sub', 'data-testid': 'graph-info' });
  const depthSel = el('select', { 'aria-label': 'Depth', 'data-testid': 'graph-depth' }, el('option', { value: '1', text: '1 step', selected: depth === 1 }), el('option', { value: '2', text: '2 steps', selected: depth === 2 }));
  depthSel.addEventListener('change', () => setQuery({ depth: depthSel.value }));
  const connectBtn = can('contributor') ? el('button', { class: 'btn', type: 'button', 'data-testid': 'graph-connect', onclick: () => {
    connectFrom = connectFrom === null ? false : null; connectBtn.classList.toggle('primary', connectFrom === false);
    info.textContent = connectFrom === false ? 'Connect mode: click the first record, then the second.' : status(); } }, icon('git-branch', 'sm'), 'Connect') : null;
  v.appendChild(el('div', { class: 'page-head' }, el('a', { class: 'btn ghost sm', href: '#/graph' }, icon('arrow-left', 'sm'), 'Change start'), el('h1', { text: 'Graph' }), info, el('span', { class: 'spacer' }), depthSel, connectBtn));
  const side = el('aside', { class: 'graph-side', 'aria-label': 'Legend and filters', 'data-testid': 'graph-legend' });
  const canvas = el('div', { class: 'graph-canvas' }, el('div', { id: 'cy', 'data-testid': 'graph-canvas', role: 'img', 'aria-label': 'Relationship graph' }));
  const tools = el('div', { class: 'graph-tools' },
    el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-fit', title: 'Fit to view', onclick: () => cy.fit(undefined, 40) }, icon('maximize-2', 'sm'), 'Fit'),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom in', 'aria-label': 'Zoom in', onclick: () => cy.zoom({ level: cy.zoom() * 1.25, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }, icon('plus', 'sm')),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom out', 'aria-label': 'Zoom out', onclick: () => cy.zoom({ level: cy.zoom() / 1.25, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }, icon('minimize-2', 'sm')));
  const mini = el('canvas', { class: 'minimap', width: '360', height: '240', 'aria-label': 'Minimap — click to move the view', 'data-testid': 'minimap' });
  canvas.append(tools, mini);
  v.appendChild(el('div', { class: 'graph-wrap' }, side, canvas));
  const css = getComputedStyle(document.documentElement);
  const cy = window.cytoscape({ container: document.getElementById('cy'), wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 3,
    style: [
      { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', 'font-size': 11, 'font-family': 'Inter, system-ui, sans-serif', color: css.getPropertyValue('--text').trim() || '#18181b',
        'text-valign': 'bottom', 'text-margin-y': 5, width: 'mapData(degree, 0, 30, 18, 44)', height: 'mapData(degree, 0, 30, 18, 44)', shape: 'data(shape)', 'text-max-width': 130, 'text-wrap': 'ellipsis',
        'text-background-color': css.getPropertyValue('--bg').trim() || '#fff', 'text-background-opacity': 0.8, 'text-background-padding': 2 } },
      { selector: 'node.center', style: { 'border-width': 3, 'border-color': css.getPropertyValue('--text').trim() || '#111' } },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': css.getPropertyValue('--accent').trim() || '#1d4ed8' } },
      { selector: 'node.connect-src', style: { 'border-width': 4, 'border-color': css.getPropertyValue('--warn').trim() || '#a16207' } },
      { selector: 'edge', style: { width: 1.2, 'line-color': css.getPropertyValue('--border-strong').trim() || '#ccc', 'target-arrow-color': css.getPropertyValue('--border-strong').trim() || '#ccc',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.7, label: 'data(label)', 'font-size': 9, color: css.getPropertyValue('--text-3').trim() || '#777', 'text-rotation': 'autorotate', 'text-opacity': 0 } },
      { selector: 'edge.hover, edge:selected', style: { 'text-opacity': 1, 'line-color': css.getPropertyValue('--accent').trim(), 'target-arrow-color': css.getPropertyValue('--accent').trim() } },
      { selector: '.hidden', style: { display: 'none' } },
    ] });
  let expanded = {}, addedBy = {}; const totals = {};
  function status() {
    const shown = cy.nodes().filter((n) => !n.hasClass('hidden')).length, t = totals[center];
    return 'Showing ' + shown + ' record(s)' + (t && t.truncated ? ' (' + t.shown + ' of ' + t.total + ' nearby)' : '') + ' · double-click to expand';
  }
  function drawLegend() {
    clear(side);
    side.appendChild(el('h3', { text: 'Record types' }));
    const present = {}; cy.nodes().forEach((n) => { present[n.data('type')] = (present[n.data('type')] || 0) + 1; });
    S.types.forEach((t) => {
      if (!present[t.key] && !hidden[t.key]) return;
      const cb = el('input', { type: 'checkbox', checked: !hidden[t.key], 'data-testid': 'graph-filter-' + t.key, 'aria-label': 'Show ' + t.plural });
      cb.addEventListener('change', () => { hidden[t.key] = !cb.checked; applyFilter(); });
      side.appendChild(el('label', { class: 'legend-item' }, cb, legendShape(SHAPES[t.key] || 'ellipse', t.color), el('span', { class: 'truncate', style: 'flex:1', text: t.plural }), el('span', { class: 'count', text: present[t.key] || 0 })));
    });
    side.appendChild(el('h3', { text: 'Relationships', style: 'margin-top:8px' }));
    const labels = {}; cy.edges().forEach((e) => { labels[e.data('label')] = (labels[e.data('label')] || 0) + 1; });
    Object.keys(labels).sort().forEach((l) => side.appendChild(el('div', { class: 'legend-item small' }, el('span', { class: 'faint', text: '→' }), el('span', { style: 'flex:1', text: l }), el('span', { class: 'count', text: labels[l] }))));
    side.appendChild(el('p', { class: 'faint xs', style: 'margin-top:8px', text: 'Click a record to open it. Double-click to expand or collapse its neighbours.' }));
  }
  async function load(id, d, isRoot) {
    try {
      const nb = await api('GET', '/nodes/' + id + '/neighbourhood' + qs({ depth: d }));
      totals[id] = { truncated: nb.truncated, total: nb.total, shown: nb.nodes.length };
      const batch = [];
      nb.nodes.forEach((n) => { if (cy.getElementById(n.id).length) return; addedBy[n.id] = id;
        batch.push({ group: 'nodes', data: { id: n.id, label: n.name, type: n.type, color: (S.typeByKey[n.type] || {}).color || n.color, degree: n.degree, shape: SHAPES[n.type] || 'ellipse' } }); });
      nb.edges.forEach((e) => { if (!cy.getElementById(e.id).length) batch.push({ group: 'edges', data: { id: e.id, source: e.source_id, target: e.target_id, label: e.label } }); });
      cy.add(batch); expanded[id] = true;
      if (isRoot) cy.getElementById(center).addClass('center');
      applyFilter();
      cy.layout({ name: batch.length > 150 ? 'concentric' : 'cose', animate: false, fit: isRoot, padding: 48, idealEdgeLength: () => 95, nodeRepulsion: () => 65000, componentSpacing: 80,
        concentric: (n) => (n.id() === center ? 10 : 10 - (n.data('degree') > 5 ? 1 : 2)) }).run();
      if (isRoot && cy.zoom() > 1.6) { cy.zoom(1.6); cy.center(); }
      drawLegend(); info.textContent = status(); drawMini();
      if (nb.truncated) toast('Showing ' + nb.nodes.length + ' of ' + nb.total + ' records around this one.');
    } catch (e) { if (isRoot) canvas.appendChild(errorBox(e, () => load(id, d, isRoot))); else failToast(e, 'Could not expand'); }
  }
  function collapse(id) {
    Object.keys(addedBy).filter((k) => addedBy[k] === id && k !== center && !expanded[k]).forEach((k) => { cy.getElementById(k).remove(); delete addedBy[k]; });
    expanded[id] = false; info.textContent = status(); drawLegend(); drawMini();
  }
  function applyFilter() { cy.nodes().forEach((n) => n.toggleClass('hidden', !!hidden[n.data('type')] && n.id() !== center)); info.textContent = status(); drawMini(); }
  // minimap: every visible node as a dot, the viewport as a rectangle; click to centre there
  function drawMini() {
    const ctx = mini.getContext('2d'); const W = mini.width, H = mini.height;
    ctx.clearRect(0, 0, W, H);
    const nodes = cy.nodes().filter((n) => !n.hasClass('hidden'));
    if (!nodes.length) return;
    const bb = nodes.boundingBox(); const pad = 20;
    const sc = Math.min((W - 2 * pad) / Math.max(bb.w, 1), (H - 2 * pad) / Math.max(bb.h, 1));
    const tx = (x) => pad + (x - bb.x1) * sc, ty = (y) => pad + (y - bb.y1) * sc;
    mini._map = { bb, sc, pad };
    ctx.strokeStyle = css.getPropertyValue('--border-strong').trim(); ctx.lineWidth = 1;
    cy.edges().forEach((e) => { if (e.source().hasClass('hidden') || e.target().hasClass('hidden')) return; ctx.beginPath(); ctx.moveTo(tx(e.source().position('x')), ty(e.source().position('y'))); ctx.lineTo(tx(e.target().position('x')), ty(e.target().position('y'))); ctx.stroke(); });
    nodes.forEach((n) => { ctx.fillStyle = n.data('color'); ctx.beginPath(); ctx.arc(tx(n.position('x')), ty(n.position('y')), 4, 0, 6.3); ctx.fill(); });
    const ext = cy.extent();
    ctx.strokeStyle = css.getPropertyValue('--accent').trim(); ctx.lineWidth = 2;
    ctx.strokeRect(tx(ext.x1), ty(ext.y1), ext.w * sc, ext.h * sc);
  }
  mini.addEventListener('click', (e) => {
    const m = mini._map; if (!m) return;
    const rect = mini.getBoundingClientRect();
    const x = ((e.clientX - rect.left) * (mini.width / rect.width) - m.pad) / m.sc + m.bb.x1, y = ((e.clientY - rect.top) * (mini.height / rect.height) - m.pad) / m.sc + m.bb.y1;
    cy.pan({ x: cy.width() / 2 - x * cy.zoom(), y: cy.height() / 2 - y * cy.zoom() });
  });
  cy.on('viewport', () => requestAnimationFrame(drawMini));
  cy.on('tap', 'node', (evt) => {
    const n = evt.target;
    if (connectFrom === false) { connectFrom = n; n.addClass('connect-src'); info.textContent = 'Now click the record to connect it to.'; return; }
    if (connectFrom) {
      const src = connectFrom; connectFrom = null; src.removeClass('connect-src'); if (connectBtn) connectBtn.classList.remove('primary');
      if (src.id() === n.id()) { info.textContent = 'Pick a different record.'; return; }
      connectPair({ id: src.id(), name: src.data('label'), type: src.data('type') }, { id: n.id(), name: n.data('label'), type: n.data('type') });
      return;
    }
    setQuery({ open: n.id() }, true);
  });
  cy.on('mouseover', 'edge', (e) => e.target.addClass('hover'));
  cy.on('mouseout', 'edge', (e) => e.target.removeClass('hover'));
  cy.on('dbltap', 'node', (evt) => { const id = evt.target.id(); if (expanded[id] && id !== center) collapse(id); else if (!expanded[id]) load(id, 1); });
  function connectPair(a, b) {
    const opts = [];
    S.edgeTypes.forEach((et) => (et.rules || []).forEach((r) => {
      if (r.source === a.type && r.target === b.type) opts.push({ type: et.key, src: a, tgt: b, label: '“' + a.name + '” ' + et.label + ' “' + b.name + '”' });
      if (r.source === b.type && r.target === a.type) opts.push({ type: et.key, src: b, tgt: a, label: '“' + b.name + '” ' + et.label + ' “' + a.name + '”' });
    }));
    if (!opts.length) { toast('No relationship type connects a ' + typeLabel(a.type).toLowerCase() + ' and a ' + typeLabel(b.type).toLowerCase() + '. An admin can add one in Settings → Types.', { error: true }); return; }
    const sel = el('select', { 'aria-label': 'Relationship', 'data-testid': 'connect-type' }, opts.map((o, i) => el('option', { value: String(i), text: o.label })));
    openDialog([el('h2', { text: 'Connect two records' }), sel, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'connect-submit', text: 'Connect', onclick: async () => {
        const o = opts[Number(sel.value)];
        try { const e = await api('POST', '/edges', { type: o.type, source_id: o.src.id, target_id: o.tgt.id }); closeDialog(); toast('Connected');
          cy.add({ group: 'edges', data: { id: e.id, source: o.src.id, target: o.tgt.id, label: (S.edgeTypes.find((x) => x.key === o.type) || {}).label } }); drawLegend(); drawMini(); }
        catch (er) { failToast(er, 'Not connected'); } } }))], { label: 'Connect' });
  }
  S.graph = { cy, reload: () => { cy.elements().remove(); expanded = {}; addedBy = {}; load(center, depth, true); }, expand: (id) => load(id, 1) };
  window.__kbGraph = S.graph;   // for tests; holds no data of its own
  load(center, depth, true);
}
