# Visual direction: decision (2026-11-07)

Approved by the owner on 2026-11-07. It replaces the "awaiting the owner's choice" status in
[README.md](README.md).

## The decision

- **Base: Direction A · Clarity.** Left sidebar; light, calm and dense; IK blue is the only accent.
  The **Admin group sits at the bottom of the sidebar**, with counts.
- **Home: Direction C's search-first top.** A large search box and suggestion chips sit above
  A's Home cards: Programs, Recently changed, Needs attention and My items.
- **Dark mode: Direction B's navy as A's dark theme**, with a light/dark toggle. The default
  follows the operating system's setting.

Refinements:

1. **Browse keeps "Map"**, the read-only overview for everyone. The editable graph moves into
   the Admin group as **"Graph editor"** (admin-only), and "Graph" leaves Browse. The map's
   admin-only button opens the **Admin area** (`/kb/#/admin`). This replaces the earlier
   "Admin Dashboard" button idea.
2. **"Sources" in Browse becomes "Resources"**, matching Program → Course → Module → Topic →
   Concept → Resource. Admin keeps **"Sources & sync"**.
3. **Week numbers appear only as program-specific information**: on program pages and on
   "Where it's used" rows, never on reusable records. *Week and order belong to each program,
   not to the topic.*
4. **Chip and badge colours meet WCAG AA contrast** in light and dark mode.

## What is built now (2026-11-07)

| Part | Where | Tests |
|---|---|---|
| Navigation shell: Home; Browse (Programs, Courses, Resources, Who teaches what, All records, Outline, Map); an Admin group at the bottom, each item shown only to the role that can use it (Overview, Graph editor, Approvals, Data quality, Activity, Archived, Members, Sources & sync) | `public/kb/js/app.js` (`NAV`, `ADMIN_NAV`) | `tests/test_kb_shell.py::test_navigation_by_role` |
| Admin overview page (`#/admin`), where the map's admin button lands | `public/kb/js/views/admin.js` | `test_admin_overview_lists_the_tools_of_the_role`, `tests/test_kb_map_switch.py` |
| Graph editor is admin-only: the page says "Admins only" to other roles, and the server refuses layout writes (`POST`/`DELETE /api/kb/graph/positions`) from anyone but an admin | `app.js` `route()`, `web/lib/kb/workspace.py` | `test_graph_editor_is_admin_only_in_the_page_and_on_the_server`, `tests/test_kb_access_sweep.py` |
| Home: a search-first top (big box, recent searches, type chips) above the cards | `public/kb/js/views/dashboard.js` | `test_home_search_first_then_cards` |
| Search results page (`#/search?q=`): grouped by type, a type filter, "See all" per group, resources last; results open beside the list | `public/kb/js/views/search.js` | same |
| Design tokens: A's light palette and B's navy dark palette; radius, small radius, z-index scale | `public/kb/kb.css` `:root` | `test_theme_toggle_cycles_and_persists_and_follows_the_system` |
| Theme toggle in the sidebar footer: System → Light → Dark | `app.js` `themeButton()` | same |
| AA contrast of chips, filter chips, badges, counts and group labels, in both themes | `kb.css` | `test_chips_and_badges_meet_aa_contrast[light/dark]` |

## What waits for the KYP-based model

These pages use this direction once Program → Course → Module → Topic → Concept → Resource is
in place: the Programs list and Program view (schedule from the KYPs), Courses pages, the record
page sections ("Where it's used" with program-specific weeks, Owners vs SMEs, Concepts,
citations), compare programs, and the map restyle onto these tokens. See
[../kyp-structure-and-model.md](../kyp-structure-and-model.md).
