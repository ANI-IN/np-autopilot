# KB design system

The knowledge base workspace (`public/kb/`) is built on one stylesheet
(`public/kb/kb.css`) and one set of components (`public/kb/js/core.js`). The
standard is a calm, dense, fast tool in the spirit of Linear or Attio: content
first, one accent, no decoration.

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

## Brand

Source: interviewkickstart.com's Elementor kit
(`https://interviewkickstart.com/wp-content/uploads/elementor/css/post-5.css`):
`--e-global-color-primary` / text **#324158** (navy), **#3996D2** (blue),
accent **#00D1B4** (teal), **#F0F3F6** (light grey); typography **Inter**. The
header logo (`.../2025/05/620b3b133ad9178175a0f3bb_interviewkickstart-logo-1.svg`,
fills #344158 and #3996D2) is saved as `public/kb/brand/ik-logo.svg` and shown
on the sign-in card (`.gate-logo`, turned white in dark mode).

How the brand maps to tokens (`--brand-blue` #3996D2, `--brand-navy` #324158):

- light `--accent` / `--accent-text` **#2670A6**: the brand blue darkened to
  5.3:1 for white text (#3996D2 itself is only 3.25:1 on white);
- dark `--accent` **#3996D2** (5.8:1 with the dark label `--on-accent`
  #0b1020), `--accent-text` #6fb8e8;
- `--brand-mark` (the sidebar's "IK" square) navy #324158 light / blue
  #3996D2 dark.

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
| Accent | one: IK blue `--accent` #2670A6 (light) / #3996D2 (dark), `--accent-soft`, `--accent-text`, `--on-accent` (label on the accent); `--brand-blue`, `--brand-navy`, `--brand-mark` (see Brand) |
| Status | `--danger`, `--warn`, `--ok` with `-soft` backgrounds |
| Elevation | `--shadow-float` on floating layers only (menus, dialogs, sheets, toasts, bulk bar, minimap) |
| Motion | `--motion` 150ms ease-out; 0ms under `prefers-reduced-motion` |
| Layout | `--sidebar-w` 240 (56 folded), `--panel-w` 440 (resizable 360–860), `--row-h` 36 / 30 compact |

The accent is the Interview Kickstart blue (see Brand; this replaces PROGRESS
D18's restrained deep blue, chosen when no brand colour was recorded). Never
purple.

**Record-type hues** come from one accessible palette (`web/lib/kb/typedefs.py`
`PALETTE`, applied to the built-in types by migration 0028). They colour a
type's icon and dot only, never text or surfaces. In dark mode icons are
lightened with `color-mix` to keep contrast.

**Contrast** (WCAG AA, computed from the token values): body `--text` on `--bg`
17.7:1 (light) / 16.1:1 (dark); `--text-2` 7.7 / 8.1; `--text-3` 5.3 / 5.8 (4.9 / 5.6
on the sidebar); accent text 5.3 / 8.8; button label on the accent 5.3 / 5.8.
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
| Dashboard (run 6) | `.dash` › `.dash-grid` › `.dash-tiles` + `.dash-cols` of `.dash-card`; `.dash-entry`, `.dash-sentence`, `.dash-first`, `.dash-actions`, `.dash-sub`, `.dash-types` | one screen, no 12-column grid (views/dashboard.js) |
| Run-6 classes (B3) | `.tab-intro`, `.settings-body`, `.inline-form`, `.field-card`, `.type-editor`, `.editor-error`, `.swatch`, `.subhead`, `.record-page`, `.record-head`, `.record-meta`, `.text-block`, `.section`, `.rel-group-label`, `.conflict-diff`, `.impact-list`, `.url-line`, `.proposal-json`, `.queue`, `.form-note`, `.form-error`, `.link-card`, `.form-section`, `.figure-zoom`, `.view-toolbar`, `.timeline-head`, `.deck-list`, `.missing-col`, `.gate-card`, `.gate-logo` | the former inline styles of each screen, as classes (kb.css "run 6 (B3)") |
| Popover | `popover(anchor, content, {alignRight})` | floating panel kept inside the viewport (flips above, clamps at both edges); Esc or outside click closes |
| Segmented switch | `.segmented` with `role=radio` buttons | labelled choices such as row density |
| Check list | `.check-list` | checkbox + label with a 10px gap, drag handle and ↑↓ buttons to reorder |
| Relationship picker | `relCombobox` (relpicker.js) | options read as sentences, grouped "This course …" / "… this course"; "Create relationship '…'" |
| Activity entry | `activityEntry(a)` (views/activity.js) | who · what · which (link or "deleted") · when (exact on hover) · field diffs; Activity page and every History tab |
| Stacked dialog | `openDialog(content, {stack: true})` | opens over another dialog and returns to it on close |
| Graph handles | `.graph-handles` | the hover toolbar beside a record on the graph: connect handle, expand, rename, presence |

**Utilities (run 6, B3)** on the 8px grid, replacing inline styles (only
data-driven values such as a type's colour or a bar's percentage stay inline):
`.grow`, `.flex-none`, `.wrap`, `.start`, `.self-start`, `.nowrap`,
`.pre-wrap`, `.right`, `.relative`, `.w-full`, `.fg`, `.min-w-0`,
`.justify-end`, `.gap-0`/`-xs`/`-1`/`-2`/`-3`/`-5`, `.mb-1`–`3`, `.mt-1`–`5`,
`.ml-2`, `.num-col`, `.toolbar-gap`, `.search-sm`, `.th-check`, `.th-when`,
`.ico-slot`, `.indent`, `.sk-icon`, `.sk-block`, `.load-more`, `.panel-note`.

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
| `full` | All records, Programs, Courses, Links, Graph | the whole width (tables and the canvas use it) |
| `contained` | Dashboard, Outline, Data quality, Approvals, Activity, Archived, Settings | centred, at most `--page-max` (1440px) |
| `reading` | Guide, a record as a page | content `--read-max` (760px) plus contents `--toc-w` (220px), centred together as one unit |

The dashboard fits one screen (run 6, F1): `.dash-grid` holds a row of six
equal tiles (`.dash-tiles`, three per row below 1100px), then three equal
columns (`.dash-cols`) whose cards end level. The old 12-column `.grid-12` /
`.span-*` utilities were removed in F6 (docs/operations/legacy-removal.md).

### Large screens

Below 2561px nothing scales. Above it, type, spacing, row heights, the sidebar,
the panel and the three widths grow with the viewport (`clamp()`, factor =
viewport / 2560, capped at 1.3), so a 3840px screen reads like a 2560px one
rather than a sea of small text.

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

Graph (when the canvas has focus): `?` the shortcut sheet · `N` new record ·
`F` fit · `/` find · `+` / `-` zoom in / out · `1`-`4` layouts (Hierarchy ·
Force · Radial · Saved positions) · `O` focus mode (off, 1 step, 2 steps) ·
`M` minimap · `Delete` archive the selection · arrows move the selection
(Shift: further) · `E` expand or collapse · `Esc` clear the selection. Double-click empty space to
create, double-click a record to rename it.
