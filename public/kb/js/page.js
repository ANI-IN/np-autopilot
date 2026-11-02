/* The one page template (run 3, B1): every screen opens with the same header —
   title, optional count, one line of context, actions on the right — and the
   same content padding, section spacing and max widths (kb.css "page
   template"). */
import { el } from './core.js';

export function pageHead(o) {
  return el('div', { class: 'page-head', 'data-testid': 'page-head' },
    el('div', { class: 'page-title' }, el('h1', { text: o.title }),
      o.count !== undefined && o.count !== null ? el('span', { class: 'count title-count', 'data-testid': 'page-count', text: String(o.count) }) : null),
    o.sub ? el('span', { class: 'sub', text: o.sub }) : null,
    el('span', { class: 'spacer' }),
    o.actions ? el('div', { class: 'page-actions' }, o.actions) : null);
}
