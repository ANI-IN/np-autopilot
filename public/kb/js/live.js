/* Live updates. Supabase Realtime when the deployment provides it (D2), with
   the RLS-scoped change feed (/api/kb/changes) polled as the automatic
   fallback whenever the socket is unavailable or drops. Either way, listeners
   get the same audit-row shaped changes. */
import { S, api, $, clear, el, add } from './core.js';
import { connectRealtime } from './realtime.js';

const POLL_MS = 4000;
const listeners = [];
let fails = 0, timer = null, socketUp = false;

export function onLiveChange(fn) { listeners.push(fn); }
function emit(changes) { const others = changes.filter((c) => c.actor_id !== S.me.user_id || c.actor_type !== 'human'); listeners.forEach((fn) => fn(others, changes)); }

export function startLive() {
  api('GET', '/changes').then((r) => { S.feedCursor = r.cursor; }).catch(() => {}).finally(schedule);
  connectRealtime({
    onUp: () => { socketUp = true; },
    onDown: () => { socketUp = false; },
    onChange: () => tick(true),          // the socket says "something changed": fetch the RLS-scoped rows
  });
}
function schedule() {
  clearTimeout(timer);
  const ms = socketUp ? POLL_MS * 8 : (document.hidden ? POLL_MS * 3 : Math.min(POLL_MS * Math.pow(2, fails), 60000));
  timer = setTimeout(() => tick(false), ms);
}
async function tick(fromSocket) {
  try {
    if (S.feedCursor === null || S.feedCursor === undefined) S.feedCursor = (await api('GET', '/changes')).cursor;
    else {
      const r = await api('GET', '/changes?since=' + encodeURIComponent(S.feedCursor));
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
