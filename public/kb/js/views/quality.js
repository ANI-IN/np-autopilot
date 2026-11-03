/* Data quality: counts first, then the records to act on. */
import { S, el, add, clear, icon, typeIcon, api, ago, skeletonBlock, errorBox, plural, can } from '../core.js';
import { pageHead } from '../page.js';
import { kindLabel } from '../detail.js';

export function viewQuality(v) {
  v.appendChild(pageHead({ title: 'Data quality', sub: 'What is incomplete, unconnected, broken or flagged.' }));
  const out = el('div', { class: 'page-body', 'data-testid': 'quality' }, skeletonBlock(8));
  v.appendChild(out);
  // On a large knowledge base the checks take a while: say so instead of a silent skeleton.
  const slow = setTimeout(() => { if (out.querySelector('[aria-busy=true]')) out.prepend(el('p', { class: 'faint small mb-3', role: 'status', 'data-testid': 'q-slow', text: 'Checking every record. On a large knowledge base this takes up to a minute.' })); }, 3000);
  const load = async () => {
    try {
      const [q, d] = await Promise.all([api('GET', '/quality'), api('GET', '/dashboard')]);
      clearTimeout(slow);
      const a = d.attention, t = q.totals;
      clear(out);
      out.appendChild(el('div', { class: 'stat-row' }, [['Need attention', a.total, 'total'], ['No owner', a.counts.no_owner, 'no-owner'], ['Missing required fields', a.counts.missing_required, 'missing-required'],
        ['Broken links', a.counts.broken_links, 'broken'], ['Flagged', a.counts.flagged, 'flagged'], ['Not connected', a.counts.orphans, 'not-connected'], ['Rule misfits', a.counts.misfits, 'misfits'],
        ['Sync conflicts', a.counts.sync_conflicts, 'sync-conflicts'], ['Removed at source', a.counts.removed_at_source, 'removed-at-source']]
        .map(([k, val, id]) => el('div', { class: 'stat', 'data-testid': 'q-' + id }, el('div', { class: 'v', text: String(val || 0) }), el('div', { class: 'k', text: k })))));
      const grid = el('div', { class: 'two-col mt-5' });
      const left = el('div', { class: 'col gap-5' }), right = el('div', { class: 'col gap-5' });
      grid.append(left, right); out.appendChild(grid);
      const list = (title, items, row, emptyText, tid) => {
        const ul = el('ul', { class: 'list bordered', 'data-testid': tid });
        if (!items.length) ul.appendChild(el('li', { class: 'link-row faint', text: emptyText }));
        items.forEach((x) => ul.appendChild(el('li', null, row(x))));
        return el('section', null, el('div', { class: 'row mb-2' }, el('h2', { text: title }), el('span', { class: 'count', text: items.length })), ul);
      };
      const rec = (x, extra) => el('a', { class: 'link-row', href: '#/quality?open=' + x.id }, typeIcon(x.type), el('span', { class: 'truncate grow fg', text: x.name }), extra ? el('span', { class: 'faint xs truncate', text: extra }) : null);
      left.appendChild(list('Records without an owner', q.unowned, (x) => rec(x), 'Every record has an owner.', 'q-unowned'));
      left.appendChild(list('Missing required fields', a.missing_required, (x) => rec(x, x.field), 'Every required field is filled in.', 'q-missing-required'));
      left.appendChild(list('Not connected to anything', q.orphans, (x) => rec(x), 'Every record has at least one relationship.', 'q-orphans'));
      left.appendChild(list('Relationships that no longer fit the rules', a.misfits, (x) => el('a', { class: 'link-row', href: '#/quality?open=' + x.source_id },
        typeIcon(x.source_type), el('span', { class: 'truncate fg', text: x.source }), el('span', { class: 'faint small', text: x.label }),
        typeIcon(x.target_type), el('span', { class: 'truncate fg', text: x.target })), 'Every relationship fits its type’s rules.', 'q-misfits'));
      // From the sync (run 5): edits the sync did not overwrite, and rows gone from the original site.
      if (can('editor')) {
        const box = el('div', { class: 'col gap-5' });
        left.appendChild(box);
        api('GET', '/quality/sync').then((sq) => {
          box.appendChild(list('Sync conflicts: edited here, changed at the source', sq.conflicts, (x) => rec(x, x.unit === 'record' ? 'kept your edit' : x.unit),
            'No conflicts: every source change applied cleanly.', 'q-sync-conflict-list'));
          box.appendChild(list('Removed at the source (kept here)', sq.removed_at_source, (x) => rec(x, 'review: archive if no longer needed'),
            'Nothing has disappeared from the original site.', 'q-removed-list'));
        }).catch(() => {});
      }
      const L = q.links;
      right.appendChild(el('section', null, el('div', { class: 'row mb-1' }, el('h2', { text: 'Link health' })),
        el('p', { class: 'muted small mb-2', 'data-testid': 'q-link-summary', text: L.checked + ' of ' + plural(L.resources, 'link') + ' checked · ' + L.ok + ' working · ' + L.needs_auth + ' need sign-in · ' + L.problems + ' broken' }),
        (() => { const ul = el('ul', { class: 'list bordered', 'data-testid': 'q-broken-links' });
          if (!L.items.length) ul.appendChild(el('li', { class: 'link-row faint', text: L.checked ? 'No broken links among the checked ones.' : 'No links checked yet.' }));
          L.items.forEach((r) => ul.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/quality?res=' + r.id }, icon('link'), el('span', { class: 'truncate grow fg', text: r.title }),
            el('span', { class: 'badge', text: kindLabel(r.kind) }), el('span', { class: 'badge danger', text: r.http_status ? 'HTTP ' + r.http_status : r.status }), el('span', { class: 'faint xs', text: ago(r.checked_at) })))));
          return ul; })(),
        el('p', { class: 'faint xs mt-1', text: 'Links are checked by the knowledge assistant (check_broken_links in Claude Code), never by this server. Drive links behind sign-in count as “need sign-in”, not broken.' })));
      right.appendChild(list('Flagged as incorrect', a.flagged, (x) => el('a', { class: 'link-row', href: '#/approvals?tab=reviews' }, icon('flag'), el('span', { class: 'truncate grow fg', text: x.name }), el('span', { class: 'faint xs truncate', text: x.reason })), 'Nothing is flagged.', 'q-flagged'));
      right.appendChild(list('Possible duplicates', q.duplicates, (x) => el('div', { class: 'link-row' }, typeIcon(x.type), el('a', { href: '#/quality?open=' + x.a_id, text: x.a_name }), el('span', { class: 'faint', text: '↔' }),
        el('a', { href: '#/quality?open=' + x.b_id, text: x.b_name }), el('span', { class: 'spacer' }), el('span', { class: 'faint xs', text: Math.round(x.similarity * 100) + '% similar' })), 'No similar names found.', 'q-duplicates'));
      const comp = el('ul', { class: 'list bordered', 'data-testid': 'q-course' });
      d.completeness.forEach((c) => comp.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/quality?open=' + c.id }, typeIcon(c.type), el('span', { class: 'truncate grow fg', text: c.name }),
        el('div', { class: 'bar w-100 ' + (c.score >= 80 ? 'ok' : c.score >= 50 ? 'warn' : 'danger') }, el('span', { style: 'width:' + c.score + '%' })), el('span', { class: 'tabular small num-col', text: c.score + '%' })))));
      left.appendChild(el('section', null, el('h2', { text: 'Completeness by course and program', class: 'mb-2' }), comp));
    } catch (e) { clearTimeout(slow); clear(out).appendChild(errorBox(e, load)); }
  };
  S.listReload = load; load();
}
