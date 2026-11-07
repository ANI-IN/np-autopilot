/* The ONE entity-detail component (run C, 2026-11-07).

   The Graph editor, the Map, the Admin pages and the record page all render a record's
   facts with entitySections(): same sections, same order, same wording. It has no
   dependency on the workspace shell, so the read-only Map can import it too.

   Input: a record as GET /api/kb/nodes/<id> returns it (node.profile is computed on the
   server from the relationships). Sections appear only when they have data.

   opts = {
     href(id)            -> link for a related record (default: the workspace record page)
     onOpen(id, ev)      -> optional click handler for related records (the Map selects in place)
     icon(name, size)    -> optional icon renderer (the workspace's sprite); text-only without it
     edit                -> optional editing hooks (workspace, contributor and up):
       { addOwner(), removeOwner(item), addSme(), changeSme(item), removeSme(item) }
   }
*/

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'text') e.textContent = v;
    else if (k === 'class') e.className = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}

const TYPE_LABEL = { program: 'Program', course: 'Course', module: 'Module', topic: 'Topic', concept: 'Concept', domain: 'Domain',
  instructor: 'Instructor', team_member: 'NP team member', session: 'Live session' };
export const typeName = (t) => TYPE_LABEL[t] || (t ? t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ') : 'Record');

function link(item, opts) {
  const a = h('a', { href: (opts.href || ((id) => '/kb/#/r/' + id))(item.id), class: 'entity-link', 'data-id': item.id, 'data-testid': 'entity-link',
    text: item.name, title: typeName(item.type) + ': ' + item.name });
  if (opts.onOpen) a.addEventListener('click', (ev) => { ev.preventDefault(); opts.onOpen(item.ref || item.id, item, ev); });
  return a;
}

function section(title, testid, body, extra) {
  return h('section', { class: 'entity-section', 'data-testid': testid },
    h('div', { class: 'entity-section-head' }, h('h3', { text: title }), extra || null), body);
}

function chips(items, opts, render) {
  return h('ul', { class: 'entity-chips' }, items.map((it) => h('li', { class: 'entity-chip', 'data-testid': 'entity-chip' }, render ? render(it) : link(it, opts))));
}

function ordered(items, opts, sub) {
  return h('ol', { class: 'entity-list' }, items.map((it) => h('li', { class: 'entity-row' },
    h('span', { class: 'entity-row-main' }, link(it, opts)), sub ? sub(it) : null)));
}

function schedule(s) {
  if (!s || !(s.labels || []).length) return null;
  return h('span', { class: 'entity-sched', title: 'Program-specific schedule' + (s.program ? ' (' + s.program + ')' : '') },
    s.labels.map((l) => /^\d/.test(l) ? 'Week ' + l : l).join(', '));
}

function btn(label, testid, fn, danger) {
  return h('button', { type: 'button', class: 'btn ghost sm' + (danger ? ' danger' : ''), 'data-testid': testid, onclick: fn, text: label });
}

export function smeBadge(s) {
  const cls = s.role === 'primary' ? 'entity-role primary' : s.role === 'backup' ? 'entity-role backup' : 'entity-role other';
  return h('span', { class: cls, 'data-testid': 'sme-role', text: s.label || s.role });
}

/* The facts of one record, as one element. */
export function entitySections(n, opts) {
  opts = opts || {};
  const p = n.profile || {}, edit = opts.edit || null;
  const root = h('div', { class: 'entity', 'data-testid': 'entity', 'data-type': n.type });

  // classification
  const facts = h('dl', { class: 'entity-facts', 'data-testid': 'entity-facts' },
    opts.hideType ? null : h('dt', { text: 'Type' }), opts.hideType ? null : h('dd', { 'data-testid': 'entity-type', text: typeName(n.type) }));
  if ((p.domains || []).length) facts.append(h('dt', { text: p.domains.length > 1 ? 'Domains' : 'Domain' }),
    h('dd', { 'data-testid': 'entity-domain' }, p.domains.map((d, i) => [i ? ', ' : '', link(d, opts)])));
  if ((p.variant_of || []).length) facts.append(h('dt', { text: 'Variant of' }), h('dd', { 'data-testid': 'entity-variant-of' }, p.variant_of.map((d) => link(d, opts))));
  if (n.summary) facts.append(h('dt', { text: 'Description' }), h('dd', { class: 'entity-desc', text: n.summary }));
  root.append(facts);

  // where a module is used: course -> programs (week labels are program data only)
  if ((p.used_in || []).length) {
    root.append(section('Used in', 'entity-used-in', h('div', null, h('ul', { class: 'entity-list' }, p.used_in.map((u) => h('li', { class: 'entity-row' },
      h('span', { class: 'entity-row-main' }, link(u, opts),
        (u.programs || []).length ? h('span', { class: 'entity-sub' }, ' in ', u.programs.map((pr, i) => [i ? ', ' : '', link(pr, opts)])) : null),
      schedule(u.schedule)))),
      h('p', { class: 'entity-note', text: 'Week and order belong to each program, not to the module.' }))));
  }

  // owners: NP team members
  if (['program', 'course', 'module'].includes(n.type) && ((p.owners || []).length || edit)) {
    const body = (p.owners || []).length ? chips(p.owners, opts, (o) => [link(o, opts),
      edit ? h('button', { type: 'button', class: 'entity-x', 'aria-label': 'Remove owner ' + o.name, 'data-testid': 'remove-owner', onclick: () => edit.removeOwner(o), text: '×' }) : null])
      : h('p', { class: 'entity-empty', text: 'No owner yet. Owners are NP team members.' });
    root.append(section('Owners', 'entity-owners', body, edit ? btn('Add owner', 'add-owner', () => edit.addOwner()) : null));
  }

  // SMEs: Primary first, then Backup 1-3, then other named roles
  if (n.type === 'module' && ((p.smes || []).length || edit)) {
    const prim = (p.smes || []).filter((s) => s.role === 'primary'), rest = (p.smes || []).filter((s) => s.role !== 'primary');
    const row = (s) => h('li', { class: 'entity-row entity-sme', 'data-testid': 'sme-row', 'data-role': s.role || '' },
      smeBadge(s), h('span', { class: 'entity-row-main' }, link(s, opts)),
      edit ? h('span', { class: 'entity-row-actions' }, btn('Role', 'change-sme-role', () => edit.changeSme(s)), btn('Remove', 'remove-sme', () => edit.removeSme(s), true)) : null);
    const body = h('div', null,
      prim.length ? h('ul', { class: 'entity-list entity-primary', 'data-testid': 'sme-primary' }, prim.map(row)) : null,
      rest.length ? h('ul', { class: 'entity-list', 'data-testid': 'sme-backups' }, rest.map(row)) : null,
      !(p.smes || []).length ? h('p', { class: 'entity-empty', text: 'No SME yet. SMEs are instructors with a role: Primary or Backup 1, 2, 3.' }) : null);
    root.append(section('SMEs', 'entity-smes', body, edit ? btn('Add SME', 'add-sme', () => edit.addSme()) : null));
  }

  if ((p.courses || []).length && n.type === 'program') root.append(section('Courses', 'entity-courses', ordered(p.courses, opts, (c) =>
    h('span', { class: 'entity-sub' }, c.modules ? c.modules + (c.modules === 1 ? ' module' : ' modules') : '', schedule(c.schedule) ? [' · ', schedule(c.schedule)] : null))));
  if ((p.modules || []).length && ['program', 'course'].includes(n.type)) root.append(section(n.type === 'program' ? 'Modules outside a course' : 'Modules', 'entity-modules', ordered(p.modules, opts, (m) => schedule(m.schedule))));
  if ((p.programs || []).length && n.type === 'course') root.append(section('Programs', 'entity-programs', chips(p.programs, opts)));
  if ((p.topics || []).length) root.append(section('Topics', 'entity-topics', ordered(p.topics, opts)));
  if ((p.content_topics || []).length) root.append(section('Topics found in its content', 'entity-content-topics',
    h('details', null, h('summary', { text: p.content_topics.length + ' topics' }), chips(p.content_topics, opts))));
  if ((p.concepts || []).length) root.append(section('Concepts', 'entity-concepts', chips(p.concepts, opts)));
  if ((p.variants || []).length) root.append(section('Variants', 'entity-variants', chips(p.variants, opts)));
  if ((p.sessions || []).length) root.append(section('Live sessions', 'entity-sessions', chips(p.sessions, opts)));
  if ((p.modules || []).length && n.type === 'topic') root.append(section('In modules', 'entity-topic-modules', chips(p.modules, opts)));
  if (n.type === 'domain') {
    if ((p.programs || []).length) root.append(section('Programs', 'entity-domain-programs', chips(p.programs, opts)));
    if ((p.courses || []).length) root.append(section('Courses', 'entity-domain-courses', chips(p.courses, opts)));
    if ((p.modules || []).length) root.append(section('Modules', 'entity-domain-modules', chips(p.modules, opts)));
  }
  if ((p.sme_of || []).length) root.append(section('SME for', 'entity-sme-of', h('ul', { class: 'entity-list' },
    p.sme_of.map((s) => h('li', { class: 'entity-row' }, smeBadge(s), h('span', { class: 'entity-row-main' }, link(s, opts)))))));
  if ((p.teaches || []).length) root.append(section('Listed as an instructor in', 'entity-teaches', chips(p.teaches, opts)));
  if ((p.owns || []).length) root.append(section('Owns', 'entity-owns', chips(p.owns, opts)));
  if ((p.listed_instructors || []).length) root.append(section('Instructors listed in the KYP', 'entity-listed-instructors', chips(p.listed_instructors, opts)));

  // resources: the original live links
  if ((n.resources || []).length) root.append(section('Resources', 'entity-resources', h('ul', { class: 'entity-list' }, n.resources.map((r) =>
    h('li', { class: 'entity-row' }, h('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', class: 'entity-link', 'data-testid': 'entity-resource', text: r.title || r.url }),
      h('span', { class: 'entity-sub', text: (r.kind || 'link').replace(/_/g, ' ') + ' · ' + hostOf(r.url) }))))));

  // sources: provenance
  if ((p.sources || []).length) root.append(section('Sources', 'entity-sources', h('ul', { class: 'entity-list' }, p.sources.map((s) =>
    h('li', { class: 'entity-row entity-source' },
      s.url ? h('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer', class: 'entity-link', 'data-testid': 'entity-source', text: s.page_title || 'Source' }) : h('span', { text: s.page_title || s.source }),
      h('span', { class: 'entity-sub', text: [s.source === 'confluence' ? 'KYP' : s.source, s.page_version ? 'version ' + s.page_version : null,
        s.heading, s.row ? 'row ' + s.row : null].filter(Boolean).join(' · ') }))))));
  return root;
}

function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return ''; } }
