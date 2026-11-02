"""Workspace features built on the core service: bulk actions, the Archived
page, the outline, flags, templates, saved views, completeness, and the
dashboard's "needs attention" list. Same rules as service.py: every write is
checked here AND by RLS; every failure is a KbError naming what to fix.
"""
from __future__ import annotations

import json

from . import validate as v
from .errors import Conflict, Forbidden, Invalid, KbError, NeedsApproval, NotFound
from .service import (ROLES, Actor, _q, _q1, _translate, archive_node, create_node, get_node, require,
                      role, tag_node)

#: Types whose records are expected to carry links (slides, recordings, briefs…).
#: Containers of people or concepts are not.
NO_LINKS_EXPECTED = ("instructor", "domain", "topic", "process", "program")


# ---------------------------------------------------------------------------
# bulk
# ---------------------------------------------------------------------------

def _ids(body: dict) -> list[str]:
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids:
        raise Invalid("select at least one record", field="ids")
    if len(ids) > 500:
        raise Invalid("at most 500 records at once", field="ids")
    return [v.uid(i, "ids") for i in ids]


def bulk_update(conn, actor: Actor, body: dict) -> dict:
    """Set owner / status / review status, add or remove tags, or add a
    placement on many records in one transaction. Field-level sets, so no
    version check: a bulk change never overwrites a field it does not name."""
    require(conn, "contributor", "editing records")
    v.only(body, {"ids", "set", "add_tags", "remove_tags", "add_parent"})
    ids = _ids(body)
    s = body.get("set") or {}
    if not isinstance(s, dict):
        raise Invalid("set must be an object", field="set")
    v.only(s, {"owner_id", "status", "review_status"})
    sets, args = [], []
    if "owner_id" in s:
        sets.append("owner_id = %s"); args.append(v.uid(s["owner_id"], "owner_id", required=False))
    if "status" in s:
        sets.append("status = %s"); args.append(v.choice(s, "status", v.NODE_STATUSES))
    if "review_status" in s:
        sets.append("review_status = %s"); args.append(v.choice(s, "review_status", ("none", "needs_review", "approved")))
    live = [r["id"] for r in _q(conn, "select id from kb.nodes where id = any(%s) and archived_at is null", (ids,))]
    if len(live) != len(ids):
        raise Invalid(f"{len(ids) - len(live)} selected record(s) are archived or missing", field="ids")
    with _translate(conn, "record"):
        if sets:
            _q(conn, f"update kb.nodes set {', '.join(sets)} where id = any(%s)", (*args, ids))
        for t in body.get("add_tags") or []:
            for i in ids:
                try:
                    tag_node(conn, actor, i, {"name": t})
                except KbError as exc:
                    if exc.status != 409:
                        raise
        for t in body.get("remove_tags") or []:
            _q(conn, """delete from kb.node_tags nt using kb.tags g where g.id = nt.tag_id
                        and nt.node_id = any(%s) and g.name_norm = kb.norm(%s)""", (ids, t))
        if body.get("add_parent"):
            from .service import create_edge
            parent = v.uid(body["add_parent"], "add_parent")
            for i in ids:
                if not _q1(conn, """select 1 from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                                    where et.key = 'contains' and e.source_id = %s and e.target_id = %s
                                      and e.archived_at is null""", (parent, i)):
                    try:
                        create_edge(conn, actor, {"type": "contains", "source_id": parent, "target_id": i})
                    except KbError as exc:
                        name = (_q1(conn, "select name from kb.nodes where id = %s", (i,)) or {}).get("name")
                        raise type(exc)(f"{name}: {exc.message}", **exc.details) from None
    return {"updated": len(ids)}


def bulk_archive(conn, actor: Actor, body: dict) -> dict:
    require(conn, "contributor", "archiving records")
    v.only(body, {"ids", "reason"})
    ids = _ids(body)
    if actor.actor_type == "ai" or ROLES.index(role(conn)) < ROLES.index("editor"):
        n = 0
        for i in ids:
            try:
                archive_node(conn, actor, i, {"reason": body.get("reason")})
            except NeedsApproval:
                n += 1
        raise NeedsApproval(f"{n} archive request(s) sent for approval", count=n)
    impact = {"records": 0, "edges": 0, "resources": 0}
    for i in ids:
        out = archive_node(conn, actor, i)
        impact["records"] += 1
        impact["edges"] += out["impact"].get("edges", 0)
        impact["resources"] += out["impact"].get("resources", 0)
    return {"archived": len(ids), "impact": impact}


# ---------------------------------------------------------------------------
# archived
# ---------------------------------------------------------------------------

def archived(conn, params: dict) -> dict:
    """Everything archived, newest first: records, resources, relationships."""
    kind = v.choice(params, "kind", ("records", "resources", "relationships"), "records")
    limit = v.limit(params)
    if kind == "records":
        rows = _q(conn, """select n.id, n.name, t.key as type, t.label as type_label, n.archived_at, n.updated_by,
                                  (select count(*) from kb.edges e where (e.source_id = n.id or e.target_id = n.id)) as edges,
                                  (select count(*) from kb.node_resources nr where nr.node_id = n.id) as links
                           from kb.nodes n join kb.node_types t on t.id = n.type_id
                           where n.archived_at is not null order by n.archived_at desc limit %s""", (limit,))
    elif kind == "resources":
        rows = _q(conn, """select r.id, r.title as name, r.url, r.kind, r.archived_at, r.updated_by,
                                  (select count(*) from kb.node_resources nr where nr.resource_id = r.id) as links
                           from kb.resources r where r.archived_at is not null order by r.archived_at desc limit %s""",
                 (limit,))
    else:
        rows = _q(conn, """select e.id, s.name || ' ' || et.label || ' ' || t.name as name, e.archived_at, e.updated_by
                           from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                           join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
                           where e.archived_at is not null order by e.archived_at desc limit %s""", (limit,))
    return {"kind": kind, "items": rows}


def delete_impact(conn, table: str, row_id: str) -> dict:
    """What a permanent delete removes with the row (for the typed confirmation)."""
    row_id = v.uid(row_id, "id")
    if table == "nodes":
        return _q1(conn, """select (select count(*) from kb.edges where source_id = %(i)s or target_id = %(i)s) as relationships,
                                   (select count(*) from kb.node_resources where node_id = %(i)s) as links,
                                   (select count(*) from kb.node_tags where node_id = %(i)s) as tags,
                                   (select count(*) from kb.nodes where scope_id = %(i)s) as scoped_records""", {"i": row_id})
    if table == "resources":
        return _q1(conn, "select (select count(*) from kb.node_resources where resource_id = %s) as links", (row_id,))
    return {}


# ---------------------------------------------------------------------------
# outline (D1)
# ---------------------------------------------------------------------------

def outline(conn, params: dict) -> dict:
    """Program › Course › Domain › Module › Week › Session as a tree, built from
    `contains` relationships (ordered by position, then name). Roots: programs,
    plus containers no live program contains. Each node carries a link count
    and its completeness."""
    nodes = {str(r["id"]): r for r in _q(conn, """
        select n.id, n.name, t.key as type, t.label as type_label, t.color, t.icon, n.status, n.owner_id,
               (select count(*) from kb.node_resources nr where nr.node_id = n.id and nr.archived_at is null) as links
        from kb.nodes n join kb.node_types t on t.id = n.type_id where n.archived_at is null""")}
    edges = _q(conn, """select e.id, e.source_id, e.target_id, e.position from kb.edges e
                        join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                        where e.archived_at is null order by e.position nulls last""")
    kids: dict = {}
    has_parent = set()
    for e in edges:
        src, tgt = str(e["source_id"]), str(e["target_id"])
        if src in nodes and tgt in nodes:
            kids.setdefault(src, []).append((e["position"], str(e["id"]), tgt))
            has_parent.add(tgt)
    scores = completeness_map(conn)

    def build(nid, depth, seen):
        n = dict(nodes[nid])
        n["completeness"] = scores.get(str(nid), {}).get("score")
        ch = sorted(kids.get(nid, []), key=lambda k: (k[0] is None, k[0] or 0, nodes[k[2]]["name"].lower()))
        n["children"] = [] if depth >= 7 else [
            {**build(c, depth + 1, seen | {nid}), "edge_id": eid} for _, eid, c in ch if c not in seen]
        return n

    root = params.get("root")
    if root:
        root = v.uid(root, "root")
        if root not in nodes:
            raise NotFound("no live record with that id")
        roots = [root]
    else:
        roots = sorted([i for i, n in nodes.items() if n["type"] == "program"]
                       + [i for i, n in nodes.items() if n["type"] == "course" and i not in has_parent],
                       key=lambda i: (nodes[i]["type"] != "program", nodes[i]["name"].lower()))
    return {"roots": [build(r, 0, frozenset()) for r in roots]}


def reorder(conn, actor: Actor, body: dict) -> dict:
    """Set the order of a parent's children (drag to reorder)."""
    require(conn, "contributor", "reordering")
    parent = v.uid(body.get("parent_id"), "parent_id")
    child_ids = body.get("child_ids")
    if not isinstance(child_ids, list) or not child_ids:
        raise Invalid("child_ids must list the children in their new order", field="child_ids")
    with _translate(conn, "relationship"):
        for pos, cid in enumerate(child_ids):
            _q(conn, """update kb.edges e set position = %s from kb.edge_types et
                        where et.id = e.edge_type_id and et.key = 'contains' and e.source_id = %s
                          and e.target_id = %s and e.archived_at is null""", (pos, parent, v.uid(cid, "child_ids")))
    return {"ordered": len(child_ids)}


# ---------------------------------------------------------------------------
# completeness (D5)
# ---------------------------------------------------------------------------

def _record_checks(r: dict, tdef: dict, links: int, placed: bool) -> list[dict]:
    checks = [{"check": "owner", "ok": r["owner_id"] is not None, "label": "Has an owner"},
              {"check": "summary", "ok": bool((r["summary"] or "").strip()), "label": "Has a summary"}]
    for f in tdef["fields"]:
        if f.get("required") and not f.get("archived"):
            val = (r["props"] or {}).get(f["key"])
            checks.append({"check": "field:" + f["key"], "ok": val not in (None, "", []),
                           "label": f"{f['label']} filled in"})
    if tdef["key"] not in NO_LINKS_EXPECTED:
        checks.append({"check": "links", "ok": links > 0, "label": "Has at least one link"})
    if tdef["allowed_parents"]:
        checks.append({"check": "placement", "ok": placed, "label": "Placed under a " + " or ".join(tdef["allowed_parents"])})
    return checks


def completeness_map(conn, ids: list | None = None) -> dict:
    """{node_id: {score, missing: [labels]}} for live records (or `ids`)."""
    types = {t["id"]: t for t in _q(conn, "select id, key, fields, allowed_parents from kb.node_types")}
    rows = _q(conn, """select n.id, n.type_id, n.owner_id, n.summary, n.props,
                              (select count(*) from kb.node_resources nr where nr.node_id = n.id and nr.archived_at is null) as links,
                              exists (select 1 from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                                      where e.target_id = n.id and e.archived_at is null) as placed
                       from kb.nodes n where n.archived_at is null""" + (" and n.id = any(%s::uuid[])" if ids else ""),
              (ids,) if ids else ())
    out = {}
    for r in rows:
        checks = _record_checks(r, types[r["type_id"]], r["links"], r["placed"])
        ok = sum(1 for c in checks if c["ok"])
        out[str(r["id"])] = {"score": round(100 * ok / len(checks)) if checks else 100,
                        "missing": [c["label"] for c in checks if not c["ok"]]}
    return out


def completeness(conn, node_id: str) -> dict:
    """One record's score and what is missing; for a container, the average over
    everything it contains (to depth 6) as well."""
    node_id = v.uid(node_id, "id")
    own = completeness_map(conn, [node_id]).get(node_id)
    if own is None:
        raise NotFound("no live record with that id")
    sub = _q(conn, """with recursive tree(id, depth) as (
                        select %s::uuid, 0
                        union
                        select e.target_id, tree.depth + 1 from kb.edges e
                        join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                        join tree on tree.id = e.source_id where e.archived_at is null and tree.depth < 6)
                      select distinct id from tree""", (node_id,))
    ids = [str(r["id"]) for r in sub]
    scores = completeness_map(conn, ids)
    out = {**own, "id": node_id}
    if len(ids) > 1:
        vals = [s["score"] for s in scores.values()]
        out["tree_score"] = round(sum(vals) / len(vals))
        out["tree_size"] = len(ids)
        worst = sorted(((s["score"], i) for i, s in scores.items() if i != str(node_id) and s["missing"]))[:10]
        names = {str(r["id"]): r for r in _q(conn, """select n.id, n.name, t.key as type from kb.nodes n
                                                join kb.node_types t on t.id = n.type_id where n.id = any(%s)""",
                                        ([i for _, i in worst],))} if worst else {}
        out["weakest"] = [{**names[i], "score": sc, "missing": scores[i]["missing"]} for sc, i in worst if i in names]
    return out


def resource_completeness(conn, rid: str) -> dict:
    r = _q1(conn, """select r.id, r.description, r.owner_id, r.link_kind,
                            (select count(*) from kb.node_resources nr where nr.resource_id = r.id and nr.archived_at is null) as used,
                            (select status from kb.link_checks lc where lc.resource_id = r.id) as health
                     from kb.resources r where r.id = %s""", (v.uid(rid, "id"),))
    if not r:
        raise NotFound("no resource with that id")
    checks = [("Has a description", bool((r["description"] or "").strip())), ("Has an owner", r["owner_id"] is not None),
              ("Attached to a record", r["used"] > 0), ("Link is not known to be broken",
                                                        r["health"] not in ("broken", "forbidden", "unreachable"))]
    ok = sum(1 for _, c in checks if c)
    return {"score": round(100 * ok / len(checks)), "missing": [label for label, c in checks if not c]}


# ---------------------------------------------------------------------------
# dashboard: needs attention (real numbers only)
# ---------------------------------------------------------------------------

def needs_attention(conn, limit: int = 12) -> dict:
    no_owner = _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                           where n.archived_at is null and n.owner_id is null order by n.updated_at desc limit %s""", (limit,))
    broken = _q(conn, """select r.id, r.title as name, lc.http_status from kb.resources r
                         join kb.link_checks lc on lc.resource_id = r.id
                         where r.archived_at is null and lc.status in ('broken', 'forbidden', 'unreachable', 'timeout')
                         order by lc.checked_at desc limit %s""", (limit,))
    orphans = _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                          where n.archived_at is null and not exists (select 1 from kb.edges e where e.archived_at is null
                                and (e.source_id = n.id or e.target_id = n.id)) order by n.updated_at desc limit %s""", (limit,))
    missing = []
    for t in _q(conn, "select id, key, label, fields from kb.node_types where archived_at is null"):
        req = [f for f in t["fields"] if f.get("required") and not f.get("archived")]
        for f in req:
            for r in _q(conn, """select id, name from kb.nodes where type_id = %s and archived_at is null
                                 and coalesce(props->>%s, '') in ('', '[]') limit %s""", (t["id"], f["key"], limit)):
                missing.append({**r, "type": t["key"], "field": f["label"]})
    flagged = _q(conn, """select f.id as flag_id, f.target_id as id, coalesce(n.name, r.title) as name, f.reason, f.target_table
                          from kb.flags f left join kb.nodes n on f.target_table = 'nodes' and n.id = f.target_id
                          left join kb.resources r on f.target_table = 'resources' and r.id = f.target_id
                          where f.status = 'open' order by f.created_at desc limit %s""", (limit,))
    misfits = _q(conn, """select e.id, s.id as source_id, s.name as source, st.key as source_type, et.label,
                                 t.id as target_id, t.name as target, tt.key as target_type
                          from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                          join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
                          join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
                          where e.archived_at is null and s.archived_at is null and t.archived_at is null
                            and not exists (select 1 from kb.edge_type_rules r where r.edge_type_id = e.edge_type_id
                                and r.archived_at is null and r.source_type_id = s.type_id and r.target_type_id = t.type_id)
                          order by e.updated_at desc limit %s""", (limit,))
    return {"no_owner": no_owner, "broken_links": broken, "orphans": orphans,
            "missing_required": missing[:limit], "flagged": flagged, "misfits": misfits,
            **attention_counts(conn)}


# The ONE definition of "needs attention" (owner bug A1): the dashboard tile, the
# dashboard list, the sidebar's Data quality count and the Data quality page all
# read these numbers. Each is an exact count (never the length of a capped list);
# total = the sum of every category the list shows.
ATTENTION_KEYS = ("no_owner", "missing_required", "broken_links", "flagged", "orphans", "misfits")
BROKEN = "('broken', 'forbidden', 'unreachable', 'timeout')"


def attention_counts(conn) -> dict:
    c = _q1(conn, f"""select
        (select count(*) from kb.nodes where archived_at is null and owner_id is null) as no_owner,
        (select count(*) from kb.link_checks lc join kb.resources r on r.id = lc.resource_id
          where r.archived_at is null and lc.status in {BROKEN}) as broken_links,
        (select count(*) from kb.nodes n where n.archived_at is null and not exists (select 1 from kb.edges e
          where e.archived_at is null and (e.source_id = n.id or e.target_id = n.id))) as orphans,
        (select count(*) from kb.flags where status = 'open') as flagged,
        (select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
          cross join lateral jsonb_array_elements(t.fields) f
          where n.archived_at is null and t.archived_at is null and coalesce((f ->> 'required')::boolean, false)
            and not coalesce((f ->> 'archived')::boolean, false)
            and coalesce(n.props ->> (f ->> 'key'), '') in ('', '[]')) as missing_required,
        (select count(*) from kb.edges e join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
          where e.archived_at is null and s.archived_at is null and t.archived_at is null
            and not exists (select 1 from kb.edge_type_rules r where r.edge_type_id = e.edge_type_id
                and r.archived_at is null and r.source_type_id = s.type_id and r.target_type_id = t.type_id)) as misfits""")
    counts = {k: int(c[k] or 0) for k in ATTENTION_KEYS}
    return {"counts": counts, "total": sum(counts.values())}


def course_completeness(conn) -> list[dict]:
    """Completeness of every course and program over everything inside it, in
    three queries whatever the number of containers (was one completeness()
    call, ~5 queries, per container: an N+1 found in run 3's EXPLAIN pass)."""
    containers = _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                             where n.archived_at is null and t.is_container order by t.sort_order, n.name_norm""")
    if not containers:
        return []
    pairs = _q(conn, """with recursive tree(root, id, depth) as (
                            select n.id, n.id, 0 from kb.nodes n join kb.node_types t on t.id = n.type_id
                            where n.archived_at is null and t.is_container
                            union
                            select tree.root, e.target_id, tree.depth + 1 from kb.edges e
                            join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                            join tree on tree.id = e.source_id where e.archived_at is null and tree.depth < 6)
                        select distinct root, id from tree""")
    scores = completeness_map(conn)
    members: dict[str, list[str]] = {}
    for p_ in pairs:
        members.setdefault(str(p_["root"]), []).append(str(p_["id"]))
    out = []
    for c in containers:
        ids = [i for i in members.get(str(c["id"]), [str(c["id"])]) if i in scores]
        vals = [scores[i]["score"] for i in ids] or [scores.get(str(c["id"]), {"score": 0})["score"]]
        out.append({**c, "score": round(sum(vals) / len(vals)), "size": max(len(ids), 1)})
    return out


# ---------------------------------------------------------------------------
# flags (D3)
# ---------------------------------------------------------------------------

def create_flag(conn, actor: Actor, body: dict) -> dict:
    require(conn, "viewer", "flagging")
    v.only(body, {"target_table", "target_id", "reason"})
    table = v.choice(body, "target_table", ("nodes", "resources"), "nodes")
    tid = v.uid(body.get("target_id"), "target_id")
    reason = v.text(body, "reason", required=True, max_len=2000, allow_empty=False)
    owner = _q1(conn, f"select owner_id, archived_at from kb.{table} where id = %s", (tid,))
    if not owner:
        raise NotFound("nothing to flag with that id")
    with _translate(conn, "flag"):
        row = _q1(conn, "insert into kb.flags (target_table, target_id, reason, assigned_to) values (%s,%s,%s,%s) "
                        "returning id", (table, tid, reason, owner["owner_id"]))
    return get_flag(conn, row["id"])


def get_flag(conn, fid) -> dict:
    return _q1(conn, """select f.*, coalesce(n.name, r.title) as target_name
                        from kb.flags f left join kb.nodes n on f.target_table = 'nodes' and n.id = f.target_id
                        left join kb.resources r on f.target_table = 'resources' and r.id = f.target_id
                        where f.id = %s""", (fid,))


def list_flags(conn, params: dict) -> list[dict]:
    status = v.choice(params, "status", ("open", "resolved", "dismissed", "all"), "open")
    where, args = [], []
    if status != "all":
        where.append("f.status = %s"); args.append(status)
    if params.get("target"):
        where.append("f.target_id = %s"); args.append(v.uid(params["target"], "target"))
    return _q(conn, f"""select f.*, coalesce(n.name, r.title) as target_name,
                               coalesce(nt.key, 'resource') as target_type
                        from kb.flags f left join kb.nodes n on f.target_table = 'nodes' and n.id = f.target_id
                        left join kb.node_types nt on nt.id = n.type_id
                        left join kb.resources r on f.target_table = 'resources' and r.id = f.target_id
                        {'where ' + ' and '.join(where) if where else ''} order by f.created_at desc limit 200""", args)


def resolve_flag(conn, actor: Actor, fid: str, body: dict, outcome: str) -> dict:
    require(conn, "viewer", "resolving a flag")
    fid = v.uid(fid, "id")
    # No FOR UPDATE: under RLS it would hide the row from a caller who may read
    # but not close it; the UPDATE below is what RLS decides.
    f = _q1(conn, "select * from kb.flags where id = %s", (fid,))
    if not f:
        raise NotFound("no such flag")
    if f["status"] != "open":
        raise Conflict(f"this flag was already {f['status']}", current=f)
    with _translate(conn, "flag"):
        n = _q(conn, """update kb.flags set status = %s, resolution = %s, resolved_by = kb.actor_id(), resolved_at = now()
                        where id = %s returning id""", (outcome, v.text(body or {}, "resolution", max_len=2000), fid))
    if not n:
        raise Forbidden("only the assignee, the person who flagged it, or an editor can close this flag")
    return get_flag(conn, fid)


# ---------------------------------------------------------------------------
# templates (D4)
# ---------------------------------------------------------------------------

def _tree(conn, root: str, depth: int = 0) -> dict:
    n = _q1(conn, """select n.id, n.name, n.summary, n.props, t.key as type from kb.nodes n
                     join kb.node_types t on t.id = n.type_id where n.id = %s""", (root,))
    kids = _q(conn, """select e.target_id from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                       join kb.nodes c on c.id = e.target_id
                       where e.source_id = %s and e.archived_at is null and c.archived_at is null
                       order by e.position nulls last, c.name_norm""", (root,))
    return {"type": n["type"], "name": n["name"], "summary": n["summary"], "props": n["props"],
            "children": [] if depth >= 6 else [_tree(conn, k["target_id"], depth + 1) for k in kids]}


def create_template(conn, actor: Actor, body: dict) -> dict:
    """Save a course/program's STRUCTURE (records, names, summaries, fields) —
    not its links, owners or relationships — as a reusable template."""
    require(conn, "editor", "saving a template")
    v.only(body, {"source_id", "name", "description"})
    src = get_node(conn, v.uid(body.get("source_id"), "source_id"), detail=False)
    name = v.text(body, "name", max_len=200) or f"{src['name']} template"
    tree = _tree(conn, str(src["id"]))
    with _translate(conn, "template"):
        row = _q1(conn, "insert into kb.templates (name, description, root_type, structure, source_id) "
                        "values (%s,%s,%s,%s,%s) returning id",
                  (name, v.text(body, "description", max_len=1000), src["type"], json.dumps(tree), src["id"]))
    return _q1(conn, "select * from kb.templates where id = %s", (row["id"],))


def list_templates(conn) -> list[dict]:
    return _q(conn, """select id, name, description, root_type, source_id, created_at,
                              jsonb_array_length(structure->'children') as top_level
                       from kb.templates where archived_at is null order by name""")


def instantiate_template(conn, actor: Actor, tid: str, body: dict) -> dict:
    """Create a new course from a template in one transaction. Every name that
    contains the template root's name has it replaced by the new name."""
    require(conn, "editor", "creating from a template")
    v.only(body, {"name", "parents"})
    t = _q1(conn, "select * from kb.templates where id = %s and archived_at is null", (v.uid(tid, "id"),))
    if not t:
        raise NotFound("no such template")
    new_name = v.name(body)
    old_name = t["structure"]["name"]
    counts = {"records": 0}

    def make(spec, parent):
        nm = spec["name"].replace(old_name, new_name) if parent else new_name
        b = {"type": spec["type"], "name": nm, "summary": spec.get("summary"), "props": spec.get("props") or {}}
        if parent:
            b["parents"] = [parent]
        elif body.get("parents"):
            b["parents"] = body["parents"]
        try:
            n = create_node(conn, actor, b)
        except KbError as exc:
            raise type(exc)(f"{nm}: {exc.message}", **exc.details) from None
        counts["records"] += 1
        for c in spec.get("children") or []:
            make(c, str(n["id"]))
        return n

    root = make(t["structure"], None)
    return {"root": get_node(conn, str(root["id"]), detail=False), "created": counts["records"]}


def archive_template(conn, actor: Actor, tid: str) -> dict:
    require(conn, "editor", "removing a template")
    _q(conn, "update kb.templates set archived_at = now(), status = 'archived' where id = %s", (v.uid(tid, "id"),))
    return {"archived": tid}


# ---------------------------------------------------------------------------
# saved views (D6)
# ---------------------------------------------------------------------------

def list_views(conn) -> list[dict]:
    return _q(conn, """select id, name, owner_id, shared, config, position, version, owner_id = kb.actor_id() as mine
                       from kb.saved_views where archived_at is null order by position, name""")


def save_view(conn, actor: Actor, body: dict, vid: str | None = None) -> dict:
    require(conn, "viewer", "saving a view")
    v.only(body, {"name", "shared", "config", "position", "version"})
    cfg = body.get("config")
    if cfg is not None and not isinstance(cfg, dict):
        raise Invalid("config must be an object", field="config")
    with _translate(conn, "view"):
        if vid:
            sets, args = [], []
            if "name" in body:
                sets.append("name = %s"); args.append(v.text(body, "name", required=True, max_len=80, allow_empty=False))
            for k in ("shared", "position"):
                if k in body:
                    sets.append(f"{k} = %s"); args.append(body[k])
            if cfg is not None:
                sets.append("config = %s"); args.append(json.dumps(cfg))
            row = _q1(conn, f"update kb.saved_views set {', '.join(sets) or 'name = name'} where id = %s "
                            "and owner_id = kb.actor_id() returning id", (*args, v.uid(vid, "id")))
            if not row:
                raise Forbidden("only the person who saved a view can change it")
        else:
            row = _q1(conn, "insert into kb.saved_views (name, owner_id, shared, config) values (%s, kb.actor_id(), %s, %s) "
                            "returning id", (v.text(body, "name", required=True, max_len=80, allow_empty=False),
                                             bool(body.get("shared")), json.dumps(cfg or {})))
    return _q1(conn, "select * from kb.saved_views where id = %s", (row["id"],))


def delete_view(conn, actor: Actor, vid: str) -> dict:
    rows = _q(conn, "delete from kb.saved_views where id = %s and owner_id = kb.actor_id() returning id", (v.uid(vid, "id"),))
    if not rows:
        raise Forbidden("only the person who saved a view can delete it")
    return {"deleted": vid}


# ---------------------------------------------------------------------------
# graph layouts (run 3, B3): node positions per layout ('default' = the shared
# layout, or a saved graph view's id). Layout only: nothing here changes a
# record, so a move never bumps a record's version or causes a conflict.
# ---------------------------------------------------------------------------

def _layout(raw) -> str:
    lay = str(raw or "default")
    if lay != "default":
        lay = str(v.uid(lay, "layout"))
    return lay


def graph_positions(conn, params: dict) -> dict:
    lay = _layout(params.get("layout"))
    ids = [x for x in str(params.get("ids") or "").split(",") if x]
    if ids:
        ids = [str(v.uid(x, "ids")) for x in ids[:5000]]
        rows = _q(conn, "select node_id, x, y from kb.graph_positions where layout = %s and node_id = any(%s::uuid[])", (lay, ids))
    else:
        rows = _q(conn, "select node_id, x, y from kb.graph_positions where layout = %s limit 5000", (lay,))
    return {"layout": lay, "items": rows}


def save_graph_positions(conn, actor: Actor, body: dict) -> dict:
    require(conn, "contributor", "arranging the graph")
    v.only(body, {"layout", "positions"})
    lay = _layout(body.get("layout"))
    pos = body.get("positions")
    if not isinstance(pos, list) or not pos or len(pos) > 5000:
        raise Invalid("positions must be a list of 1-5000 {node_id, x, y}", field="positions")
    rows = []
    for p in pos:
        try:
            rows.append((lay, str(v.uid(p.get("node_id"), "node_id")), float(p["x"]), float(p["y"])))
        except (TypeError, KeyError, ValueError, AttributeError):
            raise Invalid("each position needs node_id, x and y", field="positions") from None
    with _translate(conn, "position"):
        with conn.cursor() as cur:
            cur.executemany("""insert into kb.graph_positions (layout, node_id, x, y) values (%s, %s, %s, %s)
                               on conflict (layout, node_id) do update set x = excluded.x, y = excluded.y,
                               updated_by = auth.uid(), updated_at = now()""", rows)
    return {"layout": lay, "saved": len(rows)}


def reset_graph_positions(conn, actor: Actor, params: dict) -> dict:
    require(conn, "contributor", "arranging the graph")
    lay = _layout(params.get("layout"))
    ids = [str(v.uid(x, "ids")) for x in str(params.get("ids") or "").split(",") if x]
    if ids:
        n = _q(conn, "delete from kb.graph_positions where layout = %s and node_id = any(%s::uuid[]) returning 1", (lay, ids))
    else:
        n = _q(conn, "delete from kb.graph_positions where layout = %s returning 1", (lay,))
    return {"layout": lay, "removed": len(n)}


# ---------------------------------------------------------------------------
# configuration CRUD completed in run 3 (B2): tags, memberships, templates,
# a relationship's type. Every change is audited by the triggers.
# ---------------------------------------------------------------------------

def update_tag(conn, actor: Actor, tag_id: str, body: dict) -> dict:
    require(conn, "editor", "renaming a tag")
    v.only(body, {"version", "name", "color"})
    tid = v.uid(tag_id, "id")
    sets, args = [], []
    if "name" in body:
        nm = v.text(body, "name", required=True, max_len=60, allow_empty=False)
        if _q1(conn, "select 1 from kb.tags where name_norm = kb.norm(%s) and id <> %s and archived_at is null", (nm, tid)):
            raise Invalid(f"a tag called {nm!r} already exists; merge into it instead", field="name")
        sets.append("name = %s"); args.append(nm)
    if "color" in body:
        sets.append("color = %s"); args.append(v.text(body, "color", required=True, max_len=7))
    if not sets:
        raise Invalid("nothing to change")
    with _translate(conn, "tag"):
        row = _q1(conn, f"update kb.tags set {', '.join(sets)} where id = %s and version = %s and archived_at is null "
                        "returning id, name, color, version", (*args, tid, v.version(body)))
    if not row:
        cur = _q1(conn, "select id, name, color, version from kb.tags where id = %s", (tid,))
        if not cur:
            raise NotFound("no such tag")
        raise Conflict("This tag changed since you opened it.", current=cur)
    return row


def tag_impact(conn, tag_id: str) -> dict:
    return _q1(conn, "select count(*) as records from kb.node_tags where tag_id = %s", (v.uid(tag_id, "id"),))


def merge_tag(conn, actor: Actor, tag_id: str, body: dict) -> dict:
    """Every record tagged `tag_id` is tagged `into` instead; the old tag is archived."""
    require(conn, "editor", "merging tags")
    v.only(body, {"into"})
    src, dst = v.uid(tag_id, "id"), v.uid(body.get("into"), "into")
    if src == dst:
        raise Invalid("choose a different tag to merge into", field="into")
    if not _q1(conn, "select 1 from kb.tags where id = %s and archived_at is null", (dst,)):
        raise NotFound("the tag to merge into does not exist")
    with _translate(conn, "tag"):
        moved = _q(conn, """insert into kb.node_tags (node_id, tag_id) select node_id, %s from kb.node_tags where tag_id = %s
                            on conflict do nothing returning node_id""", (dst, src))
        _q(conn, "delete from kb.node_tags where tag_id = %s", (src,))
        _q(conn, "update kb.tags set archived_at = now(), status = 'archived' where id = %s", (src,))
    return {"merged": str(src), "into": str(dst), "records": len(moved)}


def archive_tag(conn, actor: Actor, tag_id: str) -> dict:
    """Archiving a tag takes it off its records (returned, so Undo can put it
    back, and recorded in Activity) and out of pickers."""
    require(conn, "editor", "archiving a tag")
    tid = v.uid(tag_id, "id")
    with _translate(conn, "tag"):
        on = _q(conn, "delete from kb.node_tags where tag_id = %s returning node_id", (tid,))
        row = _q1(conn, "update kb.tags set archived_at = now(), status = 'archived' where id = %s and archived_at is null returning id", (tid,))
    if not row:
        raise NotFound("no live tag with that id")
    return {"archived": str(tid), "removed_from": [str(r["node_id"]) for r in on]}


def restore_tag(conn, actor: Actor, tag_id: str, body: dict | None = None) -> dict:
    require(conn, "editor", "restoring a tag")
    tid = v.uid(tag_id, "id")
    with _translate(conn, "tag"):
        row = _q1(conn, "update kb.tags set archived_at = null, status = 'active' where id = %s returning id, name", (tid,))
        for nid in (body or {}).get("records") or []:
            _q(conn, "insert into kb.node_tags (node_id, tag_id) values (%s, %s) on conflict do nothing", (v.uid(nid, "records"), tid))
    if not row:
        raise NotFound("no such tag")
    return row


def remove_member(conn, actor: Actor, user_id: str) -> dict:
    """Take away a person's knowledge-base role (archived, so it is audited and
    can be granted again). They keep what the main site's own access gives
    them: kb.role() falls back to viewer for signed-in site users."""
    require(conn, "admin", "removing a member")
    uid = v.uid(user_id, "user_id")
    if str(uid) == str(actor.user_id):
        raise Invalid("you cannot remove your own role; ask another admin")
    target = _q1(conn, "select role from kb.memberships where user_id = %s and archived_at is null", (uid,))
    if not target:
        raise NotFound("that person has no role to remove")
    if target["role"] == "admin" and (_q1(conn, "select count(*) as c from kb.memberships where role = 'admin' and archived_at is null") or {})["c"] <= 1:
        raise Invalid("the last admin cannot be removed")
    with _translate(conn, "membership"):
        _q(conn, "update kb.memberships set archived_at = now(), status = 'archived' where user_id = %s", (uid,))
    return {"removed": str(uid)}


def rename_template(conn, actor: Actor, tid: str, body: dict) -> dict:
    require(conn, "editor", "renaming a template")
    v.only(body, {"name"})
    nm = v.text(body, "name", required=True, max_len=120, allow_empty=False)
    with _translate(conn, "template"):
        row = _q1(conn, "update kb.templates set name = %s where id = %s and archived_at is null returning id, name", (nm, v.uid(tid, "id")))
    if not row:
        raise NotFound("no live template with that id")
    return row


def restore_template(conn, actor: Actor, tid: str) -> dict:
    require(conn, "editor", "restoring a template")
    with _translate(conn, "template"):
        row = _q1(conn, "update kb.templates set archived_at = null, status = 'active' where id = %s returning id, name", (v.uid(tid, "id"),))
    if not row:
        raise NotFound("no such template")
    return row


def retype_edge(conn, actor: Actor, edge_id: str, body: dict) -> dict:
    """Change a relationship's type in one step: the old relationship is
    archived (kept in history) and one with the chosen type, the same two
    records and the same note is created, in one transaction."""
    require(conn, "contributor", "changing a relationship")
    v.only(body, {"type", "flip"})
    from .service import archive_edge, create_edge
    eid = v.uid(edge_id, "id")
    e = _q1(conn, "select source_id, target_id, note from kb.edges where id = %s and archived_at is null", (eid,))
    if not e:
        raise NotFound("no live relationship with that id")
    s, t = (e["target_id"], e["source_id"]) if body.get("flip") else (e["source_id"], e["target_id"])
    archive_edge(conn, actor, str(eid), {})
    return create_edge(conn, actor, {"type": body.get("type"), "source_id": str(s), "target_id": str(t),
                                     **({"note": e["note"]} if e["note"] else {})})
