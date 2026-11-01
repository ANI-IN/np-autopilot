# KB design system (`public/kb/kb.css`)

Tokens on `:root`; dark theme via `prefers-color-scheme` (and `data-theme` to
force either). Components use tokens only.

## Tokens

| Group | Tokens |
|---|---|
| Surfaces | `--bg` page · `--surface` cards/panels · `--surface-2` sidebar, headers · `--surface-3` pills, hover |
| Lines | `--border`, `--border-strong` |
| Text | `--text`, `--text-2` (secondary), `--text-3` (labels, timestamps) |
| Accent | `--accent`, `--accent-2` (hover), `--accent-soft` (selection), `--on-accent` |
| Status | `--ok/-soft`, `--warn/-soft`, `--danger/-2/-soft` |
| Focus | `--focus` — 3px accent ring on every `:focus-visible` |
| Radius | `--r-1` 4 · `--r-2` 6 · `--r-3` 10 |
| Space | `--s-1`…`--s-6` = 4 · 8 · 12 · 16 · 24 · 32 |
| Type | Inter/system UI; `--t-xs` 11 · `--t-sm` 12.5 · `--t-md` 14 · `--t-lg` 16 · `--t-xl` 20 · `--t-2xl` 26; `--mono` for URLs/ids |
| Layout | `--sidebar-w` 232 · `--panel-w` 440 |

Node-type colours come from `kb.node_types.color` (configurable), shown as a dot
in a `.pill`, and as node fill in the graph.

## Components

`.btn` (+ `primary`, `danger`, `danger solid`, `ghost`, `sm`) · inputs/selects
with focus ring · `label.field` · `.card`/`.cards` · `.table` (row hover,
`selected`) · `.pill` (+ `ok`/`warn`/`danger`, type dot) · `.list` · `.empty`
(empty state with action) · `.error-box` (with retry) · `.skeleton` (shimmer,
disabled under `prefers-reduced-motion`) · `.toast` (+ `err`, optional action
e.g. Undo) · `.overlay` + `.modal` / `.palette` · `.picker` (search menu, inline
"＋ Create …") · `.picked` chip · `.inline-edit` (click/Enter to edit, Esc to
cancel, blur saves) · `.diff` (conflict dialog: mine vs theirs) · `.live-banner`
(someone else changed this) · `.legend` (graph filters).

## Patterns

- **Every destructive action confirms** and shows its impact first (archive shows
  relationships/resource links archived with it; restore brings them back).
  Contributors see "Propose …" and the action becomes an approval request.
- **No dead controls.** Controls a role cannot use are not rendered (viewers see
  no create/edit/connect; only admins see roles and types).
- **Loading → skeleton; empty → explanation + next action; error → message +
  Try again.**
- **Keyboard:** Ctrl/⌘K palette (search, quick-create, navigation; ↑↓ Enter Esc);
  rows focusable with Enter to open; Esc closes palette → modal → panel; modals
  restore focus.
- **Responsive:** ≥1100px three columns; below, the side panel overlays; ≤780px
  the sidebar becomes a top bar. Tested at tablet width (820px) with no horizontal
  scroll (`tests/test_kb_e2e.py::test_tablet_width_layout_and_tokens`).
- **Safety:** all API text is rendered via `textContent`; `innerHTML` never
  receives data. External links open with `rel="noopener noreferrer"`.
