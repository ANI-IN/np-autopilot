/* Admin overview (#/admin): where the map's admin button lands (owner decision
   2026-11-07: "the map's admin-only button should open the Admin area"). One
   card per admin tool the signed-in role can use, with its count. The tools
   themselves check the role on the server; this page only lists them. */
import { S, el, icon, can } from '../core.js';
import { pageHead } from '../page.js';
import { ADMIN_NAV } from '../app.js';

const WHAT = {
  graph: 'Arrange and connect records on the editable graph.',
  approvals: 'Proposed changes waiting for an editor.',
  quality: 'Records missing an owner, required fields or links.',
  activity: 'Every change, who made it and when.',
  archived: 'Archived records, relationships and links; restore them here.',
  'settings?tab=members': 'Who can view, contribute, edit and administer.',
  'settings?tab=sync': 'The connected sources, the sync log and re-runs.',
};

export function viewAdmin(v) {
  v.appendChild(pageHead({ title: 'Admin', sub: 'The tools for keeping the knowledge base correct. Only the ones your role can use are shown.' }));
  const items = ADMIN_NAV.filter(([path, , , , role]) => path !== 'admin' && can(role));
  const counts = S.counts || {};
  const grid = el('div', { class: 'page-body admin-grid', 'data-testid': 'admin-overview' });
  if (!items.length) grid.appendChild(el('p', { class: 'muted', text: 'Your role has no admin tools.' }));
  items.forEach(([path, label, ic, countKey]) => grid.appendChild(el('a', { class: 'card admin-card', href: '#/' + path, 'data-testid': 'admin-card' },
    el('div', { class: 'row gap-2' }, icon(ic), el('h2', { text: label }), el('span', { class: 'spacer' }),
      countKey && counts[countKey] ? el('span', { class: 'count', text: counts[countKey] }) : null),
    el('p', { class: 'muted small', text: WHAT[path] || '' }))));
  v.appendChild(grid);
}
