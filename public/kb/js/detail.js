/* Record and resource detail: the side panel (pushes the list, resizable,
   expandable to a full page at #/r/<id>) and the full page itself. */
import { S, el, add, $, clear, icon, typeIcon, typeLabel, typeDot, api, toast, failToast, avatar, personName, ago, host, qs,
  openDialog, closeDialog, confirmDialog, menu, can, setQuery, skeletonBlock, empty, errorBox, combobox, nodeSource, nodeItem,
  peopleSource, plural, you } from './core.js';
import { onLiveChange, showLive, hideLive } from './live.js';
import { track, onPresence, others } from './realtime.js';
import { openRecordForm, linkKindFor, attachDialog, connectDialog, fieldInput, fieldDisplay } from './form.js';
import { activityEntry } from './views/activity.js';

// ------------------------------------------------------------------ panel host
let panelWidth = 440;
try { panelWidth = Math.max(360, Math.min(720, Number(localStorage.getItem('kb_panel_w')) || 440)); } catch (e) { /* ignore */ }

function panelShell() {
  const p = $('#panel'); p.hidden = false; $('#app').classList.add('has-panel');
  p.style.width = panelWidth + 'px';
  clear(p);
  const grip = el('div', { class: 'panel-resize', role: 'separator', 'aria-orientation': 'vertical', 'aria-label': 'Resize details panel', tabindex: '0' });
  grip.addEventListener('mousedown', (e) => {
    e.preventDefault(); grip.classList.add('dragging');
    const startX = e.clientX, startW = p.offsetWidth;
    const mv = (ev) => { panelWidth = Math.max(360, Math.min(Math.min(860, window.innerWidth - 420), startW + (startX - ev.clientX))); p.style.width = panelWidth + 'px'; };
    const up = () => { grip.classList.remove('dragging'); document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); try { localStorage.setItem('kb_panel_w', panelWidth); } catch (er) { /* ignore */ } };
    document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
  });
  grip.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); panelWidth = Math.max(360, Math.min(860, panelWidth + (e.key === 'ArrowLeft' ? 24 : -24))); p.style.width = panelWidth + 'px'; }
  });
  const scroll = el('div', { class: 'panel-scroll', 'data-testid': 'panel' });
  p.append(grip, scroll);
  return scroll;
}
export function closePanel(fromRoute) {
  S.panel = null; hideLive();
  const p = $('#panel'); p.hidden = true; clear(p); $('#app').classList.remove('has-panel');
  document.querySelectorAll('tr.selected').forEach((t) => t.classList.remove('selected'));
  if (!fromRoute) setQuery({ open: null, res: null });
}
export async function openRecordPanel(id, kind) {
  kind = kind || 'node';
  if (S.panel && S.panel.id === id && S.panel.kind === kind && !S.panel.stale) return;
  document.querySelectorAll('tr[data-id]').forEach((t) => t.classList.toggle('selected', t.dataset.id === id));
  const host = panelShell();
  S.panel = { kind, id, node: null, host, full: false };
  host.appendChild(skeletonBlock(10));
  await loadInto(S.panel);
}
async function loadInto(st, keepTab) {
  try {
    if (st.kind === 'node') {
      const n = await api('GET', '/nodes/' + st.id);
      if (S.panel !== st) return;
      st.node = n; renderNode(st, keepTab);
      track({ record: n.id, editing: false });
    } else {
      const r = await api('GET', '/resources/' + st.id);
      if (S.panel !== st) return;
      st.res = r; renderResource(st);
    }
  } catch (e) {
    if (S.panel !== st) return;
    clear(st.host).appendChild(e.status === 404 ? empty('Not found', 'It may have been deleted permanently.', null, 'search') : errorBox(e, () => loadInto(st)));
  }
}
export function renderFullRecord(v, r) {
  const st = { kind: 'node', id: r.path[1], node: null, host: v, full: true };
  S.panel = st;
  v.appendChild(skeletonBlock(12));
  loadInto(st).then(() => { if (st.node) document.title = st.node.name + ' · Knowledge Base'; });
}
/* Reloading the same record keeps the tab the person is on. */
export function reloadPanel() { if (S.panel) { S.panel.stale = false; loadInto(S.panel, true); } }

// ------------------------------------------------------------------ record
function crumbs(n) {
  const c = el('nav', { class: 'crumbs grow', 'aria-label': 'Breadcrumb', 'data-testid': 'breadcrumb' });
  (n.breadcrumb || []).forEach((b) => { c.append(el('a', { href: '#/records?open=' + b.id, text: b.name }), icon('chevron-right', 'sm')); });
  c.append(el('span', { class: 'row gap-1' }, typeIcon(n.type, 'sm'), typeLabel(n.type)));
  return c;
}

function renderNode(st, keepTab) {
  const n = st.node, editable = can('contributor') && !n.archived_at;
  // As a page, everything sits in one centred column (reading layout).
  const host = st.full ? clear(st.host).appendChild(el('div', { class: 'record-page', 'data-testid': 'record-page' })) : clear(st.host);
  const tab = keepTab && st.tab ? st.tab : 'overview';
  st.tab = tab;
  // header
  const acts = el('div', { class: 'row gap-xs flex-none' });
  if (!st.full) acts.appendChild(el('a', { class: 'btn ghost sm icon', href: '#/r/' + n.id, title: 'Open as a page', 'aria-label': 'Open as a page', 'data-testid': 'open-full' }, icon('maximize-2', 'sm')));
  else acts.appendChild(el('a', { class: 'btn ghost sm', href: '#/records?open=' + n.id, 'data-testid': 'back-to-list' }, icon('arrow-left', 'sm'), 'Back to list'));
  if (can('admin')) acts.appendChild(el('a', { class: 'btn ghost sm icon', href: '#/graph/' + n.id, title: 'Show in graph', 'aria-label': 'Show in graph', 'data-testid': 'open-graph' }, icon('network', 'sm')));
  if (editable) acts.appendChild(el('button', { class: 'btn sm', type: 'button', 'data-testid': 'edit-record', onclick: () => openRecordForm({ edit: n }) }, icon('pencil', 'sm'), 'Edit'));
  acts.appendChild(el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'More actions', 'data-testid': 'more-actions', onclick: (e) => moreMenu(e.currentTarget, st) }, icon('ellipsis')));
  if (!st.full) acts.appendChild(el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Close details', 'data-testid': 'close-panel', onclick: () => closePanel() }, icon('x')));
  const head = el('div', { class: 'section record-head' }, el('div', { class: 'row' }, crumbs(n), acts));
  const title = el('h1', { class: editable ? 'inline-edit' : '', 'data-testid': 'panel-name', text: n.name, contenteditable: editable ? 'true' : null,
    spellcheck: 'false', 'aria-label': 'Name', role: editable ? 'textbox' : null });
  if (editable) {
    title.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); title.blur(); } if (e.key === 'Escape') { title.textContent = n.name; title.blur(); } });
    title.addEventListener('blur', () => { const v = title.textContent.replace(/\s+/g, ' ').trim(); if (v && v !== n.name) saveNode(st, { name: v }); else title.textContent = n.name; });
  }
  head.appendChild(title);
  const meta = el('div', { class: 'row small faint record-meta' },
    n.status !== 'active' ? el('span', { class: 'badge ' + (n.archived_at ? 'danger' : 'warn'), text: n.archived_at ? 'Archived' : 'Draft' }) : null,
    n.review_status === 'needs_review' ? el('span', { class: 'badge warn', text: 'Needs review' }) : n.review_status === 'approved' ? el('span', { class: 'badge ok', text: 'Reviewed' }) : null,
    n.is_legacy ? el('span', { class: 'badge', 'data-testid': 'legacy-badge', title: 'From the older sheets (NP Autopilot: legacy)', text: 'Legacy' }) : null,
    el('span', { 'data-testid': 'panel-version', text: 'v' + n.version }), el('span', { text: '·' }), el('span', { text: 'Updated ' + ago(n.updated_at) }),
    el('span', { id: 'presence', class: 'row gap-1' }));
  head.appendChild(meta);
  host.appendChild(head);
  if (n.archived_at) host.appendChild(el('div', { class: 'note-box warn panel-note' }, 'Archived ' + ago(n.archived_at) + '. It is hidden from lists and the graph. ',
    can('editor') ? 'Restore it, or delete it permanently from Archived.' : 'An editor can restore it.'));
  if (n.sync && n.sync.conflict_at) host.appendChild(el('div', { class: 'note-box warn panel-note', 'data-testid': 'sync-conflict' },
    'Changed at the source since it was edited here: the sync kept your edit and did not overwrite it. Compare with the original site and update by hand if needed.'));
  if (n.sync && n.sync.removed_at) host.appendChild(el('div', { class: 'note-box warn panel-note', 'data-testid': 'sync-removed' },
    'Removed at source ' + ago(n.sync.removed_at) + ': the row no longer exists in the original site. Kept here; archive it if it is no longer needed.'));
  (n.flags || []).forEach((f) => host.appendChild(el('div', { class: 'note-box warn row panel-note', 'data-testid': 'flag-banner' }, icon('flag', 'sm'),
    el('span', { class: 'spacer', text: 'Flagged as incorrect: ' + f.reason }), el('a', { class: 'btn sm', href: '#/approvals?tab=reviews', text: 'Review' }))));
  // properties
  host.appendChild(propsGrid(st, editable));
  // tabs
  const tabs = el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Record sections' });
  const body = el('div', { 'data-testid': 'panel-tab-body' });
  const defs = [['overview', 'Overview'], ['links', 'Links', n.resources.length], ['relationships', 'Relationships', n.outgoing.length + n.incoming.length], ['history', 'History']];
  defs.forEach(([k, label, count]) => tabs.appendChild(el('button', { type: 'button', role: 'tab', 'aria-selected': k === tab ? 'true' : 'false', 'data-testid': 'tab-' + k,
    onclick: () => { st.tab = k; tabs.querySelectorAll('[role=tab]').forEach((b) => b.setAttribute('aria-selected', b.dataset.testid === 'tab-' + k ? 'true' : 'false')); drawTab(st, body, editable); } },
    label, count !== undefined ? el('span', { class: 'count', text: count }) : null)));
  host.append(tabs, body);
  drawTab(st, body, editable);
  presenceBadge(n.id);
}

function propsGrid(st, editable) {
  const n = st.node, dl = el('dl', { class: 'props', 'data-testid': 'props' });
  const t = S.typeByKey[n.type] || { fields: [] };
  const row = (k, v, tid) => add(dl, [el('dt', { text: k }), el('dd', { 'data-testid': tid }, v)]);
  row('Type', [typeIcon(n.type), typeLabel(n.type)]);
  if (editable) {
    const s = el('select', { 'aria-label': 'Status', 'data-testid': 'panel-status' }, el('option', { value: 'active', text: 'Live', selected: n.status === 'active' }), el('option', { value: 'draft', text: 'Draft', selected: n.status === 'draft' }));
    s.addEventListener('change', () => saveNode(st, { status: s.value }));
    const rv = el('select', { 'aria-label': 'Review status', 'data-testid': 'panel-review' }, [['none', 'Not reviewed'], ['needs_review', 'Needs review'], ['approved', 'Reviewed']].map(([v, l]) => el('option', { value: v, text: l, selected: n.review_status === v })));
    rv.addEventListener('change', () => saveNode(st, { review_status: rv.value }));
    row('Status', s, 'prop-status'); row('Review', rv, 'prop-review');
  } else { row('Status', n.status === 'active' ? 'Live' : n.status); }
  // owner
  const ownerDd = [avatar(n.owner_id), el('span', { text: n.owner_id ? (you(n.owner_id) ? 'You' : personName(n.owner_id)) : 'No owner', class: n.owner_id ? '' : 'faint' })];
  if (editable) ownerDd.push(el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'change-owner', text: 'Change', onclick: (e) => menu(e.currentTarget,
    [{ label: 'No owner', fn: () => saveNode(st, { owner_id: null }) }].concat(S.people.filter((p) => p.role !== 'viewer').map((p) => ({ node: el('span', { class: 'row' }, avatar(p.user_id), personName(p.user_id) + (you(p.user_id) ? ' (you)' : '')), testid: 'owner-option', fn: () => saveNode(st, { owner_id: p.user_id }) }))), { testid: 'owner-menu' }) }));
  row('Owner', ownerDd, 'panel-owner');
  if ((n.co_owners || []).length) row('Co-owners', n.co_owners.map((u) => avatar(u)));
  // Owners by role (P Primary; B1-B3 Backups): person records. They become the
  // account owner when that person's record is linked to a sign-in.
  const personLink = (r, badge) => el('span', { class: 'token' }, badge ? el('span', { class: 'role-badge', text: badge }) : null, typeIcon(r.type, 'sm'),
    el('a', { href: '#/records?open=' + r.id, text: r.name, class: 'truncate' }));
  const pick = (title, cb) => {
    const c = combobox({ label: title, placeholder: 'Search instructors and team members…', testid: 'owner-record-picker', openOnFocus: true,
      source: nodeSource(['instructor', 'team_member']), onChange: (x) => { if (x) { closeDialog(); cb(x.id); } } });
    openDialog([el('h2', { text: title }), c, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }))], { label: title });
  };
  if (n.owner_record || editable) {
    row('Owner by role', [n.owner_record ? personLink(n.owner_record, 'P') : el('span', { class: 'faint', text: 'None' }),
      editable ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'change-owner-record', text: 'Change',
        onclick: (e) => menu(e.currentTarget, [{ label: 'Choose a person…', fn: () => pick('Primary owner', (id) => saveNode(st, { owner_record_id: id })) },
          n.owner_record ? { label: 'Remove', danger: true, fn: () => saveNode(st, { owner_record_id: null }) } : null]) }) : null], 'panel-owner-record');
  }
  if ((n.co_owner_records || []).length || (editable && n.owner_record)) {
    const ids = (n.co_owner_records || []).map((r) => r.id);
    row('Backups', [(n.co_owner_records || []).map((r, i) => el('span', { class: 'row gap-xs' }, personLink(r, 'B' + (i + 1)),
      editable ? el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove backup ' + r.name, onclick: () => saveNode(st, { co_owner_record_ids: ids.filter((x) => x !== r.id) }) }, icon('x', 'sm')) : null)),
      editable ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'add-backup', text: 'Add', onclick: () => pick('Add a backup', (id) => saveNode(st, { co_owner_record_ids: ids.concat([id]) })) }) : null], 'panel-co-owner-records');
  }
  // A person record's sign-in: linked by e-mail now, or the first time they sign in.
  // B1 (run 6): "Claim this profile" — any member; an admin approves it in Approvals
  if (['instructor', 'team_member'].includes(n.type) && !n.account && !can('admin') && !S.myPerson) {
    row('Is this you?', [el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'claim-profile', text: 'Claim this profile', onclick: async () => {
      try { await api('POST', '/claims', { node_id: n.id }); } catch (e) { if (e.status === 202) { toast('Claim sent: an admin confirms it in Approvals'); return; } failToast(e, 'Not sent'); } } })], 'panel-claim');
  }
  if (['instructor', 'team_member'].includes(n.type) && (n.account || can('admin'))) {
    const acc = n.account;
    row('Sign-in account', [acc ? el('span', { text: acc.email }) : el('span', { class: 'faint', text: 'Not linked' }),
      acc ? el('span', { class: 'badge ' + (acc.user_id ? 'ok' : 'warn'), 'data-testid': 'account-state', text: acc.user_id ? 'Linked' : 'Waiting for first sign-in' }) : null,
      can('admin') ? el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'link-account', text: acc ? 'Change' : 'Link', onclick: () => {
        const inp = el('input', { type: 'email', value: acc ? acc.email : '', 'aria-label': 'E-mail', 'data-testid': 'account-email', placeholder: 'name@interviewkickstart.com' });
        const err = el('div', { class: 'field-error', role: 'alert' });
        openDialog([el('h2', { text: 'Link to a sign-in account' }),
          el('p', { class: 'small muted', text: 'When this person signs in with this e-mail (or already has), they become the owner of everything this record owns by role.' }), inp, err,
          el('div', { class: 'actions' }, acc ? el('button', { class: 'btn danger', type: 'button', text: 'Unlink', onclick: async () => { try { await api('DELETE', '/nodes/' + n.id + '/account'); closeDialog(); reloadPanel(true); } catch (e) { err.textContent = e.message; } } }) : null,
            el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
            el('button', { class: 'btn primary', type: 'button', 'data-testid': 'account-save', text: 'Link', onclick: async () => {
              try { const r = await api('POST', '/nodes/' + n.id + '/account', { email: inp.value.trim() }); closeDialog(); toast(r.user_id ? 'Linked: they now own this record’s work' : 'Saved: links on their first sign-in'); reloadPanel(true); }
              catch (e) { err.textContent = e.message; } } }))], { label: 'Link account' });
      } }) : null], 'panel-account');
  }
  // placement
  const placed = el('div', { class: 'row wrap gap-1' });
  (n.parents || []).forEach((p) => placed.appendChild(el('span', { class: 'token' }, typeIcon(p.node_type, 'sm'), el('a', { href: '#/records?open=' + p.node_id, text: p.node_name, class: 'truncate' }),
    editable ? el('button', { type: 'button', 'aria-label': 'Remove from ' + p.node_name, onclick: () => removeEdge(st, p, 'Removed from ' + p.node_name) }, icon('x', 'sm')) : null)));
  if (!(n.parents || []).length) placed.appendChild(el('span', { class: 'faint', text: t.allowed_parents && t.allowed_parents.length ? 'Not placed yet' : '—' }));
  if (editable && t.allowed_parents && t.allowed_parents.length) placed.appendChild(el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'add-placement', text: 'Add',
    onclick: () => placementDialog(st) }));
  row('Belongs to', placed, 'panel-scope');
  // tags
  const tags = el('div', { class: 'row wrap gap-1', 'data-testid': 'panel-tags' });
  n.tags.forEach((g) => tags.appendChild(el('span', { class: 'token' }, '#' + g.name, editable ? el('button', { type: 'button', 'aria-label': 'Remove tag ' + g.name, onclick: () => untag(st, g) }, icon('x', 'sm')) : null)));
  if (editable) {
    const tin = el('input', { placeholder: 'Add tag', 'aria-label': 'Add tag', class: 'tag-input', 'data-testid': 'tag-input' });
    tin.addEventListener('keydown', (e) => { if (e.key === 'Enter' && tin.value.trim()) { e.preventDefault(); addTag(st, tin.value.trim()); } });
    tags.appendChild(tin);
  } else if (!n.tags.length) tags.appendChild(el('span', { class: 'faint', text: 'None' }));
  row('Tags', tags);
  // custom fields
  (t.fields || []).filter((f) => !f.archived).forEach((f) => {
    const val = (n.props || {})[f.key];
    if (!editable) { row(f.label, fieldDisplay(f, val), 'field-' + f.key); return; }
    const inp = fieldInput(f, val, (nv) => { const props = Object.assign({}, n.props || {}); if (nv === null || nv === '' || (Array.isArray(nv) && !nv.length)) delete props[f.key]; else props[f.key] = nv; saveNode(st, { props }); }, { compact: true });
    row(f.label + (f.required ? ' *' : ''), inp, 'field-' + f.key);
  });
  // completeness
  if (n.completeness) {
    const c = n.completeness, score = c.tree_score !== undefined ? c.tree_score : c.score;
    row('Completeness', [el('div', { class: 'bar w-80 ' + (score >= 80 ? 'ok' : score >= 50 ? 'warn' : 'danger') }, el('span', { style: 'width:' + score + '%' })),
      el('span', { class: 'tabular small', text: score + '%' }), c.missing.length ? el('span', { class: 'faint small truncate', text: 'Missing: ' + c.missing.join(', ') }) : null], 'panel-completeness');
  }
  return el('div', { class: 'section' }, dl);
}

function drawTab(st, body, editable) {
  clear(body);
  const n = st.node;
  if (st.tab === 'overview') {
    const sec = el('div', { class: 'section' });
    sec.append(el('h3', { text: 'Summary' }), textBlock(st, 'summary', n.summary, editable, 'Add a one-line summary…', 2000));
    sec.append(el('h3', { text: 'Notes' }), textBlock(st, 'body', n.body, editable, 'Add notes…', 100000));
    body.appendChild(sec);
    const c = n.completeness;
    if (c && c.weakest && c.weakest.length) {
      const ul = el('ul', { class: 'list' });
      c.weakest.slice(0, 6).forEach((w) => ul.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?open=' + w.id }, typeIcon(w.type), el('span', { class: 'truncate grow', text: w.name }), el('span', { class: 'faint xs truncate missing-col', text: 'Missing: ' + w.missing.join(', ') }), el('span', { class: 'tabular small', text: w.score + '%' })))));
      body.appendChild(el('div', { class: 'section' }, el('div', { class: 'section-head' }, el('h3', { text: 'Needs work inside this ' + typeLabel(n.type).toLowerCase() })), ul));
    }
  } else if (st.tab === 'links') {
    body.appendChild(linksTab(st, editable));
  } else if (st.tab === 'relationships') {
    body.appendChild(relationshipsTab(st, editable));
  } else {
    const h = el('div', { class: 'section', 'data-testid': 'panel-history' }, skeletonBlock(4));
    body.appendChild(h);
    loadHistory(h, '/nodes/' + n.id + '/history', n.id);
  }
}

function textBlock(st, field, value, editable, placeholder, max) {
  const div = el('div', { 'data-testid': 'panel-' + field, 'data-placeholder': editable ? placeholder : '—', tabindex: editable ? '0' : null,
    role: editable ? 'button' : null, 'aria-label': editable ? 'Edit ' + (field === 'body' ? 'notes' : field) : null, class: (editable ? 'inline-edit ' : '') + 'text-block' }, value || '');
  if (!editable) { if (!value) div.textContent = '—'; return div; }
  const start = () => {
    const ta = el('textarea', { maxlength: String(max), rows: field === 'body' ? '8' : '3', 'aria-label': field, 'data-testid': 'edit-' + field }, value || '');
    div.replaceWith(ta); ta.focus();
    track({ record: st.node.id, editing: true });
    const finish = (save) => { const v = ta.value.trim(); track({ record: st.node.id, editing: false }); if (save && v !== (value || '')) saveNode(st, { [field]: v || null }); else renderNode(st, true); };
    ta.addEventListener('blur', () => finish(true));
    ta.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); ta.value = value || ''; finish(false); } if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ta.blur(); });
  };
  div.addEventListener('click', start);
  div.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); start(); } });
  return div;
}

// ------------------------------------------------------------------ links tab
export function linkRow(r, opts) {
  opts = opts || {};
  const lk = linkKindFor(r);
  const health = r.link_health || (r.link_status ? { status: r.link_status } : null);
  const hb = health && health.status !== 'ok' ? el('span', { class: 'badge ' + (health.status === 'needs_auth' ? 'warn' : 'danger'), 'data-testid': 'link-health',
    text: health.status === 'needs_auth' ? 'Needs sign-in' : 'Broken' + (health.http_status ? ' ' + health.http_status : '') }) : null;
  return el('div', { class: 'link-row', 'data-testid': 'link-row' },
    el('span', { class: 'type-icon', title: lk.label }, icon(lk.icon || 'link')),
    el('div', { class: 'col gap-0 grow' },
      el('div', { class: 'row gap-2' }, el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', class: 'truncate strong fg', text: r.title }),
        el('span', { class: 'badge', text: kindLabel(r.kind) }), hb),
      el('div', { class: 'row faint xs gap-2' }, el('span', { text: lk.label }), el('span', { text: '·' }), el('span', { class: 'truncate', text: host(r.url) }),
        r.note ? el('span', { text: '·' }) : null, r.note ? el('span', { class: 'truncate', text: r.note }) : null)),
    r.owner_id ? avatar(r.owner_id) : null,
    el('span', { class: 'actions' }, opts.actions || null));
}
export function kindLabel(k) {
  const m = { kyp_slides: 'KYP slides', speaker_notes: 'Speaker notes', live_class_link: 'Live class link', assignment_brief: 'Assignment brief',
    problem_statement: 'Problem statement', evaluation_criteria: 'Evaluation criteria', question_bank: 'Question bank', interview_guide: 'Interview guide',
    reference_doc: 'Reference doc', repo: 'Repository' };
  return m[k] || (k ? k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, ' ') : 'Link');
}
function linksTab(st, editable) {
  const n = st.node, wrap = el('div', { class: 'section' });
  wrap.appendChild(el('div', { class: 'section-head' }, el('h3', { text: plural(n.resources.length, 'link') }), el('span', { class: 'spacer' }),
    editable ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'attach', onclick: () => attachDialog(n, () => reloadPanel(true)) }, icon('plus', 'sm'), 'Add link') : null));
  const ul = el('ul', { class: 'list bordered', 'data-testid': 'panel-resources' });
  if (!n.resources.length) return add(wrap, empty('No links yet', 'Attach slides, recordings, briefs or repos so people can find them from here.', editable ? el('button', { class: 'btn sm', type: 'button', onclick: () => attachDialog(n, () => reloadPanel(true)) }, 'Add a link') : null, 'link', 'adding-links'));
  n.resources.forEach((r) => ul.appendChild(el('li', null, linkRow(r, { actions: [
    el('a', { class: 'btn ghost sm icon', href: '#/resources?res=' + r.id, title: 'Resource details', 'aria-label': 'Details for ' + r.title }, icon('panel-right', 'sm')),
    editable ? el('button', { class: 'btn ghost sm icon', type: 'button', title: 'Edit purpose', 'aria-label': 'Edit purpose of ' + r.title, onclick: () => purposeDialog(st, r) }, icon('pencil', 'sm')) : null,
    editable ? el('button', { class: 'btn ghost sm icon', type: 'button', title: 'Remove link', 'aria-label': 'Remove ' + r.title, 'data-testid': 'detach', onclick: () => detach(st, r) }, icon('x', 'sm')) : null] }))));
  wrap.appendChild(ul);
  return wrap;
}
function purposeDialog(st, r) {
  const ta = el('textarea', { rows: '3', 'aria-label': 'Purpose', 'data-testid': 'purpose-input' }, r.note || '');
  openDialog([el('h2', { text: 'Why is “' + r.title + '” attached here?' }), el('p', { class: 'muted small', text: 'The purpose is specific to this record; the link’s description says what is inside it.' }), ta,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', text: 'Save', onclick: async () => { try { await api('PATCH', '/attachments/' + r.attachment_id, { note: ta.value.trim() || null }); closeDialog(); toast('Saved'); reloadPanel(true); } catch (e) { failToast(e, 'Not saved'); } } }))], { label: 'Edit purpose' });
}
async function detach(st, r) {
  try {
    await api('POST', '/attachments/' + r.attachment_id + '/detach');
    toast('Removed “' + r.title + '”', { action: { label: 'Undo', fn: async () => { try { await api('POST', '/nodes/' + st.node.id + '/resources', { resource_id: r.id, note: r.note }); reloadPanel(true); } catch (e) { failToast(e, 'Undo failed'); } } } });
    reloadPanel(true);
  } catch (e) { if (e.status === 202) toast('Sent for approval — an editor will review the removal.'); else failToast(e, 'Not removed'); }
}

// ------------------------------------------------------------------ relationships tab
function relationshipsTab(st, editable) {
  const n = st.node, wrap = el('div', { class: 'section' });
  wrap.appendChild(el('div', { class: 'section-head' }, el('h3', { text: plural(n.outgoing.length + n.incoming.length, 'relationship') }), el('span', { class: 'spacer' }),
    editable ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'connect', onclick: () => connectDialog(n, () => reloadPanel(true)) }, icon('plus', 'sm'), 'Connect') : null));
  const rows = n.outgoing.map((e) => ({ e, label: e.label })).concat(n.incoming.map((e) => ({ e, label: e.label })));
  if (!rows.length) return add(wrap, empty('Not connected yet', 'Connect this record to the courses, topics and people it relates to.', editable ? el('button', { class: 'btn sm', type: 'button', onclick: () => connectDialog(n, () => reloadPanel(true)) }, 'Connect') : null, 'git-branch', 'connecting-records'));
  const groups = {};
  rows.forEach((r) => { (groups[r.label] = groups[r.label] || []).push(r); });
  const box = el('div', { 'data-testid': 'panel-relationships' });
  Object.keys(groups).sort().forEach((label) => {
    box.appendChild(el('div', { class: 'faint xs rel-group-label', text: label }));
    groups[label].forEach((r) => box.appendChild(el('div', { class: 'link-row', 'data-testid': 'rel' }, typeIcon(r.e.node_type),
      el('a', { href: '#/records?open=' + r.e.node_id, class: 'truncate fg', text: r.e.node_name }),
      r.e.props && r.e.props.role ? el('span', { class: 'role-badge', 'data-testid': 'rel-role', title: ROLE_LABEL[r.e.props.role] || r.e.props.role, text: ROLE_SHORT[r.e.props.role] || r.e.props.role }) : null,
      r.e.node_legacy ? el('span', { class: 'badge', text: 'Legacy' }) : null,
      r.e.note ? el('span', { class: 'faint xs truncate', text: r.e.note }) : null, el('span', { class: 'spacer' }),
      editable ? el('span', { class: 'actions' }, el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove relationship', title: can('editor') ? 'Remove' : 'Propose removal',
        onclick: () => removeEdge(st, r.e, 'Removed “' + label + ' ' + r.e.node_name + '”') }, icon('x', 'sm'))) : null)));
  });
  wrap.appendChild(box);
  return wrap;
}
async function removeEdge(st, e, msg) {
  try {
    await api('POST', '/edges/' + e.id + '/archive');
    toast(msg, { action: { label: 'Undo', fn: async () => { try { await api('POST', '/edges/' + e.id + '/restore'); reloadPanel(true); } catch (er) { failToast(er, 'Undo failed'); } } } });
    reloadPanel(true);
  } catch (er) { if (er.status === 202) toast('Sent for approval — an editor will review the removal.'); else failToast(er, 'Not removed'); }
}
function placementDialog(st) {
  const t = S.typeByKey[st.node.type];
  let chosen = null;
  const picker = combobox({ testid: 'placement-picker', placeholder: 'Search ' + t.allowed_parents.map((k) => typeLabel(k, true).toLowerCase()).join(', ') + '…',
    source: nodeSource(t.allowed_parents, [st.node.id]), onChange: (v) => { chosen = v; } });
  openDialog([el('h2', { text: 'Add “' + st.node.name + '” to…' }), picker,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'placement-save', text: 'Add', onclick: async () => {
        if (!chosen) return;
        try { await api('POST', '/edges', { type: 'contains', source_id: chosen.id, target_id: st.node.id }); closeDialog(); toast('Added to ' + chosen.label); reloadPanel(true); }
        catch (e) { failToast(e, 'Not added'); } } }))], { label: 'Add placement' });
}

// Roles from the current mastersheet (NP Autopilot): P Primary, B1-B3 Backups.
export const ROLE_SHORT = { primary: 'P', backup_1: 'B1', backup_2: 'B2', backup_3: 'B3' };
export const ROLE_LABEL = { primary: 'Primary', backup_1: 'Backup 1', backup_2: 'Backup 2', backup_3: 'Backup 3' };

// ------------------------------------------------------------------ history
/* A record's History tab: the same entry component as the Activity page, so
   it reads the same way (who, what, when, field-by-field diff). Read through
   kb.record_history(), which any member who can see the record may use. */
export async function loadHistory(box, path, recordId) {
  try {
    const h = (await api('GET', path)).items;
    clear(box);
    if (!h.length) { box.appendChild(el('p', { class: 'faint small', text: 'No history.' })); return; }
    box.appendChild(el('ul', { class: 'entries', 'data-testid': 'history-list' }, h.map((a) => activityEntry(a, { inRecord: true, all: true }))));
    if (can('editor') && recordId) box.appendChild(el('a', { class: 'btn ghost sm mt-2', href: '#/activity?record=' + recordId, 'data-testid': 'history-in-activity' }, icon('history', 'sm'), 'Open in Activity'));
  } catch (e) { clear(box).appendChild(errorBox(e)); }
}

// ------------------------------------------------------------------ actions
function moreMenu(anchor, st) {
  const n = st.node, items = [];
  items.push({ label: 'Copy link', icon: 'link-2', fn: () => { navigator.clipboard && navigator.clipboard.writeText(location.origin + '/kb/#/r/' + n.id); toast('Link copied'); } });
  items.push({ label: 'Flag as incorrect', icon: 'flag', testid: 'flag', fn: () => flagDialog('nodes', n.id, n.name) });
  if (!n.archived_at && can('editor')) items.push({ label: 'Duplicate', icon: 'copy', testid: 'duplicate', fn: () => duplicateNode(st) });
  if (!n.archived_at && can('editor') && (S.typeByKey[n.type] || {}).is_container) items.push({ label: 'Save as template', icon: 'layers', testid: 'save-template', fn: () => saveTemplate(n) });
  items.push('-');
  if (!n.archived_at && can('contributor')) items.push({ label: can('editor') ? 'Archive' : 'Propose archive', icon: 'archive', danger: true, testid: 'archive', fn: () => archiveNode(st) });
  if (n.archived_at && can('editor')) items.push({ label: 'Restore', icon: 'rotate-ccw', testid: 'restore', fn: () => restoreNode(st) });
  if (n.archived_at && can('admin')) items.push({ label: 'Delete permanently', icon: 'trash-2', danger: true, testid: 'hard-delete', fn: () => hardDelete('nodes', n.id, n.name, () => closePanel()) });
  menu(anchor, items, { alignRight: true, testid: 'more-menu' });
}
export async function archiveNode(st) {
  const n = st.node;
  let imp = { edges: 0, resources: 0, scoped_records: 0 };
  try { imp = await api('GET', '/nodes/' + n.id + '/impact'); } catch (e) { /* show without counts */ }
  const isEditor = can('editor');
  const reason = await confirmDialog({ title: (isEditor ? 'Archive' : 'Propose archiving') + ' “' + n.name + '”?', danger: isEditor, confirmLabel: isEditor ? 'Archive' : 'Send for approval', withReason: !isEditor,
    reasonPlaceholder: 'Why should it be archived? (helps the editor decide)',
    body: el('div', { class: 'col', 'data-testid': 'archive-impact' }, el('p', { class: 'small', text: 'Archiving hides it from lists, the outline and the graph. Nothing is deleted.' }),
      el('ul', { class: 'small impact-list' }, el('li', { text: plural(imp.edges, 'relationship') + ' will be archived with it' }), el('li', { text: plural(imp.resources, 'link') + ' will be archived with it' }),
        imp.scoped_records ? el('li', { text: plural(imp.scoped_records, 'record') + ' belong to it and stay, without it' }) : null),
      el('p', { class: 'faint small', text: 'You can restore it any time' + (isEditor ? ', or delete it permanently later from Archived.' : '.') })) });
  if (!reason) return;
  try {
    await api('POST', '/nodes/' + n.id + '/archive', typeof reason === 'string' ? { reason } : {});
    toast('Archived “' + n.name + '”. You can delete permanently later from Archived.', { action: { label: 'Undo', fn: () => restoreNode(st) } });
    reloadPanel(); if (S.listReload) S.listReload();
  } catch (e) { if (e.status === 202) toast('Sent for approval — an editor will review it.'); else failToast(e, 'Not archived'); }
}
async function restoreNode(st) {
  try { await api('POST', '/nodes/' + st.node.id + '/restore'); toast('Restored'); reloadPanel(); if (S.listReload) S.listReload(); }
  catch (e) { failToast(e, 'Not restored'); }
}
export async function hardDelete(table, id, name, after) {
  let imp = {};
  try { imp = await api('GET', '/' + table + '/' + id + '/delete-impact'); } catch (e) { /* counts optional */ }
  const parts = Object.entries(imp || {}).filter(([, v]) => v).map(([k, v]) => plural(v, k.replace(/_/g, ' ').replace(/s$/, '')));
  const ok = await confirmDialog({ title: 'Delete “' + name + '” permanently?', danger: true, confirmLabel: 'Delete permanently', typeToConfirm: name,
    body: el('div', { class: 'col' }, el('p', { class: 'small', text: 'This cannot be undone. It is removed from the database' + (parts.length ? ', together with ' + parts.join(', ') + '.' : '.') }),
      el('p', { class: 'faint small', text: 'The deletion is recorded in the audit log.' })) });
  if (!ok) return;
  try { await api('DELETE', '/' + table + '/' + id); toast('Deleted permanently'); if (after) after(); if (S.listReload) S.listReload(); }
  catch (e) { failToast(e, 'Not deleted'); }
}
async function duplicateNode(st) {
  try { const d = await api('POST', '/nodes/' + st.node.id + '/duplicate'); toast('Duplicated as “' + d.name + '” (draft)'); setQuery({ open: d.id }); if (S.listReload) S.listReload(); }
  catch (e) { failToast(e, 'Not duplicated'); }
}
function saveTemplate(n) {
  const name = el('input', { value: n.name + ' template', 'aria-label': 'Template name', 'data-testid': 'template-name' });
  openDialog([el('h2', { text: 'Save as template' }), el('p', { class: 'muted small', text: 'Saves the structure — the records inside “' + n.name + '”, their names, summaries and fields — not links, owners or relationships.' }),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Template name' }), name),
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'template-save', text: 'Save template', onclick: async () => {
        try { await api('POST', '/templates', { source_id: n.id, name: name.value.trim() }); closeDialog(); toast('Template saved. Use it from New record.'); } catch (e) { failToast(e, 'Not saved'); } } }))], { label: 'Save as template' });
}
export function flagDialog(table, id, name) {
  const ta = el('textarea', { rows: '3', placeholder: 'What is wrong? e.g. “the recording link is from the 2024 cohort”', 'aria-label': 'Reason', 'data-testid': 'flag-reason' });
  openDialog([el('h2', { text: 'Flag “' + name + '” as incorrect' }), el('p', { class: 'muted small', text: 'The owner gets a review request in Approvals → Reviews.' }), ta,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'flag-submit', text: 'Flag', onclick: async () => {
        if (!ta.value.trim()) { ta.focus(); return; }
        try { await api('POST', '/flags', { target_table: table, target_id: id, reason: ta.value.trim() }); closeDialog(); toast('Flagged. The owner will review it.'); reloadPanel(true); }
        catch (e) { failToast(e, 'Not flagged'); } } }))], { label: 'Flag as incorrect' });
}
async function addTag(st, name) {
  try { await api('POST', '/nodes/' + st.node.id + '/tags', { name }); reloadPanel(true); } catch (e) { failToast(e, 'Tag not added'); }
}
async function untag(st, g) {
  try { await api('DELETE', '/nodes/' + st.node.id + '/tags/' + g.id); reloadPanel(true); } catch (e) { failToast(e, 'Tag not removed'); }
}

/* OPTIMISTIC save: show the change at once; roll back on failure; a 409
   version conflict opens the conflict dialog instead of overwriting. */
export async function saveNode(st, changes, force) {
  const n = st.node, before = JSON.parse(JSON.stringify(n));
  Object.assign(n, changes); renderNode(st, true);
  try {
    const updated = await api('PATCH', '/nodes/' + n.id + (force ? '?force=1' : ''), Object.assign({ version: before.version }, changes));
    if (S.panel === st) { st.node = updated; renderNode(st, true); }
    hideLive(); toast('Saved');
    if (S.listReload) S.listReload();
  } catch (e) {
    if (S.panel === st) { st.node = before; renderNode(st, true); }
    if (e.status === 409 && e.body.error === 'version_conflict') conflictDialog(st, before, changes, e.body.current);
    else if (e.status === 409 && e.body.existing) toast(e.message, { error: true, action: { label: 'Open existing', fn: () => setQuery({ open: e.body.existing.id }) } });
    else failToast(e, 'Not saved');
  }
}
function conflictDialog(st, mine, changes, current) {
  const diff = el('div', { class: 'conflict-diff', 'data-testid': 'conflict-diff' },
    el('div', { class: 'faint', text: 'Field' }), el('div', { class: 'faint', text: 'Your change' }), el('div', { class: 'faint', text: 'Saved now (v' + current.version + ')' }));
  const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  ['name', 'summary', 'body', 'status', 'review_status', 'owner_id', 'props'].forEach((f) => {
    const yours = f in changes ? changes[f] : mine[f];
    if (!(f in changes) && JSON.stringify(mine[f]) === JSON.stringify(current[f])) return;
    add(diff, [el('div', { class: 'faint', text: f.replace('_id', '').replace('_', ' ') }), el('div', { class: 'diff-add', text: fmt(f === 'owner_id' ? personName(yours) : yours) }), el('div', { text: fmt(f === 'owner_id' ? personName(current[f]) : current[f]) })]);
  });
  const actions = el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', 'data-testid': 'conflict-reload', text: 'Use their version', onclick: () => { closeDialog(); reloadPanel(true); } }));
  if (can('editor')) actions.appendChild(el('button', { class: 'btn danger solid', type: 'button', 'data-testid': 'conflict-overwrite', text: 'Overwrite with mine',
    onclick: () => { closeDialog(); st.node = Object.assign({}, mine, current); saveNode(st, changes, true); } }));
  openDialog([el('h2', { text: 'This record changed since you opened it' }),
    el('p', { class: 'muted small', text: 'Someone saved a newer version (v' + current.version + ') while you were editing v' + mine.version + '. Your change was not saved.' }), diff,
    can('editor') ? null : el('p', { class: 'faint small', text: 'Only editors can overwrite a newer version. Copy your text, use their version, then re-apply it.' }), actions],
  { label: 'Edit conflict', testid: 'conflict-dialog', wide: true });
}

// ------------------------------------------------------------------ live updates for the open record
onLiveChange((changes) => {
  const p = S.panel;
  if (!p || p.kind !== 'node' || !p.node) return;
  const hit = changes.filter((c) => c.row_id === p.id || ['edges', 'node_resources', 'node_tags'].includes(c.table_name));
  if (!hit.length) return;
  const own = hit.filter((c) => c.row_id === p.id);
  const editing = document.querySelector('#panel textarea, #view textarea, [contenteditable]:focus');
  const who = (c) => (c.actor_type === 'ai' ? 'The AI assistant' : personName(c.actor_id) || 'A teammate');
  if (own.length && own.some((c) => Number(c.version) > p.node.version)) {
    if (editing) showLive(who(own[own.length - 1]) + ' just changed this record. Saving now will show you both versions.');
    else { reloadPanel(true); showLive(who(own[own.length - 1]) + ' just updated this record — showing the latest.'); }
  } else if (!editing) reloadPanel(true);
});
function presenceBadge(recordId) {
  const box = $('#presence'); if (!box) return;
  clear(box);
  const o = others(recordId);
  if (!o.length) return;
  box.append(el('span', { text: '·' }), ...o.map((x) => avatar(x.user_id)), el('span', { 'data-testid': 'presence', text: o.map((x) => personName(x.user_id) + (x.editing ? ' is editing' : ' is viewing')).join(', ') }));
}
onPresence(() => { if (S.panel && S.panel.node) presenceBadge(S.panel.node.id); });

// ------------------------------------------------------------------ resource
function renderResource(st) {
  const r = st.res, host = clear(st.host), editable = can('contributor') && !r.archived_at;
  host.setAttribute('data-testid', 'res-panel');
  const lk = linkKindFor(r);
  const acts = el('div', { class: 'row gap-xs' },
    editable ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'res-edit', onclick: () => resourceEdit(st) }, icon('pencil', 'sm'), 'Edit') : null,
    el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'More actions', onclick: (e) => menu(e.currentTarget, [
      { label: 'Flag as incorrect', icon: 'flag', fn: () => flagDialog('resources', r.id, r.title) },
      can('contributor') ? { label: 'Duplicate (new link from this one)', icon: 'copy', testid: 'res-duplicate', fn: () => import('./views/resources.js').then((m) => m.newResourceDialog({ title: r.title + ' (copy)', kind: r.kind, description: r.description })) } : null,
      '-',
      !r.archived_at && can('contributor') ? { label: can('editor') ? 'Archive' : 'Propose archive', icon: 'archive', danger: true, testid: 'res-archive', fn: () => archiveResource(st) } : null,
      r.archived_at && can('editor') ? { label: 'Restore', icon: 'rotate-ccw', testid: 'res-restore', fn: async () => { try { await api('POST', '/resources/' + r.id + '/restore'); reloadPanel(); if (S.listReload) S.listReload(); } catch (e) { failToast(e); } } } : null,
      r.archived_at && can('admin') ? { label: 'Delete permanently', icon: 'trash-2', danger: true, testid: 'res-hard-delete', fn: () => hardDelete('resources', r.id, r.title, () => closePanel()) } : null,
    ], { alignRight: true }) }, icon('ellipsis')),
    el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Close details', onclick: () => closePanel() }, icon('x')));
  host.appendChild(el('div', { class: 'section record-head' },
    el('div', { class: 'row mb-2' }, el('span', { class: 'crumbs' }, icon(lk.icon, 'sm'), lk.label), el('span', { class: 'spacer' }), acts),
    el('h1', { text: r.title, 'data-testid': 'res-title' }),
    el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', class: 'small truncate url-line', text: r.url })));
  if (r.archived_at) host.appendChild(el('div', { class: 'note-box warn panel-note', text: 'Archived ' + ago(r.archived_at) + '. Its attachments were archived with it.' }));
  const dl = el('dl', { class: 'props' });
  const health = r.link_health;
  add(dl, [el('dt', { text: 'Kind' }), el('dd', null, el('span', { class: 'badge', text: kindLabel(r.kind) })),
    el('dt', { text: 'Service' }), el('dd', null, icon(lk.icon), lk.label),
    el('dt', { text: 'Owner' }), el('dd', null, avatar(r.owner_id), r.owner_id ? personName(r.owner_id) : el('span', { class: 'faint', text: 'No owner' })),
    el('dt', { text: 'Link health' }), el('dd', null, health ? el('span', { class: 'badge ' + (health.status === 'ok' ? 'ok' : health.status === 'needs_auth' ? 'warn' : 'danger'), text: (health.status === 'ok' ? 'Working' : health.status === 'needs_auth' ? 'Needs sign-in' : 'Broken') + (health.http_status ? ' · HTTP ' + health.http_status : '') }) : el('span', { class: 'faint', text: 'Not checked yet' }), health ? el('span', { class: 'faint xs', text: 'checked ' + ago(health.checked_at) }) : null),
    el('dt', { text: 'Tags' }), el('dd', null, (r.tags || []).length ? r.tags.map((t) => el('span', { class: 'token', text: '#' + t })) : el('span', { class: 'faint', text: 'None' })),
    el('dt', { text: 'Description' }), el('dd', { text: r.description || '—', class: 'pre-wrap' })]);
  const compDd = el('dd', { 'data-testid': 'res-completeness' }, el('span', { class: 'faint', text: '…' }));
  add(dl, [el('dt', { text: 'Completeness' }), compDd]);
  api('GET', '/resources/' + r.id + '/completeness').then((c) => {
    clear(compDd).append(el('div', { class: 'bar w-80 ' + (c.score >= 80 ? 'ok' : c.score >= 50 ? 'warn' : 'danger') }, el('span', { style: 'width:' + c.score + '%' })),
      el('span', { class: 'tabular small', text: c.score + '%' }), c.missing.length ? el('span', { class: 'faint small truncate', text: 'Missing: ' + c.missing.join(', ') }) : null);
  }).catch(() => clear(compDd));
  host.appendChild(el('div', { class: 'section' }, dl));
  const used = el('ul', { class: 'list bordered', 'data-testid': 'res-used-by' });
  r.nodes.forEach((x) => used.appendChild(el('li', null, el('a', { class: 'link-row', href: '#/records?open=' + x.id }, typeIcon(x.type), el('span', { class: 'truncate fg', text: x.name }), x.note ? el('span', { class: 'faint xs truncate', text: '— ' + x.note }) : null))));
  host.appendChild(el('div', { class: 'section' }, el('div', { class: 'section-head' }, el('h3', { text: 'Used by ' + plural(r.nodes.length, 'record') })),
    r.nodes.length ? used : el('p', { class: 'faint small', text: 'Not attached to any record.' })));
  const hist = el('div', { class: 'section' }, el('h3', { text: 'History', class: 'mb-1' }));
  host.appendChild(hist); const hb = el('div'); hist.appendChild(hb); loadHistory(hb, '/resources/' + r.id + '/history');
}
async function archiveResource(st) {
  const r = st.res;
  const ok = await confirmDialog({ title: 'Archive “' + r.title + '”?', danger: true, confirmLabel: can('editor') ? 'Archive' : 'Send for approval',
    body: 'It is removed from the ' + plural(r.used_by, 'record') + ' it is attached to. You can restore it, or delete it permanently later from Archived.' });
  if (!ok) return;
  try { await api('POST', '/resources/' + r.id + '/archive'); toast('Archived', { action: { label: 'Undo', fn: async () => { await api('POST', '/resources/' + r.id + '/restore'); reloadPanel(); } } }); reloadPanel(); if (S.listReload) S.listReload(); }
  catch (e) { if (e.status === 202) toast('Sent for approval.'); else failToast(e, 'Not archived'); }
}
function resourceEdit(st) {
  const r = st.res;
  const url = el('input', { value: r.url, 'data-testid': 'res-edit-url', 'aria-label': 'URL' });
  const title = el('input', { value: r.title, 'data-testid': 'res-edit-title', 'aria-label': 'Title' });
  const kind = el('select', { 'aria-label': 'Kind' }, S.resourceKinds.map((k) => el('option', { value: k, text: kindLabel(k), selected: r.kind === k })));
  const desc = el('textarea', { rows: '3', 'aria-label': 'Description' }, r.description || '');
  const owner = el('select', { 'aria-label': 'Owner' }, el('option', { value: '', text: 'No owner' }), S.people.map((p) => el('option', { value: p.user_id, text: personName(p.user_id), selected: p.user_id === r.owner_id })));
  const tags = el('input', { value: (r.tags || []).join(', '), 'aria-label': 'Tags', placeholder: 'comma, separated' });
  const err = el('div', { class: 'field-error', role: 'alert' });
  openDialog([el('h2', { text: 'Edit link' }),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'URL' }), url), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Title' }), title),
    el('div', { class: 'grid-2' }, el('label', { class: 'field' }, el('span', { class: 'label', text: 'Kind' }), kind), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Owner' }), owner)),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Description' }), el('span', { class: 'help', text: 'What is inside it.' }), desc),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Tags' }), tags), err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'res-edit-save', text: 'Save', onclick: async () => {
        const body = { version: r.version };
        if (url.value.trim() !== r.url) body.url = url.value.trim();
        if (title.value !== r.title) body.title = title.value;
        if (kind.value !== r.kind) body.kind = kind.value;
        if ((desc.value || null) !== (r.description || null)) body.description = desc.value || null;
        if ((owner.value || null) !== (r.owner_id || null)) body.owner_id = owner.value || null;
        const tl = tags.value.split(',').map((x) => x.trim()).filter(Boolean);
        if (tl.join(',') !== (r.tags || []).join(',')) body.tags = tl;
        try { await api('PATCH', '/resources/' + r.id, body); closeDialog(); toast('Saved'); reloadPanel(); if (S.listReload) S.listReload(); }
        catch (e) { if (e.status === 409 && e.body.existing) err.textContent = 'Another link already has this URL: “' + e.body.existing.title + '”.'; else err.textContent = e.message; } } }))],
  { label: 'Edit link' });
}
