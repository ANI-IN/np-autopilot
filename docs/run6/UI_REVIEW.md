# Run 6 — UI review (B3)

Every KB screen, before and after, at 1536px light (the demo data). Extra sets for the
main screens: `after/demo-1280/`, `after/demo-1920/`, `after/demo-2560/` and
`after/demo-dark/` (1536px, dark). The "/" map is not part of this review (B1, B2).

How it was checked, besides looking:

- `eval/kb_ui_sweep.py` opens every screen (and, with `--layers`, the record panel and
  page, its tabs and menu, the New record sheet, the palette, the user menu, the View
  popover, the type editor and a relationship-type dialog) at 1024, 1280, 1536, 1920 and
  2560px in both themes on the real-data copy, and reports horizontal scroll, text cut
  off without a tooltip, unnamed controls and console errors. Final run: 0 problems
  (the real-data Data quality page needs more than 45 s to load; see the report).
- `eval/kb_screens.py` (the lead's script) took the after sets: 0 console errors and
  0 warnings on all 28 screens, in every set.
- `tests/test_kb_ui_run6.py` keeps it that way (34 tests).

| Screen | Before | After | What changed |
|---|---|---|---|
| Sign-in (`/local-login`, demo server only) | [before](before/demo/00-sign-in.png) | [after](after/demo/00-sign-in.png) | Unchanged (eval-only page). The real sign-in gate in `public/kb/index.html` now has a heading (`h1`) and a labelled region for screen readers. |
| Dashboard | [before](before/demo/01-dashboard.png) | [after](after/demo/01-dashboard.png) | Same layout; inline styles became classes (type column, number column, bars). Focus ring on tiles and rows. |
| All records | [before](before/demo/02-records.png) | [after](after/demo/02-records.png) | Header built with `pageHead` like every other screen: the count sits by the title in the shared count style (it was a separate grey "sub" line). |
| Programs | [before](before/demo/03-programs.png) | [after](after/demo/03-programs.png) | As All records. |
| Courses | [before](before/demo/04-courses.png) | [after](after/demo/04-courses.png) | As All records. |
| Resources → **Links** | [before](before/demo/05-resources.png) | [after](after/demo/05-resources.png) | Titled **Links** (the term used everywhere else), `pageHead`, count reads "100+ links" instead of "100 links+". Column widths are classes. |
| Outline | [before](before/demo/06-outline.png) | [after](after/demo/06-outline.png) | Unchanged layout; the before shot caught the skeleton. |
| Graph (chrome only) | [before](before/demo/07-graph.png) | [after](after/demo/07-graph.png) | No change (the canvas and its page are B2's). |
| Who teaches what | [before](before/demo/08-teaching.png) | [after](after/demo/08-teaching.png) | Column headers were clipped to 3–4 letters ("Bui", "Che"): the matrix now sizes columns to content, headers turn and stop at 160px with "…", and each header's tooltip gives the full name, kind and domains. One radius, regular weight, `scope` on headers, toolbar on the page padding. "instructors × modules and live sessions" with proper plurals. |
| Programme timeline → **Program timeline** | [before](before/demo/09-timeline.png) | [after](after/demo/09-timeline.png) | "Program" as everywhere else; "0 modules" instead of "0 module placements"; week headings sentence case (no upper-case tracking); decks as one line each with "…" and a tooltip (on real data the deck chips overlapped); empty programs no longer leave an empty lane. |
| Activity | [before](before/demo/10-activity.png) | [after](after/demo/10-activity.png) | Filters on one grid: at 1536 the "To" date wrapped alone onto a second line; now one row, two tidy rows at 1024. "Entity" is now "What changed". |
| Data quality | [before](before/demo/11-quality.png) | [after](after/demo/11-quality.png) | Classes instead of inline styles; when the checks take more than 3 s (the real data takes about a minute) the page says so instead of showing a silent skeleton. |
| Approvals | [before](before/demo/12-approvals.png) | [after](after/demo/12-approvals.png) | The empty state's help link had a 20px icon pushed off its baseline (the empty-state icon rule hit every icon inside it); fixed for every empty state. The list keeps to the page width on wide screens. |
| Archived | [before](before/demo/13-archived.png) | [after](after/demo/13-archived.png) | Same empty-state fix; the table keeps to the contained width; "1 link, 2 relationships" instead of "1 link(s)"; the actions column has an accessible name. |
| Guide | [before](before/demo/14-guide.png) | [after](after/demo/14-guide.png) | Screenshots were blown up to the column width (a 440px panel shown at 760px, giant text); they now show at their real size (half their pixels; they are 2x captures). The contents links scroll without animation under reduced motion. Copy: Links tab, legacy and sync, Who teaches what, Program timeline. |
| Settings → Record types | [before](before/demo/15-settings-types.png) | [after](after/demo/15-settings-types.png) | One intro row for every tab (text and its one action aligned on the same 32px line; Members, Tags, Tokens and Templates sat 6px higher than the others). The selected tab no longer turns bold, so the tabs beside it stop shifting. Type editor: field cards, swatches and the preview column are classes; it stacks below 900px. |
| Settings → Relationship types | [before](before/demo/16-settings-relationships.png) | [after](after/demo/16-settings-relationships.png) | Intro row, row padding on the 8px grid. |
| Settings → Link kinds | [before](before/demo/17-settings-links.png) | [after](after/demo/17-settings-links.png) | As above. |
| Settings → Tags | [before](before/demo/18-settings-tags.png) | [after](after/demo/18-settings-tags.png) | As above. |
| Settings → Members | [before](before/demo/19-settings-members.png) | [after](after/demo/19-settings-members.png) | As above. |
| Settings → API tokens | [before](before/demo/20-settings-tokens.png) | [after](after/demo/20-settings-tokens.png) | As above; the create row (name, expiry, button) wraps as one group on narrow screens. |
| Settings → Templates | [before](before/demo/21-settings-templates.png) | [after](after/demo/21-settings-templates.png) | As above. |
| Settings → Sync | [before](before/demo/22-settings-sync.png) | [after](after/demo/22-settings-sync.png) | Intro row with "Sync now"; "Run log" heading in the shared sub-heading style. |
| Settings → People | [before](before/demo/23-settings-people.png) | [after](after/demo/23-settings-people.png) | Tab not present yet (B1's `people.js`); the route falls back to Record types in both sets. |
| Record panel | [before](before/demo/30-record-panel.png) | [after](after/demo/30-record-panel.png) | Tab "Links & resources" is now "Links"; banners, tag input, bars and the summary/notes blocks are classes; in "Needs work inside" the record name gets the room and the missing list is cut with a tooltip (it was the other way round at 1024). |
| Record page (`#/r/<id>`) | [before](before/demo/31-record-page.png) | [after](after/demo/31-record-page.png) | Header and properties were capped at 900px on the left while the tabs and body ran full width, so the hairlines did not line up and the actions floated mid-page. Now one centred column (reading width) holds all of it. |
| New record | [before](before/demo/32-new-record.png) | [after](after/demo/32-new-record.png) | Section "Links and resources" is now "Links"; notes, the link card and the Ctrl↵ hint are classes. |

## Across every screen

- **Inline styles**: 165 of the 180 `style:` values in B3's files became classes in kb.css
  (utilities on the 8px grid plus named components such as `.tab-intro`, `.record-page`,
  `.field-card`, `.queue`, `.deck-list`). What stays inline is data-driven only: a type's
  colour, an avatar hue, a swatch colour, a bar's percentage, a resizable column's width
  (enforced by `test_no_one_off_inline_styles`).
- **One radius, two weights**: the run-5 matrix and timeline used an 8px radius and
  weight 500 (and `kbd` used 500); now `var(--radius)` and 400/600 only (tested).
- **Contrast** (computed in the test from the kb.css tokens, both themes): every
  text/surface pair the components use is at least 4.5:1. Fixed: the danger button and
  the error toast put white on `--danger`, which in dark mode (#f87171) is 2.8:1; they
  now use `--on-accent` (6.8:1 dark, 6.5:1 light). Lowest pair now: faint text on a
  hovered row, 4.64:1 light. Avatar hues carry white initials at 5.0:1 or more.
- **Focus**: one ring everywhere. The active sidebar link, the user button, tabs, rows,
  link rows, tiles, menu items, the panel resizer and checkboxes lost or never had a
  visible ring (their own box-shadow won over `:focus-visible`); tested by tabbing 40
  stops on six screens.
- **Reduced motion**: besides `--motion: 0ms`, every animation and transition is
  switched off and the Guide's smooth scroll becomes a jump (tested).
- **Copy**: record, relationship, link, legacy, archived; "Program" not "Programme";
  plurals instead of "(s)".

## Requests to the lead (files B3 does not own)

See the B3 report in PROGRESS.md: rename the sidebar items "Resources" → "Links" and
"Programme timeline" → "Program timeline" (app.js), add both views to the palette's
"Go to" list, and stop the palette's "Create" commands outranking "Go to" for an exact
page name.
