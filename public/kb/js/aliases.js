/* Old addresses that people may have bookmarked, and where they live now
   (run 6, F6; docs/operations/legacy-removal.md "Redirects"). No DOM, no imports, so a
   test can load it with node. The router (app.js) replaces the address, so the
   old one does not stay in the browser history.

   Each key is a first path segment that is NOT a page; the value is the page
   it became (with its own query, if any). A query on the old address is kept,
   except where the target sets the same key. */
export const ALIASES = {
  links: 'resources',                    // the sidebar says "Links" (F2); the page is #/resources
  people: 'settings?tab=people',         // People is a Settings tab (B1), never its own page
  members: 'settings?tab=members',
  sync: 'settings?tab=sync',
  tokens: 'settings?tab=tokens',
  reviews: 'approvals?tab=reviews',      // Reviews is a tab of Approvals
  dashboard: '',                         // the dashboard is #/
  'program-timeline': 'timeline',        // "Programme timeline" became "Program timeline" (F2)
  'programme-timeline': 'timeline',
  'who-teaches-what': 'teaching',
  record: 'r',                           // #/record/<id> -> #/r/<id>
};

/* The new hash for an old one, or null when the address is not an alias.
   path: the hash's path segments; q: its query (parseHash's shape). */
export function aliasTarget(path, q) {
  const key = (path && path[0]) || '';
  if (!Object.prototype.hasOwnProperty.call(ALIASES, key)) return null;
  const [tpath, tquery] = ALIASES[key].split('?');
  const query = {};
  (tquery || '').split('&').filter(Boolean).forEach((p) => { const [k, v] = p.split('='); query[k] = v || ''; });
  Object.keys(q || {}).forEach((k) => { if (!(k in query)) query[k] = q[k]; });
  const rest = (path || []).slice(1).filter(Boolean);
  const segs = [tpath].concat(rest).filter((s, i) => i === 0 || s);
  const qs = Object.keys(query).map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(query[k])).join('&');
  return '#/' + segs.join('/') + (qs ? '?' + qs : '');
}
