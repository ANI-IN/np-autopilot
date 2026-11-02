/* Data quality: counts first, then the records to act on. */
import { S, el, add, clear, icon, typeIcon, api, ago, skeletonBlock, errorBox, plural } from '../core.js';
import { kindLabel } from '../detail.js';

export function viewQuality(v) {
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Data quality' }), el('span', { class: 'sub', text: 'What is incomplete, unconnected, broken or flagged.' })));
  const out = el('div', { class: 'page-body', 'data-testid': 'quality' }, skeletonBlock(8));
  v.appendChild(out);
  const load = async () => {
    try {
      const [q, d] = await Promise.all([api('GET', '/quality'), api('GET', '/dashboard')]);
      const a = d.attention, t = q.totals;
      clear(out);
      out.appendChild(el('div', { class: 'stat-row' }, [['Live records', t.live, 'live'], ['No owner', t.no_owner, 'no-owner'], ['Missing required fields', a.counts.missing_required, 'missing-required'],
        ['Broken links', q.links.problems, 'broken'], ['Flagged', a.counts.flagged, 'flagged'], ['Not connected', t.orphans, 'not-connected']]
        .map(([k, val, id]) => el('div', { class: 'stat', 'data-testid': 'q-' + id }, el('div', { class: 'v', text: String(val || 0) }), el('div', { class: 'k', text: k })))));
      const grid = el('div', { class: 'two-col', style: 'margin-top:24px' });
      const left = el('div', { class: 'col', style: 'gap:24px' }), right = el('div', { class: 'col', style: 'gap:24px' });
      grid.append(left, right); out.appendChild(grid);
      const list = (title, items, row, emptyText, tid) => {
        const ul = el('ul', { class: 'list bordered', 'data-testid': tid });
        if (!items.length) ul.appendChild(el('li', { class: 'link-row faint', text: emptyText }));
        items.forEach((x) => ul.appendChild(el('li', null, row(x))));
        return el('section', null, el('div', { class: 'row', style: 'margin-bottom:8px' }, el('h2', { text: title }), el('span', { class: 'count', text: items.length })), ul);
      };
      const rec = (x, extra) => el('a', { class: 'link-row', href: '#/quality?open=' + x.id }, typeIcon(x.type), el('span', { class: 'truncate', text: x.name, style: 'color:var(--text);flex:1' }), extra ? el('span', { class: 'faint xs truncate', text: extra }) : null);
      left.appendChild(list('Records without an owner', q.unowned, (x) => rec(x), 'Every record has an owner.', 'q-unowned'));
      left.appendChild(list('Missing required fields', a.missing_required, (x) => rec(x, x.field), 'Every required field is filled in.', 'q-missing-required'));
      left.appendChild(list('Not connected to anything', q.orphans, (x) => rec(x), 'Every record has at least one relationship.', 'q-orphans'));
      left.appendChild(list('Relationships that no longer fit the rules', a.misfits, (x) => el('a', { class: 'link-row', href: '#/quality?open=' + x.source_id },
        typeIcon(x.source_type), el('span', { class: 'truncate', style: 'color:var(--text)', text: x.source }), el('span', { class: 'faint small', text: x.label }),
        typeIcon(x.target_type), el('span', { class: 'truncate', style: 'color:var(--text)', text: x.target })), 'Every relationship fits its type’s rules.', 'q-misfits'));
      const L = q.links;
      right.appendChild(el('section', null, el('div', { class: 'row', style: 'margin-bottom:4px' }, el('h2', { text: 'Link health' })),
        el('p', { class: 'muted small', 'data-testid': 'q-link-summary', style: 'margin-bottom:8px', text: L.checked + ' of ' + plural(L.resources, 'link') + ' checked · ' + L.ok + ' working · ' + L.needs_auth + ' need sign-in · ' + L.problems + ' broken' }),
        (() => { const ul = el('ul', { class: 'list bordered', 'data-testid': 'q-broken-links' });
          if (!L.items.length) ul.appendChild(el('li', { class: 'link-row faint', text: L.checked ? 'No broken links among the checked ones.' : 'No links checked yet.' }));
          L.items.forEach((r) => ul.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/quality?res=' + r.id }, icon('link'), el('span', { class: 'truncate', style: 'flex:1;color:var(--text)', text: r.title }),
            el('span', { class: 'badge', text: kindLabel(r.kind) }), el('span', { class: 'badge danger', text: r.http_status ? 'HTTP ' + r.http_status : r.status }), el('span', { class: 'faint xs', text: ago(r.checked_at) })))));
          return ul; })(),
        el('p', { class: 'faint xs', style: 'margin-top:6px', text: 'Links are checked by the knowledge assistant (check_broken_links in Claude Code), never by this server. Drive links behind sign-in count as “need sign-in”, not broken.' })));
      right.appendChild(list('Flagged as incorrect', a.flagged, (x) => el('a', { class: 'link-row', href: '#/approvals?tab=reviews' }, icon('flag'), el('span', { class: 'truncate', style: 'flex:1;color:var(--text)', text: x.name }), el('span', { class: 'faint xs truncate', text: x.reason })), 'Nothing is flagged.', 'q-flagged'));
      right.appendChild(list('Possible duplicates', q.duplicates, (x) => el('div', { class: 'link-row' }, typeIcon(x.type), el('a', { href: '#/quality?open=' + x.a_id, text: x.a_name }), el('span', { class: 'faint', text: '↔' }),
        el('a', { href: '#/quality?open=' + x.b_id, text: x.b_name }), el('span', { class: 'spacer' }), el('span', { class: 'faint xs', text: Math.round(x.similarity * 100) + '% similar' })), 'No similar names found.', 'q-duplicates'));
      const comp = el('ul', { class: 'list bordered', 'data-testid': 'q-course' });
      d.completeness.forEach((c) => comp.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/quality?open=' + c.id }, typeIcon(c.type), el('span', { class: 'truncate', style: 'flex:1;color:var(--text)', text: c.name }),
        el('div', { class: 'bar ' + (c.score >= 80 ? 'ok' : c.score >= 50 ? 'warn' : 'danger'), style: 'width:100px' }, el('span', { style: 'width:' + c.score + '%' })), el('span', { class: 'tabular small', style: 'width:36px;text-align:right', text: c.score + '%' })))));
      left.appendChild(el('section', null, el('h2', { text: 'Completeness by course and program', style: 'margin-bottom:8px' }), comp));
    } catch (e) { clear(out).appendChild(errorBox(e, load)); }
  };
  S.listReload = load; load();
}
