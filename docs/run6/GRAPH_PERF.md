# Graph performance, run 6 (B2), 2026-11-03

Script: `scripts/kb_graph_perf.py` (updated in run 6). Headless Chrome on this
laptop, software rendering (no GPU), 1536x900, while other run-6 streams were
also running: treat the numbers as floors and compare rows of the same table.

- **Load** = from navigation to the graph drawn (fetched, laid out, first frame).
- **FPS** = frames per second while the view pans and zooms continuously for
  3 s in the zoom band shown.
- **Drawn** = records on the canvas (not folded into a bundle).

## Scenarios

| Scenario | What is opened |
|---|---|
| hub | one record with N-1 neighbours and ~2N relationships among them, `#/graph/<hub>?limit=N&bundle=0`: every record drawn. The run-3 measurement; the old page ignores `bundle=0`. |
| tree overview | records shaped like the real data (domains > modules > weeks / sessions, ~88 % topics under modules, instructors teaching modules, themes > processes, team members), the whole-graph page `#/graph` as it opens: topics bundled per module |
| tree, all expanded | the same, `#/graph?expand=all`: every record drawn |
| real data | `kb_b2`, the local copy of the real data (3,087 current records; 5,087 with legacy) on :8772, read only (`--base`) |

## Before (commit fb25b56, the run-3 page) — hub only

The old page had no whole-graph view (`#/graph` was a start page), so only the
hub scenario can be measured on it. Its "drawn" count after load was 1: at fit
zoom it showed one cluster bubble per type; the FPS bands zoom back in to the
records.

| Records | Renderer | Load (ms) | FPS, zoom 0.5-1.2 | FPS, zoom 0.2-0.45 |
|---|---|---|---|---|
| 500 | canvas | 1807 | 30.6 | 25.6 |
| 500 | webgl | 2432 | 17.5 | 26.7 |
| 2000 | canvas | 3400 | 9.2 | 12.1 |
| 2000 | webgl | 4004 | 15.3 | 26.2 |
| 5000 | canvas | 13823 | 1.0 | 2.3 |
| 5000 | webgl | 21871 | 1.0 | 5.0 |

## After (this branch)

| Scenario | Records | Renderer | Drawn | Load (ms) | FPS, zoom 0.5-1.2 | FPS, zoom 0.2-0.45 |
|---|---|---|---|---|---|---|
| hub | 500 | canvas | 500 | 1142 | 36.9 | 16.5 |
| hub | 500 | webgl | 500 | 1519 | 43.5 | 34.8 |
| hub | 2000 | canvas | 2000 | 2497 | 11.4 | 3.7 |
| hub | 2000 | webgl | 2000 | 2106 | 15.5 | 4.1 |
| hub | 5000 | canvas | 5000 | 7883 | 4.1 | 0.9 |
| hub | 5000 | webgl | 5000 | 9967 | 4.5 | 1.0 |
| tree overview | 500 | canvas | 51 | 476 | 60.1 | 59.1 |
| tree overview | 500 | webgl | 51 | 564 | 60.1 | 60.1 |
| tree, all expanded | 500 | canvas | 500 | 693 | 58.0 | 48.4 |
| tree, all expanded | 500 | webgl | 500 | 856 | 57.7 | 49.4 |
| tree overview | 2000 | canvas | 205 | 847 | 59.7 | 53.6 |
| tree overview | 2000 | webgl | 205 | 794 | 58.4 | 53.8 |
| tree, all expanded | 2000 | canvas | 2000 | 1538 | 46.4 | 22.2 |
| tree, all expanded | 2000 | webgl | 2000 | 1783 | 26.6 | 15.1 |
| tree overview | 5000 | canvas | 508 | 1182 | 57.9 | 49.4 |
| tree overview | 5000 | webgl | 508 | 1140 | 54.6 | 43.2 |
| tree, all expanded | 5000 | canvas | 5000 | 3505 | 17.5 | 3.7 |
| tree, all expanded | 5000 | webgl | 5000 | 3923 | 7.9 | 2.4 |

Real data (kb_b2 on :8772, `--base`):

| Scenario | Records | Renderer | Drawn | Load (ms) | FPS, zoom 0.5-1.2 | FPS, zoom 0.2-0.45 |
|---|---|---|---|---|---|---|
| real data overview | 3087 | canvas | 352 | 1132 | 58.7 | 45.4 |
| real data overview | 3087 | webgl | 352 | 1422 | 54.3 | 50.0 |
| real data, all expanded | 3087 | canvas | 3087 | 2602 | 28.7 | 11.6 |
| real data, all expanded | 3087 | webgl | 3087 | 3679 | 12.1 | 6.0 |
| real data, legacy too | 5087 | canvas | 2329 | 2008 | 35.9 | 16.1 |
| real data, legacy too | 5087 | webgl | 2329 | 2542 | 21.3 | 5.6 |

Load split on real data (page timing, `window.__kbGraph.timing`): fetch
GET /api/kb/graph 140-220 ms, projection 30-100 ms, layout 35-170 ms.

## What changed, and the decisions from these numbers

- **The page opens on the whole graph, bundled.** More than 8 satellites of one
  type on one record become one bundle ("137 topics"): the real data opens with
  352 of 3,087 records drawn, at ~59 fps, in about 1 s. Bundled records are
  not added to Cytoscape at all (only to the page's model).
- **Hierarchy layout** is computed directly (graph/layouts.js, ~100 ms for the
  real data) instead of running a force simulation.
- **Clutter at scale:** edges outside the hierarchy are faint until a record at
  either end is hovered or selected; below zoom 0.3 only the hierarchy's lines
  are drawn; labels never overlap (graph/labels.js) and the hierarchy's labels
  grow when zoomed out (semantic zoom); above 400 lines dashed and dotted
  relationships draw solid (dashes were the single largest per-frame cost: the
  hub at 500 went from 2.3 to 36.9 fps); above 400 drawn records the type icons
  inside the shapes are dropped (an image per node per frame); above 800 drawn
  records straight "haystack" lines, a texture while moving, edges hidden during
  motion, one device pixel per CSS pixel.
- **WebGL.** The vendored Cytoscape is 3.34.4, which has the WebGL renderer
  (`renderer: {name: 'canvas', webgl: true}`). On the real-shaped graphs it was
  slower than the tuned canvas renderer at every size measured (2,000: 26.6 vs
  46.4 fps; 5,000: 7.9 vs 17.5), and only level on the hub. The automatic
  threshold is therefore 6,000 drawn records (beyond anything the page draws
  today); `?renderer=webgl` forces it. Re-measure on a machine with a GPU
  before lowering it: headless software rendering penalises WebGL most.
