/* Archived: everything archived, restorable; admins can delete permanently
   (typed-name confirmation, shows what goes with it, audited). */
import { S, el, clear, icon, typeIcon, api, toast, failToast, ago, skeletonRows, empty, errorBox, can, personName } from '../core.js';
import { hardDelete } from '../detail.js';
import { refreshCounts } from '../app.js';

export function viewArchived(v, r) {
  const kind = ['records', 'resources', 'relationships'].includes(r.q.kind) ? r.q.kind : 'records';
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Archived' }), el('span', { class: 'sub', text: 'Restore anything here. Admins can delete permanently.' })));
  v.appendChild(el('div', { class: 'tabs', role: 'tablist' }, [['records', 'Records'], ['resources', 'Links'], ['relationships', 'Relationships']].map(([k, l]) =>
    el('a', { href: '#/archived' + (k === 'records' ? '' : '?kind=' + k), role: 'tab', 'aria-selected': k === kind ? 'true' : 'false', 'data-testid': 'archived-tab-' + k, text: l }))));
  const box = el('div', { 'data-testid': 'archived' }, skeletonRows(6));
  v.appendChild(box);
  const table = { records: 'nodes', resources: 'resources', relationships: 'edges' }[kind];
  const load = async () => {
    try {
      const items = (await api('GET', '/archived?kind=' + kind)).items;
      clear(box);
      if (!items.length) { box.appendChild(empty('Nothing archived', 'Archived ' + kind + ' appear here, ready to restore.', null, 'archive')); return; }
      const tb = el('tbody');
      items.forEach((x) => tb.appendChild(el('tr', { 'data-testid': 'archived-row' },
        el('td', null, el('div', { class: 'cell-name' }, kind === 'records' ? typeIcon(x.type) : icon(kind === 'resources' ? 'link' : 'git-branch'), el('span', { class: 'name', text: x.name }),
          kind !== 'relationships' && x.links ? el('span', { class: 'desc', text: x.links + ' link(s)' + (x.edges ? ', ' + x.edges + ' relationship(s)' : '') }) : null)),
        el('td', { class: 'faint', text: personName(x.updated_by) || '' }),
        el('td', { class: 'faint', text: ago(x.archived_at) }),
        el('td', { style: 'text-align:right' }, el('span', { class: 'row', style: 'justify-content:flex-end;gap:4px' },
          kind === 'records' ? el('a', { class: 'btn ghost sm', href: '#/archived?open=' + x.id, text: 'View' }) : null,
          can('editor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'archived-restore', onclick: async () => {
            try { await api('POST', '/' + table + '/' + x.id + '/restore'); toast('Restored “' + x.name + '”'); load(); refreshCounts(); } catch (e) { failToast(e, 'Not restored'); } } }, icon('rotate-ccw', 'sm'), 'Restore') : null,
          can('admin') ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'archived-delete', onclick: () => hardDelete(table, x.id, x.name, () => { load(); refreshCounts(); }) }, icon('trash-2', 'sm'), 'Delete permanently') : null)))));
      box.appendChild(el('table', { class: 'table' }, el('thead', null, el('tr', null, el('th', { text: 'Name' }), el('th', { style: 'width:160px', text: 'Archived by' }), el('th', { style: 'width:110px', text: 'When' }), el('th', { style: 'width:300px' }))), tb));
    } catch (e) { clear(box).appendChild(errorBox(e, load)); }
  };
  S.listReload = load; load();
  S.onQueryChange = (nr) => { if ((nr.q.kind || '') !== (r.q.kind || '')) { clear(v); viewArchived(v, nr); } };
}
