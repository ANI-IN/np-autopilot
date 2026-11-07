/* Settings: Types (record types with fields, placement rules, live form
   preview), Relationship types, Link kinds, Members, API tokens, Templates.
   Admins apply type changes; an editor's change becomes a proposal. */
import { S, el, add, $, $$, clear, icon, typeIcon, typeLabel, api, toast, failToast, avatar, personName, ago, skeletonRows, empty, errorBox,
  can, openSheet, closeSheet, openDialog, closeDialog, confirmDialog, plural, you, setQuery, qs } from '../core.js';
import { pageHead } from '../page.js';
import { fieldInput } from '../form.js';
import { loadTypes, refreshCounts } from '../app.js';
import { kindLabel } from '../detail.js';
import { peopleTab } from './people.js';             // B1 (run 6): Settings -> People

const TABS = [['types', 'Record types'], ['relationships', 'Relationship types'], ['links', 'Link kinds'], ['tags', 'Tags'], ['members', 'Members'], ['people', 'People'], ['tokens', 'API tokens'], ['templates', 'Templates'], ['sync', 'Sync']];
const ICONS = ['box', 'book-open', 'graduation-cap', 'layers', 'calendar-days', 'radio', 'lightbulb', 'circle-user', 'workflow', 'compass', 'briefcase', 'puzzle', 'target',
  'clipboard-list', 'file-text', 'presentation', 'notebook-pen', 'list-checks', 'scroll-text', 'book-marked', 'film', 'mic-vocal', 'star', 'flag', 'shapes', 'hash', 'inbox'];
const FIELD_KIND_LABEL = { short_text: 'Short text', long_text: 'Long text', number: 'Number', date: 'Date', datetime: 'Date and time', duration: 'Duration (minutes)',
  url: 'URL', single_select: 'Single select', multi_select: 'Multi select', person: 'Person', reference: 'Record reference', checkbox: 'Checkbox' };

export function viewSettings(v, r) {
  const visible = TABS.filter(([k]) => (k !== 'members' && k !== 'sync') || can('admin'));   // an admin-only tab by link: show Types (B5)
  const tab = visible.some(([k]) => k === r.q.tab) ? r.q.tab : 'types';
  v.appendChild(pageHead({ title: 'Settings', sub: 'Your role is ' + S.me.role + '.' }));
  v.appendChild(el('div', { class: 'tabs', role: 'tablist' }, TABS.filter(([k]) => (k !== 'members' && k !== 'sync' && k !== 'people') || can('admin')).map(([k, l]) =>
    el('a', { href: '#/settings?tab=' + k, role: 'tab', 'aria-selected': k === tab ? 'true' : 'false', 'data-testid': 'settings-tab-' + k, text: l }))));
  const body = el('div', { class: 'page-body settings-body' });
  v.appendChild(body);
  ({ types: typesTab, relationships: relTab, links: linksTab, tags: tagsTab, members: membersTab, people: peopleTab, tokens: tokensTab, templates: templatesTab, sync: syncTab })[tab](body);
  S.onQueryChange = (nr) => { if ((nr.q.tab || '') !== (r.q.tab || '')) { clear(v); viewSettings(v, nr); } };
}
const reloadSettings = async () => { await loadTypes(); const { rerender } = await import('../app.js'); rerender(); };
function proposalOr(e, okMsg) {
  if (e && e.status === 202) { toast('Sent to an admin for approval (Approvals).'); closeSheet(true); closeDialog(); return true; }
  return false;
}

// ------------------------------------------------------------------ record types
function typesTab(body) {
  add(body, [el('div', { class: 'tab-intro' }, el('p', { text: can('admin') ? 'Add types and fields; they appear in the New record form, tables, filters, search, the graph, CSV and the AI tools.' : can('editor') ? 'Editors can propose type changes; an admin approves them in Approvals.' : 'Only admins change types.' }),
    can('editor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-type', onclick: () => typeEditor(null) }, icon('plus'), 'New record type') : null)]);
  const ul = el('ul', { class: 'list bordered', 'data-testid': 'types' });
  api('GET', '/types?archived=1').then((t) => {
    t.node_types.forEach((x) => ul.appendChild(el('li', { 'data-testid': 'type-row' }, el('div', { class: 'link-row roomy' },
      el('span', { class: 'type-icon', style: '--type:' + x.color }, icon(x.icon || 'box')), el('strong', { text: x.label }), el('span', { class: 'faint xs mono', text: x.key }),
      x.is_core ? el('span', { class: 'badge', text: 'Built-in' }) : null, x.archived_at ? el('span', { class: 'badge danger', text: 'Archived' }) : null,
      el('span', { class: 'faint xs truncate grow', text: (x.fields.filter((f) => !f.archived).length ? plural(x.fields.filter((f) => !f.archived).length, 'field') + ' · ' : '') + plural(x.records, 'record') }),
      can('editor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'edit-type-' + x.key, onclick: () => typeEditor(x) }, 'Edit') : null))));
  }).catch((e) => body.appendChild(errorBox(e)));
  body.appendChild(ul);
}

function typeEditor(t) {
  const isNew = !t;
  t = t || { label: '', plural: '', description: '', icon: 'box', color: S.palette[0], fields: [], allowed_parents: [], parent_required: false, default_status: 'active', owner_rule: 'creator', is_container: false };
  const fields = JSON.parse(JSON.stringify(t.fields || []));
  let icon_ = t.icon || 'box', color = t.color;
  const label = el('input', { value: t.label, 'data-testid': 'type-label', 'aria-label': 'Name', maxlength: '80', autofocus: true });
  const pluralIn = el('input', { value: t.plural || '', 'data-testid': 'type-plural', 'aria-label': 'Plural', maxlength: '80' });
  const desc = el('input', { value: t.description || '', 'aria-label': 'Description', maxlength: '500', placeholder: 'One line, shown in the New record form' });
  const iconGrid = el('div', { class: 'row wrap gap-1', 'data-testid': 'type-icons' });
  const drawIcons = () => { clear(iconGrid); ICONS.forEach((n) => iconGrid.appendChild(el('button', { type: 'button', class: 'btn sm icon' + (n === icon_ ? ' primary' : ''), 'aria-label': 'Icon ' + n, 'aria-pressed': n === icon_ ? 'true' : 'false', onclick: () => { icon_ = n; drawIcons(); preview(); } }, icon(n, 'sm')))); };
  const swatches = el('div', { class: 'row gap-2', 'data-testid': 'type-colors' });
  const drawSw = () => { clear(swatches); S.palette.forEach((c) => swatches.appendChild(el('button', { type: 'button', class: 'swatch', 'aria-label': 'Colour ' + c, 'aria-pressed': c === color ? 'true' : 'false',
    style: '--sw:' + c, onclick: () => { color = c; drawSw(); preview(); } }))); };
  const parents = el('div', { class: 'row wrap gap-3', 'data-testid': 'type-parents' }, S.types.filter((x) => x.key !== t.key).map((x) =>
    el('label', { class: 'row small gap-1' }, el('input', { type: 'checkbox', value: x.key, checked: (t.allowed_parents || []).includes(x.key) }), typeIcon(x.key, 'sm'), x.label)));
  const parentReq = el('input', { type: 'checkbox', checked: !!t.parent_required, 'aria-label': 'Must be placed under a parent' });
  const defStatus = el('select', { 'aria-label': 'Default status' }, el('option', { value: 'active', text: 'Live', selected: t.default_status !== 'draft' }), el('option', { value: 'draft', text: 'Draft', selected: t.default_status === 'draft' }));
  const ownerRule = el('select', { 'aria-label': 'Owner rule' }, el('option', { value: 'creator', text: 'The creator owns it', selected: t.owner_rule !== 'none' }), el('option', { value: 'none', text: 'No owner until assigned', selected: t.owner_rule === 'none' }));
  const container = el('input', { type: 'checkbox', checked: !!t.is_container, 'aria-label': 'Other records can live inside it (like a course)' });
  // B1 (run 6): "owner expected" decides whether "No owner" counts this type (admins change it)
  const ownerExpected = el('input', { type: 'checkbox', checked: isNew ? false : !!t.owner_expected, disabled: !can('admin'), 'data-testid': 'type-owner-expected', 'aria-label': 'Records of this type should have an owner' });
  const fieldList = el('div', { class: 'col', 'data-testid': 'type-fields' });
  const previewBox = el('div', { class: 'col gap-3', 'data-testid': 'type-preview' });
  const err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'type-error' });

  function drawFields() {
    clear(fieldList);
    fields.forEach((f, i) => {
      const lab = el('input', { value: f.label || '', placeholder: 'Field label', 'aria-label': 'Field label', 'data-testid': 'field-label', class: 'grow' });
      lab.addEventListener('input', () => { f.label = lab.value; preview(); });
      const kind = el('select', { 'aria-label': 'Field kind', 'data-testid': 'field-kind' }, S.fieldKinds.map((k) => el('option', { value: k, text: FIELD_KIND_LABEL[k] || k, selected: f.kind === k })));
      kind.addEventListener('change', () => { f.kind = kind.value; drawFields(); preview(); });
      const req = el('input', { type: 'checkbox', checked: !!f.required, 'aria-label': 'Required', 'data-testid': 'field-required' });
      req.addEventListener('change', () => { f.required = req.checked; preview(); });
      const help = el('input', { value: f.help || '', placeholder: 'Help text (optional)', 'aria-label': 'Help text' });
      help.addEventListener('input', () => { f.help = help.value; preview(); });
      const extra = el('div');
      if (f.kind === 'single_select' || f.kind === 'multi_select') {
        const opts = el('input', { value: (f.options || []).map((o) => (o.label || o.value)).join(', '), placeholder: 'Options, comma separated', 'aria-label': 'Options', 'data-testid': 'field-options', class: 'w-full' });
        opts.addEventListener('input', () => { const old = f.options || []; f.options = opts.value.split(',').map((s) => s.trim()).filter(Boolean).map((l) => { const ex = old.find((o) => o.label === l || o.value === l); return ex || { value: l.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || l, label: l }; }); preview(); });
        extra.appendChild(opts);
      }
      if (f.kind === 'reference') {
        extra.appendChild(el('div', { class: 'row wrap' }, el('span', { class: 'faint xs', text: 'May point at:' }), S.types.map((x) => {
          const c = el('input', { type: 'checkbox', checked: (f.ref_types || []).includes(x.key), 'aria-label': x.label });
          c.addEventListener('change', () => { f.ref_types = (f.ref_types || []).filter((k) => k !== x.key).concat(c.checked ? [x.key] : []); preview(); });
          return el('label', { class: 'row xs gap-1' }, c, x.label);
        })));
      }
      const def = f.kind === 'checkbox' || f.kind === 'reference' || f.kind === 'person' ? null : el('input', { value: f.default === undefined ? '' : String(f.default), placeholder: 'Default (optional)', 'aria-label': 'Default value', class: 'input-sm' });
      if (def) def.addEventListener('input', () => { const val = def.value.trim(); if (!val) delete f.default; else f.default = f.kind === 'number' || f.kind === 'duration' ? Number(val) : val; });
      fieldList.appendChild(el('div', { class: 'field-card' + (f.archived ? ' archived' : ''), 'data-testid': 'field-row' },
        el('div', { class: 'row' }, lab, kind, el('label', { class: 'row small gap-1' }, req, 'Required'),
          f.key ? el('span', { class: 'faint xs mono', title: 'Internal key — never changes', text: f.key }) : null,
          el('button', { class: 'btn ghost sm', type: 'button', 'data-testid': 'field-remove', text: f.key && !isNew ? (f.archived ? 'Restore' : 'Archive') : 'Remove',
            onclick: () => { if (f.key && !isNew) f.archived = !f.archived; else fields.splice(i, 1); drawFields(); preview(); } })),
        el('div', { class: 'row' }, help, def), extra));
    });
    fieldList.appendChild(el('button', { class: 'btn ghost sm self-start', type: 'button', 'data-testid': 'add-field', onclick: () => { fields.push({ label: '', kind: 'short_text', required: false }); drawFields(); const ls = $$('[data-testid=field-label]', fieldList); ls[ls.length - 1].focus(); } }, icon('plus', 'sm'), 'Add field'));
  }
  function preview() {
    clear(previewBox);
    previewBox.appendChild(el('div', { class: 'row' }, el('span', { class: 'type-icon', style: '--type:' + color }, icon(icon_, 'lg')), el('strong', { text: 'New ' + (label.value.trim() || 'record').toLowerCase() })));
    previewBox.appendChild(el('label', { class: 'field' }, el('span', { class: 'label req', text: 'Name' }), el('input', { disabled: true })));
    fields.filter((f) => !f.archived && f.label).forEach((f) => previewBox.appendChild(el('div', { class: 'field' }, el('span', { class: 'label' + (f.required ? ' req' : ''), text: f.label }),
      fieldInput(Object.assign({ key: 'preview_' + Math.random().toString(36).slice(2), options: [], ref_types: [] }, f), f.default, () => {}), f.help ? el('span', { class: 'help', text: f.help }) : null)));
  }
  label.addEventListener('input', () => { if (isNew && !pluralIn.dataset.touched) pluralIn.value = label.value.trim() ? label.value.trim() + 's' : ''; preview(); });
  pluralIn.addEventListener('input', () => { pluralIn.dataset.touched = '1'; });
  drawIcons(); drawSw(); drawFields();
  const fr = (l, input, help) => el('label', { class: 'field' }, el('span', { class: 'label', text: l }), input, help ? el('span', { class: 'help', text: help }) : null);
  const form = el('div', { class: 'type-editor' },
    el('div', { class: 'editor-main' },
      el('div', { class: 'form-section' }, el('div', { class: 'grid-2' }, fr('Name', label), fr('Plural', pluralIn)), fr('Description', desc), fr('Icon', iconGrid), fr('Colour', swatches, 'Used for the icon and dot only.')),
      el('div', { class: 'form-section' }, el('h3', { text: 'Fields' }), el('p', { class: 'faint xs', text: 'Keys are permanent. Archiving a field hides it and keeps its data. Changing a kind is allowed only if every existing value converts.' }), fieldList),
      el('div', { class: 'form-section' }, el('h3', { text: 'Placement and defaults' }), fr('Can be placed under', parents), el('label', { class: 'row small' }, parentReq, 'Must be placed under one of them'),
        el('label', { class: 'row small' }, container, 'Other records can live inside it (like a course)'),
        el('label', { class: 'row small' }, ownerExpected, 'Records of this type should have an owner (counted under “No owner” on Data quality)'),
        el('div', { class: 'grid-2' }, fr('Default status', defStatus), fr('Owner', ownerRule))),
      el('div', { class: 'editor-error' }, err)),
    el('div', { class: 'form-section editor-preview' }, el('h3', { text: 'Preview of the form' }), previewBox));
  preview();
  const save = el('button', { class: 'btn primary', type: 'button', 'data-testid': 'type-save', text: isNew ? (can('admin') ? 'Create type' : 'Propose type') : (can('admin') ? 'Save' : 'Propose change'), onclick: async () => {
    err.textContent = '';
    const body = { label: label.value.trim(), plural: pluralIn.value.trim() || undefined, description: desc.value.trim() || null, icon: icon_, color,
      fields: fields.filter((f) => f.label && f.label.trim()), allowed_parents: $$('input:checked', parents).map((c) => c.value), parent_required: parentReq.checked,
      default_status: defStatus.value, owner_rule: ownerRule.value, is_container: container.checked };
    if (can('admin')) body.owner_expected = ownerExpected.checked;   // B1 (run 6)
    try {
      const out = isNew ? await api('POST', '/types/node', body) : await api('PATCH', '/types/node/' + t.key, Object.assign({ version: t.version }, body));
      closeSheet(true); toast(isNew ? 'Created the “' + out.label + '” type' : 'Saved' + (out.converted_records ? ' — converted ' + plural(out.converted_records, 'record') : ''));
      (out.warnings || []).forEach((w) => toast(w, { ms: 9000 }));
      await reloadSettings();
    } catch (e) {
      if (proposalOr(e)) return;
      err.textContent = e.message + (e.body.failures ? ' — ' + e.body.failures.slice(0, 5).map((f) => (f.name || f.relationship) + (f.value !== undefined ? ' (' + JSON.stringify(f.value) + ')' : '') + (f.why ? ': ' + f.why : '')).join('; ') : '');
      if (e.body.failures && e.body.failures.some((f) => /replacement/.test(f.why || ''))) replacementsDialog(t, fields, body, e.body.failures);
    } } });
  const foot = [el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => closeSheet() }), el('span', { class: 'spacer' }),
    !isNew && !t.is_core && !t.archived_at && can('editor') ? el('button', { class: 'btn danger', type: 'button', 'data-testid': 'type-archive', text: 'Archive type', onclick: () => archiveType(t) }) : null,
    !isNew && t.archived_at && can('editor') ? el('button', { class: 'btn', type: 'button', text: 'Restore type', onclick: async () => { try { await api('POST', '/types/node/' + t.key + '/restore'); closeSheet(true); await reloadSettings(); } catch (e) { if (!proposalOr(e)) failToast(e); } } }) : null,
    !isNew && can('editor') ? el('button', { class: 'btn', type: 'button', 'data-testid': 'type-duplicate', text: 'Duplicate', onclick: async () => { try { await api('POST', '/types/node/' + t.key + '/duplicate'); closeSheet(true); toast('Duplicated'); await reloadSettings(); } catch (e) { if (!proposalOr(e)) failToast(e); } } }) : null,
    save];
  const sheet = openSheet({ title: isNew ? 'New record type' : 'Edit “' + t.label + '”', body: form, foot, testid: 'type-sheet', help: 'types' });
  sheet.classList.add('full');
}
function replacementsDialog(t, fields, body, failures) {
  const byField = {};
  failures.filter((f) => /replacement/.test(f.why || '')).forEach((f) => { (byField[f.field] = byField[f.field] || new Set()).add(f.value); });
  const selects = [];
  const rows = Object.entries(byField).map(([label, vals]) => {
    const fdef = fields.find((x) => x.label === label);
    return Array.from(vals).map((old) => { const s = el('select', { 'aria-label': 'Replace ' + old }, (fdef.options || []).map((o) => el('option', { value: o.value, text: o.label }))); selects.push([fdef.key, old, s]); return el('div', { class: 'row small' }, el('span', { class: 'grow', text: label + ': “' + old + '” → ' }), s); });
  });
  openDialog([el('h2', { text: 'Choose replacements' }), el('p', { class: 'muted small', text: 'These options are in use. Records holding them get the replacement you choose.' }), rows,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', text: 'Replace and save', onclick: async () => {
        const replacements = {}; selects.forEach(([k, old, s]) => { (replacements[k] = replacements[k] || {})[old] = s.value; });
        try { await api('PATCH', '/types/node/' + t.key, Object.assign({ version: t.version, replacements }, body)); closeDialog(); closeSheet(true); toast('Saved'); await reloadSettings(); }
        catch (e) { if (!proposalOr(e)) failToast(e); } } }))], { label: 'Replacements' });
}
async function archiveType(t) {
  if (t.records) {
    const to = el('select', { 'aria-label': 'Move records to', 'data-testid': 'change-type-to' }, S.types.filter((x) => x.key !== t.key).map((x) => el('option', { value: x.key, text: x.label })));
    const mapBox = el('div', { class: 'col' });
    const drawMap = () => {
      clear(mapBox);
      const dst = S.typeByKey[to.value];
      (t.fields || []).filter((f) => !f.archived).forEach((f) => {
        const s = el('select', { 'aria-label': 'Map ' + f.label, 'data-key': f.key }, el('option', { value: '', text: 'Drop this value' }), (dst.fields || []).filter((g) => !g.archived).map((g) => el('option', { value: g.key, text: g.label, selected: g.key === f.key || g.label === f.label })));
        mapBox.appendChild(el('div', { class: 'row small' }, el('span', { class: 'grow', text: f.label + ' →' }), s));
      });
      if (!mapBox.children.length) mapBox.appendChild(el('p', { class: 'faint small', text: 'This type has no fields to map.' }));
    };
    to.addEventListener('change', drawMap); drawMap();
    openDialog([el('h2', { text: 'Change type of ' + plural(t.records, 'record') }), el('p', { class: 'muted small', text: '“' + t.label + '” is used by ' + plural(t.records, 'record') + '. Move them to another type first; then the type can be archived.' }),
      el('label', { class: 'field' }, el('span', { class: 'label', text: 'Move to' }), to), el('h3', { text: 'Field mapping' }), mapBox,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', 'data-testid': 'change-type-go', text: 'Move ' + plural(t.records, 'record'), onclick: async () => {
          const field_map = {}; $$('select[data-key]', mapBox).forEach((s) => { field_map[s.dataset.key] = s.value || null; });
          try { const out = await api('POST', '/types/node/' + t.key + '/change-type', { to: to.value, field_map }); closeDialog(); toast('Moved ' + plural(out.moved, 'record') + '. You can archive the type now.'); t.records = 0; refreshCounts(); }
          catch (e) { if (!proposalOr(e)) failToast(e, 'Not moved'); } } }))], { label: 'Change type', wide: true });
    return;
  }
  const ok = await confirmDialog({ title: 'Archive the “' + t.label + '” type?', body: 'It disappears from the New record form. Nothing is deleted; you can restore it.', confirmLabel: 'Archive', danger: true });
  if (!ok) return;
  try { await api('POST', '/types/node/' + t.key + '/archive'); closeSheet(true); toast('Archived'); await reloadSettings(); } catch (e) { if (!proposalOr(e)) failToast(e); }
}

// ------------------------------------------------------------------ relationship types
function relTab(body) {
  add(body, el('div', { class: 'tab-intro' }, el('p', { text: 'What can be connected to what. Removing an allowed pair never deletes existing relationships; they are listed on Data quality.' }),
    can('contributor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-edge-type', onclick: () => edgeEditor(null) }, icon('plus'), can('editor') ? 'New relationship type' : 'Propose relationship type') : null));
  const ul = el('ul', { class: 'list bordered' });
  ul.setAttribute('data-testid', 'edge-types');
  api('GET', '/types').then((t) => t.edge_types.forEach((x) => ul.appendChild(el('li', { 'data-testid': 'edge-type-row', 'data-key': x.key }, el('div', { class: 'link-row roomy start' },
    el('div', { class: 'col gap-xs grow' }, el('div', { class: 'row' }, el('strong', { text: x.label }), x.inverse_label ? el('span', { class: 'faint xs', text: '/ ' + x.inverse_label }) : null,
      x.is_core ? el('span', { class: 'badge', text: 'Built-in' }) : null, x.review_status === 'unreviewed' ? el('span', { class: 'badge warn', 'data-testid': 'edge-unreviewed', text: 'Awaiting review' }) : null,
      x.cardinality !== 'many_to_many' ? el('span', { class: 'badge', text: x.cardinality.replace(/_/g, ' ') }) : null),
      el('div', { class: 'faint xs', text: x.rules.map((r) => typeLabel(r.source) + ' → ' + typeLabel(r.target)).join(' · ') })),
    el('span', { class: 'faint xs', text: plural(x.edges, 'use') }),
    can('editor') ? el('button', { class: 'btn sm', type: 'button', onclick: () => edgeEditor(x) }, 'Edit') : null,
    can('admin') && !x.is_core ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'edge-merge', onclick: () => mergeDialog(x, t.edge_types) }, icon('git-merge', 'sm'), 'Merge…') : null,
    can('admin') && !x.is_core ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'edge-archive', onclick: () => archiveEdgeType(x, t.edge_types) }, icon('archive', 'sm'), 'Archive') : null))))).catch((e) => body.appendChild(errorBox(e)));
  body.appendChild(ul);
}
/* Merge (B2): every relationship moves to the kept type; a pair that already
   holds the kept type keeps one. The preview counts first; the merge is one
   audited transaction. */
export function mergeDialog(x, all, after) {
  const keep = el('select', { 'aria-label': 'Merge into', 'data-testid': 'merge-into' }, all.filter((e) => e.key !== x.key && !e.archived_at).map((e) => el('option', { value: e.key, text: e.label + (e.inverse_label ? ' / ' + e.inverse_label : '') })));
  const flip = el('input', { type: 'checkbox', 'aria-label': 'Reverse direction', 'data-testid': 'merge-flip' });
  const prev = el('p', { class: 'note-box', 'data-testid': 'merge-preview', text: 'Counting…' });
  const err = el('div', { class: 'field-error', role: 'alert' });
  const preview = async () => {
    try { const p = await api('POST', '/types/edge/' + x.key + '/merge', { into: keep.value, flip: flip.checked, preview: true });
      prev.textContent = plural(p.relationships, 'relationship') + ' will move to “' + keep.selectedOptions[0].text + '”' + (p.duplicates ? '; ' + p.duplicates + ' already exist there and will be archived' : '') + '. “' + x.label + '” is then archived.'; }
    catch (e) { prev.textContent = e.message; }
  };
  keep.addEventListener('change', preview); flip.addEventListener('change', preview);
  openDialog([el('h2', { text: 'Merge “' + x.label + '”' }),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Into' }), keep),
    el('label', { class: 'row small' }, flip, 'Reverse the direction (it reads as the other type’s inverse)'), prev, err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'merge-confirm', text: 'Merge', onclick: async () => {
        try { const out = await api('POST', '/types/edge/' + x.key + '/merge', { into: keep.value, flip: flip.checked }); closeDialog();
          toast('Merged: ' + plural(out.moved, 'relationship') + ' moved' + (out.duplicates ? ', ' + out.duplicates + ' duplicate(s) archived' : ''));
          if (after) after(out); else await reloadSettings(); }
        catch (e) { err.textContent = e.message; } } }))], { label: 'Merge relationship type', testid: 'merge-dialog' });
  preview();
}
/* Archive with its dependencies shown first (B2): a type in use is never
   archived silently; the dialog counts what uses it and offers the merge. */
function archiveEdgeType(x, all) {
  if (x.edges) {
    openDialog([el('h2', { text: 'Archive “' + x.label + '”?' }),
      el('p', { class: 'note-box warn', 'data-testid': 'edge-archive-impact', text: plural(x.edges, 'live relationship') + ' use this type. Move them to another type first.' }),
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
        el('button', { class: 'btn primary', type: 'button', text: 'Merge into another type…', onclick: () => { closeDialog(); mergeDialog(x, all); } }))], { label: 'Archive relationship type' });
    return;
  }
  confirmDialog({ title: 'Archive “' + x.label + '”?', body: 'Nothing uses it. It disappears from pickers; its history stays in Activity.', confirmLabel: 'Archive' }).then(async (ok) => {
    if (!ok) return;
    try { await api('POST', '/types/edge/' + x.key + '/archive'); toast('Archived “' + x.label + '”'); await reloadSettings(); } catch (e) { failToast(e, 'Not archived'); }
  });
}
function edgeEditor(x) {
  const isNew = !x;
  x = x || { label: '', inverse_label: '', description: '', cardinality: 'many_to_many', allow_self: false, rules: [] };
  const label = el('input', { value: x.label, 'aria-label': 'Name', 'data-testid': 'edge-label', placeholder: 'e.g. is a prerequisite for' });
  const inv = el('input', { value: x.inverse_label || '', 'aria-label': 'Inverse name', placeholder: 'e.g. requires' });
  const desc = el('input', { value: x.description || '', 'aria-label': 'Description' });
  const card = el('select', { 'aria-label': 'Cardinality' }, [['many_to_many', 'Many to many'], ['one_to_many', 'One to many (a target has one source)'], ['many_to_one', 'Many to one (a source has one target)'], ['one_to_one', 'One to one']].map(([v, l]) => el('option', { value: v, text: l, selected: v === x.cardinality })));
  const self = el('input', { type: 'checkbox', checked: !!x.allow_self, 'aria-label': 'Allow self-links' });
  const rules = el('div', { class: 'col', 'data-testid': 'edge-rules' });
  const addRule = (r) => { const s = el('select', { 'aria-label': 'Source type' }, S.types.map((t) => el('option', { value: t.key, text: t.label, selected: r && r.source === t.key })));
    const tg = el('select', { 'aria-label': 'Target type' }, S.types.map((t) => el('option', { value: t.key, text: t.label, selected: r && r.target === t.key })));
    const row = el('div', { class: 'row', 'data-rule': '1' }, s, el('span', { class: 'faint', text: '→' }), tg, el('button', { class: 'btn ghost sm icon', type: 'button', 'aria-label': 'Remove pair', onclick: () => row.remove() }, icon('x', 'sm')));
    rules.insertBefore(row, addBtn); };
  const addBtn = el('button', { class: 'btn ghost sm self-start', type: 'button', onclick: () => addRule(null) }, icon('plus', 'sm'), 'Add allowed pair');
  rules.appendChild(addBtn);
  (x.rules.length ? x.rules : [null]).forEach(addRule);
  const err = el('div', { class: 'field-error', role: 'alert' });
  openDialog([el('h2', { text: isNew ? 'New relationship type' : 'Edit “' + x.label + '”' }),
    el('div', { class: 'grid-2' }, el('label', { class: 'field' }, el('span', { class: 'label', text: 'Name' }), label), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Inverse name' }), inv)),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Description' }), desc), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Cardinality' }), card),
    el('label', { class: 'row small' }, self, 'A record may point at itself'), el('h3', { text: 'Allowed source → target' }), rules, err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'edge-save', text: can('admin') ? 'Save' : 'Propose', onclick: async () => {
        const body = { label: label.value.trim(), inverse_label: inv.value.trim() || null, description: desc.value.trim() || null, cardinality: card.value, allow_self: self.checked,
          rules: $$('[data-rule]', rules).map((r) => { const [s, t] = $$('select', r); return { source: s.value, target: t.value }; }) };
        try { const out = isNew ? await api('POST', '/types/edge', body) : await api('PATCH', '/types/edge/' + x.key, Object.assign({ version: x.version }, body));
          closeDialog(); toast('Saved'); (out.warnings || []).forEach((w) => toast(w, { ms: 9000 })); await reloadSettings(); }
        catch (e) { if (!proposalOr(e)) err.textContent = e.message; } } }))], { label: 'Relationship type', wide: true });
}

// ------------------------------------------------------------------ link kinds
function linksTab(body) {
  add(body, el('div', { class: 'tab-intro' }, el('p', { text: 'Where links live. A pasted URL is matched against these patterns, in order, to pick the icon and default kind.' }),
    can('editor') ? el('button', { class: 'btn primary', type: 'button', 'data-testid': 'new-link-kind', onclick: () => linkEditor(null) }, icon('plus'), 'New link kind') : null));
  const ul = el('ul', { class: 'list bordered', 'data-testid': 'link-kinds' });
  S.linkKinds.forEach((x) => ul.appendChild(el('li', null, el('div', { class: 'link-row roomy' }, icon(x.icon), el('strong', { text: x.label }), x.is_core ? el('span', { class: 'badge', text: 'Built-in' }) : null,
    el('span', { class: 'faint xs mono truncate grow', text: (x.patterns || []).join('  ·  ') || 'everything else' }),
    x.defaults && x.defaults.kind ? el('span', { class: 'badge', text: kindLabel(x.defaults.kind) }) : null,
    can('editor') ? el('button', { class: 'btn sm', type: 'button', onclick: () => linkEditor(x) }, 'Edit') : null))));
  body.appendChild(ul);
}
function linkEditor(x) {
  const isNew = !x;
  x = x || { label: '', icon: 'link', patterns: [], defaults: {} };
  const label = el('input', { value: x.label, 'aria-label': 'Name', 'data-testid': 'link-kind-label' });
  const ic = el('select', { 'aria-label': 'Icon' }, ['link', 'globe', 'folder', 'file', 'file-text', 'file-spreadsheet', 'presentation', 'github', 'youtube', 'video', 'radio', 'graduation-cap', 'notebook-pen', 'book-open'].map((n) => el('option', { value: n, text: n, selected: n === x.icon })));
  const pats = el('textarea', { rows: '3', 'aria-label': 'URL patterns', 'data-testid': 'link-kind-patterns', placeholder: '^https?://(www\\.)?notion\\.so/' }, (x.patterns || []).join('\n'));
  const def = el('select', { 'aria-label': 'Default kind' }, el('option', { value: '', text: '—' }), S.resourceKinds.map((k) => el('option', { value: k, text: kindLabel(k), selected: x.defaults && x.defaults.kind === k })));
  const err = el('div', { class: 'field-error', role: 'alert' });
  openDialog([el('h2', { text: isNew ? 'New link kind' : 'Edit “' + x.label + '”' }), el('div', { class: 'grid-2' }, el('label', { class: 'field' }, el('span', { class: 'label', text: 'Name' }), label), el('label', { class: 'field' }, el('span', { class: 'label', text: 'Icon' }), ic)),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'URL patterns' }), pats, el('span', { class: 'help', text: 'One regular expression per line, matched against the full URL.' })),
    el('label', { class: 'field' }, el('span', { class: 'label', text: 'Default kind' }), def), err,
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
      !isNew && !x.is_core && can('editor') ? el('button', { class: 'btn danger', type: 'button', text: 'Archive', onclick: async () => { try { await api('POST', '/types/link/' + x.key + '/archive'); closeDialog(); await reloadSettings(); } catch (e) { if (!proposalOr(e)) err.textContent = e.message; } } }) : null,
      el('button', { class: 'btn primary', type: 'button', 'data-testid': 'link-kind-save', text: can('admin') ? 'Save' : 'Propose', onclick: async () => {
        const body = { label: label.value.trim(), icon: ic.value, patterns: pats.value.split('\n').map((s) => s.trim()).filter(Boolean), defaults: def.value ? { kind: def.value } : {} };
        try { if (isNew) await api('POST', '/types/link', body); else await api('PATCH', '/types/link/' + x.key, Object.assign({ version: x.version }, body)); closeDialog(); toast('Saved'); await reloadSettings(); }
        catch (e) { if (!proposalOr(e)) err.textContent = e.message; } } }))], { label: 'Link kind' });
}

// ------------------------------------------------------------------ members, tokens, templates
// ------------------------------------------------------------------ tags (B2)
/* Rename, merge into another tag, archive (shows how many records carry it;
   Undo puts it back on them). */
function tagsTab(body) {
  body.appendChild(el('div', { class: 'tab-intro' }, el('p', { text: 'Tags are added on records. Here an editor renames them, merges duplicates, or archives one: its records simply lose the tag.' })));
  const ul = el('ul', { class: 'list bordered', 'data-testid': 'tags' });
  body.appendChild(ul);
  const reload = () => { clear(body); tagsTab(body); };
  api('GET', '/tags').then((t) => {
    if (!t.items.length) ul.appendChild(el('li', { class: 'link-row faint', text: 'No tags yet.' }));
    t.items.forEach((x) => ul.appendChild(el('li', { 'data-testid': 'tag-row', 'data-name': x.name }, el('div', { class: 'link-row roomy' },
      icon('tag'), el('strong', { text: '#' + x.name }), el('span', { class: 'faint xs grow', text: plural(x.used_by, 'record') }),
      can('editor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'tag-rename', text: 'Rename', onclick: () => {
        const name = el('input', { value: x.name, 'aria-label': 'Tag name', 'data-testid': 'tag-name' });
        const err = el('div', { class: 'field-error', role: 'alert' });
        openDialog([el('h2', { text: 'Rename #' + x.name }), name, err, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
          el('button', { class: 'btn primary', type: 'button', 'data-testid': 'tag-rename-save', text: 'Rename', onclick: async () => {
            try { await api('PATCH', '/tags/' + x.id, { version: x.version, name: name.value.trim() }); closeDialog(); toast('Renamed'); reload(); } catch (e) { err.textContent = e.message; } } }))], { label: 'Rename tag' });
      } }) : null,
      can('editor') && t.items.length > 1 ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'tag-merge', onclick: () => {
        const into = el('select', { 'aria-label': 'Merge into', 'data-testid': 'tag-merge-into' }, t.items.filter((y) => y.id !== x.id).map((y) => el('option', { value: y.id, text: '#' + y.name })));
        openDialog([el('h2', { text: 'Merge #' + x.name }), el('p', { class: 'small', text: plural(x.used_by, 'record') + ' get the tag you choose instead; #' + x.name + ' is archived.' }), into,
          el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
            el('button', { class: 'btn primary', type: 'button', 'data-testid': 'tag-merge-save', text: 'Merge', onclick: async () => {
              try { await api('POST', '/tags/' + x.id + '/merge', { into: into.value }); closeDialog(); toast('Merged'); reload(); } catch (e) { failToast(e); } } }))], { label: 'Merge tag' });
      } }, icon('git-merge', 'sm'), 'Merge…') : null,
      can('editor') ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'tag-archive', onclick: async () => {
        const ok = await confirmDialog({ title: 'Archive #' + x.name + '?', body: plural(x.used_by, 'record') + ' will lose this tag. Undo puts it back on all of them.', confirmLabel: 'Archive', danger: true });
        if (!ok) return;
        try { const out = await api('POST', '/tags/' + x.id + '/archive');
          toast('Archived #' + x.name, { action: { label: 'Undo', fn: async () => { await api('POST', '/tags/' + x.id + '/restore', { records: out.removed_from }); toast('Restored'); reload(); } } }); reload(); }
        catch (e) { failToast(e); }
      } }, icon('archive', 'sm'), 'Archive') : null))));
  }).catch((e) => body.appendChild(errorBox(e)));
}

/* Members (run 6, F4): add an IK colleague by e-mail before or after their
   first sign-in (the role applies when they sign in), change a role, remove
   one, and what each role can do in plain words (from the server, the same
   text it enforces). The last admin can never be removed or demoted: the
   database refuses it (0034) and this tab says so before anyone tries. Every
   change appears in Activity. */
const ROLE_KEYS = ['viewer', 'contributor', 'editor', 'admin'];
const roleLabel = (r) => r.charAt(0).toUpperCase() + r.slice(1);
const LAST_ADMIN = 'The last admin cannot be removed or demoted. Make someone else an admin first.';

function membersTab(body) {
  const reload = () => { clear(body); membersTab(body); };
  body.appendChild(el('div', { class: 'tab-intro' }, el('p', { text: 'Add an IK colleague by their @interviewkickstart.com address, before or after their first sign-in: the role applies as soon as they sign in. Every change here appears in Activity.' })));
  const email = el('input', { type: 'email', placeholder: 'name@interviewkickstart.com', 'aria-label': 'IK e-mail address', 'data-testid': 'invite-email', maxlength: '254', class: 'input-md', autocomplete: 'off' });
  const role = el('select', { 'aria-label': 'Role for the new member', 'data-testid': 'invite-role' }, ROLE_KEYS.map((r) => el('option', { value: r, text: roleLabel(r), selected: r === 'contributor' })));
  const err = el('div', { class: 'field-error', role: 'alert', 'data-testid': 'invite-error' });
  const add = async () => {
    err.textContent = '';
    const v = email.value.trim().toLowerCase();
    // A hint only: the server checks the domain and the database checks it again.
    if (!/^[^@\s]+@interviewkickstart\.com$/.test(v)) { err.textContent = 'Enter an @interviewkickstart.com address: only IK Workspace accounts can sign in.'; email.focus(); return; }
    try {
      const out = await api('POST', '/members/invite', { email: v, role: role.value });
      toast(out.status === 'applied' ? roleLabel(out.role) + ' role given to ' + v : v + ' added: ' + roleLabel(out.role) + ' from their first sign-in');
      reload();
    } catch (e) { err.textContent = e.message || 'Could not add this person'; }
  };
  email.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
  body.appendChild(el('div', { class: 'inline-form', 'data-testid': 'invite-form' }, email, role,
    el('button', { class: 'btn primary', type: 'button', 'data-testid': 'invite-add', text: 'Add member', onclick: add })));
  body.appendChild(err);
  const ul = el('ul', { class: 'list bordered mt-3', 'data-testid': 'members' });
  const pending = el('ul', { class: 'list bordered', 'data-testid': 'invites' });
  const help = el('ul', { class: 'list bordered', 'data-testid': 'role-help' });
  body.append(ul, el('h3', { class: 'mt-4', text: 'Waiting for their first sign-in' }), pending, el('h3', { class: 'mt-4', text: 'What each role can do' }), help);
  api('GET', '/members').then((m) => {
    (m.roles || []).forEach((x) => help.appendChild(el('li', { 'data-testid': 'role-help-row', 'data-role': x.role }, el('div', { class: 'link-row roomy' },
      el('strong', { class: 'input-sm', text: x.label }), el('span', { class: 'small muted grow', text: x.can })))));
    const admins = m.items.filter((x) => x.role === 'admin').length;
    m.items.forEach((x) => {
      const lastAdmin = x.role === 'admin' && admins <= 1;
      const remove = !you(x.user_id) ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'member-remove', text: 'Remove', disabled: lastAdmin, title: lastAdmin ? LAST_ADMIN : null, onclick: async () => {
        const ok = await confirmDialog({ title: 'Remove ' + (x.email || 'this person') + '?', body: 'Their knowledge-base role is removed (audited). If they can sign in to the main site they stay a viewer. You can grant a role again any time.', confirmLabel: 'Remove', danger: true });
        if (!ok) return;
        try { await api('POST', '/members/' + x.user_id + '/remove'); toast('Removed'); reload(); } catch (e) { failToast(e); } } }) : null;
      const sel = el('select', { 'aria-label': 'Role for ' + (x.email || x.user_id), 'data-testid': 'member-role' }, ROLE_KEYS.map((r) => el('option', { value: r, text: roleLabel(r), selected: r === x.role, disabled: lastAdmin && r !== 'admin' })));
      sel.addEventListener('change', async () => {
        try { await api('POST', '/members/' + x.user_id, { role: sel.value }); toast('Role updated'); reload(); }
        catch (e) { sel.value = x.role; failToast(e); } });
      ul.appendChild(el('li', { 'data-testid': 'member-row' }, el('div', { class: 'link-row roomy' }, avatar(x.user_id), el('span', { class: 'truncate grow', text: x.email || x.user_id }),
        you(x.user_id) ? el('span', { class: 'badge', text: 'You' }) : null,
        lastAdmin ? el('span', { class: 'faint xs', 'data-testid': 'last-admin-note', text: LAST_ADMIN }) : null, sel, remove)));
    });
    if (!(m.invites || []).length) pending.appendChild(el('li', { class: 'link-row faint', text: 'Nobody is waiting.' }));
    (m.invites || []).forEach((x) => {
      const sel = el('select', { 'aria-label': 'Role for ' + x.email, 'data-testid': 'invite-row-role' }, ROLE_KEYS.map((r) => el('option', { value: r, text: roleLabel(r), selected: r === x.role })));
      sel.addEventListener('change', async () => {
        try { await api('POST', '/members/invites/' + x.id, { role: sel.value }); toast('Role updated'); } catch (e) { sel.value = x.role; failToast(e); } });
      pending.appendChild(el('li', { 'data-testid': 'invite-row' }, el('div', { class: 'link-row roomy' }, icon('clock'), el('span', { class: 'truncate grow', text: x.email }),
        el('span', { class: 'faint xs', text: 'added ' + ago(x.created_at) }), sel,
        el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'invite-revoke', text: 'Withdraw', onclick: async () => {
          const ok = await confirmDialog({ title: 'Withdraw the invitation for ' + x.email + '?', body: 'If they sign in later they are a viewer, like any IK colleague. The change is recorded in Activity.', confirmLabel: 'Withdraw', danger: true });
          if (!ok) return;
          try { await api('POST', '/members/invites/' + x.id + '/revoke'); toast('Withdrawn'); reload(); } catch (e) { failToast(e); } } }))));
    });
  }).catch((e) => body.appendChild(errorBox(e)));
}
function tokensTab(body) {
  body.appendChild(el('div', { class: 'tab-intro' }, el('p', { text: 'A token lets the AI assistant (Claude Code with the IK knowledge plugin) act as you, with your role. It is shown once. Anything it archives or deletes always needs a person’s approval.' })));
  const name = el('input', { placeholder: 'Token name, e.g. “laptop Claude Code”', 'aria-label': 'Token name', 'data-testid': 'token-name', maxlength: '80', class: 'input-md' });
  const days = el('select', { 'aria-label': 'Expires after' }, [['30', '30 days'], ['90', '90 days'], ['365', '1 year']].map(([v, l]) => el('option', { value: v, text: l, selected: v === '90' })));
  const out = el('div');
  const list = el('ul', { class: 'list bordered mt-3', 'data-testid': 'tokens' });
  const load = async () => { try { const t = await api('GET', '/tokens'); clear(list);
    if (!t.items.length) list.appendChild(el('li', { class: 'link-row faint', text: 'No tokens.' }));
    t.items.forEach((x) => list.appendChild(el('li', { 'data-testid': 'token-row' }, el('div', { class: 'link-row roomy' }, icon('key-round'), el('strong', { text: x.name }), el('span', { class: 'faint xs mono', text: x.prefix + '…' }),
      el('span', { class: 'faint xs grow', text: x.revoked_at ? 'revoked' : 'expires ' + (x.expires_at ? new Date(x.expires_at).toLocaleDateString() : 'never') + (x.last_used_at ? ' · used ' + ago(x.last_used_at) : ' · never used') }),
      !x.revoked_at ? el('button', { class: 'btn sm danger', type: 'button', 'data-testid': 'token-revoke', text: 'Revoke', onclick: async () => {
        if (!(await confirmDialog({ title: 'Revoke “' + x.name + '”?', body: 'Anything using this token stops working immediately.', confirmLabel: 'Revoke', danger: true }))) return;
        try { await api('POST', '/tokens/' + x.id + '/revoke'); toast('Revoked'); load(); } catch (e) { failToast(e); } } }) : null)))); }
    catch (e) { list.appendChild(errorBox(e)); } };
  body.append(el('div', { class: 'inline-form' }, name, days, el('button', { class: 'btn primary', type: 'button', 'data-testid': 'token-create', text: 'Create token', onclick: async () => {
    if (!name.value.trim()) { name.focus(); return; }
    try { const t = await api('POST', '/tokens', { name: name.value.trim(), expires_in_days: Number(days.value) }); name.value = '';
      const val = el('input', { readonly: true, value: t.token, 'data-testid': 'token-value', 'aria-label': 'New token', class: 'mono grow', onfocus: (e) => e.target.select() });
      clear(out).appendChild(el('div', { class: 'note-box accent col mt-3' }, el('strong', { text: 'Copy this token now — it will not be shown again.' }),
        el('div', { class: 'row' }, val, el('button', { class: 'btn sm', type: 'button', text: 'Copy', onclick: () => { val.select(); if (navigator.clipboard) navigator.clipboard.writeText(t.token); toast('Copied'); } }))));
      load(); } catch (e) { failToast(e); } } })), out, list);
  load();
}
function templatesTab(body) {
  body.appendChild(el('div', { class: 'tab-intro' }, el('p', { text: 'Save a course or program as a template from its “…” menu. New record → Course → “Start from” creates a copy of its structure.' })));
  const ul = el('ul', { class: 'list bordered', 'data-testid': 'templates' });
  body.appendChild(ul);
  api('GET', '/templates').then((t) => {
    if (!t.items.length) ul.appendChild(el('li', { class: 'link-row faint', text: 'No templates yet.' }));
    t.items.forEach((x) => ul.appendChild(el('li', null, el('div', { class: 'link-row roomy' }, typeIcon(x.root_type), el('strong', { text: x.name }), el('span', { class: 'faint xs grow', text: plural(x.top_level || 0, 'top-level item') + ' · ' + ago(x.created_at) }),
      can('editor') ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'template-rename', text: 'Rename', onclick: () => {
        const name = el('input', { value: x.name, 'aria-label': 'Template name' });
        openDialog([el('h2', { text: 'Rename template' }), name, el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: closeDialog }),
          el('button', { class: 'btn primary', type: 'button', text: 'Rename', onclick: async () => { try { await api('PATCH', '/templates/' + x.id, { name: name.value.trim() }); closeDialog(); toast('Renamed'); clear(body); templatesTab(body); } catch (e) { failToast(e); } } }))], { label: 'Rename template' }); } }) : null,
      can('editor') ? el('button', { class: 'btn sm', type: 'button', text: 'Remove', onclick: async () => { try { await api('POST', '/templates/' + x.id + '/archive'); clear(body); templatesTab(body);
        toast('Removed', { action: { label: 'Undo', fn: async () => { await api('POST', '/templates/' + x.id + '/restore'); clear(body); templatesTab(body); } } }); } catch (e) { failToast(e); } } }) : null))));
  }).catch((e) => body.appendChild(errorBox(e)));
}

// ------------------------------------------------------------------ sync (admins)
/* The original site's tables -> the KB, on a schedule (hourly by default; the
   schedule lives in the database) and on demand. Edits made here are never
   overwritten: they become conflicts on Data quality. */
// ---------------------------------------------------------------- sources (run C, 2026-11-07)
// The source catalog: everything the registry sheet reaches (Drive), every KYP page and attachment
// (Confluence), and every access failure, with its live link, version and provenance.
const SRC_STATUS = { extracted: ['Read', 'ok'], extracted_empty: ['Read (no text)', 'warn'], listed: ['Listed', ''], media_listed: ['Audio/video: counted only', ''],
  failed: ['Failed', 'danger'], do_not_use: ['[Do not Use]: skipped', 'warn'], deferred: ['Deferred', 'warn'], imported: ['Imported', 'ok'], attachment_listed: ['Attachment: listed only', ''] };
const fmtBytes = (b) => !b ? '' : b > 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1e3)) + ' KB';
function sourcesSection(host) {
  const st = { status: '', q: '', offset: 0 };
  const sum = el('div', { 'data-testid': 'sources-summary' }, skeletonRows(2));
  const list = el('div', { 'data-testid': 'sources-list' });
  const chipsRow = el('div', { class: 'chip-row', role: 'group', 'aria-label': 'Filter by status' });
  const search = el('input', { type: 'search', placeholder: 'Search sources by name or link…', 'aria-label': 'Search sources', 'data-testid': 'sources-search' });
  let t = null;
  search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { st.q = search.value.trim(); st.offset = 0; loadList(); }, 250); });
  add(host, [el('h3', { class: 'subhead', text: 'Sources' }),
    el('p', { class: 'small muted', text: 'The registry sheet is the single list of sources. Every Drive folder and file it reaches, every KYP page in Confluence, and every link that could not be read, with its live link and version. Re-crawling compares each source by its id and version.' }),
    sum, el('div', { class: 'row wrap gap-2' }, chipsRow, search), list]);
  const loadList = () => api('GET', '/sources' + qs({ status: st.status || null, q: st.q || null, limit: 50, offset: st.offset })).then((d) => {
    clear(list);
    if (!d.items.length) { list.appendChild(empty('No sources match', 'Change the filter or the search.', null, 'search')); return; }
    list.appendChild(el('table', { class: 'table', 'data-testid': 'sources-table' },
      el('thead', {}, el('tr', {}, ['Source', 'Kind', 'Status', 'Version / modified', 'Reached from'].map((h) => el('th', { text: h })))),
      el('tbody', {}, d.items.map((r) => el('tr', { 'data-testid': 'source-row', 'data-status': r.status },
        el('td', {}, el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', text: r.title || r.url, class: 'truncate', 'data-testid': 'source-link' }),
          r.failure_reason ? el('div', { class: 'xs source-failure', 'data-testid': 'source-failure', text: r.failure_reason }) : null),
        el('td', { class: 'small', text: [r.provider === 'confluence' ? 'KYP ' + r.kind : r.kind, fmtBytes(r.size_bytes)].filter(Boolean).join(' · ') }),
        el('td', {}, el('span', { class: 'badge ' + ((SRC_STATUS[r.status] || [])[1] || ''), text: (SRC_STATUS[r.status] || [r.status])[0] })),
        el('td', { class: 'small', text: [r.version ? 'v' + r.version : null, r.modified_at ? ago(r.modified_at) : null, r.last_changed ? 'changed since last crawl' : null].filter(Boolean).join(' · ') }),
        el('td', { class: 'xs faint', text: (r.provenance || []).join(' › ') }))))),
      el('div', { class: 'row gap-2' }, el('span', { class: 'small faint', text: (st.offset + 1) + '–' + (st.offset + d.items.length) + ' of ' + d.total }),
        st.offset ? el('button', { class: 'btn sm', type: 'button', text: 'Previous', onclick: () => { st.offset = Math.max(0, st.offset - 50); loadList(); } }) : null,
        st.offset + d.items.length < d.total ? el('button', { class: 'btn sm', type: 'button', 'data-testid': 'sources-next', text: 'Next', onclick: () => { st.offset += 50; loadList(); } }) : null));
  }).catch((e) => { clear(list); list.appendChild(errorBox(e, loadList)); });
  api('GET', '/sources/summary').then((d) => {
    clear(sum);
    const tot = {}; d.by_status.forEach((r) => { tot[r.status] = (tot[r.status] || 0) + r.n; });
    sum.appendChild(el('table', { class: 'table compact', 'data-testid': 'sources-counts' },
      el('thead', {}, el('tr', {}, ['Where', 'Status', 'Count', 'Size'].map((h) => el('th', { text: h })))),
      el('tbody', {}, d.by_status.map((r) => el('tr', {}, el('td', { text: r.provider === 'drive' ? 'Drive (registry)' : r.provider === 'confluence' ? 'Confluence (KYPs)' : r.provider }),
        el('td', { text: (SRC_STATUS[r.status] || [r.status])[0] }), el('td', { class: 'tabular', text: String(r.n) }), el('td', { class: 'small', text: fmtBytes(r.bytes) }))))));
    clear(chipsRow);
    [['', 'All']].concat(Object.keys(SRC_STATUS).filter((k) => tot[k]).map((k) => [k, SRC_STATUS[k][0] + ' (' + tot[k] + ')'])).forEach(([k, l]) => chipsRow.appendChild(
      el('button', { type: 'button', class: 'filter-chip' + (st.status === k ? ' on' : ''), 'aria-pressed': st.status === k ? 'true' : 'false', 'data-testid': 'sources-filter-' + (k || 'all'), text: l,
        onclick: (e) => { st.status = k; st.offset = 0; chipsRow.querySelectorAll('.filter-chip').forEach((b) => { b.classList.toggle('on', b === e.currentTarget); b.setAttribute('aria-pressed', b === e.currentTarget ? 'true' : 'false'); }); loadList(); } })));
  }).catch((e) => { clear(sum); sum.appendChild(errorBox(e)); });
  loadList();
}

function syncTab(body) {
  sourcesSection(body.appendChild(el('div', { class: 'section', 'data-testid': 'sources-section' })));
  const host = el('div', { 'data-testid': 'sync-tab' }, skeletonRows(4));
  body.appendChild(el('h3', { class: 'subhead', text: 'Sync' }));
  body.appendChild(host);
  const load = () => api('GET', '/sync').then((d) => {
    clear(host);
    const btn = el('button', { class: 'btn primary', type: 'button', 'data-testid': 'sync-now', disabled: !d.enabled, onclick: async () => {
      btn.disabled = true; btn.textContent = 'Syncing…';
      try { const r = await api('POST', '/sync/run'); toast(r.status === 'ok' ? (r.partial ? 'Sync ran out of time; the next run continues' : 'Sync finished') : r.status === 'skipped' ? 'A sync is already running' : 'Sync failed: ' + (r.message || r.status)); }
      catch (e) { failToast(e); }
      load();
    } }, icon('refresh-cw'), 'Sync now');
    add(host, [
      el('div', { class: 'tab-intro' },
        el('p', { text: 'Copies changes from the original site into the knowledge base: hourly by default, or now. Only changed rows are written; a record edited here is never overwritten (it is flagged on Data quality); a row removed at the source is flagged, never deleted.' }),
        btn),
      d.enabled ? null : el('div', { class: 'note-box warn', 'data-testid': 'sync-disabled', text: 'The sync is switched off (KB_SYNC_ENABLED=false).' }),
      d.failing ? el('div', { class: 'note-box warn', 'data-testid': 'sync-failing', text: 'The last sync failed: ' + ((d.last.errors || [])[0] || d.last.message || 'see the log below') }) : null,
      el('h3', { class: 'subhead', text: 'Run log' }),
      d.runs.length ? el('table', { class: 'table', 'data-testid': 'sync-runs' },
        el('thead', {}, el('tr', {}, ['Started', 'Trigger', 'Status', 'Changes', 'Conflicts', 'Took'].map((h) => el('th', { text: h })))),
        el('tbody', {}, d.runs.map((r) => el('tr', { 'data-testid': 'sync-run' },
          el('td', { text: ago(r.started_at), title: String(r.started_at) }), el('td', { text: r.trigger === 'cron' ? 'Schedule' : r.trigger === 'manual' ? (r.actor_id ? personName(r.actor_id) : 'Sync now') : 'Command line' }),
          el('td', {}, el('span', { class: 'badge ' + (r.status === 'ok' ? 'ok' : r.status === 'error' ? 'danger' : 'warn'), text: r.status === 'ok' && r.counts && r.counts.partial ? 'ok (continues)' : r.status })),
          el('td', { class: 'small', text: r.counts ? (['created', 'updated', 'removed_at_source'].map((k) => k.replace(/_/g, ' ') + ' ' + Object.values(r.counts[k] || {}).reduce((a, b) => a + b, 0)).join(' · ')) : (r.message || '') }),
          el('td', { text: String(r.conflicts || 0) }),
          el('td', { text: r.finished_at ? Math.max(0, Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000)) + ' s' : '…' }))))) :
        empty('No runs yet', 'The first run happens on the next schedule, or press Sync now.', null, 'refresh-cw'),
    ]);
  }).catch((e) => { clear(host); host.appendChild(errorBox(e, load)); });
  load();
}
