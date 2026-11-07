/* Search results (#/search?q=…&type=…), Direction A (owner decision 2026-11-07).
   The big box on Home and Enter in the palette land here: results grouped by
   record type, a type filter, "See all" per group, links last. Opening a result
   opens its record in the side panel without leaving the results. */
import { S, el, clear, icon, typeIcon, typeLabel, api, qs, skeletonRows, errorBox, empty } from '../core.js';
import { pageHead } from '../page.js';

const GROUP_SHOWN = 5;            // per type before "See all"

export function searchBox({ value = '', big = false, testid = 'search-box', autofocus = false } = {}) {
  const input = el('input', { type: 'search', value, placeholder: 'Search topics, modules, courses, people, resources…', 'aria-label': 'Search the knowledge base',
    'data-testid': testid + '-input', autocomplete: 'off' });
  const form = el('form', { class: 'search-box' + (big ? ' big' : ''), role: 'search', 'data-testid': testid,
    onsubmit: (e) => { e.preventDefault(); const q = input.value.trim(); if (q) { remember(q); location.hash = '#/search' + qs({ q }); } } },
    icon('search'), input, el('button', { class: 'btn primary', type: 'submit', text: 'Search' }));
  // Only when nothing else has the focus: a palette or dialog opened meanwhile keeps it.
  if (autofocus) setTimeout(() => { const a = document.activeElement; if (input.isConnected && (!a || a === document.body)) input.focus(); }, 0);
  return form;
}

const RECENT_KEY = 'kb_recent_searches';
export function recentSearches() { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').slice(0, 6); } catch (e) { return []; } }
function remember(q) {
  try { const r = [q].concat(recentSearches().filter((x) => x.toLowerCase() !== q.toLowerCase())).slice(0, 6); localStorage.setItem(RECENT_KEY, JSON.stringify(r)); } catch (e) { /* storage blocked */ }
}

export function viewSearch(v, r) {
  const q = (r.q.q || '').trim(), type = r.q.type || null;
  v.appendChild(pageHead({ title: 'Search', sub: q ? null : 'Find anything in the knowledge base.' }));
  const body = el('div', { class: 'page-body search-page', 'data-testid': 'search-page' });
  v.appendChild(body);
  body.appendChild(searchBox({ value: q, testid: 'search-page-box', autofocus: !q }));
  const out = el('div', { class: 'search-results', 'data-testid': 'search-results', 'aria-live': 'polite' });
  body.appendChild(out);
  if (!q) { out.appendChild(empty('Type what you are looking for', 'Topics, modules, courses, programs, people and resources are all searched.', null, 'search')); return; }
  out.appendChild(skeletonRows(6));
  const load = async () => {
    try {
      const d = await api('GET', '/search' + qs({ q, limit: 50, types: type }));
      clear(out);
      const groups = new Map();
      d.nodes.forEach((n) => { if (!groups.has(n.type)) groups.set(n.type, []); groups.get(n.type).push(n); });
      const total = d.nodes.length + (type ? 0 : d.resources.length);
      // type filter: All plus each type that has results
      const chips = el('div', { class: 'chip-row', role: 'group', 'aria-label': 'Filter by type', 'data-testid': 'search-type-filter' },
        el('a', { class: 'filter-chip' + (type ? '' : ' on'), href: '#/search' + qs({ q }), 'aria-current': type ? null : 'true', text: 'All' }),
        [...groups.keys()].concat(type && !groups.has(type) ? [type] : []).map((k) => el('a', { class: 'filter-chip' + (type === k ? ' on' : ''), href: '#/search' + qs({ q, type: k }),
          'aria-current': type === k ? 'true' : null, 'data-testid': 'search-type-' + k }, typeIcon(k), typeLabel(k, true))));
      out.append(el('p', { class: 'muted small', 'data-testid': 'search-count', text: total ? total + (total >= 50 ? '+' : '') + ' result' + (total === 1 ? '' : 's') + ' for “' + q + '”' : '' }), chips);
      if (!total) { out.appendChild(empty('Nothing matches “' + q + '”', 'Try fewer words, another spelling, or a broader topic.', null, 'search')); return; }
      for (const [k, items] of groups) {
        const shown = type ? items : items.slice(0, GROUP_SHOWN);
        const sec = el('section', { class: 'card search-group', 'data-testid': 'search-group', 'data-type': k },
          el('div', { class: 'card-head' }, el('h2', { class: 'row gap-1' }, typeIcon(k), typeLabel(k, true)), el('span', { class: 'count', text: items.length }), el('span', { class: 'spacer' }),
            !type && items.length > GROUP_SHOWN ? el('a', { class: 'xs', href: '#/search' + qs({ q, type: k }), 'data-testid': 'search-see-all', text: 'See all ' + items.length }) : null),
          el('ul', { class: 'list' }, shown.map((n) => el('li', null, el('a', { class: 'link-row search-hit', href: '#/search' + qs({ q, type, open: n.id }), 'data-testid': 'search-hit' },
            el('span', { class: 'col gap-0 min-w-0 grow' }, el('span', { class: 'truncate fg', text: n.name }),
              n.summary || n.scope_name ? el('span', { class: 'truncate faint xs', text: [n.scope_name ? 'in ' + n.scope_name : '', n.summary || ''].filter(Boolean).join(' · ') }) : null))))));
        out.appendChild(sec);
      }
      if (!type && d.resources.length) {
        out.appendChild(el('section', { class: 'card search-group', 'data-testid': 'search-group', 'data-type': 'resource' },
          el('div', { class: 'card-head' }, el('h2', { class: 'row gap-1' }, icon('link'), 'Resources'), el('span', { class: 'count', text: d.resources.length })),
          el('ul', { class: 'list' }, d.resources.map((x) => el('li', null, el('a', { class: 'link-row search-hit', href: x.url, target: '_blank', rel: 'noopener noreferrer', 'data-testid': 'search-hit' },
            icon('external-link', 'sm'), el('span', { class: 'truncate fg grow', text: x.title || x.url }), el('span', { class: 'faint xs', text: x.kind || '' })))))));
      }
    } catch (e) { clear(out).appendChild(errorBox(e, load)); }
  };
  load();
  S.onQueryChange = (r2) => { if ((r2.q.q || '') !== q || (r2.q.type || null) !== type) { clear(v); viewSearch(v, r2); } };
}
