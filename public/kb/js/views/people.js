/* People (run 6, B1): owners become real people.
   - peopleTab(body): Settings -> People (admins). Every instructor and team
     member with its e-mail address and link state; a bulk CSV upload
     (name,email) shown as a PREVIEW first — exact matches, matches that differ
     only in case or spacing, suggested near matches to confirm one by one,
     ambiguous names to resolve by hand — and nothing is written until the
     admin confirms. Pending profile claims link to Approvals.
   - legacyExpertiseSection(): a Data quality list.
   (The dashboard's "Owned by you" is views/dashboard.js since F1; a claim is
   made from the record panel, detail.js. F6 removed the unused copies here.)
   E-mail addresses are shown to admins only (the server's RLS decides). */
import { S, el, add, clear, icon, typeIcon, typeLabel, api, toast, failToast, skeletonRows, empty, errorBox, plural, can } from '../core.js';

const STATUS = {
  exact: ['Exact match', 'ok'], normalised: ['Same name, other case or spacing', 'ok'], suggested: ['Suggested: confirm', 'warn'],
  ambiguous: ['Several records with this name: pick one', 'warn'], none: ['No matching record', ''], invalid: ['Not usable', 'danger'],
};
const STATE = { all: 'All', linked: 'Linked to a sign-in', waiting: 'Waiting for first sign-in', none: 'No e-mail yet' };

// ------------------------------------------------------------------ Settings -> People
export function peopleTab(body) {
  if (!can('admin')) { body.appendChild(empty('Admins only', 'People’s e-mail addresses are shown to admins only.', null, 'lock')); return; }
  const q = el('input', { type: 'search', placeholder: 'Find a person or an address', 'aria-label': 'Find a person', 'data-testid': 'people-search' });
  const state = el('select', { 'aria-label': 'Show', 'data-testid': 'people-state' }, Object.entries(STATE).map(([k, l]) => el('option', { value: k === 'all' ? '' : k, text: l })));
  const listBox = el('div', { 'data-testid': 'people-list' }, skeletonRows(6));
  const csvBox = el('section', { class: 'card', style: 'margin-bottom:16px', 'data-testid': 'people-csv' });
  add(body, [el('p', { class: 'muted small', style: 'margin-bottom:12px', text: 'A person record with an e-mail address is linked to that sign-in the first time the person signs in; they then own, as themselves, what their record owns by role. Addresses are visible to admins only and never written to the activity log.' }),
    csvBox, el('div', { class: 'row', style: 'gap:8px;margin-bottom:8px' }, el('div', { class: 'input-icon', style: 'flex:1;max-width:360px' }, icon('search'), q), state), listBox]);
  csvPanel(csvBox, () => load());
  let t = null;
  q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 200); });
  state.addEventListener('change', load);
  async function load() {
    try {
      const p = new URLSearchParams({ limit: '300' }); if (q.value.trim()) p.set('q', q.value.trim()); if (state.value) p.set('state', state.value);
      const out = await api('GET', '/person-records?' + p);
      clear(listBox);
      listBox.appendChild(el('p', { class: 'faint small', 'data-testid': 'people-counts', style: 'margin-bottom:8px',
        text: out.counts.linked + ' linked · ' + out.counts.waiting + ' waiting for first sign-in · ' + out.counts.no_email + ' current without an e-mail address' }));
      if (out.claims.length) listBox.appendChild(el('p', { class: 'note-box warn', 'data-testid': 'people-claims' }, plural(out.claims.length, 'profile claim') + ' waiting in ',
        el('a', { href: '#/approvals', text: 'Approvals' }), '.'));
      if (!out.items.length) { listBox.appendChild(empty('No one here', 'Try another search or filter.', null, 'users')); return; }
      const table = el('table', { class: 'table', 'data-testid': 'people-table' }, el('thead', {}, el('tr', {}, ['Person', 'Type', 'E-mail', 'Sign-in'].map((h) => el('th', { text: h })))),
        el('tbody', {}, out.items.map((x) => el('tr', { 'data-testid': 'people-row' },
          el('td', {}, el('a', { href: '#/settings?tab=people&open=' + x.id, text: x.name }), x.is_legacy ? el('span', { class: 'badge', text: 'Legacy' }) : null),
          el('td', { class: 'faint small', text: typeLabel(x.type) }),
          el('td', { class: 'small', text: x.email || '—' }),
          el('td', {}, x.user_id ? el('span', { class: 'badge ok', text: 'Linked' }) : x.email ? el('span', { class: 'badge warn', text: 'Waiting' }) : el('span', { class: 'faint small', text: '—' }))))));
      listBox.appendChild(el('div', { class: 'table-wrap' }, table));
      if (out.total > out.items.length) listBox.appendChild(el('p', { class: 'faint xs', style: 'margin-top:6px', text: 'Showing ' + out.items.length + ' of ' + out.total + '. Search to narrow it down.' }));
    } catch (e) { clear(listBox).appendChild(errorBox(e, load)); }
  }
  S.listReload = load;
  load();
}

function csvPanel(box, after) {
  const file = el('input', { type: 'file', accept: '.csv,text/csv', 'aria-label': 'CSV file', 'data-testid': 'people-csv-file' });
  const text = el('textarea', { rows: 4, placeholder: 'name,email\nAda Example,ada@interviewkickstart.com', 'aria-label': 'CSV: name,email', 'data-testid': 'people-csv-text', style: 'width:100%;font-family:var(--mono, monospace)' });
  const out = el('div', { 'data-testid': 'people-preview' });
  file.addEventListener('change', async () => { const f = file.files && file.files[0]; if (f) text.value = await f.text(); });
  const previewBtn = el('button', { class: 'btn', type: 'button', 'data-testid': 'people-preview-btn', text: 'Preview matches', onclick: async () => {
    try { renderPreview(out, await api('POST', '/person-records/preview', { csv: text.value }), after); } catch (e) { failToast(e, 'Could not read the CSV'); }
  } });
  add(box, [el('div', { class: 'card-head' }, el('h2', { text: 'Add e-mail addresses from a CSV' })),
    el('div', { class: 'card-body col', style: 'gap:8px' }, el('p', { class: 'card-hint', text: 'Two columns: name,email. You see every match first; nothing is saved until you confirm.' }),
      el('div', { class: 'row', style: 'gap:8px' }, file, previewBtn), text, out)]);
}

function renderPreview(box, res, after) {
  clear(box);
  const chosen = new Map();                 // row -> {node_id, email}
  const summary = Object.entries(res.summary).map(([k, n]) => n + ' ' + (STATUS[k] ? STATUS[k][0].toLowerCase() : k)).join(' · ');
  const confirm = el('button', { class: 'btn primary', type: 'button', 'data-testid': 'people-confirm', disabled: true });
  const setCount = () => { confirm.disabled = !chosen.size; confirm.textContent = chosen.size ? 'Link ' + plural(chosen.size, 'person', 'people') : 'Pick the rows to link'; };
  const rows = res.rows.map((r) => {
    const st = STATUS[r.status] || [r.status, ''];
    let pick = null;
    if (r.match && r.status !== 'invalid' && !r.email_taken_by) {
      pick = el('input', { type: 'checkbox', checked: r.status === 'exact' || r.status === 'normalised', 'aria-label': 'Link ' + r.match.name, 'data-testid': 'people-pick' });
      const sync = () => { if (pick.checked) chosen.set(r.row, { node_id: r.match.id, email: r.email }); else chosen.delete(r.row); setCount(); };
      pick.addEventListener('change', sync); sync();
    } else if (r.candidates && r.candidates.length && !r.email_taken_by) {
      pick = el('select', { 'aria-label': 'Which record is ' + r.name, 'data-testid': 'people-candidate' }, el('option', { value: '', text: 'Do not link' }),
        r.candidates.map((c) => el('option', { value: c.id, text: c.name + ' · ' + typeLabel(c.type) + (c.is_legacy ? ' · legacy' : '') })));
      pick.addEventListener('change', () => { if (pick.value) chosen.set(r.row, { node_id: pick.value, email: r.email }); else chosen.delete(r.row); setCount(); });
    }
    const note = r.reason || (r.email_taken_by ? 'This address is already on ' + r.email_taken_by.name : r.current_email ? 'Replaces ' + r.current_email : '');
    return el('tr', { 'data-testid': 'people-preview-row', 'data-status': r.status },
      el('td', { class: 'tabular faint', text: r.row }), el('td', { text: r.name || '—' }), el('td', { class: 'small', text: r.email || '—' }),
      el('td', {}, el('span', { class: 'badge ' + st[1], text: st[0] })),
      el('td', {}, r.match ? el('span', { class: 'row', style: 'gap:4px' }, typeIcon(r.match.type, 'sm'), r.match.name) : null, note ? el('div', { class: 'faint xs', text: note }) : null),
      el('td', {}, pick));
  });
  confirm.addEventListener('click', async () => {
    try {
      const out = await api('POST', '/person-records/link', { links: [...chosen.values()] });
      toast(plural(out.written, 'person', 'people') + ' linked · ' + out.linked_now + ' already signed in');
      clear(box); after();
    } catch (e) { failToast(e, 'Nothing was saved'); }
  });
  setCount();
  add(box, [el('p', { class: 'small', 'data-testid': 'people-preview-summary', text: summary + '. Nothing is saved yet.' }),
    el('div', { class: 'table-wrap' }, el('table', { class: 'table' }, el('thead', {}, el('tr', {}, ['Row', 'Name', 'E-mail', 'Match', 'Record', 'Link'].map((h) => el('th', { text: h })))), el('tbody', {}, rows))),
    el('div', { class: 'row', style: 'gap:8px;margin-top:8px' }, confirm, el('button', { class: 'btn ghost', type: 'button', text: 'Cancel', onclick: () => clear(box) }))]);
}

// ------------------------------------------------------------------ Data quality lists
function qualityList(title, tid, emptyText, load, row) {
  const ul = el('ul', { class: 'list bordered', 'data-testid': tid }, el('li', { class: 'link-row faint', text: 'Loading…' }));
  const count = el('span', { class: 'count', text: '…' });
  load().then((out) => {
    clear(ul); count.textContent = String(out.total);
    if (!out.items.length) ul.appendChild(el('li', { class: 'link-row faint', text: emptyText }));
    out.items.forEach((x) => ul.appendChild(el('li', null, row(x))));
  }).catch((e) => { clear(ul).appendChild(el('li', null, errorBox(e))); });
  return el('section', null, el('div', { class: 'row', style: 'margin-bottom:8px' }, el('h2', { text: title }), count), ul);
}
export function legacyExpertiseSection() {
  return qualityList('Legacy domains still referenced as expertise', 'q-legacy-expertise', 'No legacy domain is anyone’s current expertise.',
    () => api('GET', '/quality/legacy-expertise'),
    (x) => el('a', { class: 'link-row', href: '#/quality?open=' + x.id }, typeIcon('domain'), el('span', { class: 'truncate', style: 'flex:1;color:var(--text)', text: x.name }),
      el('span', { class: 'faint xs', text: plural(x.instructors, 'current instructor') })));
}
