/* Dashboard (run 6, F1): everything on one screen, without scrolling, at
   1536×730 and 1920×1080. One request (/dashboard, cached until the next
   change): the key numbers; what needs attention; the newest activity as the
   server's sentences; quick actions, what you own and the records by type.
   Nothing that another page already lists in full (completeness lives on
   Data quality). */
import { S, el, clear, icon, typeIcon, typeLabel, api, ago, skeletonBlock, errorBox, can, failToast, qs } from '../core.js';
import { openRecordForm } from '../form.js';
import { sentenceParts } from './activity.js';
import { searchBox, recentSearches } from './search.js';

/* Home (owner decision 2026-11-07, docs/design/phase1/DECISION.md): Direction C's
   search-first top (one big box and suggestion chips) above Direction A's cards. */
const SUGGEST_TYPES = ['program', 'course', 'module', 'topic', 'instructor'];
function hero() {
  const recent = recentSearches();
  const chips = el('div', { class: 'chip-row center', 'data-testid': 'home-suggestions', 'aria-label': 'Suggestions' },
    recent.map((q) => el('a', { class: 'filter-chip', href: '#/search' + qs({ q }), 'data-testid': 'home-recent' }, icon('history', 'sm'), q)),
    SUGGEST_TYPES.filter((k) => S.typeByKey[k]).map((k) => el('a', { class: 'filter-chip', href: '#/records?type=' + k, 'data-testid': 'home-type-' + k }, typeIcon(k), typeLabel(k, true))));
  return el('section', { class: 'home-hero', 'data-testid': 'home-hero' },
    el('h1', { class: 'home-title', text: 'What are you looking for?' }),
    searchBox({ big: true, testid: 'home-search', autofocus: true }), chips);
}

const ATTENTION = [['no_owner', 'No owner'], ['missing_required', 'Missing required fields'], ['broken_links', 'Broken links'],
  ['flagged', 'Flagged'], ['orphans', 'Not connected to anything'], ['misfits', 'Relationships that no longer fit'],
  ['sync_conflicts', 'Sync conflicts'], ['removed_at_source', 'Removed at the source']];

export function viewDashboard(v) {
  v.appendChild(hero());
  const body = el('div', { class: 'page-body dash', 'data-testid': 'dashboard' }, skeletonBlock(6));
  v.appendChild(body);
  linkOnce();
  const load = async () => {
    try {
      const [d, progs] = await Promise.all([api('GET', '/dashboard'),
        api('GET', '/nodes' + qs({ type: 'program', limit: 6, sort: 'name' })).catch(() => ({ items: [] }))]);
      if (S.applyCounts) S.applyCounts(d);          // the sidebar counts, from the same reply
      clear(body);
      const grid = el('div', { class: 'dash-grid', 'data-testid': 'dash-grid' });
      body.appendChild(grid);
      // 1. key numbers
      grid.appendChild(el('div', { class: 'dash-tiles' }, [stat('Records', d.totals.nodes, '#/records'), stat('Relationships', d.totals.edges, can('admin') ? '#/graph' : null),
        stat('Links', d.totals.resources, '#/resources'), stat('Awaiting approval', d.totals.pending_proposals, '#/approvals'),
        stat('Need attention', d.attention.total, '#/quality', 'dash-attention-total'), stat('Changed in 7 days', d.totals.changed_7d, can('editor') ? '#/activity' : null)]));
      const cols = el('div', { class: 'dash-cols' });
      grid.appendChild(cols);
      // Programs (the KYP-based program pages follow with the new model)
      const pl = el('ul', { class: 'list', 'data-testid': 'home-programs' });
      (progs.items || []).forEach((x) => pl.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/programs?open=' + x.id },
        typeIcon('program'), el('span', { class: 'truncate grow fg', text: x.name })))));
      if (!(progs.items || []).length) pl.appendChild(el('li', { class: 'faint small', text: 'No programs yet.' }));
      cols.appendChild(block('Programs', pl, el('a', { class: 'xs', href: '#/programs', text: 'All programs' })));
      // 2. needs attention: each category with its count, then the first records to fix
      const a = d.attention, att = el('div', { class: 'col gap-2', 'data-testid': 'dash-attention' });
      const cats = ATTENTION.filter(([k]) => (a.counts[k] || 0) > 0);
      const catList = el('ul', { class: 'list' });
      cats.forEach(([k, label]) => catList.appendChild(el('li', { 'data-testid': 'attention-group' }, el('a', { class: 'link-row', href: '#/quality' },
        el('span', { class: 'truncate grow fg', text: label }), el('span', { class: 'count', 'data-testid': 'attention-count', text: a.counts[k] })))));
      const first = [];
      for (const [k] of cats) (a[k] || []).forEach((x) => { if (first.length < 4 && x.id && x.name) first.push(x); });
      if (cats.length) {
        att.appendChild(catList);
        if (first.length) att.appendChild(el('ul', { class: 'list dash-first' }, first.map((x) => el('li', null,
          el('a', { class: 'link-row', href: '#/records?open=' + x.id }, x.type ? typeIcon(x.type) : icon('link'), el('span', { class: 'truncate fg', text: x.name }))))));
      } else att.appendChild(el('p', { class: 'faint small', text: 'Nothing needs attention right now.' }));
      if (can('contributor')) cols.appendChild(block('Needs attention', att, el('a', { class: 'xs', href: '#/quality', text: 'See all' })));
      // 3. recent activity: the server's sentences (editors and admins, as on the Activity page)
      if (can('editor')) {
        const act = el('ul', { class: 'list', 'data-testid': 'activity' });
        (d.recent_sentences || []).forEach((x) => act.appendChild(el('li', { class: 'dash-entry' },
          el('span', { class: 'small grow dash-sentence', title: x.sentence || '' }, sentenceParts(x)), el('time', { class: 'faint xs nowrap', datetime: x.at, title: new Date(x.at).toLocaleString(), text: ago(x.at) }))));
        if (!(d.recent_sentences || []).length) act.appendChild(el('li', { class: 'faint small', text: 'No activity yet.' }));
        cols.appendChild(block('Recently changed', act, el('a', { class: 'xs', href: '#/activity', text: 'All activity' })));
      }
      // 4. quick actions, what you own, records by type
      const side = el('div', { class: 'col gap-3' });
      const actions = el('div', { class: 'dash-actions' });
      if (can('contributor')) actions.appendChild(el('button', { class: 'btn primary sm', type: 'button', 'data-testid': 'new-record-dash', onclick: () => openRecordForm({}) }, icon('plus'), 'New record'));
      if (can('admin')) actions.appendChild(el('a', { class: 'btn sm', href: '#/graph' }, icon('network'), 'Graph editor'));
      actions.appendChild(el('a', { class: 'btn sm', href: '/' }, icon('globe'), 'Map'));
      actions.appendChild(el('a', { class: 'btn sm', href: '#/teaching' }, icon('users'), 'Who teaches what'));
      if (can('admin')) actions.appendChild(el('a', { class: 'btn sm', href: '#/settings?tab=sync' }, icon('refresh-cw'), 'Sources & sync'));
      side.appendChild(actions);
      const owned = d.owned || { items: [] }, ow = el('ul', { class: 'list', 'data-testid': 'owned-by-you' });
      (owned.items || []).slice(0, 4).forEach((x) => ow.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?open=' + x.id, 'data-testid': 'owned-row' },
        typeIcon(x.type), el('span', { class: 'truncate grow fg', text: x.name }), el('span', { class: 'faint xs', text: x.how || '' })))));
      if (!(owned.items || []).length) ow.appendChild(el('li', { class: 'faint small', text: owned.person ? 'Nothing is owned by you or your person record yet.' : 'Nothing is owned by you yet.' }));
      if (S.myLink && S.myLink.status === 'ambiguous') ow.appendChild(el('li', { class: 'faint small' }, 'More than one person record has your name: ', el('a', { href: '#/settings?tab=people', text: 'claim yours' })));
      side.appendChild(el('div', null, el('h3', { class: 'dash-sub', text: 'My items' }), ow));
      const types = el('div', { class: 'dash-types', 'data-testid': 'dash-types' });
      d.counts.filter((c) => c.n > 0).forEach((c) => types.appendChild(el('a', { class: 'chip', href: '#/records?type=' + c.key, 'data-testid': 'count-' + c.key },
        typeIcon(c.key), el('span', { text: typeLabel(c.key, c.n !== 1) }), el('span', { class: 'count', text: c.n }))));
      side.appendChild(el('div', null, el('h3', { class: 'dash-sub', text: 'Records by type' }), types));
      cols.appendChild(block('My items and shortcuts', side));
    } catch (e) { clear(body).appendChild(errorBox(e, load)); if (S.refreshCounts) S.refreshCounts(); }
  };
  S.listReload = load; load();
}

/* Link the signed-in account to its person record once per browser session
   (it used to run on every dashboard load: a write per visit). */
function linkOnce() {
  let done = false; try { done = sessionStorage.getItem('kb_linked') === '1'; } catch (e) { /* storage blocked */ }
  if (done) return;
  api('POST', '/my/link').then((me) => {
    S.myLink = me; S.myPerson = me.person || null;
    try { sessionStorage.setItem('kb_linked', '1'); } catch (e) { /* ignore */ }
  }).catch((e) => { if (e.status && e.status >= 500) failToast(e, 'Could not link your person record'); });
}

function stat(k, value, href, testid) {
  const inner = [el('div', { class: 'v', text: value === null || value === undefined ? '0' : String(value) }), el('div', { class: 'k', text: k })];
  return el('div', { class: 'card dash-tile' }, href ? el('a', { class: 'tile', href, 'data-testid': testid }, inner) : el('div', { class: 'tile', 'data-testid': testid }, inner));
}
function block(title, content, extra) {
  return el('section', { class: 'card dash-card' }, el('div', { class: 'card-head' }, el('h2', { text: title }), el('span', { class: 'spacer' }), extra || null),
    el('div', { class: 'card-body' }, content));
}
