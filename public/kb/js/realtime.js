/* Supabase Realtime over a plain WebSocket (Phoenix channel protocol), with
   presence. Used only when GET /api/kb/realtime returns a configuration, which
   the server does only when the deployment allows that origin in the security
   policy's connect-src (KB_REALTIME_ORIGIN; see docs/DEPLOYMENT.md). Otherwise
   this is a no-op and live.js polls. Any socket error → onDown → polling.

   The socket only says THAT something changed (a kb.changes insert (0029), which
   Realtime filters through the same RLS as every read); live.js then fetches
   the change rows through the API as before. */
import { S, api } from './core.js';

let ws = null, cfg = null, ref = 0, hb = null, handlers = null, retry = 0, joinRef = null;
const presenceListeners = [];
let presence = {};                 // presence key -> [metas]
let tracked = null;
const TOPIC = 'realtime:kb-changes';

export async function connectRealtime(h) {
  handlers = h;
  try { cfg = await api('GET', '/realtime'); } catch (e) { cfg = null; }
  if (!cfg || !cfg.url || !cfg.key) return;
  open();
}

function send(topic, event, payload) {
  if (!ws || ws.readyState !== 1) return null;
  ref += 1;
  ws.send(JSON.stringify({ topic, event, payload, ref: String(ref), join_ref: joinRef || String(ref) }));
  return String(ref);
}

function open() {
  const url = cfg.url.replace(/^http/, 'ws') + '/realtime/v1/websocket?apikey=' + encodeURIComponent(cfg.key) + '&vsn=1.0.0';
  try { ws = new WebSocket(url); } catch (e) { handlers.onDown(); return; }
  ws.onopen = () => {
    retry = 0;
    joinRef = null;
    joinRef = send(TOPIC, 'phx_join', {
      config: { broadcast: { self: false }, presence: { key: S.me.user_id },
        postgres_changes: [{ event: 'INSERT', schema: 'kb', table: 'changes' }] },
      access_token: S.session.access_token,
    });
    hb = setInterval(() => send('phoenix', 'heartbeat', {}), 25000);
  };
  ws.onmessage = (m) => {
    let msg; try { msg = JSON.parse(m.data); } catch (e) { return; }
    // Only the reply to OUR join decides up/down (track and other pushes reply too).
    if (msg.event === 'phx_reply' && msg.topic === TOPIC && msg.ref === joinRef) {
      if (msg.payload && msg.payload.status === 'ok') { handlers.onUp(); if (tracked) track(tracked); }
      else { handlers.onDown(); ws.close(); }
    } else if (msg.event === 'postgres_changes') handlers.onChange(msg.payload);
    else if (msg.event === 'presence_state') { presence = {}; mergePresence(msg.payload, {}); }
    else if (msg.event === 'presence_diff') mergePresence(msg.payload.joins || {}, msg.payload.leaves || {});
    else if (msg.event === 'phx_error' || msg.event === 'system' && msg.payload && msg.payload.status === 'error') { handlers.onDown(); }
  };
  ws.onclose = () => {
    clearInterval(hb); handlers.onDown();
    retry += 1;
    if (retry <= 6) setTimeout(open, Math.min(30000, 1000 * Math.pow(2, retry)));
  };
  ws.onerror = () => { /* onclose follows */ };
}

function mergePresence(joins, leaves) {
  Object.entries(joins).forEach(([k, v]) => { presence[k] = (v.metas || []); });
  Object.keys(leaves).forEach((k) => { if (!joins[k]) delete presence[k]; });
  presenceListeners.forEach((fn) => fn(presence));
}

/* Announce what this person is looking at / editing. */
export function track(state) {
  tracked = state;
  send(TOPIC, 'presence', { type: 'presence', event: 'track', payload: Object.assign({ user_id: S.me.user_id }, state) });
}
export function onPresence(fn) { presenceListeners.push(fn); return () => { const i = presenceListeners.indexOf(fn); if (i >= 0) presenceListeners.splice(i, 1); }; }
export function others(recordId) {
  const out = [];
  Object.entries(presence).forEach(([k, metas]) => {
    if (k === S.me.user_id) return;
    const m = metas[metas.length - 1];
    if (m && m.record === recordId) out.push({ user_id: k, editing: !!m.editing });
  });
  return out;
}
export function realtimeActive() { return !!(ws && ws.readyState === 1); }
