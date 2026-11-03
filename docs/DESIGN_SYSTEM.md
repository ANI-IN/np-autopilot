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
  `public/vendor/inter/`, a 126-icon Lucide subset (ISC; 20 added in run 3) as one SVG sprite in
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
| Page header (run 3) | `pageHead({title, count, sub, actions})` | the one header every screen uses: title, count, one line of context, actions on the right |
| Card | `.card` › `.card-head` + `.card-body` | hairline border, one radius, no shadow; dashboard blocks |
| Tile | `.card.dash-tile` › `.tile` (`.v` value, `.k` label) | dashboard numbers, six equal tiles in `.dash-tiles` |
| Popover | `popover(anchor, content, {alignRight})` | floating panel kept inside the viewport (flips above, clamps at both edges); Esc or outside click closes |
| Segmented switch | `.segmented` with `role=radio` buttons | labelled choices such as row density |
| Check list | `.check-list` | checkbox + label with a 10px gap, drag handle and ↑↓ buttons to reorder |
| Relationship picker | `relCombobox` (relpicker.js) | options read as sentences, grouped "This course …" / "… this course"; "Create relationship '…'" |
| Activity entry | `activityEntry(a)` (views/activity.js) | who · what · which (link or "deleted") · when (exact on hover) · field diffs; Activity page and every History tab |
| Stacked dialog | `openDialog(content, {stack: true})` | opens over another dialog and returns to it on close |
| Graph handles | `.graph-handles` | the hover toolbar beside a record on the graph: connect handle, expand, rename, presence |

Text that can be cut off with "…" always carries its full text as a tooltip:
`el()` adds a `title` to any `.truncate` element given `text`.

## Layout

Sidebar (240px, folds to 56px icons; grouped Workspace · Browse · Maintain, with
counts; Guide, Settings and the user menu at the bottom) | the page | the detail
panel (440px, resizable with the mouse or arrow keys, pushes the list, expands
to a full page at `#/r/<id>`). On screens up to 1280px the sidebar folds while a
record is open, so the list keeps its width. Nothing scrolls horizontally at
1024px (tested for every screen).

### Page template (run 3)

Every screen opens with the same header (`pageHead`), then `.page-body` with
24px side padding and 24px between sections. The router sets `data-layout` on
the view:

| Layout | Screens | Width |
|---|---|---|
| `full` | All records, Programs, Courses, Resources, Graph | the whole width (tables and the canvas use it) |
| `contained` | Dashboard, Outline, Data quality, Approvals, Activity, Archived, Settings | centred, at most `--page-max` (1440px) |
| `reading` | Guide, a record as a page | content `--read-max` (760px) plus contents `--toc-w` (220px), centred together as one unit |

The dashboard fits one screen (run 6, F1): `.dash-grid` holds a row of six
equal tiles (`.dash-tiles`, three per row below 1100px), then three equal
columns (`.dash-cols`) whose cards end level. The old 12-column `.grid-12` /
`.span-*` utilities were removed in F6 (docs/LEGACY_REMOVAL.md).

### Large screens

Below 2561px nothing scales. Above it, type, spacing, row heights, the sidebar,
the panel and the three widths grow with the viewport (`clamp()`, factor =
viewport / 2560, capped at 1.3), so a 3840px screen reads like a 2560px one
rather than a sea of small text. Screenshots at 1280, 1536, 1920, 2560 and
3840px, at 1x and 2x: `docs/redesign/run3/`.

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

Graph (when the canvas has focus): `N` new record · `F` fit · `/` find ·
`Delete` archive the selection · arrows move the selection (Shift: further) ·
`E` expand or collapse · `Esc` clear the selection. Double-click empty space to
create, double-click a record to rename it.
