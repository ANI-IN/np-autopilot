/* Guide: renders public/kb/guide.md — ONE plain-text file anyone can edit.
   Supported markdown: # ## ### headings, paragraphs, - and 1. lists,
   ![caption](/kb/guide/x.png), **bold**, `code`, [text](link). Everything is
   built with el()/textContent: the file is never injected as HTML. */
import { el, add, clear, skeletonBlock, errorBox, openDialog, closeDialog, icon } from '../core.js';

function inline(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith('**')) out.push(el('strong', { text: t.slice(2, -2) }));
    else if (t.startsWith('`')) out.push(el('code', { text: t.slice(1, -1) }));
    else { const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(t); const href = /^(#|\/|https?:)/.test(mm[2]) ? mm[2] : '#'; out.push(el('a', { href, text: mm[1] })); }
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function lightbox(src, alt) {
  openDialog([el('div', { class: 'row' }, el('h2', { class: 'truncate', text: alt || 'Screenshot' }), el('span', { class: 'spacer' }),
    el('button', { class: 'btn ghost icon', type: 'button', 'aria-label': 'Close', onclick: closeDialog }, icon('x'))),
  el('img', { src, alt: alt || '', class: 'lightbox-img', 'data-testid': 'guide-lightbox' })], { label: alt || 'Screenshot', wide: true, cls: 'lightbox' });
}
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export function render(md) {
  const doc = el('article', { class: 'guide', 'data-testid': 'guide' });
  const toc = [];
  let list = null, para = [];
  const flush = () => { if (para.length) { doc.appendChild(el('p', null, inline(para.join(' ')))); para = []; } };
  md.split(/\r?\n/).forEach((line) => {
    const img = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/.exec(line.trim());
    let m;
    if (!line.trim()) { flush(); list = null; return; }
    if ((m = /^(#{1,3})\s+(.*)$/.exec(line))) {
      flush(); list = null;
      const lvl = m[1].length, id = slug(m[2]);
      doc.appendChild(el('h' + lvl, { id: 'g-' + id, text: m[2] }));
      if (lvl === 2) toc.push([id, m[2]]);
      return;
    }
    if (img) {
      flush(); list = null;
      const src = img[2].startsWith('/kb/guide/') ? img[2] : '';
      // Click (or Enter) to see the screenshot full size (A6).
      doc.appendChild(el('figure', null, el('button', { class: 'figure-zoom', type: 'button', 'aria-label': 'Enlarge: ' + (img[1] || 'screenshot'), 'data-testid': 'guide-figure', onclick: () => lightbox(src, img[1]) },
        el('img', { src, alt: img[1], loading: 'lazy', decoding: 'async' })), img[1] ? el('figcaption', { text: img[1] }) : null));
      return;
    }
    if ((m = /^\s*(-|\d+\.)\s+(.*)$/.exec(line))) {
      flush();
      const ordered = m[1] !== '-';
      if (!list || list.tagName !== (ordered ? 'OL' : 'UL')) { list = el(ordered ? 'ol' : 'ul'); doc.appendChild(list); }
      list.appendChild(el('li', null, inline(m[2])));
      return;
    }
    list = null; para.push(line.trim());
  });
  flush();
  return { doc, toc };
}

export function viewGuide(v, r) {
  const box = el('div', { class: 'guide-layout' }, skeletonBlock(12));
  v.appendChild(box);
  fetch('/kb/guide.md', { cache: 'no-store' }).then((res) => { if (!res.ok) throw new Error('The guide could not be loaded (' + res.status + ').'); return res.text(); }).then((md) => {
    const { doc, toc } = render(md);
    clear(box);
    box.append(doc, el('nav', { class: 'guide-toc', 'aria-label': 'Guide contents' }, el('div', { class: 'faint xs', text: 'On this page', style: 'margin-bottom:6px' }),
      toc.map(([id, t]) => el('a', { href: '#/guide?s=' + id, onclick: (e) => { e.preventDefault(); const h = document.getElementById('g-' + id); if (h) h.scrollIntoView({ behavior: 'smooth' }); }, text: t }))));
    const want = r.q.s;
    if (want) { const h = document.getElementById('g-' + want) || Array.from(doc.querySelectorAll('h2')).find((x) => x.id.includes(want)); if (h) setTimeout(() => h.scrollIntoView(), 50); }
  }).catch((e) => { clear(box).appendChild(errorBox(e)); });
}
