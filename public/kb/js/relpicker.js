/* Relationship picking, shared by New record, the record panel's Connect and
   the graph (A7, B2). Options read as plain sentences, grouped by direction:
     This course …   "This course contains a live session"
     … this course   "An instructor teaches this course"
   Typing a name that does not exist offers "Create relationship '<name>'":
   admins create it at once, editors create it for immediate use (unreviewed,
   queued in Approvals), contributors propose it. The database enforces the
   same split and refuses near-duplicate names (0029). */
import { S, el, clear, icon, api, toast, typeLabel, combobox, openDialog, closeDialog, can, debounce } from './core.js';
import { loadTypes } from './app.js';

const lower = (k) => typeLabel(k).toLowerCase();
const article = (w) => (/^[aeiou]/i.test(w) ? 'an ' : 'a ') + w;
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
// "related to", "part of", "subject expert for" read as "is related to" in a sentence.
const verb = (label) => (/ (to|of|for|by|with)$/.test(label) && !/^(is|has|belongs|reports|leads|links|refers|maps|points|moves|leads) /.test(label) ? 'is ' + label : label);

/* Every relationship this type can take part in, as sentences. `otherType`
   (optional) keeps only options that reach that type. */
export function relItems(typeKey, otherType) {
  const out = [];
  const me = lower(typeKey);
  S.edgeTypes.filter((et) => !et.archived_at).forEach((et) => (et.rules || []).forEach((r) => {
    const sub = et.review_status === 'unreviewed' ? 'New · awaiting admin review' : null;
    if (r.source === typeKey && (!otherType || r.target === otherType)) {
      out.push({ id: et.key + '|out|' + r.target, type: et.key, direction: 'out', other: r.target, sub, group: 'This ' + me + ' …',
        label: 'This ' + me + ' ' + verb(et.label) + ' ' + article(lower(r.target)), search: et.label + ' ' + (et.inverse_label || '') + ' ' + lower(r.target) });
    }
    if (r.target === typeKey && (!otherType || r.source === otherType) && !(r.source === typeKey && et.key === 'related')) {
      out.push({ id: et.key + '|in|' + r.source, type: et.key, direction: 'in', other: r.source, sub, group: '… this ' + me,
        label: cap(article(lower(r.source))) + ' ' + verb(et.label) + ' this ' + me, search: et.label + ' ' + (et.inverse_label || '') + ' ' + lower(r.source) });
    }
  }));
  return out.sort((a, b) => (a.direction === b.direction ? a.label.localeCompare(b.label) : a.direction === 'out' ? -1 : 1));
}

/* "mentors" -> "mentored by", "teaches" -> "taught by", "prerequisite of" -> "has prerequisite". */
const IRREGULAR = { teach: 'taught', lead: 'led', write: 'written', build: 'built', give: 'given', hold: 'held', make: 'made', run: 'run',
  see: 'seen', take: 'taken', own: 'owned', feed: 'fed', find: 'found', keep: 'kept', buy: 'bought', bring: 'brought', drive: 'driven', choose: 'chosen' };
export function suggestInverse(name) {
  const t = name.trim().replace(/\s+/g, ' ');
  if (!t) return '';
  let m;
  if ((m = /^(.*) by$/i.exec(t))) return m[1].replace(/ed$/, 's');
  if ((m = /^(.*) of$/i.exec(t))) return 'has ' + m[1];
  if ((m = /^(.*) (to|for|with|on|in|from)$/i.exec(t))) return m[2] === 'to' ? 'receives ' + m[1] : m[1] + ' ' + m[2] + ' (inverse)';
  const words = t.split(' '), v = words[0].toLowerCase(), rest = words.slice(1).join(' ');
  const base = /(ch|sh|ss|x)es$/.test(v) ? v.slice(0, -2) : /ies$/.test(v) ? v.slice(0, -3) + 'y' : /s$/.test(v) ? v.slice(0, -1) : v;
  const past = IRREGULAR[base] || (/e$/.test(base) ? base + 'd' : /[^aeiou]y$/.test(base) ? base.slice(0, -1) + 'ied' : base + 'ed');
  return (past + (rest ? ' ' + rest : '') + ' by').trim();
}

/* The picker. o: { typeKey: () => key, otherType: () => key|null, onChange(item|null), testid, value } */
export function relCombobox(o) {
  return combobox({ testid: o.testid || 'rel-type', label: 'Relationship', menuWidth: 380, placeholder: 'Choose or type a relationship…', openOnFocus: true, value: o.value ? [o.value] : [],
    source: async (q) => {
      const items = relItems(o.typeKey(), o.otherType ? o.otherType() : null);
      const ql = q.toLowerCase();
      return q ? items.filter((it) => (it.label + ' ' + it.search).toLowerCase().includes(ql)) : items;
    },
    create: can('contributor') ? (q) => (relItems(o.typeKey()).some((it) => it.search.split(' ')[0].toLowerCase() === q.toLowerCase()) ? []
      : [{ id: 'new-rel:' + q, label: 'Create relationship “' + q + '”', name: q }]) : null,
    onCreateRequest: (it, done) => createRelationshipType({ name: it.name, sourceType: o.typeKey(), targetType: o.otherType ? o.otherType() : null })
      .then((made) => { if (!made) return done(null); const pick = relItems(o.typeKey()).find((x) => x.type === made.key); done(pick || null); if (pick && o.onChange) o.onChange(pick); }),
    onChange: o.onChange });
}

/* The "Create relationship" dialog. Resolves with the new edge type (admin,
   editor) or null (contributor proposal, cancel). */
export function createRelationshipType(o) {
  return new Promise((resolve) => {
    let inverseTouched = false, done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const name = el('input', { value: o.name || '', 'aria-label': 'Relationship name', 'data-testid': 'newrel-name', placeholder: 'e.g. mentors' });
    const inverse = el('input', { value: suggestInverse(o.name || ''), 'aria-label': 'Read the other way', 'data-testid': 'newrel-inverse', placeholder: 'e.g. mentored by' });
    const typeSel = (val, testid, label) => el('select', { 'aria-label': label, 'data-testid': testid },
      S.types.filter((t) => !t.archived_at).map((t) => el('option', { value: t.key, text: t.label, selected: t.key === val })));
    const src = typeSel(o.sourceType, 'newrel-source', 'From type'), tgt = typeSel(o.targetType || o.sourceType, 'newrel-target', 'To type');
    const preview = el('p', { class: 'note-box', 'data-testid': 'newrel-preview' });
    const dup = el('div', { 'data-testid': 'newrel-duplicate' });
    const err = el('div', { class: 'field-error', role: 'alert' });
    const save = el('button', { class: 'btn primary', type: 'button', 'data-testid': 'newrel-save', text: can('admin') ? 'Create relationship' : can('editor') ? 'Create (admin reviews later)' : 'Propose relationship' });
    const draw = () => {
      const n = name.value.trim() || '…', inv = inverse.value.trim() || '…';
      preview.textContent = cap(article(lower(src.value))) + ' ' + n + ' ' + article(lower(tgt.value)) + '; read the other way, ' + article(lower(tgt.value)) + ' is ' + inv + ' ' + article(lower(src.value)) + '.';
    };
    const check = debounce(async () => {
      clear(dup);
      if (!name.value.trim()) return;
      try {
        const r = await api('GET', '/types/edge-similar?label=' + encodeURIComponent(name.value.trim()) + '&inverse_label=' + encodeURIComponent(inverse.value.trim()));
        if (r.existing) showDuplicate(r.existing);
      } catch (e) { /* the save re-checks */ }
    }, 250);
    function showDuplicate(x) {
      clear(dup).appendChild(el('div', { class: 'note-box warn row wrap' }, icon('triangle-alert', 'sm'),
        el('span', null, 'Already exists: ', el('strong', { text: x.label }), x.inverse_label ? ' (other way: ' + x.inverse_label + ')' : '', '.'),
        el('span', { class: 'spacer' }), el('button', { class: 'btn sm', type: 'button', 'data-testid': 'newrel-use-existing', text: 'Use “' + x.label + '”',
          onclick: () => { closeDialog(); finish(S.edgeTypes.find((e) => e.key === x.key) || null); } })));
      save.disabled = true;
    }
    name.addEventListener('input', () => { if (!inverseTouched) inverse.value = suggestInverse(name.value); save.disabled = false; draw(); check(); });
    inverse.addEventListener('input', () => { inverseTouched = true; save.disabled = false; draw(); check(); });
    [src, tgt].forEach((s) => s.addEventListener('change', draw));
    save.addEventListener('click', async () => {
      err.textContent = '';
      if (!name.value.trim()) { err.textContent = 'Give the relationship a name.'; name.focus(); return; }
      save.disabled = true;
      try {
        const made = await api('POST', '/types/edge', { label: name.value.trim(), inverse_label: inverse.value.trim() || null, rules: [{ source: src.value, target: tgt.value }] });
        await loadTypes();
        closeDialog();
        toast(made.review_status === 'unreviewed' ? 'Created “' + made.label + '”; you can use it now, and an admin will review it' : 'Created “' + made.label + '”');
        finish(made);
      } catch (e) {
        save.disabled = false;
        if (e.status === 202) { closeDialog(); toast('Proposed “' + name.value.trim() + '”; an admin reviews it in Approvals'); finish(null); return; }
        if (e.status === 409 && e.body && e.body.existing) showDuplicate(e.body.existing);
        else err.textContent = e.message;
      }
    });
    draw();
    openDialog([el('h2', { text: 'New relationship type' }),
      el('p', { class: 'muted small', text: can('admin') ? 'Available to everyone straight away.' : can('editor') ? 'You can use it straight away; an admin confirms, renames or merges it.' : 'An admin reviews your proposal before anyone can use it.' }),
      el('label', { class: 'field' }, el('span', { class: 'label', text: 'Name' }), name),
      el('label', { class: 'field' }, el('span', { class: 'label', text: 'Read the other way' }), inverse, el('span', { class: 'help', text: 'Suggested from the name; change it if it reads oddly.' })),
      el('div', { class: 'grid-2' }, el('label', { class: 'field' }, el('span', { class: 'label', text: 'From' }), src), el('label', { class: 'field' }, el('span', { class: 'label', text: 'To' }), tgt)),
      preview, dup, err,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => { closeDialog(); finish(null); } }), save)],
    { label: 'New relationship type', testid: 'newrel-dialog', stack: true });
    check();
  });
}
