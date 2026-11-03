/* Activity (Maintain → Activity): every create, update, archive, restore,
   delete, merge, approval, import, configuration change and AI action, from
   the append-only audit log. Admins see everything; editors see their own
   actions and their courses (enforced by the database). Each record's History
   tab renders entries with the same component (activityEntry). */
import { S, el, clear, icon, api, avatar, ago, skeletonRows, empty, errorBox, can, setQuery, qs, combobox, peopleSource, debounce, you, failToast, toast } from '../core.js';
import { pageHead } from '../page.js';

const ENTITY = { nodes: 'record', edges: 'relationship', resources: 'link', node_resources: 'attached link', node_tags: 'tag',
  node_types: 'record type', edge_types: 'relationship type', edge_type_rules: 'relationship rule', link_kinds: 'link kind', proposals: 'proposal',
  flags: 'flag', templates: 'template', saved_views: 'saved view', memberships: 'role', member_invites: 'invitation', api_tokens: 'API token', import_runs: 'import', tags: 'tag' };
const SOURCE_LABEL = { app: 'App', ai: 'AI assistant', import: 'Import', sync: 'Sync', system: 'System' };

function verb(a) {
  const b = a.before || {}, f = a.after || {};
  if (a.action === 'insert') return a.table_name === 'proposals' ? 'proposed' : a.table_name === 'node_resources' ? 'attached' : a.table_name === 'node_tags' ? 'added' : 'created';
  if (a.action === 'delete' && a.table_name === 'node_tags') return 'removed';
  if (a.action === 'delete') return 'permanently deleted';
  if (!b.archived_at && f.archived_at) return 'archived';
  if (b.archived_at && !f.archived_at) return 'restored';
  if (a.table_name === 'proposals' && b.status === 'pending' && f.status && f.status !== 'pending') return f.status === 'approved' ? 'approved' : 'rejected';
  if (a.table_name === 'edge_types' && !b.merged_into && f.merged_into) return 'merged';
  if (a.table_name === 'edge_types' && b.review_status === 'unreviewed' && f.review_status === 'reviewed') return 'confirmed';
  return 'updated';
}
const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

/* One entry: who · what · which (link, or "deleted") · when (relative, exact
   on hover) · field-by-field diff for updates. */
export function activityEntry(a, opts) {
  opts = opts || {};
  const who = a.actor_type === 'human' && you(a.actor_id) ? 'You' : a.actor_label;
  const kind = ENTITY[a.table_name] || a.table_name.replace(/_/g, ' ');
  const target = opts.inRecord && (a.table_name === 'nodes' || a.table_name === 'resources') ? 'this' :
    a.label ? (a.exists_now === false || a.action === 'delete'
      ? el('span', null, el('strong', { text: a.label }), el('span', { class: 'badge ml-2', text: 'deleted', 'data-testid': 'entry-deleted' }))
      : a.table_name === 'nodes' ? el('a', { href: '#/' + (S.route ? S.route.path.join('/') : '') + qs(Object.assign({}, S.route ? S.route.q : {}, { open: a.row_id })), text: a.label })
        : a.table_name === 'resources' ? el('a', { href: '#/resources?res=' + a.row_id, text: a.label }) : el('strong', { text: a.label })) : null;
  const diffs = el('div', { class: 'diff-list' });
  (a.changes || []).slice(0, opts.all ? 50 : 8).forEach((c) => diffs.appendChild(el('div', { class: 'diff-row', 'data-testid': 'history-diff' },
    el('span', { class: 'faint', text: c.field.replace(/^props\./, '').replace(/_id$/, '').replace(/_/g, ' ') }),
    el('span', { class: 'diff-del', text: fmt(c.before).slice(0, 160) }), icon('arrow-right', 'sm'), el('span', { class: 'diff-add', text: fmt(c.after).slice(0, 160) }))));
  const when = new Date(a.at);
  return el('li', { class: 'entry', 'data-testid': 'activity-entry' },
    a.actor_type === 'human' && a.actor_id ? avatar(a.actor_id) : el('span', { class: 'avatar system', title: a.actor_label }, icon(a.actor_type === 'ai' ? 'sparkles' : a.actor_type === 'import' ? 'upload' : a.actor_type === 'sync' ? 'refresh-cw' : 'settings', 'sm')),
    el('div', { class: 'entry-body' },
      el('div', { class: 'entry-line' }, el('strong', { 'data-testid': 'activity-actor', text: who }), ' ' + verb(a) + ' ',
        opts.inRecord && (a.table_name === 'nodes' || a.table_name === 'resources') ? 'this'
          : a.table_name === 'node_resources' || a.table_name === 'node_tags' ? [target || 'a ' + kind]
            : ['the ' + kind + ' ', target],
        a.source && a.source !== 'app' ? el('span', { class: 'badge ml-2', text: SOURCE_LABEL[a.source] }) : null),
      diffs.children.length ? diffs : null),
    el('time', { class: 'faint xs entry-time', datetime: a.at, title: when.toLocaleString(), text: ago(a.at) }));
}

export function viewActivity(v, r) {
  const q = r.q;
  const head = pageHead({ title: 'Activity', sub: 'Every change, who made it, and what it was before.',
    actions: [el('button', { class: 'btn', type: 'button', 'data-testid': 'activity-csv', onclick: () => exportCsv(q) }, icon('download'), 'Export CSV')] });
  v.appendChild(head);
  if (!can('editor')) {
    v.appendChild(el('div', { class: 'page-body' }, empty('Activity is for editors and admins', 'Each record’s History tab shows what changed on it.', null, 'history')));
    return;
  }
  // filters
  const set = (k, val) => setQuery({ [k]: val || null, cursor: null });
  const sel = (k, label, opts) => el('label', { class: 'filter' }, el('span', { class: 'faint xs', text: label }),
    el('select', { 'aria-label': label, 'data-testid': 'activity-' + k, onchange: (e) => set(k, e.target.value) },
      el('option', { value: '', text: 'Any' }), opts.map(([val, l]) => el('option', { value: val, text: l, selected: q[k] === val ? '' : null }))));
  const actor = combobox({ label: 'Person', placeholder: 'Anyone', testid: 'activity-actor-filter', source: peopleSource(), openOnFocus: true,
    value: q.actor && S.personById[q.actor] ? [{ id: q.actor, label: S.personById[q.actor].email }] : [], onChange: (p) => set('actor', p ? p.id : null) });
  const search = el('input', { type: 'search', placeholder: 'Names or values', 'aria-label': 'Search activity', 'data-testid': 'activity-search', value: q.q || '' });
  search.addEventListener('input', debounce(() => set('q', search.value.trim()), 300));
  const date = (k, label) => el('label', { class: 'filter' }, el('span', { class: 'faint xs', text: label }),
    el('input', { type: 'date', 'aria-label': label, 'data-testid': 'activity-' + k, value: q[k] ? q[k].slice(0, 10) : '', onchange: (e) => set(k, e.target.value ? (k === 'to' ? e.target.value + 'T23:59:59' : e.target.value) : null) }));
  const bar = el('div', { class: 'toolbar filters' }, el('label', { class: 'filter wide' }, el('span', { class: 'faint xs', text: 'Search' }), search),
    el('div', { class: 'filter' }, el('span', { class: 'faint xs', text: 'Person' }), actor),
    sel('action', 'Action', [['insert', 'Created'], ['update', 'Updated (incl. archive, restore)'], ['delete', 'Deleted permanently']]),
    sel('table', 'What changed', Object.entries(ENTITY).filter(([k]) => !['api_tokens', 'node_tags'].includes(k)).map(([k, l]) => [k, l[0].toUpperCase() + l.slice(1)])),
    sel('source', 'Source', Object.entries(SOURCE_LABEL)), date('from', 'From'), date('to', 'To'),
    Object.keys(q).some((k) => ['actor', 'action', 'table', 'source', 'from', 'to', 'q', 'record'].includes(k))
      ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'activity-clear', onclick: () => { location.hash = '#/activity'; } }, icon('x', 'sm'), 'Clear filters') : null);
  const body = el('div', { class: 'page-body' }, bar,
    q.record ? el('div', { class: 'notice', 'data-testid': 'activity-record-filter' }, icon('filter', 'sm'), 'Showing one record’s activity. ', el('a', { href: '#/activity', text: 'Show everything' })) : null);
  const list = el('ul', { class: 'entries', 'data-testid': 'activity-list' });
  const more = el('div', { class: 'row load-more' });
  const box = el('div', { class: 'card' }, skeletonRows(8));
  body.appendChild(box); v.appendChild(body);
  const params = () => { const p = {}; ['actor', 'action', 'table', 'source', 'from', 'to', 'q', 'record'].forEach((k) => { if (q[k]) p[k] = q[k]; }); return p; };
  const load = async (cursor) => {
    try {
      const out = await api('GET', '/activity' + qs(Object.assign(params(), { cursor, limit: 50 })));
      if (!cursor) { clear(box); clear(list); box.append(list, more); }
      if (!out.items.length && !cursor) { clear(box).appendChild(empty('No activity matches', 'Try fewer filters.', null, 'history')); return; }
      out.items.forEach((a) => list.appendChild(activityEntry(a)));
      clear(more);
      if (out.next_cursor) more.appendChild(el('button', { class: 'btn', type: 'button', 'data-testid': 'activity-more', text: 'Load older', onclick: () => load(out.next_cursor) }));
    } catch (e) { clear(box).appendChild(errorBox(e, () => load())); }
  };
  S.listReload = () => load(); load();
  S.onQueryChange = (nr) => { const keys = ['actor', 'action', 'table', 'source', 'from', 'to', 'q', 'record']; if (keys.some((k) => (nr.q[k] || '') !== (q[k] || ''))) { clear(v); viewActivity(v, nr); } };
}

async function exportCsv(q) {
  try {
    const p = {}; ['actor', 'action', 'table', 'source', 'from', 'to', 'q', 'record'].forEach((k) => { if (q[k]) p[k] = q[k]; });
    const out = await api('GET', '/activity' + qs(Object.assign(p, { format: 'csv' })));
    const a = el('a', { href: URL.createObjectURL(new Blob([out.csv], { type: 'text/csv' })), download: 'activity-' + new Date().toISOString().slice(0, 10) + '.csv' });
    document.body.appendChild(a); a.click(); a.remove();
    toast('Exported the filtered activity');
  } catch (e) { failToast(e, 'Not exported'); }
}
