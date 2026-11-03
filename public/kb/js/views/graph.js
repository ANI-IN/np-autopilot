/* Graph (run 3 editing surface; run 6 B2: one clear structure and navigation).

   Two entry points, one view:
     #/graph            the whole graph (current records), read from GET /api/kb/graph
     #/graph/<id>       one record's neighbourhood (focus=<id>, depth 1-2), expandable

   Structure  the default arrangement is the hierarchy Program > Course > Domain >
              Module > Week > Session in rows, with topics, people and links as
              satellites under the record they hang off; more than BUNDLE_FROM of one
              type on one record become a bundle ("137 topics") that opens on click.
              Arrangements: Hierarchy, Force, Radial (rings around the focused record),
              Saved positions. Group by type or by program / course / domain / module:
              a box per group that folds into one node. Legacy and archived records
              are hidden unless "Show legacy" / "Show archived" (legacy=all / archived=1).
   Reading    shapes, colours and icons per type and line colour / style per
              relationship come from GET /api/kb/types (graph/style.js); the legend is
              also the filter; breadcrumbs for the focused record; focus mode dims all
              but 1-2 hops; search jumps to a record (opening its bundle or group);
              minimap and fit; labels never overlap (graph/labels.js) and appear on
              hover; edges outside the hierarchy hide when zoomed far out.
   Editing    as built in run 3: create (double-click / N), connect (drag a handle),
              rename (double-click), archive (Delete) with Undo, move (positions saved
              per layout), saved graph views. `?` opens the shortcut sheet.
   Live       applyChanges(rows) is the single entry point for change-feed rows (the
              shared feed in live.js, and this page's own poll of /changes from `head`).
   Rendering  Cytoscape's canvas renderer; its WebGL renderer above GL_FROM drawn
              records (docs/run6/GRAPH_PERF.md). */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, toast, failToast, qs, setQuery, empty, errorBox, combobox, nodeSource,
  openDialog, closeDialog, confirmDialog, can, popover, closeMenu, debounce, plural, personName } from '../core.js';
import { pageHead } from '../page.js';
import { relItems, relCombobox, createRelationshipType } from '../relpicker.js';
import { openRecordForm } from '../form.js';
import { onLiveChange } from '../live.js';
import { onPresence, others } from '../realtime.js';
import { RANK, looks, nodeLook, edgeLook, cyStyle, legendShape, legendLine, loadIcons, isShown } from '../graph/style.js';
import { hierarchy, radial, grouped, structure } from '../graph/layouts.js';
import { createMinimap } from '../graph/minimap.js';
import { declutter, labelBoxes } from '../graph/labels.js';

const GL_FROM = 6000;          // WebGL renderer above this many drawn records; measured slower than canvas on real-shaped graphs up to 5,000 (docs/run6/GRAPH_PERF.md); ?renderer=webgl forces it
const BIG_FROM = 800;          // above: straight edges, texture while moving, edges hidden during motion
const BUNDLE_FROM = 9;         // this many satellites of one type on one record become one bundle
const EDGE_LOD_ZOOM = 0.3;     // below this zoom only the hierarchy's lines are drawn
const POLL_MS = 4000;
const DASH_UPTO = 400;       // above this many lines, dashed and dotted relationships draw solid
const ICONS_UPTO = 400;      // icons inside the shapes only while few records are drawn (each is an image per frame)
const ARRANGE = [['hierarchy', 'Hierarchy'], ['force', 'Force'], ['radial', 'Radial'], ['saved', 'Saved positions']];
const isRecord = (n) => !n.id().startsWith('__');
const humanActor = (c) => c.actor_type === 'human' || c.actor_type === 'user';

/* The graph library (~430 KB) loads only when a graph is opened (Phase C). */
let libLoading = null;
function loadLib() {
  if (typeof window.cytoscape === 'function') return Promise.resolve();
  libLoading = libLoading || new Promise((res, rej) => { const sc = document.createElement('script'); sc.src = '/vendor/cytoscape.min.js'; sc.onload = res; sc.onerror = rej; document.head.appendChild(sc); });
  return libLoading;
}
/* graph.css is linked from index.html by the lead; until then the view adds it (same file). */
function ensureCss() {
  if (document.querySelector('link[href="/kb/graph.css"]')) return;
  document.head.appendChild(el('link', { rel: 'stylesheet', href: '/kb/graph.css' }));
}

const normNode = (n) => ({ id: n.id, type: n.type, name: n.name, status: n.status, scope_id: n.scope_id || null, is_legacy: !!n.is_legacy,
  archived: !!(n.archived || n.archived_at), owner_record_id: n.owner_record_id || null, external_id: n.external_id || null,
  degree: n.degree || 0, version: n.version });
const normEdge = (e) => ({ id: e.id, type: e.type || e.edge_type, source: e.source || e.source_id, target: e.target || e.target_id,
  role: e.role || (e.props && e.props.role) || null, is_legacy: !!e.is_legacy, archived: !!(e.archived || e.archived_at), note: e.note, version: e.version });

export function viewGraph(v, r) {
  ensureCss();
  if (typeof window.cytoscape !== 'function') {
    v.appendChild(el('div', { class: 'page-body', 'data-testid': 'graph-loading' }, el('p', { class: 'muted', text: 'Loading the graph…' })));
    loadLib().then(() => { if (S.route && S.route.path[0] === 'graph' && (S.route.path[1] || '') === (r.path[1] || '')) { clear(v); viewGraph(v, S.route); } })
      .catch(() => { clear(v); v.appendChild(errorBox({ message: 'The graph library did not load. Reload the page.' })); });
    return;
  }
  buildGraph(v, r);
}

function buildGraph(v, r) {
  const center = r.path[1] || null;
  const q0 = r.q;
  const opt = { depth: q0.depth === '2' ? 2 : 1, arrange: q0.arrange || (q0.view ? 'saved' : 'hierarchy'), group: q0.group || 'none',
    legacy: q0.legacy === 'all' ? 'all' : 'current', archived: q0.archived === '1', focus: Number(q0.focus) || 0, unbundled: q0.bundle === '0' || q0.expand === 'all' };
  const layoutId = q0.view || 'default';
  const canEdit = can('contributor');
  const hidden = {}, edgeHidden = {};
  let ownerFilter = null, scopeFilter = null, connectFrom = null;
  const M = { nodes: new Map(), edges: new Map() };
  const expandedBundles = new Set(), foldedGroups = new Set();
  let expanded = {}, addedBy = {}, total = 0, truncated = false, head = 0, cy = null, mm = null, lastStruct = null;
  const G = { center, layoutId };                 // this view's handle; listeners check S.graph === G
  S.graph = G;
  window.__kbGraph = G;                            // for tests and the perf script; holds no data of its own

  // ---------------------------------------------------------------- header
  const info = el('span', { class: 'sub', 'data-testid': 'graph-info', 'aria-live': 'polite' });
  const depthSel = center ? el('select', { 'aria-label': 'Depth', 'data-testid': 'graph-depth' }, el('option', { value: '1', text: '1 step', selected: opt.depth === 1 }), el('option', { value: '2', text: '2 steps', selected: opt.depth === 2 })) : null;
  if (depthSel) depthSel.addEventListener('change', () => setQuery({ depth: depthSel.value }, true));
  const layoutSel = el('select', { 'aria-label': 'Saved layout', 'data-testid': 'graph-layout' }, el('option', { value: 'default', text: 'Shared layout' }));
  layoutSel.addEventListener('change', () => { const w = (G.views || []).find((x) => x.id === layoutSel.value);
    location.hash = '#/graph' + (w ? '/' + w.config.center : center ? '/' + center : '') + qs({ depth: w ? w.config.depth || 1 : center ? opt.depth : null, view: w ? w.id : null }); });
  const connectBtn = canEdit ? el('button', { class: 'btn', type: 'button', 'data-testid': 'graph-connect', title: 'Or drag from a record’s handle',
    onclick: () => { connectFrom = connectFrom === null ? false : null; connectBtn.classList.toggle('primary', connectFrom === false);
      info.textContent = connectFrom === false ? 'Connect: click the first record, then the second.' : status(); } }, icon('git-branch', 'sm'), 'Connect') : null;
  const head1 = pageHead({ title: 'Graph', actions: [
    center ? el('a', { class: 'btn ghost', href: '#/graph', 'data-testid': 'graph-overview', title: 'The whole graph' }, icon('network', 'sm'), 'Whole graph') : null,
    layoutSel, depthSel,
    canEdit ? el('button', { class: 'btn', type: 'button', 'data-testid': 'graph-save-view', onclick: saveViewDialog }, 'Save view') : null, connectBtn,
    canEdit ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'graph-new', title: 'New record here (N)', onclick: () => quickCreate(null) }, icon('plus'), 'New') : null] });
  head1.querySelector('.page-title').after(info);
  v.appendChild(head1);

  // ---------------------------------------------------------------- canvas + tools
  const side = el('aside', { class: 'graph-side', 'aria-label': 'Legend and filters', 'data-testid': 'graph-legend' });
  const cyBox = el('div', { id: 'cy', 'data-testid': 'graph-canvas', role: 'application', tabindex: '0',
    'aria-label': 'Relationship graph. Question mark lists the shortcuts: N new record, F fit, slash search, Delete archive the selection, arrows move it, Escape clears it.' });
  const canvas = el('div', { class: 'graph-canvas' }, cyBox);
  const search = el('input', { type: 'search', placeholder: 'Find in graph  /', 'aria-label': 'Find a record in the graph', 'data-testid': 'graph-search', list: 'graph-search-list' });
  const searchList = el('datalist', { id: 'graph-search-list' });
  const sel = (testid, label, options, value, onchange) => { const s = el('select', { 'aria-label': label, title: label, 'data-testid': testid },
    options.map(([v2, t]) => el('option', { value: v2, text: t, selected: v2 === value }))); s.addEventListener('change', () => onchange(s.value)); return s; };
  const arrangeSel = sel('graph-arrange', 'Arrangement', ARRANGE, opt.arrange, (x) => setQuery({ arrange: x === 'hierarchy' && layoutId === 'default' ? null : x }, true));
  const groupSel = sel('graph-group', 'Group by', [['none', 'No groups']], opt.group, (x) => setQuery({ group: x === 'none' ? null : x }, true));
  const focusSel = sel('graph-focus', 'Focus mode', [['0', 'Focus off'], ['1', 'Focus: 1 step'], ['2', 'Focus: 2 steps']], String(opt.focus), (x) => setQuery({ focus: x === '0' ? null : x }, true));
  const tools = el('div', { class: 'graph-tools' },
    el('div', { class: 'input-icon graph-find' }, icon('search'), search, searchList),
    el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-fit', title: 'Fit to view (F)', onclick: () => fit() }, icon('maximize-2', 'sm'), 'Fit'),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom in (+)', 'aria-label': 'Zoom in', onclick: () => zoomBy(1.25) }, icon('zoom-in', 'sm')),
    el('button', { class: 'btn sm icon', type: 'button', title: 'Zoom out (-)', 'aria-label': 'Zoom out', onclick: () => zoomBy(0.8) }, icon('zoom-out', 'sm')),
    arrangeSel, groupSel, focusSel,
    canEdit ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-autolayout', title: 'Arrange everything automatically and save it to this layout', onclick: () => autoLayout(true) }, icon('layout-grid', 'sm'), 'Auto-layout') : null,
    canEdit ? el('button', { class: 'btn sm ghost', type: 'button', 'data-testid': 'graph-reset', title: 'Forget the saved positions of this layout', onclick: resetLayout }, icon('rotate-ccw', 'sm'), 'Reset') : null,
    el('span', { class: 'spacer' }),
    el('button', { class: 'btn sm icon', type: 'button', 'data-testid': 'graph-help', title: 'Keyboard shortcuts (?)', 'aria-label': 'Keyboard shortcuts', onclick: () => shortcutSheet() }, icon('keyboard', 'sm')));
  const crumbs = el('nav', { class: 'graph-crumbs', 'aria-label': 'Where this record sits', 'data-testid': 'graph-breadcrumbs', hidden: true });
  const mini = el('canvas', { class: 'minimap', width: '360', height: '240', tabindex: '0', 'aria-label': 'Minimap: click or drag to move the view, arrows pan', 'data-testid': 'minimap' });
  const miniToggle = el('button', { class: 'btn sm icon graph-mini-toggle', type: 'button', title: 'Show or hide the minimap (M)', 'aria-label': 'Show or hide the minimap', 'data-testid': 'graph-minimap-toggle',
    onclick: () => toggleMini() }, icon('scan', 'sm'));
  const handles = el('div', { class: 'graph-handles', hidden: true, 'data-testid': 'graph-handles' });
  const hint = el('div', { class: 'graph-hint', 'data-testid': 'graph-hint', hidden: true });
  const emptyBox = el('div', { class: 'graph-empty', hidden: true, 'data-testid': 'graph-empty' });
  canvas.append(tools, crumbs, mini, miniToggle, handles, hint, emptyBox);
  v.appendChild(el('div', { class: 'graph-wrap' }, side, canvas));

  const css = getComputedStyle(document.documentElement);
  const tok = (k, d) => css.getPropertyValue(k).trim() || d;
  const meta = () => ({ node_types: S.types, edge_types: S.edgeTypes });
  let L = looks(meta()), icons = {};

  // ---------------------------------------------------------------- data
  function ingest(resp, by) {
    resp.nodes.forEach((n0) => { const n = normNode(n0); const had = M.nodes.get(n.id); if (had && had.version !== undefined && n.version === undefined) n.version = had.version;
      M.nodes.set(n.id, n); if (by && !addedBy[n.id] && n.id !== center) addedBy[n.id] = by; });
    resp.edges.forEach((e0) => { const e = normEdge(e0); const had = M.edges.get(e.id); if (had) { e.note = had.note; if (e.version === undefined) e.version = had.version; } M.edges.set(e.id, e); });
    if (resp.head && resp.head > head) head = resp.head;
  }
  function params(extra) { return Object.assign({ legacy: opt.legacy === 'all' ? 'all' : null, archived: opt.archived ? '1' : null }, extra); }
  async function fetchAll() {
    if (center) {
      const resp = await api('GET', '/graph' + qs(params({ focus: center, depth: opt.depth, limit: r.q.limit || 1000 })));
      ingest(resp); total = resp.total_nodes; truncated = resp.truncated; expanded[center] = true;
      return;
    }
    let cursor = null, pages = 0;
    do {
      const resp = await api('GET', '/graph' + qs(params({ limit: r.q.limit || 5000, cursor })));
      ingest(resp); total = resp.total_nodes; cursor = resp.next_cursor; pages++;
    } while (cursor && pages < 6);
    truncated = !!cursor;
  }

  // ---------------------------------------------------------------- projection: model -> what is drawn
  const nodeData = (n) => { const k = nodeLook(L, n.type); return { id: n.id, label: n.name, type: n.type, color: k.color, rank: k.rank, scope: n.scope_id,
    owner: n.owner_record_id, version: n.version, degree: n.degree }; };
  const edgeData = (e) => { const k = edgeLook(L, e.type); return { id: e.id, source: e.source, target: e.target, type: e.type, label: k.label + (e.role ? ' (' + e.role.replace('_', ' ') + ')' : ''),
    version: e.version, color: k.color, lineStyle: k.style }; };
  function passes(n) {
    if (n.id === center) return true;
    if (hidden[n.type]) return false;
    if (ownerFilter === 'none' ? !!n.owner_record_id : ownerFilter ? n.owner_record_id !== ownerFilter : false) return false;
    if (scopeFilter && !scopeFilter.ids.has(n.id)) return false;
    return true;
  }
  function groupKeyFn(st) {
    if (opt.group === 'none') return () => null;
    if (opt.group === 'type') return (n) => n.type;
    const T = opt.group, memo = new Map();
    const up = (id, seen) => {
      if (memo.has(id)) return memo.get(id);
      const n = M.nodes.get(id); if (!n || seen.has(id)) return null;
      seen.add(id);
      let k = null;
      if (n.type === T) k = id;
      else { const p = st.parent.get(id) || st.owner.get(id) || (n.scope_id && M.nodes.has(n.scope_id) ? n.scope_id : null); k = p ? up(p, seen) : null; }
      memo.set(id, k); return k;
    };
    return (n) => up(n.id, new Set());
  }
  const groupLabel = (k, count) => (opt.group === 'type' ? typeLabel(k, true) : (M.nodes.get(k) || {}).name || 'Other') + ' · ' + count;
  let drawn = [], bundles = new Map(), groups = new Map(), groupOf = () => null;

  /* Rebuild what is drawn from the model and the view options. Additive and
     idempotent: elements are added or updated, records removed only by remove(). */
  function project() {
    const want = [...M.nodes.values()].filter(passes);
    const wantIds = new Set(want.map((n) => n.id));
    const wantEdges = [...M.edges.values()].filter((e) => wantIds.has(e.source) && wantIds.has(e.target) && !edgeHidden[e.type]);
    const st = structure(want.map((n) => ({ id: n.id, type: n.type, label: n.name, scope: n.scope_id, rank: nodeLook(L, n.type).rank, degree: n.degree })),
      wantEdges.map((e) => ({ source: e.source, target: e.target })));
    lastStruct = st;
    // bundles: satellites of one type on one record
    bundles = new Map();
    const keepOut = new Set([center, ...cy.$(':selected').map((x) => x.id()), ...cy.nodes('.found').map((x) => x.id())]);
    const noBundle = opt.unbundled;
    if (!noBundle) {
      const by = new Map();
      want.forEach((n) => { const a = st.anchor.get(n.id); if (!a || keepOut.has(n.id) || nodeLook(L, n.type).rank !== null) return;
        const k = a + '|' + n.type; if (!by.has(k)) by.set(k, []); by.get(k).push(n.id); });
      by.forEach((ids, k) => { if (ids.length >= BUNDLE_FROM && !expandedBundles.has(k)) bundles.set(k, { anchor: k.split('|')[0], type: k.split('|')[1], ids }); });
    }
    const bundled = new Map(); bundles.forEach((b, k) => b.ids.forEach((id) => bundled.set(id, k)));
    const adj = new Map(); wantEdges.forEach((e) => { [e.source, e.target].forEach((x) => { if (!adj.has(x)) adj.set(x, []); adj.get(x).push(e); }); });
    // groups
    groupOf = groupKeyFn(st);
    groups = new Map();
    want.forEach((n) => { const g = groupOf(n); if (g) { if (!groups.has(g)) groups.set(g, []); groups.get(g).push(n.id); } });
    const folded = new Map(); foldedGroups.forEach((g) => { (groups.get(g) || []).forEach((id) => { if (id !== center) folded.set(id, g); }); });

    cy.batch(() => {
      // records: bundled ones are not drawn at all (the bundle stands in for them)
      const addN = [], addE = [];
      const cls = (c, k, on) => { if (c.hasClass(k) !== on) c.toggleClass(k, on); };
      M.nodes.forEach((n) => {
        const c = cy.getElementById(n.id);
        if (bundled.has(n.id)) { if (c.length) c.remove(); return; }
        const flags = { hidden: !wantIds.has(n.id), folded: folded.has(n.id), legacy: n.is_legacy, archived: n.archived, center: n.id === center };
        if (!c.length) { addN.push({ group: 'nodes', data: nodeData(n), position: { x: 0, y: 0 }, classes: Object.keys(flags).filter((k) => flags[k]).join(' ') }); return; }
        const d = nodeData(n); if (c.data('label') !== d.label || c.data('version') !== d.version || c.data('type') !== d.type || c.data('owner') !== d.owner || c.data('color') !== d.color) c.data(d);
        Object.entries(flags).forEach(([k, on]) => cls(c, k, on));
      });
      if (addN.length) cy.add(addN);
      M.edges.forEach((e) => {
        if (bundled.has(e.source) || bundled.has(e.target)) return;
        const c = cy.getElementById(e.id);
        const flags = { hidden: !!edgeHidden[e.type], legacy: e.is_legacy, archived: e.archived };
        if (!c.length) { if (cy.getElementById(e.source).length && cy.getElementById(e.target).length) addE.push({ group: 'edges', data: edgeData(e), classes: Object.keys(flags).filter((k) => flags[k]).join(' ') }); return; }
        // a merge changes a relationship's type; a type rename or restyle changes its look
        const d = edgeData(e); if (c.data('type') !== d.type || c.data('version') !== d.version || c.data('label') !== d.label || c.data('color') !== d.color) c.data(d);
        Object.entries(flags).forEach(([k, on]) => cls(c, k, on));
      });
      if (addE.length) cy.add(addE);
      // bundles + their one line to the anchor
      const keepB = new Set();
      bundles.forEach((b, k) => {
        const id = '__b:' + k, look = nodeLook(L, b.type); keepB.add(id); keepB.add('__be:' + k);
        const types = {}; const mem = new Set(b.ids);
        (adj.get(b.anchor) || []).forEach((e) => { if (mem.has(e.source) || mem.has(e.target)) types[e.type] = (types[e.type] || 0) + 1; });
        const rt = Object.keys(types).sort((x, y) => types[y] - types[x])[0] || 'related';
        const label = b.ids.length + ' ' + (look.plural || typeLabel(b.type, true) || b.type).toLowerCase();
        const data = { id, label, type: b.type, color: look.color, rank: null, size: Math.round(Math.max(28, Math.min(44, 22 + Math.sqrt(b.ids.length) * 1.6))), count: b.ids.length, bundle: k };
        let bn = cy.getElementById(id);
        if (!bn.length) { const ap = cy.getElementById(b.anchor).position(); bn = cy.add({ group: 'nodes', data, classes: 'bundle', position: { x: ap.x, y: ap.y + 64 } }); } else bn.data(data);
        bn.toggleClass('folded', folded.has(b.anchor));
        const ed = { id: '__be:' + k, source: b.anchor, target: id, type: rt, label: edgeLook(L, rt).label + ' · ' + b.ids.length, w: Math.min(6, 1.2 + Math.log2(b.ids.length) / 2) };
        if (!cy.getElementById(ed.id).length) cy.add({ group: 'edges', data: ed, classes: 'bundle-edge' });
      });
      // folded groups: one node each, and their lines to the rest merged per neighbour
      foldedGroups.forEach((g) => { if (!groups.has(g)) return;
        const ids = groups.get(g).filter((id) => id !== center), first = M.nodes.get(ids[0]) || {};
        const look = opt.group === 'type' ? nodeLook(L, g) : nodeLook(L, (M.nodes.get(g) || first).type);
        const id = '__g:' + g; keepB.add(id);
        const data = { id, label: groupLabel(g, ids.length), type: opt.group === 'type' ? g : (M.nodes.get(g) || first).type, color: look.color, rank: look.rank,
          size: Math.round(Math.max(34, Math.min(52, 26 + Math.sqrt(ids.length) * 2))), count: ids.length, group: g };
        let gn = cy.getElementById(id);
        if (!gn.length) { const pp = cy.getElementById(ids[0]).position(); gn = cy.add({ group: 'nodes', data, classes: 'collapsed', position: { x: pp.x, y: pp.y } }); } else gn.data(data);
      });
      const meta2 = new Map();
      cy.edges().forEach((e) => { if (e.id().startsWith('__')) return;
        const s = e.source().id(), t = e.target().id(); const gs = folded.get(s), gt = folded.get(t);
        if (!gs && !gt) return;
        const a = gs ? '__g:' + gs : (bundled.has(s) || e.source().hasClass('hidden') ? null : s), b = gt ? '__g:' + gt : (bundled.has(t) || e.target().hasClass('hidden') ? null : t);
        if (!a || !b || a === b || e.hasClass('hidden')) return;
        const k = a < b ? a + '|' + b : b + '|' + a; const m = meta2.get(k) || { a, b, n: 0, type: e.data('type') }; m.n++; meta2.set(k, m); });
      meta2.forEach((m, k) => { const id = '__ge:' + k; keepB.add(id);
        const data = { id, source: m.a, target: m.b, type: m.type, label: plural(m.n, 'relationship'), w: Math.min(6, 1 + Math.log2(m.n + 1)) };
        const c = cy.getElementById(id);
        if (!c.length) cy.add({ group: 'edges', data, classes: 'bundle-edge' }); else c.data({ label: data.label, w: data.w }); });
      cy.elements().filter((x) => /^__(b|be|g|ge):/.test(x.id()) && !keepB.has(x.id())).remove();
    });
    drawn = cy.nodes().filter(isShown).filter((n) => !n.hasClass('gbox') && !n.hasClass('ghead') && !n.hasClass('ghost'));
    G.bundles = bundles.size; G.total = total;
  }

  // ---------------------------------------------------------------- layout
  function layoutInput() {
    const nodes = drawn.map((n) => ({ id: n.id(), type: n.data('type'), label: n.data('label'), scope: n.data('scope'),
      rank: n.data('rank') === undefined ? null : n.data('rank'), degree: n.degree(false), bundle: n.data('bundle') ? { anchor: bundles.get(n.data('bundle')).anchor } : null }));
    const ids = new Set(nodes.map((n) => n.id));
    const edges = cy.edges().filter((e) => ids.has(e.source().id()) && ids.has(e.target().id())).map((e) => ({ source: e.source().id(), target: e.target().id() }));
    return { nodes, edges };
  }
  async function arrange(how, keep) {
    const before = keep ? cy.getElementById(keep) : null;
    const rp = before && before.length ? Object.assign({}, before.renderedPosition()) : null;
    const { nodes, edges } = layoutInput();
    let pos = null;
    if (opt.group === 'type' && how !== 'saved' && how !== 'force') pos = grouped(nodes, (n) => n.type, (k) => typeLabel(k, true)).pos;
    else if (how === 'radial') pos = radial(nodes, edges, focusId() || center);
    else if (how === 'force') {
      const eles = drawn.union(drawn.connectedEdges().filter((e) => isShown(e)));
      if (!cy.nodes('.placed').length) applyPositions(hierarchy(nodes, edges));
      await new Promise((done) => { const l = eles.layout({ name: 'cose', animate: false, randomize: false, fit: false, padding: 48, numIter: drawn.length > 600 ? 300 : 1000,
        idealEdgeLength: () => 110, nodeRepulsion: () => 90000, nodeOverlap: 30, componentSpacing: 120, gravity: 0.6 }); l.one('layoutstop', done); l.run(); });
    } else pos = hierarchy(nodes, edges);
    if (how === 'saved') {
      const saved = await savedPositions();
      Object.entries(saved).forEach(([id, p]) => { if (pos.has(id)) pos.set(id, p); });
    }
    if (pos) applyPositions(pos);
    cy.nodes().filter(isRecord).addClass('placed');
    const treeOn = (how === 'hierarchy' || how === 'saved') && opt.group !== 'type';
    const isS = (n) => n.data('rank') !== null && n.data('rank') !== undefined;
    const many = cy.nodes().filter(isShown).length > 60;
    cy.batch(() => cy.edges().forEach((e) => { const t = treeOn && ((isS(e.source()) && isS(e.target())) || e.hasClass('bundle-edge')) && e.source().position('y') < e.target().position('y'); if (e.hasClass('tree') !== t) e.toggleClass('tree', t);
      const x = treeOn && !t && !e.hasClass('bundle-edge') && many; if (e.hasClass('cross') !== x) e.toggleClass('cross', x); }));
    drawBoxes();
    if (rp && before.inside()) { const now = before.renderedPosition(); cy.panBy({ x: rp.x - now.x, y: rp.y - now.y }); }
    afterChange();
  }
  function applyPositions(pos) { cy.batch(() => pos.forEach((p, id) => { const n = cy.getElementById(id); if (n.length) n.position(p); })); }

  /* Group boxes: a faint box per (unfolded) group around its records, with a
     title to fold it; for "type" grouping the regions come from the layout. */
  function drawBoxes() {
    cy.batch(() => {
      cy.remove('node.gbox, node.ghead');
      if (opt.group === 'none') return;
      groups.forEach((ids, g) => {
        if (foldedGroups.has(g)) return;
        const els = cy.collection(ids.map((id) => cy.getElementById(id)).filter((x) => x.length && isShown(x)));
        const withB = els.union(cy.nodes('.bundle').filter((b) => ids.includes(bundles.get(b.data('bundle')) && bundles.get(b.data('bundle')).anchor)));
        if (!withB.length) return;
        const bb = withB.boundingBox({ includeLabels: true }); const pad = 18;
        const w = bb.w + 2 * pad, h = bb.h + 2 * pad + 26;
        cy.add([{ group: 'nodes', data: { id: '__box:' + g, w, h }, classes: 'gbox', position: { x: bb.x1 - pad + w / 2, y: bb.y1 - pad - 26 + h / 2 }, selectable: false, grabbable: false },
          { group: 'nodes', data: { id: '__head:' + g, w: Math.min(w, 320), label: groupLabel(g, ids.length), group: g }, classes: 'ghead', position: { x: bb.x1 - pad + Math.min(w, 320) / 2, y: bb.y1 - pad - 12 }, selectable: false, grabbable: false }]);
      });
    });
  }
  const refreshBoxes = debounce(() => { if (opt.group !== 'none') drawBoxes(); }, 120);

  // ---------------------------------------------------------------- helpers
  const visibleNodes = () => cy.nodes().filter(isShown).filter(isRecord);
  function status() {
    const shown = visibleNodes().length;
    let s = 'Showing ' + shown + ' record(s)';
    const inB = [...bundles.values()].reduce((a, b) => a + b.ids.length, 0);
    if (inB) s += ' · ' + inB + ' more in ' + plural(bundles.size, 'bundle');
    const inG = [...foldedGroups].reduce((a, g) => a + ((groups.get(g) || []).length), 0);
    if (inG) s += ' · ' + inG + ' in ' + plural(foldedGroups.size, 'folded group');
    if (truncated) s += ' (' + M.nodes.size + ' of ' + total + ' loaded)';
    return s;
  }
  function fit(eles) {
    const vis = eles || cy.nodes().filter(isShown).filter((n) => !n.hasClass('ghead'));
    cy.fit(vis.length ? vis : undefined, 48);
    if (cy.zoom() > 1.6) { cy.zoom(1.6); cy.center(vis); }
  }
  function zoomBy(f) { cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); }
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
  const focusId = () => { const s = cy.$('node:selected').filter(isRecord); if (s.length === 1) return s.id(); if (S.route && S.route.q.open && cy.getElementById(S.route.q.open).length) return S.route.q.open; return center; };

  // ---------------------------------------------------------------- after any change: classes, labels, legend, status
  let lodOn = false, tier = 0;
  /* Semantic zoom: zoomed out, the hierarchy's labels (and bundles') grow so the
     structure stays readable; everything else waits for hover or zoom. */
  function lod() {
    const t = cy.zoom() < 0.25 ? 2 : cy.zoom() < 0.5 ? 1 : 0;
    if (t !== tier) { tier = t; cy.batch(() => cy.nodes().forEach((n) => { const big = (n.data('rank') !== null && n.data('rank') !== undefined) || n.hasClass('collapsed') || n.hasClass('ghead');
      n.toggleClass('far1', big && t === 1); n.toggleClass('far2', big && t === 2); })); }
    const want = cy.zoom() < EDGE_LOD_ZOOM && cy.edges().filter((e) => !e.hasClass('hidden') && isShown(e.source()) && isShown(e.target())).length > 150;
    if (want === lodOn) return;
    lodOn = want;
    cy.batch(() => cy.edges().forEach((e) => {
      const hier = (e.source().data('rank') !== null && e.source().data('rank') !== undefined && e.target().data('rank') !== null && e.target().data('rank') !== undefined) || e.hasClass('bundle-edge');
      e.toggleClass('lod', want && !hier);
    }));
  }
  let relabelT = null;
  function relabel() { clearTimeout(relabelT); relabelT = setTimeout(() => { if (!cy || S.graph !== G) return; G.labels = declutter(cy); }, 120); }
  function applyFocus() {
    cy.batch(() => {
      cy.elements('.dim, .near, .focus, .focus-edge').removeClass('dim near focus focus-edge');
      const fid = focusId();
      if (!opt.focus || !fid) return;
      let ring = cy.getElementById(fid); if (!ring.length) return;
      ring.addClass('focus');
      let set = ring;
      for (let i = 0; i < opt.focus; i++) set = set.union(set.neighborhood());
      set.nodes().addClass('near');
      cy.nodes().filter(isShown).filter((n) => !set.contains(n) && !n.hasClass('gbox') && !n.hasClass('ghead')).addClass('dim');
      cy.edges().filter(isShown).forEach((e) => e.addClass(set.contains(e.source()) && set.contains(e.target()) ? 'focus-edge' : 'dim'));
    });
  }
  /* Many lines on screen: dashes and dots cost a canvas a lot per frame, so the
     lines go solid (their colour still says the relationship; the legend keeps
     the style). */
  let dashOff = false, bigMode = false, iconsOn = true;
  function applyStyle() {
    cy.style(cyStyle(meta(), tok, iconsOn ? icons : {})
      // large graphs: Cytoscape's recipe -- straight "haystack" lines without arrows
      .concat(bigMode ? [{ selector: 'edge', style: { 'curve-style': 'haystack', 'haystack-radius': 0, 'target-arrow-shape': 'none' } }] : [])
      .concat(dashOff ? [{ selector: 'edge', style: { 'line-style': 'solid' } }] : []));
  }
  function dashes() {
    const many = cy.edges().filter((e) => !e.hasClass('hidden')).length > DASH_UPTO;
    const ic = drawn.length <= ICONS_UPTO;
    if (many === dashOff && ic === iconsOn) return;
    dashOff = many; iconsOn = ic;
    applyStyle();
  }
  function afterChange() {
    dashes();
    applyFocus(); lod(); drawLegend(); drawCrumbs(); info.textContent = status(); if (mm) mm.invalidate(); relabel(); markPresence(); showEmpty();
    searchList.replaceChildren(...[...M.nodes.values()].slice(0, 400).map((n) => el('option', { value: n.name })));
  }

  // ---------------------------------------------------------------- legend (doubles as the filter)
  function drawLegend() {
    clear(side);
    const present = {}; M.nodes.forEach((n) => { if (n.id === center || (!scopeFilter || scopeFilter.ids.has(n.id))) present[n.type] = (present[n.type] || 0) + 1; });
    side.appendChild(el('h3', { text: 'Record types' }));
    side.appendChild(el('p', { class: 'faint xs legend-help', text: 'Click a type to hide or show it; Only shows just that type.' }));
    const types = S.types.filter((t) => present[t.key] || hidden[t.key]).sort((a, b) => ((RANK[a.key] ?? 9) - (RANK[b.key] ?? 9)) || a.label.localeCompare(b.label));
    Object.keys(present).filter((k) => !S.typeByKey[k]).forEach((k) => types.push({ key: k, label: k, plural: k, color: L.generic.color, shape: 'ellipse' }));
    types.forEach((t) => {
      const cb = el('input', { type: 'checkbox', checked: !hidden[t.key], 'data-testid': 'graph-filter-' + t.key, 'aria-label': 'Show ' + t.plural });
      cb.addEventListener('change', () => { hidden[t.key] = !cb.checked; applyFilter(); });
      const only = el('button', { class: 'btn ghost sm legend-only', type: 'button', text: 'Only', 'data-testid': 'graph-only-' + t.key, 'aria-label': 'Show only ' + t.plural,
        onclick: (e) => { e.preventDefault(); const solo = types.every((x) => x.key === t.key ? !hidden[x.key] : hidden[x.key]);
          types.forEach((x) => { hidden[x.key] = solo ? false : x.key !== t.key; }); applyFilter(); } });
      side.appendChild(el('label', { class: 'legend-item' + (hidden[t.key] ? ' off' : '') }, cb, legendShape(t.shape || 'ellipse', t.color || L.generic.color),
        el('span', { class: 'truncate', style: 'flex:1', text: t.plural }), only, el('span', { class: 'count', text: present[t.key] || 0 })));
    });
    side.appendChild(el('h3', { text: 'Relationships', style: 'margin-top:8px' }));
    const rels = {}; M.edges.forEach((e) => { rels[e.type] = (rels[e.type] || 0) + 1; });
    Object.keys(rels).concat(Object.keys(edgeHidden).filter((k) => !rels[k])).sort().forEach((k) => {
      const look = edgeLook(L, k);
      const cb = el('input', { type: 'checkbox', checked: !edgeHidden[k], 'data-testid': 'graph-edge-filter-' + k, 'aria-label': 'Show ' + look.label });
      cb.addEventListener('change', () => { edgeHidden[k] = !cb.checked; applyFilter(); });
      side.appendChild(el('label', { class: 'legend-item small' + (edgeHidden[k] ? ' off' : ''), title: look.label + ' (' + look.style + ' line)' }, cb, legendLine(look),
        el('span', { class: 'truncate', style: 'flex:1', text: look.label }), el('span', { class: 'count', text: rels[k] || 0 })));
    });
    side.appendChild(el('h3', { text: 'Show', style: 'margin-top:8px' }));
    const leg = el('input', { type: 'checkbox', checked: opt.legacy === 'all', 'data-testid': 'graph-legacy', 'aria-label': 'Show legacy records' });
    leg.addEventListener('change', () => setQuery({ legacy: leg.checked ? 'all' : null }, true));
    const arc = el('input', { type: 'checkbox', checked: opt.archived, 'data-testid': 'graph-archived', 'aria-label': 'Show archived records' });
    arc.addEventListener('change', () => setQuery({ archived: arc.checked ? '1' : null }, true));
    side.appendChild(el('label', { class: 'legend-item' }, leg, el('span', { text: 'Legacy records' })));
    side.appendChild(el('label', { class: 'legend-item' }, arc, el('span', { text: 'Archived records' })));
    side.appendChild(el('h3', { text: 'Filter', style: 'margin-top:8px' }));
    const owners = {}; M.nodes.forEach((n) => { if (n.owner_record_id) owners[n.owner_record_id] = 1; });
    const ownerSel = el('select', { 'aria-label': 'Owner', 'data-testid': 'graph-owner-filter' }, el('option', { value: '', text: 'Any owner' }), el('option', { value: 'none', text: 'No owner', selected: ownerFilter === 'none' }),
      Object.keys(owners).map((id) => el('option', { value: id, text: (M.nodes.get(id) || {}).name || ownerNames[id] || 'Record ' + id.slice(0, 8), selected: ownerFilter === id })));
    ownerSel.addEventListener('change', () => { ownerFilter = ownerSel.value || null; applyFilter(); });
    side.appendChild(el('label', { class: 'field' }, el('span', { class: 'faint xs', text: 'Owner' }), ownerSel));
    side.appendChild(el('div', { class: 'field' }, el('span', { class: 'faint xs', text: 'Inside a course or program' }),
      combobox({ testid: 'graph-scope-filter', label: 'Inside a course or program', placeholder: 'Any', value: scopeFilter ? [scopeFilter.item] : [], source: nodeSource(['program', 'course']), onChange: async (it) => {
        if (!it) { scopeFilter = null; applyFilter(); return; }
        try { const p = await api('GET', '/nodes' + qs({ parent: it.id, limit: 1000 })); scopeFilter = { item: it, ids: new Set([it.id].concat(p.items.map((x) => x.id))) }; applyFilter(); }
        catch (e) { failToast(e); }
      } })));
    side.appendChild(el('p', { class: 'faint xs', style: 'margin-top:8px', text: canEdit
      ? 'Double-click empty space to add a record. Hover a record for its handles: drag the line handle onto another record to connect them. Double-click a record to rename it. Shift-drag to select several; Delete archives them. Press ? for every shortcut.'
      : 'Click a record to open it. Hover it for its handles: expand, focus. Press ? for every shortcut.' }));
    loadOwnerNames(Object.keys(owners).filter((id) => !M.nodes.has(id) && !ownerNames[id]));
  }
  const ownerNames = {};
  let ownerLoading = false;
  async function loadOwnerNames(ids) {
    if (ownerLoading || !ids.length) return; ownerLoading = true;
    await Promise.all(ids.slice(0, 30).map((id) => api('GET', '/nodes/' + id).then((n) => { ownerNames[id] = n.name; }).catch(() => { ownerNames[id] = 'Record ' + id.slice(0, 8); })));
    ownerLoading = false; if (S.graph === G) drawLegend();
  }
  /* A filter change: hide or show in place (no re-arrangement), unless the
     records that are drawn change shape (bundles, groups). */
  function applyFilter() { project(); drawBoxes(); afterChange(); }

  // ---------------------------------------------------------------- breadcrumbs
  const crumbName = {};
  function chainOf(id) {
    const out = []; let cur = id; const seen = new Set([id]);
    while (out.length < 8) {
      const rec = M.nodes.get(cur);
      const up = (lastStruct && (lastStruct.parent.get(cur) || lastStruct.anchor.get(cur))) || (rec && rec.scope_id) || (crumbName[cur] && crumbName[cur].scope) || null;
      if (!up || seen.has(up)) break;
      seen.add(up); out.unshift(up); cur = up;
      if (!M.nodes.has(up)) { if (crumbName[up] && crumbName[up].scope) { cur = up; continue; } break; }
    }
    return out;
  }
  function drawCrumbs() {
    const fid = focusId() || null;
    if (!fid || !M.nodes.has(fid)) { crumbs.hidden = true; return; }
    const chain = chainOf(fid);
    const missing = chain.filter((id) => !M.nodes.has(id) && !crumbName[id]);
    if (missing.length) Promise.all(missing.map((id) => api('GET', '/nodes/' + id).then((n) => { crumbName[id] = { name: n.name, type: n.type, scope: n.scope_id }; }).catch(() => { crumbName[id] = { name: '…', type: null }; })))
      .then(() => { if (S.graph === G) drawCrumbs(); });
    const item = (id, last) => { const n = M.nodes.get(id) || crumbName[id] || { name: '…' };
      return el('button', { class: 'graph-crumb' + (last ? ' current' : ''), type: 'button', 'data-testid': 'graph-crumb', title: last ? n.name : 'Go to ' + n.name, 'aria-current': last ? 'true' : null,
        onclick: () => goTo(id) }, n.type ? typeIcon(n.type, 'sm') : null, el('span', { class: 'truncate', text: n.name })); };
    const parts = [];
    chain.forEach((id) => { parts.push(item(id, false)); parts.push(el('span', { class: 'sep', 'aria-hidden': 'true' }, icon('chevron-right', 'sm'))); });
    parts.push(item(fid, true));
    crumbs.replaceChildren(...parts); crumbs.hidden = false;
  }
  /* Jump to a record: open its bundle or group if it is inside one, select it,
     centre it. Not in this graph: open its own neighbourhood. */
  function reveal(id) {
    const b = [...bundles.entries()].find(([, x]) => x.ids.includes(id));
    const g = [...foldedGroups].find((k) => (groups.get(k) || []).includes(id));
    if (b) expandedBundles.add(b[0]);
    if (g) foldedGroups.delete(g);
    if (b || g) { project(); return arrange(opt.arrange, b ? b[1].anchor : null); }
    return Promise.resolve();
  }
  async function goTo(id) {
    if (!M.nodes.has(id)) { location.hash = '#/graph/' + id; return; }
    if (hidden[(M.nodes.get(id) || {}).type]) { hidden[M.nodes.get(id).type] = false; applyFilter(); }
    await reveal(id);
    const n = cy.getElementById(id);
    cy.$(':selected').unselect(); n.select();
    cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1) }, { duration: 200, complete: () => relabel() });
  }

  // ---------------------------------------------------------------- loading, positions
  async function savedPositions() {
    try {
      const p = await api('GET', '/graph/positions' + qs({ layout: layoutId }));
      const m = {}; p.items.forEach((x) => { m[x.node_id] = { x: x.x, y: x.y }; }); return m;
    } catch (e) { return {}; }
  }
  /* Progressive expansion: one record's neighbours join the graph; the
     arrangement is recomputed with that record kept where it is on screen. */
  async function expand(id) {
    try {
      const resp = await api('GET', '/graph' + qs(params({ focus: id, depth: 1, limit: r.q.limit || 1000 })));
      const before = M.nodes.size;
      ingest(resp, id); expanded[id] = true;
      project();
      if (M.nodes.size > before) await arrange(opt.arrange === 'saved' ? 'hierarchy' : opt.arrange, id); else afterChange();
      if (resp.truncated) toast('Showing ' + resp.nodes.length + ' of ' + resp.total_nodes + ' records around this one.');
      G.loadedAt = performance.now();
    } catch (e) { failToast(e, 'Could not expand'); }
  }
  function collapse(id) {
    const gone = Object.keys(addedBy).filter((k) => addedBy[k] === id && k !== center && !expanded[k]);
    gone.forEach((k) => removeRecord(k, true)); expanded[id] = false;
    project(); afterChange();
  }
  function removeRecord(id, quiet) {
    M.nodes.delete(id); delete addedBy[id];
    [...M.edges.values()].forEach((e) => { if (e.source === id || e.target === id) { M.edges.delete(e.id); cy.getElementById(e.id).remove(); } });
    cy.getElementById(id).remove();
    if (!quiet) { project(); afterChange(); }
  }
  function removeEdgeEl(id) { M.edges.delete(id); cy.getElementById(id).remove(); }
  const pendingSave = {};
  const flushPositions = debounce(async () => {
    const items = Object.entries(pendingSave).map(([node_id, p]) => ({ node_id, x: p.x, y: p.y }));
    Object.keys(pendingSave).forEach((k) => delete pendingSave[k]);
    if (!items.length || !canEdit) return;
    try {
      for (let i = 0; i < items.length; i += 1000) await api('POST', '/graph/positions', { layout: layoutId, positions: items.slice(i, i + 1000) });
      G.savedPositions = (G.savedPositions || 0) + items.length;
    } catch (e) { failToast(e, 'Layout not saved'); }
  }, 400);
  function queueSave(nodes) { nodes.forEach((n) => { if (isRecord(n)) pendingSave[n.id()] = Object.assign({}, n.position()); }); flushPositions(); }
  async function autoLayout(save) {
    await arrange(opt.arrange === 'saved' ? 'hierarchy' : opt.arrange); fit();
    if (save) { queueSave(visibleNodes()); toast('Arranged and saved to ' + (layoutId === 'default' ? 'the shared layout' : 'this view')); }
  }
  async function resetLayout() {
    const ok = await confirmDialog({ title: 'Reset this layout?', body: 'Forgets every saved position in ' + (layoutId === 'default' ? 'the shared layout' : 'this view') + ' and arranges the graph automatically. Records do not change.', confirmLabel: 'Reset', danger: false });
    if (!ok) return;
    try { await api('DELETE', '/graph/positions' + qs({ layout: layoutId })); await autoLayout(false); toast('Layout reset'); } catch (e) { failToast(e, 'Not reset'); }
  }

  // ---------------------------------------------------------------- hints, empty state, shortcut sheet
  function showEmpty() {
    const none = !visibleNodes().length && !cy.nodes('.bundle, .collapsed').length;
    emptyBox.hidden = !none;
    if (none && !emptyBox.firstChild) emptyBox.appendChild(empty(M.nodes.size ? 'Everything is filtered out' : 'Nothing to show yet',
      M.nodes.size ? 'Turn a record type back on in the legend, or clear the filters.' : canEdit ? 'Double-click anywhere on the canvas, or press N, to add the first record.' : 'Records appear here as soon as someone adds them.',
      canEdit && !M.nodes.size ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'graph-empty-new', onclick: () => quickCreate(null) }, icon('plus', 'sm'), 'New record') : null, 'network'));
    if (!none) clear(emptyBox);
  }
  function showHint() {
    let seen = false; try { seen = localStorage.getItem('kb_graph_hint') === '1'; } catch (e) { /* storage blocked */ }
    if (seen) return;
    hint.replaceChildren(icon('mouse-pointer-2', 'sm'),
      el('span', { text: canEdit ? 'Hover a record for its handles · double-click empty space to add · drag a handle onto a record to connect · press ? for shortcuts'
        : 'Hover a record for its handles · click a bundle to open it · press ? for shortcuts' }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Got it', 'data-testid': 'graph-hint-dismiss', onclick: () => { hint.hidden = true; try { localStorage.setItem('kb_graph_hint', '1'); } catch (e) { /* ignore */ } } }));
    hint.hidden = false;
  }
  function shortcutSheet() {
    const rows = [['?', 'This list'], ['/', 'Find a record and jump to it'], ['F', 'Fit everything in view'], ['+ / −', 'Zoom in / out'],
      ['1 · 2 · 3 · 4', 'Hierarchy · Force · Radial · Saved positions'], ['O', 'Focus mode: off, 1 step, 2 steps around the selected record'],
      ['M', 'Show or hide the minimap'], ['E', 'Expand or collapse the selected record’s neighbours (or open a bundle)'], ['Esc', 'Clear the selection']];
    if (canEdit) rows.splice(4, 0, ['N', 'New record at the centre (or double-click empty space)'], ['Delete', 'Archive the selection (Undo in the message)'],
      ['Arrows', 'Move the selection (Shift: further)'], ['Double-click', 'Rename a record'], ['Drag a handle', 'Connect two records']);
    openDialog([el('h2', { text: 'Graph shortcuts' }), el('dl', { class: 'props', 'data-testid': 'graph-shortcuts' }, rows.map(([k, d]) => [el('dt', null, el('kbd', { text: k })), el('dd', { text: d })])),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Close', 'data-testid': 'graph-shortcuts-close', onclick: closeDialog }))],
      { label: 'Graph shortcuts', testid: 'graph-shortcuts-dialog' });
  }
  function toggleMini(force) {
    const off = force !== undefined ? !force : !mini.hidden;
    mini.hidden = off; miniToggle.setAttribute('aria-pressed', String(!off));
    try { localStorage.setItem('kb_graph_minimap', off ? '0' : '1'); } catch (e) { /* ignore */ }
    if (!off && mm) mm.invalidate();
  }

  // ---------------------------------------------------------------- build: fetch, then the renderer that suits the size
  info.textContent = 'Loading…';
  (async () => {
    try {
      const t0 = performance.now();
      const [, ic] = await Promise.all([fetchAll(), loadIcons(S.types.map((t) => t.icon).concat(['box']))]);
      icons = ic; G.timing = { fetch: Math.round(performance.now() - t0) };
    } catch (e) { canvas.appendChild(errorBox(e, () => { clear(v); buildGraph(v, S.route); })); info.textContent = ''; return; }
    if (S.graph !== G) return;
    // the expected drawn size decides the renderer and the large-graph settings
    const expect = Math.min(M.nodes.size, opt.unbundled ? M.nodes.size : 600);
    const useGL = r.q.renderer === 'webgl' || (r.q.renderer !== 'canvas' && expect > GL_FROM);
    const big = expect > BIG_FROM;
    cy = window.cytoscape({ container: cyBox, minZoom: 0.03, maxZoom: 3, boxSelectionEnabled: true, selectionType: 'additive',
      renderer: useGL ? { name: 'canvas', webgl: true } : undefined,
      hideEdgesOnViewport: big, textureOnViewport: big, pixelRatio: big ? 1 : 'auto',
      style: [] });
    iconsOn = expect <= ICONS_UPTO;
    Object.assign(G, { cy, webgl: !!(useGL && cy.renderer() && cy.renderer().webgl) });
    bigMode = big; applyStyle();
    mm = createMinimap(cy, mini, tok, isRecord);
    let miniOn = true; try { miniOn = localStorage.getItem('kb_graph_minimap') !== '0'; } catch (e) { /* ignore */ }
    toggleMini(miniOn);
    wire();
    groupSel.replaceChildren(...[['none', 'No groups'], ['type', 'Group by type']].concat(['program', 'course', 'domain', 'module'].filter((t) => [...M.nodes.values()].some((n) => n.type === t))
      .map((t) => [t, 'Group by ' + typeLabel(t).toLowerCase()])).map(([k, t]) => el('option', { value: k, text: t, selected: k === opt.group })));
    const t1 = performance.now(); project(); G.timing.project = Math.round(performance.now() - t1);
    const t2 = performance.now(); await arrange(opt.arrange); G.timing.arrange = Math.round(performance.now() - t2);
    fit();
    if (center) { const c = cy.getElementById(center); if (c.length && cy.zoom() < 0.5) cy.animate({ center: { eles: c }, zoom: 0.8 }, { duration: 0 }); }
    afterChange();
    showHint();
    if (truncated && center) toast('Showing ' + M.nodes.size + ' of ' + total + ' records around this one.');
    G.loadedAt = performance.now();
    loadViews();
    poll();
  })();

  // ---------------------------------------------------------------- events (wired once the canvas exists)
  let handleNode = null, dragging = null, tapTimer = null;
  const connectHandle = el('button', { class: 'graph-handle connect', type: 'button', 'data-testid': 'graph-handle', title: 'Drag onto another record to connect', 'aria-label': 'Connect from this record' }, icon('spline', 'sm'));
  const expandBtn = el('button', { class: 'graph-handle', type: 'button', 'data-testid': 'graph-expand', title: 'Expand or collapse neighbours (E)', 'aria-label': 'Expand or collapse neighbours' }, icon('plus', 'sm'));
  const focusBtn = el('button', { class: 'graph-handle', type: 'button', 'data-testid': 'graph-focus-here', title: 'Focus on this record (O)', 'aria-label': 'Focus on this record' }, icon('locate-fixed', 'sm'));
  const renameBtn = el('button', { class: 'graph-handle', type: 'button', 'data-testid': 'graph-rename', title: 'Rename (double-click)', 'aria-label': 'Rename' }, icon('pencil', 'sm'));
  const presenceTag = el('span', { class: 'graph-presence', 'data-testid': 'graph-presence' });
  handles.append(canEdit ? connectHandle : null, expandBtn, focusBtn, canEdit ? renameBtn : null, presenceTag);
  function showHandles(n) { handleNode = n; handles.hidden = !n; placeHandles(); }
  function placeHandles() {
    if (!handleNode || !handleNode.inside() || !isShown(handleNode)) { handles.hidden = true; return; }
    const b = handleNode.renderedBoundingBox({ includeLabels: false });
    handles.style.left = (b.x2 + 6) + 'px'; handles.style.top = (b.y1 - 4) + 'px'; handles.hidden = false;
    expandBtn.replaceChildren(icon(expanded[handleNode.id()] && handleNode.id() !== center ? 'minus' : 'plus', 'sm'));
    const o = others(handleNode.id());
    presenceTag.textContent = o.length ? o.map((x) => personName(x.user_id) + (x.editing ? ' is editing' : ' is viewing')).join(', ') : '';
    presenceTag.hidden = !o.length;
  }
  function toggleExpand(id) {
    if (id.startsWith('__b:')) { const k = id.slice(4), anchor = k.split('|')[0]; expandedBundles.add(k); project(); arrange(opt.arrange, anchor); return; }
    if (id.startsWith('__g:')) { foldedGroups.delete(id.slice(4)); project(); arrange(opt.arrange); return; }
    const mine = [...bundles.keys()].filter((k) => k.startsWith(id + '|'));
    if (mine.length) { mine.forEach((k) => expandedBundles.add(k)); project(); arrange(opt.arrange, id); return; }
    const opened = [...expandedBundles].filter((k) => k.startsWith(id + '|'));
    if (opened.length && !center) { opened.forEach((k) => expandedBundles.delete(k)); project(); arrange(opt.arrange, id); return; }
    if (expanded[id] && id !== center) collapse(id); else if (!expanded[id]) expand(id);
  }

  function wire() {
    cy.on('mouseover', 'node', (e) => { const n = e.target; if (n.hasClass('gbox')) return; n.addClass('hover'); n.connectedEdges().addClass('hover-near');
      if (!dragging && isRecord(n) && !n.hasClass('ghost')) showHandles(n); });
    cy.on('mouseout', 'node', (e) => { e.target.removeClass('hover'); e.target.connectedEdges().removeClass('hover-near'); });
    cy.on('select', 'node', (e) => { e.target.connectedEdges().addClass('sel-near'); if (isRecord(e.target)) showHandles(e.target); applyFocus(); drawCrumbs(); });
    cy.on('unselect', 'node', (e) => { e.target.connectedEdges().removeClass('sel-near'); applyFocus(); drawCrumbs(); });
    cy.on('position', 'node', (e) => { if (e.target === handleNode) placeHandles(); });
    cy.on('remove', 'node', (e) => { if (e.target === handleNode) showHandles(null); });
    cy.on('tap', 'node.bundle, node.collapsed', (evt) => toggleExpand(evt.target.id()));
    cy.on('tap', 'node.ghead', (evt) => { foldedGroups.add(evt.target.data('group')); project(); arrange(opt.arrange); });
    cy.on('tap', 'node', (evt) => {
      const n = evt.target; if (!isRecord(n) || n.hasClass('ghost')) return;
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
    cy.on('tap', 'edge', (evt) => { const e = evt.target; if (e.hasClass('ghost')) return;
      if (e.hasClass('bundle-edge')) { const t = e.target(); if (t.hasClass('bundle') || t.hasClass('collapsed')) toggleExpand(t.id()); return; }
      edgeInspector(e, evt.renderedPosition); });
    cy.on('dbltap', (evt) => { if (evt.target === cy) quickCreate(evt.position); });
    cy.on('dbltap', 'node', (evt) => { clearTimeout(tapTimer); const n = evt.target; if (!isRecord(n) || n.hasClass('ghost')) return; if (canEdit) rename(n); else toggleExpand(n.id()); });
    cy.on('mouseover', 'edge', (e) => e.target.addClass('hover'));
    cy.on('mouseout', 'edge', (e) => e.target.removeClass('hover'));
    cy.on('dragfree', 'node', (evt) => { const sel2 = cy.$('node:selected'); queueSave(sel2.length && evt.target.selected() ? sel2 : evt.target); refreshBoxes(); relabel(); });
    cy.on('tap', (evt) => { if (evt.target === cy) { showHandles(null); } });
    cy.on('viewport', () => { lod(); relabel(); if (handleNode) placeHandles(); });
    // connect: drag a handle onto another record
    connectHandle.addEventListener('mousedown', (ev) => {
      if (!handleNode) return;
      ev.preventDefault(); ev.stopPropagation();
      const src = handleNode, rect = cyBox.getBoundingClientRect();
      const start = toModel({ x: ev.clientX - rect.left, y: ev.clientY - rect.top });
      cy.add([{ group: 'nodes', data: { id: '__ghost', color: 'transparent', label: '', type: '' }, classes: 'ghost', position: start },
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
  }
  expandBtn.addEventListener('click', () => { if (handleNode) toggleExpand(handleNode.id()); });
  renameBtn.addEventListener('click', () => { if (handleNode) rename(handleNode); });
  focusBtn.addEventListener('click', () => { if (!handleNode) return; const id = handleNode.id(); cy.$(':selected').unselect(); cy.getElementById(id).select();
    if (!opt.focus) setQuery({ focus: '1' }, true); else applyFocus(); });

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
        const ne = normEdge(Object.assign({ type: chosen.type }, e)); ne.note = e.note || '';
        M.edges.set(ne.id, ne);
        if (cy.getElementById(ne.source).length && cy.getElementById(ne.target).length && !cy.getElementById(ne.id).length) cy.add({ group: 'edges', data: edgeData(ne) });
        project(); afterChange();
      } catch (er) { if (er.status === 202) { closeMenu(); toast('Sent for approval'); } else err.textContent = er.message; }
    } });
    popover(anchor, [el('strong', { text: 'Connect “' + a.name + '” and “' + b.name + '”' }), picker, sentence, err,
      el('div', { class: 'row' }, can('contributor') ? createBtn : null, el('span', { class: 'spacer' }), el('button', { class: 'btn sm ghost', type: 'button', text: 'Cancel', onclick: closeMenu }), submit)],
    { testid: 'graph-connect-popover', label: 'Connect two records' });
    picker.focus();
  }

  // ---------------------------------------------------------------- create
  function quickCreate(model) {
    if (!canEdit || !cy) return;
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
        const rec = normNode(Object.assign({ degree: 0 }, n)); M.nodes.set(rec.id, rec);
        addedBy[n.id] = center;
        project();
        const c = cy.getElementById(n.id); c.position(mp); c.addClass('placed'); queueSave(c);
        cy.$(':selected').unselect(); c.select();
        afterChange();
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
  /* The graph read API carries no version: fetch it once, when a rename starts,
     unless one is already known (a stale one must still conflict). */
  const versionLoads = {};
  function ensureVersion(n) {
    if (n.data('version') !== undefined && n.data('version') !== null) return Promise.resolve();
    const id = n.id();
    versionLoads[id] = versionLoads[id] || api('GET', '/nodes/' + id).then((x) => {
      const c = cy.getElementById(id); if (c.length && (c.data('version') === undefined || c.data('version') === null)) c.data('version', x.version);
      const rec = M.nodes.get(id); if (rec && rec.version === undefined) rec.version = x.version;
    }).catch(() => {}).finally(() => { delete versionLoads[id]; });
    return versionLoads[id];
  }
  function rename(n) {
    if (!canEdit) return;
    ensureVersion(n);
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
    await ensureVersion(n);
    const old = n.data('label');
    n.data('label', nm);
    try {
      const u = await api('PATCH', '/nodes/' + n.id() + (force ? '?force=1' : ''), { version: n.data('version'), name: nm });
      n.data('version', u.version); const rec = M.nodes.get(n.id()); if (rec) { rec.name = nm; rec.version = u.version; }
      toast('Renamed', { action: { label: 'Undo', fn: () => saveName(n, old, false) } });
      relabel(); drawCrumbs();
    } catch (e) {
      n.data('label', old);
      if (e.status === 409 && e.body.error === 'version_conflict') conflict(n, nm, e.body.current);
      else failToast(e, 'Not renamed');
    }
  }
  function conflict(n, mine, current) {
    const actions = el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', 'data-testid': 'conflict-reload', text: 'Use their version',
      onclick: () => { closeDialog(); n.data({ label: current.name, version: current.version }); const rec = M.nodes.get(n.id()); if (rec) { rec.name = current.name; rec.version = current.version; } } }));
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
    done.forEach((id) => { const n = cy.getElementById(id); if (n.length) G.pendingRestore.set(id, Object.assign({}, n.position())); removeRecord(id, true); });
    project(); afterChange();
    if (done.length && !quiet) toast('Archived ' + plural(done.length, 'record'), { action: { label: 'Undo', fn: () => restore('nodes', done) } });
    return done;
  }
  async function removeEdges(ids, quiet) {
    const done = [];
    for (const id of ids) {
      try { await api('POST', '/edges/' + id + '/archive', {}); done.push(id); }
      catch (e) { if (e.status === 202) toast('Sent for approval'); else failToast(e, 'Not removed'); }
    }
    done.forEach((id) => removeEdgeEl(id));
    project(); afterChange();
    if (done.length && !quiet) toast('Removed ' + plural(done.length, 'relationship'), { action: { label: 'Undo', fn: () => restore('edges', done) } });
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
    await applyChanges(rows, true);
  }
  async function deleteSelection() {
    if (!canEdit) return;
    const nodes = cy.$('node:selected').filter((n) => isRecord(n)), edges = cy.$('edge:selected').filter((e) => isRecord(e));
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

  // ---------------------------------------------------------------- edges: click -> inspector
  async function edgeInspector(e, rp) {
    if (e.data('note') === undefined) {
      try { const x = await api('GET', '/edges/' + e.id()); e.data({ note: x.note || '', version: x.version }); const rec = M.edges.get(e.id()); if (rec) { rec.note = x.note || ''; rec.version = x.version; } }
      catch (er) { e.data('note', ''); }
    }
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

  // ---------------------------------------------------------------- keyboard: the view-level hook app.js calls
  S.tableKeys = (e) => {
    if (S.graph !== G || !cy) return false;
    const k = e.key;
    if (k === '?') { shortcutSheet(); return true; }
    if (k === '/') { search.focus(); return true; }
    if (k === 'f' || k === 'F') { fit(); return true; }
    if (k === '+' || k === '=') { zoomBy(1.25); return true; }
    if (k === '-') { zoomBy(0.8); return true; }
    if (['1', '2', '3', '4'].includes(k)) { const a = ARRANGE[Number(k) - 1][0]; setQuery({ arrange: a === 'hierarchy' && layoutId === 'default' ? null : a }, true); return true; }
    if (k === 'o' || k === 'O') { const f = (opt.focus + 1) % 3; setQuery({ focus: f ? String(f) : null }, true); return true; }
    if (k === 'm' || k === 'M') { toggleMini(); return true; }
    if ((k === 'n' || k === 'N') && canEdit) { quickCreate(null); return true; }
    if ((k === 'Delete' || k === 'Backspace') && canEdit) { deleteSelection(); return true; }
    if (k === 'e' || k === 'E') { const n = cy.$('node:selected').first(); if (n.length) toggleExpand(n.id()); return true; }
    if (k === 'Escape') { cy.$(':selected').unselect(); showHandles(null); return true; }
    if (k.startsWith('Arrow') && canEdit) {
      const sel2 = cy.$('node:selected').filter(isRecord); if (!sel2.length) return false;
      const d = e.shiftKey ? 80 : 20, dx = k === 'ArrowLeft' ? -d : k === 'ArrowRight' ? d : 0, dy = k === 'ArrowUp' ? -d : k === 'ArrowDown' ? d : 0;
      sel2.positions((n) => ({ x: n.position('x') + dx, y: n.position('y') + dy })); queueSave(sel2); refreshBoxes(); if (mm) mm.invalidate(); return true;
    }
    return false;
  };

  /* The URL holds the view options; controls only change the URL, and this
     applies the difference (same view: the router does not rebuild it). */
  S.onQueryChange = (r2) => {
    if (S.graph !== G || !cy) return;
    const q = r2.q;
    const next = { depth: q.depth === '2' ? 2 : 1, arrange: q.arrange || (q.view ? 'saved' : 'hierarchy'), group: q.group || 'none',
      legacy: q.legacy === 'all' ? 'all' : 'current', archived: q.archived === '1', focus: Number(q.focus) || 0, unbundled: q.bundle === '0' || q.expand === 'all' };
    const refetch = next.legacy !== opt.legacy || next.archived !== opt.archived || (center && next.depth !== opt.depth);
    const relayout = next.arrange !== opt.arrange || next.group !== opt.group || next.unbundled !== opt.unbundled;
    Object.assign(opt, next);
    arrangeSel.value = opt.arrange; groupSel.value = opt.group; focusSel.value = String(opt.focus); if (depthSel) depthSel.value = String(opt.depth);
    if (refetch) { reload(); return; }
    if (relayout) { foldedGroups.clear(); expandedBundles.clear(); project(); arrange(opt.arrange).then(() => fit()); return; }
    applyFocus(); drawCrumbs(); relabel();
  };
  async function reload() {
    M.nodes.clear(); M.edges.clear(); expanded = {}; addedBy = {};
    cy.elements().remove();
    info.textContent = 'Loading…';
    try { await fetchAll(); } catch (e) { failToast(e); return; }
    project(); await arrange(opt.arrange); fit(); afterChange();
    G.loadedAt = performance.now();
  }

  // ---------------------------------------------------------------- search: jump to and highlight
  const runSearch = async () => {
    const q = search.value.trim().toLowerCase(); cy.nodes('.found').removeClass('found');
    if (!q) return;
    let hitId = null;
    const exact = [...M.nodes.values()].filter((n) => passes(n));
    const m = exact.find((n) => n.name.toLowerCase() === q) || exact.find((n) => n.name.toLowerCase().startsWith(q)) || exact.find((n) => n.name.toLowerCase().includes(q));
    if (m) hitId = m.id;
    if (!hitId) {
      try { const r2 = await api('GET', '/search' + qs({ q: search.value.trim(), limit: 1 }));
        const n = r2.nodes[0]; if (!n) { toast('Nothing called “' + search.value.trim() + '”'); return; }
        if (!M.nodes.has(n.id)) await expand(n.id);
        hitId = n.id;
      } catch (e) { failToast(e); return; }
    }
    await reveal(hitId);
    const hit = cy.getElementById(hitId);
    if (!hit.length) return;
    hit.addClass('found'); cy.$(':selected').unselect(); hit.select();
    cy.animate({ center: { eles: hit }, zoom: Math.max(cy.zoom(), 1) }, { duration: 200, complete: () => relabel() });
  };
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); runSearch(); } if (e.key === 'Escape') { search.value = ''; if (cy) cy.nodes('.found').removeClass('found'); cyBox.focus(); } });
  search.addEventListener('input', debounce(() => { if (!cy) return; const q = search.value.trim().toLowerCase(); cy.nodes('.found').removeClass('found');
    if (q.length > 1) visibleNodes().filter((n) => (n.data('label') || '').toLowerCase().includes(q)).addClass('found'); relabel(); }, 150));

  // ---------------------------------------------------------------- saved graph views
  async function loadViews() {
    try { G.views = (await api('GET', '/views')).items.filter((w) => w.config && w.config.kind === 'graph');
      G.views.forEach((w) => layoutSel.appendChild(el('option', { value: w.id, text: w.name + (w.shared ? ' (shared)' : ''), selected: w.id === layoutId })));
      const view = G.views.find((w) => w.id === layoutId) || null;
      if (view && view.config) { Object.assign(hidden, view.config.hidden || {}); Object.assign(edgeHidden, view.config.edgeHidden || {}); ownerFilter = view.config.owner || null; applyFilter(); }
    } catch (e) { G.views = []; }
  }
  function saveViewDialog() {
    const name = el('input', { 'aria-label': 'View name', 'data-testid': 'graph-view-name', placeholder: 'e.g. Backend course map' });
    const shared = el('input', { type: 'checkbox', checked: true, 'aria-label': 'Shared' });
    openDialog([el('h2', { text: 'Save graph view' }), el('p', { class: 'muted small', text: 'Keeps the starting record, depth, filters, grouping and the positions as they are now. Moving records later changes only this view.' }),
      name, el('label', { class: 'row small' }, shared, 'Share with everyone'),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', 'data-testid': 'graph-view-save', text: 'Save', onclick: async () => {
          if (!name.value.trim()) { name.focus(); return; }
          try {
            const w = await api('POST', '/views', { name: name.value.trim(), shared: shared.checked, config: { kind: 'graph', center, depth: opt.depth, hidden, edgeHidden, owner: ownerFilter, group: opt.group } });
            const items = visibleNodes().map((n) => ({ node_id: n.id(), x: n.position('x'), y: n.position('y') }));
            for (let i = 0; i < items.length; i += 1000) await api('POST', '/graph/positions', { layout: w.id, positions: items.slice(i, i + 1000) });
            closeDialog(); toast('Saved view “' + w.name + '”'); location.hash = '#/graph' + (center ? '/' + center : '') + qs({ depth: center ? opt.depth : null, view: w.id });
          } catch (e) { failToast(e, 'Not saved'); }
        } }))], { label: 'Save graph view' });
  }

  // ---------------------------------------------------------------- live sync
  /* The single entry point for change-feed rows (docs/CONTRACTS.md §2): the
     shared feed (live.js, B1) and this page's own poll both call it. Rows
     carry table_name + row_id (+ kind, node_ids from 0032). A record or
     relationship that was archived or deleted disappears; a renamed one updates
     in place; a new one appears when it belongs here (the whole graph: always;
     a neighbourhood: when it touches a record on screen). Type changes restyle.
     More than 200 rows at once: refetch instead of patching. */
  const seenChange = new Set();
  async function applyChanges(changes, mine) {
    if (S.graph !== G || !cy) return;
    changes = changes.filter((c) => { if (c.id === undefined || c.id === null) return true; if (seenChange.has(c.id)) return false; seenChange.add(c.id); return true; });
    if (!changes.length) return;
    G.feed = (G.feed || 0) + 1;            // batches received (tests and diagnostics)
    changes.forEach((c) => { if (c.id > head) head = c.id; });
    if (changes.length > 200) { await reload(); return; }
    if (changes.some((c) => /^(type|reltype)\./.test(c.kind || '') || c.table_name === 'node_types' || c.table_name === 'edge_types' || c.table_name === 'edge_type_rules')) {
      try { const t = await api('GET', '/types'); S.types = t.node_types; S.edgeTypes = t.edge_types; S.typeByKey = {}; S.types.forEach((x) => { S.typeByKey[x.key] = x; });
        L = looks(meta()); icons = Object.assign(icons, await loadIcons(S.types.map((x) => x.icon))); applyStyle(); } catch (e) { /* next change retries */ }
    }
    // A layout save moves records only where saved positions are what is shown.
    const moved = [...new Set(changes.filter((c) => c.kind === 'layout.update').flatMap((c) => c.node_ids || []))].filter((id) => cy.getElementById(id).length);
    if (moved.length && opt.arrange === 'saved') {
      const pos = await savedPositions();
      cy.batch(() => moved.forEach((id) => { if (pos[id]) cy.getElementById(id).position(pos[id]); }));
    }
    const nodeIds = [...new Set(changes.filter((c) => c.table_name === 'nodes').map((c) => c.row_id))];
    const edgeIds = [...new Set(changes.filter((c) => c.table_name === 'edges').map((c) => c.row_id))];
    let added = false; const newIds = new Set();
    for (const id of nodeIds) {
      try {
        const n = await api('GET', '/nodes/' + id);
        if ((n.archived_at && !opt.archived) || (n.is_legacy && opt.legacy !== 'all')) { if (M.nodes.has(id) || cy.getElementById(id).length) removeRecord(id, true); continue; }
        const rec = normNode(n);
        if (M.nodes.has(id)) { rec.degree = M.nodes.get(id).degree; M.nodes.set(id, rec); const c = cy.getElementById(id); if (c.length) c.data(Object.assign({}, c.data(), { label: rec.name, version: rec.version, owner: rec.owner_record_id })); }
        else if (G.pendingRestore && G.pendingRestore.has(id)) { M.nodes.set(id, rec); newIds.add(id); added = true; }
        else if (!center) { M.nodes.set(id, rec); newIds.add(id); added = true; }
        else if (cy.getElementById(id).length) { const c = cy.getElementById(id); c.data(Object.assign({}, c.data(), { label: rec.name, version: rec.version })); }
      } catch (e) { if (e.status === 404) removeRecord(id, true); }
    }
    for (const id of edgeIds) {
      try {
        const e0 = await api('GET', '/edges/' + id);
        const e = normEdge(e0); e.note = e0.note || '';
        if (e.archived && !opt.archived) { removeEdgeEl(id); continue; }
        if (M.edges.has(id)) { M.edges.set(id, e); const c = cy.getElementById(id); if (c.length) c.data({ note: e.note, version: e.version }); continue; }
        const hasS = M.nodes.has(e.source), hasT = M.nodes.has(e.target);
        if (!hasS && !hasT) continue;                   // not about anything on screen
        for (const other of [hasS ? null : e.source, hasT ? null : e.target]) {
          if (!other) continue;
          try { const o = await api('GET', '/nodes/' + other); if (!o.archived_at && (!o.is_legacy || opt.legacy === 'all')) { M.nodes.set(o.id, normNode(o)); newIds.add(o.id); addedBy[o.id] = hasS ? e.source : e.target; added = true; } } catch (er) { /* gone */ }
        }
        if (M.nodes.has(e.source) && M.nodes.has(e.target)) { M.edges.set(id, e); added = true; }
      } catch (er) { if (er.status === 404) removeEdgeEl(id); }
    }
    project();
    const fresh = cy.nodes().filter((n) => newIds.has(n.id()) && !n.hasClass('placed'));
    if (fresh.length) {
      // newcomers go where they were (Undo) or beside a neighbour; the rest of the canvas stays put
      fresh.forEach((n) => {
        const back = G.pendingRestore && G.pendingRestore.get(n.id());
        if (back) { n.position(back); G.pendingRestore.delete(n.id()); }
        else { const nb = n.neighborhood('node.placed').first(); const p = nb.length ? nb.position() : toModel({ x: cy.width() / 2, y: cy.height() / 2 });
          n.position({ x: p.x + (Math.random() - 0.5) * 220, y: p.y + 120 }); }
        n.addClass('placed');
      });
      refreshBoxes();
    }
    void added; void mine;
    afterChange();
    G.synced = (G.synced || 0) + 1;
  }
  G.applyChanges = applyChanges;
  const offLive = onLiveChange((theirs) => { if (S.graph === G) applyChanges(theirs.filter((c) => c.table_name !== 'audit_log')); });
  /* Fallback: this page follows /changes from the graph's `head` itself, so it
     is live even where the shared feed is not running. */
  let pollTimer = null;
  async function poll() {
    if (S.graph !== G) return;
    try {
      const x = await api('GET', '/changes?since=' + encodeURIComponent(String(head || 0)));
      const rows = x.changes.filter((c) => !(c.actor_id === (S.me || {}).user_id && humanActor(c)));
      if (x.cursor > head) head = x.cursor;
      x.changes.forEach((c) => { if (!rows.includes(c)) seenChange.add(c.id); });
      if (rows.length) await applyChanges(rows);
    } catch (e) { /* the next poll retries */ }
    if (S.graph === G) pollTimer = setTimeout(poll, document.hidden ? POLL_MS * 3 : POLL_MS);
  }
  void pollTimer;
  function markPresence() {
    if (!cy) return;
    cy.batch(() => cy.nodes().filter(isRecord).forEach((n) => n.toggleClass('presence', others(n.id()).some((o) => o.editing))));
    if (handleNode) placeHandles();
  }
  const offPresence = onPresence(() => { if (S.graph === G) markPresence(); });
  // Leaving the page (router leave hook): unsubscribe, stop polling, free the canvas (run 6, F7; B5's heap finding).
  S.onLeave = () => {
    offLive(); offPresence();
    if (pollTimer) clearTimeout(pollTimer);
    if (S.graph === G) S.graph = null;
    try { if (cy) cy.destroy(); } catch (e) { /* already gone */ }
    if (window.__kbGraph === G) window.__kbGraph = null;
  };
  G.reload = reload;
  G.expand = (id) => expand(id);
  G.connect = (a, b) => connectPair(ref(cy.getElementById(a)), ref(cy.getElementById(b)), cy.getElementById(b).renderedPosition());
  G.refresh = () => applyChanges([...M.nodes.keys()].map((id) => ({ table_name: 'nodes', row_id: id })));
  G.renderedPosition = (id) => { const rect = cyBox.getBoundingClientRect(), q = cy.getElementById(id).renderedPosition(); return [rect.left + q.x, rect.top + q.y]; };
  G.labelBoxes = () => labelBoxes(cy);
  G.declutter = () => (G.labels = declutter(cy));
  G.arrangement = () => opt.arrange;
}
