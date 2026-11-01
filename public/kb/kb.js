/* KB workspace. Vanilla JS, no build step (the repo has none, and the CSP is
   script-src 'self'). Every value from the API is rendered with textContent via
   el(); innerHTML is never given data. */
(function () {
  'use strict';

  var SESSION_KEY = 'np_session';
  var POLL_MS = 4000;
  var S = { session: null, me: null, types: [], edgeTypes: [], typeByKey: {}, route: null,
            panel: null, feedCursor: null, feedFails: 0, listReload: null };

  // ------------------------------------------------------------------ dom
  function el(tag, props) {
    var n = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v === undefined || v === null || v === false) return;
      if (k === 'text') n.textContent = v;
      else if (k === 'class') n.className = v;
      else if (k === 'style') n.setAttribute('style', v);
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.keys(v).forEach(function (d) { n.dataset[d] = v[d]; });
      else if (v === true) n.setAttribute(k, '');
      else n.setAttribute(k, v);
    });
    for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
    return n;
  }
  function add(n, c) {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(n, x); }); return; }
    n.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  }
  function $(s, r) { return (r || document).querySelector(s); }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
  function debounce(fn, ms) { var t; return function () { var a = arguments, me = this; clearTimeout(t); t = setTimeout(function () { fn.apply(me, a); }, ms); }; }
  function ago(ts) {
    if (!ts) return '';
    var s = (Date.now() - new Date(ts).getTime()) / 1000;
    if (s < 45) return 'just now'; if (s < 3600) return Math.round(s / 60) + 'm ago';
    if (s < 86400) return Math.round(s / 3600) + 'h ago'; return new Date(ts).toLocaleDateString();
  }
  var ROLE_RANK = { none: 0, viewer: 1, contributor: 2, editor: 3, admin: 4 };
  function can(role) { return S.me && ROLE_RANK[S.me.role] >= ROLE_RANK[role]; }
  function typePill(key) {
    var t = S.typeByKey[key] || { label: key, color: '#64748b' };
    return el('span', { class: 'pill', 'data-type': key }, el('span', { class: 'dot', style: 'background:' + t.color }), t.label);
  }
  function statusPill(n) {
    if (n.archived_at) return el('span', { class: 'pill danger' }, 'archived');
    if (n.status === 'draft') return el('span', { class: 'pill warn' }, 'draft');
    return null;
  }
  function actorLabel(a) {
    if (a.actor_type === 'ai') return 'AI assistant';
    if (a.actor_type === 'import') return 'Sheets import';
    if (a.actor_type === 'system') return 'System';
    return S.me && a.actor_id === S.me.user_id ? 'You' : 'A teammate';
  }

  // ------------------------------------------------------------------ api
  function ApiError(status, body) { this.status = status; this.body = body || {}; this.message = (body && (body.message || body.reason || body.error)) || ('HTTP ' + status); }
  function loadSession() { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch (e) { return null; } }
  function saveSession(s) { S.session = s; try { localStorage.setItem(SESSION_KEY, JSON.stringify(s)); } catch (e) { /* storage blocked */ } }
  async function refreshSession() {
    if (!S.session || !S.session.refresh_token) return false;
    try {
      var r = await fetch('/api/session', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action: 'refresh', refresh_token: S.session.refresh_token }) });
      if (!r.ok) return false;
      saveSession(await r.json()); return true;
    } catch (e) { return false; }
  }
  async function api(method, path, body, retried) {
    var opts = { method: method, headers: {} };
    if (S.session) opts.headers.authorization = 'Bearer ' + S.session.access_token;
    if (body !== undefined) { opts.headers['content-type'] = 'application/json'; opts.body = JSON.stringify(body); }
    var r;
    try { r = await fetch('/api/kb' + path, opts); }
    catch (e) { throw new ApiError(0, { message: 'Network error — check your connection and try again.' }); }
    if (r.status === 401 && !retried) {
      if (await refreshSession()) return api(method, path, body, true);
      showGate('Your session has expired. Sign in again to continue.');
      throw new ApiError(401, { message: 'signed out' });
    }
    var data = await r.json().catch(function () { return {}; });
    if (r.status >= 400 || r.status === 202) throw new ApiError(r.status, data);
    return data;
  }
  function qs(o) {
    var p = []; Object.keys(o).forEach(function (k) { if (o[k] !== undefined && o[k] !== null && o[k] !== '') p.push(encodeURIComponent(k) + '=' + encodeURIComponent(o[k])); });
    return p.length ? '?' + p.join('&') : '';
  }

  // ------------------------------------------------------------------ feedback
  function toast(msg, opts) {
    opts = opts || {};
    var t = el('div', { class: 'toast' + (opts.error ? ' err' : ''), role: opts.error ? 'alert' : 'status', 'data-testid': 'toast' }, el('span', { text: msg }));
    if (opts.action) t.appendChild(el('button', { type: 'button', text: opts.action.label, onclick: function () { opts.action.fn(); t.remove(); } }));
    $('#toasts').appendChild(t);
    setTimeout(function () { t.remove(); }, opts.ms || (opts.error ? 7000 : 3500));
  }
  function failToast(e, what) {
    if (e && e.status === 401) return;
    toast((what ? what + ': ' : '') + (e && e.message || 'Something went wrong'), { error: true });
  }
  var lastFocus = null;
  function openModal(content, opts) {
    lastFocus = document.activeElement;
    var box = clear($('#modal-box'));
    box.setAttribute('aria-label', (opts && opts.label) || 'Dialog');
    box.appendChild(content);
    $('#modal').hidden = false;
    var f = box.querySelector('[autofocus], input, select, textarea, button.primary, button');
    if (f) f.focus();
  }
  function closeModal() { $('#modal').hidden = true; clear($('#modal-box')); if (lastFocus && lastFocus.focus) lastFocus.focus(); }
  function confirmDialog(o) {
    return new Promise(function (resolve) {
      var done = function (v) { closeModal(); resolve(v); };
      openModal(el('div', { 'data-testid': 'confirm-dialog' },
        el('h2', { text: o.title }), o.body ? (typeof o.body === 'string' ? el('p', { class: 'muted', text: o.body }) : o.body) : null,
        el('div', { class: 'actions' },
          el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: function () { done(false); } }),
          el('button', { class: 'btn ' + (o.danger ? 'danger solid' : 'primary'), type: 'button', 'data-testid': 'confirm-ok', text: o.confirmLabel || 'Confirm', onclick: function () { done(true); } }))),
        { label: o.title });
    });
  }
  function skeleton(n) { var w = el('div'); for (var i = 0; i < (n || 6); i++) w.appendChild(el('div', { class: 'skeleton' + (i === 0 ? ' tall' : '') })); return w; }
  function empty(title, body, action) { return el('div', { class: 'empty', 'data-testid': 'empty' }, el('h2', { text: title }), el('p', { text: body }), action || null); }
  function errorBox(e, retry) {
    return el('div', { class: 'error-box', role: 'alert' }, el('strong', { text: 'Could not load this. ' }), e.message || '',
      retry ? el('div', { style: 'margin-top:8px' }, el('button', { class: 'btn sm', type: 'button', text: 'Try again', onclick: retry })) : null);
  }
  function showGate(msg) { $('#gate-msg').textContent = msg; $('#gate').hidden = false; }

  // ------------------------------------------------------------------ boot
  async function boot() {
    S.session = loadSession();
    if (!S.session || !S.session.access_token) { showGate('Sign in with your Interview Kickstart Google account to continue.'); return; }
    try {
      var res = await Promise.all([api('GET', '/me'), api('GET', '/types')]);
      S.me = res[0]; setTypes(res[1]);
    } catch (e) { if (e.status !== 401) showGate('The knowledge base is unavailable: ' + e.message); return; }
    if (S.me.role === 'none') { showGate('Your account has no access to the knowledge base yet. Ask an admin to grant you a role.'); return; }
    document.body.dataset.role = S.me.role;
    $('#whoami').textContent = ((S.session.user && S.session.user.email) || 'Signed in') + ' · ' + S.me.role;
    $('#palette-kbd').textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K';
    window.addEventListener('hashchange', route);
    document.addEventListener('keydown', globalKeys);
    $('#open-palette').addEventListener('click', openPalette);
    $('#modal').addEventListener('mousedown', function (e) { if (e.target.id === 'modal') closeModal(); });
    $('#palette').addEventListener('mousedown', function (e) { if (e.target.id === 'palette') closePalette(); });
    route();
    startFeed();
    refreshPending();
  }
  function setTypes(t) {
    S.types = t.node_types; S.edgeTypes = t.edge_types; S.typeByKey = {};
    S.types.forEach(function (x) { S.typeByKey[x.key] = x; });
  }
  function globalKeys(e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); return; }
    if (e.key === 'Escape') {
      if (!$('#palette').hidden) closePalette();
      else if (!$('#modal').hidden) closeModal();
      else if (S.panel) closePanel();
    }
  }

  // ------------------------------------------------------------------ routing
  function parseHash() {
    var h = location.hash.replace(/^#/, '') || '/';
    var parts = h.split('?'); var q = {};
    (parts[1] || '').split('&').forEach(function (kv) { if (!kv) return; var p = kv.split('='); q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ''); });
    return { path: parts[0].split('/').filter(Boolean), q: q };
  }
  function setQuery(patch, replace) {
    var r = parseHash(); Object.keys(patch).forEach(function (k) { if (patch[k] === null || patch[k] === '') delete r.q[k]; else r.q[k] = patch[k]; });
    var h = '#/' + r.path.join('/') + qs(r.q);
    if (replace) history.replaceState(null, '', h); else location.hash = h;
  }
  var lastViewKey = null;
  function route() {
    var r = parseHash(); S.route = r;
    var head = r.path[0] || 'dashboard';
    document.querySelectorAll('#nav a').forEach(function (a) { a.classList.toggle('active', a.dataset.nav === head); });
    var viewKey = r.path.join('/') + '|' + JSON.stringify(Object.assign({}, r.q, { open: undefined, res: undefined }));
    if (viewKey !== lastViewKey) {
      lastViewKey = viewKey;
      var v = clear($('#view')); S.listReload = null;
      ({ dashboard: viewDashboard, records: viewRecords, courses: viewRecords, programs: viewRecords,
         resources: viewResources, graph: viewGraph, proposals: viewProposals, settings: viewSettings, quality: viewQuality }[head] || viewNotFound)(v, r);
    }
    if (r.q.open) openNodePanel(r.q.open); else if (r.q.res) openResourcePanel(r.q.res); else if (S.panel) closePanel(true);
  }
  function viewNotFound(v) { v.appendChild(empty('Page not found', 'That address does not match anything here.', el('a', { class: 'btn', href: '#/' }, 'Go to dashboard'))); }

  // ------------------------------------------------------------------ dashboard
  async function viewDashboard(v) {
    v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Dashboard' }), el('div', { class: 'muted', text: 'What the knowledge base holds, and what changed.' })),
      can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-record', text: 'New record', onclick: function () { createNodeModal({}); } }) : null));
    var body = el('div'); v.appendChild(body); body.appendChild(skeleton(5));
    var load = async function () {
      try {
        var d = await api('GET', '/dashboard');
        clear(body);
        var cards = el('div', { class: 'cards', 'data-testid': 'dash-counts' });
        d.counts.forEach(function (c) {
          cards.appendChild(el('a', { class: 'card', href: '#/records' + qs({ type: c.key }), 'data-testid': 'count-' + c.key },
            el('div', { class: 'muted small' }, typePill(c.key)), el('div', { class: 'num', text: c.n })));
        });
        cards.appendChild(el('a', { class: 'card', href: '#/resources' }, el('div', { class: 'muted small', text: 'Resources' }), el('div', { class: 'num', text: d.totals.resources })));
        cards.appendChild(el('div', { class: 'card' }, el('div', { class: 'muted small', text: 'Relationships' }), el('div', { class: 'num', text: d.totals.edges })));
        cards.appendChild(el('a', { class: 'card', href: '#/proposals' }, el('div', { class: 'muted small', text: 'Awaiting approval' }), el('div', { class: 'num', text: d.totals.pending_proposals })));
        body.appendChild(cards);
        body.appendChild(el('h2', { text: 'Recent activity' }));
        if (!d.recent.length) body.appendChild(empty('No activity yet', 'Changes to records, relationships and resources appear here.'));
        else {
          var ul = el('ul', { class: 'list feed', 'data-testid': 'activity' });
          d.recent.forEach(function (a) {
            var link = a.table_name === 'nodes' && a.action !== 'delete' ? el('a', { href: '#/records' + qs({ open: a.row_id }), text: a.label || 'a record' })
              : a.table_name === 'resources' && a.action !== 'delete' ? el('a', { href: '#/resources' + qs({ res: a.row_id }), text: a.label || 'a resource' })
              : el('span', { text: a.label || a.table_name.replace('_', ' ') });
            ul.appendChild(el('li', null, el('strong', { text: actorLabel(a) }),
              el('span', { class: 'muted', text: { insert: 'created', update: 'updated', delete: 'deleted' }[a.action] + ' ' + ({ nodes: '', edges: 'a relationship', resources: '', node_resources: 'a resource link' }[a.table_name] || '') }),
              (a.table_name === 'nodes' || a.table_name === 'resources') ? link : null, el('span', { class: 'spacer' }), el('span', { class: 'faint small', text: ago(a.at) })));
          });
          body.appendChild(ul);
        }
      } catch (e) { clear(body).appendChild(errorBox(e, load)); }
    };
    S.listReload = load; load();
  }

  // ------------------------------------------------------------------ records list
  function viewRecords(v, r) {
    var fixed = { courses: 'course', programs: 'program' }[r.path[0]] || null;
    var title = fixed ? S.typeByKey[fixed].label + 's' : 'All records';
    var f = { q: r.q.q || '', type: fixed || r.q.type || '', status: r.q.status || 'live', sort: r.q.sort || 'updated',
              scope: r.q.scope || '', tag: r.q.tag || '', owner: r.q.owner || '' };
    v.appendChild(el('div', { class: 'page-head' },
      el('div', null, el('h1', { text: title }), el('div', { class: 'muted', text: fixed ? 'Each ' + fixed + ' carries its own modules, relationships and resources.' : 'Every authored record, filterable.' })),
      can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-record', text: 'New ' + (fixed || 'record'), onclick: function () { createNodeModal({ type: fixed || f.type || undefined }); } }) : null));
    var filters = el('div', { class: 'filters', role: 'search' });
    var qIn = el('input', { type: 'search', placeholder: 'Filter by name or text…', value: f.q, 'aria-label': 'Filter', 'data-testid': 'filter-q' });
    qIn.addEventListener('input', debounce(function () { setQuery({ q: qIn.value }, true); f.q = qIn.value; reset(); }, 250));
    filters.appendChild(qIn);
    if (!fixed) {
      var tSel = el('select', { 'aria-label': 'Type', 'data-testid': 'filter-type' }, el('option', { value: '', text: 'All types' }));
      S.types.forEach(function (t) { tSel.appendChild(el('option', { value: t.key, text: t.label, selected: f.type === t.key })); });
      tSel.addEventListener('change', function () { f.type = tSel.value; setQuery({ type: tSel.value }, true); reset(); });
      filters.appendChild(tSel);
    }
    var scSel = el('select', { 'aria-label': 'Course or program', 'data-testid': 'filter-scope' }, el('option', { value: '', text: 'Any course / program' }));
    filters.appendChild(scSel);
    api('GET', '/nodes' + qs({ type: 'course,program', sort: 'name', limit: 200 })).then(function (p) {
      p.items.forEach(function (n) { scSel.appendChild(el('option', { value: n.id, text: n.name + ' (' + n.type + ')', selected: f.scope === n.id })); });
    }).catch(function () { /* the filter just stays empty */ });
    scSel.addEventListener('change', function () { f.scope = scSel.value; setQuery({ scope: scSel.value }, true); reset(); });
    var tagSel = el('select', { 'aria-label': 'Tag', 'data-testid': 'filter-tag' }, el('option', { value: '', text: 'Any tag' }));
    filters.appendChild(tagSel);
    api('GET', '/tags').then(function (p) { p.items.forEach(function (t) { tagSel.appendChild(el('option', { value: t.id, text: t.name, selected: f.tag === t.id })); }); }).catch(function () {});
    tagSel.addEventListener('change', function () { f.tag = tagSel.value; setQuery({ tag: tagSel.value }, true); reset(); });
    var stSel = el('select', { 'aria-label': 'Status', 'data-testid': 'filter-status' });
    [['live', 'Live'], ['draft', 'Drafts'], ['archived', 'Archived'], ['all', 'All']].forEach(function (o) { stSel.appendChild(el('option', { value: o[0], text: o[1], selected: f.status === o[0] })); });
    stSel.addEventListener('change', function () { f.status = stSel.value; setQuery({ status: stSel.value }, true); reset(); });
    var ownSel = el('select', { 'aria-label': 'Owner', 'data-testid': 'filter-owner' }, el('option', { value: '', text: 'Anyone' }),
      el('option', { value: 'owned', text: 'Owned by me', selected: f.owner === 'owned' }), el('option', { value: 'created', text: 'Created by me', selected: f.owner === 'created' }));
    ownSel.addEventListener('change', function () { f.owner = ownSel.value; setQuery({ owner: ownSel.value }, true); reset(); });
    var sortSel = el('select', { 'aria-label': 'Sort', 'data-testid': 'sort' }, el('option', { value: 'updated', text: 'Recently updated', selected: f.sort === 'updated' }), el('option', { value: 'name', text: 'Name A–Z', selected: f.sort === 'name' }));
    sortSel.addEventListener('change', function () { f.sort = sortSel.value; setQuery({ sort: sortSel.value }, true); reset(); });
    var exportBtn = el('button', { class: 'btn', type: 'button', text: 'Export CSV', 'data-testid': 'export-csv', onclick: async function () {
      exportBtn.disabled = true;
      try {
        var rows = [], cur = null, pages = 0;
        do {
          var p = await api('GET', '/nodes' + qs({ q: f.q, type: f.type, status: f.status, sort: f.sort, scope: f.scope, tag: f.tag,
            owner: f.owner === 'owned' ? S.me.user_id : '', created_by: f.owner === 'created' ? S.me.user_id : '', cursor: cur, limit: 200 }));
          rows = rows.concat(p.items); cur = p.next_cursor; pages++;
        } while (cur && pages < 50);
        var cell = function (x) { x = x === null || x === undefined ? '' : String(x); return /[",\r\n]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x; };
        var csv = [['id', 'type', 'name', 'summary', 'course_or_program', 'status', 'archived_at', 'updated_at', 'version']].concat(rows.map(function (n) {
          return [n.id, n.type, n.name, n.summary, n.scope_name, n.status, n.archived_at, n.updated_at, n.version]; })).map(function (r) { return r.map(cell).join(','); }).join('\r\n');
        var a = el('a', { href: URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })), download: 'kb-records.csv' });
        document.body.appendChild(a); a.click(); a.remove();
        toast('Exported ' + rows.length + ' record(s)' + (cur ? ' (first 10,000 — narrow the filters for the rest)' : ''));
      } catch (e) { failToast(e, 'Export failed'); }
      exportBtn.disabled = false;
    } });
    add(filters, [stSel, ownSel, sortSel, exportBtn]);
    v.appendChild(filters);
    var out = el('div', { 'data-testid': 'records' }); v.appendChild(out);
    var cursors = [null], page = 0;
    function reset() { cursors = [null]; page = 0; load(); }
    async function load() {
      clear(out).appendChild(skeleton(8));
      try {
        var p = await api('GET', '/nodes' + qs({ q: f.q, type: f.type, status: f.status, sort: f.sort, scope: f.scope, tag: f.tag,
          owner: f.owner === 'owned' ? S.me.user_id : '', created_by: f.owner === 'created' ? S.me.user_id : '', cursor: cursors[page], limit: 50 }));
        clear(out);
        if (!p.items.length) {
          out.appendChild(page === 0 ? empty(f.q || f.type || f.scope || f.tag || f.owner || f.status !== 'live' ? 'Nothing matches these filters' : 'No records yet',
            f.q ? 'Try fewer words, or clear the filters.' : 'Records you create appear here.',
            can('contributor') ? el('button', { class: 'btn primary', type: 'button', text: 'Create one', onclick: function () { createNodeModal({ type: fixed || f.type || undefined, name: f.q }); } }) : null)
            : empty('End of the list', 'There are no more records.'));
        } else {
          var tb = el('tbody');
          p.items.forEach(function (n) {
            var tr = el('tr', { tabindex: '0', 'data-id': n.id, 'data-testid': 'row', class: S.route.q.open === n.id ? 'selected' : '',
              onclick: function () { setQuery({ open: n.id, res: null }); },
              onkeydown: function (e) { if (e.key === 'Enter') setQuery({ open: n.id, res: null }); } },
              el('td', null, el('strong', { text: n.name }), n.summary ? el('div', { class: 'faint small', text: n.summary.slice(0, 120) }) : null),
              el('td', null, typePill(n.type)), el('td', { class: 'muted small', text: n.scope_name || '—' }),
              el('td', null, statusPill(n) || el('span', { class: 'pill ok', text: 'live' })), el('td', { class: 'faint small', text: ago(n.updated_at) }));
            tb.appendChild(tr);
          });
          out.appendChild(el('table', { class: 'table' }, el('thead', null, el('tr', null, ['Name', 'Type', 'Course / program', 'Status', 'Updated'].map(function (h) { return el('th', { text: h, scope: 'col' }); }))), tb));
        }
        var pager = el('div', { class: 'pager' }, el('span', { class: 'muted small', text: 'Page ' + (page + 1) + (p.items.length ? ' · ' + p.items.length + ' shown' : '') }),
          el('div', { class: 'row' },
            el('button', { class: 'btn sm', type: 'button', text: '← Previous', disabled: page === 0, 'data-testid': 'prev', onclick: function () { page--; load(); } }),
            el('button', { class: 'btn sm', type: 'button', text: 'Next →', disabled: !p.next_cursor, 'data-testid': 'next', onclick: function () { cursors[page + 1] = p.next_cursor; page++; load(); } })));
        out.appendChild(pager);
      } catch (e) { clear(out).appendChild(errorBox(e, load)); }
    }
    S.listReload = load;
    load();
  }

  // ------------------------------------------------------------------ pickers
  /* A searchable picker. opts: types (array), placeholder, onPick(node),
     allowCreate (a container type list: offers "Create course 'X'" inline). */
  function nodePicker(opts) {
    var wrap = el('div', { class: 'picker' });
    var input = el('input', { type: 'text', placeholder: opts.placeholder || 'Search…', 'aria-label': opts.placeholder || 'Search', autocomplete: 'off', 'data-testid': opts.testid || 'picker-input' });
    var menu = el('ul', { class: 'picker-menu', role: 'listbox', hidden: true, 'data-testid': (opts.testid || 'picker') + '-menu' });
    var picked = el('div', { hidden: true });
    var items = [], active = -1;
    add(wrap, [input, menu, picked]);
    function choose(n) { menu.hidden = true; input.hidden = true; clear(picked).hidden = false;
      picked.appendChild(el('span', { class: 'picked', 'data-testid': (opts.testid || 'picker') + '-picked' }, typePill(n.type), n.name,
        el('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Clear', text: '×', onclick: function () { picked.hidden = true; input.hidden = false; input.value = ''; input.focus(); opts.onPick(null); } })));
      opts.onPick(n); }
    function render(q) {
      clear(menu); items = [];
      var src = q ? api('GET', '/search' + qs({ q: q, types: (opts.types || []).join(','), limit: 12 })).then(function (r) { return r.nodes; })
                  : api('GET', '/nodes' + qs({ type: (opts.types || []).join(','), limit: 12 })).then(function (r) { return r.items; });
      src.then(function (nodes) {
        clear(menu); items = [];
        nodes.filter(function (n) { return !opts.exclude || opts.exclude.indexOf(n.id) < 0; }).forEach(function (n) {
          items.push({ node: n });
          menu.appendChild(el('li', { role: 'option', 'data-testid': 'picker-option', onmousedown: function (e) { e.preventDefault(); choose(n); } }, typePill(n.type), el('span', { text: n.name }), n.scope_name ? el('span', { class: 'faint', text: '· ' + n.scope_name }) : null));
        });
        (opts.allowCreate || []).forEach(function (tk) {
          if (!q || !can('contributor')) return;
          var exact = nodes.some(function (n) { return n.type === tk && n.name.toLowerCase().trim() === q.toLowerCase().trim(); });
          if (exact) return;
          items.push({ create: tk });
          menu.appendChild(el('li', { class: 'create', role: 'option', 'data-testid': 'picker-create-' + tk, onmousedown: function (e) { e.preventDefault(); choose({ id: null, type: tk, name: q.trim(), isNew: true }); } },
            '＋ Create ' + S.typeByKey[tk].label.toLowerCase() + ' “' + q.trim() + '”'));
        });
        if (!items.length) menu.appendChild(el('li', { class: 'faint', text: q ? 'No matches' : 'Type to search' }));
        menu.hidden = false; active = -1;
      }).catch(function (e) { clear(menu).appendChild(el('li', { class: 'faint', text: e.message })); menu.hidden = false; });
    }
    var deb = debounce(function () { render(input.value.trim()); }, 180);
    input.addEventListener('input', deb);
    input.addEventListener('focus', function () { render(input.value.trim()); });
    input.addEventListener('blur', function () { setTimeout(function () { menu.hidden = true; }, 120); });
    input.addEventListener('keydown', function (e) {
      var lis = menu.querySelectorAll('li[role=option]');
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, lis.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); }
      else if (e.key === 'Enter') { e.preventDefault(); if (active >= 0 && lis[active]) lis[active].dispatchEvent(new MouseEvent('mousedown')); return; }
      else return;
      lis.forEach(function (li, i) { li.classList.toggle('active', i === active); });
    });
    if (opts.initial) setTimeout(function () { choose(opts.initial); }, 0);
    wrap.focusInput = function () { input.focus(); };
    return wrap;
  }

  // ------------------------------------------------------------------ create
  function containerKeys() { return S.types.filter(function (t) { return t.is_container; }).map(function (t) { return t.key; }); }
  function createNodeModal(pre) {
    var err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'form-error' });
    var tSel = el('select', { name: 'type', 'data-testid': 'create-type', required: true });
    S.types.forEach(function (t) { tSel.appendChild(el('option', { value: t.key, text: t.label, selected: (pre.type || 'topic') === t.key })); });
    var name = el('input', { name: 'name', required: true, maxlength: '300', value: pre.name || '', 'data-testid': 'create-name', autofocus: true });
    var summary = el('textarea', { name: 'summary', maxlength: '2000', rows: '3', 'data-testid': 'create-summary' });
    var scope = null;
    var scopePicker = nodePicker({ types: containerKeys(), allowCreate: containerKeys(), placeholder: 'Course or program (optional)', testid: 'scope-picker',
      initial: pre.scope || null, onPick: function (n) { scope = n; } });
    var status = el('select', { name: 'status', 'data-testid': 'create-status' }, el('option', { value: 'active', text: 'Live' }), el('option', { value: 'draft', text: 'Draft' }));
    var submit = el('button', { class: 'btn primary', type: 'submit', text: 'Create', 'data-testid': 'create-submit' });
    var form = el('form', { novalidate: true, onsubmit: async function (e) {
      e.preventDefault(); err.textContent = '';
      if (!name.value.trim()) { err.textContent = 'Name is required.'; name.focus(); return; }
      var body = { type: tSel.value, name: name.value, summary: summary.value || undefined, status: status.value };
      if (scope) body.scope = scope.isNew ? { new: { type: scope.type, name: scope.name } } : scope.id;
      if (pre.edgeFrom) body.edges = [pre.edgeFrom];
      submit.disabled = true;
      try {
        var n = await api('POST', '/nodes', body);
        closeModal();
        toast('Created ' + n.name + (n.created_scope_id ? ' and ' + n.scope_type + ' “' + n.scope_name + '”' : ''));
        if (pre.onCreated) pre.onCreated(n); else setQuery({ open: n.id, res: null });
        if (S.listReload) S.listReload();
      } catch (ex) {
        submit.disabled = false;
        if (ex.status === 409 && ex.body.existing) {
          clear(err).appendChild(el('span', null, ex.message + '. ', el('a', { href: '#/records' + qs({ open: ex.body.existing.id }), 'data-testid': 'open-existing', onclick: closeModal, text: 'Open the existing ' + ex.body.existing.type })));
        } else err.textContent = ex.message;
      }
    } },
      el('h2', { text: 'New record' }),
      el('label', { class: 'field' }, 'Type', tSel),
      el('label', { class: 'field' }, 'Name', name),
      el('label', { class: 'field' }, 'Summary', summary),
      el('div', { class: 'field' }, el('span', { class: 'small muted', text: 'Belongs to' }), scopePicker),
      el('label', { class: 'field' }, 'Status', status),
      err,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeModal }), submit));
    openModal(form, { label: 'New record' });
  }

  // ------------------------------------------------------------------ side panel: node
  function closePanel(fromRoute) {
    S.panel = null; $('#panel').hidden = true; clear($('#panel')); $('#app').classList.remove('with-panel');
    document.querySelectorAll('tr.selected').forEach(function (t) { t.classList.remove('selected'); });
    if (!fromRoute) setQuery({ open: null, res: null });
  }
  function panelShell() { var p = $('#panel'); p.hidden = false; $('#app').classList.add('with-panel'); return clear(p); }
  async function openNodePanel(id, force) {
    if (!force && S.panel && S.panel.kind === 'node' && S.panel.id === id) return;
    document.querySelectorAll('tr[data-id]').forEach(function (t) { t.classList.toggle('selected', t.dataset.id === id); });
    var p = panelShell(); S.panel = { kind: 'node', id: id, node: null };
    p.appendChild(skeleton(10));
    try {
      var n = await api('GET', '/nodes/' + id);
      if (!S.panel || S.panel.id !== id) return;
      S.panel.node = n; renderNodePanel();
    } catch (e) {
      clear(p).appendChild(e.status === 404 ? empty('Record not found', 'It may have been permanently deleted.') : errorBox(e, function () { openNodePanel(id, true); }));
    }
  }
  function renderNodePanel() {
    var n = S.panel.node, p = clear($('#panel')), editable = can('contributor') && !n.archived_at;
    p.setAttribute('data-testid', 'panel');
    var close = el('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Close details', text: '✕', onclick: function () { closePanel(); } });
    var title = el('h1', { class: editable ? 'inline-edit' : '', 'data-testid': 'panel-name', text: n.name, contenteditable: editable ? 'true' : null, spellcheck: 'false',
      'aria-label': 'Name', role: editable ? 'textbox' : null });
    if (editable) {
      title.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); title.blur(); } if (e.key === 'Escape') { title.textContent = n.name; title.blur(); } });
      title.addEventListener('blur', function () { var v = title.textContent.replace(/\s+/g, ' ').trim(); if (v && v !== n.name) saveNode({ name: v }); else title.textContent = n.name; });
    }
    p.appendChild(el('div', { class: 'panel-head' }, el('div', { class: 'row' }, typePill(n.type), statusPill(n), el('span', { class: 'faint small', text: 'v' + n.version, 'data-testid': 'panel-version' })), close));
    p.appendChild(title);
    if (n.archived_at) p.appendChild(el('div', { class: 'error-box small', style: 'margin:8px 0' }, 'Archived ' + ago(n.archived_at) + '. It is hidden from lists and the graph.'));
    // actions
    var acts = el('div', { class: 'row', style: 'margin:12px 0' });
    acts.appendChild(el('a', { class: 'btn sm', href: '#/graph/' + n.id, 'data-testid': 'open-graph', text: 'Graph' }));
    if (can('contributor') && !n.archived_at) {
      acts.appendChild(el('button', { class: 'btn sm', type: 'button', 'data-testid': 'connect', text: 'Connect', onclick: function () { connectModal(n); } }));
      acts.appendChild(el('button', { class: 'btn sm', type: 'button', 'data-testid': 'duplicate', text: 'Duplicate', onclick: duplicateNode }));
    }
    if (!n.archived_at && can('contributor')) acts.appendChild(el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'archive', text: can('editor') ? 'Archive' : 'Propose archive', onclick: archiveNode }));
    if (n.archived_at && can('editor')) acts.appendChild(el('button', { class: 'btn sm', type: 'button', 'data-testid': 'restore', text: 'Restore', onclick: restoreNode }));
    if (n.archived_at && can('admin')) acts.appendChild(el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'hard-delete', text: 'Delete permanently', onclick: hardDeleteNode }));
    p.appendChild(acts);
    // summary / body
    p.appendChild(el('h3', { text: 'Summary' }));
    p.appendChild(textBlock('summary', n.summary, editable, 'Add a short summary…', 2000));
    p.appendChild(el('h3', { text: 'Notes' }));
    p.appendChild(textBlock('body', n.body, editable, 'Add notes…', 100000));
    // facts
    var kv = el('dl', { class: 'kv' });
    var scopeDd = el('dd', { 'data-testid': 'panel-scope' }, n.scope_id ? el('a', { href: '#/records' + qs({ open: n.scope_id }), text: n.scope_name + ' (' + n.scope_type + ')' }) : el('span', { class: 'faint', text: 'None' }));
    if (editable && n.type !== 'program') scopeDd.appendChild(el('button', { class: 'btn ghost sm', type: 'button', text: 'Change', 'data-testid': 'change-scope', onclick: changeScope }));
    add(kv, [el('dt', { text: 'Belongs to' }), scopeDd]);
    if (S.typeByKey[n.type] && S.typeByKey[n.type].is_container) add(kv, [el('dt', { text: 'Contains' }), el('dd', null, el('a', { href: '#/records' + qs({ scope: n.id }), text: n.children_count + ' record(s)' }))]);
    add(kv, [el('dt', { text: 'Status' }), el('dd', null, editable ? statusSelect(n) : (n.status))]);
    add(kv, [el('dt', { text: 'Updated' }), el('dd', { text: ago(n.updated_at) }), el('dt', { text: 'Created' }), el('dd', { text: new Date(n.created_at).toLocaleString() })]);
    if (n.external_id) add(kv, [el('dt', { text: 'Imported from' }), el('dd', { class: 'mono', text: n.external_id })]);
    p.appendChild(kv);
    // tags
    p.appendChild(el('h3', { text: 'Tags' }));
    var tags = el('div', { class: 'row', 'data-testid': 'panel-tags' });
    n.tags.forEach(function (t) { tags.appendChild(el('span', { class: 'pill' }, t.name, editable ? el('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Remove tag ' + t.name, text: '×', onclick: function () { untag(t); } }) : null)); });
    if (editable) {
      var tagIn = el('input', { placeholder: 'Add tag', 'aria-label': 'Add tag', style: 'width:120px', 'data-testid': 'tag-input' });
      tagIn.addEventListener('keydown', function (e) { if (e.key === 'Enter' && tagIn.value.trim()) { e.preventDefault(); addTag(tagIn.value.trim()); } });
      tags.appendChild(tagIn);
    } else if (!n.tags.length) tags.appendChild(el('span', { class: 'faint small', text: 'No tags' }));
    p.appendChild(tags);
    // relationships
    p.appendChild(el('h3', { text: 'Relationships (' + (n.outgoing.length + n.incoming.length) + ')' }));
    var rels = el('div', { 'data-testid': 'panel-relationships' });
    var rows = n.outgoing.map(function (e) { return { e: e, label: e.label }; }).concat(n.incoming.map(function (e) { return { e: e, label: e.label }; }));
    if (!rows.length) rels.appendChild(el('div', { class: 'faint small', text: 'Not connected to anything yet.' }));
    rows.forEach(function (r) {
      rels.appendChild(el('div', { class: 'rel', 'data-testid': 'rel' }, el('span', { class: 'label', text: r.label }), typePill(r.e.node_type),
        el('a', { href: '#/records' + qs({ open: r.e.node_id }), text: r.e.node_name }), el('span', { class: 'spacer' }),
        can('contributor') && !n.archived_at ? el('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Remove relationship', title: can('editor') ? 'Remove' : 'Propose removal', text: '×', onclick: function () { archiveEdge(r.e); } }) : null));
    });
    p.appendChild(rels);
    // resources
    p.appendChild(el('div', { class: 'row' }, el('h3', { text: 'Resources (' + n.resources.length + ')' }), el('span', { class: 'spacer' }),
      editable ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'attach', text: 'Attach', onclick: function () { attachModal(n); } }) : null));
    var res = el('ul', { class: 'list', 'data-testid': 'panel-resources' });
    if (!n.resources.length) res.appendChild(el('li', { class: 'faint small', text: 'No resources attached.' }));
    n.resources.forEach(function (r) {
      res.appendChild(el('li', null, el('span', { class: 'pill', text: r.kind }), el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', text: r.title }),
        r.note ? el('span', { class: 'faint small', text: '— ' + r.note }) : null, el('span', { class: 'spacer' }),
        el('a', { class: 'btn ghost sm', href: '#/resources' + qs({ res: r.id }), text: 'Details' }),
        editable ? el('button', { class: 'btn ghost sm', type: 'button', 'aria-label': 'Detach ' + r.title, text: '×', onclick: function () { detach(r); } }) : null));
    });
    p.appendChild(res);
    // history
    var hist = el('details', { 'data-testid': 'panel-history' }, el('summary', { class: 'small muted', text: 'History' }));
    hist.addEventListener('toggle', function () { if (hist.open && !hist.dataset.loaded) loadHistory(hist, '/nodes/' + n.id + '/history'); });
    p.appendChild(el('div', { style: 'margin-top:16px' }, hist));
  }
  function textBlock(field, value, editable, placeholder, max) {
    var div = el('div', { class: editable ? 'inline-edit' : '', 'data-testid': 'panel-' + field, 'data-placeholder': editable ? placeholder : '—', tabindex: editable ? '0' : null, role: editable ? 'button' : null, 'aria-label': editable ? 'Edit ' + field : null, style: 'white-space:pre-wrap' }, value || '');
    if (!editable) return div;
    var start = function () {
      var ta = el('textarea', { maxlength: String(max), rows: field === 'body' ? '8' : '3', 'aria-label': field, 'data-testid': 'edit-' + field }, value || '');
      div.replaceWith(ta); ta.focus();
      var finish = function (save) { var v = ta.value.trim(); if (save && v !== (value || '')) saveNode(objOf(field, v || null)); else renderNodePanel(); };
      ta.addEventListener('blur', function () { finish(true); });
      ta.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); ta.value = value || ''; finish(false); } if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ta.blur(); });
    };
    div.addEventListener('click', start); div.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); start(); } });
    return div;
  }
  function objOf(k, v) { var o = {}; o[k] = v; return o; }
  function statusSelect(n) {
    var s = el('select', { 'aria-label': 'Status', 'data-testid': 'panel-status' }, el('option', { value: 'active', text: 'Live', selected: n.status === 'active' }), el('option', { value: 'draft', text: 'Draft', selected: n.status === 'draft' }));
    s.addEventListener('change', function () { saveNode({ status: s.value }); });
    return s;
  }

  /* OPTIMISTIC save: the panel shows the new value immediately; a failure rolls
     it back. A 409 opens the conflict dialog instead of overwriting. */
  async function saveNode(changes, force) {
    var n = S.panel.node, before = Object.assign({}, n);
    Object.keys(changes).forEach(function (k) { n[k] = changes[k]; }); renderNodePanel();
    try {
      var updated = await api('PATCH', '/nodes/' + n.id + (force ? '?force=1' : ''), Object.assign({ version: before.version }, changes));
      if (S.panel && S.panel.id === updated.id) { S.panel.node = updated; renderNodePanel(); }
      hideLive();
      toast('Saved');
      if (S.listReload) S.listReload();
    } catch (e) {
      if (S.panel && S.panel.id === before.id) { S.panel.node = before; renderNodePanel(); }
      if (e.status === 409 && e.body.error === 'version_conflict') conflictDialog(before, changes, e.body.current);
      else if (e.status === 409 && e.body.existing) toast(e.message, { error: true, action: { label: 'Open existing', fn: function () { setQuery({ open: e.body.existing.id }); } } });
      else failToast(e, 'Not saved');
    }
  }
  function conflictDialog(mine, changes, current) {
    var diff = el('div', { class: 'diff', 'data-testid': 'conflict-diff' }, el('div', { class: 'h', text: 'Field' }), el('div', { class: 'h', text: 'Your change' }), el('div', { class: 'h', text: 'Saved now (v' + current.version + ')' }));
    var fields = ['name', 'summary', 'body', 'status', 'scope_name'];
    fields.forEach(function (f) {
      var yours = f in changes ? changes[f] : mine[f];
      if (!(f in changes) && String(mine[f] || '') === String(current[f] || '')) return;
      add(diff, [el('div', { class: 'faint', text: f.replace('_name', '') }), el('div', { class: 'mine', text: String(yours === null || yours === undefined ? '—' : yours) }), el('div', { class: 'theirs', text: String(current[f] === null || current[f] === undefined ? '—' : current[f]) })]);
    });
    var actions = el('div', { class: 'actions' },
      el('button', { class: 'btn', type: 'button', 'data-testid': 'conflict-reload', text: 'Reload their version', onclick: function () { closeModal(); openNodePanel(mine.id, true); } }));
    if (can('editor')) actions.appendChild(el('button', { class: 'btn danger solid', type: 'button', 'data-testid': 'conflict-overwrite', text: 'Overwrite with mine', onclick: function () {
      closeModal(); S.panel.node = Object.assign({}, mine, current); saveNode(changes, true); } }));
    openModal(el('div', { 'data-testid': 'conflict-dialog' }, el('h2', { text: 'This record changed since you opened it' }),
      el('p', { class: 'muted', text: 'Someone saved a newer version (v' + current.version + ') while you were editing v' + mine.version + '. Your change was not saved.' }), diff,
      can('editor') ? null : el('p', { class: 'faint small', text: 'Only editors can overwrite a newer version.' }), actions), { label: 'Edit conflict' });
  }
  async function changeScope() {
    var n = S.panel.node, chosen = null;
    var picker = nodePicker({ types: containerKeys(), allowCreate: containerKeys(), placeholder: 'Pick or create a course / program', testid: 'rescope-picker', exclude: [n.id], onPick: function (x) { chosen = x; } });
    openModal(el('div', null, el('h2', { text: 'Move “' + n.name + '”' }), picker,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Remove from scope', onclick: function () { closeModal(); saveNode({ scope: null }); } }),
        el('button', { class: 'btn primary', type: 'button', text: 'Move', 'data-testid': 'rescope-save', onclick: function () {
          if (!chosen) return; closeModal(); saveNode({ scope: chosen.isNew ? { new: { type: chosen.type, name: chosen.name } } : chosen.id }); } }))), { label: 'Move record' });
  }
  async function addTag(name) {
    var n = S.panel.node; n.tags = n.tags.concat([{ id: 'pending', name: name }]); renderNodePanel();
    try { await api('POST', '/nodes/' + n.id + '/tags', { name: name }); openNodePanel(n.id, true); }
    catch (e) { n.tags = n.tags.filter(function (t) { return t.id !== 'pending'; }); renderNodePanel(); failToast(e, 'Tag not added'); }
  }
  async function untag(t) {
    var n = S.panel.node, before = n.tags; n.tags = n.tags.filter(function (x) { return x.id !== t.id; }); renderNodePanel();
    try { await api('DELETE', '/nodes/' + n.id + '/tags/' + t.id); }
    catch (e) { n.tags = before; renderNodePanel(); failToast(e, 'Tag not removed'); }
  }
  async function duplicateNode() {
    try { var d = await api('POST', '/nodes/' + S.panel.node.id + '/duplicate'); toast('Duplicated as “' + d.name + '” (draft)'); setQuery({ open: d.id }); if (S.listReload) S.listReload(); }
    catch (e) { failToast(e, 'Not duplicated'); }
  }
  async function archiveNode() {
    var n = S.panel.node, imp;
    try { imp = await api('GET', '/nodes/' + n.id + '/impact'); } catch (e) { failToast(e); return; }
    var reason = el('textarea', { rows: '2', placeholder: 'Why? (optional)', 'aria-label': 'Reason', 'data-testid': 'archive-reason' });
    var body = el('div', null, el('ul', { class: 'small', 'data-testid': 'archive-impact' },
      el('li', { text: imp.edges + ' relationship(s) will be archived with it' }), el('li', { text: imp.resources + ' resource link(s) will be archived with it' }),
      imp.scoped_records ? el('li', { text: imp.scoped_records + ' record(s) belong to it and stay live' }) : null),
      el('p', { class: 'muted small', text: 'Restoring brings back exactly the relationships archived with it.' }), can('editor') ? null : reason);
    var ok = await confirmDialog({ title: (can('editor') ? 'Archive “' : 'Propose archiving “') + n.name + '”?', body: body, danger: true, confirmLabel: can('editor') ? 'Archive' : 'Send for approval' });
    if (!ok) return;
    try { await api('POST', '/nodes/' + n.id + '/archive', { reason: reason.value || undefined }); toast('Archived “' + n.name + '”', { action: can('editor') ? { label: 'Undo', fn: restoreNode } : null }); openNodePanel(n.id, true); if (S.listReload) S.listReload(); }
    catch (e) { if (e.status === 202) { toast('Sent for approval — an editor will review it.'); refreshPending(); } else failToast(e, 'Not archived'); }
  }
  async function restoreNode() {
    var n = S.panel.node;
    try { await api('POST', '/nodes/' + n.id + '/restore'); toast('Restored “' + n.name + '”'); openNodePanel(n.id, true); if (S.listReload) S.listReload(); }
    catch (e) { failToast(e, 'Not restored'); }
  }
  async function hardDeleteNode() {
    var n = S.panel.node;
    if (!await confirmDialog({ title: 'Delete “' + n.name + '” permanently?', body: 'This cannot be undone. Its history stays in the audit log.', danger: true, confirmLabel: 'Delete permanently' })) return;
    try { await api('DELETE', '/nodes/' + n.id); toast('Deleted'); closePanel(); if (S.listReload) S.listReload(); } catch (e) { failToast(e, 'Not deleted'); }
  }
  async function archiveEdge(e) {
    if (!await confirmDialog({ title: can('editor') ? 'Remove this relationship?' : 'Propose removing this relationship?', body: e.label + ' → ' + e.node_name, danger: true, confirmLabel: can('editor') ? 'Remove' : 'Send for approval' })) return;
    try { await api('POST', '/edges/' + e.id + '/archive', {}); toast('Relationship removed'); openNodePanel(S.panel.id, true); }
    catch (x) { if (x.status === 202) { toast('Sent for approval.'); refreshPending(); } else failToast(x, 'Not removed'); }
  }
  async function detach(r) {
    if (!await confirmDialog({ title: can('editor') ? 'Detach “' + r.title + '”?' : 'Propose detaching “' + r.title + '”?', body: 'The resource stays in the library for other records.', confirmLabel: can('editor') ? 'Detach' : 'Send for approval' })) return;
    try { await api('POST', '/attachments/' + r.attachment_id + '/detach'); toast('Detached'); openNodePanel(S.panel.id, true); }
    catch (x) { if (x.status === 202) { toast('Sent for approval.'); refreshPending(); } else failToast(x, 'Not detached'); }
  }
  async function loadHistory(container, path) {
    container.dataset.loaded = '1';
    var ul = el('ul', { class: 'list feed small' }); container.appendChild(ul); ul.appendChild(el('li', { text: 'Loading…' }));
    try {
      var h = await api('GET', path); clear(ul);
      if (!h.items.length) ul.appendChild(el('li', { class: 'faint', text: 'No history.' }));
      h.items.forEach(function (x) {
        var changed = [];
        if (x.before && x.after) Object.keys(x.after).forEach(function (k) { if (['version', 'updated_at', 'updated_by', 'name_norm'].indexOf(k) < 0 && JSON.stringify(x.before[k]) !== JSON.stringify(x.after[k])) changed.push(k); });
        ul.appendChild(el('li', null, el('strong', { text: actorLabel(x) }), el('span', { class: 'muted', text: x.action === 'update' ? 'changed ' + (changed.join(', ') || 'metadata') : x.action + 'd' }), el('span', { class: 'spacer' }), el('span', { class: 'faint', text: ago(x.at) })));
      });
    } catch (e) { clear(ul).appendChild(el('li', { class: 'field-error', text: e.message })); }
  }

  // ------------------------------------------------------------------ connect
  function allowedRules(nodeType) {
    var out = [];
    S.edgeTypes.forEach(function (et) {
      et.rules.forEach(function (r) {
        if (r.source === nodeType) out.push({ et: et, dir: 'out', other: r.target });
        if (r.target === nodeType && !(r.source === nodeType && r.target === nodeType)) out.push({ et: et, dir: 'in', other: r.source });
      });
    });
    return out;
  }
  function connectModal(n, presetTarget) {
    var rules = allowedRules(n.type);
    if (!rules.length) { toast('No relationship types are configured for ' + n.type + ' records.', { error: true }); return; }
    var err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'connect-error' });
    var sel = el('select', { 'data-testid': 'connect-type', 'aria-label': 'Relationship' });
    var groups = {};
    rules.forEach(function (r) { var k = r.et.key + '|' + r.dir; (groups[k] = groups[k] || { et: r.et, dir: r.dir, others: [] }).others.push(r.other); });
    Object.keys(groups).forEach(function (k) { var g = groups[k]; sel.appendChild(el('option', { value: k, text: (g.dir === 'out' ? g.et.label : (g.et.inverse_label || g.et.label)) + ' → ' + g.others.map(function (o) { return S.typeByKey[o] ? S.typeByKey[o].label.toLowerCase() : o; }).join(' / ') })); });
    var target = presetTarget || null, holder = el('div');
    function mountPicker() {
      var g = groups[sel.value]; clear(holder);
      if (presetTarget) { holder.appendChild(el('span', { class: 'picked' }, typePill(presetTarget.type), presetTarget.name)); return; }
      holder.appendChild(nodePicker({ types: g.others, placeholder: 'Find a ' + g.others.join(' or ') + '…', testid: 'connect-picker', exclude: [n.id], onPick: function (x) { target = x; } }));
    }
    sel.addEventListener('change', function () { if (!presetTarget) target = null; mountPicker(); });
    if (presetTarget) { for (var i = 0; i < sel.options.length; i++) { if (groups[sel.options[i].value].others.indexOf(presetTarget.type) >= 0) { sel.selectedIndex = i; break; } } }
    mountPicker();
    var note = el('input', { placeholder: 'Note (optional)', 'aria-label': 'Note', maxlength: '2000' });
    var go = el('button', { class: 'btn primary', type: 'submit', text: 'Connect', 'data-testid': 'connect-submit' });
    openModal(el('form', { onsubmit: async function (e) {
      e.preventDefault(); err.textContent = '';
      var g = groups[sel.value];
      if (!target) { err.textContent = 'Pick a record to connect to.'; return; }
      if (g.others.indexOf(target.type) < 0) { err.textContent = 'A ' + target.type + ' cannot be the other end of this relationship.'; return; }
      go.disabled = true;
      try {
        await api('POST', '/edges', { type: g.et.key, source_id: g.dir === 'out' ? n.id : target.id, target_id: g.dir === 'out' ? target.id : n.id, note: note.value || undefined });
        closeModal(); toast('Connected to “' + target.name + '”');
        if (S.panel && S.panel.id === n.id) openNodePanel(n.id, true);
        if (S.graph) S.graph.reload();
      } catch (x) { go.disabled = false; err.textContent = x.message; }
    } }, el('h2', { text: 'Connect “' + n.name + '”' }), el('label', { class: 'field' }, 'Relationship', sel), el('div', { class: 'field' }, el('span', { class: 'small muted', text: 'To' }), holder),
      el('label', { class: 'field' }, 'Note', note), err, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeModal }), go)), { label: 'Connect records' });
  }

  // ------------------------------------------------------------------ attach resource
  function attachModal(n) {
    var err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'attach-error' });
    var search = el('input', { placeholder: 'Search the library, or paste a new URL', 'aria-label': 'Resource', 'data-testid': 'attach-search', autocomplete: 'off', autofocus: true });
    var list = el('ul', { class: 'picker-menu', style: 'position:static;box-shadow:none;max-height:200px', 'data-testid': 'attach-results' });
    var title = el('input', { placeholder: 'Title for a new resource', 'aria-label': 'Title', 'data-testid': 'attach-title', maxlength: '300' });
    var kind = el('select', { 'aria-label': 'Kind', 'data-testid': 'attach-kind' });
    ['link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other'].forEach(function (k) { kind.appendChild(el('option', { value: k, text: k })); });
    var note = el('input', { placeholder: 'How it relates (optional)', 'aria-label': 'Note', 'data-testid': 'attach-note', maxlength: '2000' });
    var chosen = [];
    var chips = el('div', { class: 'row', 'data-testid': 'attach-chosen' });
    function renderChips() { clear(chips); chosen.forEach(function (c, i) { chips.appendChild(el('span', { class: 'picked' }, c.title || c.url, el('button', { class: 'btn ghost sm', type: 'button', text: '×', 'aria-label': 'Remove', onclick: function () { chosen.splice(i, 1); renderChips(); } }))); }); }
    var isUrl = function (s) { return /^https?:\/\/\S+\.\S+/i.test(s); };
    var find = debounce(async function () {
      var q = search.value.trim(); clear(list);
      if (!q) return;
      try {
        var r = await api('GET', '/resources' + qs({ q: q, limit: 8 }));
        r.items.forEach(function (x) { list.appendChild(el('li', { 'data-testid': 'attach-option', onclick: function () { chosen.push({ resource_id: x.id, title: x.title }); renderChips(); search.value = ''; clear(list); } }, el('span', { class: 'pill', text: x.kind }), x.title, el('span', { class: 'faint', text: '· used by ' + x.used_by }))); });
        if (isUrl(q) && !r.items.length) list.appendChild(el('li', { class: 'faint', text: 'New URL — give it a title below and add it.' }));
      } catch (e) { list.appendChild(el('li', { class: 'field-error', text: e.message })); }
    }, 200);
    search.addEventListener('input', find);
    var addNew = el('button', { class: 'btn sm', type: 'button', text: 'Add URL', 'data-testid': 'attach-add-url', onclick: function () {
      var u = search.value.trim(); err.textContent = '';
      if (!isUrl(u)) { err.textContent = 'Paste a full http(s) URL to add a new resource.'; return; }
      if (!title.value.trim()) { err.textContent = 'Give the new resource a title.'; title.focus(); return; }
      chosen.push({ url: u, title: title.value.trim(), kind: kind.value }); renderChips(); search.value = ''; title.value = ''; clear(list);
    } });
    var go = el('button', { class: 'btn primary', type: 'submit', text: 'Attach', 'data-testid': 'attach-submit' });
    openModal(el('form', { onsubmit: async function (e) {
      e.preventDefault(); err.textContent = '';
      if (!chosen.length) { err.textContent = 'Choose at least one resource.'; return; }
      go.disabled = true; var reused = 0, done = 0;
      for (var i = 0; i < chosen.length; i++) {
        try { var r = await api('POST', '/nodes/' + n.id + '/resources', Object.assign({ note: note.value || undefined }, chosen[i])); done++; if (r.reused) reused++; }
        catch (x) { err.textContent = (chosen[i].title || chosen[i].url) + ': ' + x.message; }
      }
      go.disabled = false;
      if (done) { toast('Attached ' + done + ' resource(s)' + (reused ? ' — ' + reused + ' already in the library, reused' : '')); }
      if (!err.textContent) closeModal();
      openNodePanel(n.id, true);
    } }, el('h2', { text: 'Attach resources to “' + n.name + '”' }), search, list,
      el('div', { class: 'row' }, title, kind, addNew), chips, note, err,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeModal }), go)), { label: 'Attach resources' });
  }

  // ------------------------------------------------------------------ resources
  function viewResources(v, r) {
    var f = { q: r.q.q || '', kind: r.q.kind || '', status: r.q.status || 'live' };
    v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Resources' }), el('div', { class: 'muted', text: 'One library of links, reused across records.' })),
      can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-resource', text: 'New resource', onclick: newResourceModal }) : null));
    var qIn = el('input', { type: 'search', placeholder: 'Filter by title or URL…', value: f.q, 'aria-label': 'Filter', 'data-testid': 'res-filter' });
    var kSel = el('select', { 'aria-label': 'Kind' }, el('option', { value: '', text: 'Any kind' }));
    ['link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other'].forEach(function (k) { kSel.appendChild(el('option', { value: k, text: k, selected: f.kind === k })); });
    var sSel = el('select', { 'aria-label': 'Status' }, el('option', { value: 'live', text: 'Live' }), el('option', { value: 'archived', text: 'Archived', selected: f.status === 'archived' }));
    qIn.addEventListener('input', debounce(function () { f.q = qIn.value; setQuery({ q: f.q }, true); reset(); }, 250));
    kSel.addEventListener('change', function () { f.kind = kSel.value; setQuery({ kind: f.kind }, true); reset(); });
    sSel.addEventListener('change', function () { f.status = sSel.value; setQuery({ status: f.status }, true); reset(); });
    v.appendChild(el('div', { class: 'filters' }, qIn, kSel, sSel));
    var out = el('div'); v.appendChild(out);
    var cursors = [null], page = 0;
    function reset() { cursors = [null]; page = 0; load(); }
    async function load() {
      clear(out).appendChild(skeleton(6));
      try {
        var p = await api('GET', '/resources' + qs({ q: f.q, kind: f.kind, status: f.status, cursor: cursors[page], limit: 50 }));
        clear(out);
        if (!p.items.length) { out.appendChild(empty(f.q || f.kind ? 'Nothing matches' : 'No resources yet', 'Attach a link to a record, or add one here.')); return; }
        var tb = el('tbody');
        p.items.forEach(function (x) {
          tb.appendChild(el('tr', { tabindex: '0', 'data-testid': 'res-row', onclick: function () { setQuery({ res: x.id, open: null }); }, onkeydown: function (e) { if (e.key === 'Enter') setQuery({ res: x.id, open: null }); } },
            el('td', null, el('strong', { text: x.title }), el('div', { class: 'faint small mono', text: x.url })), el('td', null, el('span', { class: 'pill', text: x.kind })),
            el('td', { class: 'muted small', text: x.used_by + ' record(s)' }), el('td', { class: 'faint small', text: ago(x.updated_at) })));
        });
        out.appendChild(el('table', { class: 'table' }, el('thead', null, el('tr', null, ['Resource', 'Kind', 'Used by', 'Updated'].map(function (h) { return el('th', { text: h }); }))), tb));
        out.appendChild(el('div', { class: 'pager' }, el('span'), el('div', { class: 'row' },
          el('button', { class: 'btn sm', type: 'button', text: '← Previous', disabled: page === 0, onclick: function () { page--; load(); } }),
          el('button', { class: 'btn sm', type: 'button', text: 'Next →', disabled: !p.next_cursor, onclick: function () { cursors[page + 1] = p.next_cursor; page++; load(); } }))));
      } catch (e) { clear(out).appendChild(errorBox(e, load)); }
    }
    S.listReload = load; load();
  }
  function newResourceModal() {
    var err = el('div', { class: 'field-error', role: 'alert' });
    var url = el('input', { type: 'url', placeholder: 'https://…', required: true, 'data-testid': 'res-url', autofocus: true, maxlength: '2048' });
    var title = el('input', { required: true, 'data-testid': 'res-title', maxlength: '300' });
    var kind = el('select', { 'data-testid': 'res-kind' }); ['link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other'].forEach(function (k) { kind.appendChild(el('option', { value: k, text: k })); });
    openModal(el('form', { novalidate: true, onsubmit: async function (e) {
      e.preventDefault(); err.textContent = '';
      try { var r = await api('POST', '/resources', { url: url.value.trim(), title: title.value, kind: kind.value }); closeModal(); toast('Added “' + r.title + '”'); setQuery({ res: r.id }); if (S.listReload) S.listReload(); }
      catch (x) {
        if (x.status === 409 && x.body.existing) clear(err).appendChild(el('span', null, 'This URL is already in the library as “' + x.body.existing.title + '”. ', el('a', { href: '#/resources' + qs({ res: x.body.existing.id }), onclick: closeModal, text: 'Open it' })));
        else err.textContent = x.message;
      }
    } }, el('h2', { text: 'New resource' }), el('label', { class: 'field' }, 'URL', url), el('label', { class: 'field' }, 'Title', title), el('label', { class: 'field' }, 'Kind', kind), err,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeModal }), el('button', { class: 'btn primary', type: 'submit', text: 'Add', 'data-testid': 'res-submit' }))), { label: 'New resource' });
  }
  async function openResourcePanel(id, force) {
    if (!force && S.panel && S.panel.kind === 'res' && S.panel.id === id) return;
    var p = panelShell(); S.panel = { kind: 'res', id: id }; p.appendChild(skeleton(6));
    try { var r = await api('GET', '/resources/' + id); if (S.panel.id !== id) return; S.panel.res = r; renderResourcePanel(); }
    catch (e) { clear(p).appendChild(e.status === 404 ? empty('Resource not found', '') : errorBox(e, function () { openResourcePanel(id, true); })); }
  }
  function renderResourcePanel() {
    var r = S.panel.res, p = clear($('#panel')), editable = can('contributor') && !r.archived_at;
    p.setAttribute('data-testid', 'res-panel');
    p.appendChild(el('div', { class: 'panel-head' }, el('div', { class: 'row' }, el('span', { class: 'pill', text: r.kind }), r.archived_at ? el('span', { class: 'pill danger', text: 'archived' }) : null, el('span', { class: 'faint small', text: 'v' + r.version })),
      el('button', { class: 'btn ghost sm', type: 'button', text: '✕', 'aria-label': 'Close', onclick: function () { closePanel(); } })));
    p.appendChild(el('h1', { text: r.title }));
    p.appendChild(el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', class: 'mono', text: r.url }));
    var acts = el('div', { class: 'row', style: 'margin:12px 0' });
    if (editable) acts.appendChild(el('button', { class: 'btn sm', type: 'button', text: 'Edit', 'data-testid': 'res-edit', onclick: editResourceModal }));
    if (!r.archived_at && can('contributor')) acts.appendChild(el('button', { class: 'btn sm danger', type: 'button', text: can('editor') ? 'Archive' : 'Propose archive', 'data-testid': 'res-archive', onclick: async function () {
      if (!await confirmDialog({ title: 'Archive “' + r.title + '”?', body: 'It will be detached from ' + r.used_by + ' record(s). Restoring re-attaches them.', danger: true, confirmLabel: can('editor') ? 'Archive' : 'Send for approval' })) return;
      try { await api('POST', '/resources/' + r.id + '/archive', {}); toast('Archived'); openResourcePanel(r.id, true); if (S.listReload) S.listReload(); }
      catch (x) { if (x.status === 202) { toast('Sent for approval.'); refreshPending(); } else failToast(x); } } }));
    if (r.archived_at && can('editor')) acts.appendChild(el('button', { class: 'btn sm', type: 'button', text: 'Restore', 'data-testid': 'res-restore', onclick: async function () {
      try { await api('POST', '/resources/' + r.id + '/restore'); toast('Restored'); openResourcePanel(r.id, true); if (S.listReload) S.listReload(); } catch (x) { failToast(x); } } }));
    p.appendChild(acts);
    if (r.description) p.appendChild(el('p', { class: 'muted', text: r.description }));
    p.appendChild(el('h3', { text: 'Used by ' + r.nodes.length + ' record(s)' }));
    var ul = el('ul', { class: 'list', 'data-testid': 'res-used-by' });
    if (!r.nodes.length) ul.appendChild(el('li', { class: 'faint small', text: 'Not attached to any record.' }));
    r.nodes.forEach(function (n) { ul.appendChild(el('li', null, typePill(n.type), el('a', { href: '#/records' + qs({ open: n.id }), text: n.name }), n.note ? el('span', { class: 'faint small', text: '— ' + n.note }) : null)); });
    p.appendChild(ul);
    var hist = el('details', null, el('summary', { class: 'small muted', text: 'History' }));
    hist.addEventListener('toggle', function () { if (hist.open && !hist.dataset.loaded) loadHistory(hist, '/resources/' + r.id + '/history'); });
    p.appendChild(el('div', { style: 'margin-top:16px' }, hist));
  }
  function editResourceModal() {
    var r = S.panel.res, err = el('div', { class: 'field-error', role: 'alert' });
    var url = el('input', { value: r.url, 'data-testid': 'res-edit-url' }), title = el('input', { value: r.title, 'data-testid': 'res-edit-title' });
    var kind = el('select'); ['link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other'].forEach(function (k) { kind.appendChild(el('option', { value: k, text: k, selected: r.kind === k })); });
    openModal(el('form', { onsubmit: async function (e) {
      e.preventDefault(); err.textContent = '';
      var body = { version: r.version }; if (url.value.trim() !== r.url) body.url = url.value.trim(); if (title.value !== r.title) body.title = title.value; if (kind.value !== r.kind) body.kind = kind.value;
      if (Object.keys(body).length === 1) { closeModal(); return; }
      try { await api('PATCH', '/resources/' + r.id, body); closeModal(); toast('Saved'); openResourcePanel(r.id, true); if (S.listReload) S.listReload(); }
      catch (x) { err.textContent = x.status === 409 && x.body.error === 'version_conflict' ? 'This resource changed since you opened it (now v' + x.body.current.version + '). Close and reopen to see the latest.' : x.message; }
    } }, el('h2', { text: 'Edit resource' }), el('label', { class: 'field' }, 'URL', url), el('label', { class: 'field' }, 'Title', title), el('label', { class: 'field' }, 'Kind', kind), err,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeModal }), el('button', { class: 'btn primary', type: 'submit', text: 'Save', 'data-testid': 'res-edit-save' }))), { label: 'Edit resource' });
  }

  // ------------------------------------------------------------------ graph
  var SHAPES = { program: 'round-hexagon', course: 'round-rectangle', module: 'ellipse', topic: 'ellipse', instructor: 'round-diamond', process: 'round-triangle' };
  function viewGraph(v, r) {
    var center = r.path[1];
    if (!center) {
      v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Graph' }), el('div', { class: 'muted', text: 'Pick a record to explore its neighbourhood. The graph never loads everything at once.' }))));
      v.appendChild(el('div', { style: 'max-width:420px' }, nodePicker({ placeholder: 'Start from…', testid: 'graph-start', onPick: function (n) { if (n) location.hash = '#/graph/' + n.id; } })));
      return;
    }
    var depth = r.q.depth === '2' ? 2 : 1, hidden = {}, connectFrom = null;
    var info = el('span', { class: 'muted small', 'data-testid': 'graph-info' });
    var depthSel = el('select', { 'aria-label': 'Depth', 'data-testid': 'graph-depth' }, el('option', { value: '1', text: '1 hop', selected: depth === 1 }), el('option', { value: '2', text: '2 hops', selected: depth === 2 }));
    depthSel.addEventListener('change', function () { setQuery({ depth: depthSel.value }); });
    var legend = el('div', { class: 'legend', 'data-testid': 'graph-legend' });
    S.types.forEach(function (t) {
      var cb = el('input', { type: 'checkbox', checked: true, 'data-testid': 'graph-filter-' + t.key });
      cb.addEventListener('change', function () { hidden[t.key] = !cb.checked; applyFilter(); });
      legend.appendChild(el('label', null, cb, el('span', { class: 'pill' }, el('span', { class: 'dot', style: 'background:' + t.color }), t.label)));
    });
    var connectBtn = can('contributor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'graph-connect', text: 'Connect mode', onclick: function () {
      connectFrom = connectFrom === null ? false : null; connectBtn.classList.toggle('primary', connectFrom !== null);
      info.textContent = connectFrom === false ? 'Connect mode: click the source record, then the target.' : status(); } }) : null;
    var wrap = el('div', { class: 'graph-wrap' },
      el('div', { class: 'graph-tools' }, el('a', { class: 'btn sm', href: '#/graph', text: '← Change start' }), depthSel,
        el('button', { class: 'btn sm', type: 'button', text: 'Fit', onclick: function () { cy.fit(undefined, 30); } }), connectBtn, el('span', { class: 'spacer' }), info),
      legend, el('div', { id: 'cy', 'data-testid': 'graph-canvas', role: 'img', 'aria-label': 'Relationship graph' }));
    v.appendChild(wrap);
    if (typeof window.cytoscape !== 'function') { wrap.appendChild(errorBox({ message: 'The graph library did not load.' })); return; }
    var cy = window.cytoscape({ container: $('#cy'), wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 3,
      style: [
        { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', 'font-size': 10, color: getComputedStyle(document.body).getPropertyValue('--text'), 'text-valign': 'bottom', 'text-margin-y': 4, width: 'mapData(degree, 0, 30, 18, 46)', height: 'mapData(degree, 0, 30, 18, 46)', shape: 'data(shape)', 'text-max-width': 120, 'text-wrap': 'ellipsis' } },
        { selector: 'node.center', style: { 'border-width': 3, 'border-color': '#111' } },
        { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#4f46e5' } },
        { selector: 'node.connect-src', style: { 'border-width': 4, 'border-color': '#d97706' } },
        { selector: 'edge', style: { width: 1.2, 'line-color': '#b9b9b2', 'target-arrow-color': '#b9b9b2', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.7, label: 'data(label)', 'font-size': 8, color: '#8a8a83', 'text-rotation': 'autorotate', 'text-opacity': 0 } },
        { selector: 'edge.hover, edge:selected', style: { 'text-opacity': 1, 'line-color': '#4f46e5', 'target-arrow-color': '#4f46e5' } },
        { selector: '.hidden', style: { display: 'none' } }
      ] });
    var expanded = {}, addedBy = {}, totals = {};
    function status() {
      var shown = cy.nodes().filter(function (n) { return !n.hasClass('hidden'); }).length, t = totals[center];
      return 'Showing ' + shown + ' record(s)' + (t && t.truncated ? ' — showing ' + t.shown + ' of ' + t.total + ' in this neighbourhood' : '') + '. Double-click to expand or collapse.';
    }
    async function load(id, d, isRoot) {
      try {
        var nb = await api('GET', '/nodes/' + id + '/neighbourhood' + qs({ depth: d }));
        totals[id] = { truncated: nb.truncated, total: nb.total, shown: nb.nodes.length };
        var batch = [];
        nb.nodes.forEach(function (n) {
          if (cy.getElementById(n.id).length) return;
          addedBy[n.id] = id;
          batch.push({ group: 'nodes', data: { id: n.id, label: n.name, type: n.type, color: n.color, degree: n.degree, shape: SHAPES[n.type] || 'ellipse' } });
        });
        nb.edges.forEach(function (e) { if (!cy.getElementById(e.id).length) batch.push({ group: 'edges', data: { id: e.id, source: e.source_id, target: e.target_id, label: e.label } }); });
        cy.add(batch);
        expanded[id] = true;
        if (isRoot) cy.getElementById(center).addClass('center');
        applyFilter();
        cy.layout({ name: batch.length > 150 ? 'concentric' : 'cose', animate: false, fit: isRoot, padding: 30,
          concentric: function (n) { return n.id() === center ? 10 : 10 - (n.data('degree') > 5 ? 1 : 2); } }).run();
        if (isRoot && cy.zoom() > 1.25) { cy.zoom(1.25); cy.center(); }
        info.textContent = status();
        if (nb.truncated) toast('Showing ' + nb.nodes.length + ' of ' + nb.total + ' records around this one.');
      } catch (e) { if (isRoot) wrap.appendChild(errorBox(e, function () { load(id, d, isRoot); })); else failToast(e, 'Could not expand'); }
    }
    function collapse(id) {
      var gone = Object.keys(addedBy).filter(function (k) { return addedBy[k] === id && k !== center && !expanded[k]; });
      gone.forEach(function (k) { cy.getElementById(k).remove(); delete addedBy[k]; });
      expanded[id] = false; info.textContent = status();
    }
    function applyFilter() {
      cy.nodes().forEach(function (n) { n.toggleClass('hidden', !!hidden[n.data('type')] && n.id() !== center); });
      info.textContent = status();
    }
    cy.on('tap', 'node', function (evt) {
      var n = evt.target;
      if (connectFrom === false) { connectFrom = n; n.addClass('connect-src'); info.textContent = 'Now click the target record.'; return; }
      if (connectFrom && connectFrom !== null) {
        var src = connectFrom; connectFrom = false; src.removeClass('connect-src');
        if (src.id() === n.id()) { info.textContent = 'Pick a different target.'; return; }
        connectModal({ id: src.id(), name: src.data('label'), type: src.data('type') }, { id: n.id(), name: n.data('label'), type: n.data('type') });
        return;
      }
      setQuery({ open: n.id() }, true); openNodePanel(n.id());
    });
    cy.on('mouseover', 'edge', function (e) { e.target.addClass('hover'); });
    cy.on('mouseout', 'edge', function (e) { e.target.removeClass('hover'); });
    cy.on('dbltap', 'node', function (evt) { var id = evt.target.id(); if (expanded[id] && id !== center) collapse(id); else if (!expanded[id]) load(id, 1); });
    S.graph = { cy: cy, reload: function () { cy.elements().remove(); expanded = {}; addedBy = {}; load(center, depth, true); },
                expand: function (id) { return load(id, 1); } };
    window.__kbGraph = S.graph;   // for tests and keyboard users' devtools; holds no data of its own
    load(center, depth, true);
  }

  // ------------------------------------------------------------------ data quality
  async function viewQuality(v) {
    v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Data quality' }), el('div', { class: 'muted', text: 'What is incomplete, unconnected or possibly duplicated. Counts first; fix the top of each list.' }))));
    var out = el('div', { 'data-testid': 'quality' }); v.appendChild(out); out.appendChild(skeleton(6));
    var load = async function () {
      try {
        var q = await api('GET', '/quality'); clear(out);
        var t = q.totals, cards = el('div', { class: 'cards' });
        [['Live records', t.live], ['Not connected', t.orphans], ['No resources', t.no_resources], ['No owner', t.no_owner], ['No summary', t.no_summary]].forEach(function (c) {
          cards.appendChild(el('div', { class: 'card', 'data-testid': 'q-' + c[0].toLowerCase().replace(/ /g, '-') }, el('div', { class: 'muted small', text: c[0] }), el('div', { class: 'num', text: c[1] })));
        });
        out.appendChild(cards);
        out.appendChild(el('h2', { text: 'Completeness by course and program' }));
        if (!q.courses.length) out.appendChild(empty('No courses or programs yet', 'Completeness is the share of a course and its contents that carry at least one resource.'));
        else {
          var tb = el('tbody');
          q.courses.forEach(function (c) {
            var pct = Number(c.completeness);
            tb.appendChild(el('tr', { tabindex: '0', 'data-testid': 'q-course', onclick: function () { setQuery({ open: c.id }); } },
              el('td', null, el('strong', { text: c.name })), el('td', null, typePill(c.type)), el('td', { class: 'small', text: c.contents + ' item(s)' }),
              el('td', null, el('span', { class: 'pill ' + (pct >= 80 ? 'ok' : pct >= 40 ? 'warn' : 'danger'), text: pct + '%' }))));
          });
          out.appendChild(el('table', { class: 'table' }, el('thead', null, el('tr', null, ['Course / program', 'Type', 'Contents', 'With resources'].map(function (h) { return el('th', { text: h }); }))), tb));
        }
        out.appendChild(el('h2', { text: 'Not connected to anything', style: 'margin-top:24px' }));
        var ul = el('ul', { class: 'list', 'data-testid': 'q-orphans' });
        if (!q.orphans.length) ul.appendChild(el('li', { class: 'faint small', text: 'Every record has at least one relationship.' }));
        q.orphans.forEach(function (n) { ul.appendChild(el('li', null, typePill(n.type), el('a', { href: '#/quality' + qs({ open: n.id }), text: n.name }))); });
        out.appendChild(ul);
        out.appendChild(el('h2', { text: 'Possible duplicates', style: 'margin-top:24px' }));
        var dl = el('ul', { class: 'list', 'data-testid': 'q-duplicates' });
        if (!q.duplicates.length) dl.appendChild(el('li', { class: 'faint small', text: 'No similar names found.' }));
        q.duplicates.forEach(function (d) { dl.appendChild(el('li', null, typePill(d.type), el('a', { href: '#/quality' + qs({ open: d.a_id }), text: d.a_name }), el('span', { class: 'faint', text: '↔' }), el('a', { href: '#/quality' + qs({ open: d.b_id }), text: d.b_name }), el('span', { class: 'spacer' }), el('span', { class: 'faint small', text: 'similarity ' + d.similarity }))); });
        out.appendChild(dl);
        out.appendChild(el('p', { class: 'faint small', style: 'margin-top:16px', text: 'Link health is checked by the MCP tool check_broken_links (Google Drive links behind sign-in count as “needs access”, not broken).' }));
      } catch (e) { clear(out).appendChild(errorBox(e, load)); }
    };
    S.listReload = load; load();
  }

  // ------------------------------------------------------------------ proposals
  async function viewProposals(v) {
    v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Approvals' }), el('div', { class: 'muted', text: 'Archive requests from contributors and AI assistants wait here for an editor.' }))));
    var out = el('div', { 'data-testid': 'proposals' }); v.appendChild(out);
    var load = async function () {
      clear(out).appendChild(skeleton(4));
      try {
        var p = await api('GET', '/proposals'); clear(out);
        if (!p.items.length) { out.appendChild(empty('Nothing waiting', 'Proposed archives and removals appear here.')); return; }
        var ul = el('ul', { class: 'list' });
        p.items.forEach(function (x) {
          ul.appendChild(el('li', { 'data-testid': 'proposal' }, el('span', { class: 'pill warn', text: x.action }), el('span', { class: 'pill', text: x.target_table.replace('node_resources', 'resource link').replace(/s$/, '') }),
            x.target_table === 'nodes' ? el('a', { href: '#/proposals' + qs({ open: x.target_id }), text: x.target_label || x.target_id }) : el('span', { text: x.target_label || x.target_id }),
            x.reason ? el('span', { class: 'muted small', text: '“' + x.reason + '”' }) : null,
            el('span', { class: 'faint small', text: 'by ' + actorLabel({ actor_type: x.actor_type, actor_id: x.created_by }) + ' · ' + ago(x.created_at) }), el('span', { class: 'spacer' }),
            can('editor') ? el('button', { class: 'btn sm', type: 'button', text: 'Reject', 'data-testid': 'reject', onclick: function () { decide(x, false); } }) : null,
            can('editor') ? el('button', { class: 'btn sm primary', type: 'button', text: 'Approve', 'data-testid': 'approve', onclick: function () { decide(x, true); } }) : null));
        });
        out.appendChild(ul);
      } catch (e) { clear(out).appendChild(errorBox(e, load)); }
    };
    async function decide(x, yes) {
      if (yes && !await confirmDialog({ title: 'Approve: ' + x.action + ' “' + (x.target_label || '') + '”?', body: 'This executes the change now.', danger: true, confirmLabel: 'Approve' })) return;
      try { await api('POST', '/proposals/' + x.id + '/' + (yes ? 'approve' : 'reject')); toast(yes ? 'Approved and applied' : 'Rejected'); load(); refreshPending(); }
      catch (e) { failToast(e); load(); }
    }
    S.listReload = load; load();
  }
  async function refreshPending() {
    try { var p = await api('GET', '/proposals'); var b = $('#pending-badge'); b.hidden = !p.items.length; b.textContent = p.items.length; } catch (e) { /* badge stays as is */ }
  }

  // ------------------------------------------------------------------ settings
  async function viewSettings(v) {
    v.appendChild(el('div', { class: 'page-head' }, el('div', null, el('h1', { text: 'Settings' }), el('div', { class: 'muted', text: 'Your role is ' + S.me.role + '.' }))));
    // tokens
    var tok = el('section', { 'data-testid': 'tokens' }); v.appendChild(tok);
    tok.appendChild(el('h2', { text: 'API tokens for Claude (MCP)' }));
    tok.appendChild(el('p', { class: 'muted small', text: 'A token lets an AI assistant act as you, with your role, through the MCP server. It is shown once. Archive and delete requests made with it always need a person\'s approval.' }));
    var nameIn = el('input', { placeholder: 'Token name, e.g. “laptop Claude Code”', 'aria-label': 'Token name', 'data-testid': 'token-name', maxlength: '80' });
    var days = el('select', { 'aria-label': 'Expiry' }, el('option', { value: '30', text: '30 days' }), el('option', { value: '90', text: '90 days', selected: true }), el('option', { value: '365', text: '1 year' }));
    tok.appendChild(el('div', { class: 'row' }, nameIn, days, el('button', { class: 'btn primary', type: 'button', text: 'Create token', 'data-testid': 'token-create', onclick: async function () {
      if (!nameIn.value.trim()) { nameIn.focus(); toast('Name the token first.', { error: true }); return; }
      try {
        var t = await api('POST', '/tokens', { name: nameIn.value.trim(), expires_in_days: parseInt(days.value, 10) });
        nameIn.value = ''; loadTokens();
        var code = el('input', { readonly: true, value: t.token, class: 'mono', style: 'width:100%', 'data-testid': 'token-value', 'aria-label': 'Token' });
        openModal(el('div', null, el('h2', { text: 'Copy your token now' }), el('p', { class: 'muted', text: 'It will not be shown again. Put it in KB_MCP_TOKEN for the MCP server (docs/MCP.md).' }), code,
          el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Copy', onclick: function () { code.select(); try { navigator.clipboard.writeText(t.token); toast('Copied'); } catch (e) { document.execCommand('copy'); } } }),
            el('button', { class: 'btn primary', type: 'button', text: 'Done', onclick: closeModal }))), { label: 'New token' });
        code.select();
      } catch (e) { failToast(e, 'Token not created'); }
    } })));
    var tlist = el('ul', { class: 'list', style: 'margin-top:12px' }); tok.appendChild(tlist);
    async function loadTokens() {
      clear(tlist).appendChild(el('li', { class: 'faint', text: 'Loading…' }));
      try {
        var t = await api('GET', '/tokens'); clear(tlist);
        if (!t.items.length) tlist.appendChild(el('li', { class: 'faint small', text: 'No tokens.' }));
        t.items.forEach(function (x) {
          var dead = x.revoked_at || (x.expires_at && new Date(x.expires_at) < new Date());
          tlist.appendChild(el('li', { 'data-testid': 'token-row' }, el('strong', { text: x.name }), el('span', { class: 'mono faint', text: x.prefix + '…' }),
            el('span', { class: 'pill ' + (dead ? 'danger' : 'ok'), text: x.revoked_at ? 'revoked' : dead ? 'expired' : 'active' }),
            el('span', { class: 'faint small', text: x.last_used_at ? 'used ' + ago(x.last_used_at) : 'never used' }), el('span', { class: 'spacer' }),
            dead ? null : el('button', { class: 'btn sm danger', type: 'button', text: 'Revoke', 'data-testid': 'token-revoke', onclick: async function () {
              if (!await confirmDialog({ title: 'Revoke “' + x.name + '”?', body: 'Anything using it stops working immediately.', danger: true, confirmLabel: 'Revoke' })) return;
              try { await api('POST', '/tokens/' + x.id + '/revoke'); toast('Revoked'); loadTokens(); } catch (e) { failToast(e); } } })));
        });
      } catch (e) { clear(tlist).appendChild(el('li', { class: 'field-error', text: e.message })); }
    }
    loadTokens();
    if (!can('admin')) return;
    // members
    var mem = el('section', { style: 'margin-top:32px', 'data-testid': 'members' }); v.appendChild(mem);
    mem.appendChild(el('h2', { text: 'Roles' }));
    mem.appendChild(el('p', { class: 'muted small', text: 'Anyone with an IK profile is a viewer. Grant more here. Admins can also be bootstrapped with pipeline/kb_admins.py.' }));
    var mlist = el('ul', { class: 'list' }); mem.appendChild(mlist);
    async function loadMembers() {
      try {
        var m = await api('GET', '/members'); clear(mlist);
        m.items.forEach(function (x) {
          var sel = el('select', { 'aria-label': 'Role for ' + (x.email || x.user_id) });
          ['viewer', 'contributor', 'editor', 'admin'].forEach(function (r) { sel.appendChild(el('option', { value: r, text: r, selected: x.role === r })); });
          sel.addEventListener('change', async function () { try { await api('POST', '/members/' + x.user_id, { role: sel.value }); toast('Role updated'); } catch (e) { failToast(e); loadMembers(); } });
          mlist.appendChild(el('li', null, el('span', { text: x.email || x.user_id }), el('span', { class: 'spacer' }), sel));
        });
      } catch (e) { clear(mlist).appendChild(el('li', { class: 'field-error', text: e.message })); }
    }
    loadMembers();
    // types
    var ty = el('section', { style: 'margin-top:32px', 'data-testid': 'types' }); v.appendChild(ty);
    ty.appendChild(el('h2', { text: 'Record types and relationship rules' }));
    var tl = el('ul', { class: 'list' });
    S.types.forEach(function (t) { tl.appendChild(el('li', null, typePill(t.key), el('span', { class: 'mono faint', text: t.key }), t.is_container ? el('span', { class: 'pill', text: 'container' }) : null, el('span', { class: 'muted small', text: t.description || '' }))); });
    ty.appendChild(tl);
    var key = el('input', { placeholder: 'key (e.g. lab)', 'aria-label': 'Type key', pattern: '[a-z][a-z0-9_]+' }), label = el('input', { placeholder: 'Label', 'aria-label': 'Type label' });
    var color = el('input', { type: 'color', value: '#64748b', 'aria-label': 'Colour' });
    ty.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, key, label, color, el('button', { class: 'btn', type: 'button', text: 'Add type', onclick: async function () {
      try { await api('POST', '/types/node', { key: key.value.trim(), label: label.value.trim(), color: color.value }); setTypes(await api('GET', '/types')); toast('Type added'); lastViewKey = null; route(); } catch (e) { failToast(e); } } })));
    var rules = el('ul', { class: 'list', style: 'margin-top:12px' });
    S.edgeTypes.forEach(function (et) { rules.appendChild(el('li', null, el('strong', { text: et.label }), el('span', { class: 'muted small', text: et.rules.map(function (r) { return r.source + ' → ' + r.target; }).join(' · ') || 'no rules (accepts nothing)' }))); });
    ty.appendChild(rules);
    var rt = el('select', { 'aria-label': 'Relationship' }), rs = el('select', { 'aria-label': 'From type' }), rtg = el('select', { 'aria-label': 'To type' });
    S.edgeTypes.forEach(function (et) { rt.appendChild(el('option', { value: et.key, text: et.label })); });
    S.types.forEach(function (t) { rs.appendChild(el('option', { value: t.key, text: t.label })); rtg.appendChild(el('option', { value: t.key, text: t.label })); });
    ty.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, rs, rt, rtg, el('button', { class: 'btn', type: 'button', text: 'Allow', onclick: async function () {
      try { await api('POST', '/types/rule', { type: rt.value, source_type: rs.value, target_type: rtg.value }); setTypes(await api('GET', '/types')); toast('Rule added'); lastViewKey = null; route(); } catch (e) { failToast(e); } } })));
  }

  // ------------------------------------------------------------------ palette
  var pal = { items: [], active: 0 };
  function openPalette() { $('#palette').hidden = false; var i = $('#palette-input'); i.value = ''; i.focus(); renderPalette(''); }
  function closePalette() { $('#palette').hidden = true; }
  var palSearch = debounce(function (q) { renderPalette(q); }, 150);
  $('#palette-input').addEventListener('input', function (e) { palSearch(e.target.value.trim()); });
  $('#palette-input').addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); pal.active = Math.min(pal.active + 1, pal.items.length - 1); paintPalette(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); pal.active = Math.max(pal.active - 1, 0); paintPalette(); }
    else if (e.key === 'Enter') { e.preventDefault(); var it = pal.items[pal.active]; if (it) it.run(); }
    else if (e.key === 'Escape') closePalette();
  });
  async function renderPalette(q) {
    var list = clear($('#palette-results')); pal.items = []; pal.active = 0;
    var sections = [];
    if (q) {
      try {
        var r = await api('GET', '/search' + qs({ q: q, limit: 8 }));
        if ($('#palette-input').value.trim() !== q) return;
        if (r.nodes.length) sections.push(['Records', r.nodes.map(function (n) { return { label: n.name, pill: n.type, sub: n.scope_name, testid: 'palette-node', run: function () { closePalette(); setQuery({ open: n.id, res: null }); } }; })]);
        if (r.resources.length) sections.push(['Resources', r.resources.map(function (x) { return { label: x.title, sub: x.url, testid: 'palette-res', run: function () { closePalette(); location.hash = '#/resources' + qs({ res: x.id }); } }; })]);
      } catch (e) { sections.push(['Search failed', [{ label: e.message, run: function () {} }]]); }
      if (can('contributor')) sections.push(['Create', S.types.map(function (t) { return { label: 'Create ' + t.label.toLowerCase() + ' “' + q + '”', testid: 'palette-create-' + t.key, run: function () { closePalette(); quickCreate(t.key, q); } }; })]);
    } else {
      sections.push(['Go to', [['Dashboard', '#/'], ['All records', '#/records'], ['Programs', '#/programs'], ['Courses', '#/courses'], ['Resources', '#/resources'], ['Graph', '#/graph'], ['Approvals', '#/proposals'], ['Settings', '#/settings']].map(function (x) { return { label: x[0], run: function () { closePalette(); location.hash = x[1]; } }; })]);
      if (can('contributor')) sections.push(['Create', [{ label: 'New record…', run: function () { closePalette(); createNodeModal({}); } }, { label: 'New resource…', run: function () { closePalette(); newResourceModal(); } }]]);
    }
    sections.forEach(function (s) {
      list.appendChild(el('li', { class: 'section', text: s[0] }));
      s[1].forEach(function (it) {
        var idx = pal.items.length; pal.items.push(it);
        it.li = el('li', { role: 'option', 'data-testid': it.testid || 'palette-item', onmousedown: function (e) { e.preventDefault(); it.run(); }, onmousemove: function () { pal.active = idx; paintPalette(); } },
          it.pill ? typePill(it.pill) : null, el('span', { text: it.label }), it.sub ? el('span', { class: 'faint small', text: it.sub }) : null);
        list.appendChild(it.li);
      });
    });
    paintPalette();
  }
  function paintPalette() { pal.items.forEach(function (it, i) { it.li.classList.toggle('active', i === pal.active); it.li.setAttribute('aria-selected', i === pal.active ? 'true' : 'false'); }); }
  async function quickCreate(type, name) {
    try { var n = await api('POST', '/nodes', { type: type, name: name }); toast('Created ' + n.name); setQuery({ open: n.id, res: null }); if (S.listReload) S.listReload(); }
    catch (e) {
      if (e.status === 409 && e.body.existing) toast(e.message, { error: true, action: { label: 'Open existing', fn: function () { setQuery({ open: e.body.existing.id }); } } });
      else if (e.status === 422) createNodeModal({ type: type, name: name });
      else failToast(e, 'Not created');
    }
  }

  // ------------------------------------------------------------------ collaboration: change feed
  /* Poll the audit-log change feed (RLS-scoped). Lists refresh when someone
     else changes something; an open record whose version moved shows a banner
     instead of silently swapping content under the editor's cursor. On a
     network failure it backs off, and on recovery it refetches the view. */
  function startFeed() {
    api('GET', '/changes').then(function (r) { S.feedCursor = r.cursor; schedule(); }).catch(function () { schedule(); });
    function schedule() { setTimeout(tick, document.hidden ? POLL_MS * 3 : Math.min(POLL_MS * Math.pow(2, S.feedFails), 60000)); }
    async function tick() {
      if (S.feedCursor === null) { try { S.feedCursor = (await api('GET', '/changes')).cursor; } catch (e) { S.feedFails++; } schedule(); return; }
      try {
        var r = await api('GET', '/changes' + qs({ since: S.feedCursor }));
        var recovered = S.feedFails > 0; S.feedFails = 0; S.feedCursor = r.cursor;
        var others = r.changes.filter(function (c) { return c.actor_id !== S.me.user_id || c.actor_type !== 'human'; });
        if (others.length || recovered) onRemoteChanges(others, recovered);
      } catch (e) { S.feedFails = Math.min(S.feedFails + 1, 5); }
      schedule();
    }
  }
  var softReload = debounce(function () { if (S.listReload && !document.querySelector('.view textarea:focus, .view input:focus')) S.listReload(); }, 800);
  function onRemoteChanges(changes, recovered) {
    if (recovered) softReload();
    if (changes.length) { softReload(); refreshPending(); }
    var p = S.panel;
    if (!p) return;
    var hit = changes.filter(function (c) { return c.row_id === p.id || (p.kind === 'node' && ['edges', 'node_resources', 'node_tags'].indexOf(c.table_name) >= 0); });
    if (!hit.length) return;
    var own = hit.filter(function (c) { return c.row_id === p.id; });
    var editing = document.querySelector('#panel textarea, #panel [contenteditable]:focus');
    if (own.length && p.kind === 'node' && p.node && own.some(function (c) { return Number(c.version) > p.node.version; })) {
      if (editing) showLive(actorLabel(own[own.length - 1]) + ' just changed this record. Saving now will show you both versions.');
      else { openNodePanel(p.id, true); showLive(actorLabel(own[own.length - 1]) + ' just updated this record — showing the latest.', true); }
    } else if (!editing && p.kind === 'node') openNodePanel(p.id, true);
  }
  function showLive(msg, auto) {
    var b = clear($('#live-banner')); b.hidden = false; b.setAttribute('data-testid', 'live-banner');
    add(b, [el('span', { text: msg }), el('span', { class: 'spacer' }), el('button', { class: 'btn sm', type: 'button', text: auto ? 'Dismiss' : 'Reload', onclick: function () { hideLive(); if (!auto && S.panel) openNodePanel(S.panel.id, true); } })]);
  }
  function hideLive() { $('#live-banner').hidden = true; }

  boot();
})();
