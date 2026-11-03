/* Outline: Program › Course › Domain › Module › Week › Session as an
   expandable tree. Drag to reorder within a parent, link count and
   completeness per node, quick-add at any level, "Copy as text". */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, toast, failToast, setQuery, skeletonRows, empty, errorBox, can, qs } from '../core.js';
import { pageHead } from '../page.js';
import { openRecordForm } from '../form.js';

let openState = {};
try { openState = JSON.parse(localStorage.getItem('kb_outline_open') || '{}'); } catch (e) { openState = {}; }
const saveOpen = () => { try { localStorage.setItem('kb_outline_open', JSON.stringify(openState)); } catch (e) { /* ignore */ } };

export function viewOutline(v, r) {
  const root = r.q.root || '';
  let data = null;
  const head = pageHead({ title: 'Outline', sub: 'Programs and courses, top to bottom.', actions: [
    el('button', { class: 'btn ghost', type: 'button', 'data-testid': 'outline-expand', onclick: () => { if (!data) return; walk(data.roots, (n) => { openState[n.id] = true; }); saveOpen(); draw(); } }, 'Expand all'),
    el('button', { class: 'btn ghost', type: 'button', onclick: () => { if (!data) return; openState = {}; saveOpen(); draw(); } }, 'Collapse all'),
    el('button', { class: 'btn', type: 'button', 'data-testid': 'outline-copy', onclick: copyText }, icon('copy', 'sm'), 'Copy as text'),
    can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'outline-new-program', onclick: () => openRecordForm({ type: 'program' }) }, icon('plus'), 'New program') : null] });
  v.appendChild(head);
  const body = el('div', { class: 'page-body', 'data-testid': 'outline' }, skeletonRows(10));
  v.appendChild(body);

  function walk(nodes, fn) { (nodes || []).forEach((n) => { fn(n); walk(n.children, fn); }); }
  async function load() {
    try { data = await api('GET', '/outline' + qs({ root })); draw(); }
    catch (e) { clear(body).appendChild(errorBox(e, load)); }
  }
  S.listReload = load;
  function draw() {
    clear(body);
    if (!data.roots.length) { body.appendChild(empty('No programs or courses yet', 'Start with a program, then add courses, modules, weeks and sessions inside it.', can('contributor') ? el('button', { class: 'btn primary sm', type: 'button', text: 'New program', onclick: () => openRecordForm({ type: 'program' }) }) : null, 'list-tree', 'finding-things')); return; }
    const ul = el('ul', { class: 'tree', role: 'tree', 'aria-label': 'Outline' });
    data.roots.forEach((n) => ul.appendChild(item(n, null, 0)));
    body.appendChild(ul);
  }
  function childTypes(type) { return S.types.filter((t) => (t.allowed_parents || []).includes(type)).map((t) => t.key); }
  function item(n, parent, depth) {
    const kids = n.children || [];
    const isOpen = openState[n.id] !== undefined ? openState[n.id] : depth < 1;
    const li = el('li', { role: 'treeitem', 'aria-expanded': kids.length ? String(isOpen) : null, 'data-id': n.id });
    const twisty = el('button', { class: 'twisty', type: 'button', 'aria-label': (isOpen ? 'Collapse ' : 'Expand ') + n.name, tabindex: kids.length ? '0' : '-1',
      style: kids.length ? '' : 'visibility:hidden', onclick: () => { openState[n.id] = !isOpen; saveOpen(); draw(); } }, icon(isOpen ? 'chevron-down' : 'chevron-right', 'sm'));
    const score = n.completeness;
    const adds = childTypes(n.type);
    const row = el('div', { class: 'tree-row', 'data-testid': 'outline-row', draggable: parent && can('contributor') ? 'true' : null },
      parent && can('contributor') ? el('span', { class: 'grip', title: 'Drag to reorder' }, icon('grip-vertical', 'sm')) : el('span', { class: 'ico-slot' }),
      twisty, typeIcon(n.type), el('a', { class: 'name truncate', href: '#/outline?open=' + n.id + (root ? '&root=' + root : ''), text: n.name, onclick: (e) => { e.preventDefault(); setQuery({ open: n.id }); } }),
      n.status === 'draft' ? el('span', { class: 'badge warn', text: 'Draft' }) : null,
      el('span', { class: 'spacer' }),
      el('span', { class: 'row-actions' }, adds.length && can('contributor') ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'outline-add',
        onclick: (e) => quickAdd(e.currentTarget, n, adds) }, icon('plus', 'sm'), 'Add') : null),
      n.links ? el('span', { class: 'faint xs row gap-xs', title: n.links + ' link(s)' }, icon('link', 'sm'), n.links) : null,
      score !== null && score !== undefined ? el('span', { class: 'xs tabular ' + (score >= 80 ? 'faint' : ''), style: score < 50 ? 'color:var(--danger)' : score < 80 ? 'color:var(--warn)' : '', title: 'Completeness', text: score + '%' }) : null);
    if (parent) dnd(row, n, parent);
    li.appendChild(row);
    if (kids.length && isOpen) { const sub = el('ul', { role: 'group' }); kids.forEach((c) => sub.appendChild(item(c, n, depth + 1))); li.appendChild(sub); }
    return li;
  }
  function quickAdd(anchor, n, types) {
    const go = (t) => openRecordForm({ type: t, parents: [{ id: n.id, label: n.name, type: n.type, icon: typeIcon(n.type) }], onCreated: () => { openState[n.id] = true; saveOpen(); load(); } });
    if (types.length === 1) return go(types[0]);
    import('../core.js').then(({ menu }) => menu(anchor, types.map((t) => ({ node: el('span', { class: 'row' }, typeIcon(t), typeLabel(t)), testid: 'outline-add-' + t, fn: () => go(t) }))));
  }
  let drag = null;
  function dnd(row, n, parent) {
    row.addEventListener('dragstart', (e) => { drag = { id: n.id, parent: parent.id }; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', n.id); });
    row.addEventListener('dragover', (e) => {
      if (!drag || drag.parent !== parent.id || drag.id === n.id) return;
      e.preventDefault();
      const r = row.getBoundingClientRect(), after = e.clientY > r.top + r.height / 2;
      row.classList.toggle('drop-after', after); row.classList.toggle('drop-before', !after);
    });
    row.addEventListener('dragleave', () => row.classList.remove('drop-before', 'drop-after'));
    row.addEventListener('drop', async (e) => {
      e.preventDefault();
      const after = row.classList.contains('drop-after');
      row.classList.remove('drop-before', 'drop-after');
      if (!drag || drag.parent !== parent.id) return;
      const ids = parent.children.map((c) => c.id).filter((x) => x !== drag.id);
      ids.splice(ids.indexOf(n.id) + (after ? 1 : 0), 0, drag.id);
      drag = null;
      try { await api('POST', '/outline/reorder', { parent_id: parent.id, child_ids: ids }); toast('Order saved'); load(); } catch (er) { failToast(er, 'Order not saved'); }
    });
  }
  function copyText() {
    if (!data) return;
    const lines = [];
    const rec = (nodes, d) => nodes.forEach((n) => { lines.push('  '.repeat(d) + '- ' + typeLabel(n.type) + ': ' + n.name + (n.links ? ' (' + n.links + ' links)' : '')); rec(n.children || [], d + 1); });
    rec(data.roots, 0);
    const text = lines.join('\n');
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => toast('Copied ' + lines.length + ' lines')).catch(() => {
      import('../core.js').then(({ openDialog }) => openDialog([el('h2', { text: 'Outline as text' }), el('textarea', { rows: '16', readonly: true, 'data-testid': 'outline-text' }, text)], { label: 'Outline as text', wide: true }));
    });
  }
  load();
}
