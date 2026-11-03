/* Activity (Maintain → Activity): every create, update, archive, restore,
   delete, merge, approval, import, sync run, layout move and configuration
   change, from the append-only audit log and the change feed. Admins see
   everything; editors see their own actions and their courses (enforced by
   the database). Each record's History tab renders entries with the same
   component (activityEntry).

   Every entry is one plain sentence — WHO did WHAT to WHICH entity, old → new —
   built on the SERVER (web/lib/kb/activity.py) so the API, this page, the CSV
   export and the MCP tools say the same thing. This file only renders the
   sentence's parts (actor, text, entity link, values) with el()/textContent. */
import { S, el, clear, icon, api, avatar, ago, skeletonRows, empty, errorBox, can, setQuery, qs, combobox, personName, debounce, you, failToast, toast } from '../core.js';
import { pageHead } from '../page.js';

const ENTITY = { nodes: 'record', edges: 'relationship', resources: 'link', node_resources: 'attached link', node_tags: 'tag on a record',
  tags: 'tag', node_types: 'record type', edge_types: 'relationship type', edge_type_rules: 'relationship rule', link_kinds: 'link kind',
  proposals: 'proposal', flags: 'flag', templates: 'template', saved_views: 'saved view', memberships: 'role', member_invites: 'invitation', api_tokens: 'API token',
  graph_positions: 'graph layout', person_accounts: 'sign-in account', sync_runs: 'sync run' };
const SOURCE_LABEL = { app: 'App', graph: 'Graph', ai: 'AI assistant', import: 'Import', sync: 'Sync', system: 'System' };
const OPS = [['create', 'Created'], ['update', 'Updated'], ['owner', 'Owner changes'], ['archive', 'Archived'], ['restore', 'Restored'],
  ['delete', 'Deleted permanently'], ['attach', 'Attached or tagged'], ['detach', 'Detached or untagged'], ['layout', 'Moved on the graph'],
  ['sync', 'Sync runs']];
const KEYS = ['actor', 'action', 'op', 'table', 'type', 'source', 'from', 'to', 'q', 'record'];
const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

function entityHref(p) {
  if (!p.id || p.deleted) return null;
  if (p.kind === 'record') return '#/' + (S.route ? S.route.path.join('/') : 'records') + qs(Object.assign({}, S.route ? S.route.q : {}, { open: p.id }));
  if (p.kind === 'link') return '#/resources' + qs({ res: p.id });
  if (p.kind === 'tag') return '#/records' + qs({ tag: p.id, tag_name: '#' + p.text });
  return { type: '#/settings?tab=types', reltype: '#/settings?tab=relationships', link_kind: '#/settings?tab=links', template: '#/settings?tab=templates' }[p.kind] || null;
}

/* The server's sentence, piece by piece: the actor (or "You"), plain text,
   each entity as a link (or marked "deleted"), and the values. */
export function sentenceParts(a, parts) {
  return (parts || a.parts || []).map((p) => {
    if (p.t === 'actor') return el('strong', { 'data-testid': 'activity-actor', text: a.actor_type === 'human' && p.id && you(p.id) ? 'You' : p.text });
    if (p.t === 'entity') {
      const href = entityHref(p);
      return ['\'', href ? el('a', { href, text: p.text, 'data-testid': 'entry-entity' }) : el('strong', { text: p.text }), '\'',
        p.deleted && p.badge !== false ? el('span', { class: 'badge ml-2', text: 'deleted', 'data-testid': 'entry-deleted' }) : null];
    }
    if (p.t === 'value') return el('span', { class: 'entry-value', text: p.quote ? '\'' + p.text + '\'' : p.text });
    return p.text;
  });
}

function actorMark(a) {
  return a.actor_type === 'human' && a.actor_id ? avatar(a.actor_id)
    : el('span', { class: 'avatar system', title: a.actor_label },
      icon(a.source === 'graph' ? 'network' : a.actor_type === 'ai' ? 'sparkles' : a.actor_type === 'import' ? 'upload' : a.actor_type === 'sync' || a.source === 'sync' ? 'refresh-cw' : 'settings', 'sm'));
}

function when(at) {
  return el('time', { class: 'faint xs entry-time', datetime: at, title: new Date(at).toLocaleString(), text: ago(at) });
}

/* One entry: the sentence · source · when (relative, exact on hover) · the
   field-by-field diff for updates, folded until opened. */
export function activityEntry(a, opts) {
  opts = opts || {};
  const line = a.parts
    ? sentenceParts(a, a.parts)
    : [el('strong', { 'data-testid': 'activity-actor', text: a.actor_label }), ' ' + (a.sentence || a.action)];
  const diffs = el('div', { class: 'diff-list' });
  (a.changes || []).slice(0, opts.all ? 50 : 12).forEach((c) => diffs.appendChild(el('div', { class: 'diff-row', 'data-testid': 'history-diff' },
    el('span', { class: 'faint', text: c.field.replace(/^props\./, '').replace(/_id$/, '').replace(/_/g, ' ') }),
    el('span', { class: 'diff-del', text: fmt(c.before).slice(0, 160) }), icon('arrow-right', 'sm'), el('span', { class: 'diff-add', text: fmt(c.after).slice(0, 160) }))));
  const n = (a.changes || []).length;
  return el('li', { class: 'entry', 'data-testid': 'activity-entry', 'data-kind': a.kind || null },
    actorMark(a),
    el('div', { class: 'entry-body' },
      el('div', { class: 'entry-line', 'data-testid': 'activity-sentence' }, line,
        a.source && a.source !== 'app' ? el('span', { class: 'badge ml-2', 'data-testid': 'activity-source', text: SOURCE_LABEL[a.source] || a.source }) : null),
      n ? el('details', { class: 'entry-diff' }, el('summary', { class: 'faint xs', text: n === 1 ? 'Show the change' : 'Show ' + n + ' changes' }), diffs) : null),
    when(a.at));
}

/* A group (one bulk request, an import, a sync: same actor, same action,
   seconds apart): its own sentence, the members folded underneath. */
function groupEntry(g, first) {
  const inner = el('ul', { class: 'entries', 'data-testid': 'activity-group-list' });
  const li = el('li', { class: 'entry', 'data-testid': 'activity-group' },
    actorMark(first),
    el('div', { class: 'entry-body' },
      el('div', { class: 'entry-line', 'data-testid': 'activity-sentence' }, sentenceParts(first, g.parts),
        first.source && first.source !== 'app' ? el('span', { class: 'badge ml-2', text: SOURCE_LABEL[first.source] || first.source }) : null),
      el('details', { class: 'entry-diff' }, el('summary', { class: 'faint xs', text: 'Show all ' + g.count }), inner)),
    when(first.at));
  return { li, inner };
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
  // filters: who, what happened, what it happened to, record type, source, when, and a search
  const set = (k, val) => setQuery({ [k]: val || null, cursor: null });
  const sel = (k, testid, label, opts) => el('label', { class: 'filter' }, el('span', { class: 'faint xs', text: label }),
    el('select', { 'aria-label': label, 'data-testid': testid, onchange: (e) => set(k, e.target.value) },
      el('option', { value: '', text: 'Any' }), opts.map(([val, l]) => el('option', { value: val, text: l, selected: q[k] === val }))));
  // People by name only: an e-mail address is never shown here.
  const people = async (text) => S.people.filter((p) => !text || (personName(p.user_id) || '').toLowerCase().includes(text.toLowerCase()))
    .slice(0, 12).map((p) => ({ id: p.user_id, label: personName(p.user_id), icon: avatar(p.user_id) }));
  const actor = combobox({ label: 'Person', placeholder: 'Anyone', testid: 'activity-actor-filter', source: people, openOnFocus: true,
    value: q.actor ? [{ id: q.actor, label: personName(q.actor) }] : [], onChange: (p) => set('actor', p ? p.id : null) });
  const search = el('input', { type: 'search', placeholder: 'Names, people or values', 'aria-label': 'Search activity', 'data-testid': 'activity-search', value: q.q || '' });
  search.addEventListener('input', debounce(() => set('q', search.value.trim()), 300));
  const date = (k, label) => el('label', { class: 'filter' }, el('span', { class: 'faint xs', text: label }),
    el('input', { type: 'date', 'aria-label': label, 'data-testid': 'activity-' + k, value: q[k] ? q[k].slice(0, 10) : '', onchange: (e) => set(k, e.target.value ? (k === 'to' ? e.target.value + 'T23:59:59' : e.target.value) : null) }));
  const types = Object.entries(S.typeByKey || {}).map(([k, t]) => [k, t.label || k]);
  const bar = el('div', { class: 'toolbar filters' }, el('label', { class: 'filter wide' }, el('span', { class: 'faint xs', text: 'Search' }), search),
    el('div', { class: 'filter' }, el('span', { class: 'faint xs', text: 'Person' }), actor),
    sel('op', 'activity-action', 'Action', OPS),
    sel('table', 'activity-table', 'What changed', Object.entries(ENTITY).filter(([k]) => k !== 'api_tokens').map(([k, l]) => [k, l[0].toUpperCase() + l.slice(1)])),
    types.length ? sel('type', 'activity-type', 'Record type', types) : null,
    sel('source', 'activity-source-filter', 'Source', Object.entries(SOURCE_LABEL)), date('from', 'From'), date('to', 'To'),
    Object.keys(q).some((k) => KEYS.includes(k))
      ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'activity-clear', onclick: () => { location.hash = '#/activity'; } }, icon('x', 'sm'), 'Clear filters') : null);
  const body = el('div', { class: 'page-body' }, bar,
    q.record ? el('div', { class: 'notice', 'data-testid': 'activity-record-filter' }, icon('filter', 'sm'), 'Showing one record’s activity. ', el('a', { href: '#/activity', text: 'Show everything' })) : null);
  const list = el('ul', { class: 'entries', 'data-testid': 'activity-list' });
  const more = el('div', { class: 'row load-more' });
  const box = el('div', { class: 'card' }, skeletonRows(8));
  body.appendChild(box); v.appendChild(body);
  const params = () => { const p = {}; KEYS.forEach((k) => { if (q[k]) p[k] = q[k]; }); return p; };
  const load = async (cursor) => {
    try {
      const out = await api('GET', '/activity' + qs(Object.assign(params(), { cursor, limit: 50, group: 1 })));
      if (!cursor) { clear(box); clear(list); box.append(list, more); }
      if (!out.items.length && !cursor) { clear(box).appendChild(empty('No activity matches', 'Try fewer filters.', null, 'history')); return; }
      const groups = {}; (out.groups || []).forEach((g) => { groups[g.key] = g; });
      const open = {};
      out.items.forEach((a) => {
        const g = a.group && groups[a.group];
        if (!g) { list.appendChild(activityEntry(a)); return; }
        if (!open[g.key]) { open[g.key] = groupEntry(g, a); list.appendChild(open[g.key].li); }
        open[g.key].inner.appendChild(activityEntry(a));
      });
      clear(more);
      if (out.next_cursor) more.appendChild(el('button', { class: 'btn', type: 'button', 'data-testid': 'activity-more', text: 'Load older', onclick: () => load(out.next_cursor) }));
    } catch (e) { clear(box).appendChild(errorBox(e, () => load())); }
  };
  S.listReload = () => load(); load();
  S.onQueryChange = (nr) => { if (KEYS.some((k) => (nr.q[k] || '') !== (q[k] || ''))) { clear(v); viewActivity(v, nr); } };
}

async function exportCsv(q) {
  try {
    const p = {}; KEYS.forEach((k) => { if (q[k]) p[k] = q[k]; });
    const out = await api('GET', '/activity' + qs(Object.assign(p, { format: 'csv' })));
    const a = el('a', { href: URL.createObjectURL(new Blob([out.csv], { type: 'text/csv' })), download: 'activity-' + new Date().toISOString().slice(0, 10) + '.csv' });
    document.body.appendChild(a); a.click(); a.remove();
    toast('Exported the filtered activity');
  } catch (e) { failToast(e, 'Not exported'); }
}
