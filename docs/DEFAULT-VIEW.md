# DEFAULT VIEW — owner decisions, 2026-09-29

Approved by Animesh Kumar. This replaced the bounded ~60-node overview that
`web/lib/data.py::overview()` served at the time. Phase B built from this file.
Today the map routes are served from `kb` by `web/lib/kb/npmap.py`;
`web/lib/data.py` serves them only under the `NP_MAP_SOURCE=old` rollback.

---

## D1 · `live_class` is retired as a node type — DONE

Pass 7 minted one `live_class` node **per file**: 845 of them. The mastersheet
remodel had already produced **134 `class_session` nodes**, which are the
sessions the roster actually names. The 845 were a parallel layer:

| | count | what it actually was |
|---|---:|---|
| wrapper around a `slide_deck` from the same file | 402 | the deck node already existed |
| class-role file | 443 | the `file` node already existed |

It was the single largest thing in the default view, and none of it was a
session. Files and decks now hang off the module directly, behind a toggle:

- `delivers` — role `module_class_file`, **module → file**
- `presented_with` — role `module_deck`, **module → slide_deck**

The structure layer keeps only sessions the mastersheet names. Nothing was
dropped; every file and deck is still reachable one hop from its module.

### Effect on the default view

| | before | after |
|---|---:|---:|
| structure nodes | 4,200 | **3,355** |
| structure edges | 5,815 | **4,970** |
| behind toggles (nodes) | 4,757 | 5,200 |
| combined nodes | 8,957 | 8,555 |

**Measured again 2026-09-29, after the MOD and INS merges: 3,307 structure
nodes / 4,970 edges** (904 of them legacy modules), from the local projection
via `web/lib/data.py::structure()` and independently from
`knowledge/merged_graph.json` — the two agree. The 3,355 above was correct when
measured; the merges since absorbed 48 nodes — modules 942 → 924, and
instructors 1,953 (1,915 main + 38 mastersheet) → 1,923 across the INS bulk,
the Velaga/Velega alias and PPL-11's `Bharath`. The edge count is unchanged. **3,307 is the figure to quote.**

`file` rises 1,440 → 1,957 because the 508 unavailable-content nodes were
typed `live_class` and are now typed `file`. They are still **marked, never
dropped** — `docs/project-history/DOWNLOAD-DISABLED-FILES.md` is unchanged.

---

## D2 · Legacy modules are faded, not hidden and not merged

The projection will carry two module populations until `MOD-01…16` and the
`INS` rows are answered:

- **20 row-B modules**, keyed `(domain_slug, sequence)`, from the mastersheet.
  Shown **prominently**, with their program weeks, sessions and instructors.
- **922 legacy modules**, keyed on their label. Shown **de-emphasised** —
  faded, grouped under their domain — with a toggle to hide them.

15 of the 922 share a label with a row-B module and 32 instructors share a
label across the two graphs. **Nothing is merged automatically** and nothing is
dropped: everything stays reachable, and the visual weight says which layer has
been reviewed. When the MOD/INS answers land, the de-emphasis is what goes
away, not the nodes.

This is the `CLAUDE.md` §4 rule applied to a renderer rather than a threshold:
rank or warn, never silently exclude. A hidden-by-default legacy module would
be a filter on truth wearing a stylesheet.

### Grouping, amended 2026-09-29

The first version of this section said the legacy modules are "grouped under
their domain". **724 of the 922 have no `contains` edge from any programme**,
so for most of them that grouping edge does not exist. Measured, not assumed.

So the rule is:

1. group by **domain** where a domain edge exists;
2. otherwise put the module in one faded cluster labelled
   **"Legacy — no programme recorded"**.

The cluster is a statement about the evidence, not a bin for leftovers. Its
label says what is true of everything in it, which is the difference between
grouping and hiding.

### After the MOD merges

16 of the collisions are now answered and applied (`config/module-merges.yaml`,
pass 8). Module nodes 942 → 924, duplicate module labels **15 → 0**. What
remains de-emphasised is the ~900 legacy modules that never collided with a
row-B module at all, plus **4 instructor labels still duplicated across the
two graphs** — `Bill Ogden` / `William David Ogden` (INS-08/30) and
`Konstantinos`, `Shelby` (INS-31/32), all left apart by owner decision. It was
30 before the INS bulk answer was applied.

---

## D3 · Speed plan — approved

**Status 2026-09-30 (B3, local only):** items 1, 2, 3 and 5 DONE; item 6
(`pg_trgm`) **NOT shipped, by owner decision (Animesh Kumar, 2026-09-30,
origin: hand)**: the index sped up search only for the table owner (18.5 →
1.4 ms); under RLS it gains nothing, because `ILIKE` is not LEAKPROOF and the
policy must run first, so the planner can never use it. Search stays ~9 ms
p50, and a SECURITY DEFINER search would duplicate the visibility rules
(measured in B3);
item 4 unchanged — the canvas is 2D and no WebGL path was built, since B3's
scope was the other five. Locally: settled 135 ms, default-view payload
127,261 B brotli (target ≤ 150 KB). Production figures are Phase D's.

Targets, against a measured ~360 ms Vercel cold-start + RTT floor:

| target | value |
|---|---|
| first render | ≤ 1.0 s p50 |
| settled layout | ≤ 1.5 s p50 |
| default-view payload | ≤ 150 KB brotli (3,307 nodes / 4,970 edges) |
| `/api/*` | ≤ 400 ms p95 |
| search | ≤ 250 ms p95 warm |

1. **Precomputed layout.** x/y computed at build time and shipped. The graph
   changes only when the projection runs, so in-browser force simulation is
   pure waste and it is the whole settle time.
2. **Columnar payload.** `Float32Array` coords, `Uint16` edge pairs, labels in
   one length-prefixed blob. One request.
3. **ETag + `Cache-Control: private, max-age=300, must-revalidate`.**
   `private` because the graph is behind auth.
4. **Canvas 2D by default; WebGL only behind the topic toggle.** 3,307 arcs is
   a few ms a frame. 8,507 with topics on is not.
5. **Lazy panels** — `/api/node` on click, never in the bulk payload.
6. **`pg_trgm` GIN index** for substring search. `nodes_label_idx` already
   serves prefix matching.

**Self-hosted libraries only. The CSP is not widened.** It currently allows one
external origin (`accounts.google.com/gsi/client`) and inline scripts are
hash-pinned — so **the hash regeneration is wired into the build**, because a
hand-maintained hash is a guard that silently stops matching.

---

## D4 · UI — approved as described

Instructor panel with `teaches` tags by role (main-graph and mastersheet
provenance shown separately, so an unanswered `INS` row is visible rather than
silently merged); module panel showing the full chain with each hop's source
and locator; a who-teaches-what matrix with an "unconfirmed" hatch for anything
resting on an open review row; a program timeline on program week; filters for
domain / week / role; colour by domain with shape carrying type; search badges
driving the `types=` param; shareable URLs carrying focus, depth and filters.

---

## D4a · The matrix load column

**Owner decision, 2026-09-29.** Each instructor row carries a load: the number
of modules taught, split Primary and Backup ("3 P · 2 B").

**Counted PER NODE and never summed across an unresolved identity.** `Bill
Ogden` is two nodes (INS-08/30, answered "leave apart"); adding their loads
together would assert the merge the owner declined. Each row shows its own load
with the unconfirmed marker.

Only confirmed identities are counted as one person.

---

## D5 · What Phase B must also fix

- **Coverage counts `rel='teaches'`.** Row-B instructors are attached by
  `taught_by`, so `modules_without_instructor` would count all 20 row-B modules
  as unstaffed. Adapt it for both.
- **The isolated CTE.** It is `where type <> 'file'`, so the 1,443 provenance-
  only file nodes are already excluded correctly. Measured: the only content
  nodes that would enter it are **8 instructors** who appear in a mastersheet
  instructor table with no module row — a real finding awaiting an `INS`
  answer, so it should be reported as that rather than as isolation.
- **Staffing** mixes both module populations; it stays blocked on `MOD-01…16`.

---

## D6 · B4 — the explorer as shipped (owner review rounds and approval, 2026-09-30)

**Owner decisions, Animesh Kumar, 2026-09-30 (origin: hand).** Given in the
B4 review rounds and the approval message. Until this section they were
recorded only in commit messages (`ee47ccc`, `befa170`, `9945fb1`,
`714f5c1`) and code comments; they are recorded here, each with what holds it.
Live since the window of 2026-09-30 (`dpl_3HZSPGpQEsz9gogu9WofSGQdJR8r`).

| decision | held by |
|---|---|
| **Launch the curriculum release now; expand the scope next** (the NEXT-PHASE plan, archived; in git history) | — (order of work) |
| **Old and new domains stay SEPARATE**, never merged; current domains wear their code (`SD1 · Full Stack`, SD1–SD4); legacy carries a **legacy badge everywhere** it appears | `public/index.html` (domain labels, badges); `tests/test_default_view_labels.py` |
| **The map is THE default for every type**: one network of every current type (domain hubs, modules, weeks, sessions, assignments, reviews, current decks, instructors with role-coloured edges, people, themes, workflows); topics, files, repos, curriculum docs and programmes stay behind their chips; legacy as collapsed groups | `test_the_default_map_holds_every_current_type` |
| **Chips filter the map, not a list** (List is its own toggle); a filtered-out parent stays as a **ghost anchor**, so nothing is a bare dot | `test_a_chip_filters_the_map_not_a_list`, `test_sessions_alone_are_never_bare_dots` |
| Labels of current domains, modules and instructors are **never dropped or shortened**; an overlap is resolved by moving the label | `test_every_current_label_is_shown_in_full` (6 window sizes) |
| **The map is 2D only** (owner, 2026-11-07; the 3D floating view of 2026-09-30 was removed with its toggle, bundle and slow-machine fallback). An old `?dim=` link opens the 2D map and is rewritten without it | `test_an_old_dim_link_opens_the_2d_map_without_the_parameter`, `test_the_3d_bundle_and_toggle_are_gone`, `tests/test_kb_map_switch.py` |
| **Floating and drag**: nodes drift round a home position, a dragged node pulls its neighbours on springs and all settle home; `prefers-reduced-motion` = no drift; paused when the tab is hidden; 60 fps | `test_a_dragged_node_pulls_its_neighbours_and_all_settle_home` |
| **Focus**: clicking a module spreads and frames its things (sessions, decks, instructors, topics); Esc returns to the whole graph | `tests/test_default_view_labels.py` (2D focus) |
| **Role order and colours everywhere**: Primary (green) → Backup 1 (blue) → Backup 2 (amber) → Backup 3 (grey), then week, code, cell; the owner's Backend and Testing orders are the test cases | `tests/test_role_order.py` (`ROLE ORDER: begin/end` in `public/index.html`) |
| **Who teaches what** (matrix) and **Programme timeline** as their own views | `eval/drive_dom.mjs` |
| **Historical files are grouped** (collapsed "Historical (N)"), never mixed with current ones; build/recording artefacts collapse into their own group | `public/index.html::moduleChain`; `tests/test_corroboration_after_merge.py` |
| **Plain language** in panels and notes; **crisp rendering** on high-DPI screens (canvas at device pixel ratio) | `public/index.html` |
| **The URL is the current view**: one place, at most ONE focused item; opening pushes history, adjustments replace it; Back/Forward restore each view; old links keep only their last item | `test_twenty_clicks_leave_at_most_one_item_in_the_url` and four more |
| **Search never lists a held-back (`not_a_topic`) topic** | `tests/test_search_holds_back_topics.py` |
| **A possessive first name of a known person is not a topic** ("Tilo’s Introduction"): 18 titles, all Tilo Dickopp's note pages | `tests/test_not_a_topic.py` (`REVIEWED_PERSON_NAME`) |
| **Decks are core structure** (on the map, hung off their session) | `pipeline/lib/layout.py`; `STRUCTURE_FORMAT = "columnar-3"` |
| **The local review mode**: the local server signs in a stub member with a "LOCAL PREVIEW, not production" banner, and the stub can **never ship** | `tests/test_local_stub_never_ships.py`; `db/window/check_function_map.py` |
| **Landing "What it answers well" for this release** (a module's full picture; who teaches what, by role; the programme timeline; the map); "Where a fact came from" and "What it will not tell you" kept | `public/index.html` (CSP-hashed) |
| **Review screenshots are not committed** (they broke the 15 MiB repo budget); regenerated by `eval/screenshot_views.py` | `.gitignore` (`docs/screenshots/b4/`) |
