/* Dashboard: real numbers only — records by type, completeness by course,
   what needs attention, recent activity as sentences with avatars. */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, avatar, ago, skeletonBlock, errorBox, plural, you, can } from '../core.js';
import { pageHead } from '../page.js';
import { openRecordForm } from '../form.js';

export function viewDashboard(v) {
  v.appendChild(pageHead({ title: 'Dashboard', actions: can('contributor') ? [el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-record-dash', onclick: () => openRecordForm({}) }, icon('plus'), 'New record')] : null }));
  const body = el('div', { class: 'page-body', 'data-testid': 'dashboard' }, skeletonBlock(10));
  v.appendChild(body);
  const load = async () => {
    try {
      const d = await api('GET', '/dashboard');
      clear(body);
      // headline numbers
      // 12-column grid: six equal tiles (2 columns each), then two equal columns (6 each).
      const grid = el('div', { class: 'grid-12', 'data-testid': 'dash-grid' });
      body.appendChild(grid);
      add(grid, [stat('Records', d.totals.nodes, '#/records'), stat('Relationships', d.totals.edges, '#/graph'), stat('Links', d.totals.resources, '#/resources'),
        stat('Awaiting approval', d.totals.pending_proposals, '#/approvals'), stat('Need attention', d.attention.total, '#/quality', 'dash-attention-total'),
        stat('Changed in 7 days', d.totals.changed_7d, can('editor') ? '#/activity' : null)]);
      const left = el('div', { class: 'stack span-6', 'data-testid': 'dash-left' }), right = el('div', { class: 'stack span-6', 'data-testid': 'dash-right' });
      add(grid, [left, right]);
      // records by type
      const max = Math.max(1, ...d.counts.map((c) => c.n));
      const types = el('ul', { class: 'list', 'data-testid': 'dash-types' });
      d.counts.filter((c) => c.n > 0).forEach((c) => types.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?type=' + c.key },
        typeIcon(c.key), el('span', { class: 'truncate type-col', text: typeLabel(c.key, true), 'data-testid': 'count-' + c.key }),
        el('div', { class: 'bar grow' }, el('span', { style: 'width:' + Math.round(100 * c.n / max) + '%;background:' + c.color })),
        el('span', { class: 'tabular num-col', text: c.n })))));
      left.appendChild(block('Records by type', types));
      // completeness by course
      const comp = el('ul', { class: 'list', 'data-testid': 'dash-completeness' });
      d.completeness.forEach((c) => comp.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?open=' + c.id },
        typeIcon(c.type), el('span', { class: 'truncate grow', text: c.name }), el('span', { class: 'faint xs', text: plural(c.size - 1, 'item') }),
        el('div', { class: 'bar w-120 ' + (c.score >= 80 ? 'ok' : c.score >= 50 ? 'warn' : 'danger') }, el('span', { style: 'width:' + c.score + '%' })),
        el('span', { class: 'tabular num-col', text: c.score + '%' })))));
      if (!d.completeness.length) comp.appendChild(el('li', { class: 'faint small', text: 'No courses or programs yet.' }));
      left.appendChild(block('Completeness by course and program', comp, 'Share of owner, summary, required fields, links and placement filled in, across everything inside.'));
      // needs attention
      const a = d.attention, att = el('div', { class: 'col gap-3', 'data-testid': 'dash-attention' });
      const group = (label, items, render, href) => {
        if (!items.length) return;
        const ul = el('ul', { class: 'list' });
        items.slice(0, 5).forEach((x) => ul.appendChild(el('li', null, render(x))));
        att.appendChild(el('div', { 'data-testid': 'attention-group' }, el('div', { class: 'row small mb-1' }, el('strong', { text: label }), el('span', { class: 'count', 'data-testid': 'attention-count', text: a.counts[href] }), el('span', { class: 'spacer' }),
          el('a', { class: 'xs', href: '#/quality', text: 'See all' })), ul));
      };
      const rec = (x, extra) => el('a', { class: 'link-row', href: '#/records?open=' + x.id }, typeIcon(x.type), el('span', { class: 'truncate fg', text: x.name }), extra ? el('span', { class: 'faint xs truncate', text: extra }) : null);
      group('No owner', a.no_owner, (x) => rec(x), 'no_owner');
      group('Broken links', a.broken_links, (x) => el('a', { class: 'link-row', href: '#/resources?res=' + x.id }, icon('link'), el('span', { class: 'truncate fg', text: x.name }), el('span', { class: 'badge danger', text: x.http_status ? 'HTTP ' + x.http_status : 'Broken' })), 'broken_links');
      group('Missing required fields', a.missing_required, (x) => rec(x, x.field), 'missing_required');
      group('Flagged as incorrect', a.flagged, (x) => el('a', { class: 'link-row', href: '#/approvals?tab=reviews' }, icon('flag'), el('span', { class: 'truncate fg', text: x.name }), el('span', { class: 'faint xs truncate', text: x.reason })), 'flagged');
      group('Not connected to anything', a.orphans, (x) => rec(x), 'orphans');
      group('Relationships that no longer fit the rules', a.misfits, (x) => el('a', { class: 'link-row', href: '#/records?open=' + x.source_id }, typeIcon(x.source_type),
        el('span', { class: 'truncate fg', text: x.source }), el('span', { class: 'faint xs', text: x.label }), el('span', { class: 'truncate fg', text: x.target })), 'misfits');
      if (!att.children.length) att.appendChild(el('p', { class: 'faint small', text: 'Nothing needs attention right now.' }));
      right.appendChild(block('Needs attention', att));
      // recent activity
      const act = el('ul', { class: 'list', 'data-testid': 'activity' });
      d.recent.slice(0, 12).forEach((x) => act.appendChild(el('li', null, el('div', { class: 'link-row start' },
        x.actor_type === 'human' && x.actor_id ? avatar(x.actor_id) : el('span', { class: 'avatar system' }, icon(x.actor_type === 'ai' ? 'star' : 'upload', 'sm')),
        el('span', { class: 'small grow' }, sentence(x)), el('span', { class: 'faint xs nowrap', text: ago(x.at) })))));
      if (!d.recent.length) act.appendChild(el('li', { class: 'faint small', text: 'No activity yet.' }));
      if (can('editor')) right.appendChild(block('Recent activity', act, null, el('a', { class: 'xs', href: '#/activity', text: 'All activity' })));
      // Both columns end level: the last card in each grows to the taller column.
      [left, right].forEach((c) => { if (c.lastElementChild) c.lastElementChild.style.flex = '1'; });
    } catch (e) { clear(body).appendChild(errorBox(e, load)); }
  };
  S.listReload = load; load();
}
function stat(k, value, href, testid) {
  const inner = [el('div', { class: 'v', text: value === null || value === undefined ? '0' : String(value) }), el('div', { class: 'k', text: k })];
  return el('div', { class: 'card span-2 dash-tile' }, href ? el('a', { class: 'tile', href, 'data-testid': testid }, inner) : el('div', { class: 'tile', 'data-testid': testid }, inner));
}
function block(title, content, hint, extra) {
  return el('section', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: title }), el('span', { class: 'spacer' }), extra || null),
    el('div', { class: 'card-body' }, hint ? el('p', { class: 'card-hint', text: hint }) : null, content));
}
export function sentence(a) {
  // Every entry names its actor (server-resolved: a person, the AI assistant for
  // a named person, an import, or the system); never "Someone".
  const who = a.actor_type === 'human' && you(a.actor_id) ? 'You' : a.actor_label;
  const what = { insert: 'created', update: 'updated', delete: 'deleted' }[a.action] || a.action;
  const thing = { nodes: '', resources: 'the link', edges: 'a relationship', node_resources: 'a link on a record', node_tags: 'a tag' }[a.table_name];
  const label = a.label;
  const link = label && (a.table_name === 'nodes' || a.table_name === 'resources') && a.action !== 'delete' && a.exists_now !== false
    ? el('a', { href: a.table_name === 'nodes' ? '#/records?open=' + a.row_id : '#/resources?res=' + a.row_id, text: label }) : label ? el('strong', { text: label }) : null;
  return [el('strong', { text: who, 'data-testid': 'activity-actor' }), ' ' + what + ' ', thing ? thing + ' ' : '', link];
}
