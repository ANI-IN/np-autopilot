# DEFAULT VIEW — owner decisions, 2026-09-29

Approved by Animesh Kumar. This replaces the bounded ~60-node overview that
`web/lib/data.py::overview()` serves today. Phase B builds from this file.

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
dropped** — `docs/DOWNLOAD-DISABLED-FILES.md` is unchanged.

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
