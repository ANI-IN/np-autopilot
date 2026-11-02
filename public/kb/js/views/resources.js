/* Resources: the link library, reused across records. */
import { S, el, add, clear, icon, api, toast, failToast, avatar, ago, qs, host, setQuery, skeletonRows, empty, errorBox, debounce,
  openDialog, closeDialog, can, plural, menu } from '../core.js';
import { linkKindFor, detectLinkKind, kindSelect } from '../form.js';
import { kindLabel } from '../detail.js';

export function viewResources(v, r) {
  let f = { q: r.q.q || '', kind: r.q.kind || '', link_kind: r.q.link_kind || '', status: r.q.status || 'live' };
  const count = el('span', { class: 'sub', 'data-testid': 'result-count' });
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Resources' }), count, el('span', { class: 'spacer' }),
    can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-resource', onclick: () => newResourceDialog() }, icon('plus'), 'New link') : null));
  const search = el('input', { placeholder: 'Search title or URL', 'aria-label': 'Search links', 'data-testid': 'res-filter', value: f.q });
  search.addEventListener('input', debounce(() => setQuery({ q: search.value.trim() || null }, true), 250));
  const lkBtn = el('button', { class: 'btn', type: 'button', 'data-testid': 'res-service', onclick: (e) => menu(e.currentTarget, [{ label: 'Any service', fn: () => setQuery({ link_kind: null }) }]
    .concat(S.linkKinds.map((k) => ({ label: k.label, icon: k.icon, fn: () => setQuery({ link_kind: k.key }) })))) }, icon('globe', 'sm'), f.link_kind ? (S.linkKinds.find((k) => k.key === f.link_kind) || {}).label : 'Service');
  const kindBtn = el('button', { class: 'btn', type: 'button', 'data-testid': 'res-kind-filter', onclick: (e) => menu(e.currentTarget, [{ label: 'Any kind', fn: () => setQuery({ kind: null }) }]
    .concat(S.resourceKinds.map((k) => ({ label: kindLabel(k), fn: () => setQuery({ kind: k }) })))) }, icon('shapes', 'sm'), f.kind ? kindLabel(f.kind) : 'Kind');
  const stBtn = el('button', { class: 'btn ghost', type: 'button', onclick: () => setQuery({ status: f.status === 'archived' ? null : 'archived' }) }, icon('archive', 'sm'), f.status === 'archived' ? 'Showing archived' : 'Archived');
  v.append(el('div', { style: 'height:12px' }), el('div', { class: 'toolbar' }, el('div', { class: 'input-icon search' }, icon('search'), search), lkBtn, kindBtn, el('span', { class: 'spacer' }), stBtn));
  const host_ = el('div', { class: 'table-wrap' }), foot = el('div', { class: 'table-foot' });
  v.append(host_, foot);
  let items = [], cursor = null;
  async function load(more) {
    if (!more) { clear(host_).appendChild(skeletonRows(10)); items = []; cursor = null; }
    try {
      const p = await api('GET', '/resources' + qs({ q: f.q, kind: f.kind, link_kind: f.link_kind, status: f.status, cursor: more ? cursor : null, limit: 100 }));
      items = items.concat(p.items); cursor = p.next_cursor; draw();
    } catch (e) { clear(host_).appendChild(errorBox(e, () => load(false))); }
  }
  S.listReload = () => load(false);
  function draw() {
    clear(host_);
    count.textContent = plural(items.length, 'link') + (cursor ? '+' : '');
    if (!items.length) { host_.appendChild(f.q || f.kind || f.link_kind ? empty('Nothing matches', 'Try a different search or service.', null, 'search') : empty('No links yet', 'Add slides, recordings and repos from a record, or here.', can('contributor') ? el('button', { class: 'btn sm', type: 'button', text: 'New link', onclick: () => newResourceDialog() }) : null, 'link')); clear(foot); return; }
    const tb = el('tbody');
    items.forEach((x) => {
      const lk = linkKindFor(x);
      tb.appendChild(el('tr', { 'data-id': x.id, 'data-testid': 'res-row', class: S.panel && S.panel.id === x.id ? 'selected' : '', onclick: () => setQuery({ res: x.id, open: null }) },
        el('td', null, el('div', { class: 'cell-name' }, el('span', { class: 'type-icon', title: lk.label }, icon(lk.icon)), el('span', { class: 'name', text: x.title }),
          x.link_status && x.link_status !== 'ok' ? el('span', { class: 'badge ' + (x.link_status === 'needs_auth' ? 'warn' : 'danger'), text: x.link_status === 'needs_auth' ? 'Needs sign-in' : 'Broken' }) : null,
          el('span', { class: 'desc mono', text: host(x.url) }))),
        el('td', null, el('span', { class: 'badge', text: kindLabel(x.kind) })),
        el('td', { class: 'col-optional' }, avatar(x.owner_id)),
        el('td', { class: 'num faint', text: x.used_by ? String(x.used_by) : '' }),
        el('td', { class: 'faint', text: ago(x.updated_at) })));
    });
    host_.appendChild(el('table', { class: 'table' }, el('thead', null, el('tr', null, el('th', { text: 'Link' }), el('th', { style: 'width:150px', text: 'Kind' }),
      el('th', { class: 'col-optional', style: 'width:64px', text: 'Owner' }), el('th', { class: 'num', style: 'width:80px', text: 'Used by' }), el('th', { style: 'width:96px', text: 'Updated' }))), tb));
    clear(foot); add(foot, [el('span', { text: 'Showing ' + items.length }), el('span', { class: 'spacer' }), cursor ? el('button', { class: 'btn sm', type: 'button', text: 'Load more', onclick: () => load(true) }) : null]);
  }
  S.onQueryChange = (nr) => {
    const nf = { q: nr.q.q || '', kind: nr.q.kind || '', link_kind: nr.q.link_kind || '', status: nr.q.status || 'live' };
    if (JSON.stringify(nf) !== JSON.stringify(f)) { clear(v); viewResources(v, nr); }
  };
  load(false);
}

export function newResourceDialog(pre) {
  pre = pre || {};
  const url = el('input', { type: 'url', placeholder: 'https://…', 'data-testid': 'res-url', autofocus: true, 'aria-label': 'URL', value: pre.url || '' });
  const title = el('input', { 'data-testid': 'res-title', maxlength: '300', 'aria-label': 'Title', value: pre.title || '' });
  const kind = kindSelect(pre.kind || 'link', 'res-kind');
  const desc = el('textarea', { rows: '2', 'aria-label': 'Description' }, pre.description || '');
  const lkLabel = el('span', { class: 'faint xs' });
  url.addEventListener('input', () => { const lk = S.linkKinds.find((k) => k.key === detectLinkKind(url.value.trim())); lkLabel.textContent = url.value.trim() ? 'Detected: ' + (lk ? lk.label : 'Website') : ''; if (lk && lk.defaults && lk.defaults.kind && !pre.kind) kind.value = lk.defaults.kind; });
  const err = el('div', { class: 'field-error', role: 'alert' });
  openDialog([el('h2', { text: 'New link' }),
    el('label', { class: 'field' }, el('span', { class: 'label req', text: 'URL' }), url, lkLabel), el('label', { class: 'field' }, el('span', { class: 'label req', text: 'Title' }), title),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Kind' }), kind), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Description' }), el('span', { class: 'help', text: 'What is inside it.' }), desc), err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'res-submit', text: 'Add link', onclick: async () => {
        try { const x = await api('POST', '/resources', { url: url.value.trim(), title: title.value, kind: kind.value, description: desc.value.trim() || undefined }); closeDialog(); toast('Added “' + x.title + '”'); setQuery({ res: x.id, open: null }); if (S.listReload) S.listReload(); }
        catch (e) {
          if (e.status === 409 && e.body.existing) { err.textContent = ''; err.append('This URL is already in the library as “' + e.body.existing.title + '”. ', el('a', { href: '#/resources?res=' + e.body.existing.id, onclick: closeDialog, text: 'Open it' })); }
          else err.textContent = e.message;
        } } }))], { label: 'New link' });
}
