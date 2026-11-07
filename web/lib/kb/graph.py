"""The one graph read API (run 6, docs/architecture/contracts.md §1): GET /api/kb/graph.

Behind every graph: the knowledge base Graph page and the NP Autopilot map at
"/". Runs as the caller (RLS decides what is visible). Lead-owned: a change to
the response shape is a contract change.
"""
from __future__ import annotations

from . import validate as v
from .errors import Invalid, NotFound
from .profile import OWNED_BY
from .service import _q, _q1, _cursor_decode, _cursor_encode

DEFAULT_LIMIT = 2000
MAX_LIMIT = 5000
LEGACY = ("current", "all", "only")


def _keys(raw, field: str) -> list[str] | None:
    if raw in (None, ""):
        return None
    keys = [k.strip() for k in str(raw).split(",") if k.strip()]
    for k in keys:
        if not k.replace("_", "").isalnum():
            raise Invalid(f"{field}: {k!r} is not a type key", field=field)
    return keys or None


def _int(raw, field: str, lo: int, hi: int, default: int) -> int:
    if raw in (None, ""):
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise Invalid(f"{field} must be a whole number", field=field) from None
    if not lo <= n <= hi:
        raise Invalid(f"{field} must be between {lo} and {hi}", field=field)
    return n


def read(conn, params: dict) -> dict:
    types = _keys(params.get("types"), "types")
    rels = _keys(params.get("rels"), "rels")
    legacy = params.get("legacy") or "current"
    if legacy not in LEGACY:
        raise Invalid("legacy must be current, all or only", field="legacy")
    archived = params.get("archived") in ("1", "true")
    limit = _int(params.get("limit"), "limit", 1, MAX_LIMIT, DEFAULT_LIMIT)
    focus = v.uid(params["focus"], "focus") if params.get("focus") else None
    depth = _int(params.get("depth"), "depth", 1, 2, 1)
    scope = v.uid(params["scope"], "scope") if params.get("scope") else None
    for rid, name in ((focus, "focus"), (scope, "scope")):
        if rid and not _q1(conn, "select 1 from kb.nodes where id = %s", (rid,)):
            raise NotFound(f"no record with id {rid}", field=name)

    # The node filter, written once and used for both ends of every relationship.
    f = {"types": types, "legacy": legacy, "archived": archived, "scope": scope}
    node_ok = """(%(types)s::text[] is null or t.key = any(%(types)s))
        and (%(archived)s or n.archived_at is null)
        and (%(legacy)s = 'all' or (%(legacy)s = 'only') = n.is_legacy)
        and (%(scope)s::uuid is null or n.id in (select id from in_scope))"""
    scope_cte = """with recursive in_scope(id) as (
            select %(scope)s::uuid where %(scope)s::uuid is not null
            union select c.id from kb.nodes c join in_scope s on c.scope_id = s.id)"""
    head = _q1(conn, "select coalesce(max(id), 0) as m from kb.changes")["m"]

    if focus:
        rows = _q(conn, scope_cte + """, walk(id, dist) as (
                select %(seed)s::uuid, 0
                union
                select case when e.source_id = w.id then e.target_id else e.source_id end, w.dist + 1
                from walk w join kb.edges e on (e.source_id = w.id or e.target_id = w.id)
                     and (%(archived)s or e.archived_at is null)
                join kb.edge_types et on et.id = e.edge_type_id
                where w.dist < %(depth)s and (%(rels)s::text[] is null or et.key = any(%(rels)s)))
            select n.id from (select id, min(dist) as dist from walk group by id) b
            join kb.nodes n on n.id = b.id join kb.node_types t on t.id = n.type_id
            where b.dist = 0 or (""" + node_ok + """)
            order by b.dist, n.name_norm, n.id""", {**f, "seed": focus, "depth": depth, "rels": rels})
        total = len(rows)
        ids = [r["id"] for r in rows[:limit]]
        next_cursor = None
    else:
        after = _cursor_decode(params.get("cursor"))
        rows = _q(conn, scope_cte + """
            select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
            where """ + node_ok + """ and (%(after)s::uuid is null or n.id > %(after)s::uuid)
            order by n.id limit %(lim)s""", {**f, "after": after, "lim": limit + 1})
        total = _q1(conn, scope_cte + """
            select count(*) as c from kb.nodes n join kb.node_types t on t.id = n.type_id where """ + node_ok, f)["c"]
        ids = [r["id"] for r in rows[:limit]]
        next_cursor = _cursor_encode(str(ids[-1])) if len(rows) > limit and ids else None

    nodes = _q(conn, f"""
        select n.id, t.key as type, n.name, n.status, n.scope_id, n.is_legacy,
               n.archived_at is not null as archived, n.external_id, n.version,
               (select array_agg(e.target_id::text order by e.target_id) from kb.edges e
                  join kb.edge_types et on et.id = e.edge_type_id and et.key = '{OWNED_BY}'
                 where e.source_id = n.id and e.archived_at is null) as owners,
               (select count(*) from kb.edges e where (%(archived)s or e.archived_at is null)
                  and (e.source_id = n.id or e.target_id = n.id)) as degree
        from kb.nodes n join kb.node_types t on t.id = n.type_id
        where n.id = any(%(ids)s::uuid[]) order by n.id""", {"ids": ids, "archived": archived})

    # Each relationship arrives with the page of its SOURCE; its target must pass the
    # same filters (focus mode: both ends in the returned set).
    edge_sql = scope_cte + """
        select e.id, et.key as type, e.source_id as source, e.target_id as target,
               case when e.props ->> 'role' = 'backup' and e.props ? 'rank' then 'backup ' || (e.props ->> 'rank')
                    else e.props ->> 'role' end as role, (s.is_legacy or tn.is_legacy) as is_legacy,
               e.archived_at is not null as archived, e.version, e.note
        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
        join kb.nodes s on s.id = e.source_id
        join kb.nodes tn on tn.id = e.target_id
        join kb.node_types t on t.id = tn.type_id
        where e.source_id = any(%(ids)s::uuid[])
          and (%(archived)s or e.archived_at is null)
          and (%(rels)s::text[] is null or et.key = any(%(rels)s))
          and """
    if focus:
        edges = _q(conn, edge_sql + "e.target_id = any(%(ids)s::uuid[]) order by e.id", {**f, "ids": ids, "rels": rels})
    else:
        edges = _q(conn, edge_sql + "(" + node_ok.replace("n.", "tn.") + ") order by e.id",
                   {**f, "ids": ids, "rels": rels})
    return {"nodes": nodes, "edges": edges, "total_nodes": total,
            "truncated": total > len(ids) if focus else next_cursor is not None,
            "next_cursor": next_cursor, "head": head}
