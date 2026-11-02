/* Approvals: proposals (contributors' and the AI's creates, archives,
   removals; editors' type changes) and Reviews (records/links flagged as
   incorrect, assigned to their owner). */
import { S, el, clear, icon, typeIcon, api, toast, failToast, avatar, personName, ago, skeletonRows, empty, errorBox, can, setQuery, openDialog, closeDialog, you } from '../core.js';
import { refreshCounts } from '../app.js';

const ACTION = { archive: 'Archive', delete: 'Delete', create: 'Create', type_change: 'Change types' };

export function viewApprovals(v, r) {
  const tab = r.q.tab === 'reviews' ? 'reviews' : 'proposals';
  v.appendChild(el('div', { class: 'page-head' }, el('h1', { text: 'Approvals' })));
  v.appendChild(el('div', { class: 'tabs', role: 'tablist' },
    el('a', { href: '#/approvals', role: 'tab', 'aria-selected': tab === 'proposals' ? 'true' : 'false', 'data-testid': 'tab-proposals' }, 'Proposals'),
    el('a', { href: '#/approvals?tab=reviews', role: 'tab', 'aria-selected': tab === 'reviews' ? 'true' : 'false', 'data-testid': 'tab-reviews' }, icon('flag', 'sm'), 'Reviews')));
  const box = el('div', { 'data-testid': tab === 'reviews' ? 'reviews' : 'proposals' }, skeletonRows(5));
  v.appendChild(box);
  const load = tab === 'reviews' ? () => loadReviews(box) : () => loadProposals(box);
  S.listReload = load; load();
  S.onQueryChange = (nr) => { if ((nr.q.tab || '') !== (r.q.tab || '')) { clear(v); viewApprovals(v, nr); } };
}

async function loadProposals(box) {
  try {
    const items = (await api('GET', '/proposals')).items;
    clear(box);
    if (!items.length) { box.appendChild(empty('Nothing waiting', 'When a contributor or the AI assistant proposes a change, it appears here for an editor to approve.', null, 'circle-check')); return; }
    const ul = el('ul', { class: 'list' });
    items.forEach((x) => {
      const p = x.payload || {};
      const detail = x.action === 'create' ? 'New ' + (p.type || 'record') + (p.parents && p.parents.length ? ' with placement' : '') + ((p.resources || []).length ? ', ' + p.resources.length + ' link(s)' : '')
        : x.action === 'type_change' ? (p.op || '').replace('_', ' ') : x.target_table.replace('node_resources', 'link on a record').replace(/s$/, '');
      const decide = (yes) => async () => {
        try { const out = await api('POST', '/proposals/' + x.id + '/' + (yes ? 'approve' : 'reject'));
          toast(yes ? 'Approved and applied' : 'Rejected', out.result && out.result.id && x.action === 'create' ? { action: { label: 'Open', fn: () => setQuery({ open: out.result.id }) } } : {});
          loadProposals(box); refreshCounts(); }
        catch (e) { failToast(e, 'Not decided'); }
      };
      ul.appendChild(el('li', { 'data-testid': 'proposal', style: 'border-bottom:1px solid var(--border)' }, el('div', { class: 'link-row', style: 'padding:12px 24px;align-items:flex-start' },
        x.created_by ? avatar(x.created_by) : el('span', { class: 'avatar', style: '--av:#475569' }, icon('star', 'sm')),
        el('div', { class: 'col', style: 'gap:2px;flex:1;min-width:0' },
          el('div', { class: 'row' }, el('span', { class: 'badge ' + (x.action === 'create' ? 'accent' : 'warn'), text: ACTION[x.action] || x.action }), el('strong', { class: 'truncate', text: x.target_label || '(record)' })),
          el('div', { class: 'faint xs' }, (x.actor_type === 'ai' ? 'The AI assistant' : you(x.created_by) ? 'You' : personName(x.created_by) || 'Someone') + ' · ' + detail + ' · ' + ago(x.created_at)),
          x.reason && x.action !== 'create' ? el('div', { class: 'small', text: '“' + x.reason + '”' }) : null),
        x.target_id && x.target_table === 'nodes' ? el('a', { class: 'btn ghost sm', href: '#/approvals?open=' + x.target_id }, 'View') : null,
        x.action === 'create' ? el('button', { class: 'btn ghost sm', type: 'button', onclick: () => openDialog([el('h2', { text: 'Proposed record' }), el('pre', { class: 'mono', style: 'white-space:pre-wrap;max-height:50vh;overflow:auto', text: JSON.stringify(p, null, 2) }),
          el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Close', onclick: closeDialog }))], { label: 'Proposed record', wide: true }) }, 'Details') : null,
        can(x.action === 'type_change' ? 'admin' : 'editor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'reject', text: 'Reject', onclick: decide(false) }) : null,
        can(x.action === 'type_change' ? 'admin' : 'editor') ? el('button', { class: 'btn primary sm', type: 'button', 'data-testid': 'approve', text: 'Approve', onclick: decide(true) }) : null)));
    });
    box.appendChild(ul);
  } catch (e) { clear(box).appendChild(errorBox(e, () => loadProposals(box))); }
}

async function loadReviews(box) {
  try {
    const items = (await api('GET', '/flags?status=open')).items;
    clear(box);
    if (!items.length) { box.appendChild(empty('No open reviews', 'When someone flags a record or link as incorrect, the owner sees it here.', null, 'flag')); return; }
    const ul = el('ul', { class: 'list' });
    items.forEach((f) => {
      const close = (outcome) => () => {
        const ta = el('textarea', { rows: '2', placeholder: outcome === 'resolve' ? 'What did you change?' : 'Why is it fine as it is?', 'aria-label': 'Resolution', 'data-testid': 'flag-resolution' });
        openDialog([el('h2', { text: outcome === 'resolve' ? 'Mark as fixed' : 'Dismiss flag' }), ta, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
          el('button', { class: 'btn primary', type: 'button', text: outcome === 'resolve' ? 'Mark fixed' : 'Dismiss', 'data-testid': 'flag-close', onclick: async () => {
            try { await api('POST', '/flags/' + f.id + '/' + outcome, { resolution: ta.value.trim() || null }); closeDialog(); toast(outcome === 'resolve' ? 'Marked fixed' : 'Dismissed'); loadReviews(box); refreshCounts(); }
            catch (e) { failToast(e, 'Not closed'); } } }))], { label: 'Close flag' });
      };
      const href = f.target_table === 'nodes' ? '#/approvals?tab=reviews&open=' + f.target_id : '#/approvals?tab=reviews&res=' + f.target_id;
      ul.appendChild(el('li', { 'data-testid': 'review', style: 'border-bottom:1px solid var(--border)' }, el('div', { class: 'link-row', style: 'padding:12px 24px;align-items:flex-start' },
        avatar(f.created_by),
        el('div', { class: 'col', style: 'gap:2px;flex:1;min-width:0' },
          el('div', { class: 'row' }, f.target_type === 'resource' ? icon('link') : typeIcon(f.target_type), el('a', { href, class: 'strong truncate', text: f.target_name || '(deleted)' }),
            f.assigned_to && you(f.assigned_to) ? el('span', { class: 'badge accent', text: 'Assigned to you' }) : f.assigned_to ? el('span', { class: 'faint xs', text: 'Owner: ' + personName(f.assigned_to) }) : el('span', { class: 'badge warn', text: 'No owner' })),
          el('div', { class: 'small', text: '“' + f.reason + '”' }),
          el('div', { class: 'faint xs', text: (you(f.created_by) ? 'You' : personName(f.created_by)) + ' · ' + ago(f.created_at) })),
        el('button', { class: 'btn sm', type: 'button', text: 'Dismiss', onclick: close('dismiss') }),
        el('button', { class: 'btn primary sm', type: 'button', 'data-testid': 'flag-resolve', text: 'Mark fixed', onclick: close('resolve') }))));
    });
    box.appendChild(ul);
  } catch (e) { clear(box).appendChild(errorBox(e, () => loadReviews(box))); }
}
