/* Core of the KB workspace: DOM helpers, icons, API client, feedback
   (toasts, dialogs, menus, side sheets), shared state. Vanilla ES modules, no
   build step (CSP script-src 'self'). Every value from the API is rendered with
   textContent via el(); innerHTML is never given data. */

export const S = {
  session: null, me: null, people: [], personById: {},
  types: [], typeByKey: {}, edgeTypes: [], linkKinds: [], resourceKinds: [], fieldKinds: [], palette: [],
  route: null, panel: null, listReload: null, counts: {}, feedCursor: null,
};
export const SESSION_KEY = 'np_session';

// ------------------------------------------------------------------ DOM
export function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'text') n.textContent = v;
    else if (k === 'class') n.className = v;
    else if (k === 'style') n.setAttribute('style', v);
    else if (k === 'dataset') Object.assign(n.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (k === 'value') n.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'hidden' || k === 'open') n[k] = !!v;
    else n.setAttribute(k, v === true ? '' : v);
  }
  add(n, kids);
  // Text that may be cut off with "…" always carries its full text as a tooltip (A5 sweep).
  if (props && props.text && !props.title && / truncate |^truncate | truncate$|^truncate$/.test(props.class || '')) n.title = String(props.text);
  return n;
}
export function add(parent, kids) {
  for (const k of [].concat(kids)) {
    if (k === null || k === undefined || k === false) continue;
    if (Array.isArray(k)) add(parent, k);
    else parent.appendChild(typeof k === 'string' || typeof k === 'number' ? document.createTextNode(String(k)) : k);
  }
  return parent;
}
export const $ = (s, root) => (root || document).querySelector(s);
export const $$ = (s, root) => Array.from((root || document).querySelectorAll(s));
export function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

const SVGNS = 'http://www.w3.org/2000/svg';
export function icon(name, cls) {
  const s = document.createElementNS(SVGNS, 'svg');
  s.setAttribute('class', 'i' + (cls ? ' ' + cls : '')); s.setAttribute('aria-hidden', 'true');
  const u = document.createElementNS(SVGNS, 'use');
  u.setAttribute('href', '/vendor/lucide-sprite.svg#i-' + (name || 'box'));
  s.appendChild(u);
  return s;
}
export function typeIcon(key, cls) {
  const t = S.typeByKey[key] || {};
  const w = el('span', { class: 'type-icon', style: '--type:' + (t.color || 'var(--text-3)'), title: t.label || key });
  w.appendChild(icon(t.icon || 'box', cls));
  return w;
}
export function typeLabel(key, plural) { const t = S.typeByKey[key]; return t ? (plural ? t.plural : t.label) : key; }
export function typeDot(key) { const t = S.typeByKey[key] || {}; return el('span', { class: 'dot', style: '--type:' + (t.color || 'var(--text-3)') }); }

// ------------------------------------------------------------------ people
const AV = ['#1d4ed8', '#0f766e', '#b45309', '#be123c', '#4d7c0f', '#0e7490', '#9a3412', '#475569'];
export function personName(id) {
  if (!id) return null;
  const p = S.personById[id];
  return p ? p.email.split('@')[0].replace(/[._-]+/g, ' ') : 'Former member';
}
export function avatar(id, cls) {
  if (!id) return el('span', { class: 'avatar no-owner' + (cls ? ' ' + cls : ''), title: 'No owner' }, icon('user', 'sm'));
  const name = personName(id) || '?';
  let h = 0; for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const initials = name.split(' ').filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
  return el('span', { class: 'avatar' + (cls ? ' ' + cls : ''), style: '--av:' + AV[h % AV.length], title: name }, initials);
}
export function you(id) { return S.me && id === S.me.user_id; }

// ------------------------------------------------------------------ formatting
export function ago(ts) {
  if (!ts) return '';
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 45) return 'just now';
  if (s < 3600) return Math.round(s / 60) + 'm ago';
  if (s < 86400) return Math.round(s / 3600) + 'h ago';
  if (s < 86400 * 30) return Math.round(s / 86400) + 'd ago';
  return new Date(ts).toLocaleDateString();
}
export function plural(n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); }
export function host(url) { try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return ''; } }
export function qs(o) {
  const p = [];
  for (const [k, v] of Object.entries(o || {})) if (v !== undefined && v !== null && v !== '') p.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
  return p.length ? '?' + p.join('&') : '';
}
export function debounce(fn, ms) { let t; return function (...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); }; }
export function can(role) {
  const order = ['none', 'viewer', 'contributor', 'editor', 'admin'];
  return S.me && order.indexOf(S.me.role) >= order.indexOf(role);
}

// ------------------------------------------------------------------ API
export class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.message || body.reason || body.error)) || ('HTTP ' + status));
    this.status = status; this.body = body || {};
  }
}
export function loadSession() { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch (e) { return null; } }
export function saveSession(s) { S.session = s; try { localStorage.setItem(SESSION_KEY, JSON.stringify(s)); } catch (e) { /* storage blocked */ } }
async function refreshSession() {
  if (!S.session || !S.session.refresh_token) return false;
  try {
    const r = await fetch('/api/session', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'refresh', refresh_token: S.session.refresh_token }) });
    if (!r.ok) return false;
    saveSession(await r.json()); return true;
  } catch (e) { return false; }
}
let onSignedOut = () => {};
export function setSignedOutHandler(fn) { onSignedOut = fn; }
export async function api(method, path, body, retried) {
  const opts = { method, headers: {} };
  if (S.session) opts.headers.authorization = 'Bearer ' + S.session.access_token;
  if (body !== undefined) { opts.headers['content-type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let r;
  try { r = await fetch('/api/kb' + path, opts); }
  catch (e) { throw new ApiError(0, { message: 'Could not reach the server. Check your connection and try again.' }); }
  if (r.status === 401 && !retried) {
    if (await refreshSession()) return api(method, path, body, true);
    onSignedOut('Your session expired. Sign in again to continue.');
    throw new ApiError(401, { message: 'signed out' });
  }
  const data = await r.json().catch(() => ({}));
  if (r.status >= 400 || r.status === 202) throw new ApiError(r.status, data);
  return data;
}

// ------------------------------------------------------------------ toasts
export function toast(msg, opts) {
  opts = opts || {};
  const t = el('div', { class: 'toast' + (opts.error ? ' err' : ''), role: opts.error ? 'alert' : 'status', 'data-testid': 'toast' }, el('span', { text: msg }));
  for (const a of opts.actions || (opts.action ? [opts.action] : [])) {
    t.appendChild(el('button', { type: 'button', text: a.label, 'data-testid': 'toast-' + a.label.toLowerCase(), onclick: () => { a.fn(); t.remove(); } }));
  }
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), opts.ms || (opts.error ? 7000 : (opts.actions || opts.action ? 10000 : 3500)));
  return t;
}
export function failToast(e, what) {
  if (e && e.status === 401) return;
  toast((what ? what + ': ' : '') + ((e && e.message) || 'Something went wrong'), { error: true });
}

// ------------------------------------------------------------------ dialogs
/* Dialogs stack: one opened from inside another (New relationship type from
   Connect) sits on top, and closing it returns to the one below with its
   state intact. Without `stack`, opening a dialog replaces whatever is open. */
export function openDialog(content, opts) {
  opts = opts || {};
  const stacked = opts.stack && $$('.overlay[data-dialog]').length > 0;
  if (!stacked) closeAllDialogs();
  const box = el('div', { class: 'dialog' + (opts.wide ? ' wide' : '') + (opts.cls ? ' ' + opts.cls : ''), role: 'dialog', 'aria-modal': 'true', 'aria-label': opts.label || 'Dialog', 'data-testid': opts.testid || 'dialog' }, content);
  const ov = el('div', { class: 'overlay' + (stacked ? ' stacked' : ''), id: stacked ? null : 'dialog-overlay', 'data-dialog': '1',
    onmousedown: (e) => { if (e.target === ov && !opts.sticky) closeDialog(); } }, box);
  ov._lastFocus = document.activeElement;
  ov.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); closeDialog(); } });
  document.body.appendChild(ov);
  const f = box.querySelector('[autofocus], input:not([type=hidden]), select, textarea, button.primary, button');
  if (f) f.focus();
  return box;
}
export function closeDialog() {
  const all = $$('.overlay[data-dialog]');
  const ov = all.length ? all[all.length - 1] : $('#dialog-overlay');
  if (ov) { ov.remove(); const lf = ov._lastFocus; if (lf && lf.focus && document.contains(lf)) lf.focus(); }
}
function closeAllDialogs() { $$('.overlay[data-dialog]').forEach((o) => o.remove()); const p = $('#dialog-overlay'); if (p) p.remove(); }
export function confirmDialog(o) {
  return new Promise((resolve) => {
    let input = null;
    const ok = el('button', { class: 'btn ' + (o.danger ? 'danger solid' : 'primary'), type: 'button', 'data-testid': 'confirm-ok', text: o.confirmLabel || 'Confirm',
      disabled: !!o.typeToConfirm, onclick: () => { const v = input ? input.value : true; closeDialog(); resolve(o.withReason ? (reason ? reason.value : '') || true : v ? true : false); } });
    let reason = null;
    if (o.typeToConfirm) {
      input = el('input', { 'aria-label': 'Type the name to confirm', 'data-testid': 'confirm-type', autocomplete: 'off', placeholder: o.typeToConfirm });
      input.addEventListener('input', () => { ok.disabled = input.value.trim() !== o.typeToConfirm.trim(); });
    }
    if (o.withReason) reason = el('textarea', { rows: '2', placeholder: o.reasonPlaceholder || 'Reason (optional)', 'data-testid': 'confirm-reason', 'aria-label': 'Reason' });
    openDialog([
      el('h2', { text: o.title }),
      o.body ? (typeof o.body === 'string' ? el('p', { class: 'muted small', text: o.body }) : o.body) : null,
      o.typeToConfirm ? el('label', { class: 'field' }, el('span', { class: 'label', text: 'Type “' + o.typeToConfirm + '” to confirm' }), input) : null,
      reason,
      el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => { closeDialog(); resolve(false); } }), ok),
    ], { label: o.title, testid: 'confirm-dialog' });
  });
}

// ------------------------------------------------------------------ menus
let openMenuEl = null;
export function closeMenu() { if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; } }
export function menu(anchor, items, opts) {
  closeMenu();
  opts = opts || {};
  const m = el('div', { class: 'menu', role: 'menu', 'data-testid': opts.testid || 'menu' });
  for (const it of items) {
    if (!it) continue;
    if (it === '-') { m.appendChild(el('div', { class: 'menu-sep' })); continue; }
    if (it.label && it.header) { m.appendChild(el('div', { class: 'menu-label', text: it.label })); continue; }
    const checkable = it.checked !== undefined;
    m.appendChild(el('button', { type: 'button', role: checkable ? 'menuitemradio' : 'menuitem', 'aria-checked': checkable ? String(!!it.checked) : null,
      class: it.danger ? 'danger' : '', 'data-testid': it.testid, onclick: () => { closeMenu(); it.fn(); } },
      it.icon ? icon(it.icon) : null, it.node || it.label, (it.hint || checkable) ? el('span', { class: 'spacer' }) : null,
      it.hint ? el('kbd', { text: it.hint }) : null, it.checked ? icon('check', 'sm') : null));
  }
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect();
  const top = Math.min(r.bottom + 4, window.innerHeight - m.offsetHeight - 8);
  const left = Math.min(opts.alignRight ? r.right - m.offsetWidth : r.left, window.innerWidth - m.offsetWidth - 8);
  m.style.top = Math.max(8, top) + 'px'; m.style.left = Math.max(8, left) + 'px';
  openMenuEl = m;
  const first = m.querySelector('button'); if (first) first.focus();
  m.addEventListener('keydown', (e) => {
    const btns = $$('button', m); const i = btns.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); (btns[i + 1] || btns[0]).focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); (btns[i - 1] || btns[btns.length - 1]).focus(); }
    if (e.key === 'Escape') { e.stopPropagation(); closeMenu(); anchor.focus(); }
  });
  return m;
}
// A picker's option list lives in <body>; choosing from one inside a popover must not close the popover.
document.addEventListener('mousedown', (e) => { if (openMenuEl && !openMenuEl.contains(e.target) && !(e.target.closest && e.target.closest('.menu[role=listbox]'))) closeMenu(); });

/* A popover: a floating panel anchored to a button, always inside the
   viewport (flips above when there is no room below, clamps at both edges),
   closed by Esc or a click outside. Shares the single open-menu slot. */
export function popover(anchor, content, opts) {
  closeMenu();
  opts = opts || {};
  const m = el('div', { class: 'popover', role: 'dialog', 'aria-label': opts.label || 'Options', 'data-testid': opts.testid || 'popover' }, content);
  document.body.appendChild(m);
  const place = () => {
    const r = anchor.getBoundingClientRect(), w = m.offsetWidth, h = m.offsetHeight, vw = document.documentElement.clientWidth, vh = window.innerHeight;
    let left = opts.alignRight ? r.right - w : r.left;
    left = Math.max(8, Math.min(left, vw - w - 8));
    let top = r.bottom + 6;
    if (top + h > vh - 8 && r.top - h - 6 > 8) top = r.top - h - 6;
    m.style.left = left + 'px'; m.style.top = Math.max(8, Math.min(top, vh - h - 8)) + 'px';
  };
  place();
  openMenuEl = m;
  m.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); closeMenu(); anchor.focus(); } });
  const first = m.querySelector('input, button, select'); if (first) first.focus();
  m.reposition = place;
  return m;
}

// ------------------------------------------------------------------ side sheet
let sheetState = null;
export function openSheet(o) {
  closeSheet(true);
  const body = el('div', { class: 'sheet-body' }, o.body);
  const expand = el('button', { class: 'btn ghost icon', type: 'button', title: 'Expand to full page', 'aria-label': 'Expand to full page', onclick: () => { sheet.classList.toggle('full'); expand.replaceChildren(icon(sheet.classList.contains('full') ? 'minimize-2' : 'maximize-2')); } }, icon('maximize-2'));
  const close = el('button', { class: 'btn ghost icon', type: 'button', 'aria-label': 'Close', 'data-testid': 'sheet-close', onclick: () => requestCloseSheet() }, icon('x'));
  const sheet = el('aside', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': o.title, 'data-testid': o.testid || 'sheet' },
    el('div', { class: 'sheet-head' }, el('h2', { text: o.title, class: 'truncate' }), o.headExtra || null, el('span', { class: 'spacer' }), o.help ? el('a', { class: 'btn ghost sm', href: '#/guide' + (o.help ? '?s=' + o.help : ''), onclick: () => closeSheet(true) }, icon('circle-help', 'sm'), 'Help') : null, expand, close),
    body, o.foot ? el('div', { class: 'sheet-foot' }, o.foot) : null);
  const ov = el('div', { class: 'sheet-overlay', onmousedown: () => requestCloseSheet() });
  sheet.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !openMenuEl) { e.preventDefault(); e.stopPropagation(); requestCloseSheet(); } });
  document.body.append(ov, sheet);
  sheetState = { sheet, ov, isDirty: o.isDirty || (() => false), onClose: o.onClose };
  // Focus synchronously: a fast typist's first keys must land in the form.
  const f = sheet.querySelector('[autofocus]') || sheet.querySelector('input, select, textarea');
  if (f) f.focus();
  return sheet;
}
export async function requestCloseSheet() {
  if (!sheetState) return;
  if (sheetState.isDirty()) {
    const ok = await confirmDialog({ title: 'Discard this draft?', body: 'Your unsaved changes are kept as a draft on this device and offered again next time you open this form.', confirmLabel: 'Close', danger: false });
    if (!ok) return;
  }
  closeSheet();
}
export function closeSheet(silent) {
  if (!sheetState) return;
  const st = sheetState; sheetState = null;
  st.sheet.remove(); st.ov.remove();
  if (!silent && st.onClose) st.onClose();
}

// ------------------------------------------------------------------ states
export function skeletonRows(n, cols) {
  const w = el('div', { 'aria-busy': 'true', 'aria-label': 'Loading' });
  for (let i = 0; i < (n || 8); i++) {
    w.appendChild(el('div', { class: 'sk-row' }, el('div', { class: 'skeleton', style: 'width:16px;height:16px' }),
      el('div', { class: 'skeleton', style: 'width:' + (30 + (i * 7) % 25) + '%' }), el('span', { class: 'spacer' }),
      (cols || 2) > 1 ? el('div', { class: 'skeleton', style: 'width:12%' }) : null, el('div', { class: 'skeleton', style: 'width:8%' })));
  }
  return w;
}
export function skeletonBlock(lines) {
  const w = el('div', { class: 'col', style: 'padding:16px 24px', 'aria-busy': 'true' });
  for (let i = 0; i < (lines || 6); i++) w.appendChild(el('div', { class: 'skeleton', style: 'width:' + (90 - (i * 13) % 50) + '%' }));
  return w;
}
export function empty(title, body, action, iconName, help) {
  return el('div', { class: 'empty', 'data-testid': 'empty' }, iconName ? icon(iconName) : null, el('h2', { text: title }), el('p', { text: body }),
    el('div', { class: 'row' }, action || null, help ? el('a', { class: 'btn ghost sm', href: '#/guide?s=' + help, 'data-testid': 'empty-help' }, icon('circle-help', 'sm'), 'How this works') : null));
}
export function errorBox(e, retry) {
  const msg = e.status === 403 ? 'You do not have access to this. Ask an admin for a role that allows it.' :
    e.status === 0 ? e.message : (e.message || 'Something went wrong.') + ' Try again; if it keeps happening, tell the knowledge base admin.';
  return el('div', { class: 'error-box', role: 'alert' }, el('strong', { text: 'Could not load this. ' }), msg,
    retry ? el('div', { style: 'margin-top:8px' }, el('button', { class: 'btn sm', type: 'button', text: 'Try again', onclick: retry })) : null);
}

// ------------------------------------------------------------------ routing helpers
export function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, query] = h.split('?');
  const q = {};
  (query || '').split('&').filter(Boolean).forEach((p) => { const [k, v] = p.split('='); q[decodeURIComponent(k)] = decodeURIComponent(v || ''); });
  return { path: path ? path.split('/') : [''], q };
}
export function setQuery(changes, replace) {
  const r = parseHash();
  const q = Object.assign({}, r.q, changes);
  Object.keys(q).forEach((k) => { if (q[k] === null || q[k] === undefined || q[k] === '') delete q[k]; });
  const url = '#/' + r.path.join('/') + qs(q);
  if (replace) history.replaceState(null, '', url); else history.pushState(null, '', url);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

// ------------------------------------------------------------------ comboboxes
/* A searchable single/multi picker. `source(q)` → [{id, label, sub, icon, node}].
   `create(q)` (optional) → items offered as "Create '<q>'" options. */
export function combobox(o) {
  const chosen = (o.value || []).slice();
  const input = el('input', { placeholder: o.placeholder || 'Search…', 'aria-label': o.label || 'Search', 'data-testid': o.testid, autocomplete: 'off', role: 'combobox', 'aria-expanded': 'false' });
  const box = el('div', { class: 'combo-box', onclick: () => input.focus() });
  const wrap = el('div', { class: 'combo' }, box);
  let menuEl = null, items = [], active = 0;
  function render() {
    clear(box);
    for (const c of chosen) {
      box.appendChild(el('span', { class: 'token', 'data-testid': (o.testid || 'combo') + '-picked' }, c.icon || null, el('span', { class: 'truncate', text: c.label }),
        el('button', { type: 'button', 'aria-label': 'Remove ' + c.label, onclick: (e) => { e.stopPropagation(); chosen.splice(chosen.indexOf(c), 1); render(); changed(); } }, icon('x', 'sm'))));
    }
    input.placeholder = !o.multi && chosen.length ? 'Change…' : (o.placeholder || 'Search…');
    box.appendChild(input);
  }
  function changed() { if (o.onChange) o.onChange(o.multi ? chosen.slice() : (chosen[0] || null)); }
  function closeList() { if (menuEl) { menuEl.remove(); menuEl = null; input.setAttribute('aria-expanded', 'false'); } }
  function pick(it) {
    if (!it) return;
    if (it.isCreate && o.onCreateRequest) { closeList(); input.value = ''; o.onCreateRequest(it, (made) => { if (made) { if (!o.multi) chosen.length = 0; chosen.push(made); render(); changed(); } }); return; }
    if (!o.multi) chosen.length = 0;
    if (!chosen.some((c) => c.id === it.id)) chosen.push(it);
    input.value = ''; closeList(); render(); changed();
    if (o.multi) input.focus();
  }
  const search = debounce(async () => {
    const q = input.value.trim();
    let res = [];
    try { res = await o.source(q); } catch (e) { res = []; }
    if (o.multi) res = res.filter((r) => !chosen.some((c) => c.id === r.id));
    if (q && o.create) res = res.concat(o.create(q).map((c) => Object.assign({ isCreate: true }, c)));
    items = res; active = 0;
    closeList();
    if (!items.length && !q) return;
    menuEl = el('div', { class: 'menu', role: 'listbox', 'data-testid': (o.testid || 'combo') + '-menu' });
    if (!items.length) menuEl.appendChild(el('div', { class: 'menu-label', text: 'No matches' }));
    let group = null;
    items.forEach((it, i) => (it.group && it.group !== group && !it.isCreate ? menuEl.appendChild(el('div', { class: 'menu-label', role: 'presentation', text: (group = it.group) })) : null, menuEl.appendChild(el('button', { type: 'button', role: 'option', 'aria-selected': i === active ? 'true' : 'false',
      'data-testid': it.isCreate ? (o.testid || 'combo') + '-create' : (o.testid || 'combo') + '-option', onmousedown: (e) => { e.preventDefault(); pick(it); } },
      it.isCreate ? icon('plus') : (it.icon || null), el('span', { class: 'truncate', text: it.label }), it.sub ? el('span', { class: 'faint small truncate', text: it.sub }) : null))));
    document.body.appendChild(menuEl);
    const r = box.getBoundingClientRect();
    // Never past the viewport's edges (A4 sweep): clamp the width and the left edge.
    const vw = document.documentElement.clientWidth, w = Math.min(Math.max(r.width, o.menuWidth || 240), vw - 16);
    menuEl.style.width = w + 'px'; menuEl.style.maxWidth = w + 'px'; menuEl.style.left = Math.max(8, Math.min(r.left, vw - w - 8)) + 'px';
    const below = window.innerHeight - r.bottom;
    if (below < 220 && r.top > below) menuEl.style.bottom = (window.innerHeight - r.top + 4) + 'px'; else menuEl.style.top = (r.bottom + 4) + 'px';
    input.setAttribute('aria-expanded', 'true');
  }, 150);
  input.addEventListener('input', search);
  input.addEventListener('focus', () => { if (o.openOnFocus) search(); });
  input.addEventListener('blur', () => setTimeout(closeList, 150));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); if (!menuEl) return search();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      $$('[role=option]', menuEl).forEach((b, i) => b.setAttribute('aria-selected', i === active ? 'true' : 'false'));
    } else if (e.key === 'Enter') { if (menuEl && items.length) { e.preventDefault(); pick(items[active]); } }
    else if (e.key === 'Escape' && menuEl) { e.stopPropagation(); closeList(); }
    else if (e.key === 'Backspace' && !input.value && chosen.length) { chosen.pop(); render(); changed(); }
  });
  render();
  wrap.getValue = () => (o.multi ? chosen.slice() : (chosen[0] || null));
  wrap.setValue = (v) => { chosen.length = 0; [].concat(v || []).forEach((x) => chosen.push(x)); render(); };
  wrap.focus = () => input.focus();
  return wrap;
}

/* Records as combobox items. */
export function nodeSource(types, exclude) {
  return async (q) => {
    const p = await api('GET', '/nodes' + qs({ q, type: (types || []).join(','), limit: 12, sort: q ? 'updated' : 'name' }));
    return p.items.filter((n) => !(exclude || []).includes(n.id)).map(nodeItem);
  };
}
export function nodeItem(n) {
  return { id: n.id, label: n.name, sub: typeLabel(n.type) + (n.scope_name ? ' · ' + n.scope_name : ''), icon: typeIcon(n.type), type: n.type, node: n };
}
export function peopleSource(roles) {
  return async (q) => S.people.filter((p) => (!roles || roles.includes(p.role)) && (!q || p.email.toLowerCase().includes(q.toLowerCase())))
    .slice(0, 12).map((p) => ({ id: p.user_id, label: personName(p.user_id), sub: p.email, icon: avatar(p.user_id) }));
}
