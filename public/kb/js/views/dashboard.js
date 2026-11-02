/* Dashboard: real numbers only — records by type, completeness by course,
   what needs attention, recent activity as sentences with avatars. */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, avatar, personName, ago, skeletonBlock, errorBox, plural, you, can } from '../core.js';
import { openRecordForm } from '../form.js';

export function viewDashboard(v) {
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Dashboard' }), el('span', { class: 'spacer' }),
    can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-record-dash', onclick: () => openRecordForm({}) }, icon('plus'), 'New record') : null));
  const body = el('div', { class: 'page-body', 'data-testid': 'dashboard' }, skeletonBlock(10));
  v.appendChild(body);
  const load = async () => {
    try {
      const d = await api('GET', '/dashboard');
      clear(body);
      // headline numbers
      add(body, el('div', { class: 'stat-row', 'data-testid': 'dash-counts' },
        stat('Records', d.totals.nodes, '#/records'), stat('Relationships', d.totals.edges), stat('Links', d.totals.resources, '#/resources'),
        stat('Awaiting approval', d.totals.pending_proposals, '#/approvals'), stat('Need attention', sumAttention(d.attention.counts), '#/quality')));
      const left = el('div', { class: 'col', style: 'gap:24px' }), right = el('div', { class: 'col', style: 'gap:24px' });
      body.appendChild(el('div', { class: 'two-col', style: 'margin-top:24px' }, left, right));
      // records by type
      const max = Math.max(1, ...d.counts.map((c) => c.n));
      const types = el('ul', { class: 'list', 'data-testid': 'dash-types' });
      d.counts.filter((c) => c.n > 0).forEach((c) => types.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?type=' + c.key },
        typeIcon(c.key), el('span', { style: 'width:120px', class: 'truncate', text: typeLabel(c.key, true), 'data-testid': 'count-' + c.key }),
        el('div', { class: 'bar', style: 'flex:1' }, el('span', { style: 'width:' + Math.round(100 * c.n / max) + '%;background:' + c.color })),
        el('span', { class: 'tabular', style: 'width:40px;text-align:right', text: c.n })))));
      left.appendChild(block('Records by type', types));
      // completeness by course
      const comp = el('ul', { class: 'list', 'data-testid': 'dash-completeness' });
      d.completeness.forEach((c) => comp.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?open=' + c.id },
        typeIcon(c.type), el('span', { class: 'truncate', style: 'flex:1', text: c.name }), el('span', { class: 'faint xs', text: plural(c.size - 1, 'item') }),
        el('div', { class: 'bar ' + (c.score >= 80 ? 'ok' : c.score >= 50 ? 'warn' : 'danger'), style: 'width:120px' }, el('span', { style: 'width:' + c.score + '%' })),
        el('span', { class: 'tabular', style: 'width:40px;text-align:right', text: c.score + '%' })))));
      if (!d.completeness.length) comp.appendChild(el('li', { class: 'faint small', text: 'No courses or programs yet.' }));
      left.appendChild(block('Completeness by course and program', comp, 'Share of owner, summary, required fields, links and placement filled in, across everything inside.'));
      // needs attention
      const a = d.attention, att = el('div', { class: 'col', style: 'gap:12px', 'data-testid': 'dash-attention' });
      const group = (label, items, render, href) => {
        if (!items.length) return;
        const ul = el('ul', { class: 'list' });
        items.slice(0, 5).forEach((x) => ul.appendChild(el('li', null, render(x))));
        att.appendChild(el('div', null, el('div', { class: 'row small', style: 'margin-bottom:2px' }, el('strong', { text: label }), el('span', { class: 'count', text: a.counts[href] !== undefined ? a.counts[href] : items.length }), el('span', { class: 'spacer' }),
          el('a', { class: 'xs', href: '#/quality', text: 'See all' })), ul));
      };
      const rec = (x, extra) => el('a', { class: 'link-row', href: '#/records?open=' + x.id }, typeIcon(x.type), el('span', { class: 'truncate', text: x.name, style: 'color:var(--text)' }), extra ? el('span', { class: 'faint xs truncate', text: extra }) : null);
      group('No owner', a.no_owner, (x) => rec(x), 'no_owner');
      group('Broken links', a.broken_links, (x) => el('a', { class: 'link-row', href: '#/resources?res=' + x.id }, icon('link'), el('span', { class: 'truncate', text: x.name, style: 'color:var(--text)' }), el('span', { class: 'badge danger', text: x.http_status ? 'HTTP ' + x.http_status : 'Broken' })), 'broken_links');
      group('Missing required fields', a.missing_required, (x) => rec(x, x.field), 'missing_required');
      group('Flagged as incorrect', a.flagged, (x) => el('a', { class: 'link-row', href: '#/approvals?tab=reviews' }, icon('flag'), el('span', { class: 'truncate', text: x.name, style: 'color:var(--text)' }), el('span', { class: 'faint xs truncate', text: x.reason })), 'flagged');
      group('Not connected to anything', a.orphans, (x) => rec(x), 'orphans');
      if (!att.children.length) att.appendChild(el('p', { class: 'faint small', text: 'Nothing needs attention right now.' }));
      right.appendChild(block('Needs attention', att));
      // recent activity
      const act = el('ul', { class: 'list', 'data-testid': 'activity' });
      d.recent.slice(0, 12).forEach((x) => act.appendChild(el('li', null, el('div', { class: 'link-row', style: 'align-items:flex-start' },
        x.actor_type === 'human' && x.actor_id ? avatar(x.actor_id) : el('span', { class: 'avatar', style: '--av:#475569' }, icon(x.actor_type === 'ai' ? 'star' : 'upload', 'sm')),
        el('span', { class: 'small', style: 'flex:1;min-width:0' }, sentence(x)), el('span', { class: 'faint xs', style: 'white-space:nowrap', text: ago(x.at) })))));
      if (!d.recent.length) act.appendChild(el('li', { class: 'faint small', text: 'No activity yet.' }));
      right.appendChild(block('Recent activity', act));
    } catch (e) { clear(body).appendChild(errorBox(e, load)); }
  };
  S.listReload = load; load();
}
function sumAttention(c) { return (c.no_owner || 0) + (c.broken_links || 0) + (c.missing_required || 0) + (c.flagged || 0); }
function stat(k, value, href) {
  const inner = [el('div', { class: 'v', text: value === null || value === undefined ? '0' : String(value) }), el('div', { class: 'k', text: k })];
  return href ? el('a', { class: 'stat', href, style: 'color:inherit;text-decoration:none' }, inner) : el('div', { class: 'stat' }, inner);
}
function block(title, content, hint) {
  return el('section', null, el('div', { class: 'row', style: 'margin-bottom:8px' }, el('h2', { text: title })), hint ? el('p', { class: 'faint xs', style: 'margin:-4px 0 8px', text: hint }) : null, content);
}
function sentence(a) {
  const who = a.actor_type === 'ai' ? 'The AI assistant' : a.actor_type === 'import' ? 'The Sheets import' : a.actor_type === 'system' ? 'The system' : you(a.actor_id) ? 'You' : (personName(a.actor_id) || 'Someone');
  const what = { insert: 'created', update: 'updated', delete: 'deleted' }[a.action] || a.action;
  const thing = { nodes: '', resources: 'the link', edges: 'a relationship', node_resources: 'a link on a record', node_tags: 'a tag' }[a.table_name];
  const label = a.label;
  const link = label && (a.table_name === 'nodes' || a.table_name === 'resources') && a.action !== 'delete'
    ? el('a', { href: a.table_name === 'nodes' ? '#/records?open=' + a.row_id : '#/resources?res=' + a.row_id, text: label }) : label ? el('strong', { text: label }) : null;
  return [el('strong', { text: who }), ' ' + what + ' ', thing ? thing + ' ' : '', link];
}
