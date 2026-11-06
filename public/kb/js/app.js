/* Boot, sidebar, router, ⌘K palette, keyboard shortcuts, live updates. */
import { S, el, add, $, $$, clear, icon, typeIcon, typeLabel, api, toast, failToast, loadSession, setSignedOutHandler, parseHash,
  setQuery, avatar, personName, menu, debounce, can, qs, closeDialog, closeMenu } from './core.js';
import { startLive, onLiveChange } from './live.js';
import { openRecordPanel, closePanel, renderFullRecord } from './detail.js';
import { openRecordForm } from './form.js';
import { viewDashboard } from './views/dashboard.js';
import { viewRecords } from './views/records.js';
import { viewResources } from './views/resources.js';
import { viewGraph } from './views/graph.js';
import { viewOutline } from './views/outline.js';
import { viewQuality } from './views/quality.js';
import { viewApprovals } from './views/approvals.js';
import { viewArchived } from './views/archived.js';
import { viewSettings } from './views/settings.js';
import { viewGuide } from './views/guide.js';
import { viewActivity } from './views/activity.js';
import { viewTeaching, viewTimeline } from './views/teaching.js';
import { aliasTarget } from './aliases.js';

const ROUTES = {
  '': viewDashboard, records: viewRecords, programs: viewRecords, courses: viewRecords, resources: viewResources,
  outline: viewOutline, graph: viewGraph, quality: viewQuality, approvals: viewApprovals, proposals: viewApprovals,
  archived: viewArchived, settings: viewSettings, guide: viewGuide, r: renderFullRecord, activity: viewActivity,
  teaching: viewTeaching, timeline: viewTimeline,
};
/* Page template widths (B1): tables and the graph use the full width; reading
   content is centred at a readable measure; everything else is contained. */
const LAYOUT = { records: 'full', programs: 'full', courses: 'full', resources: 'full', graph: 'full', teaching: 'full', timeline: 'full', guide: 'reading', r: 'reading' };

// ------------------------------------------------------------------ theme
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem('kb_theme', t || 'system'); } catch (e) { /* ignore */ }
}
function currentTheme() { try { return localStorage.getItem('kb_theme') || 'system'; } catch (e) { return 'system'; } }
applyTheme(currentTheme());

// ------------------------------------------------------------------ boot
/* "New record" from the sidebar or the c key starts where you are: with a
   record open (or a graph centred on one), the form is placed under it and
   picks the first type that may live there. */
export function newRecordFromContext(extra) {
  const r = S.route || { path: [''] };
  let n = S.panel && S.panel.node ? S.panel.node : null;
  if (!n && r.path[0] === 'graph' && r.path[1] && S.graph) {
    const c = S.graph.cy.getElementById(r.path[1]);
    if (c && c.length) n = { id: c.id(), name: c.data('label'), type: c.data('type') };
  }
  const o = Object.assign({}, extra || {});
  if (r.path[0] === 'courses' && !o.type && !n) o.type = 'course';
  if (r.path[0] === 'programs' && !o.type && !n) o.type = 'program';
  if (n && !o.parents) {
    const child = S.types.find((t) => (t.allowed_parents || []).includes(n.type));
    if (child) { o.type = o.type || child.key; o.parents = [{ id: n.id, label: n.name, type: n.type, icon: typeIcon(n.type) }]; }
  }
  openRecordForm(o);
}

function showGate(msg) { $('#gate-msg').textContent = msg; $('#gate').hidden = false; }
setSignedOutHandler(showGate);

export async function loadTypes() {
  const t = await api('GET', '/types');
  S.types = t.node_types; S.edgeTypes = t.edge_types; S.linkKinds = t.link_kinds;
  S.resourceKinds = t.resource_kinds; S.fieldKinds = t.field_kinds; S.palette = t.palette;
  S.typeByKey = {}; S.types.forEach((x) => { S.typeByKey[x.key] = x; });
}
export async function loadPeople() {
  try { S.people = (await api('GET', '/people')).items; } catch (e) { S.people = []; }
  S.personById = {}; S.people.forEach((p) => { S.personById[p.user_id] = p; });
}

async function boot() {
  S.session = loadSession();
  if (!S.session || !S.session.access_token) { showGate('Sign in with your Interview Kickstart Google account to continue.'); return; }
  try {
    // /types and /people do not depend on /me: one round trip instead of two
    // before the first page can render (2026-11-07, sign-in timing).
    const rest = Promise.allSettled([loadTypes(), loadPeople()]);
    S.me = await api('GET', '/me');
    if (S.me.role === 'none') { showGate('Your account has no access to the knowledge base yet. Ask an admin to grant you a role.'); return; }
    const [types] = await rest;
    if (types.status === 'rejected') throw types.reason;
  } catch (e) { if (e.status !== 401) showGate('The knowledge base is unavailable: ' + e.message); return; }
  document.body.dataset.role = S.me.role;
  try { if (localStorage.getItem('kb_sidebar') === 'collapsed') $('#app').classList.add('collapsed'); } catch (e) { /* ignore */ }
  renderSidebar();
  refreshCounts();
  syncBanner();
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', route);
  document.addEventListener('keydown', globalKeys);
  route();
  startLive();
  onLiveChange(debounce(refreshCounts, 1500));
}

// ------------------------------------------------------------------ sidebar
/* Every page, for the palette's "Go to" and the browser tab's title (run 6, F2). */
const PAGES = [['Dashboard', ''], ['All records', 'records'], ['Programs', 'programs'], ['Courses', 'courses'], ['Links', 'resources'],
  ['Outline', 'outline'], ['Graph', 'graph'], ['Who teaches what', 'teaching'], ['Program timeline', 'timeline'],
  ['Data quality', 'quality'], ['Approvals', 'approvals'], ['Activity', 'activity', 'editor'], ['Archived', 'archived'],
  ['Guide', 'guide'], ['Settings', 'settings'], ['People', 'settings?tab=people', 'admin'], ['Members', 'settings?tab=members', 'admin'],
  ['Sync', 'settings?tab=sync', 'admin']];
const NAV = [
  ['Workspace', [['', 'Dashboard', 'layout-dashboard'], ['records', 'All records', 'list', 'records'], ['outline', 'Outline', 'list-tree'], ['graph', 'Graph', 'network']]],
  ['Browse', [['programs', 'Programs', 'graduation-cap', 'program'], ['courses', 'Courses', 'book-open', 'course'], ['resources', 'Links', 'link', 'resources'], ['teaching', 'Who teaches what', 'users'], ['timeline', 'Program timeline', 'calendar-days']]],
  ['Maintain', [['quality', 'Data quality', 'shield-check', 'attention'], ['approvals', 'Approvals', 'circle-check', 'pending'], ['activity', 'Activity', 'history', null, 'editor'], ['archived', 'Archived', 'archive', 'archived']]],
];
function renderSidebar() {
  const sb = clear($('#sidebar'));
  const collapse = el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Collapse sidebar', title: 'Collapse sidebar',
    onclick: () => { const c = $('#app').classList.toggle('collapsed'); try { localStorage.setItem('kb_sidebar', c ? 'collapsed' : 'open'); } catch (e) { /* ignore */ } } }, icon('panel-left'));
  // Admins switch to the map from the TOP (owner, 2026-11-07). The link comes from
  // /me, which includes it only for a role the server verified (B5); nothing here
  // decides who is an admin, and every route still checks the role itself.
  const toMap = (S.me.admin_links || []).map((l) => el('a', { class: 'btn primary sm brand-map', href: l.href, 'data-testid': l.testid + '-nav', title: l.label, 'aria-label': l.label },
    icon('arrow-left'), el('span', { class: 'label-text', text: 'Map' })));
  sb.appendChild(el('div', { class: 'brand' }, el('span', { class: 'brand-mark', text: 'IK' }), el('span', { class: 'label-text truncate', text: 'Knowledge Base' }), el('span', { class: 'spacer label-text' }), toMap, collapse));
  sb.appendChild(el('button', { class: 'nav-search', type: 'button', 'data-testid': 'open-palette', onclick: openPalette, 'aria-label': 'Search or run a command' },
    icon('search'), el('span', { class: 'label-text', text: 'Search' }), el('span', { class: 'spacer' }), el('kbd', { text: /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K' })));
  if (can('contributor')) sb.appendChild(el('button', { class: 'btn primary w-full mb-1', type: 'button', 'data-testid': 'new-record',
    onclick: () => newRecordFromContext() }, icon('plus'), el('span', { class: 'label-text', text: 'New record' })));
  const nav = el('nav', { class: 'nav', id: 'nav' });
  for (const [group, items] of NAV) {
    const g = el('div', { class: 'nav-group' }, el('div', { class: 'nav-group-label', text: group }));
    for (const [path, label, ic, countKey, minRole] of items) {
      if (minRole && !can(minRole)) continue;
      g.appendChild(el('a', { href: '#/' + path, 'data-nav': path || 'dashboard', title: label }, icon(ic), el('span', { class: 'label-text', text: label }),
        countKey ? el('span', { class: 'count', 'data-count': countKey }) : null));
    }
    nav.appendChild(g);
  }
  sb.appendChild(nav);
  const user = el('button', { class: 'user-btn', type: 'button', 'data-testid': 'whoami', onclick: (e) => userMenu(e.currentTarget) },
    avatar(S.me.user_id, 'lg'), el('span', { class: 'label-text col gap-0 min-w-0' },
      el('span', { class: 'truncate', text: (S.session.user && S.session.user.email) || personName(S.me.user_id) }),
      el('span', { class: 'faint xs', text: 'Role: ' + S.me.role })));
  // The local demo server's badge (eval/ only): kept across sidebar re-renders.
  const badge = S.demoBadge = document.getElementById('demo-badge-slot') || S.demoBadge;
  sb.appendChild(el('div', { class: 'sidebar-foot nav' },
    el('a', { href: '#/guide', 'data-nav': 'guide', title: 'Guide' }, icon('circle-help'), el('span', { class: 'label-text', text: 'Guide' })),
    el('a', { href: '#/settings', 'data-nav': 'settings', title: 'Settings' }, icon('settings'), el('span', { class: 'label-text', text: 'Settings' })),
    el('div', { class: 'sidebar-slot', id: 'sidebar-slot' }),
    user));
  if (badge) $('#sidebar-slot').appendChild(badge);
}
function userMenu(anchor) {
  const t = currentTheme();
  menu(anchor, [
    { header: true, label: 'Theme' },
    { label: 'System', checked: t === 'system', icon: 'monitor', fn: () => applyTheme('system'), testid: 'theme-system' },
    { label: 'Light', checked: t === 'light', icon: 'sun', fn: () => applyTheme('light'), testid: 'theme-light' },
    { label: 'Dark', checked: t === 'dark', icon: 'moon', fn: () => applyTheme('dark'), testid: 'theme-dark' },
    '-',
    { label: 'Keyboard shortcuts', icon: 'keyboard', fn: shortcutsDialog },
    ...(S.me.admin_links || []).flatMap((l) => ['-', { label: l.label, icon: 'arrow-left', testid: l.testid, fn: () => { location.href = l.href; } }]),
  ]);
}
/* Admins: a banner while the last sync run failed (Settings -> Sync has the log). */
async function syncBanner() {
  if (!can('admin')) return;
  try {
    const d = await api('GET', '/sync');
    const old = document.getElementById('sync-banner'); if (old) old.remove();
    if (!d.failing) return;
    const b = el('div', { id: 'sync-banner', class: 'note-box warn row', role: 'alert', 'data-testid': 'sync-banner' },
      icon('triangle-alert', 'sm'), el('span', { class: 'spacer', text: 'The last sync from the original site failed. Edits here are safe; new source changes are not coming in.' }),
      el('a', { class: 'btn sm', href: '#/settings?tab=sync', text: 'Open the sync log' }));
    const main = $('#main') || document.body; main.prepend(b);
  } catch (e) { /* the banner is decoration */ }
}

export async function refreshCounts() {
  try {
    const d = await api('GET', '/counts');
    const byType = {}; d.counts.forEach((c) => { byType[c.key] = c.n; });
    const vals = { records: d.totals.nodes, program: byType.program, course: byType.course, resources: d.totals.resources,
      pending: d.totals.pending_proposals || '', archived: d.totals.archived || '',
      attention: d.attention.total || '' };
    $$('[data-count]').forEach((c) => { c.textContent = vals[c.dataset.count] === undefined ? '' : vals[c.dataset.count]; });
    S.counts = vals;
  } catch (e) { /* counts are decoration */ }
}

// ------------------------------------------------------------------ router
let lastView = null;
export function rerender() { lastView = null; route(); }
export function route() {
  closeMenu();
  const r = parseHash();
  // An old, bookmarked address goes to its page (F6, aliases.js); replace() keeps it out of the history.
  const moved = aliasTarget(r.path, r.q);
  if (moved) { location.replace(moved); return; }
  S.route = r;
  const key = r.path[0] || '';
  $$('#sidebar [data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === (key || 'dashboard') ||
    (key === 'proposals' && a.dataset.nav === 'approvals')));
  const viewKey = key + '|' + (r.path[1] || '');
  const fn = ROUTES[key];
  const v = $('#view');
  const page = PAGES.find(([, p]) => p === key) || (key === 'proposals' && ['Approvals']) || (key === 'r' && ['Record']);
  document.title = (page ? page[0] + ' · ' : '') + 'IK Knowledge Base';
  if (viewKey !== lastView || r.q.__force) {
    lastView = viewKey;
    // The view being left releases what it holds (run 6, F7: the graph's listeners, poll and canvas).
    if (S.onLeave) { const f = S.onLeave; S.onLeave = null; try { f(); } catch (e) { console.warn('leaving a view', e); } }
    v.dataset.layout = LAYOUT[key] || 'contained';
    S.listReload = null; S.onSelect = null; S.onQueryChange = null; S.tableKeys = null;
    if (S.panel && S.panel.full) S.panel = null;          // leaving a full-page record
    clear(v); v.scrollTop = 0;
    if (!fn) v.appendChild(el('div', { class: 'page-body' }, el('div', { class: 'empty' }, el('h2', { text: 'Page not found' }), el('p', { text: 'That address does not match anything here.' }), el('a', { class: 'btn', href: '#/' , text: 'Go to the dashboard' }))));
    else fn(v, r);
  } else if (S.onQueryChange) S.onQueryChange(r);
  if (key !== 'r') {
    if (r.q.open) openRecordPanel(r.q.open);
    else if (r.q.res) openRecordPanel(r.q.res, 'resource');
    else closePanel(true);
  } else {
    // A full-page record owns S.panel; only the side panel element is hidden.
    const p = $('#panel'); p.hidden = true; clear(p); $('#app').classList.remove('has-panel');
  }
}

// ------------------------------------------------------------------ palette
function openPalette(prefill) {
  closeDialog(); closeMenu();
  const input = el('input', { 'data-testid': 'palette-input', placeholder: 'Search records and resources, or type a command…', autocomplete: 'off', 'aria-label': 'Search', value: typeof prefill === 'string' ? prefill : '' });
  const list = el('ul', { role: 'listbox', 'data-testid': 'palette-results' });
  const pal = el('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Command palette' }, input, list,
    el('div', { class: 'palette-foot' }, el('span', null, el('kbd', { text: '↑↓' }), ' move'), el('span', null, el('kbd', { text: 'Enter' }), ' open'), el('span', null, el('kbd', { text: 'Esc' }), ' close')));
  const ov = el('div', { class: 'overlay', id: 'dialog-overlay', onmousedown: (e) => { if (e.target === ov) ov.remove(); } }, pal);
  document.body.appendChild(ov);
  let items = [], active = 0;
  const close = () => ov.remove();
  function draw() {
    clear(list);
    let group = null;
    items.forEach((it, i) => {
      if (it.group !== group) { group = it.group; list.appendChild(el('li', { class: 'group', text: group })); }
      list.appendChild(el('li', { class: i === active ? 'active' : '', role: 'option', 'data-testid': it.testid || 'palette-item',
        onmousedown: (e) => { e.preventDefault(); close(); it.fn(); } }, it.icon, el('span', { class: 'truncate', text: it.label }), it.sub ? el('span', { class: 'faint small truncate', text: it.sub }) : null));
    });
  }
  const commands = () => {
    const c = [];
    if (can('contributor')) S.types.forEach((t) => c.push({ group: 'Create', label: 'New ' + t.label.toLowerCase(), icon: typeIcon(t.key), fn: () => openRecordForm({ type: t.key, name: input.value.trim() }), testid: 'palette-create-' + t.key }));
    PAGES.filter(([, , role]) => !role || can(role))
      .forEach(([l, p]) => c.push({ group: 'Go to', label: l, icon: icon('arrow-right'), fn: () => { location.hash = '#/' + p; }, testid: 'palette-go-' + (p.split('?')[0] || 'dashboard') }));
    c.push({ group: 'Commands', label: 'Toggle dark mode', icon: icon('moon'), fn: () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark') });
    return c;
  };
  let searched = '';
  const runSearch = async () => {
    const q = input.value.trim();
    searched = q;
    const cmds = commands().filter((c) => !q || c.label.toLowerCase().includes(q.toLowerCase()) || c.group === 'Create');
    if (!q) { items = cmds.filter((c) => c.group !== 'Create').concat(cmds.filter((c) => c.group === 'Create').slice(0, 3)); active = 0; draw(); return; }
    try {
      const r = await api('GET', '/search' + qs({ q, limit: 12 }));
      const found = r.nodes.map((n) => ({ group: 'Records', label: n.name, sub: typeLabel(n.type) + (n.scope_name ? ' · ' + n.scope_name : ''), icon: typeIcon(n.type),
        fn: () => setQuery({ open: n.id, res: null }), testid: 'palette-node' }))
        .concat((r.resources || []).map((x) => ({ group: 'Resources', label: x.title, sub: x.url, icon: icon('link'), fn: () => setQuery({ res: x.id, open: null }), testid: 'palette-resource' })));
      // An exact page name ("Settings", "Links") goes to that page first, never "Create 'Settings'" (run 6, F2).
      const exact = cmds.filter((c) => c.group === 'Go to' && c.label.toLowerCase() === q.toLowerCase());
      items = exact.concat(found).concat(cmds.filter((c) => c.group === 'Create').map((c) => Object.assign({}, c, { label: c.label + ' “' + q + '”' }))).concat(cmds.filter((c) => c.group !== 'Create' && !exact.includes(c)));
    } catch (e) { items = cmds; }
    active = 0; draw();
  };
  const search = debounce(runSearch, 120);
  input.addEventListener('input', search);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(items.length - 1, active + 1); draw(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(0, active - 1); draw(); }
    if (e.key === 'Enter') {
      e.preventDefault();
      // Enter right after typing must act on the results for what was typed.
      const go = () => { if (items[active]) { close(); items[active].fn(); } };
      if (searched !== input.value.trim()) runSearch().then(go); else go();
    }
  });
  input.focus(); runSearch();
}

function shortcutsDialog() {
  const rows = [['⌘K / Ctrl K', 'Search or run a command'], ['/', 'Focus the table search'], ['c', 'New record'], ['j / k', 'Move down / up in a table'],
    ['Enter', 'Open the highlighted record'], ['x', 'Select the highlighted row'], ['e', 'Edit the open record'], ['Esc', 'Close a panel, sheet or dialog'], ['⌘/Ctrl Enter', 'Save a form']];
  import('./core.js').then(({ openDialog }) => openDialog([el('h2', { text: 'Keyboard shortcuts' }),
    el('dl', { class: 'props' }, rows.map(([k, d]) => [el('dt', null, el('kbd', { text: k })), el('dd', { text: d })]))], { label: 'Keyboard shortcuts' }));
}

function globalKeys(e) {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
  if ($('#dialog-overlay') || $('.sheet')) return;
  if (e.key === 'Escape' && S.panel) { e.preventDefault(); closePanel(); return; }
  if (e.key === 'c' && can('contributor')) { e.preventDefault(); newRecordFromContext(); return; }
  if (e.key === 'e' && S.panel && S.panel.kind === 'node' && S.panel.node && can('contributor')) { e.preventDefault(); openRecordForm({ edit: S.panel.node }); return; }
  if (S.tableKeys && S.tableKeys(e)) e.preventDefault();
}

export { openPalette };
boot();
