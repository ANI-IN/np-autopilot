/* Graph: a neighbourhood around one record (never the whole graph), and a full
   editing surface (run 3, B3) on the same service layer, permissions,
   validation and audit as the forms:
     create   double-click empty canvas, or N → quick create (type + name; More… = full form)
     connect  drag a node's handle onto another node → relationship picker
              (allowed types + "Create relationship…"); an invalid pair says why
     edit     click → the detail panel; double-click a node → rename in place;
              click a relationship → its sentence, note and Remove
     delete   select (click, shift-click, shift-drag box) → Delete → archive with
              the impact shown, Undo in the toast
     move     drag; positions are saved per layout (the shared one or a saved
              graph view) and never change records; Auto-layout, Reset
     navigate zoom, pan, fit (F), minimap, search (/), filters (type, relationship,
              owner, course/program), expand/collapse, legend; arrows move the
              selection, Esc clears it
     sync     other people's changes arrive live; presence rings show who is
              editing; a stale rename gets the same conflict dialog as forms.
   Rendering is Cytoscape's canvas renderer; above GL_FROM nodes it switches
   to Cytoscape's WebGL renderer (docs/TEST_RESULTS.md has the measurements). */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, toast, failToast, qs, setQuery, empty, errorBox, combobox, nodeSource,
  openDialog, closeDialog, confirmDialog, can, popover, closeMenu, debounce, plural, personName, peopleSource } from '../core.js';
import { pageHead } from '../page.js';
import { relItems, relCombobox, createRelationshipType } from '../relpicker.js';
import { openRecordForm } from '../form.js';
import { onLiveChange } from '../live.js';
import { onPresence, others } from '../realtime.js';

const SHAPES = { program: 'round-hexagon', course: 'round-rectangle', domain: 'round-pentagon', module: 'ellipse', week: 'round-tag',
  session: 'barrel', topic: 'ellipse', instructor: 'round-diamond', process: 'round-triangle' };
const SHAPE_ICON = { 'round-hexagon': 'hexagon', 'round-rectangle': 'rect', 'round-pentagon': 'penta', ellipse: 'circle', 'round-tag': 'tag', barrel: 'barrel', 'round-diamond': 'diamond', 'round-triangle': 'tri' };
const GL_FROM = 1500;          // switch to the WebGL renderer above this many nodes
const LABELS_FROM_ZOOM = 0.45; // labels hidden below this zoom (simplified drawing)

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

function startPage(v) {
  v.appendChild(pageHead({ title: 'Graph', sub: 'Pick a record to see, arrange and edit what it connects to.' }));
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
  api('GET', '/views').then((x) => {
    const g = x.items.filter((w) => w.config && w.config.kind === 'graph');
    if (g.length) add(starts, [el('h3', { text: 'Saved graph views', style: 'margin:16px 0 8px' }),
      el('div', { class: 'row', style: 'flex-wrap:wrap;gap:8px' }, g.map((w) => el('a', { class: 'btn', href: '#/graph/' + w.config.center + qs({ depth: w.config.depth || 1, view: w.id }) }, icon('network', 'sm'), w.name)))]);
  }).catch(() => {});
}

/* The graph library (~430 KB) loads only when a graph is opened (Phase C). */
let libLoading = null;
function loadLib() {
  if (typeof window.cytoscape === 'function') return Promise.resolve();
  libLoading = libLoading || new Promise((res, rej) => { const sc = document.createElement('script'); sc.src = '/vendor/cytoscape.min.js'; sc.onload = res; sc.onerror = rej; document.head.appendChild(sc); });
  return libLoading;
}

export function viewGraph(v, r) {
  const center = r.path[1];
  if (!center) { startPage(v); return; }
  if (typeof window.cytoscape !== 'function') {
    loadLib().then(() => { if (S.route && S.route.path[0] === 'graph' && S.route.path[1] === center) { clear(v); viewGraph(v, r); } })
      .catch(() => v.appendChild(errorBox({ message: 'The graph library did not load. Reload the page.' })));
    return;
  }
  const depth = r.q.depth === '2' ? 2 : 1;
  const layoutId = r.q.view || 'default';
  const canEdit = can('contributor');
  const hidden = {}, edgeHidden = {};
  let ownerFilter = null, scopeFilter = null, connectFrom = null, view = null;
  const G = {};                                   // this view's handle; listeners check S.graph === G

  // ---------------------------------------------------------------- header + layout
  const info = el('span', { class: 'sub', 'data-testid': 'graph-info' });
  const depthSel = el('select', { 'aria-label': 'Depth', 'data-testid': 'graph-depth' }, el('option', { value: '1', text: '1 step', selected: depth === 1 }), el('option', { value: '2', text: '2 steps', selected: depth === 2 }));
  depthSel.addEventListener('change', () => setQuery({ depth: depthSel.value }));
  const layoutSel = el('select', { 'aria-label': 'Layout', 'data-testid': 'graph-layout' }, el('option', { value: 'default', text: 'Shared layout' }));
  layoutSel.addEventListener('change', () => { const w = (G.views || []).find((x) => x.id === layoutSel.value);
    location.hash = '#/graph/' + (w ? w.config.center : center) + qs({ depth: w ? w.config.depth || 1 : depth, view: w ? w.id : null }); });
  const connectBtn = canEdit ? el('button', { class: 'btn', type: 'button', 'data-testid': 'graph-connect', title: 'Or drag from a record’s handle',
    onclick: () => { connectFrom = connectFrom === null ? false : null; connectBtn.classList.toggle('primary', connectFrom === false);
      info.textContent = connectFrom === false ? 'Connect: click the first record, then the second.' : status(); } }, icon('git-branch', 'sm'), 'Connect') : null;
  const head = pageHead({ title: 'Graph', actions: [el('a', { class: 'btn ghost', href: '#/graph' }, icon('arrow-left', 'sm'), 'Change start'), layoutSel, depthSel,
    canEdit ? el('button', { class: 'btn', type: 'button', 'data-testid': 'graph-save-view', onclick: saveViewDialog }, 'Save view') : null, connectBtn,
    canEdit ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'graph-new', title: 'New record here (N)', onclick: () => quickCreate(null) }, icon('plus'), 'New') : null] });
  head.querySelector('.page-title').after(info);
  v.appendChild(head);

  const side = el('aside', { class: 'graph-side', 'aria-label': 'Legend and filters', 'data-testid': 'graph-legend' });
  const cyBox = el('div', { id: 'cy', 'data-testid': 'graph-canvas', role: 'application', tabindex: '0',
    'aria-label': 'Relationship graph. N new record, F fit, slash search, Delete archive the selection, arrows move it, Escape clears it.' });
  const canvas = el('div', { class: 'graph-canvas' }, cyBox);
  const search = el('input', { type: 'search', placeholder: 'Find in graph  /', 'aria-label': 'Find a record in the graph', 'data-testid': 'graph-search' });
  const tools = el('div', { class: 'graph-tools' },
    el('div', { class: 'input-icon', style: 'width:220px' }, icon('search'), search),
    el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-fit', title: 'Fit to view (F)', onclick: () => fit() }, icon('maximize-2', 'sm'), 'Fit'),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom in', 'aria-label': 'Zoom in', onclick: () => zoomBy(1.25) }, icon('zoom-in', 'sm')),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom out', 'aria-label': 'Zoom out', onclick: () => zoomBy(0.8) }, icon('zoom-out', 'sm')),
    canEdit ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-autolayout', title: 'Arrange everything automatically and save it to this layout', onclick: () => autoLayout(true) }, icon('layout-grid', 'sm'), 'Auto-layout') : null,
    canEdit ? el('button', { class: 'btn sm ghost', type: 'button', 'data-testid': 'graph-reset', title: 'Forget the saved positions of this layout', onclick: resetLayout }, icon('rotate-ccw', 'sm'), 'Reset') : null);
  const mini = el('canvas', { class: 'minimap', width: '360', height: '240', 'aria-label': 'Minimap — click to move the view', 'data-testid': 'minimap' });
  const handles = el('div', { class: 'graph-handles', hidden: true, 'data-testid': 'graph-handles' });
  canvas.append(tools, mini, handles);
  v.appendChild(el('div', { class: 'graph-wrap' }, side, canvas));

  const css = getComputedStyle(document.documentElement);
  const tok = (k, d) => css.getPropertyValue(k).trim() || d;
  // Renderer: canvas by default; WebGL for very large neighbourhoods (or ?renderer=webgl|canvas to compare).
  const useGL = r.q.renderer === 'webgl' || (r.q.renderer !== 'canvas' && r.q.limit && Number(r.q.limit) > GL_FROM);
  const cy = window.cytoscape({ container: cyBox, wheelSensitivity: 0.25, minZoom: 0.05, maxZoom: 3, boxSelectionEnabled: true, selectionType: 'additive',
    renderer: useGL ? { name: 'canvas', webgl: true } : undefined,
    hideEdgesOnViewport: false, textureOnViewport: false,
    style: [
      { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', 'font-size': 11, 'font-family': 'Inter, system-ui, sans-serif', color: tok('--text', '#18181b'),
        'text-valign': 'bottom', 'text-margin-y': 5, width: 'mapData(degree, 0, 30, 18, 44)', height: 'mapData(degree, 0, 30, 18, 44)', shape: 'data(shape)', 'text-max-width': 130, 'text-wrap': 'ellipsis',
        'text-background-color': tok('--bg', '#fff'), 'text-background-opacity': 0.8, 'text-background-padding': 2, 'min-zoomed-font-size': 11 * LABELS_FROM_ZOOM } },
      { selector: 'node.center', style: { 'border-width': 3, 'border-color': tok('--text', '#111') } },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': tok('--accent', '#1d4ed8'), 'underlay-color': tok('--accent', '#1d4ed8'), 'underlay-opacity': 0.12, 'underlay-padding': 6 } },
      { selector: 'node.connect-src', style: { 'border-width': 4, 'border-color': tok('--warn', '#a16207') } },
      { selector: 'node.found', style: { 'underlay-color': tok('--warn', '#a16207'), 'underlay-opacity': 0.35, 'underlay-padding': 10 } },
      { selector: 'node.presence', style: { 'border-width': 3, 'border-style': 'dashed', 'border-color': tok('--ok', '#15803d') } },
      { selector: 'node.ghost', style: { width: 1, height: 1, opacity: 0, label: '' } },
      { selector: 'edge', style: { width: 1.2, 'line-color': tok('--border-strong', '#ccc'), 'target-arrow-color': tok('--border-strong', '#ccc'),
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.7, label: 'data(label)', 'font-size': 9, color: tok('--text-3', '#777'), 'text-rotation': 'autorotate', 'text-opacity': 0,
        'min-zoomed-font-size': 9 * LABELS_FROM_ZOOM } },
      { selector: 'edge.hover, edge:selected', style: { 'text-opacity': 1, width: 2, 'line-color': tok('--accent', '#1d4ed8'), 'target-arrow-color': tok('--accent', '#1d4ed8') } },
      { selector: 'edge.ghost', style: { 'line-style': 'dashed', 'line-color': tok('--accent', '#1d4ed8'), 'target-arrow-color': tok('--accent', '#1d4ed8'), width: 2, label: '' } },
      { selector: '.hidden', style: { display: 'none' } },
    ] });
  let expanded = {}, addedBy = {}; const totals = {};
  Object.assign(G, { cy, center, layoutId, webgl: !!(useGL && cy.renderer() && cy.renderer().webgl) });
  S.graph = G;
  window.__kbGraph = G;                 // for tests; holds no data of its own

  // ---------------------------------------------------------------- helpers
  const visibleNodes = () => cy.nodes().filter((n) => !n.hasClass('hidden') && !n.hasClass('ghost'));
  function status() {
    const shown = visibleNodes().length, t = totals[center];
    return 'Showing ' + shown + ' record(s)' + (t && t.truncated ? ' (' + t.shown + ' of ' + t.total + ' nearby)' : '');
  }
  function fit() { const vis = visibleNodes(); cy.fit(vis.length ? vis : undefined, 40); if (cy.zoom() > 1.6) { cy.zoom(1.6); cy.center(vis); } }
  function zoomBy(f) { cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); }
  const nodeData = (n) => ({ id: n.id, label: n.name, type: n.type, color: (S.typeByKey[n.type] || {}).color || n.color, degree: n.degree || 0,
    shape: SHAPES[n.type] || 'ellipse', owner: n.owner_id || null, scope: n.scope_id || null, version: n.version });
  const edgeData = (e) => ({ id: e.id, source: e.source_id, target: e.target_id, label: e.label, type: e.type, note: e.note || '', version: e.version });
  function toRendered(pos) { const pan = cy.pan(), z = cy.zoom(); return { x: pos.x * z + pan.x, y: pos.y * z + pan.y }; }
  function toModel(rp) { const pan = cy.pan(), z = cy.zoom(); return { x: (rp.x - pan.x) / z, y: (rp.y - pan.y) / z }; }
  function nodeAt(rp) {
    let hit = null;
    visibleNodes().forEach((n) => { const b = n.renderedBoundingBox({ includeLabels: false }); if (rp.x >= b.x1 - 4 && rp.x <= b.x2 + 4 && rp.y >= b.y1 - 4 && rp.y <= b.y2 + 4) hit = n; });
    return hit;
  }
  function anchorAt(rp) {      // an invisible element to anchor a popover at a canvas point
    const a = el('span', { class: 'graph-anchor', style: 'left:' + rp.x + 'px;top:' + rp.y + 'px' });
    canvas.appendChild(a); setTimeout(() => a.remove(), 30000);
    return a;
  }
  const ref = (n) => ({ id: n.id(), name: n.data('label'), type: n.data('type') });

  // ---------------------------------------------------------------- legend + filters
  function drawLegend() {
    clear(side);
    side.appendChild(el('h3', { text: 'Record types' }));
    const present = {}; cy.nodes(':not(.ghost)').forEach((n) => { present[n.data('type')] = (present[n.data('type')] || 0) + 1; });
    S.types.forEach((t) => {
      if (!present[t.key] && !hidden[t.key]) return;
      const cb = el('input', { type: 'checkbox', checked: !hidden[t.key], 'data-testid': 'graph-filter-' + t.key, 'aria-label': 'Show ' + t.plural });
      cb.addEventListener('change', () => { hidden[t.key] = !cb.checked; applyFilter(); });
      side.appendChild(el('label', { class: 'legend-item' }, cb, legendShape(SHAPES[t.key] || 'ellipse', t.color), el('span', { class: 'truncate', style: 'flex:1', text: t.plural }), el('span', { class: 'count', text: present[t.key] || 0 })));
    });
    side.appendChild(el('h3', { text: 'Relationships', style: 'margin-top:8px' }));
    const types = {}; cy.edges(':not(.ghost)').forEach((e) => { const k = e.data('type'); types[k] = types[k] || { label: e.data('label'), n: 0 }; types[k].n++; });
    Object.keys(types).sort().forEach((k) => {
      const cb = el('input', { type: 'checkbox', checked: !edgeHidden[k], 'data-testid': 'graph-edge-filter-' + k, 'aria-label': 'Show ' + types[k].label });
      cb.addEventListener('change', () => { edgeHidden[k] = !cb.checked; applyFilter(); });
      side.appendChild(el('label', { class: 'legend-item small' }, cb, el('span', { class: 'legend-line', 'aria-hidden': 'true' }), el('span', { class: 'truncate', style: 'flex:1', text: types[k].label }), el('span', { class: 'count', text: types[k].n })));
    });
    side.appendChild(el('h3', { text: 'Filter', style: 'margin-top:8px' }));
    const owners = {}; cy.nodes(':not(.ghost)').forEach((n) => { if (n.data('owner')) owners[n.data('owner')] = 1; });
    const ownerSel = el('select', { 'aria-label': 'Owner', 'data-testid': 'graph-owner-filter' }, el('option', { value: '', text: 'Any owner' }), el('option', { value: 'none', text: 'No owner', selected: ownerFilter === 'none' }),
      Object.keys(owners).map((id) => el('option', { value: id, text: personName(id) || id.slice(0, 8), selected: ownerFilter === id })));
    ownerSel.addEventListener('change', () => { ownerFilter = ownerSel.value || null; applyFilter(); });
    side.appendChild(el('label', { class: 'field' }, el('span', { class: 'faint xs', text: 'Owner' }), ownerSel));
    side.appendChild(el('div', { class: 'field' }, el('span', { class: 'faint xs', text: 'Inside a course or program' }),
      combobox({ testid: 'graph-scope-filter', placeholder: 'Any', value: scopeFilter ? [scopeFilter.item] : [], source: nodeSource(['program', 'course']), onChange: async (it) => {
        if (!it) { scopeFilter = null; applyFilter(); return; }
        try { const p = await api('GET', '/nodes' + qs({ parent: it.id, limit: 1000 })); scopeFilter = { item: it, ids: new Set([it.id].concat(p.items.map((x) => x.id))) }; applyFilter(); }
        catch (e) { failToast(e); }
      } })));
    side.appendChild(el('p', { class: 'faint xs', style: 'margin-top:8px', text: canEdit
      ? 'Double-click empty space to add a record. Drag from a record’s handle to connect. Double-click a record to rename it. Shift-drag to select several; Delete archives them.'
      : 'Click a record to open it. Use its + button to expand or collapse neighbours.' }));
  }
  function applyFilter() {
    cy.batch(() => {
      cy.nodes(':not(.ghost)').forEach((n) => {
        const id = n.id(), own = n.data('owner');
        const hide = id !== center && (!!hidden[n.data('type')] || (ownerFilter === 'none' ? !!own : ownerFilter ? own !== ownerFilter : false) || (scopeFilter ? !scopeFilter.ids.has(id) : false));
        n.toggleClass('hidden', hide);
      });
      cy.edges(':not(.ghost)').forEach((e) => e.toggleClass('hidden', !!edgeHidden[e.data('type')]));
    });
    info.textContent = status(); drawMini();
  }

  // ---------------------------------------------------------------- loading, positions
  async function savedPositions(ids) {
    try {
      const p = await api('GET', '/graph/positions' + qs({ layout: layoutId, ids: ids.length <= 200 ? ids.join(',') : null }));
      const m = {}; p.items.forEach((x) => { m[x.node_id] = { x: x.x, y: x.y }; }); return m;
    } catch (e) { return {}; }
  }
  async function load(id, d, isRoot) {
    try {
      const nb = await api('GET', '/nodes/' + id + '/neighbourhood' + qs({ depth: d, limit: r.q.limit || null }));
      totals[id] = { truncated: nb.truncated, total: nb.total, shown: nb.nodes.length };
      const fresh = nb.nodes.filter((n) => !cy.getElementById(n.id).length);
      const pos = await savedPositions(fresh.map((n) => n.id));
      const near = isRoot ? null : cy.getElementById(id).position();
      const batch = [];
      fresh.forEach((n) => { addedBy[n.id] = id;
        batch.push({ group: 'nodes', data: nodeData(n), position: pos[n.id] || (near ? { x: near.x + (Math.random() - 0.5) * 160, y: near.y + (Math.random() - 0.5) * 160 } : undefined), classes: pos[n.id] ? 'placed' : '' }); });
      nb.nodes.forEach((n) => { const c = cy.getElementById(n.id); if (c.length) c.data(nodeData(n)); });
      nb.edges.forEach((e) => { if (!cy.getElementById(e.id).length) batch.push({ group: 'edges', data: edgeData(e) }); });
      cy.add(batch); expanded[id] = true;
      if (isRoot) cy.getElementById(center).addClass('center');
      applyFilter();
      const unplaced = cy.nodes(':not(.placed):not(.ghost)').filter((n) => fresh.some((f) => f.id === n.id()));
      if (unplaced.length) {
        const placed = cy.nodes('.placed'); placed.lock();
        const n = cy.nodes().length;
        cy.layout({ name: n > 300 ? 'concentric' : 'cose', animate: false, fit: false, padding: 48, idealEdgeLength: () => 120, nodeRepulsion: () => 140000, componentSpacing: 100, nodeOverlap: 20,
          concentric: (x) => (x.id() === center ? 10 : 10 - (x.data('degree') > 5 ? 1 : 2)), minNodeSpacing: n > 1000 ? 4 : 20, spacingFactor: n > 1000 ? 0.6 : 1 }).run();
        placed.unlock();
        cy.nodes(':not(.ghost)').addClass('placed');
      }
      if (isRoot) fit();
      drawLegend(); info.textContent = status(); drawMini();
      if (nb.truncated) toast('Showing ' + nb.nodes.length + ' of ' + nb.total + ' records around this one.');
      G.loadedAt = performance.now();
    } catch (e) { if (isRoot) canvas.appendChild(errorBox(e, () => load(id, d, isRoot))); else failToast(e, 'Could not expand'); }
  }
  function collapse(id) {
    Object.keys(addedBy).filter((k) => addedBy[k] === id && k !== center && !expanded[k]).forEach((k) => { cy.getElementById(k).remove(); delete addedBy[k]; });
    expanded[id] = false; info.textContent = status(); drawLegend(); drawMini();
  }
  const pendingSave = {};
  const flushPositions = debounce(async () => {
    const items = Object.entries(pendingSave).map(([node_id, p]) => ({ node_id, x: p.x, y: p.y }));
    Object.keys(pendingSave).forEach((k) => delete pendingSave[k]);
    if (!items.length || !canEdit) return;
    try { await api('POST', '/graph/positions', { layout: layoutId, positions: items }); G.savedPositions = (G.savedPositions || 0) + items.length; }
    catch (e) { failToast(e, 'Layout not saved'); }
  }, 400);
  function queueSave(nodes) { nodes.forEach((n) => { if (!n.hasClass('ghost')) pendingSave[n.id()] = Object.assign({}, n.position()); }); flushPositions(); }
  function autoLayout(save) {
    const n = visibleNodes().length;
    cy.layout({ name: n > 300 ? 'concentric' : 'cose', animate: false, fit: true, padding: 48, eles: cy.elements(':visible:not(.ghost)'), idealEdgeLength: () => 120, nodeRepulsion: () => 140000,
      concentric: (x) => (x.id() === center ? 10 : 10 - (x.data('degree') > 5 ? 1 : 2)), minNodeSpacing: n > 1000 ? 4 : 20 }).run();
    drawMini();
    if (save) { queueSave(visibleNodes()); toast('Arranged and saved to ' + (layoutId === 'default' ? 'the shared layout' : 'this view')); }
  }
  async function resetLayout() {
    const ok = await confirmDialog({ title: 'Reset this layout?', body: 'Forgets every saved position in ' + (layoutId === 'default' ? 'the shared layout' : 'this view') + ' and arranges the graph automatically. Records do not change.', confirmLabel: 'Reset', danger: false });
    if (!ok) return;
    try { await api('DELETE', '/graph/positions' + qs({ layout: layoutId })); autoLayout(false); toast('Layout reset'); } catch (e) { failToast(e, 'Not reset'); }
  }

  // ---------------------------------------------------------------- minimap
  function drawMini() {
    const ctx = mini.getContext('2d'); const W = mini.width, H = mini.height;
    ctx.clearRect(0, 0, W, H);
    const nodes = visibleNodes();
    if (!nodes.length) return;
    const bb = nodes.boundingBox(); const pad = 20;
    const sc = Math.min((W - 2 * pad) / Math.max(bb.w, 1), (H - 2 * pad) / Math.max(bb.h, 1));
    const tx = (x) => pad + (x - bb.x1) * sc, ty = (y) => pad + (y - bb.y1) * sc;
    mini._map = { bb, sc, pad };
    if (nodes.length < 1500) {
      ctx.strokeStyle = tok('--border-strong', '#ccc'); ctx.lineWidth = 1;
      cy.edges(':visible').forEach((e) => { ctx.beginPath(); ctx.moveTo(tx(e.source().position('x')), ty(e.source().position('y'))); ctx.lineTo(tx(e.target().position('x')), ty(e.target().position('y'))); ctx.stroke(); });
    }
    nodes.forEach((n) => { ctx.fillStyle = n.data('color'); ctx.fillRect(tx(n.position('x')) - 2, ty(n.position('y')) - 2, 4, 4); });
    const ext = cy.extent();
    ctx.strokeStyle = tok('--accent', '#1d4ed8'); ctx.lineWidth = 2;
    ctx.strokeRect(tx(ext.x1), ty(ext.y1), ext.w * sc, ext.h * sc);
  }
  mini.addEventListener('click', (e) => {
    const m = mini._map; if (!m) return;
    const rect = mini.getBoundingClientRect();
    const x = ((e.clientX - rect.left) * (mini.width / rect.width) - m.pad) / m.sc + m.bb.x1, y = ((e.clientY - rect.top) * (mini.height / rect.height) - m.pad) / m.sc + m.bb.y1;
    cy.pan({ x: cy.width() / 2 - x * cy.zoom(), y: cy.height() / 2 - y * cy.zoom() });
  });
  let miniQueued = false;
  cy.on('viewport', () => { if (!miniQueued) { miniQueued = true; requestAnimationFrame(() => { miniQueued = false; drawMini(); placeHandles(); }); } });

  // ---------------------------------------------------------------- handles (hover toolbar)
  let handleNode = null;
  const connectHandle = el('button', { class: 'graph-handle connect', type: 'button', 'data-testid': 'graph-handle', title: 'Drag onto another record to connect', 'aria-label': 'Connect from this record' }, icon('spline', 'sm'));
  const expandBtn = el('button', { class: 'graph-handle', type: 'button', 'data-testid': 'graph-expand', title: 'Expand or collapse neighbours (E)', 'aria-label': 'Expand or collapse neighbours' }, icon('plus', 'sm'));
  const renameBtn = el('button', { class: 'graph-handle', type: 'button', 'data-testid': 'graph-rename', title: 'Rename (double-click)', 'aria-label': 'Rename' }, icon('pencil', 'sm'));
  const presenceTag = el('span', { class: 'graph-presence', 'data-testid': 'graph-presence' });
  handles.append(canEdit ? connectHandle : null, expandBtn, canEdit ? renameBtn : null, presenceTag);
  function showHandles(n) { handleNode = n; handles.hidden = !n; placeHandles(); }
  function placeHandles() {
    if (!handleNode || !handleNode.inside() || handleNode.hasClass('hidden')) { handles.hidden = true; return; }
    const b = handleNode.renderedBoundingBox({ includeLabels: false });
    handles.style.left = (b.x2 + 6) + 'px'; handles.style.top = (b.y1 - 4) + 'px'; handles.hidden = false;
    expandBtn.replaceChildren(icon(expanded[handleNode.id()] && handleNode.id() !== center ? 'minus' : 'plus', 'sm'));
    const o = others(handleNode.id());
    presenceTag.textContent = o.length ? o.map((x) => personName(x.user_id) + (x.editing ? ' is editing' : ' is viewing')).join(', ') : '';
    presenceTag.hidden = !o.length;
  }
  cy.on('mouseover', 'node', (e) => { if (!dragging && !e.target.hasClass('ghost')) showHandles(e.target); });
  cy.on('select', 'node', (e) => showHandles(e.target));
  cy.on('position', 'node', (e) => { if (e.target === handleNode) placeHandles(); });
  cy.on('remove', 'node', (e) => { if (e.target === handleNode) showHandles(null); });
  expandBtn.addEventListener('click', () => { if (handleNode) toggleExpand(handleNode.id()); });
  renameBtn.addEventListener('click', () => { if (handleNode) rename(handleNode); });
  function toggleExpand(id) { if (expanded[id] && id !== center) collapse(id); else if (!expanded[id]) load(id, 1); }

  // ---------------------------------------------------------------- connect (drag a handle)
  let dragging = null;
  connectHandle.addEventListener('mousedown', (ev) => {
    if (!handleNode) return;
    ev.preventDefault(); ev.stopPropagation();
    const src = handleNode, rect = cyBox.getBoundingClientRect();
    const start = toModel({ x: ev.clientX - rect.left, y: ev.clientY - rect.top });
    cy.add([{ group: 'nodes', data: { id: '__ghost', color: 'transparent', shape: 'ellipse', label: '', type: '' }, classes: 'ghost', position: start },
      { group: 'edges', data: { id: '__ghost_edge', source: src.id(), target: '__ghost', label: '' }, classes: 'ghost' }]);
    dragging = src; handles.hidden = true;
    const move = (e) => { cy.getElementById('__ghost').position(toModel({ x: e.clientX - rect.left, y: e.clientY - rect.top })); };
    const up = (e) => {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      cy.remove('#__ghost, #__ghost_edge');
      const rp = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      const tgt = nodeAt(rp); dragging = null;
      if (!tgt || tgt.id() === src.id()) { if (tgt) toast('Drop on a different record to connect.'); return; }   // snaps back
      connectPair(ref(src), ref(tgt), rp);
    };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });

  /* Offer the relationships allowed between the two (either direction), and
     "Create relationship…". No allowed pair: say why and offer the create. */
  function connectPair(a, b, rp) {
    rp = rp || { x: cy.width() / 2, y: cy.height() / 2 };
    const anchor = anchorAt(rp);
    const options = relItems(a.type, b.type);
    const err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'graph-connect-error' });
    const createBtn = el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-create-rel', onclick: async () => {
      closeMenu();
      const made = await createRelationshipType({ name: '', sourceType: a.type, targetType: b.type });
      if (made) connectPair(a, b, rp);
    } }, icon('plus', 'sm'), 'Create relationship…');
    if (!options.length) {
      popover(anchor, [el('strong', { text: 'These two can’t be connected yet' }),
        el('p', { class: 'small', 'data-testid': 'graph-connect-reason', text: 'No relationship type allows ' + typeLabel(a.type).toLowerCase() + ' “' + a.name + '” and ' + typeLabel(b.type).toLowerCase() + ' “' + b.name + '” to be connected, in either direction.' }),
        el('div', { class: 'row' }, can('contributor') ? createBtn : null, el('button', { class: 'btn sm ghost', type: 'button', text: 'Cancel', onclick: closeMenu }))],
      { testid: 'graph-connect-popover', label: 'Connect two records' });
      return;
    }
    let chosen = null;
    const picker = relCombobox({ typeKey: () => a.type, otherType: () => b.type, testid: 'graph-rel', onChange: (it) => { chosen = it; sentence.textContent = it ? describe(it) : ''; } });
    const sentence = el('p', { class: 'small', 'data-testid': 'graph-rel-sentence' });
    const describe = (it) => { const et = S.edgeTypes.find((x) => x.key === it.type) || {}; return it.direction === 'out' ? '“' + a.name + '” ' + et.label + ' “' + b.name + '”' : '“' + b.name + '” ' + et.label + ' “' + a.name + '”'; };
    const submit = el('button', { class: 'btn primary sm', type: 'button', 'data-testid': 'connect-submit', text: 'Connect', onclick: async () => {
      if (!chosen) { err.textContent = 'Choose a relationship.'; return; }
      const [s, t] = chosen.direction === 'out' ? [a, b] : [b, a];
      try {
        const e = await api('POST', '/edges', { type: chosen.type, source_id: s.id, target_id: t.id });
        closeMenu(); toast('Connected', { action: { label: 'Undo', fn: () => removeEdges([e.id], true) } });
        cy.add({ group: 'edges', data: edgeData(Object.assign({ label: (S.edgeTypes.find((x) => x.key === chosen.type) || {}).label, type: chosen.type }, e)) });
        drawLegend(); drawMini();
      } catch (er) { if (er.status === 202) { closeMenu(); toast('Sent for approval'); } else err.textContent = er.message; }
    } });
    popover(anchor, [el('strong', { text: 'Connect “' + a.name + '” and “' + b.name + '”' }), picker, sentence, err,
      el('div', { class: 'row' }, can('contributor') ? createBtn : null, el('span', { class: 'spacer' }), el('button', { class: 'btn sm ghost', type: 'button', text: 'Cancel', onclick: closeMenu }), submit)],
    { testid: 'graph-connect-popover', label: 'Connect two records' });
    picker.focus();
  }

  // ---------------------------------------------------------------- create
  function quickCreate(model) {
    if (!canEdit) return;
    const mp = model || toModel({ x: cy.width() / 2, y: cy.height() / 2 });
    const rp = toRendered(mp);
    const types = S.types.filter((t) => !t.archived_at);
    const typeSel = el('select', { 'aria-label': 'Type', 'data-testid': 'graph-new-type' }, types.map((t) => el('option', { value: t.key, text: t.label, selected: t.key === (G.lastType || 'topic') })));
    const name = el('input', { 'aria-label': 'Name', placeholder: 'Name', 'data-testid': 'graph-new-name' });
    const err = el('div', { class: 'field-error', role: 'alert' });
    const go = async () => {
      if (!name.value.trim()) { err.textContent = 'Give it a name.'; name.focus(); return; }
      G.lastType = typeSel.value;
      try {
        const n = await api('POST', '/nodes', { type: typeSel.value, name: name.value.trim() });
        closeMenu();
        cy.add({ group: 'nodes', data: nodeData(Object.assign({ degree: 0 }, n)), position: mp, classes: 'placed' });
        addedBy[n.id] = center; queueSave(cy.getElementById(n.id));
        cy.$(':selected').unselect(); cy.getElementById(n.id).select();
        applyFilter(); drawLegend();
        toast('Created “' + n.name + '”', { action: { label: 'Undo', fn: () => archiveNodes([n.id], true) } });
      } catch (e) {
        if (e.status === 202) { closeMenu(); toast('Proposed “' + name.value.trim() + '”; an editor approves it in Approvals'); }
        else err.textContent = e.message;
      }
    };
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
    popover(anchorAt(rp), [el('strong', { text: 'New record here' }), typeSel, name, err,
      el('div', { class: 'row' }, el('button', { class: 'btn sm ghost', type: 'button', 'data-testid': 'graph-new-more', text: 'More…', onclick: () => { closeMenu(); openRecordForm({ type: typeSel.value, name: name.value.trim() }); } }),
        el('span', { class: 'spacer' }), el('button', { class: 'btn primary sm', type: 'button', 'data-testid': 'graph-new-create', text: 'Create', onclick: go }))],
    { testid: 'graph-new-popover', label: 'New record' });
    name.focus();
  }

  // ---------------------------------------------------------------- rename in place
  function rename(n) {
    if (!canEdit) return;
    const b = n.renderedBoundingBox({ includeLabels: true });
    const input = el('input', { class: 'graph-rename', value: n.data('label'), 'aria-label': 'Rename ' + n.data('label'), 'data-testid': 'graph-rename-input',
      style: 'left:' + Math.max(4, (b.x1 + b.x2) / 2 - 110) + 'px;top:' + (b.y2 - 16) + 'px' });
    canvas.appendChild(input); input.focus(); input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return; done = true; input.remove(); cyBox.focus();
      const nm = input.value.trim();
      if (!save || !nm || nm === n.data('label')) return;
      await saveName(n, nm, false);
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); finish(true); } if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); } });
    input.addEventListener('blur', () => finish(true));
  }
  async function saveName(n, nm, force) {
    const old = n.data('label');
    n.data('label', nm);
    try {
      const u = await api('PATCH', '/nodes/' + n.id() + (force ? '?force=1' : ''), { version: n.data('version'), name: nm });
      n.data('version', u.version); toast('Renamed', { action: { label: 'Undo', fn: () => saveName(n, old, false) } });
    } catch (e) {
      n.data('label', old);
      if (e.status === 409 && e.body.error === 'version_conflict') conflict(n, nm, e.body.current);
      else failToast(e, 'Not renamed');
    }
  }
  function conflict(n, mine, current) {
    const actions = el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', 'data-testid': 'conflict-reload', text: 'Use their version',
      onclick: () => { closeDialog(); n.data({ label: current.name, version: current.version }); } }));
    if (can('editor')) actions.appendChild(el('button', { class: 'btn danger solid', type: 'button', 'data-testid': 'conflict-overwrite', text: 'Overwrite with mine',
      onclick: () => { closeDialog(); n.data('version', current.version); saveName(n, mine, true); } }));
    openDialog([el('h2', { text: 'This record changed since you opened it' }),
      el('div', { 'data-testid': 'conflict-diff', style: 'display:grid;grid-template-columns:100px 1fr 1fr;gap:6px 12px;font-size:13px' },
        el('div', { class: 'faint', text: 'Field' }), el('div', { class: 'faint', text: 'Your change' }), el('div', { class: 'faint', text: 'Saved now (v' + current.version + ')' }),
        el('div', { class: 'faint', text: 'name' }), el('div', { class: 'diff-add', text: mine }), el('div', { text: current.name })), actions],
    { label: 'Edit conflict', testid: 'conflict-dialog' });
  }

  // ---------------------------------------------------------------- delete (archive) + undo
  async function archiveNodes(ids, quiet) {
    const done = [];
    for (const id of ids) {
      try { await api('POST', '/nodes/' + id + '/archive', {}); done.push(id); }
      catch (e) { if (e.status === 202) toast('Sent for approval: an editor archives it'); else failToast(e, 'Not archived'); }
    }
    G.pendingRestore = G.pendingRestore || new Map();
    done.forEach((id) => { const n = cy.getElementById(id); G.pendingRestore.set(id, Object.assign({}, n.position())); n.remove(); });
    applyFilter(); drawLegend();
    if (done.length && !quiet) toast('Archived ' + plural(done.length, 'record'), { action: { label: 'Undo', fn: () => restore('nodes', done) } });
    return done;
  }
  async function removeEdges(ids, quiet) {
    const done = [], data = ids.map((id) => cy.getElementById(id).data());
    for (const id of ids) {
      try { await api('POST', '/edges/' + id + '/archive', {}); done.push(id); }
      catch (e) { if (e.status === 202) toast('Sent for approval'); else failToast(e, 'Not removed'); }
    }
    done.forEach((id) => cy.getElementById(id).remove());
    drawLegend(); drawMini();
    if (done.length && !quiet) toast('Removed ' + plural(done.length, 'relationship'), { action: { label: 'Undo', fn: () => restore('edges', done, data) } });
  }
  async function restore(table, ids) {
    for (const id of ids) { try { await api('POST', '/' + table + '/' + id + '/restore'); } catch (e) { failToast(e, 'Not restored'); } }
    toast('Restored');
    // Archiving a record archived its relationships too: bring both back where they were.
    const rows = ids.map((id) => ({ table_name: table, row_id: id }));
    if (table === 'nodes') {
      const back = await Promise.all(ids.map((id) => api('GET', '/edges' + qs({ node: id })).then((x) => x.items).catch(() => [])));
      back.flat().forEach((e) => rows.push({ table_name: 'edges', row_id: e.id }));
    }
    await applyChanges(rows);
  }
  async function deleteSelection() {
    if (!canEdit) return;
    const nodes = cy.$('node:selected').filter((n) => !n.hasClass('ghost')), edges = cy.$('edge:selected').filter((e) => !e.hasClass('ghost'));
    if (!nodes.length && !edges.length) return;
    let imp = { edges: 0, resources: 0 };
    for (const n of nodes.toArray().slice(0, 20)) { try { const x = await api('GET', '/nodes/' + n.id() + '/impact'); imp.edges += x.edges; imp.resources += x.resources; } catch (e) { /* counts are advisory */ } }
    const isEditor = can('editor');
    const ok = await confirmDialog({ title: (isEditor ? 'Archive ' : 'Propose archiving ') + [nodes.length ? plural(nodes.length, 'record') : null, edges.length ? plural(edges.length, 'relationship') : null].filter(Boolean).join(' and ') + '?',
      danger: isEditor, confirmLabel: isEditor ? 'Archive' : 'Send for approval',
      body: el('div', { class: 'col', 'data-testid': 'archive-impact' },
        nodes.length ? el('p', { class: 'small', text: nodes.map((n) => '“' + n.data('label') + '”').slice(0, 5).join(', ') + (nodes.length > 5 ? ' and ' + (nodes.length - 5) + ' more' : '') }) : null,
        nodes.length ? el('ul', { class: 'small', style: 'margin:0;padding-left:18px' }, el('li', { text: plural(imp.edges, 'relationship') + ' will be archived with them' }), el('li', { text: plural(imp.resources, 'link') + ' will be archived with them' })) : null,
        el('p', { class: 'faint small', text: 'Nothing is deleted: everything can be restored from Archived, or with Undo.' })) });
    if (!ok) return;
    if (edges.length) await removeEdges(edges.map((e) => e.id()), !!nodes.length);
    if (nodes.length) await archiveNodes(nodes.map((n) => n.id()));
  }

  // ---------------------------------------------------------------- edges: click → inspector
  function edgeInspector(e, rp) {
    const s = e.source(), t = e.target();
    const note = el('input', { value: e.data('note') || '', 'aria-label': 'Note', placeholder: 'Note (optional)', 'data-testid': 'graph-edge-note', disabled: !canEdit });
    popover(anchorAt(rp), [el('p', { class: 'small', 'data-testid': 'graph-edge-sentence' }, el('strong', { text: s.data('label') }), ' ' + e.data('label') + ' ', el('strong', { text: t.data('label') })),
      note, el('div', { class: 'row' },
        el('button', { class: 'btn sm ghost', type: 'button', text: 'Open ' + s.data('label'), onclick: () => { closeMenu(); setQuery({ open: s.id() }, true); } }),
        el('span', { class: 'spacer' }),
        canEdit ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'graph-edge-remove', onclick: () => { closeMenu(); removeEdges([e.id()]); } }, icon('trash-2', 'sm'), 'Remove') : null,
        canEdit ? el('button', { class: 'btn sm primary', type: 'button', 'data-testid': 'graph-edge-save', text: 'Save note', onclick: async () => {
          try { const u = await api('PATCH', '/edges/' + e.id(), { version: e.data('version'), note: note.value.trim() || null }); e.data({ note: u.note || '', version: u.version }); closeMenu(); toast('Saved'); }
          catch (er) { failToast(er, 'Not saved'); } } }) : null)],
    { testid: 'graph-edge-popover', label: 'Relationship' });
  }

  // ---------------------------------------------------------------- events
  cy.on('tap', 'node', (evt) => {
    const n = evt.target; if (n.hasClass('ghost')) return;
    if (connectFrom === false) { connectFrom = n; n.addClass('connect-src'); info.textContent = 'Now click the record to connect it to.'; return; }
    if (connectFrom) {
      const src = connectFrom; connectFrom = null; src.removeClass('connect-src'); if (connectBtn) connectBtn.classList.remove('primary');
      if (src.id() === n.id()) { info.textContent = 'Pick a different record.'; return; }
      connectPair(ref(src), ref(n), n.renderedPosition()); info.textContent = status();
      return;
    }
    if (evt.originalEvent && evt.originalEvent.shiftKey) return;     // shift-click adds to the selection
    // Open the panel a moment later, so a double-click (rename) is not undone by
    // the panel opening and resizing the canvas under the second click.
    clearTimeout(tapTimer); tapTimer = setTimeout(() => setQuery({ open: n.id() }, true), 260);
  });
  let tapTimer = null;
  cy.on('tap', 'edge', (evt) => { if (!evt.target.hasClass('ghost')) edgeInspector(evt.target, evt.renderedPosition); });
  cy.on('dbltap', (evt) => { if (evt.target === cy) quickCreate(evt.position); });
  cy.on('dbltap', 'node', (evt) => { clearTimeout(tapTimer); if (!evt.target.hasClass('ghost')) { if (canEdit) rename(evt.target); else toggleExpand(evt.target.id()); } });
  cy.on('mouseover', 'edge', (e) => e.target.addClass('hover'));
  cy.on('mouseout', 'edge', (e) => e.target.removeClass('hover'));
  cy.on('dragfree', 'node', (evt) => { const sel = cy.$('node:selected'); queueSave(sel.length && evt.target.selected() ? sel : evt.target); drawMini(); });
  cy.on('tap', (evt) => { if (evt.target === cy) { showHandles(null); } });

  // keyboard: the view-level hook app.js calls (N, F, /, Delete, arrows, E, Esc)
  S.tableKeys = (e) => {
    if (S.graph !== G) return false;
    const k = e.key;
    if (k === '/') { search.focus(); return true; }
    if (k === 'f' || k === 'F') { fit(); return true; }
    if ((k === 'n' || k === 'N') && canEdit) { quickCreate(null); return true; }
    if ((k === 'Delete' || k === 'Backspace') && canEdit) { deleteSelection(); return true; }
    if (k === 'e' || k === 'E') { const n = cy.$('node:selected').first(); if (n.length) toggleExpand(n.id()); return true; }
    if (k === 'Escape') { cy.$(':selected').unselect(); showHandles(null); return true; }
    if (k.startsWith('Arrow') && canEdit) {
      const sel = cy.$('node:selected'); if (!sel.length) return false;
      const d = e.shiftKey ? 80 : 20, dx = k === 'ArrowLeft' ? -d : k === 'ArrowRight' ? d : 0, dy = k === 'ArrowUp' ? -d : k === 'ArrowDown' ? d : 0;
      sel.positions((n) => ({ x: n.position('x') + dx, y: n.position('y') + dy })); queueSave(sel); drawMini(); return true;
    }
    return false;
  };

  // search: jump to and highlight; not loaded yet → load its neighbourhood
  const runSearch = async () => {
    const q = search.value.trim().toLowerCase(); cy.nodes('.found').removeClass('found');
    if (!q) return;
    let hit = visibleNodes().filter((n) => n.data('label').toLowerCase().includes(q)).first();
    if (!hit.length) {
      try { const r2 = await api('GET', '/search' + qs({ q: search.value.trim(), limit: 1 }));
        const n = r2.nodes[0]; if (!n) { toast('Nothing called “' + search.value.trim() + '”'); return; }
        await load(n.id, 1); hit = cy.getElementById(n.id);
      } catch (e) { failToast(e); return; }
    }
    hit.addClass('found'); cy.$(':selected').unselect(); hit.select();
    cy.animate({ center: { eles: hit }, zoom: Math.max(cy.zoom(), 1) }, { duration: 200 });
  };
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); runSearch(); } if (e.key === 'Escape') { search.value = ''; cy.nodes('.found').removeClass('found'); cyBox.focus(); } });
  search.addEventListener('input', debounce(() => { const q = search.value.trim().toLowerCase(); cy.nodes('.found').removeClass('found'); if (q.length > 1) visibleNodes().filter((n) => n.data('label').toLowerCase().includes(q)).addClass('found'); }, 150));

  // ---------------------------------------------------------------- saved graph views
  async function loadViews() {
    try { G.views = (await api('GET', '/views')).items.filter((w) => w.config && w.config.kind === 'graph');
      G.views.forEach((w) => layoutSel.appendChild(el('option', { value: w.id, text: w.name + (w.shared ? ' (shared)' : ''), selected: w.id === layoutId })));
      view = G.views.find((w) => w.id === layoutId) || null;
      if (view && view.config) { Object.assign(hidden, view.config.hidden || {}); Object.assign(edgeHidden, view.config.edgeHidden || {}); ownerFilter = view.config.owner || null; applyFilter(); drawLegend(); }
    } catch (e) { G.views = []; }
  }
  function saveViewDialog() {
    const name = el('input', { 'aria-label': 'View name', 'data-testid': 'graph-view-name', placeholder: 'e.g. Backend course map' });
    const shared = el('input', { type: 'checkbox', checked: true, 'aria-label': 'Shared' });
    openDialog([el('h2', { text: 'Save graph view' }), el('p', { class: 'muted small', text: 'Keeps the starting record, depth, filters and the positions as they are now. Moving records later changes only this view.' }),
      name, el('label', { class: 'row small' }, shared, 'Share with everyone'),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', 'data-testid': 'graph-view-save', text: 'Save', onclick: async () => {
          if (!name.value.trim()) { name.focus(); return; }
          try {
            const w = await api('POST', '/views', { name: name.value.trim(), shared: shared.checked, config: { kind: 'graph', center, depth, hidden, edgeHidden, owner: ownerFilter } });
            await api('POST', '/graph/positions', { layout: w.id, positions: visibleNodes().map((n) => ({ node_id: n.id(), x: n.position('x'), y: n.position('y') })) });
            closeDialog(); toast('Saved view “' + w.name + '”'); location.hash = '#/graph/' + center + qs({ depth, view: w.id });
          } catch (e) { failToast(e, 'Not saved'); }
        } }))], { label: 'Save graph view' });
  }

  // ---------------------------------------------------------------- live sync + presence
  /* Live sync: apply exactly the rows that changed. A record or relationship
     that was archived or deleted disappears; a renamed one updates in place; a
     new relationship touching a record on screen appears, bringing its other
     end along. Nothing else on the canvas moves. */
  async function applyChanges(changes) {
    if (S.graph !== G) return;
    const nodeIds = [...new Set(changes.filter((c) => c.table_name === 'nodes').map((c) => c.row_id))];
    const edgeIds = [...new Set(changes.filter((c) => c.table_name === 'edges').map((c) => c.row_id))];
    for (const id of nodeIds) {
      const here = cy.getElementById(id);
      try {
        const n = await api('GET', '/nodes/' + id);
        if (n.archived_at) { here.remove(); continue; }
        if (here.length) here.data(Object.assign(here.data(), { label: n.name, version: n.version, owner: n.owner_id || null }));
        else if (G.pendingRestore && G.pendingRestore.has(id)) { addNode(n, G.pendingRestore.get(id)); G.pendingRestore.delete(id); }
      } catch (e) { if (e.status === 404) here.remove(); }
    }
    for (const id of edgeIds) {
      const here = cy.getElementById(id);
      try {
        const e = await api('GET', '/edges/' + id);
        if (e.archived_at) { here.remove(); continue; }
        if (here.length) { here.data({ note: e.note || '', version: e.version }); continue; }
        const s0 = cy.getElementById(e.source_id), t0 = cy.getElementById(e.target_id);
        if (!s0.length && !t0.length) continue;                   // not about anything on screen
        for (const [have, other] of [[s0, e.target_id], [t0, e.source_id]]) {
          if (have.length && !cy.getElementById(other).length) {
            try { const o = await api('GET', '/nodes/' + other); if (!o.archived_at) { addNode(o, { x: have.position('x') + (Math.random() - 0.5) * 220, y: have.position('y') + 120 }); addedBy[o.id] = have.id(); } } catch (er) { /* gone */ }
          }
        }
        if (cy.getElementById(e.source_id).length && cy.getElementById(e.target_id).length) {
          const et = S.edgeTypes.find((x) => x.key === e.type) || {};
          cy.add({ group: 'edges', data: edgeData(Object.assign({ label: et.label || e.type }, e)) });
        }
      } catch (er) { if (er.status === 404) here.remove(); }
    }
    applyFilter(); drawLegend(); markPresence();
    G.synced = (G.synced || 0) + 1;
  }
  function addNode(n, pos) {
    if (cy.getElementById(n.id).length) return;
    cy.add({ group: 'nodes', data: nodeData(Object.assign({ degree: 0 }, n)), position: pos, classes: 'placed' });
  }
  async function refresh() { await applyChanges([...cy.nodes(':not(.ghost)').map((n) => ({ table_name: 'nodes', row_id: n.id() }))]); }
  onLiveChange((theirs) => {
    if (S.graph !== G) return;
    const mine = theirs.filter((c) => c.table_name === 'nodes' || c.table_name === 'edges');
    if (mine.length) applyChanges(mine);
  });
  function markPresence() {
    cy.batch(() => cy.nodes(':not(.ghost)').forEach((n) => n.toggleClass('presence', others(n.id()).some((o) => o.editing))));
    if (handleNode) placeHandles();
  }
  onPresence(() => { if (S.graph === G) markPresence(); });
  G.reload = () => { cy.elements().remove(); expanded = {}; addedBy = {}; load(center, depth, true); };
  G.expand = (id) => load(id, 1);
  G.connect = (a, b) => connectPair(ref(cy.getElementById(a)), ref(cy.getElementById(b)), cy.getElementById(b).renderedPosition());
  G.refresh = refresh;
  G.renderedPosition = (id) => { const rect = cyBox.getBoundingClientRect(), q = cy.getElementById(id).renderedPosition(); return [rect.left + q.x, rect.top + q.y]; };
  loadViews();
  load(center, depth, true);
}
