/* The one-step New record side sheet (and the same form for editing), plus the
   link and relationship dialogs and the type-driven field inputs. Everything
   in one save: POST /nodes creates the record, its placement (nested inline
   creates), relationships, links, people and tags in ONE transaction; any
   failure rolls all of it back and the failing field is highlighted. */
import { S, el, add, $, $$, clear, icon, typeIcon, typeLabel, api, toast, failToast, avatar, personName, debounce, qs, host,
  openSheet, closeSheet, requestCloseSheet, openDialog, closeDialog, combobox, nodeSource, nodeItem, peopleSource, can, setQuery, you, plural } from './core.js';

// ------------------------------------------------------------------ link kinds
export function linkKindFor(r) {
  const key = r.link_kind || detectLinkKind(r.url || '');
  return S.linkKinds.find((k) => k.key === key) || { key: 'website', label: 'Website', icon: 'globe' };
}
export function detectLinkKind(url) {
  for (const lk of S.linkKinds) {
    for (const p of lk.patterns || []) { try { if (new RegExp(p, 'i').test(url)) return lk.key; } catch (e) { /* skip bad pattern */ } }
  }
  return 'website';
}
const KIND_LABELS = { kyp_slides: 'KYP slides / lecture deck', speaker_notes: 'Speaker notes', recording: 'Recording', live_class_link: 'Live class link',
  assignment_brief: 'Assignment brief', problem_statement: 'Problem statement', solution: 'Solution', evaluation_criteria: 'Evaluation criteria',
  question_bank: 'Question bank', interview_guide: 'Interview guide', reading: 'Reading', reference_doc: 'Reference doc', repo: 'Repository',
  slides: 'Slides', assignment: 'Assignment', doc: 'Document', sheet: 'Sheet', video: 'Video', pdf: 'PDF', folder: 'Folder', link: 'Link', other: 'Other' };
const KIND_ORDER = ['kyp_slides', 'speaker_notes', 'recording', 'live_class_link', 'assignment_brief', 'problem_statement', 'solution', 'evaluation_criteria',
  'question_bank', 'interview_guide', 'reading', 'reference_doc', 'repo', 'slides', 'assignment', 'doc', 'sheet', 'video', 'pdf', 'folder', 'link', 'other'];
export function kindSelect(value, testid) {
  return el('select', { 'aria-label': 'Kind', 'data-testid': testid }, KIND_ORDER.filter((k) => S.resourceKinds.includes(k)).map((k) => el('option', { value: k, text: KIND_LABELS[k] || k, selected: k === value })));
}
function defaultKind(linkKey) { const lk = S.linkKinds.find((k) => k.key === linkKey); return (lk && lk.defaults && lk.defaults.kind) || 'link'; }
const isUrl = (s) => /^https?:\/\/[^\s/$.?#][^\s]*\.[^\s]+/i.test(s);

// ------------------------------------------------------------------ field inputs (type-driven)
export function fieldDisplay(f, val) {
  if (val === undefined || val === null || val === '') return el('span', { class: 'faint', text: '—' });
  if (f.kind === 'checkbox') return el('span', { text: val ? 'Yes' : 'No' });
  if (f.kind === 'url') return el('a', { href: val, target: '_blank', rel: 'noopener noreferrer', class: 'truncate', text: host(val) || val });
  if (f.kind === 'person') return el('span', { class: 'row' }, avatar(val), personName(val));
  if (f.kind === 'single_select') { const o = (f.options || []).find((x) => x.value === val); return el('span', { class: 'badge', text: o ? o.label : val }); }
  if (f.kind === 'multi_select') return (val || []).map((v) => { const o = (f.options || []).find((x) => x.value === v); return el('span', { class: 'badge', text: o ? o.label : v }); });
  if (f.kind === 'reference') return el('a', { href: '#/records?open=' + val, text: 'Open record' });
  if (f.kind === 'duration') return el('span', { class: 'tabular', text: val + ' min' });
  return el('span', { text: String(val) });
}
/* onChange(value) fires on commit (change/blur), with null for empty. */
export function fieldInput(f, val, onChange, opts) {
  opts = opts || {};
  const tid = 'field-input-' + f.key;
  const commit = (v) => onChange(v === '' ? null : v);
  switch (f.kind) {
    case 'long_text': { const t = el('textarea', { rows: opts.compact ? '2' : '3', 'data-testid': tid, 'aria-label': f.label }, val || ''); t.addEventListener('change', () => commit(t.value.trim())); return t; }
    case 'number': case 'duration': { const i = el('input', { type: 'number', step: f.kind === 'duration' ? '5' : 'any', min: f.kind === 'duration' ? '0' : null, value: val === undefined || val === null ? '' : String(val), 'data-testid': tid, 'aria-label': f.label + (f.kind === 'duration' ? ' (minutes)' : '') });
      i.addEventListener('change', () => commit(i.value === '' ? null : Number(i.value))); return f.kind === 'duration' ? el('span', { class: 'row' }, i, el('span', { class: 'faint small', text: 'min' })) : i; }
    case 'date': { const i = el('input', { type: 'date', value: val || '', 'data-testid': tid, 'aria-label': f.label }); i.addEventListener('change', () => commit(i.value)); return i; }
    case 'datetime': { const i = el('input', { type: 'datetime-local', value: val ? String(val).slice(0, 16) : '', 'data-testid': tid, 'aria-label': f.label }); i.addEventListener('change', () => commit(i.value ? new Date(i.value).toISOString() : '')); return i; }
    case 'url': { const i = el('input', { type: 'url', value: val || '', placeholder: 'https://…', 'data-testid': tid, 'aria-label': f.label }); i.addEventListener('change', () => commit(i.value.trim())); return i; }
    case 'checkbox': { const i = el('input', { type: 'checkbox', checked: !!val, 'data-testid': tid, 'aria-label': f.label }); i.addEventListener('change', () => onChange(i.checked)); return i; }
    case 'single_select': { const s = el('select', { 'data-testid': tid, 'aria-label': f.label }, el('option', { value: '', text: '—' }), (f.options || []).map((o) => el('option', { value: o.value, text: o.label, selected: o.value === val })));
      s.addEventListener('change', () => commit(s.value)); return s; }
    case 'multi_select': {
      const box = el('div', { class: 'row', style: 'flex-wrap:wrap;gap:8px', 'data-testid': tid });
      (f.options || []).forEach((o) => { const c = el('input', { type: 'checkbox', checked: (val || []).includes(o.value), 'aria-label': o.label });
        c.addEventListener('change', () => onChange($$('input', box).map((x, i) => (x.checked ? f.options[i].value : null)).filter(Boolean)));
        box.appendChild(el('label', { class: 'row small', style: 'gap:4px' }, c, o.label)); });
      return box; }
    case 'person': { const s = el('select', { 'data-testid': tid, 'aria-label': f.label }, el('option', { value: '', text: '—' }), S.people.map((p) => el('option', { value: p.user_id, text: personName(p.user_id), selected: p.user_id === val })));
      s.addEventListener('change', () => commit(s.value)); return s; }
    case 'reference': {
      const cb = combobox({ testid: tid, label: f.label, placeholder: 'Search ' + (f.ref_types || []).map((k) => typeLabel(k, true).toLowerCase()).join(', '),
        source: nodeSource(f.ref_types), onChange: (v) => onChange(v ? v.id : null), value: val ? [{ id: val, label: 'Linked record' }] : [] });
      if (val) api('GET', '/nodes/' + val).then((n) => cb.setValue([nodeItem(n)])).catch(() => {});
      return cb; }
    default: { const i = el('input', { value: val || '', 'data-testid': tid, 'aria-label': f.label, maxlength: '300' }); i.addEventListener('change', () => commit(i.value.trim())); return i; }
  }
}

// ------------------------------------------------------------------ placement picker (nested inline create)
/* Returns an element whose .getValue() is a list of placement specs:
   "<id>" or {new: {type, name, parent: spec?}}. */
function placementPicker(typeKey, initial, testid, single) {
  const list = el('div', { class: 'col', 'data-testid': testid || 'placement' });
  const rows = [];
  function parentsOf(k) { const t = S.typeByKey[k]; return (t && t.allowed_parents) || []; }
  function addRow(pre) {
    const row = el('div', { class: 'col', style: 'gap:4px' });
    const state = { value: null, nested: null };
    const allowed = parentsOf(typeKey);
    const cb = combobox({ testid: (testid || 'placement') + '-picker', label: 'Belongs to', placeholder: 'Search ' + allowed.map((k) => typeLabel(k, true).toLowerCase()).join(', ') + '…',
      source: nodeSource(allowed), create: (q) => allowed.map((k) => ({ id: 'new:' + k + ':' + q, label: 'Create ' + typeLabel(k).toLowerCase() + ' “' + q + '”', type: k, name: q, testid: 'create-' + k })),
      onCreateRequest: (it, done) => done({ id: 'new:' + it.type + ':' + it.name, label: it.name + ' (new ' + typeLabel(it.type).toLowerCase() + ')', icon: typeIcon(it.type), type: it.type, isNew: true, name: it.name }),
      value: pre ? [pre] : [],
      onChange: (v) => { state.value = v; drawNested(); } });
    const nestedBox = el('div', { style: 'margin-left:16px' });
    function drawNested() {
      clear(nestedBox); state.nested = null;
      if (state.value && state.value.isNew && parentsOf(state.value.type).length) {
        const np = placementPicker(state.value.type, null, (testid || 'placement') + '-nested', true);
        state.nested = np;
        nestedBox.append(el('div', { class: 'faint xs', text: 'Place the new ' + typeLabel(state.value.type).toLowerCase() + ' under (optional):' }), np);
      }
    }
    const rm = el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove placement', onclick: () => { rows.splice(rows.indexOf(state), 1); row.remove(); } }, icon('x', 'sm'));
    row.append(el('div', { class: 'row' }, el('div', { style: 'flex:1;min-width:0' }, cb), rm), nestedBox);
    state.value = pre || null;
    state.spec = () => {
      const v = state.value; if (!v) return null;
      if (!v.isNew) return v.id;
      const parent = state.nested ? state.nested.getValue()[0] : null;
      return { new: Object.assign({ type: v.type, name: v.name }, parent ? { parent } : {}) };
    };
    rows.push(state);
    list.insertBefore(row, addBtn);
  }
  const addBtn = el('button', { class: 'btn ghost sm', type: 'button', style: 'align-self:flex-start', 'data-testid': (testid || 'placement') + '-add', onclick: () => addRow() }, icon('plus', 'sm'), 'Add another place');
  list.appendChild(addBtn);
  if (single) addBtn.hidden = true;                // a new parent has one place
  (initial && initial.length ? initial : [null]).forEach((p) => addRow(p));
  list.getValue = () => rows.map((r) => r.spec()).filter(Boolean);
  list.count = () => list.getValue().length;
  return list;
}

// ------------------------------------------------------------------ relationship rows
function relOptions(typeKey) {
  const out = [];
  S.edgeTypes.forEach((et) => (et.rules || []).forEach((r) => {
    if (et.key === 'contains' && r.target === typeKey) return;      // placement covers "part of"
    if (r.source === typeKey) out.push({ key: et.key + '|out|' + r.target, type: et.key, direction: 'out', other: r.target, label: et.label + ' → ' + typeLabel(r.target).toLowerCase() });
    if (r.target === typeKey && et.key !== 'contains') out.push({ key: et.key + '|in|' + r.source, type: et.key, direction: 'in', other: r.source, label: (et.inverse_label || et.label) + ' ← ' + typeLabel(r.source).toLowerCase() });
  }));
  return out.sort((a, b) => a.label.localeCompare(b.label));
}
function relationshipRows(typeKey, getName, testid) {
  const box = el('div', { class: 'col', 'data-testid': testid || 'rel-rows' });
  const rows = [];
  const addBtn = el('button', { class: 'btn ghost sm', type: 'button', style: 'align-self:flex-start', 'data-testid': 'add-relationship', onclick: () => addRow() }, icon('plus', 'sm'), 'Add relationship');
  function addRow() {
    const opts = relOptions(typeKey());
    const st = { opt: opts[0] || null, target: null, note: '' };
    const sel = el('select', { 'aria-label': 'Relationship', 'data-testid': 'rel-type' }, opts.map((o) => el('option', { value: o.key, text: o.label })));
    if (!opts.length) sel.appendChild(el('option', { text: 'No relationships allowed for this type' }));
    const tgtHost = el('div', { style: 'flex:1;min-width:0' });
    const sentence = el('div', { class: 'faint xs', 'data-testid': 'rel-sentence' });
    const note = el('input', { placeholder: 'Note (optional)', 'aria-label': 'Note', style: 'width:100%' });
    note.addEventListener('input', () => { st.note = note.value; });
    function drawTarget() {
      clear(tgtHost);
      if (!st.opt) return;
      tgtHost.appendChild(combobox({ testid: 'rel-target', label: 'Related record', placeholder: 'Search ' + typeLabel(st.opt.other, true).toLowerCase() + '…',
        source: nodeSource([st.opt.other]), create: (q) => [{ id: 'new:' + q, label: 'Create ' + typeLabel(st.opt.other).toLowerCase() + ' “' + q + '”', name: q }],
        onCreateRequest: (it, done) => done({ id: 'new:' + st.opt.other + ':' + it.name, label: it.name + ' (new)', icon: typeIcon(st.opt.other), isNew: true, name: it.name, type: st.opt.other }),
        onChange: (v) => { st.target = v; drawSentence(); } }));
      drawSentence();
    }
    function drawSentence() {
      const me = getName() || 'This record', other = st.target ? st.target.label.replace(/ \(new\)$/, '') : '…';
      const et = st.opt && S.edgeTypes.find((e) => e.key === st.opt.type);
      sentence.textContent = !st.opt ? '' : st.opt.direction === 'out' ? '“' + me + '” ' + et.label + ' “' + other + '”' : '“' + other + '” ' + et.label + ' “' + me + '”';
    }
    sel.addEventListener('change', () => { st.opt = opts.find((o) => o.key === sel.value); st.target = null; drawTarget(); });
    const row = el('div', { class: 'col', style: 'gap:4px;padding:8px;border:1px solid var(--border);border-radius:6px', 'data-testid': 'rel-row' },
      el('div', { class: 'row' }, sel, tgtHost, el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove relationship row', onclick: () => { rows.splice(rows.indexOf(st), 1); row.remove(); } }, icon('x', 'sm'))),
      note, sentence);
    st.row = row;
    rows.push(st); box.insertBefore(row, addBtn); drawTarget();
  }
  box.appendChild(addBtn);
  box.getValue = () => rows.filter((r) => r.opt && r.target).map((r) => ({ type: r.opt.type, direction: r.opt.direction,
    node: r.target.isNew ? { new: { type: r.target.type, name: r.target.name } } : r.target.id, note: r.note || undefined, _row: r.row }));
  box.validate = () => {
    const seen = {};
    for (const r of box.getValue()) {
      const k = r.type + r.direction + JSON.stringify(r.node);
      if (seen[k]) return { row: r._row, message: 'This relationship is listed twice.' };
      seen[k] = true;
    }
    return null;
  };
  box.rows = () => rows.map((r) => r.row);
  box.count = () => box.getValue().length;
  box.refreshOptions = () => { rows.slice().forEach((r) => r.row.remove()); rows.length = 0; };
  box.addRow = () => addRow();
  return box;
}

// ------------------------------------------------------------------ link rows
function linkRows(testid) {
  const box = el('div', { class: 'col', 'data-testid': testid || 'link-rows' });
  const rows = [];
  const addBtn = el('button', { class: 'btn ghost sm', type: 'button', style: 'align-self:flex-start', 'data-testid': 'add-link', onclick: () => addRow() }, icon('plus', 'sm'), 'Add link');
  const pickBtn = el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'pick-link', onclick: () => addRow(true) }, icon('library', 'sm'), 'Pick from library');
  function addRow(fromLibrary) {
    const st = { existing: null, row: null };
    const url = el('input', { type: 'url', placeholder: 'Paste a URL — Drive, Docs, Slides, UpLevel, GitHub, YouTube, Zoom…', 'aria-label': 'URL', 'data-testid': 'link-url', style: 'flex:1' });
    const kindIcon = el('span', { class: 'type-icon', style: 'width:20px' }, icon('link'));
    const msg = el('div', { class: 'xs', 'data-testid': 'link-msg' });
    const title = el('input', { placeholder: 'Title', 'aria-label': 'Title', 'data-testid': 'link-title' });
    const kind = kindSelect('link', 'link-kind');
    const desc = el('input', { placeholder: 'Description — what is inside it', 'aria-label': 'Description' });
    const purpose = el('input', { placeholder: 'Purpose — why it is attached here', 'aria-label': 'Purpose', 'data-testid': 'link-purpose' });
    const owner = el('select', { 'aria-label': 'Link owner' }, S.people.map((p) => el('option', { value: p.user_id, text: personName(p.user_id) + (you(p.user_id) ? ' (you)' : ''), selected: you(p.user_id) })));
    const tags = el('input', { placeholder: 'Tags, comma separated', 'aria-label': 'Link tags' });
    const details = el('div', { class: 'col', style: 'gap:6px' }, el('div', { class: 'grid-2' }, title, kind), desc, purpose, el('div', { class: 'grid-2' }, owner, tags));
    const lib = combobox({ testid: 'link-library', label: 'Find a link in the library', placeholder: 'Search the library by title or URL',
      source: async (q) => (await api('GET', '/resources' + qs({ q, limit: 10 }))).items.map((r) => ({ id: r.id, label: r.title, sub: r.url, icon: icon(linkKindFor(r).icon), r })),
      onChange: (v) => { st.existing = v ? v.r : null; drawExisting(); } });
    function drawExisting() {
      if (st.existing) { details.hidden = true; url.hidden = true; kindIcon.hidden = true; msg.textContent = 'Using existing link “' + st.existing.title + '”.'; msg.className = 'xs faint'; details.after(purpose); }
    }
    const check = debounce(async () => {
      const u = url.value.trim(); msg.textContent = ''; msg.className = 'xs'; st.existing = null; details.hidden = false;
      if (!u) return;
      if (!isUrl(u)) { msg.textContent = 'Enter a full link starting with https://'; msg.className = 'xs field-error'; return; }
      const lk = S.linkKinds.find((k) => k.key === detectLinkKind(u)) || {};
      kindIcon.replaceChildren(icon(lk.icon || 'globe')); kindIcon.title = lk.label || 'Website';
      if (kind.value === 'link' || !st.kindTouched) kind.value = defaultKind(lk.key);
      try {
        const r = await api('GET', '/resources' + qs({ q: u.replace(/\/+$/, ''), limit: 5 }));
        const hit = r.items.find((x) => x.url.replace(/\/+$/, '').toLowerCase() === u.replace(/\/+$/, '').toLowerCase());
        if (hit) {
          clear(msg).append('Already in the library as “' + hit.title + '”. ', el('button', { class: 'btn sm', type: 'button', 'data-testid': 'use-existing', text: 'Use existing',
            onclick: () => { st.existing = hit; details.hidden = true; msg.textContent = 'Using existing link “' + hit.title + '”.'; msg.className = 'xs faint'; details.after(purpose); } }));
        } else msg.append(el('span', { class: 'faint', text: (lk.label || 'Website') + ' link' }));
      } catch (e) { /* the server checks again on save */ }
    }, 250);
    url.addEventListener('input', check);
    kind.addEventListener('change', () => { st.kindTouched = true; });
    const rm = el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove link row', onclick: () => { rows.splice(rows.indexOf(st), 1); row.remove(); } }, icon('x', 'sm'));
    const row = el('div', { class: 'col', style: 'gap:6px;padding:8px;border:1px solid var(--border);border-radius:6px', 'data-testid': 'link-row-form' },
      fromLibrary ? el('div', { class: 'row' }, el('div', { style: 'flex:1;min-width:0' }, lib), rm) : el('div', { class: 'row' }, kindIcon, url, rm), msg, fromLibrary ? purpose : details);
    if (fromLibrary) { details.hidden = true; }
    st.row = row;
    st.value = () => {
      if (st.existing) return { resource_id: st.existing.id, note: purpose.value.trim() || undefined };
      const u = url.value.trim(); if (!u) return null;
      return { url: u, title: title.value.trim() || host(u) || u, kind: kind.value, link_kind: detectLinkKind(u), description: desc.value.trim() || undefined,
        note: purpose.value.trim() || undefined, owner_id: owner.value || undefined, tags: tags.value.split(',').map((x) => x.trim()).filter(Boolean) };
    };
    st.invalid = () => (url.hidden || !url.value.trim() || isUrl(url.value.trim()) ? null : 'Enter a full link starting with https://');
    rows.push(st); box.insertBefore(row, actions);
    (fromLibrary ? lib : url).focus && setTimeout(() => (fromLibrary ? lib.focus() : url.focus()), 0);
  }
  const actions = el('div', { class: 'row' }, addBtn, pickBtn);
  box.appendChild(actions);
  box.getValue = () => rows.map((r) => r.value()).filter(Boolean);
  box.rows = () => rows.map((r) => r.row);
  box.firstInvalid = () => { for (const r of rows) { const m = r.invalid(); if (m) return { row: r.row, message: m }; } return null; };
  box.count = () => box.getValue().length;
  box.addRow = (lib) => addRow(lib);
  return box;
}

// ------------------------------------------------------------------ the form
const DRAFT_KEY = 'kb_draft_new_record';
function section(title, content, opts) {
  opts = opts || {};
  const count = el('span', { class: 'count' });
  const d = el('details', { class: 'form-section', open: !!opts.open, 'data-testid': 'section-' + opts.key },
    el('summary', null, icon('chevron-right', 'sm chev'), title, count, opts.hint ? el('span', { class: 'faint xs', style: 'font-weight:400', text: opts.hint }) : null), content);
  d.setCount = (n) => { count.textContent = n ? String(n) : ''; };
  return d;
}

/* o: {type, name, parents:[{id,label,type}], edit: node} */
export function openRecordForm(o) {
  o = o || {};
  const editing = !!o.edit;
  const n = o.edit || null;
  let draft = null;
  if (!editing) { try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch (e) { draft = null; } }
  let typeKey = (n && n.type) || o.type || (draft && draft.type) || 'module';
  if (!S.typeByKey[typeKey]) typeKey = S.types[0].key;
  const contributorOnly = !can('editor') && !editing;
  const err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'form-error' });

  // --- basics
  const typeCb = combobox({ testid: 'create-type', label: 'Type', placeholder: 'Search types…', openOnFocus: true,
    source: async (q) => S.types.filter((t) => !q || (t.label + ' ' + (t.description || '')).toLowerCase().includes(q.toLowerCase()))
      .map((t) => ({ id: t.key, label: t.label, sub: t.description || '', icon: typeIcon(t.key) })),
    value: [{ id: typeKey, label: typeLabel(typeKey), icon: typeIcon(typeKey) }],
    onChange: (v) => { if (v) { typeKey = v.id; onTypeChange(); } } });
  const typeHelp = el('div', { class: 'help' });
  const name = el('input', { 'data-testid': 'create-name', 'aria-label': 'Name', maxlength: '300', autofocus: true, value: (n && n.name) || o.name || '' });
  const dupBox = el('div', { class: 'xs', 'data-testid': 'dup-warning' });
  const summary = el('textarea', { rows: '2', 'data-testid': 'create-summary', 'aria-label': 'Summary', maxlength: '2000' }, (n && n.summary) || '');
  const status = el('select', { 'data-testid': 'create-status', 'aria-label': 'Status' }, el('option', { value: 'active', text: 'Live' }), el('option', { value: 'draft', text: 'Draft' }));
  const review = el('select', { 'data-testid': 'create-review', 'aria-label': 'Review status' }, [['none', 'Not reviewed'], ['needs_review', 'Needs review'], ['approved', 'Reviewed']].map(([v, l]) => el('option', { value: v, text: l })));
  if (n) { status.value = n.status === 'draft' ? 'draft' : 'active'; review.value = n.review_status || 'none'; }
  const fieldRow = (label, input, req, help, key) => el('label', { class: 'field', 'data-field': key }, el('span', { class: 'label' + (req ? ' req' : ''), text: label }), input, help ? el('span', { class: 'help', text: help }) : null);
  const templateSel = el('select', { 'aria-label': 'Start from a template', 'data-testid': 'template-select' }, el('option', { value: '', text: 'Blank' }));
  const templateRow = el('label', { class: 'field', hidden: true }, el('span', { class: 'label', text: 'Start from' }), templateSel, el('span', { class: 'help', text: 'Creates the template’s modules, weeks and sessions too, renamed for this one.' }));
  const basics = el('div', { class: 'form-section' },
    el('div', { class: 'field', 'data-field': 'type' }, el('span', { class: 'label req', text: 'Type' }), typeCb, typeHelp),
    fieldRow('Name', name, true, null, 'name'), dupBox, templateRow,
    fieldRow('Summary', summary, false, 'One line: what is this?', 'summary'),
    el('div', { class: 'grid-2' }, fieldRow('Status', status), fieldRow('Review status', review)));
  const requiredFields = el('div', { class: 'col', style: 'gap:12px' });
  basics.appendChild(requiredFields);

  // --- optional sections
  const props = Object.assign({}, (n && n.props) || {});
  const placement = el('div');
  const rels = relationshipRows(() => typeKey, () => name.value.trim());
  const links = linkRows();
  const owner = combobox({ testid: 'owner-picker', label: 'Primary owner', placeholder: 'Search people', source: peopleSource(['contributor', 'editor', 'admin']),
    value: n ? (n.owner_id ? [{ id: n.owner_id, label: personName(n.owner_id), icon: avatar(n.owner_id) }] : []) : [{ id: S.me.user_id, label: personName(S.me.user_id) + ' (you)', icon: avatar(S.me.user_id) }] });
  const coOwners = combobox({ multi: true, testid: 'co-owners', label: 'Secondary owners', placeholder: 'Add people', source: peopleSource(),
    value: ((n && n.co_owners) || []).map((u) => ({ id: u, label: personName(u), icon: avatar(u) })) });
  const instr = (et, tid) => combobox({ multi: true, testid: tid, label: et, placeholder: 'Search instructors', source: nodeSource(['instructor']),
    create: (q) => [{ id: 'new:' + q, label: 'Add person “' + q + '”', name: q }],
    onCreateRequest: (it, done) => done({ id: 'new:instructor:' + it.name, label: it.name + ' (new)', icon: typeIcon('instructor'), isNew: true, name: it.name }) });
  const instructors = instr('Instructors', 'instructors'), smes = instr('Subject experts', 'smes');
  const tagsCb = combobox({ multi: true, testid: 'tags', label: 'Tags', placeholder: 'Add tags', value: ((n && n.tags) || []).map((t) => ({ id: t.name, label: '#' + t.name })),
    source: async (q) => (await api('GET', '/tags')).items.filter((t) => !q || t.name.includes(q.toLowerCase())).slice(0, 10).map((t) => ({ id: t.name, label: '#' + t.name })),
    create: (q) => [{ id: q, label: 'Create tag “' + q + '”' }], onCreateRequest: (it, done) => done({ id: it.id.replace(/^new:/, ''), label: '#' + it.id.replace(/^new:/, '') }) });
  const optionalFields = el('div', { class: 'col', style: 'gap:12px' });

  const sPlace = section('Placement', placement, { key: 'placement', open: !editing, hint: 'where it belongs' });
  const sRels = section('Relationships', rels, { key: 'relationships' });
  const sLinks = section('Links and resources', links, { key: 'links', open: !editing });
  const sPeople = section('People', el('div', { class: 'col', style: 'gap:12px' }, fieldRow('Primary owner', owner, false, 'Defaults to you.'), fieldRow('Secondary owners', coOwners),
    editing ? null : fieldRow('Instructors', instructors, false, 'Linked with “teaches”.'), editing ? null : fieldRow('Subject experts (SMEs)', smes)), { key: 'people' });
  const sTags = section('Tags', tagsCb, { key: 'tags' });
  const sFields = section('More fields', optionalFields, { key: 'fields' });

  let existingBlock = null;
  if (editing) {
    existingBlock = el('div', { class: 'note-box', style: 'margin:16px 24px 0' }, 'Placement, relationships and links of this record are edited on its tabs; anything you add here is added to them.');
  }
  const form = el('form', { novalidate: true, 'data-testid': 'record-form', onsubmit: (e) => { e.preventDefault(); submit(false); } },
    contributorOnly ? el('div', { class: 'note-box accent', style: 'margin:16px 24px 0', 'data-testid': 'proposal-note' }, icon('circle-check', 'sm'), ' As a contributor, your new record is sent to an editor for approval. You will see it in Approvals.') : null,
    existingBlock, basics, sPlace, sRels, sLinks, sPeople, sTags, sFields, el('div', { style: 'padding:0 24px' }, err));

  function onTypeChange() {
    const t = S.typeByKey[typeKey];
    typeHelp.textContent = t.description || '';
    if (!editing) status.value = t.default_status === 'draft' ? 'draft' : 'active';
    clear(requiredFields); clear(optionalFields);
    (t.fields || []).filter((f) => !f.archived).forEach((f) => {
      if (!editing && props[f.key] === undefined && f.default !== undefined) props[f.key] = f.default;
      const input = fieldInput(f, props[f.key], (v) => { if (v === null) delete props[f.key]; else props[f.key] = v; changed(); });
      const row = el('div', { class: 'field', 'data-field': 'props.' + f.key }, el('span', { class: 'label' + (f.required ? ' req' : ''), text: f.label }), input, f.help ? el('span', { class: 'help', text: f.help }) : null);
      (f.required ? requiredFields : optionalFields).appendChild(row);
    });
    sFields.hidden = !optionalFields.children.length;
    clear(placement);
    if ((t.allowed_parents || []).length) placement.appendChild(placementPicker(typeKey, o.parents || null, 'placement'));
    else placement.appendChild(el('p', { class: 'faint small', text: typeLabel(typeKey, true) + ' are not placed under anything.' }));
    sPlace.hidden = editing;
    templateRow.hidden = editing || !t.is_container;
    rels.refreshOptions();
    checkName();
  }
  if (!editing) api('GET', '/templates').then((r) => r.items.forEach((t) => templateSel.appendChild(el('option', { value: t.id, text: t.name + ' (' + typeLabel(t.root_type).toLowerCase() + ')' })))).catch(() => {});

  const checkName = debounce(async () => {
    clear(dupBox);
    const v = name.value.trim();
    if (!v || (editing && v === n.name)) return;
    try {
      const r = await api('GET', '/nodes/check-name' + qs({ type: typeKey, name: v }));
      if (r.exact && !(editing && r.exact.id === n.id)) {
        dupBox.append(el('span', { class: 'field-error', text: 'A ' + typeLabel(typeKey).toLowerCase() + ' with this name already exists. ' }),
          el('a', { href: '#/records?open=' + r.exact.id, 'data-testid': 'open-existing', onclick: () => closeSheet(true), text: 'Open existing?' }));
      } else if (r.similar.length) {
        dupBox.append(el('span', { class: 'faint', text: 'Similar: ' }), ...r.similar.slice(0, 3).map((s, i) => [i ? ', ' : '', el('a', { href: '#/records?open=' + s.id, onclick: () => closeSheet(true), text: s.name })]));
      }
    } catch (e) { /* the server checks again on save */ }
  }, 250);
  name.addEventListener('input', () => { checkName(); changed(); });

  // --- counts + draft autosave
  function changed() {
    sRels.setCount(rels.count()); sLinks.setCount(links.count()); sTags.setCount(tagsCb.getValue().length);
    sPeople.setCount(coOwners.getValue().length + instructors.getValue().length + smes.getValue().length);
    const pv = placement.firstChild && placement.firstChild.getValue ? placement.firstChild.getValue().length : 0; sPlace.setCount(pv);
    if (!editing) saveDraft();
  }
  const saveDraft = debounce(() => {
    const d = { type: typeKey, name: name.value, summary: summary.value, at: Date.now() };
    try { if (d.name || d.summary) localStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch (e) { /* ignore */ }
  }, 400);
  form.addEventListener('input', changed); form.addEventListener('change', changed); form.addEventListener('click', () => setTimeout(changed, 0));
  const dirty = () => editing ? (name.value !== n.name || summary.value !== (n.summary || '')) : !!(name.value.trim() || summary.value.trim() || links.count() || rels.count());

  // --- submit
  function clearErrors() { err.textContent = ''; $$('.invalid', form).forEach((x) => x.classList.remove('invalid')); }
  function markError(field, message) {
    err.textContent = message;
    let target = null;
    if (!field) target = null;
    else if (field === 'name' || field === 'type' || field === 'summary' || field.startsWith('props.')) target = $('[data-field="' + field + '"]', form);
    else if (field.startsWith('parents')) { sPlace.open = true; target = sPlace; }
    else if (field.startsWith('edges')) { sRels.open = true; target = rels.rows()[Number(field.split('.')[1])] || sRels; }
    else if (field.startsWith('resources')) { sLinks.open = true; target = links.rows()[Number(field.split('.')[1])] || sLinks; }
    else if (field.startsWith('instructors') || field.startsWith('smes') || field === 'owner_id') { sPeople.open = true; target = sPeople; }
    if (target) {
      if (target.closest('details')) target.closest('details').open = true;
      target.classList.add('invalid'); target.scrollIntoView({ block: 'center' });
      const f = target.querySelector('input, select, textarea'); if (f) f.focus();
    }
  }
  const submitBtn = el('button', { class: 'btn primary', type: 'button', 'data-testid': 'create-submit', onclick: () => submit(false) },
    editing ? 'Save changes' : contributorOnly ? 'Send for approval' : 'Create', el('kbd', { text: /Mac/.test(navigator.platform) ? '⌘↵' : 'Ctrl↵', style: 'border-color:transparent;color:inherit;background:transparent' }));
  const anotherBtn = editing ? null : el('button', { class: 'btn', type: 'button', 'data-testid': 'create-another', text: contributorOnly ? 'Send and add another' : 'Create and add another', onclick: () => submit(true) });

  async function submit(another) {
    clearErrors();
    if (!name.value.trim()) { markError('name', 'Give it a name.'); return; }
    const bad = links.firstInvalid(); if (bad) { sLinks.open = true; bad.row.classList.add('invalid'); err.textContent = bad.message; return; }
    const dupRel = rels.validate(); if (dupRel) { sRels.open = true; dupRel.row.classList.add('invalid'); err.textContent = dupRel.message; return; }
    submitBtn.disabled = true; if (anotherBtn) anotherBtn.disabled = true;
    try {
      if (editing) await saveEdit(); else await saveNew(another);
    } catch (e) {
      if (e.status === 202) {
        try { localStorage.removeItem(DRAFT_KEY); } catch (er) { /* ignore */ }
        toast(e.message, { action: { label: 'View', fn: () => { location.hash = '#/approvals'; } } });
        if (another) resetForm(); else closeSheet(true);
      } else if (e.status === 409 && e.body.existing) {
        markError('name', e.message + '.');
        dupBox.replaceChildren(el('a', { href: '#/records?open=' + e.body.existing.id, 'data-testid': 'open-existing', onclick: () => closeSheet(true), text: 'Open the existing ' + typeLabel(e.body.existing.type || typeKey).toLowerCase() }));
      } else markError(e.body && e.body.field, e.message);
    } finally { submitBtn.disabled = false; if (anotherBtn) anotherBtn.disabled = false; }
  }
  async function saveNew(another) {
    const t = S.typeByKey[typeKey];
    const ownerV = owner.getValue();
    const body = { type: typeKey, name: name.value.trim(), summary: summary.value.trim() || undefined, status: status.value, review_status: review.value,
      owner_id: ownerV ? ownerV.id : null, co_owners: coOwners.getValue().map((x) => x.id),
      parents: placement.firstChild && placement.firstChild.getValue ? placement.firstChild.getValue() : [],
      edges: rels.getValue().map(({ _row, ...r }) => r), resources: links.getValue(),
      instructors: instructors.getValue().map((x) => (x.isNew ? { new: { name: x.name } } : x.id)), smes: smes.getValue().map((x) => (x.isNew ? { new: { name: x.name } } : x.id)),
      tags: tagsCb.getValue().map((x) => x.id), props: Object.keys(props).length ? props : undefined };
    if (templateSel.value && t.is_container) {
      const out = await api('POST', '/templates/' + templateSel.value + '/instantiate', { name: body.name, parents: body.parents });
      done(out.root, another, 'Created “' + out.root.name + '” from the template (' + plural(out.created, 'record') + ')');
      return;
    }
    const made = await api('POST', '/nodes', body);
    done(made, another, 'Created “' + made.name + '”' + (made.created_inline && made.created_inline.length ? ' and ' + plural(made.created_inline.length, 'new record') : ''));
  }
  function done(made, another, msg) {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
    const canUndo = can('editor');
    toast(msg, { actions: [{ label: 'Open', fn: () => setQuery({ open: made.id, res: null }) }].concat(canUndo ? [{ label: 'Undo', fn: async () => {
      try { await api('POST', '/nodes/' + made.id + '/archive'); toast('Undone — “' + made.name + '” archived.'); if (S.listReload) S.listReload(); } catch (e) { failToast(e, 'Undo failed'); } } }] : []) });
    if (S.listReload) S.listReload();
    import('./app.js').then((m) => m.refreshCounts());
    if (another) resetForm(); else { closeSheet(true); if (o.onCreated) o.onCreated(made); else setQuery({ open: made.id, res: null }); }
  }
  function resetForm() { closeSheet(true); openRecordForm({ type: typeKey, parents: o.parents }); }

  async function saveEdit() {
    const body = { version: n.version };
    if (name.value.trim() !== n.name) body.name = name.value.trim();
    if ((summary.value.trim() || null) !== (n.summary || null)) body.summary = summary.value.trim() || null;
    if (status.value !== (n.status === 'draft' ? 'draft' : 'active')) body.status = status.value;
    if (review.value !== (n.review_status || 'none')) body.review_status = review.value;
    const ov = owner.getValue(); if ((ov ? ov.id : null) !== (n.owner_id || null)) body.owner_id = ov ? ov.id : null;
    const co = coOwners.getValue().map((x) => x.id); if (co.join() !== (n.co_owners || []).join()) body.co_owners = co;
    if (JSON.stringify(props) !== JSON.stringify(n.props || {})) body.props = props;
    let updated = n;
    if (Object.keys(body).length > 1) updated = await api('PATCH', '/nodes/' + n.id, body);
    const problems = [];
    for (const [i, e] of rels.getValue().entries()) {
      try {
        let other = e.node;
        if (typeof other !== 'string') other = (await api('POST', '/nodes', { type: e.node.new.type, name: e.node.new.name })).id;
        await api('POST', '/edges', { type: e.type, source_id: e.direction === 'out' ? n.id : other, target_id: e.direction === 'out' ? other : n.id, note: e.note });
      } catch (x) { problems.push('Relationship ' + (i + 1) + ': ' + x.message); }
    }
    for (const [i, r] of links.getValue().entries()) { try { await api('POST', '/nodes/' + n.id + '/resources', r); } catch (x) { problems.push('Link ' + (i + 1) + ': ' + x.message); } }
    const want = tagsCb.getValue().map((x) => x.id), have = (n.tags || []).map((t) => t.name);
    for (const t of want.filter((x) => !have.includes(x))) { try { await api('POST', '/nodes/' + n.id + '/tags', { name: t }); } catch (x) { problems.push('Tag ' + t + ': ' + x.message); } }
    for (const t of (n.tags || []).filter((x) => !want.includes(x.name))) { try { await api('DELETE', '/nodes/' + n.id + '/tags/' + t.id); } catch (x) { problems.push('Tag ' + t.name + ': ' + x.message); } }
    closeSheet(true);
    if (problems.length) toast('Saved, but: ' + problems.join('; '), { error: true });
    else toast('Saved');
    const { reloadPanel } = await import('./detail.js'); reloadPanel(true);
    if (S.listReload) S.listReload();
    return updated;
  }

  const foot = [el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => requestCloseSheet() }), el('span', { class: 'spacer' }),
    el('a', { class: 'btn ghost sm', href: '#/guide?s=create', onclick: () => closeSheet(true) }, icon('circle-help', 'sm'), 'How this works'), anotherBtn, submitBtn];
  const sheet = openSheet({ title: editing ? 'Edit ' + typeLabel(typeKey).toLowerCase() : 'New record', body: form, foot, testid: 'record-sheet', isDirty: dirty });
  sheet.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(false); } });
  onTypeChange();
  if (!editing && draft && !o.type && !o.name && (draft.name || draft.summary)) {
    const note = el('div', { class: 'note-box row', style: 'margin:16px 24px 0', 'data-testid': 'draft-restore' }, icon('history', 'sm'),
      el('span', { class: 'spacer', text: 'You have an unsaved draft from ' + new Date(draft.at).toLocaleString() + '.' }),
      el('button', { class: 'btn sm', type: 'button', text: 'Restore', onclick: () => { name.value = draft.name || ''; summary.value = draft.summary || ''; note.remove(); checkName(); } }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Discard', onclick: () => { try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ } note.remove(); } }));
    form.prepend(note);
  }
  changed();
}

// ------------------------------------------------------------------ dialogs used by the detail tabs
export function attachDialog(node, after) {
  const rows = linkRows('attach-rows');
  const err = el('div', { class: 'field-error', role: 'alert' });
  openDialog([el('h2', { text: 'Add links to “' + node.name + '”' }), rows, err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'attach-submit', text: 'Add', onclick: async () => {
        const bad = rows.firstInvalid(); if (bad) { err.textContent = bad.message; return; }
        const vals = rows.getValue(); if (!vals.length) { err.textContent = 'Paste a URL or pick a link from the library.'; return; }
        let n = 0;
        for (const v of vals) { try { await api('POST', '/nodes/' + node.id + '/resources', v); n++; } catch (e) { err.textContent = e.message; if (n === 0) return; } }
        closeDialog(); toast('Added ' + plural(n, 'link')); after();
      } }))], { label: 'Add links', wide: true });
  rows.addRow();
}
export function connectDialog(node, after) {
  const rows = relationshipRows(() => node.type, () => node.name, 'connect-rows');
  const err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'connect-error' });
  openDialog([el('h2', { text: 'Connect “' + node.name + '”' }), rows, err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'connect-submit', text: 'Connect', onclick: async () => {
        const dup = rows.validate(); if (dup) { err.textContent = dup.message; return; }
        const vals = rows.getValue(); if (!vals.length) { err.textContent = 'Choose a relationship and a record.'; return; }
        let n = 0;
        for (const e of vals) {
          try {
            let other = e.node;
            if (typeof other !== 'string') other = (await api('POST', '/nodes', { type: e.node.new.type, name: e.node.new.name })).id;
            await api('POST', '/edges', { type: e.type, source_id: e.direction === 'out' ? node.id : other, target_id: e.direction === 'out' ? other : node.id, note: e.note });
            n++;
          } catch (x) { err.textContent = x.status === 409 ? 'These two records are already connected that way.' : x.message; e._row.classList.add('invalid'); return; }
        }
        closeDialog(); toast('Connected ' + plural(n, 'record')); after();
      } }))], { label: 'Connect records', wide: true });
  rows.addRow();
}
