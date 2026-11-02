# KB design system

The knowledge base workspace (`public/kb/`) is built on one stylesheet
(`public/kb/kb.css`) and one set of components (`public/kb/js/core.js`). The
standard is a calm, dense, fast tool in the spirit of Linear or Attio: content
first, one accent, no decoration.

Before/after screenshots at 1440, 1280 and 1024px: `docs/redesign/before/` and
`docs/redesign/after/`.

## Technology decision

**Vanilla JavaScript ES modules, no framework, no build step** (PROGRESS D17).

- The repo has no JS toolchain. The app is one Python WSGI function plus static
  files on Vercel, and the security policy allows scripts only from the same
  origin (`script-src 'self'`). Native ES modules satisfy that policy with zero
  tooling: `index.html` loads `/kb/js/app.js` as a module and the browser
  resolves the imports.
- About ten screens with shared components do not need a virtual DOM. A
  framework would add a bundler, a dependency tree to audit and a second deploy
  surface for no capability the brief needs.
- Everything is self-hosted: Inter (variable woff2, OFL) in
  `public/vendor/inter/`, a 106-icon Lucide subset (ISC) as one SVG sprite in
  `public/vendor/lucide-sprite.svg`, Cytoscape.js for the graph. No CDN, no
  Google Fonts: `default-src 'self'` holds.
- Every value from the API is rendered with `textContent` via `el()`. The Guide's
  markdown is parsed into elements; `innerHTML` is never given data.

Files:

| File | Contents |
|---|---|
| `public/kb/kb.css` | tokens, components, layouts |
| `public/kb/js/core.js` | `el`, `icon`, API client, toast, dialog, confirm (incl. typed confirmation), menu, side sheet, combobox, skeletons, empty and error states, routing helpers |
| `public/kb/js/app.js` | boot, sidebar, router, ⌘K palette, keyboard shortcuts |
| `public/kb/js/detail.js` | record and resource detail (panel and full page) |
| `public/kb/js/form.js` | New record / edit sheet, link and relationship rows, field inputs |
| `public/kb/js/live.js`, `realtime.js` | change feed polling, Supabase Realtime + presence |
| `public/kb/js/views/*.js` | one module per screen |
| `public/kb/guide.md` | the Guide's content (one plain-text file) |

## Tokens

All colours, sizes and motion are custom properties on `:root`, redefined for
dark mode under `prefers-color-scheme: dark` (unless `data-theme="light"`) and
under `[data-theme="dark"]`. The user menu toggles System / Light / Dark; the
choice is remembered per browser.

| Group | Tokens |
|---|---|
| Type | `--font` Inter; `--fs-xs` 12, `--fs-sm` 13 (tables), `--fs-md` 14 (body), `--fs-lg` 16, `--fs-title` 20 (page titles, semibold). Two weights only: 400 and 600. Tabular numbers in counts and percentages. |
| Space | 8px grid: `--s-1` 4 … `--s-7` 48 |
| Shape | one radius, `--radius: 6px`; hairline 1px borders |
| Neutrals | `--bg`, `--bg-subtle` (sidebar), `--surface`, `--surface-2`, `--surface-hover`, `--border`, `--border-strong`, `--text`, `--text-2`, `--text-3` |
| Accent | one: deep blue `--accent` #1d4ed8 (light) / #5b8cff (dark), `--accent-soft`, `--accent-text` |
| Status | `--danger`, `--warn`, `--ok` with `-soft` backgrounds |
| Elevation | `--shadow-float` on floating layers only (menus, dialogs, sheets, toasts, bulk bar, minimap) |
| Motion | `--motion` 150ms ease-out; 0ms under `prefers-reduced-motion` |
| Layout | `--sidebar-w` 240 (56 folded), `--panel-w` 440 (resizable 360–860), `--row-h` 36 / 30 compact |

No IK brand colour is recorded in the repo (PROGRESS D18), so the accent is a
restrained deep blue. Never purple.

**Record-type hues** come from one accessible palette (`web/lib/kb/typedefs.py`
`PALETTE`, applied to the built-in types by migration 0028). They colour a
type's icon and dot only, never text or surfaces. In dark mode icons are
lightened with `color-mix` to keep contrast.

**Contrast** (WCAG AA, computed from the token values): body `--text` on `--bg`
17.7:1 (light) / 16.1:1 (dark); `--text-2` 7.7 / 8.1; `--text-3` 5.3 / 5.8 (4.9 / 5.6
on the sidebar); accent text 6.7 / 8.9; button label on the accent 6.7 / 6.0.
Every palette hue is at least 4.9:1 on white (the AA threshold for icons is 3:1).

## Components

| Component | Class / function | Notes |
|---|---|---|
| Button | `.btn` `.primary` `.ghost` `.danger` `.sm` `.icon` | 32px (26 small); one primary per area |
| Input, select, textarea | native elements, styled | 32px; focus ring from `--accent` |
| Field | `label.field > .label + control + .help` | `.req` adds the required star; `.invalid` turns the control red |
| Combobox | `combobox({source, create, multi})` | search, keyboard (↑↓ Enter Esc Backspace), tokens, inline "Create '…'" |
| Menu | `menu(anchor, items)` | keyboard navigable; `checked` items show a check icon |
| Dialog | `openDialog`, `confirmDialog({typeToConfirm, withReason})` | Esc closes; focus returns to the opener |
| Side sheet | `openSheet({title, body, foot, isDirty})` | 640px, expandable to full page; asks before discarding a dirty form |
| Table | `.table` in `.table-wrap` | sticky header, 36/30px rows, hover actions that fade in (keyboard reachable), selection |
| Badge | `.badge` `.accent` `.ok` `.warn` `.danger` | status only when not "live" |
| Tabs | `.tabs` with `role=tab` / `aria-selected` | |
| Toast | `toast(msg, {actions})` | bottom right; actions like Open / Undo |
| Skeleton | `skeletonRows`, `skeletonBlock` | shaped like the content they replace; pulse, not shimmer |
| Empty state | `empty(title, sentence, action, icon)` | one sentence, one action, left aligned |
| Error | `errorBox(e, retry)` | says what to do; permission errors say who to ask |
| Avatar | `avatar(userId)` | initials on a stable hue; dashed outline when nobody owns it |
| Link row | `.link-row`, `linkRow(resource)` | service icon, title, kind, domain, purpose, owner, health |
| Properties | `dl.props` | 120px label column |
| Progress | `.bar` `.ok` `.warn` `.danger` | completeness |

## Layout

Sidebar (240px, folds to 56px icons; grouped Workspace · Browse · Maintain, with
counts; Guide, Settings and the user menu at the bottom) | the page | the detail
panel (440px, resizable with the mouse or arrow keys, pushes the list, expands
to a full page at `#/r/<id>`). On screens up to 1280px the sidebar folds while a
record is open, so the list keeps its width. Nothing scrolls horizontally at
1024px (tested for every screen).

## Banned (and checked against every after-screenshot)

Gradients, glassmorphism, glows, emoji as icons, purple accents, card grids for
tabular data, centred heroes, filler copy, Title Case labels, decorative
illustrations, mixed icon sets (Lucide only), shadows on non-floating
elements, more than one radius, placeholder or never-enabled buttons, fake
numbers (every number on the dashboard is a query).

## Keyboard

⌘K / Ctrl K palette (search, create any type, go to any page) · `c` new record ·
`/` table search · `j` / `k` move · `Enter` open · `x` select · `e` edit the open
record · `Esc` closes the innermost layer · ⌘/Ctrl Enter saves a form. Every
control is reachable with Tab; menus and comboboxes use arrow keys.
