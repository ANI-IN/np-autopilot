/* Two views over the KB (web/lib/kb/views.py):
   "Who teaches what": instructors x modules and sessions; each cell is the
   role from the current mastersheet (P Primary, B1-B3 Backups) or T (teaches,
   older sheets). Filter by domain, role, name; current only unless legacy is
   included; export as CSV.
   (The "Programme timeline" view was retired with the week records, 2026-11-07:
   week and order belong to each program.) Formerly: each programme's modules by week, with their
   sessions and slide decks. */
import { S, el, clear, icon, api, skeletonRows, empty, errorBox, setQuery, plural } from '../core.js';
import { pageHead } from '../page.js';
import { ROLE_SHORT, ROLE_LABEL } from '../detail.js';

function downloadCsv(name, rows) {
  // Same escaping as the records export: quoted, formula-leading cells defused.
  const csv = rows.map((rw) => rw.map((x) => { let s = String(x === null || x === undefined ? '' : x); if (/^[=+\-@]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; }).join(',')).join('\r\n');
  const a = el('a', { href: URL.createObjectURL(new Blob([String.fromCharCode(0xFEFF) + csv], { type: 'text/csv;charset=utf-8' })), download: name + '-' + new Date().toISOString().slice(0, 10) + '.csv' });
  document.body.appendChild(a); a.click(); a.remove();
}
const cellText = (c) => (c.role ? ROLE_SHORT[c.role] || c.role : 'T');

// ------------------------------------------------------------------ who teaches what
export function viewTeaching(v, r) {
  const q = r.q;
  let data = null;
  const exportBtn = el('button', { class: 'btn ghost', type: 'button', 'data-testid': 'teaching-export', disabled: true, onclick: () => {
    if (!data) return;
    const head = ['Instructor'].concat(data.columns.map((c) => (c.type === 'session' ? 'Session: ' : '') + c.name));
    const at = {}; data.cells.forEach((c) => { at[c.instructor_id + '|' + c.target_id] = c; });
    downloadCsv('who-teaches-what', [head].concat(data.instructors.map((i) => [i.name].concat(data.columns.map((c) => { const x = at[i.id + '|' + c.id]; return x ? cellText(x) : ''; })))));
  } }, icon('download', 'sm'), 'Export');
  v.appendChild(pageHead({ title: 'Who teaches what', sub: 'P Primary · B1–B3 Backups (current mastersheet) · T teaches (older sheets)', actions: exportBtn }));
  const domSel = el('select', { 'aria-label': 'Domain', 'data-testid': 'teaching-domain' }, el('option', { value: '', text: 'All domains' }));
  const roleSel = el('select', { 'aria-label': 'Role', 'data-testid': 'teaching-role' }, [['', 'Any role'], ['any_role', 'With a role (P, B1–B3)'], ['primary', 'Primary (P)'], ['backup_1', 'Backup 1'], ['backup_2', 'Backup 2'], ['backup_3', 'Backup 3']]
    .map(([k, l]) => el('option', { value: k, text: l, selected: (q.role || '') === k })));
  const legacyBox = el('input', { type: 'checkbox', 'data-testid': 'teaching-legacy', checked: q.legacy === 'all' });
  const search = el('input', { type: 'search', placeholder: 'Filter by name…', 'aria-label': 'Filter by name', value: q.q || '', class: 'search-sm', 'data-testid': 'teaching-q' });
  domSel.addEventListener('change', () => setQuery({ domain: domSel.value || null }));
  roleSel.addEventListener('change', () => setQuery({ role: roleSel.value || null }));
  legacyBox.addEventListener('change', () => setQuery({ legacy: legacyBox.checked ? 'all' : null }));
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') setQuery({ q: search.value.trim() || null }); });
  v.appendChild(el('div', { class: 'view-toolbar' }, domSel, roleSel, search,
    el('label', { class: 'row small' }, legacyBox, 'Include legacy (older sheets)')));
  const box = el('div', { class: 'page-body', 'data-testid': 'teaching' }, skeletonRows(8));
  v.appendChild(box);
  const load = async (rq) => {
    try {
      const p = new URLSearchParams(); ['domain', 'role', 'legacy', 'q'].forEach((k) => { if (rq[k]) p.set(k, rq[k]); });
      data = await api('GET', '/views/teaching' + (p.toString() ? '?' + p : ''));
      exportBtn.disabled = !data.instructors.length;
      clear(domSel); domSel.appendChild(el('option', { value: '', text: 'All domains' }));
      data.domains.forEach((d) => domSel.appendChild(el('option', { value: d.id, text: d.name, selected: rq.domain === d.id })));
      clear(box);
      if (!data.instructors.length) { box.appendChild(empty('No one matches', 'Try another domain or role, or include legacy.', null, 'users')); return; }
      const at = {}; data.cells.forEach((c) => { at[c.instructor_id + '|' + c.target_id] = c; });
      const c = data.counts;
      box.appendChild(el('p', { class: 'small muted mb-2', 'data-testid': 'teaching-summary',
        text: plural(data.instructors.length, 'instructor') + ' × ' + data.columns.length + ' modules and live sessions · P ' + c.primary + ' · B1 ' + c.backup_1 + ' · B2 ' + c.backup_2 + ' · B3 ' + c.backup_3 + ' · T ' + c.teaches_without_role }));
      const table = el('table', { class: 'table matrix', 'data-testid': 'teaching-matrix' },
        el('thead', {}, el('tr', {}, el('th', { text: 'Instructor', class: 'sticky-col', scope: 'col' }), data.columns.map((col) => el('th', { class: 'rot', scope: 'col', title: (col.type === 'session' ? 'Live session: ' : 'Module: ') + col.name + ' · ' + (col.domains.map((d) => d.name).join(', ') || 'no domain') + (col.legacy ? ' · legacy' : '') },
          el('a', { href: '#/teaching?' + new URLSearchParams(Object.assign({}, rq, { open: col.id })).toString(), text: (col.type === 'session' ? '· ' : '') + col.name }))))),
        el('tbody', {}, data.instructors.map((i) => el('tr', { 'data-testid': 'teaching-row' },
          el('th', { class: 'sticky-col', scope: 'row' }, el('a', { href: '#/teaching?' + new URLSearchParams(Object.assign({}, rq, { open: i.id })).toString(), text: i.name }), i.legacy ? el('span', { class: 'badge', text: 'Legacy' }) : null),
          data.columns.map((col) => { const x = at[i.id + '|' + col.id]; return el('td', { class: 'cell' }, x ? el('span', { class: 'role-badge' + (x.role ? ' r-' + x.role : ' r-none'), 'data-testid': 'teaching-cell', title: x.role ? ROLE_LABEL[x.role] : 'Teaches (older sheets)', text: cellText(x) }) : null); })))));
      box.appendChild(el('div', { class: 'matrix-wrap' }, table));
    } catch (e) { clear(box); box.appendChild(errorBox(e, () => load(rq))); }
  };
  load(q);
  S.listReload = () => load((S.route && S.route.q) || r.q);   // B1 (run 6): live updates reload this view
  const keys = (x) => ['domain', 'role', 'legacy', 'q'].map((k) => x[k] || '').join('|');
  let last = keys(q);
  S.onQueryChange = (nr) => { if (keys(nr.q) !== last) { last = keys(nr.q); load(nr.q); } };
}
