# Contracts — run 6

The shared interfaces the run-6 workstreams build on. **A workstream must not
change a contract on its own.** It asks the lead in its PROGRESS.md report
("Contract change request: …"); only the lead edits this file, the
migration that backs it (0032), and `web/lib/kb/graph.py`.

Additive changes (a new optional field, a new filter value) still go through
the lead, so that every stream sees them at the same time.

## 1. Graph read API — `GET /api/kb/graph`

One endpoint behind every graph: the knowledge base Graph page, and the NP
Autopilot map at `/`. Implemented in `web/lib/kb/graph.py` (`read`), and it
runs as the caller under RLS.

### Query parameters (all optional)

| Param | Values | Default | Meaning |
|---|---|---|---|
| `types` | comma list of node type keys | all | which records |
| `rels` | comma list of edge type keys | all | which relationships |
| `legacy` | `current` · `all` · `only` | `current` | legacy records (`is_legacy`) |
| `archived` | `0` · `1` | `0` | include archived records and relationships |
| `focus` | record id | — | neighbourhood mode: this record plus `depth` hops |
| `depth` | `1` · `2` | `1` | hops, with `focus` only |
| `scope` | record id | — | only this record and the records under it (`scope_id` chain, any depth) |
| `limit` | 1–5000 | 2000 | records per page |
| `cursor` | from `next_cursor` | — | the next page |

### Response

```json
{
  "nodes": [{"id": "uuid", "type": "module", "name": "…", "status": "…",
             "scope_id": "uuid|null", "is_legacy": false, "archived": false,
             "owner_record_id": "uuid|null", "external_id": "np:…|null",
             "degree": 4}],
  "edges": [{"id": "uuid", "type": "teaches", "source": "uuid", "target": "uuid",
             "role": "primary|backup_1|backup_2|backup_3|null",
             "is_legacy": false, "archived": false}],
  "total_nodes": 3087, "truncated": false, "next_cursor": null,
  "head": 123456
}
```

- **Paging** is by record id. A relationship is returned with the page of its
  SOURCE record, when its target also passes the filters, so every relationship
  arrives exactly once across all the pages.
- **`edges[].is_legacy`** is true when either end is legacy. `role` is `props.role`
  (teaching roles from the mastersheet), otherwise null.
- **`head`** is the newest `kb.changes` id at read time. A client applies the
  change feed from `head`.
- **Focus mode** ignores `cursor` and returns at most `limit` records nearest
  first; `truncated` tells the client that more exist.
- **Errors:** 422 for an invalid parameter (with `field`), 404 for an unknown
  `focus` or `scope`.

## 2. Change feed — `kb.changes` and `GET /api/kb/changes?since=<id>`

Every write to an audited KB table appends one row through the audit trigger:
no row content, so every member may follow it. Realtime publishes the table,
and polling `/api/kb/changes` is the fallback.

| Field | Type | Meaning |
|---|---|---|
| `id` | bigint | the audit log id (monotonic) |
| `at`, `actor_id`, `actor_type` | | who and when (`actor_type`: user · ai · import · sync) |
| `table_name`, `row_id`, `action`, `version` | | as before (insert · update · delete) |
| `kind` | text | **new (0032)**: what happened, below |
| `node_ids` | uuid[] | **new (0032)**: every record whose graph or panel must refresh |

`kind` values (the trigger derives them; one per row):

| Table | `kind` |
|---|---|
| nodes | `record.create` · `record.update` · `record.archive` · `record.restore` · `record.delete` · `record.owner` (only the owner / co-owner columns changed) |
| edges | `relationship.create` · `relationship.update` · `relationship.archive` · `relationship.restore` · `relationship.delete` |
| edge_types, edge_type_rules | `reltype.create` · `reltype.update` (also rename / merge) · `reltype.archive` · `reltype.restore` · `reltype.delete` |
| node_types | `type.create` · `type.update` (fields, icon, colour, shape, owner expected) · `type.archive` · `type.restore` |
| tags, node_tags | `tag.create` · `tag.update` · `tag.archive` · `tag.attach` · `tag.detach` |
| resources, node_resources | `link.create` · `link.update` · `link.archive` · `link.attach` · `link.detach` |
| graph_positions | `layout.update` |
| person_accounts | `owner.account` |
| sync_runs | `sync.run` (when a run finishes) |
| any other table | `<table>.<action>` |

`node_ids` holds: the record for `nodes`; source and target for `edges`;
`node_id` for `node_tags`, `node_resources`, `graph_positions` and
`person_accounts`; empty for type, tag and sync changes, which mean "refetch
the type metadata or the whole view".

**Bulk edits, template creates, imports and syncs** emit one row per changed
row, the same as any other write. A client that receives more than 200 rows
in one poll refetches instead of patching.

## 3. Type and relationship-type metadata — `GET /api/kb/types`

```json
{"node_types": [{"id", "key", "label", "plural", "icon", "color", "shape",
                 "owner_expected", "is_core", "is_container", "fields", "…"}],
 "edge_types": [{"id", "key", "label", "inverse_label", "color", "line_style",
                 "is_core", "rules": [{"source", "target"}], "…"}]}
```

- **`shape`** (0032) is one of `round-rectangle` · `ellipse` · `diamond` ·
  `hexagon` · `triangle` · `rectangle` · `tag` · `barrel`. Built-in types get
  fixed shapes; a custom type gets the next shape in that order.
- **`color`** on node types is unchanged: the palette in `typedefs.PALETTE`.
- **Edge `color`** (0032) is a palette hue. **`line_style`** is `solid` ·
  `dashed` · `dotted`. Built-ins get fixed styles. A custom relationship type
  gets the next unused colour × style pair from `typedefs.edge_style(n)`, so
  every custom type is visually distinct.
- **`owner_expected`** (0032): ON for program, course, domain, module, session,
  week (and `link`, if such a type is ever added); OFF for every other type. Data quality's
  "No owner" counts only records whose type has it ON.
- An archived type disappears from this list. Clients treat an unknown type
  key as "generic", with a neutral style.

## 4. Design system component API

The components in `docs/DESIGN_SYSTEM.md` ("Components"), exported from
`public/kb/js/core.js` and `page.js`, keep their names and signatures:
`el`, `icon`, `typeIcon`, `api`, `toast`, `openDialog`, `confirmDialog`,
`openSheet`, `menu`, `popover`, `combobox`, `skeletonRows`, `skeletonBlock`,
`empty`, `errorBox`, `avatar`, `pageHead`, `relCombobox`. The tokens in
`kb.css` `:root` keep their names.

A stream may ADD a component in its own files. Adding a token, or changing an
existing component's signature, goes through the lead. The BANNED list in
DESIGN_SYSTEM.md applies everywhere.

## 5. The map's routes (`/api/structure`, `/node`, `/neighbourhood`, `/search`, `/overview`, `/staffing`, `/coverage`, `/me`)

Their response shapes are frozen: `public/index.html` keeps working
unchanged. Run 6 changes only where the data comes from (kb). A field the KB
cannot supply keeps its key, with an empty value, and is listed in
docs/ARCHITECTURE.md.
