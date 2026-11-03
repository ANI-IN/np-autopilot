/* Live updates. Supabase Realtime when the deployment provides it (D2), with
   the RLS-scoped change feed (/api/kb/changes) polled as the automatic
   fallback whenever the socket is unavailable or drops. Either way, listeners
   get the same audit-row shaped changes.

   Run 6 (B1): ONE live-update policy for every page (docs/CONTRACTS.md §2).
   Every change carries `kind` and `node_ids`. A page patches the records named
   in `node_ids`; a type, relationship-type, tag or sync change, or more than
   200 changes at once, means "refetch" instead. Without being asked, this
   module keeps the open list / outline / dashboard / Data quality / Who
   teaches what page (S.listReload) current (the open record follows on its
   own, detail.js), unless the
   person is typing or a dialog is open (then it waits for the next poll). The
   polling interval is 2.5 s while the tab is visible, so a change made
   anywhere shows within 5 s even without Realtime. */
import { S, api, $, clear, el, add } from './core.js';
import { connectRealtime } from './realtime.js';

const POLL_MS = 2500;
const listeners = [], feedListeners = [];
let fails = 0, timer = null, socketUp = false, pending = null;

/* fn(others, all): `others` leaves out your own human writes (they are already
   on your screen); `all` is every change. */
/* Each returns an unsubscribe function: a view that subscribes per visit must call it when it is left (run 6, F7). */
export function onLiveChange(fn) { listeners.push(fn); return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); }; }
/* fn(changes, info) for every batch, yours included; info = classify(changes). */
export function onLiveFeed(fn) { feedListeners.push(fn); return () => { const i = feedListeners.indexOf(fn); if (i >= 0) feedListeners.splice(i, 1); }; }

const PATCH = ['record.', 'relationship.', 'link.', 'layout.', 'owner.'];
const REFETCH = ['type.', 'reltype.', 'tag.', 'sync.'];
export const REFETCH_OVER = 200;
export function classify(changes) {
  const kinds = changes.map((c) => String(c.kind || c.table_name + '.' + c.action));
  const starts = (list) => kinds.some((k) => list.some((p) => k.indexOf(p) === 0));
  const ids = new Set();
  changes.forEach((c) => (c.node_ids || []).forEach((i) => ids.add(String(i))));
  const types = kinds.some((k) => k.indexOf('type.') === 0 || k.indexOf('reltype.') === 0);
  const refetch = changes.length >= REFETCH_OVER || starts(REFETCH);   // a full poll page may have more behind it
  return { ids, types, refetch, relevant: refetch || starts(PATCH), kinds };
}

function emit(changes) {
  const others = changes.filter((c) => c.actor_id !== S.me.user_id || c.actor_type !== 'human');
  listeners.forEach((fn) => { try { fn(others, changes); } catch (e) { console.warn('live listener', e); } });
  const info = classify(changes);
  feedListeners.forEach((fn) => { try { fn(changes, info); } catch (e) { console.warn('live listener', e); } });
  if (info.relevant) refreshViews(info);
}

function busy() {
  const a = document.activeElement;
  const typing = a && (/INPUT|TEXTAREA|SELECT/.test(a.tagName) || a.isContentEditable) && !a.closest('.palette') && a.type !== 'search';
  return !!(typing || $('#dialog-overlay') || $('.sheet'));
}
async function refreshViews(info) {
  if (pending) { pending.types = pending.types || info.types; info.ids.forEach((i) => pending.ids.add(i)); return; }
  if (busy()) { pending = { types: info.types, ids: new Set(info.ids) }; return; }
  try {
    if (info.types) { const app = await import('./app.js'); await app.loadTypes(); }
    if (S.listReload) S.listReload();       // the open record follows on its own (detail.js)
    S.liveApplied = (S.liveApplied || 0) + 1;
  } catch (e) { console.warn('live refresh', e); }
}

export function startLive() {
  api('GET', '/changes').then((r) => { S.feedCursor = r.cursor; }).catch(() => {}).finally(schedule);
  connectRealtime({
    onUp: () => { socketUp = true; },
    onDown: () => { socketUp = false; },
    onChange: () => tick(true),          // the socket says "something changed": fetch the RLS-scoped rows
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) schedule(); });
}
function schedule() {
  clearTimeout(timer);
  const ms = socketUp ? POLL_MS * 8 : (document.hidden ? POLL_MS * 6 : Math.min(POLL_MS * Math.pow(2, fails), 60000));
  timer = setTimeout(() => tick(false), ms);
}
async function tick(fromSocket) {
  try {
    if (pending && !busy()) { const p = pending; pending = null; refreshViews({ types: p.types, ids: p.ids, refetch: false, relevant: true }); }
    if (S.feedCursor === null || S.feedCursor === undefined) S.feedCursor = (await api('GET', '/changes')).cursor;
    else {
      const r = await api('GET', '/changes?since=' + encodeURIComponent(S.feedCursor) + '&limit=500');
      S.feedCursor = r.cursor; fails = 0;
      if (r.changes.length) emit(r.changes);
    }
  } catch (e) { fails = Math.min(fails + 1, 5); }
  if (!fromSocket) schedule();
}

export function showLive(msg, action) {
  const b = clear($('#live-banner')); b.hidden = false; b.setAttribute('data-testid', 'live-banner');
  add(b, [el('span', { text: msg }), el('span', { class: 'spacer' }),
    action ? el('button', { class: 'btn sm', type: 'button', text: action.label, onclick: () => { hideLive(); action.fn(); } }) : null,
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Dismiss', onclick: hideLive })]);
}
export function hideLive() { $('#live-banner').hidden = true; }
