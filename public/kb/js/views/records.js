/* Records table: one-row toolbar (search, Filter → removable chips, sort, view
   options, export), saved views as tabs, sticky header, hover actions, bulk
   bar, density toggle, result count, keyboard (j/k, Enter, x, e, /). */
import { S, el, add, $, $$, clear, icon, typeIcon, typeLabel, api, toast, failToast, avatar, personName, ago, qs, menu, popover, can, setQuery,
  skeletonRows, empty, errorBox, debounce, openDialog, closeDialog, combobox, nodeSource, confirmDialog, plural, you } from '../core.js';
import { openRecordForm, fieldDisplay } from '../form.js';

const FIXED = { programs: 'program', courses: 'course' };
const COLS = [['scope', 'Course / program'], ['owner', 'Owner'], ['links', 'Links'], ['updated', 'Updated']];

function prefs() { try { return JSON.parse(localStorage.getItem('kb_table') || '{}'); } catch (e) { return {}; } }
function savePrefs(p) { try { localStorage.setItem('kb_table', JSON.stringify(p)); } catch (e) { /* ignore */ } }

export function viewRecords(v, r) {
  const fixed = FIXED[r.path[0]] || null;
  const title = fixed ? typeLabel(fixed, true) : 'All records';
  const p = prefs();
  const cols = p.cols || { scope: true, owner: true, links: true, updated: true };
  let f = filtersFrom(r.q, fixed);
  let items = [], cursor = null, total = null, selected = new Set(), cur = -1, views = [];

  const count = el('span', { class: 'sub', 'data-testid': 'result-count' });
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: title }), count, el('span', { class: 'spacer' }),
    can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': fixed ? 'new-' + fixed : 'new-record-page',
      onclick: () => openRecordForm(fixed ? { type: fixed } : {}) }, icon('plus'), fixed ? 'New ' + typeLabel(fixed).toLowerCase() : 'New record') : null));

  // saved views (D6)
  const tabs = el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Saved views', 'data-testid': 'saved-views' });
  v.appendChild(tabs);
  async function loadViews() {
    try { views = (await api('GET', '/views')).items.filter((x) => (x.config.fixed || null) === fixed); } catch (e) { views = []; }
    drawTabs();
  }
  function drawTabs() {
    clear(tabs);
    tabs.appendChild(el('button', { type: 'button', role: 'tab', 'aria-selected': !f.view ? 'true' : 'false', text: 'All', onclick: () => applyView(null) }));
    views.forEach((x) => tabs.appendChild(el('button', { type: 'button', role: 'tab', 'aria-selected': f.view === x.id ? 'true' : 'false', 'data-testid': 'view-tab',
      onclick: () => applyView(x), oncontextmenu: (e) => { e.preventDefault(); viewMenu(e.currentTarget, x); } },
      x.shared ? icon('users', 'sm') : null, x.name, f.view === x.id ? el('span', { class: 'btn ghost sm icon', role: 'button', 'aria-label': 'View options', onclick: (e) => { e.stopPropagation(); viewMenu(e.currentTarget, x); } }, icon('chevron-down', 'sm')) : null)));
    tabs.appendChild(el('button', { type: 'button', 'data-testid': 'save-view', onclick: saveViewDialog }, icon('plus', 'sm'), 'Save view'));
  }
  function applyView(x) {
    const q = x ? Object.assign({}, x.config, { view: x.id }) : {};
    delete q.fixed;
    location.hash = '#/' + r.path[0] + qs(q);
  }
  function viewMenu(anchor, x) {
    menu(anchor, [
      x.mine ? { label: 'Update with current filters', icon: 'refresh-cw', fn: async () => { await api('PATCH', '/views/' + x.id, { config: Object.assign(currentConfig(), { fixed }) }); toast('View updated'); loadViews(); } } : null,
      x.mine ? { label: x.shared ? 'Make personal' : 'Share with the team', icon: 'users', fn: async () => { await api('PATCH', '/views/' + x.id, { shared: !x.shared }); loadViews(); } } : null,
      x.mine ? { label: 'Delete view', icon: 'trash-2', danger: true, fn: async () => { await api('DELETE', '/views/' + x.id); applyView(null); loadViews(); } } : { label: 'Shared by ' + personName(x.owner_id), icon: 'users', fn: () => {} },
    ]);
  }
  function saveViewDialog() {
    const name = el('input', { 'aria-label': 'View name', 'data-testid': 'view-name', placeholder: 'e.g. My drafts' });
    const shared = el('input', { type: 'checkbox', 'aria-label': 'Share with the team', 'data-testid': 'view-shared' });
    openDialog([el('h2', { text: 'Save this view' }), el('p', { class: 'muted small', text: 'Saves the current filters and sort as a tab.' }),
      el('label', { class: 'field' }, el('span', { class: 'label', text: 'Name' }), name), el('label', { class: 'row small' }, shared, 'Share with the team'),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', text: 'Save', 'data-testid': 'view-save', onclick: async () => {
          if (!name.value.trim()) { name.focus(); return; }
          try { const x = await api('POST', '/views', { name: name.value.trim(), shared: shared.checked, config: Object.assign(currentConfig(), { fixed }) }); closeDialog(); views.push(x); applyView(x); loadViews(); }
          catch (e) { failToast(e, 'Not saved'); } } }))], { label: 'Save view' });
  }
  function currentConfig() { const c = {}; ['q', 'type', 'parent', 'owner', 'tag', 'status', 'flagged', 'review', 'sort'].forEach((k) => { if (f[k]) c[k] = f[k]; }); return c; }

  // toolbar
  const search = el('input', { placeholder: 'Search', 'aria-label': 'Search records', 'data-testid': 'filter-q', value: f.q || '' });
  search.addEventListener('input', debounce(() => setQuery({ q: search.value.trim() || null, view: null }, true), 250));
  const toolbar = el('div', { class: 'toolbar' },
    el('div', { class: 'input-icon search' }, icon('search'), search),
    el('button', { class: 'btn', type: 'button', 'data-testid': 'filter-button', onclick: (e) => filterMenu(e.currentTarget) }, icon('filter', 'sm'), 'Filter'),
    el('button', { class: 'btn', type: 'button', 'data-testid': 'sort', onclick: (e) => menu(e.currentTarget, [
      { label: 'Recently updated', checked: f.sort !== 'name', fn: () => setQuery({ sort: null }) },
      { label: 'Name A–Z', checked: f.sort === 'name', fn: () => setQuery({ sort: 'name' }), testid: 'sort-name' }]) }, icon('arrow-up-down', 'sm'), f.sort === 'name' ? 'Name' : 'Updated'),
    el('span', { class: 'spacer' }),
    el('button', { class: 'btn ghost', type: 'button', 'data-testid': 'view-options', onclick: (e) => optionsMenu(e.currentTarget) }, icon('sliders-horizontal', 'sm'), 'View'),
    el('button', { class: 'btn ghost', type: 'button', 'data-testid': 'export-csv', onclick: exportCsv }, icon('download', 'sm'), 'Export'));
  const chips = el('div', { class: 'chips', 'data-testid': 'filter-chips' });
  v.append(el('div', { style: 'height:12px' }), toolbar, chips);
  const tableHost = el('div', { class: 'table-wrap' + (p.compact ? ' compact' : ''), style: 'position:relative' });
  const foot = el('div', { class: 'table-foot' });
  v.append(tableHost, foot);
  const bulk = el('div', { class: 'bulk-bar', hidden: true, 'data-testid': 'bulk-bar' });
  v.appendChild(bulk);

  function filterMenu(anchor) {
    const items = [];
    if (!fixed) { items.push({ header: true, label: 'Type' }); S.types.forEach((t) => items.push({ node: el('span', { class: 'row' }, typeIcon(t.key), t.label), testid: 'filter-type-' + t.key, fn: () => setQuery({ type: t.key, view: null }) })); items.push('-'); }
    items.push({ label: 'In a course or program…', icon: 'book-open', testid: 'filter-parent', fn: parentPicker });
    items.push({ label: 'Owned by me', icon: 'user', testid: 'filter-owner-me', fn: () => setQuery({ owner: 'me', view: null }) });
    items.push({ label: 'Without an owner', icon: 'circle-dot', testid: 'filter-no-owner', fn: () => setQuery({ owner: 'none', view: null }) });
    items.push({ label: 'Owner…', icon: 'users', fn: ownerPicker });
    items.push({ label: 'Tag…', icon: 'tag', fn: tagPicker });
    items.push('-');
    items.push({ label: 'Drafts', icon: 'pencil', testid: 'filter-draft', fn: () => setQuery({ status: 'draft', view: null }) });
    items.push({ label: 'Needs review', icon: 'badge-check', fn: () => setQuery({ review: 'needs_review', view: null }) });
    items.push({ label: 'Flagged as incorrect', icon: 'flag', testid: 'filter-flagged', fn: () => setQuery({ flagged: '1', view: null }) });
    items.push({ label: 'Archived', icon: 'archive', fn: () => setQuery({ status: 'archived', view: null }) });
    menu(anchor, items, { testid: 'filter-menu' });
  }
  function pickDialog(title, cb, apply) {
    let val = null;
    const c = cb((x) => { val = x; });
    openDialog([el('h2', { text: title }), c, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', text: 'Apply', 'data-testid': 'filter-apply', onclick: () => { if (val) { closeDialog(); apply(val); } } }))], { label: title });
  }
  function parentPicker() { pickDialog('Show records in…', (on) => combobox({ testid: 'filter-parent-picker', placeholder: 'Search programs, courses, modules…', source: nodeSource(['program', 'course', 'domain', 'module', 'week']), onChange: on }), (x) => setQuery({ parent: x.id, view: null })); }
  function ownerPicker() { pickDialog('Owner', (on) => combobox({ placeholder: 'Search people', source: async (q) => S.people.filter((p) => !q || p.email.includes(q)).map((p) => ({ id: p.user_id, label: personName(p.user_id), sub: p.email, icon: avatar(p.user_id) })), onChange: on }), (x) => setQuery({ owner: x.id, view: null })); }
  function tagPicker() { pickDialog('Tag', (on) => combobox({ placeholder: 'Search tags', source: async (q) => (await api('GET', '/tags')).items.filter((t) => !q || t.name.includes(q)).map((t) => ({ id: t.id, label: '#' + t.name })), onChange: on }), (x) => setQuery({ tag: x.id, tag_name: x.label, view: null })); }
  // A list of one type shows that type's custom fields as optional columns.
  function typeFields() { const t = S.typeByKey[fixed || f.type]; return t ? (t.fields || []).filter((x) => !x.archived) : []; }
  function fieldOn(k) { return (p.fieldCols || {})[(fixed || f.type) + ':' + k] !== false; }
  /* View settings (A4): a popover that stays inside the viewport, with a
     labelled density switch and one checkbox per column; drag a row by its
     handle (or use the arrows) to reorder the columns. */
  function optionsMenu(anchor) {
    const seg = el('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Row density' });
    const setDensity = (c) => { p.compact = c; savePrefs(p); tableHost.classList.toggle('compact', c); $$('button', seg).forEach((b) => b.setAttribute('aria-checked', String((b.dataset.v === 'compact') === c))); };
    [['comfortable', 'Comfortable'], ['compact', 'Compact']].forEach(([k, l]) => seg.appendChild(el('button', { type: 'button', role: 'radio', 'data-v': k, 'data-testid': 'density-' + k,
      'aria-checked': String((k === 'compact') === !!p.compact), text: l, onclick: () => setDensity(k === 'compact') })));
    const list = el('ul', { class: 'check-list', 'data-testid': 'column-list' });
    let dragId = null;
    const drawList = () => {
      clear(list);
      columnOrder().forEach((c) => {
        const li = el('li', { draggable: 'true', 'data-col': c.id, 'data-testid': 'col-row-' + c.id.replace(':', '-'),
          ondragstart: (e) => { dragId = c.id; e.dataTransfer.effectAllowed = 'move'; },
          ondragover: (e) => { e.preventDefault(); li.classList.add('drag-over'); },
          ondragleave: () => li.classList.remove('drag-over'),
          ondrop: (e) => { e.preventDefault(); li.classList.remove('drag-over'); moveColumn(dragId, c.id); drawList(); draw(); } },
          el('span', { class: 'grip', title: 'Drag to reorder', 'aria-hidden': 'true' }, icon('grip-vertical', 'sm')),
          el('label', null, el('input', { type: 'checkbox', checked: c.on, 'data-testid': c.field ? 'col-field-' + c.field.key : 'col-' + c.id,
            onchange: (e) => { setColumn(c, e.target.checked); draw(); } }), el('span', { class: 'truncate', text: c.label })),
          el('span', { class: 'row', style: 'gap:0' },
            el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Move ' + c.label + ' up', onclick: () => { moveBy(c.id, -1); drawList(); draw(); } }, icon('chevron-up', 'sm')),
            el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Move ' + c.label + ' down', onclick: () => { moveBy(c.id, 1); drawList(); draw(); } }, icon('chevron-down', 'sm'))));
        list.appendChild(li);
      });
    };
    drawList();
    popover(anchor, [el('div', { class: 'popover-label', text: 'Density' }), seg, el('div', { class: 'popover-label', text: 'Columns' }), list,
      el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'columns-reset', onclick: () => { delete p.order; delete p.widths; Object.assign(cols, { scope: true, owner: true, links: true, updated: true }); p.cols = cols; savePrefs(p); drawList(); draw(); } }, icon('rotate-ccw', 'sm'), 'Reset columns')],
    { alignRight: true, testid: 'view-popover', label: 'View settings' });
  }
  // Columns other than Name: built-ins and (for a one-type list) the type's fields, in the saved order.
  function columnOrder() {
    const all = COLS.map(([k, label]) => ({ id: k, label, on: !!cols[k] }))
      .concat(typeFields().map((x) => ({ id: 'field:' + x.key, label: x.label, on: fieldOn(x.key), field: x })));
    const order = p.order || [];
    const rank = (c) => { const i = order.indexOf(c.id); return i < 0 ? 100 + all.indexOf(c) : i; };
    return all.slice().sort((a, b) => rank(a) - rank(b));
  }
  function setColumn(c, on) {
    if (c.field) { p.fieldCols = p.fieldCols || {}; p.fieldCols[(fixed || f.type) + ':' + c.field.key] = on; } else { cols[c.id] = on; p.cols = cols; }
    savePrefs(p);
  }
  function moveColumn(from, to) {
    if (!from || from === to) return;
    const ids = columnOrder().map((c) => c.id); ids.splice(ids.indexOf(from), 1); ids.splice(ids.indexOf(to), 0, from);
    p.order = ids; savePrefs(p);
  }
  function moveBy(id, d) {
    const ids = columnOrder().map((c) => c.id); const i = ids.indexOf(id), j = i + d;
    if (j < 0 || j >= ids.length) return; ids.splice(i, 1); ids.splice(j, 0, id); p.order = ids; savePrefs(p);
  }
  const DEFAULT_W = { scope: 220, owner: 72, links: 72, updated: 104 };
  function colWidth(id) { return (p.widths || {})[id] || DEFAULT_W[id] || 140; }
  // Drag the right edge of a header to resize that column; saved per browser.
  function resizer(id, th) {
    const h = el('span', { class: 'col-resize', role: 'separator', 'aria-orientation': 'vertical', 'aria-label': 'Resize column', 'data-testid': 'col-resize-' + id.replace(':', '-'),
      onclick: (e) => e.stopPropagation(),
      onmousedown: (e) => {
        e.preventDefault(); e.stopPropagation(); h.classList.add('dragging');
        const x0 = e.clientX, w0 = th.getBoundingClientRect().width;
        const mv = (ev) => { th.style.width = Math.max(56, Math.round(w0 + ev.clientX - x0)) + 'px'; };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); h.classList.remove('dragging');
          p.widths = Object.assign({}, p.widths, { [id]: parseInt(th.style.width, 10) }); savePrefs(p); };
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      } });
    return h;
  }

  async function drawChips() {
    clear(chips);
    const chip = (label, value, key) => chips.appendChild(el('span', { class: 'chip', 'data-testid': 'chip-' + key }, label + ' ', el('b', { text: value }),
      el('button', { type: 'button', 'aria-label': 'Remove filter ' + label, onclick: () => setQuery({ [key]: null, view: null, ...(key === 'tag' ? { tag_name: null } : {}) }) }, icon('x', 'sm'))));
    if (f.type && !fixed) chip('Type is', typeLabel(f.type), 'type');
    if (f.owner) chip('Owner', f.owner === 'me' ? 'me' : f.owner === 'none' ? 'nobody' : personName(f.owner), 'owner');
    if (f.tag) chip('Tag', f.tag_name || 'tag', 'tag');
    if (f.status && f.status !== 'live') chip('Status', f.status, 'status');
    if (f.flagged) chip('Is', 'flagged', 'flagged');
    if (f.review) chip('Review', 'needs review', 'review');
    if (f.parent) { const c = chip('In', '…', 'parent'); api('GET', '/nodes/' + f.parent).then((n) => { const b = $('[data-testid="chip-parent"] b', chips); if (b) b.textContent = n.name; }).catch(() => {}); }
  }

  function params(extra) {
    return Object.assign({ q: f.q, type: fixed || f.type, parent: f.parent, tag: f.tag, status: f.status || 'live', flagged: f.flagged ? 1 : null,
      review_status: f.review, sort: f.sort || 'updated', owner: f.owner === 'me' ? S.me.user_id : (f.owner && f.owner !== 'none' ? f.owner : null), no_owner: f.owner === 'none' ? 1 : null }, extra || {});
  }
  async function load(more) {
    if (!more) { clear(tableHost).appendChild(skeletonRows(10, 3)); items = []; cursor = null; selected.clear(); cur = -1; drawBulk(); }
    try {
      const page = await api('GET', '/nodes' + qs(params({ cursor: more ? cursor : null, limit: 100 })));
      items = items.concat(page.items); cursor = page.next_cursor; if (page.total !== null && page.total !== undefined) total = page.total;
      draw();
    } catch (e) { clear(tableHost).appendChild(errorBox(e, () => load(false))); }
  }
  S.listReload = () => load(false);
  function draw() {
    clear(tableHost);
    count.textContent = total === null ? '' : plural(total, 'record');
    if (!items.length) {
      const filtered = f.q || f.type || f.parent || f.owner || f.tag || f.flagged || f.review || (f.status && f.status !== 'live');
      tableHost.appendChild(filtered ? empty('Nothing matches', 'Try fewer filters or a different search.', el('button', { class: 'btn sm', type: 'button', text: 'Clear filters', onclick: () => { location.hash = '#/' + r.path[0]; } }), 'search')
        : empty('No ' + title.toLowerCase() + ' yet', 'Create the first one; it takes one form.', can('contributor') ? el('button', { class: 'btn primary sm', type: 'button', text: 'New ' + (fixed ? typeLabel(fixed).toLowerCase() : 'record'), onclick: () => openRecordForm(fixed ? { type: fixed } : {}) }) : null, 'inbox', 'creating-records'));
      clear(foot); return;
    }
    const allBox = el('input', { type: 'checkbox', 'aria-label': 'Select all shown', 'data-testid': 'select-all', onclick: (e) => { e.stopPropagation(); if (allBox.checked) items.forEach((n) => selected.add(n.id)); else selected.clear(); draw(); drawBulk(); } });
    allBox.checked = selected.size && selected.size === items.length;
    const shown = columnOrder().filter((c) => c.on);
    const nameTh = el('th', { class: 'resizable', text: 'Name', style: p.widths && p.widths.name ? 'width:' + p.widths.name + 'px' : null });
    nameTh.appendChild(resizer('name', nameTh));
    const head = el('tr', null, el('th', { style: 'width:44px' }, allBox), nameTh,
      shown.map((c) => { const th = el('th', { class: 'resizable' + (c.id === 'links' ? ' num' : '') + (['scope', 'links'].includes(c.id) || c.field ? ' col-optional' : ''),
        style: 'width:' + colWidth(c.id) + 'px', text: c.label, 'data-testid': c.field ? 'th-field-' + c.field.key : 'th-' + c.id }); th.appendChild(resizer(c.id, th)); return th; }),
      el('th', { style: 'width:72px', 'aria-label': 'Actions' }));
    const tb = el('tbody');
    items.forEach((n, i) => {
      const box = el('input', { type: 'checkbox', 'aria-label': 'Select ' + n.name, checked: selected.has(n.id), 'data-testid': 'row-check',
        onclick: (e) => { e.stopPropagation(); if (box.checked) selected.add(n.id); else selected.delete(n.id); drawBulk(); } });
      const tr = el('tr', { 'data-id': n.id, 'data-testid': 'row', tabindex: '-1', class: (S.panel && S.panel.id === n.id ? 'selected' : '') + (i === cur ? ' cursor' : ''),
        onclick: () => { cur = i; setQuery({ open: n.id, res: null }); } },
        el('td', null, box),
        // Full name and description on hover (A5); comfortable density wraps the description to two lines.
        el('td', { title: n.name + (n.summary ? '\n\n' + n.summary : ''), 'data-testid': 'cell-name' }, el('div', { class: 'cell-stack' }, typeIcon(n.type),
          el('div', { class: 'head' }, el('span', { class: 'name', text: n.name }),
            n.status === 'draft' ? el('span', { class: 'badge warn', text: 'Draft' }) : null, n.archived_at ? el('span', { class: 'badge danger', text: 'Archived' }) : null,
            n.flags ? el('span', { class: 'badge danger', title: 'Flagged as incorrect' }, icon('flag', 'sm')) : null),
          n.summary ? el('span', { class: 'desc', text: n.summary, 'data-testid': 'cell-desc' }) : null)),
        shown.map((c) => c.field ? el('td', { class: 'col-optional truncate small' }, fieldDisplay(c.field, (n.props || {})[c.field.key]))
          : c.id === 'scope' ? el('td', { class: 'col-optional truncate faint', title: n.scope_name || '', text: n.scope_name || '' })
            : c.id === 'owner' ? el('td', null, avatar(n.owner_id))
              : c.id === 'links' ? el('td', { class: 'col-optional num faint', text: n.links ? String(n.links) : '' })
                : el('td', { class: 'faint', title: n.updated_at ? new Date(n.updated_at).toLocaleString() : '', text: ago(n.updated_at) })),
        el('td', null, el('span', { class: 'row-actions' },
          el('a', { class: 'btn ghost sm icon', href: '#/r/' + n.id, title: 'Open as a page', 'aria-label': 'Open ' + n.name + ' as a page', onclick: (e) => e.stopPropagation() }, icon('maximize-2', 'sm')),
          can('contributor') ? el('button', { class: 'btn ghost sm icon', type: 'button', title: 'Edit', 'aria-label': 'Edit ' + n.name, onclick: async (e) => { e.stopPropagation(); try { openRecordForm({ edit: await api('GET', '/nodes/' + n.id) }); } catch (er) { failToast(er); } } }, icon('pencil', 'sm')) : null)));
      tb.appendChild(tr);
    });
    tableHost.appendChild(el('table', { class: 'table', 'data-testid': 'records-table' }, el('thead', null, head), tb));
    clear(foot);
    add(foot, [el('span', { text: 'Showing ' + items.length + (total !== null ? ' of ' + total : '') }), el('span', { class: 'spacer' }),
      cursor ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'load-more', text: 'Load more', onclick: () => load(true) }) : null,
      el('span', { class: 'faint' }, el('kbd', { text: 'j' }), ' ', el('kbd', { text: 'k' }), ' move · ', el('kbd', { text: 'x' }), ' select · ', el('kbd', { text: 'Enter' }), ' open')]);
  }
  function drawBulk() {
    clear(bulk); bulk.hidden = !selected.size;
    if (!selected.size) return;
    const ids = Array.from(selected);
    add(bulk, [el('strong', { text: plural(ids.length, 'record') + ' selected' }),
      can('contributor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'bulk-owner', onclick: (e) => menu(e.currentTarget, [{ label: 'No owner', fn: () => bulkSet({ set: { owner_id: null } }) }]
        .concat(S.people.filter((p) => p.role !== 'viewer').map((p) => ({ node: el('span', { class: 'row' }, avatar(p.user_id), personName(p.user_id)), testid: 'bulk-owner-option', fn: () => bulkSet({ set: { owner_id: p.user_id } }) })))) }, icon('user', 'sm'), 'Owner') : null,
      can('contributor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'bulk-status', onclick: (e) => menu(e.currentTarget, [
        { label: 'Live', fn: () => bulkSet({ set: { status: 'active' } }) }, { label: 'Draft', fn: () => bulkSet({ set: { status: 'draft' } }) },
        { label: 'Needs review', fn: () => bulkSet({ set: { review_status: 'needs_review' } }) }, { label: 'Reviewed', fn: () => bulkSet({ set: { review_status: 'approved' } }) }]) }, 'Status') : null,
      can('contributor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'bulk-tag', onclick: bulkTag }, icon('tag', 'sm'), 'Tag') : null,
      can('contributor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'bulk-place', onclick: bulkPlace }, icon('folder', 'sm'), 'Add to…') : null,
      can('contributor') ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'bulk-archive', onclick: bulkArchive }, icon('archive', 'sm'), can('editor') ? 'Archive' : 'Propose archive') : null,
      el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Clear selection', onclick: () => { selected.clear(); draw(); drawBulk(); } }, icon('x', 'sm'))]);
  }
  async function bulkSet(body) {
    try { const out = await api('POST', '/nodes/bulk', Object.assign({ ids: Array.from(selected) }, body)); toast('Updated ' + plural(out.updated, 'record')); load(false); }
    catch (e) { failToast(e, 'Not updated'); }
  }
  function bulkTag() {
    const inp = el('input', { 'aria-label': 'Tag', 'data-testid': 'bulk-tag-input', placeholder: 'tag name' });
    openDialog([el('h2', { text: 'Tag ' + plural(selected.size, 'record') }), inp, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Remove tag', onclick: () => { if (inp.value.trim()) { closeDialog(); bulkSet({ remove_tags: [inp.value.trim()] }); } } }),
      el('button', { class: 'btn primary', type: 'button', text: 'Add tag', 'data-testid': 'bulk-tag-add', onclick: () => { if (inp.value.trim()) { closeDialog(); bulkSet({ add_tags: [inp.value.trim()] }); } } }))], { label: 'Tag records' });
  }
  function bulkPlace() {
    let val = null;
    openDialog([el('h2', { text: 'Add ' + plural(selected.size, 'record') + ' to…' }), el('p', { class: 'muted small', text: 'Each record is also placed under the parent you choose. Existing placements stay.' }),
      combobox({ placeholder: 'Search programs, courses, modules, weeks…', source: nodeSource(['program', 'course', 'domain', 'module', 'week', 'session']), onChange: (x) => { val = x; } }),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', text: 'Add', onclick: () => { if (val) { closeDialog(); bulkSet({ add_parent: val.id }); } } }))], { label: 'Add to' });
  }
  async function bulkArchive() {
    const n = selected.size;
    const ok = await confirmDialog({ title: (can('editor') ? 'Archive ' : 'Propose archiving ') + plural(n, 'record') + '?', danger: can('editor'), confirmLabel: can('editor') ? 'Archive' : 'Send for approval',
      body: 'Their relationships and links are archived with them. You can restore them, or delete them permanently later from Archived.' });
    if (!ok) return;
    const ids = Array.from(selected);
    try {
      const out = await api('POST', '/nodes/bulk-archive', { ids });
      toast('Archived ' + plural(out.archived, 'record'), { action: { label: 'Undo', fn: async () => { for (const i of ids) { try { await api('POST', '/nodes/' + i + '/restore'); } catch (e) { /* skip */ } } load(false); } } });
      load(false);
    } catch (e) { if (e.status === 202) { toast(e.message); selected.clear(); drawBulk(); } else failToast(e, 'Not archived'); }
  }
  async function exportCsv() {
    const rows = [['id', 'type', 'name', 'summary', 'status', 'course_or_program', 'owner', 'links', 'updated_at']];
    const fields = new Set();
    let c = null, all = [];
    try {
      do { const pg = await api('GET', '/nodes' + qs(params({ cursor: c, limit: 200 }))); all = all.concat(pg.items); c = pg.next_cursor; } while (c && all.length < 20000);
    } catch (e) { failToast(e, 'Export failed'); return; }
    all.forEach((n) => Object.keys(n.props || {}).forEach((k) => fields.add(k)));
    const fk = Array.from(fields).sort();
    rows[0] = rows[0].concat(fk.map((k) => 'field:' + k));
    all.forEach((n) => rows.push([n.id, n.type, n.name, n.summary || '', n.status, n.scope_name || '', n.owner_id ? (S.personById[n.owner_id] || {}).email || '' : '', n.links, n.updated_at]
      .concat(fk.map((k) => { const x = (n.props || {})[k]; return x === undefined || x === null ? '' : Array.isArray(x) ? x.join('; ') : String(x); }))));
    // Cells starting with = + - @ would be formulas in a spreadsheet: neutralise them.
    const csv = rows.map((rw) => rw.map((x) => { let s = String(x === null || x === undefined ? '' : x); if (/^[=+\-@]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; }).join(',')).join('\r\n');
    const a = el('a', { href: URL.createObjectURL(new Blob([String.fromCharCode(0xFEFF) + csv], { type: 'text/csv;charset=utf-8' })), download: (fixed || 'records') + '-' + new Date().toISOString().slice(0, 10) + '.csv' });
    document.body.appendChild(a); a.click(); a.remove();
    toast('Exported ' + plural(all.length, 'record'));
  }

  // keyboard (j/k, Enter, x, /)
  S.tableKeys = (e) => {
    if (!items.length) return false;
    if (e.key === '/') { search.focus(); return true; }
    if (e.key === 'j' || e.key === 'ArrowDown' && e.altKey) { cur = Math.min(items.length - 1, cur + 1); moveCursor(); return true; }
    if (e.key === 'k') { cur = Math.max(0, cur - 1); moveCursor(); return true; }
    if (e.key === 'Enter' && cur >= 0) { setQuery({ open: items[cur].id, res: null }); return true; }
    if (e.key === 'x' && cur >= 0) { const id = items[cur].id; if (selected.has(id)) selected.delete(id); else selected.add(id); draw(); drawBulk(); return true; }
    return false;
  };
  function moveCursor() {
    $$('tr[data-testid=row]', tableHost).forEach((tr, i) => tr.classList.toggle('cursor', i === cur));
    const tr = $$('tr[data-testid=row]', tableHost)[cur]; if (tr) tr.scrollIntoView({ block: 'nearest' });
    if (S.panel) setQuery({ open: items[cur].id }, true);
  }
  S.onQueryChange = (nr) => {
    const nf = filtersFrom(nr.q, fixed);
    if (JSON.stringify(nf) !== JSON.stringify(f)) { f = nf; if (document.activeElement !== search) search.value = f.q || ''; drawChips(); drawTabs(); load(false); }
    else $$('tr[data-testid=row]', tableHost).forEach((tr) => tr.classList.toggle('selected', tr.dataset.id === nr.q.open));
  };
  drawChips(); loadViews(); load(false);
}

function filtersFrom(q, fixed) {
  const f = {};
  ['q', 'type', 'parent', 'owner', 'tag', 'tag_name', 'status', 'flagged', 'review', 'sort', 'view'].forEach((k) => { if (q[k]) f[k] = q[k]; });
  if (q.scope) f.parent = q.scope;
  if (fixed) delete f.type;
  return f;
}
