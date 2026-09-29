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

---

## D3 · Speed plan — approved

Targets, against a measured ~360 ms Vercel cold-start + RTT floor:

| target | value |
|---|---|
| first render | ≤ 1.0 s p50 |
| settled layout | ≤ 1.5 s p50 |
| default-view payload | ≤ 150 KB brotli (3,355 nodes / 4,970 edges) |
| `/api/*` | ≤ 400 ms p95 |
| search | ≤ 250 ms p95 warm |

1. **Precomputed layout.** x/y computed at build time and shipped. The graph
   changes only when the projection runs, so in-browser force simulation is
   pure waste and it is the whole settle time.
2. **Columnar payload.** `Float32Array` coords, `Uint16` edge pairs, labels in
   one length-prefixed blob. One request.
3. **ETag + `Cache-Control: private, max-age=300, must-revalidate`.**
   `private` because the graph is behind auth.
4. **Canvas 2D by default; WebGL only behind the topic toggle.** 3,355 arcs is
   a few ms a frame. 8,555 with topics on is not.
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
