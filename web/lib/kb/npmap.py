"""The NP Autopilot map ("/") read from the knowledge base (run 6, B1).

docs/architecture/overview.md (top): `kb` is the single source of truth. The map's
routes (/api/structure, /overview, /node, /neighbourhood, /search, /staffing,
/coverage, /me) keep the RESPONSE SHAPES of web/lib/data.py (docs/architecture/contracts.md
§5: frozen) and read kb instead of the old projection tables.

THE VOCABULARY IS TRANSLATED BACK, never written out here. The map speaks the
projection's types and relations (config/taxonomy.yaml); the KB speaks its own.
config/kb-projection-mapping.yaml is the one place that says how the one
becomes the other (the sync reads it forwards), and this module reads it
backwards:

  - a KB record type -> the projection type that maps to it (`types`), or the
    KB key itself for a type the projection never had (a course, a custom type);
  - a KB relationship (type, source type, target type) -> the projection
    relation (`relationships`, with `flip` reversing it). The teaching pair is
    split on the relationship's own props, as the sync merged it (D41): a
    current-mastersheet role becomes the module -> instructor relation with the
    role, the older sheets' role the instructor -> module one;
  - a LINK attached to a record with one of the mapping's `attachments` notes
    (Slides, Code, Assignment, ...) becomes the artifact node it came from
    (a deck, a repo, an assignment), joined by that relation. Provenance
    ("Source" links) stays out of the graph and is shown in the panel.

IDS. A record the sync brought in keeps its projection id (external_id
`np:<id>`), so links people shared still open; a record made in the KB uses its
uuid; an artifact uses `link:<resource uuid>`. Relationship ids are 32-bit
numbers derived from the KB ids (the wire format packs them as Uint32;
collisions are resolved deterministically within one model).

ONE MODEL PER CHANGE-FEED HEAD. Every route answers from one in-memory model of
the live KB, rebuilt when the newest kb.changes id moves (any write anywhere
moves it) and cached per process for that head and the caller's ability to
read the KB (RLS: every member reads the same rows, docs/architecture/overview.md).

ROLLBACK: NP_MAP_SOURCE=old serves the old tables (web/lib/data.py) again.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from collections import defaultdict, deque

from .. import data as _data
from pipeline.lib import layout as _layout
from pipeline.lib import taxonomy as _tax

#: The wire format of the structure payload is web/lib/data.py's, unchanged.
STRUCTURE_TYPES, DEFERRED_TYPES = _data.STRUCTURE_TYPES, _data.DEFERRED_TYPES
MAX_DEPTH = _data.MAX_DEPTH
DepthExceeded = _data.DepthExceeded

#: KB field keys whose projection property had another name (the sync's
#: desired_state renamed exactly these two).
FIELD_BACK = {"document_type": "doctype", "week_number": "number"}

#: The KB's graph layout the map shares with the Graph page's default view.
LAYOUT = "default"


def enabled() -> bool:
    """The rollback switch: NP_MAP_SOURCE=old serves the old tables again."""
    return os.environ.get("NP_MAP_SOURCE", "kb").strip().lower() != "old"


# ---------------------------------------------------------------------------- mapping (read backwards)
_MAP = None


def mapping() -> dict:
    """config/kb-projection-mapping.yaml, read backwards. Loaded once."""
    global _MAP
    if _MAP is not None:
        return _MAP
    from .sync import load_mapping, LAYOUT_SCALE, SOURCE_NOTE
    M = load_mapping()
    R = M["roles"]
    type_back = {kb: proj for proj, kb in M["types"].items()}
    rel_back = defaultdict(list)            # (kb rel, kb source type, kb target type) -> [(proj rel, flip)]
    for r in M["relationships"]:
        s, t = M["types"].get(r["source"]), M["types"].get(r["target"])
        if not s or not t:
            continue
        key = (r["kb"], t, s) if r.get("flip") else (r["kb"], s, t)
        rel_back[key].append((r["rel"], bool(r.get("flip"))))
    notes = {}                               # attachment note -> (rel, record side, record proj type, artifact type)
    for a in M["attachments"]:
        rec_t, art_t = (a["source"], a["target"]) if a["record"] == "source" else (a["target"], a["source"])
        notes[a["note"]] = (a["rel"], a["record"], rec_t, art_t)
    kind_art = defaultdict(list)             # link kind -> artifact types
    for art, kind in M["artifact_kind"].items():
        kind_art[kind].append(art)
    _MAP = {"M": M, "R": R, "type_back": type_back, "rel_back": dict(rel_back), "notes": notes,
            "kind_art": {k: v[0] for k, v in kind_art.items() if len(v) == 1},
            "artifacts": list(M["artifacts"]), "scale": LAYOUT_SCALE, "source_note": SOURCE_NOTE,
            "provenance": _tax.edge_for_role("provenance")}
    return _MAP


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _eid(key: str) -> int:
    """A 32-bit id for a relationship, stable for the same KB row."""
    h = key.replace("-", "")
    if re.fullmatch(r"[0-9a-f]{32}", h):
        return int(h[:8], 16) or 1
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) or 1


def _props_back(props: dict) -> dict:
    return {FIELD_BACK.get(k, k): v for k, v in (props or {}).items() if v not in (None, "")}


def _dates(note: str | None) -> list[str]:
    """The class dates the sync kept in a teaching relationship's note."""
    m = re.search(r"class dates: ([0-9, \-]+)", note or "")
    return [d.strip() for d in m.group(1).split(",") if d.strip()] if m else []


# ---------------------------------------------------------------------------- the model
_CACHE: dict = {}


def _q(conn, sql, args=()):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def head(conn) -> tuple[str, bool, str]:
    """(a fingerprint of the KB's state, may read the KB, the caller's KB role).
    The fingerprint is the newest change id, plus the live counts so that a
    database whose change feed was emptied (a demo re-seed) never matches a
    model built before."""
    r = _q(conn, """select coalesce((select max(id) from kb.changes), 0), kb.role_at_least('viewer'), kb.role(),
                           (select count(*) from kb.nodes), (select count(*) from kb.edges),
                           (select count(*) from kb.node_resources)""")[0]
    return f"{r[0]}.{r[3]}.{r[4]}.{r[5]}", bool(r[1]), str(r[2])


def model(conn) -> dict:
    h, can, _role = head(conn)
    key = (h, can)
    if key in _CACHE:
        return _CACHE[key]
    built = _build(conn, h) if can else _empty(h)
    if len(_CACHE) >= 2:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = built
    return built


def _empty(h):
    return {"head": h, "nodes": {}, "edges": [], "adj": defaultdict(list), "by_kb": {}, "extra": {}}


def _build(conn, h: str) -> dict:
    X = mapping()
    R, tb, notes = X["R"], X["type_back"], X["notes"]
    scale = X["scale"]
    rows = _q(conn, """
        select n.id::text, t.key, n.name, n.props, n.external_id, n.is_legacy, gp.x, gp.y
        from kb.nodes n join kb.node_types t on t.id = n.type_id
        left join kb.graph_positions gp on gp.layout = %s and gp.node_id = n.id
        where n.archived_at is null order by n.id""", (LAYOUT,))
    nodes, by_kb = {}, {}
    for kid, tkey, name, props, ext, legacy, x, y in rows:
        mid = ext[3:] if ext and ext.startswith("np:") and not ext.startswith("np:url:") else kid
        nodes[mid] = {"id": mid, "kb_id": kid, "type": tb.get(tkey, tkey), "kb_type": tkey, "label": name,
                      "props": _props_back(props), "legacy": bool(legacy),
                      "x": (x / scale) if x is not None else None, "y": (y / scale) if y is not None else None}
        by_kb[kid] = mid
    erows = _q(conn, """
        select e.id::text, et.key, e.source_id::text, e.target_id::text, e.props, e.note
        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
        join kb.nodes s on s.id = e.source_id and s.archived_at is null
        join kb.nodes t on t.id = e.target_id and t.archived_at is null
        where e.archived_at is null order by e.id""")
    arows = _q(conn, """
        select nr.id::text, nr.node_id::text, coalesce(nr.note, ''), r.id::text, r.title, r.url, r.kind, r.tags
        from kb.node_resources nr join kb.resources r on r.id = nr.resource_id
        join kb.nodes n on n.id = nr.node_id and n.archived_at is null
        where nr.archived_at is null and r.archived_at is null and coalesce(nr.note, '') <> %s
        order by nr.id""", (X["source_note"],))

    used: set = set()

    def new_id(key: str) -> int:
        i = _eid(key)
        while i in used:                       # deterministic: rows arrive in id order
            i = (i + 1) & 0xFFFFFFFF or 1
        used.add(i)
        return i

    edges = []
    teach, teach_rev = R["teaching"], R["teaching_reversed"]
    for kid, rel, s, t, props, note in erows:
        sm, tm = by_kb.get(s), by_kb.get(t)
        if not sm or not tm:
            continue
        props = props or {}
        cands = X["rel_back"].get((rel, nodes[sm]["kb_type"], nodes[tm]["kb_type"]), [])
        names = {c[0] for c in cands}
        if teach in names and teach_rev in names:
            # One KB relationship per pair (D41): the current mastersheet's role and
            # the older sheets' teaching are two projection relations again.
            current = props.get("tier") == "mastersheet" or bool(props.get("role"))
            older = bool(props.get("older_role")) or props.get("tier") not in (None, "mastersheet") or not current
            if current:
                p = {"tier": "mastersheet", **({"instructor_role": props["role"]} if props.get("role") else {})}
                edges.append((new_id(kid), teach_rev, tm, sm, p, kid))
            if older:
                p = {"tier": "legacy", **({"role": props["older_role"]} if props.get("older_role") else {})}
                dates = _dates(note)
                if dates:
                    p["class_dates"] = dates
                edges.append((new_id(kid + "#older" if current else kid), teach, sm, tm, p, kid))
            continue
        prel, flip = cands[0] if cands else (rel, False)
        p = {k: v for k, v in props.items() if v not in (None, "")}
        if note:
            p["note"] = note
        edges.append((new_id(kid), prel, tm if flip else sm, sm if flip else tm, p, kid))

    # links on records: artifacts (decks, repos, assignments, ...) and panel links
    extra = defaultdict(dict)                # record mid -> panel-only props from its links
    art_of: dict = {}                        # resource id -> artifact node
    order = {a: i for i, a in enumerate(X["artifacts"])}
    pending = []
    for aid, nid, note, rid, title, url, kind, tags in arows:
        rec = by_kb.get(nid)
        if not rec:
            continue
        if note == "UpLevel":
            extra[rec]["uplevel_link"] = url
            continue
        if note == "Drive folder":
            extra[rec].setdefault("drive_folders", []).append(url)
            continue
        spec = notes.get(note)
        if spec is None:
            art = X["kind_art"].get(kind)
            spec = next((s for s in notes.values() if s[3] == art and s[2] == nodes[rec]["type"]), None) if art else None
        if spec is None or spec[2] != nodes[rec]["type"]:
            continue
        rel, side, _rec_t, art_t = spec
        cur = art_of.get(rid)
        if cur is None or order.get(art_t, 99) < order.get(cur["type"], 99):
            p = {"drive_url": url}
            if "historical" in (tags or []):
                p["historical"] = True
            if "unavailable" in (tags or []):
                p["content_available"] = False
            art_of[rid] = {"id": "link:" + rid, "kb_id": None, "resource_id": rid, "type": art_t, "kb_type": None,
                           "label": title, "props": p, "legacy": False, "x": None, "y": None}
        pending.append((aid, rec, rid, rel, side))
    for a in art_of.values():
        nodes[a["id"]] = a
    for aid, rec, rid, rel, side in pending:
        lid = "link:" + rid
        s, t = (rec, lid) if side == "source" else (lid, rec)
        edges.append((new_id(aid), rel, s, t, {}, aid))

    # domain slugs for current modules (the map codes current domains by them)
    dom_t, mod_t = R["domain"], R["module"]
    offers = R["domain_offers"]
    slug_of = {}
    for _i, rel, s, t, _p, _k in edges:
        if rel == offers and nodes[s]["type"] == dom_t and nodes[t]["type"] == mod_t:
            d = nodes[s]
            slug_of.setdefault(t, d["props"].get("slug") or _slug(d["label"]))
    for n in nodes.values():
        if n["type"] == mod_t and not n["legacy"]:
            n["props"]["domain_slug"] = slug_of.get(n["id"], "")
        n["props"].pop("slug", None) if n["type"] == dom_t else None

    adj = defaultdict(list)
    for e in edges:
        adj[e[2]].append(e)
        adj[e[3]].append(e)
    _place(nodes, adj)
    return {"head": h, "nodes": nodes, "edges": edges, "adj": adj, "by_kb": by_kb, "extra": dict(extra)}


def _place(nodes: dict, adj: dict) -> None:
    """A position for every record that has none: next to its placed
    neighbours, else on a ring by id (deterministic, so a reload moves
    nothing). The client then starts frozen instead of re-simulating."""
    for _ in range(3):
        for n in nodes.values():
            if n["x"] is not None:
                continue
            pts = []
            for e in adj.get(n["id"], ()):
                o = nodes[e[3] if e[2] == n["id"] else e[2]]
                if o["x"] is not None:
                    pts.append((o["x"], o["y"]))
            if pts:
                a = 2 * math.pi * _layout._unit(n["id"], "a")
                n["x"] = sum(p[0] for p in pts) / len(pts) + 24 * math.cos(a)
                n["y"] = sum(p[1] for p in pts) / len(pts) + 24 * math.sin(a)
    for n in nodes.values():
        if n["x"] is None:
            a = 2 * math.pi * _layout._unit(n["id"], "ring")
            r = 220 + 40 * _layout._unit(n["id"], "r")
            n["x"], n["y"] = r * math.cos(a), r * math.sin(a)


def resolve(conn, node_id: str) -> str | None:
    """A map id (projection id, KB uuid or link:<uuid>) -> the model's id."""
    m = model(conn)
    nid = (node_id or "").strip()
    if nid in m["nodes"]:
        return nid
    return m["by_kb"].get(nid)


def _other(e, nid):
    return e[3] if e[2] == nid else e[2]


def _edge_row(e) -> dict:
    return {"id": e[0], "rel": e[1], "source_id": e[2], "target_id": e[3], "props": e[4]}


def _node_row(m, n, full=False) -> dict:
    props = dict(n["props"])
    if full:
        props.update(m["extra"].get(n["id"], {}))
    return {"id": n["id"], "type": n["type"], "label": n["label"], "label_raw": None, "sensitive": False,
            "props": props}


# ---------------------------------------------------------------------------- the routes (data.py's shapes)
def _in_structure(t: str) -> bool:
    """The structure layer's types, and every type the projection never had (a
    course, a type made in the KB): the map carries them so they can be found,
    opened and followed; the deferred content types still load on demand."""
    return t in STRUCTURE_TYPES or (t not in DEFERRED_TYPES and t not in _known_types())


def _known_types() -> set:
    return set(_tax.node_type_names())


def structure(conn) -> dict:
    m = model(conn)
    prov = mapping()["provenance"]
    keep = {i for i, n in m["nodes"].items() if _in_structure(n["type"])}
    nodes = [(i, n["type"], n["label"], None, n["props"], n["x"], n["y"])
             for i, n in sorted(m["nodes"].items()) if i in keep]
    edges = sorted(((e[0], e[1], e[2], e[3], e[4]) for e in m["edges"]
                    if e[1] != prov and e[2] in keep and e[3] in keep), key=lambda e: e[0])
    out = _data.pack_structure(nodes, edges)
    counts: dict = defaultdict(int)
    for n in m["nodes"].values():
        counts[n["type"]] += 1
    out["counts"] = dict(counts)
    out["source"] = "kb"
    return out


def structure_etag(conn) -> str | None:
    """Changes with the newest kb.changes id, the wire format and the caller's
    roles (a member and an admin never share a validator)."""
    h, can, role = head(conn)
    if not can:
        return None
    np_role = _q(conn, "select np_role()")[0][0]
    raw = "|".join([_data.STRUCTURE_FORMAT, "kb", str(h), str(np_role), role])
    return '"' + hashlib.sha256(raw.encode()).hexdigest()[:32] + '"'


def node(conn, node_id: str) -> dict | None:
    m = model(conn)
    nid = resolve(conn, node_id)
    return _node_row(m, m["nodes"][nid], full=True) if nid else None


def provenance(conn, node_id: str) -> dict:
    """The KB keeps provenance as the record's "Source" links (the sync made one
    per cited file): shown as corpus rows with the file's name and link. The
    sheet / row / column detail of the old node_sources is not in the KB
    (listed in docs/architecture/overview.md), so those keys are empty."""
    m = model(conn)
    nid = resolve(conn, node_id)
    kid = m["nodes"][nid]["kb_id"] if nid else None
    rows = _q(conn, """select r.title, r.url from kb.node_resources nr join kb.resources r on r.id = nr.resource_id
                       where nr.node_id = %s and nr.note = %s and nr.archived_at is null and r.archived_at is null
                       order by r.title""", (kid, mapping()["source_note"])) if kid else []
    corpus = [{"origin": "corpus", "file": t, "sheet": None, "row_num": None, "col_num": None, "col_name": None,
               "page": None, "within_cell": None, "ordinal": None, "prop": None, "evidence": None,
               "entered_at": None, "drive_url": u, "sheet_count": None} for t, u in rows]
    return {"corpus": corpus, "hand": [], "hand_note": None}


def node_detail(conn, node_id: str) -> dict:
    m = model(conn)
    nid = resolve(conn, node_id)
    if not nid:
        return {"edges": [], "neighbours": []}
    prov = mapping()["provenance"]
    edges = [e for e in m["adj"].get(nid, ()) if e[1] != prov]
    nbrs = sorted({_other(e, nid) for e in edges})
    nbrs = [i for i in nbrs if _in_structure(m["nodes"][i]["type"])]
    keep = set(nbrs) | {nid}
    return {"edges": [_edge_row(e) for e in edges if e[2] in keep and e[3] in keep],
            "neighbours": [_node_row(m, m["nodes"][i], full=True) for i in nbrs]}


def neighbourhood(conn, node_id: str, depth: int = 1, rels: list[str] | None = None, limit: int = 300) -> dict:
    depth = int(depth)
    if depth < 1 or depth > MAX_DEPTH:
        raise DepthExceeded(
            f"depth {depth} is outside 1..{MAX_DEPTH}. The cap is deliberate: "
            "silently truncating a neighbourhood makes a tooling limit look "
            "like a sparse graph.")
    limit = max(1, min(int(limit), 1000))
    m = model(conn)
    seed = resolve(conn, node_id)
    if not seed:
        return {"nodes": [], "edges": [], "truncated": False, "depth": depth}
    prov = mapping()["provenance"]
    dist = {seed: 0}
    q = deque([seed])
    while q:
        x = q.popleft()
        if dist[x] >= depth:
            continue
        for e in m["adj"].get(x, ()):
            if e[1] == prov or (rels and e[1] not in rels):
                continue
            o = _other(e, x)
            if o not in dist:
                dist[o] = dist[x] + 1
                q.append(o)
    ordered = sorted(dist, key=lambda i: (dist[i], m["nodes"][i]["label"]))[:limit]
    ids = set(ordered)
    nodes = [{"id": i, "type": m["nodes"][i]["type"], "label": m["nodes"][i]["label"], "depth": dist[i]}
             for i in ordered]
    seen, edges = set(), []
    for i in ordered:
        for e in m["adj"].get(i, ()):
            if e[0] in seen or e[2] not in ids or e[3] not in ids:
                continue
            seen.add(e[0])
            edges.append(_edge_row(e))
    return {"nodes": nodes, "edges": edges, "truncated": len(nodes) >= limit, "depth": depth}


def search(conn, query: str, types: list[str] | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    m = model(conn)
    ql = (query or "").lower()
    hits = [n for n in m["nodes"].values()
            if ql in (n["label"] or "").lower() and (not types or n["type"] in types)]
    hits.sort(key=lambda n: (len(n["label"] or ""), n["label"] or ""))
    return [{"id": n["id"], "type": n["type"], "label": n["label"]} for n in hits[:limit]]


def overview(conn) -> dict:
    m = model(conn)
    rels = set(_data.OVERVIEW_RELS)
    t0 = _data.OVERVIEW_TYPE
    edges = [e for e in m["edges"] if e[1] in rels
             and (m["nodes"][e[2]]["type"] == t0 or m["nodes"][e[3]]["type"] == t0)]
    touched = {e[2] for e in edges} | {e[3] for e in edges}
    pick = sorted((n for n in m["nodes"].values() if n["type"] == t0 or n["id"] in touched),
                  key=lambda n: (n["type"], n["label"]))
    truncated = len(pick) > _data.OVERVIEW_CAP
    pick = pick[:_data.OVERVIEW_CAP]
    keep = {n["id"] for n in pick}
    edges = [e for e in edges if e[2] in keep and e[3] in keep]
    owner_rel = _tax.edge_for_role(_data.OWNER_ROLE)
    owned = {e[2] for e in edges if e[1] == owner_rel} | {e[3] for e in edges if e[1] == owner_rel}
    unowned = sorted(n["label"] for n in pick if n["type"] == t0 and n["id"] not in owned)
    return {"nodes": [{"id": n["id"], "type": n["type"], "label": n["label"], "label_raw": None,
                       "props": n["props"]} for n in pick],
            "edges": [_edge_row(e) for e in edges], "truncated": truncated, "unowned": unowned,
            "unowned_note": ("domains with no owner recorded. Not an error and not an empty "
                             "result: ownership is domain-level and blank is a real state. "
                             "Surfaced because the default view is where it is cheapest to "
                             "notice.") if unowned else None}


def coverage(conn) -> dict:
    """data.coverage's numbers, over the KB. Same keys, same caveats."""
    m = model(conn)
    N, E = m["nodes"], m["edges"]
    R = mapping()["R"]
    prog_t, mod_t, dom_t = R["programme"], R["module"], R["domain"]
    covers, contains = R["programme_covers"], R["programme_contains"]
    im, mi = _tax.edge_for_role("instructor_module"), _tax.edge_for_role("module_instructor")
    attach = {_tax.edge_for_role(r) for r in _data.DOMAIN_ATTACHMENT_ROLES}
    out_rels, in_rels, deg = defaultdict(set), defaultdict(set), defaultdict(int)
    for e in E:
        out_rels[e[2]].add(e[1])
        in_rels[e[3]].add(e[1])
        deg[e[2]] += 1
        deg[e[3]] += 1
    row = {
        "programs_without_domain": sum(1 for n in N.values() if n["type"] == prog_t and covers not in out_rels[n["id"]]),
        "modules_without_program": sum(1 for n in N.values() if n["type"] == mod_t and contains not in in_rels[n["id"]]),
        "modules_without_instructor": sum(1 for n in N.values() if n["type"] == mod_t
                                          and im not in in_rels[n["id"]] and mi not in out_rels[n["id"]]),
        "domains_without_owner": sum(1 for n in N.values() if n["type"] == dom_t and not (attach & out_rels[n["id"]])),
        "isolated_records": sum(1 for n in N.values() if not deg[n["id"]]),
    }
    row["workflow_ownership"] = (
        "OUT OF SCOPE — ownership in New Programs attaches to domains, not "
        "workflows. Never report 92 workflows as missing an owner.")
    row["counts_are_floors"] = (
        "person, instructor and module counts are floors over 127 of 374 "
        "worksheets, not totals.")
    row["two_module_populations"] = (
        "Modules come from two sources: keyed (domain, sequence) from the Resource "
        "Collection Mastersheet (current), and the older sheets (legacy). Read from "
        "the knowledge base: archived legacy records are not counted.")
    row["modules_without_program_caveat"] = (
        "Most legacy modules carry no programme relationship at all, so this "
        "number is dominated by a structural gap in the legacy layer rather "
        "than by missing data about any one module.")
    return row


def domain_labels(conn) -> list[str]:
    m = model(conn)
    dom_t = mapping()["R"]["domain"]
    return [n["label"] for n in m["nodes"].values() if n["type"] == dom_t]


def domain_subgraph(conn, domain_label: str) -> dict:
    """data.domain_subgraph over the KB: the same three tiers, never merged."""
    m = model(conn)
    X = mapping()
    R = X["R"]
    N = m["nodes"]
    doms = [n for n in N.values() if n["type"] == R["domain"] and n["label"].lower() == (domain_label or "").lower()]
    if not doms:
        return {"domain": None}
    d = doms[0]
    dom = {"id": d["id"], "label": d["label"], "props": d["props"]}

    def rel_edges(rel):
        return [e for e in m["edges"] if e[1] == rel]
    progs = {e[2] for e in rel_edges(R["programme_covers"]) if e[3] == d["id"]}
    mods = {e[3]: N[e[3]]["label"] for e in rel_edges(R["programme_contains"]) if e[2] in progs and N[e[3]]["type"] == R["module"]}
    taught = [{"id": e[2], "label": N[e[2]]["label"], "edge_props": e[4], "module": mods[e[3]]}
              for e in rel_edges(R["teaching"]) if e[3] in mods]
    declared = [{"id": e[2], "label": N[e[2]]["label"], "edge_props": e[4]}
                for e in rel_edges(_tax.edge_for_role("instructor_domain")) if e[3] == d["id"]]
    offered = {e[3] for e in rel_edges(_tax.edge_for_role("domain_module")) if e[2] == d["id"] and N[e[3]]["type"] == R["module"]}
    sheet = [{"id": e[3], "label": N[e[3]]["label"], "edge_props": e[4], "module": N[e[2]]["label"],
              "role": (e[4] or {}).get("instructor_role")}
             for e in rel_edges(_tax.edge_for_role("module_instructor")) if e[2] in offered]
    return {"domain": dom, "taught": taught, "declared": declared, "sheet": sheet}


def visible_count(conn) -> int:
    return len(model(conn)["nodes"])


def landing_stats(conn) -> dict:
    """The landing numbers (public/stats.json's keys), from kb at request time,
    through kb.landing_stats() (0033: counts only, no row content)."""
    r = _q(conn, "select kb.landing_stats()")[0][0] or {}
    return r
