"""KB service — the single source of KB business logic.

Every function takes a connection ALREADY scoped to the caller
(web/lib/data.request_connection: role `authenticated`, the caller's JWT claims)
and an Actor. So RLS (0023) is the enforcement; the role checks here exist to
fail fast with a sentence instead of a SQLSTATE, and they never grant anything
RLS would refuse.

The caller owns the transaction: commit on success, roll back on any KbError.
A multi-step write (node + inline course + resources + edges) is therefore one
transaction — it all lands or none of it does.

Limits (the wrapper's "never return the whole graph"): pages default 50, max
200; neighbourhood depth max 2 and max 300 nodes per response.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass

import psycopg
from psycopg import errors as pgerr

from . import validate as v
from .errors import Conflict, Duplicate, Forbidden, Invalid, KbError, NeedsApproval, NotFound

ROLES = ("none", "viewer", "contributor", "editor", "admin")
MAX_DEPTH = 2
MAX_NEIGHBOURHOOD = 300
TOKEN_PREFIX = "ikkb_"


@dataclass(frozen=True)
class Actor:
    user_id: str
    actor_type: str = "human"        # human | ai | import | system


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

def _rows(cur) -> list[dict]:
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _one(cur) -> dict | None:
    rows = _rows(cur)
    return rows[0] if rows else None


def _q(conn, sql: str, params=()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return _rows(cur)


def _q1(conn, sql: str, params=()) -> dict | None:
    rows = _q(conn, sql, params)
    return rows[0] if rows else None


def begin(conn, actor: Actor) -> None:
    """Attribute this transaction's writes (kb.audit reads the GUC)."""
    with conn.cursor() as cur:
        cur.execute("select set_config('kb.actor_type', %s, true)", (actor.actor_type,))


def role(conn) -> str:
    return (_q1(conn, "select kb.role() as r") or {}).get("r", "none")


def require(conn, want: str, doing: str) -> str:
    have = role(conn)
    if ROLES.index(have) < ROLES.index(want):
        raise Forbidden(f"{doing} needs the {want} role; you are {have}",
                        required_role=want, role=have)
    return have


class _translate:
    """Turn database refusals into KbErrors. RLS refusals become Forbidden."""

    def __init__(self, conn, what: str = "record"):
        self.conn, self.what = conn, what

    def __enter__(self):
        with self.conn.cursor() as cur:
            cur.execute("savepoint kb_op")
        return self

    def __exit__(self, et, exc, tb):
        if exc is None:
            with self.conn.cursor() as cur:
                cur.execute("release savepoint kb_op")
            return False
        if isinstance(exc, psycopg.Error):
            with self.conn.cursor() as cur:
                cur.execute("rollback to savepoint kb_op")
            diag = exc.diag
            hint = diag.message_hint or ""
            msg = diag.message_primary or str(exc)
            if isinstance(exc, pgerr.InsufficientPrivilege):
                raise Forbidden(msg if hint.startswith("kb_") else
                                f"you do not have permission to change this {self.what}") from None
            if isinstance(exc, pgerr.UniqueViolation):
                raise Duplicate(f"a {self.what} like this already exists",
                                constraint=diag.constraint_name) from None
            if isinstance(exc, (pgerr.CheckViolation, pgerr.NotNullViolation,
                                pgerr.StringDataRightTruncation)):
                raise Invalid(msg, constraint=diag.constraint_name, rule=hint or None) from None
            if isinstance(exc, pgerr.ForeignKeyViolation):
                raise Invalid(f"a referenced record does not exist ({msg})") from None
            if isinstance(exc, pgerr.RaiseException):
                raise Invalid(msg, rule=hint or None) from None
        return False


def _cursor_encode(values) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode()


def _cursor_decode(raw):
    if not raw:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(raw.encode()))
    except Exception:                                                  # noqa: BLE001
        raise Invalid("cursor is not valid; start from the first page", field="cursor") from None


# ---------------------------------------------------------------------------
# types and vocabulary
# ---------------------------------------------------------------------------

def node_types(conn) -> list[dict]:
    return _q(conn, "select id, key, label, color, icon, is_container, description, version "
                    "from kb.node_types where archived_at is null order by sort_order, label")


def edge_types(conn) -> list[dict]:
    types = _q(conn, "select id, key, label, inverse_label, description, allow_self, version "
                     "from kb.edge_types where archived_at is null order by label")
    rules = _q(conn, """select r.edge_type_id, s.key as source_type, t.key as target_type
                        from kb.edge_type_rules r
                        join kb.node_types s on s.id = r.source_type_id
                        join kb.node_types t on t.id = r.target_type_id
                        where r.archived_at is null""")
    for t in types:
        t["rules"] = [{"source": r["source_type"], "target": r["target_type"]}
                      for r in rules if r["edge_type_id"] == t["id"]]
    return types


def _type_id(conn, key: str) -> str:
    row = _q1(conn, "select id from kb.node_types where key = %s and archived_at is null", (key,))
    if not row:
        raise Invalid(f"unknown node type {key!r}", field="type")
    return row["id"]


def _edge_type(conn, key: str) -> dict:
    row = _q1(conn, "select id, key from kb.edge_types where key = %s and archived_at is null", (key,))
    if not row:
        raise Invalid(f"unknown relationship type {key!r}", field="type")
    return row


def create_node_type(conn, actor: Actor, body: dict) -> dict:
    require(conn, "admin", "adding a node type")
    v.only(body, {"key", "label", "color", "description", "is_container"})
    key = v.text(body, "key", required=True, max_len=40)
    label = v.text(body, "label", required=True, max_len=80)
    with _translate(conn, "node type"):
        return _q1(conn, "insert into kb.node_types (key, label, color, description, is_container) "
                         "values (%s,%s,coalesce(%s,'#64748b'),%s,coalesce(%s,false)) returning *",
                   (key, label, body.get("color"), body.get("description"), body.get("is_container")))


def add_edge_rule(conn, actor: Actor, body: dict) -> dict:
    require(conn, "admin", "changing relationship rules")
    et = _edge_type(conn, v.text(body, "type", required=True, max_len=40))
    s = _type_id(conn, v.text(body, "source_type", required=True, max_len=40))
    t = _type_id(conn, v.text(body, "target_type", required=True, max_len=40))
    with _translate(conn, "rule"):
        return _q1(conn, "insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id) "
                         "values (%s,%s,%s) returning id, version", (et["id"], s, t))


# ---------------------------------------------------------------------------
# nodes (courses and programs are node types; see 0022)
# ---------------------------------------------------------------------------

_NODE_COLS = """n.id, n.name, n.summary, n.body, n.status, n.version, n.props, n.scope_id,
    n.owner_id, n.external_id, n.created_by, n.updated_by, n.created_at, n.updated_at,
    n.archived_at, t.key as type, t.label as type_label, t.color as type_color,
    sc.name as scope_name, st.key as scope_type"""
_NODE_FROM = """kb.nodes n join kb.node_types t on t.id = n.type_id
    left join kb.nodes sc on sc.id = n.scope_id left join kb.node_types st on st.id = sc.type_id"""


def _node_row(conn, node_id: str) -> dict | None:
    return _q1(conn, f"select {_NODE_COLS} from {_NODE_FROM} where n.id = %s", (node_id,))


def get_node(conn, node_id: str, *, detail: bool = True) -> dict:
    node_id = v.uid(node_id, "id")
    node = _node_row(conn, node_id)
    if not node:
        raise NotFound(f"no record with id {node_id}")
    if not detail:
        return node
    node["tags"] = _q(conn, """select g.id, g.name, g.color from kb.node_tags nt
                               join kb.tags g on g.id = nt.tag_id where nt.node_id = %s
                               order by g.name_norm""", (node_id,))
    node["outgoing"] = _q(conn, """
        select e.id, e.version, e.note, et.key as type, et.label, o.id as node_id, o.name as node_name,
               ot.key as node_type, o.archived_at as node_archived_at
        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
        join kb.nodes o on o.id = e.target_id join kb.node_types ot on ot.id = o.type_id
        where e.source_id = %s and e.archived_at is null order by et.label, o.name_norm limit 200""",
        (node_id,))
    node["incoming"] = _q(conn, """
        select e.id, e.version, e.note, et.key as type, coalesce(et.inverse_label, et.label) as label,
               o.id as node_id, o.name as node_name, ot.key as node_type, o.archived_at as node_archived_at
        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
        join kb.nodes o on o.id = e.source_id join kb.node_types ot on ot.id = o.type_id
        where e.target_id = %s and e.archived_at is null order by et.label, o.name_norm limit 200""",
        (node_id,))
    node["resources"] = _q(conn, """
        select nr.id as attachment_id, nr.version as attachment_version, nr.note, r.id, r.url,
               r.title, r.kind, r.version
        from kb.node_resources nr join kb.resources r on r.id = nr.resource_id
        where nr.node_id = %s and nr.archived_at is null order by nr.position, r.title""", (node_id,))
    node["children_count"] = (_q1(conn, "select count(*) as c from kb.nodes where scope_id = %s "
                                        "and archived_at is null", (node_id,)) or {}).get("c", 0)
    return node


def list_nodes(conn, params: dict) -> dict:
    """Cursor-paginated, filterable. Sort: updated (default) or name."""
    limit = v.limit(params)
    sort = v.choice(params, "sort", ("updated", "name"), "updated")
    where, args = [], []
    status = params.get("status") or "live"
    if status == "live":
        where.append("n.archived_at is null")
    elif status == "archived":
        where.append("n.archived_at is not null")
    elif status in ("draft", "active"):
        where.append("n.status = %s"); args.append(status)
    elif status != "all":
        raise Invalid("status must be live, archived, draft, active or all", field="status")
    if params.get("type"):
        types = params["type"] if isinstance(params["type"], list) else str(params["type"]).split(",")
        where.append("t.key = any(%s)"); args.append(types)
    if params.get("scope"):
        where.append("n.scope_id = %s"); args.append(v.uid(params["scope"], "scope"))
    if params.get("owner"):
        where.append("n.owner_id = %s"); args.append(v.uid(params["owner"], "owner"))
    if params.get("created_by"):
        where.append("n.created_by = %s"); args.append(v.uid(params["created_by"], "created_by"))
    if params.get("tag"):
        where.append("exists (select 1 from kb.node_tags nt where nt.node_id = n.id and nt.tag_id = %s)")
        args.append(v.uid(params["tag"], "tag"))
    if params.get("q"):
        q = str(params["q"]).strip()[:200]
        where.append("(n.search @@ websearch_to_tsquery('simple', %s) or n.name_norm like %s)")
        args += [q, "%" + kb_like(q) + "%"]
    cur = _cursor_decode(params.get("cursor"))
    if sort == "updated":
        order = "n.updated_at desc, n.id desc"
        if cur:
            where.append("(n.updated_at, n.id) < (%s::timestamptz, %s::uuid)"); args += cur
    else:
        order = "n.name_norm asc, n.id asc"
        if cur:
            where.append("(n.name_norm, n.id) > (%s, %s::uuid)"); args += cur
    sql = (f"select {_NODE_COLS}, n.name_norm from {_NODE_FROM}"
           + (" where " + " and ".join(where) if where else "")
           + f" order by {order} limit %s")
    rows = _q(conn, sql, (*args, limit + 1))
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = None
    if more and rows:
        last = rows[-1]
        nxt = _cursor_encode([last["updated_at"], last["id"]] if sort == "updated"
                             else [last["name_norm"], last["id"]])
    for r in rows:
        r.pop("name_norm", None)
    return {"items": rows, "next_cursor": nxt, "limit": limit}


def kb_like(q: str) -> str:
    return " ".join(q.lower().split()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _existing_by_name(conn, type_id: str, scope_id, name: str) -> dict | None:
    return _q1(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                        where n.type_id = %s and n.scope_id is not distinct from %s
                          and n.name_norm = kb.norm(%s) and n.archived_at is null""",
               (type_id, scope_id, name))


def _insert_node(conn, *, type_key: str, name: str, summary=None, body=None, scope_id=None,
                 owner_id=None, status="active", props=None, external_id=None,
                 imported: bool = False) -> dict:
    type_id = _type_id(conn, type_key)
    dupe = _existing_by_name(conn, type_id, scope_id, name)
    if dupe:
        raise Duplicate(f"a {type_key} named {dupe['name']!r} already exists"
                        + (" in this scope" if scope_id else ""), existing=dupe)
    with _translate(conn, type_key):
        row = _q1(conn, """insert into kb.nodes (type_id, name, summary, body, scope_id, owner_id,
                               status, props, external_id, imported_at, imported_version)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                   case when %s then now() end, case when %s then 1 end)
                           returning id""",
                  (type_id, name, summary, body, scope_id, owner_id, status,
                   json.dumps(props or {}), external_id, imported, imported))
    return row


def _resolve_scope(conn, actor: Actor, body: dict):
    """`scope` is an id, or {"new": {"type": "course", "name": ...}} to create the
    course/program inline in the same transaction."""
    raw = body.get("scope")
    if raw in (None, ""):
        return None, None
    if isinstance(raw, dict) and "new" in raw:
        spec = raw["new"] or {}
        tkey = v.choice(spec, "type", tuple(t["key"] for t in node_types(conn) if t["is_container"]))
        if not tkey:
            raise Invalid("an inline scope needs a type (course or program)", field="scope")
        nm = v.name(spec)
        existing = _existing_by_name(conn, _type_id(conn, tkey), None, nm)
        if existing:
            return existing["id"], None     # reuse rather than fail: the picker's intent is clear
        created = _insert_node(conn, type_key=tkey, name=nm)
        return created["id"], created["id"]
    sid = v.uid(raw, "scope")
    sc = _q1(conn, """select n.id, t.is_container, n.archived_at from kb.nodes n
                      join kb.node_types t on t.id = n.type_id where n.id = %s""", (sid,))
    if not sc:
        raise Invalid("the chosen course/program does not exist", field="scope")
    if not sc["is_container"]:
        raise Invalid("a scope must be a course or a program", field="scope")
    if sc["archived_at"]:
        raise Invalid("the chosen course/program is archived", field="scope")
    return sid, None


NODE_FIELDS = {"type", "name", "summary", "body", "scope", "owner_id", "status", "props",
               "resources", "edges", "tags"}


def create_node(conn, actor: Actor, body: dict) -> dict:
    """Create a node, optionally with an inline new scope, resources and edges,
    all in one transaction."""
    require(conn, "contributor", "creating a record")
    v.only(body, NODE_FIELDS)
    type_key = v.text(body, "type", required=True, max_len=40)
    name = v.name(body)
    summary = v.text(body, "summary", max_len=v.SUMMARY_MAX)
    text_body = v.text(body, "body", max_len=v.BODY_MAX)
    status = v.choice(body, "status", v.NODE_STATUSES, "active")
    # Unless the caller says otherwise (including an explicit null), the creator
    # owns what they create: "No owner" is a gap the quality page reports.
    owner = (v.uid(body.get("owner_id"), "owner_id", required=False) if "owner_id" in body
             else actor.user_id)
    props = v.props(body)
    scope_id, created_scope = _resolve_scope(conn, actor, body)
    row = _insert_node(conn, type_key=type_key, name=name, summary=summary, body=text_body,
                       scope_id=scope_id, owner_id=owner, status=status, props=props)
    nid = row["id"]
    for res in body.get("resources") or []:
        attach_resource(conn, actor, nid, res)
    for e in body.get("edges") or []:
        if not isinstance(e, dict):
            raise Invalid("each edge must be an object", field="edges")
        spec = dict(e)
        direction = spec.pop("direction", "out")
        other = spec.pop("node_id", None)
        if direction == "out":
            spec.update(source_id=nid, target_id=other)
        else:
            spec.update(source_id=other, target_id=nid)
        create_edge(conn, actor, spec)
    for tag in body.get("tags") or []:
        tag_node(conn, actor, nid, tag)
    out = get_node(conn, nid)
    if created_scope:
        out["created_scope_id"] = created_scope
    return out


def update_node(conn, actor: Actor, node_id: str, body: dict, *, force: bool = False) -> dict:
    """Optimistic: `version` must match, else Conflict with the current record.
    `force` (editor+) overwrites a newer version deliberately."""
    require(conn, "contributor", "editing a record")
    node_id = v.uid(node_id, "id")
    v.only(body, {"version", "name", "summary", "body", "scope", "owner_id", "status", "props"})
    expected = v.version(body)
    if force:
        require(conn, "editor", "overwriting someone else's change")
    current = _node_row(conn, node_id)
    if not current:
        raise NotFound(f"no record with id {node_id}")
    if current["archived_at"]:
        raise Invalid("this record is archived; restore it before editing")
    sets, args = [], []
    if "name" in body:
        nm = v.name(body)
        sets.append("name = %s"); args.append(nm)
    for f, mx in (("summary", v.SUMMARY_MAX), ("body", v.BODY_MAX)):
        if f in body:
            sets.append(f"{f} = %s"); args.append(v.text(body, f, max_len=mx))
    if "status" in body:
        sets.append("status = %s"); args.append(v.choice(body, "status", v.NODE_STATUSES))
    if "owner_id" in body:
        sets.append("owner_id = %s"); args.append(v.uid(body["owner_id"], "owner_id", required=False))
    if "props" in body:
        sets.append("props = %s"); args.append(json.dumps(v.props(body) or {}))
    if "scope" in body:
        sid, _ = _resolve_scope(conn, actor, body)
        if sid == node_id:
            raise Invalid("a record cannot be its own scope", field="scope")
        sets.append("scope_id = %s"); args.append(sid)
    if not sets:
        raise Invalid("nothing to change")
    if "name" in body or "scope" in body:
        new_name = args[0] if "name" in body else current["name"]
        new_scope = sid if "scope" in body else current["scope_id"]
        dupe = _existing_by_name(conn, _type_id(conn, current["type"]), new_scope, new_name)
        if dupe and str(dupe["id"]) != node_id:
            raise Duplicate(f"a {current['type']} named {dupe['name']!r} already exists", existing=dupe)
    where = "id = %s" + ("" if force else " and version = %s")
    wargs = [node_id] if force else [node_id, expected]
    with _translate(conn, "record"):
        with conn.cursor() as cur:
            cur.execute(f"update kb.nodes set {', '.join(sets)} where {where}", (*args, *wargs))
            n = cur.rowcount
    if n == 0:
        if _node_row(conn, node_id) is None:
            raise NotFound(f"no record with id {node_id}")
        raise Conflict("This record changed since you opened it. Your change was NOT saved.",
                       current=get_node(conn, node_id), your_version=expected)
    return get_node(conn, node_id)


def archive_impact(conn, node_id: str) -> dict:
    node_id = v.uid(node_id, "id")
    r = _q1(conn, """select
        (select count(*) from kb.edges where (source_id = %(id)s or target_id = %(id)s) and archived_at is null) as edges,
        (select count(*) from kb.node_resources where node_id = %(id)s and archived_at is null) as resources,
        (select count(*) from kb.nodes where scope_id = %(id)s and archived_at is null) as scoped_records""",
            {"id": node_id})
    return r


def archive_node(conn, actor: Actor, node_id: str, body: dict | None = None) -> dict:
    node_id = v.uid(node_id, "id")
    if actor.actor_type == "ai" or ROLES.index(role(conn)) < ROLES.index("editor"):
        return propose(conn, actor, "archive", "nodes", node_id, (body or {}).get("reason"))
    node = _node_row(conn, node_id)
    if not node:
        raise NotFound(f"no record with id {node_id}")
    if node["archived_at"]:
        return {"node": get_node(conn, node_id), "impact": {"edges": 0, "resources": 0}}
    impact = archive_impact(conn, node_id)
    with _translate(conn, "record"):
        with conn.cursor() as cur:
            cur.execute("update kb.nodes set archived_at = now(), status = 'archived' "
                        "where id = %s and archived_at is null", (node_id,))
    return {"node": get_node(conn, node_id), "impact": impact}


def restore_node(conn, actor: Actor, node_id: str) -> dict:
    require(conn, "editor", "restoring a record")
    node_id = v.uid(node_id, "id")
    node = _node_row(conn, node_id)
    if not node:
        raise NotFound(f"no record with id {node_id}")
    if not node["archived_at"]:
        return get_node(conn, node_id)
    dupe = _existing_by_name(conn, _type_id(conn, node["type"]), node["scope_id"], node["name"])
    if dupe:
        raise Duplicate(f"cannot restore: a live {node['type']} named {dupe['name']!r} now exists; "
                        "rename one of them first", existing=dupe)
    with _translate(conn, "record"):
        with conn.cursor() as cur:
            cur.execute("update kb.nodes set archived_at = null, status = 'active' where id = %s",
                        (node_id,))
    return get_node(conn, node_id)


def duplicate_node(conn, actor: Actor, node_id: str) -> dict:
    """A copy with the same type, scope, text, tags and resource attachments.
    Relationships are NOT copied: an edge asserts a fact about the original."""
    require(conn, "contributor", "duplicating a record")
    src = get_node(conn, node_id)
    type_id = _type_id(conn, src["type"])
    base, n = f"{src['name']} (copy)", 1
    name = base
    while _existing_by_name(conn, type_id, src["scope_id"], name):
        n += 1
        name = f"{src['name']} (copy {n})"
    row = _insert_node(conn, type_key=src["type"], name=name[:v.NAME_MAX], summary=src["summary"],
                       body=src["body"], scope_id=src["scope_id"], owner_id=src["owner_id"],
                       status="draft", props=src["props"])
    for r in src["resources"]:
        attach_resource(conn, actor, row["id"], {"resource_id": str(r["id"]), "note": r["note"]})
    for t in src["tags"]:
        tag_node(conn, actor, row["id"], {"tag_id": str(t["id"])})
    return get_node(conn, row["id"])


def hard_delete(conn, actor: Actor, table: str, row_id: str) -> dict:
    require(conn, "admin", "permanently deleting")
    if table not in ("nodes", "edges", "resources"):
        raise Invalid("only nodes, edges and resources can be deleted")
    row_id = v.uid(row_id, "id")
    row = _q1(conn, f"select archived_at from kb.{table} where id = %s", (row_id,))
    if not row:
        raise NotFound(f"no {table[:-1]} with id {row_id}")
    if not row["archived_at"]:
        raise Invalid("archive it first; only archived records can be permanently deleted")
    with _translate(conn, table[:-1]):
        with conn.cursor() as cur:
            cur.execute(f"delete from kb.{table} where id = %s and archived_at is not null", (row_id,))
    return {"deleted": row_id}


# ---------------------------------------------------------------------------
# edges
# ---------------------------------------------------------------------------

def _edge_row(conn, edge_id: str) -> dict | None:
    return _q1(conn, """select e.id, e.version, e.note, e.props, e.status, e.archived_at, e.created_at,
                               e.updated_at, e.created_by, et.key as type, et.label,
                               e.source_id, s.name as source_name, st.key as source_type,
                               e.target_id, t.name as target_name, tt.key as target_type
                        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                        join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
                        join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
                        where e.id = %s""", (edge_id,))


def get_edge(conn, edge_id: str) -> dict:
    edge_id = v.uid(edge_id, "id")
    e = _edge_row(conn, edge_id)
    if not e:
        raise NotFound(f"no relationship with id {edge_id}")
    return e


def list_edges(conn, params: dict) -> dict:
    limit = v.limit(params)
    where, args = ["e.archived_at is null" if params.get("status", "live") == "live"
                   else "e.archived_at is not null"], []
    if params.get("node"):
        nid = v.uid(params["node"], "node")
        where.append("(e.source_id = %s or e.target_id = %s)"); args += [nid, nid]
    if params.get("type"):
        where.append("et.key = %s"); args.append(params["type"])
    cur = _cursor_decode(params.get("cursor"))
    if cur:
        where.append("(e.created_at, e.id) < (%s::timestamptz, %s::uuid)"); args += cur
    rows = _q(conn, f"""select e.id, e.version, e.note, et.key as type, et.label, e.created_at,
                               e.source_id, s.name as source_name, e.target_id, t.name as target_name
                        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                        join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
                        where {' and '.join(where)} order by e.created_at desc, e.id desc limit %s""",
              (*args, limit + 1))
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": rows, "limit": limit,
            "next_cursor": _cursor_encode([rows[-1]["created_at"], rows[-1]["id"]]) if more else None}


def create_edge(conn, actor: Actor, body: dict) -> dict:
    require(conn, "contributor", "connecting records")
    v.only(body, {"type", "source_id", "target_id", "note", "props"})
    et = _edge_type(conn, v.text(body, "type", required=True, max_len=40))
    s = v.uid(body.get("source_id"), "source_id")
    t = v.uid(body.get("target_id"), "target_id")
    note = v.text(body, "note", max_len=v.NOTE_MAX)
    dupe = _q1(conn, "select id from kb.edges where source_id = %s and target_id = %s "
                     "and edge_type_id = %s and archived_at is null", (s, t, et["id"]))
    if dupe:
        raise Duplicate("these two records are already connected by this relationship",
                        existing={"id": dupe["id"], "type": et["key"]})
    with _translate(conn, "relationship"):
        row = _q1(conn, "insert into kb.edges (edge_type_id, source_id, target_id, note, props) "
                        "values (%s,%s,%s,%s,%s) returning id",
                  (et["id"], s, t, note, json.dumps(v.props(body) or {})))
    return get_edge(conn, row["id"])


def update_edge(conn, actor: Actor, edge_id: str, body: dict) -> dict:
    require(conn, "contributor", "editing a relationship")
    edge_id = v.uid(edge_id, "id")
    v.only(body, {"version", "note", "props"})
    expected = v.version(body)
    with _translate(conn, "relationship"):
        with conn.cursor() as cur:
            cur.execute("update kb.edges set note = %s, props = coalesce(%s::jsonb, props) "
                        "where id = %s and version = %s and archived_at is null",
                        (v.text(body, "note", max_len=v.NOTE_MAX),
                         json.dumps(body["props"]) if "props" in body else None, edge_id, expected))
            n = cur.rowcount
    if n == 0:
        cur_row = _edge_row(conn, edge_id)
        if not cur_row:
            raise NotFound(f"no relationship with id {edge_id}")
        raise Conflict("This relationship changed since you opened it.", current=cur_row)
    return get_edge(conn, edge_id)


def archive_edge(conn, actor: Actor, edge_id: str, body: dict | None = None) -> dict:
    edge_id = v.uid(edge_id, "id")
    if actor.actor_type == "ai" or ROLES.index(role(conn)) < ROLES.index("editor"):
        return propose(conn, actor, "archive", "edges", edge_id, (body or {}).get("reason"))
    get_edge(conn, edge_id)
    with _translate(conn, "relationship"):
        with conn.cursor() as cur:
            cur.execute("update kb.edges set archived_at = now(), status = 'archived', archived_with = null "
                        "where id = %s and archived_at is null", (edge_id,))
    return get_edge(conn, edge_id)


def restore_edge(conn, actor: Actor, edge_id: str) -> dict:
    require(conn, "editor", "restoring a relationship")
    e = get_edge(conn, edge_id)
    if not e["archived_at"]:
        return e
    with _translate(conn, "relationship"):
        with conn.cursor() as cur:
            cur.execute("update kb.edges set archived_at = null, status = 'active', archived_with = null "
                        "where id = %s", (e["id"],))
    return get_edge(conn, e["id"])


# ---------------------------------------------------------------------------
# resources and attachments
# ---------------------------------------------------------------------------

def _resource_row(conn, rid) -> dict | None:
    return _q1(conn, """select r.id, r.url, r.title, r.kind, r.description, r.version, r.status,
                               r.archived_at, r.created_at, r.updated_at, r.created_by,
                               (select count(*) from kb.node_resources nr where nr.resource_id = r.id
                                  and nr.archived_at is null) as used_by
                        from kb.resources r where r.id = %s""", (rid,))


def find_resource_by_url(conn, url: str) -> dict | None:
    return _q1(conn, "select id, url, title, kind, version from kb.resources "
                     "where url_norm = lower(regexp_replace(btrim(%s), '/+$', '')) and archived_at is null",
               (url,))


def get_resource(conn, rid: str) -> dict:
    rid = v.uid(rid, "id")
    r = _resource_row(conn, rid)
    if not r:
        raise NotFound(f"no resource with id {rid}")
    r["nodes"] = _q(conn, """select n.id, n.name, t.key as type, nr.note from kb.node_resources nr
                             join kb.nodes n on n.id = nr.node_id join kb.node_types t on t.id = n.type_id
                             where nr.resource_id = %s and nr.archived_at is null order by n.name_norm""",
                    (rid,))
    return r


def list_resources(conn, params: dict) -> dict:
    limit = v.limit(params)
    where, args = ["r.archived_at is null" if params.get("status", "live") == "live"
                   else "r.archived_at is not null"], []
    if params.get("q"):
        q = "%" + kb_like(str(params["q"])[:200]) + "%"
        where.append("(lower(r.title) like %s or r.url_norm like %s)"); args += [q, q]
    if params.get("kind"):
        where.append("r.kind = %s"); args.append(params["kind"])
    cur = _cursor_decode(params.get("cursor"))
    if cur:
        where.append("(r.updated_at, r.id) < (%s::timestamptz, %s::uuid)"); args += cur
    rows = _q(conn, f"""select r.id, r.url, r.title, r.kind, r.version, r.updated_at, r.archived_at,
                               (select count(*) from kb.node_resources nr where nr.resource_id = r.id
                                  and nr.archived_at is null) as used_by
                        from kb.resources r where {' and '.join(where)}
                        order by r.updated_at desc, r.id desc limit %s""", (*args, limit + 1))
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": rows, "limit": limit,
            "next_cursor": _cursor_encode([rows[-1]["updated_at"], rows[-1]["id"]]) if more else None}


def create_resource(conn, actor: Actor, body: dict) -> dict:
    """Same URL twice → Duplicate naming the existing resource, so the caller
    can offer to link it instead."""
    require(conn, "contributor", "adding a resource")
    v.only(body, {"url", "title", "kind", "description"})
    url = v.url(body)
    title = v.text(body, "title", required=True, max_len=v.NAME_MAX, allow_empty=False)
    kind = v.choice(body, "kind", v.RESOURCE_KINDS, "link")
    existing = find_resource_by_url(conn, url)
    if existing:
        raise Duplicate("this URL is already a resource; link the existing one instead",
                        existing=existing)
    with _translate(conn, "resource"):
        row = _q1(conn, "insert into kb.resources (url, title, kind, description) values (%s,%s,%s,%s) "
                        "returning id", (url, title, kind, v.text(body, "description", max_len=v.SUMMARY_MAX)))
    return get_resource(conn, row["id"])


def update_resource(conn, actor: Actor, rid: str, body: dict, *, force: bool = False) -> dict:
    require(conn, "contributor", "editing a resource")
    rid = v.uid(rid, "id")
    v.only(body, {"version", "url", "title", "kind", "description"})
    expected = v.version(body)
    if force:
        require(conn, "editor", "overwriting someone else's change")
    sets, args = [], []
    if "url" in body:
        url = v.url(body)
        ex = find_resource_by_url(conn, url)
        if ex and str(ex["id"]) != rid:
            raise Duplicate("another resource already has this URL", existing=ex)
        sets.append("url = %s"); args.append(url)
    if "title" in body:
        sets.append("title = %s")
        args.append(v.text(body, "title", required=True, max_len=v.NAME_MAX, allow_empty=False))
    if "kind" in body:
        sets.append("kind = %s"); args.append(v.choice(body, "kind", v.RESOURCE_KINDS))
    if "description" in body:
        sets.append("description = %s"); args.append(v.text(body, "description", max_len=v.SUMMARY_MAX))
    if not sets:
        raise Invalid("nothing to change")
    where = "id = %s and archived_at is null" + ("" if force else " and version = %s")
    with _translate(conn, "resource"):
        with conn.cursor() as cur:
            cur.execute(f"update kb.resources set {', '.join(sets)} where {where}",
                        (*args, rid) if force else (*args, rid, expected))
            n = cur.rowcount
    if n == 0:
        cur_row = _resource_row(conn, rid)
        if not cur_row:
            raise NotFound(f"no resource with id {rid}")
        if cur_row["archived_at"]:
            raise Invalid("this resource is archived; restore it before editing")
        raise Conflict("This resource changed since you opened it. Your change was NOT saved.",
                       current=cur_row, your_version=expected)
    return get_resource(conn, rid)


def archive_resource(conn, actor: Actor, rid: str, body: dict | None = None) -> dict:
    rid = v.uid(rid, "id")
    if actor.actor_type == "ai" or ROLES.index(role(conn)) < ROLES.index("editor"):
        return propose(conn, actor, "archive", "resources", rid, (body or {}).get("reason"))
    get_resource(conn, rid)
    with _translate(conn, "resource"):
        with conn.cursor() as cur:
            cur.execute("update kb.resources set archived_at = now(), status = 'archived' "
                        "where id = %s and archived_at is null", (rid,))
    return get_resource(conn, rid)


def restore_resource(conn, actor: Actor, rid: str) -> dict:
    require(conn, "editor", "restoring a resource")
    r = get_resource(conn, rid)
    if not r["archived_at"]:
        return r
    ex = find_resource_by_url(conn, r["url"])
    if ex:
        raise Duplicate("cannot restore: another live resource has this URL", existing=ex)
    with _translate(conn, "resource"):
        with conn.cursor() as cur:
            cur.execute("update kb.resources set archived_at = null, status = 'active' where id = %s",
                        (r["id"],))
    return get_resource(conn, r["id"])


def attach_resource(conn, actor: Actor, node_id: str, body: dict) -> dict:
    """Attach an existing resource ({resource_id}) or a new one ({url, title}).
    A new URL that already exists REUSES the existing resource (reported as
    `reused: true`) rather than failing: attaching is the intent."""
    require(conn, "contributor", "attaching a resource")
    node_id = v.uid(node_id, "node_id")
    if not isinstance(body, dict):
        raise Invalid("a resource must be an object")
    note = v.text(body, "note", max_len=v.NOTE_MAX)
    reused = False
    if body.get("resource_id"):
        rid = v.uid(body["resource_id"], "resource_id")
        if not _resource_row(conn, rid):
            raise Invalid("that resource does not exist", field="resource_id")
    else:
        url = v.url(body)
        ex = find_resource_by_url(conn, url)
        if ex:
            rid, reused = str(ex["id"]), True
        else:
            rid = str(create_resource(conn, actor, {k: body[k] for k in ("url", "title", "kind", "description")
                                                    if k in body})["id"])
    already = _q1(conn, "select id from kb.node_resources where node_id = %s and resource_id = %s "
                        "and archived_at is null", (node_id, rid))
    if already:
        raise Duplicate("this resource is already attached to this record",
                        existing={"attachment_id": already["id"], "resource_id": rid})
    pos = (_q1(conn, "select coalesce(max(position), 0) + 1 as p from kb.node_resources where node_id = %s",
               (node_id,)) or {}).get("p", 1)
    with _translate(conn, "attachment"):
        row = _q1(conn, "insert into kb.node_resources (node_id, resource_id, note, position) "
                        "values (%s,%s,%s,%s) returning id, version", (node_id, rid, note, pos))
    return {"attachment_id": row["id"], "resource_id": rid, "node_id": node_id, "reused": reused}


def detach_resource(conn, actor: Actor, attachment_id: str) -> dict:
    """Detaching archives the attachment row (history kept); the resource stays
    in the library for reuse. Archiving is an editor action, so a contributor's
    detach becomes a proposal, like any other archive."""
    require(conn, "contributor", "detaching a resource")
    aid = v.uid(attachment_id, "attachment_id")
    row = _q1(conn, "select id from kb.node_resources where id = %s and archived_at is null", (aid,))
    if not row:
        raise NotFound("that attachment does not exist")
    if actor.actor_type == "ai" or ROLES.index(role(conn)) < ROLES.index("editor"):
        return propose(conn, actor, "archive", "node_resources", aid, "detach resource")
    with _translate(conn, "attachment"):
        with conn.cursor() as cur:
            cur.execute("update kb.node_resources set archived_at = now(), status = 'archived' where id = %s", (aid,))
    return {"detached": aid}


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------

def list_tags(conn) -> list[dict]:
    return _q(conn, """select g.id, g.name, g.color, g.version,
                              (select count(*) from kb.node_tags nt where nt.tag_id = g.id) as used_by
                       from kb.tags g where g.archived_at is null order by g.name_norm""")


def tag_node(conn, actor: Actor, node_id: str, body) -> dict:
    require(conn, "contributor", "tagging")
    node_id = v.uid(node_id, "node_id")
    if isinstance(body, str):
        body = {"name": body}
    if body.get("tag_id"):
        tid = v.uid(body["tag_id"], "tag_id")
    else:
        nm = v.text(body, "name", required=True, max_len=60, allow_empty=False)
        ex = _q1(conn, "select id from kb.tags where name_norm = kb.norm(%s) and archived_at is null", (nm,))
        if ex:
            tid = ex["id"]
        else:
            with _translate(conn, "tag"):
                tid = _q1(conn, "insert into kb.tags (name) values (%s) returning id", (nm,))["id"]
    with _translate(conn, "tag"):
        _q(conn, "insert into kb.node_tags (node_id, tag_id, created_by) values (%s,%s,kb.actor_id()) "
                 "on conflict do nothing", (node_id, tid))
    return {"node_id": node_id, "tag_id": tid}


def untag_node(conn, actor: Actor, node_id: str, tag_id: str) -> dict:
    require(conn, "contributor", "tagging")
    with _translate(conn, "tag"):
        _q(conn, "delete from kb.node_tags where node_id = %s and tag_id = %s",
           (v.uid(node_id, "node_id"), v.uid(tag_id, "tag_id")))
    return {"removed": True}


# ---------------------------------------------------------------------------
# neighbourhood and search
# ---------------------------------------------------------------------------

def neighbourhood(conn, node_id: str, depth=1, *, types=None, limit: int = MAX_NEIGHBOURHOOD) -> dict:
    """The node plus everything within `depth` hops (max 2), at most 300 nodes.
    When capped, `total` says how many there were — never a silent truncation."""
    node_id = v.uid(node_id, "id")
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        raise Invalid("depth must be 1 or 2", field="depth") from None
    if depth < 1 or depth > MAX_DEPTH:
        raise Invalid(f"depth must be between 1 and {MAX_DEPTH}", field="depth")
    limit = max(1, min(int(limit), MAX_NEIGHBOURHOOD))
    if not _node_row(conn, node_id):
        raise NotFound(f"no record with id {node_id}")
    type_filter = list(types) if types else None
    rows = _q(conn, """
        with recursive walk(id, dist) as (
            select %(seed)s::uuid, 0
            union
            select case when e.source_id = w.id then e.target_id else e.source_id end, w.dist + 1
            from walk w join kb.edges e on (e.source_id = w.id or e.target_id = w.id)
                                       and e.archived_at is null
            where w.dist < %(depth)s
        ), best as (select id, min(dist) as dist from walk group by id)
        select b.id, b.dist from best b join kb.nodes n on n.id = b.id join kb.node_types t on t.id = n.type_id
        where n.archived_at is null and (b.dist = 0 or %(types)s::text[] is null or t.key = any(%(types)s))
        order by b.dist, n.name_norm""", {"seed": node_id, "depth": depth, "types": type_filter})
    total = len(rows)
    keep = rows[:limit]
    ids = [r["id"] for r in keep]
    dist = {r["id"]: r["dist"] for r in keep}
    nodes = _q(conn, """select n.id, n.name, n.status, n.scope_id, t.key as type, t.color, t.label as type_label,
                               (select count(*) from kb.edges e where e.archived_at is null
                                  and (e.source_id = n.id or e.target_id = n.id)) as degree
                        from kb.nodes n join kb.node_types t on t.id = n.type_id where n.id = any(%s)""", (ids,))
    for n in nodes:
        n["distance"] = dist[n["id"]]
    edges = _q(conn, """select e.id, e.source_id, e.target_id, et.key as type, et.label
                        from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                        where e.archived_at is null and e.source_id = any(%s) and e.target_id = any(%s)
                        limit 2000""", (ids, ids))
    return {"center": node_id, "depth": depth, "nodes": nodes, "edges": edges,
            "total": total, "truncated": total > len(keep), "limit": limit}


def search(conn, q: str, *, types=None, limit: int = 20) -> dict:
    """Full-text (websearch syntax) plus trigram similarity on names, and
    resources by title/URL. Ranked; each hit names its type."""
    q = (q or "").strip()
    if not q:
        raise Invalid("q is required", field="q")
    q = q[:200]
    limit = max(1, min(int(limit), 50))
    nodes = _q(conn, """
        select n.id, n.name, n.summary, t.key as type, t.color, sc.name as scope_name,
               greatest(ts_rank(n.search, websearch_to_tsquery('simple', %(q)s)),
                        extensions.similarity(n.name_norm, kb.norm(%(q)s))) as score
        from kb.nodes n join kb.node_types t on t.id = n.type_id left join kb.nodes sc on sc.id = n.scope_id
        where n.archived_at is null
          and (%(types)s::text[] is null or t.key = any(%(types)s))
          and (n.search @@ websearch_to_tsquery('simple', %(q)s)
               or n.name_norm operator(extensions.%%) kb.norm(%(q)s)
               or n.name_norm like %(like)s)
        order by score desc, n.name_norm limit %(lim)s""",
               {"q": q, "types": list(types) if types else None, "like": "%" + kb_like(q) + "%", "lim": limit})
    resources = _q(conn, """
        select r.id, r.title, r.url, r.kind from kb.resources r
        where r.archived_at is null and (lower(r.title) like %(like)s or r.url_norm like %(like)s)
        order by r.title limit %(lim)s""", {"like": "%" + kb_like(q) + "%", "lim": min(limit, 10)})
    return {"q": q, "nodes": nodes, "resources": resources}


# ---------------------------------------------------------------------------
# proposals (approval-required changes)
# ---------------------------------------------------------------------------

def propose(conn, actor: Actor, action: str, table: str, target_id: str, reason=None) -> dict:
    require(conn, "contributor", "proposing a change")
    exists = _q1(conn, f"select id from kb.{table} where id = %s", (target_id,))
    if not exists:
        raise NotFound(f"no {table[:-1]} with id {target_id}")
    pending = _q1(conn, "select id from kb.proposals where target_id = %s and action = %s and status = 'pending'",
                  (target_id, action))
    if pending:
        raise NeedsApproval("this change is already awaiting approval", proposal_id=pending["id"])
    with _translate(conn, "proposal"):
        row = _q1(conn, "insert into kb.proposals (action, target_table, target_id, reason, actor_type) "
                        "values (%s,%s,%s,%s,%s) returning id",
                  (action, table, target_id, (reason or "")[:2000] or None, actor.actor_type))
    raise NeedsApproval(f"{action} recorded as a proposal; an editor must approve it in the app",
                        proposal_id=row["id"])


def list_proposals(conn, status: str = "pending") -> list[dict]:
    return _q(conn, """select p.id, p.action, p.target_table, p.target_id, p.reason, p.actor_type,
                              p.status, p.created_at, p.created_by, p.version,
                              coalesce(n.name, r.title, es.name || ' → ' || et.name) as target_label
                       from kb.proposals p
                       left join kb.nodes n on p.target_table = 'nodes' and n.id = p.target_id
                       left join kb.resources r on p.target_table = 'resources' and r.id = p.target_id
                       left join kb.edges e on p.target_table = 'edges' and e.id = p.target_id
                       left join kb.nodes es on es.id = e.source_id left join kb.nodes et on et.id = e.target_id
                       where p.status = %s order by p.created_at desc limit 200""", (status,))


def decide_proposal(conn, actor: Actor, proposal_id: str, approve: bool) -> dict:
    require(conn, "editor", "deciding a proposal")
    if actor.actor_type == "ai":
        raise Forbidden("an AI client cannot approve proposals; a person decides in the app")
    pid = v.uid(proposal_id, "id")
    p = _q1(conn, "select * from kb.proposals where id = %s for update", (pid,))
    if not p:
        raise NotFound("no such proposal")
    if p["status"] != "pending":
        raise Conflict(f"this proposal was already {p['status']}", current=p)
    if approve:
        human = Actor(actor.user_id, "human")
        if p["target_table"] == "nodes":
            archive_node(conn, human, str(p["target_id"]))
        elif p["target_table"] == "edges":
            archive_edge(conn, human, str(p["target_id"]))
        elif p["target_table"] == "resources":
            archive_resource(conn, human, str(p["target_id"]))
        elif p["target_table"] == "node_resources":
            with _translate(conn, "attachment"):
                _q(conn, "update kb.node_resources set archived_at = now(), status = 'archived' "
                         "where id = %s and archived_at is null", (p["target_id"],))
    with _translate(conn, "proposal"):
        return _q1(conn, "update kb.proposals set status = %s, decided_by = kb.actor_id(), decided_at = now() "
                         "where id = %s returning id, status, version", ("approved" if approve else "rejected", pid))


# ---------------------------------------------------------------------------
# activity, history, dashboard, change feed
# ---------------------------------------------------------------------------

def history(conn, row_id: str, limit: int = 50) -> list[dict]:
    return _q(conn, """select id, at, actor_id, actor_type, table_name, action, before, after
                       from kb.audit_log where row_id = %s order by id desc limit %s""",
              (v.uid(row_id, "id"), max(1, min(int(limit), 200))))


def changes(conn, since: int | None, limit: int = 200) -> dict:
    """The change feed clients poll for collaboration (M7). Cursor = audit id."""
    if since is None:
        last = _q1(conn, "select coalesce(max(id), 0) as m from kb.audit_log")
        return {"cursor": last["m"], "changes": []}
    rows = _q(conn, """select id, at, actor_id, actor_type, table_name, row_id, action,
                              coalesce(after ->> 'version', before ->> 'version') as version
                       from kb.audit_log where id > %s order by id limit %s""",
              (int(since), max(1, min(int(limit), 500))))
    return {"cursor": rows[-1]["id"] if rows else int(since), "changes": rows}


def dashboard(conn) -> dict:
    counts = _q(conn, """select t.key, t.label, t.color, count(n.id) as n
                         from kb.node_types t left join kb.nodes n on n.type_id = t.id and n.archived_at is null
                         where t.archived_at is null group by t.key, t.label, t.color, t.sort_order
                         order by t.sort_order""")
    totals = _q1(conn, """select
        (select count(*) from kb.nodes where archived_at is null) as nodes,
        (select count(*) from kb.edges where archived_at is null) as edges,
        (select count(*) from kb.resources where archived_at is null) as resources,
        (select count(*) from kb.nodes where archived_at is not null) as archived,
        (select count(*) from kb.proposals where status = 'pending') as pending_proposals""")
    recent = _q(conn, """select a.id, a.at, a.actor_id, a.actor_type, a.table_name, a.row_id, a.action,
                                coalesce(a.after ->> 'name', a.before ->> 'name', a.after ->> 'title',
                                         a.before ->> 'title') as label
                         from kb.audit_log a where a.table_name in ('nodes', 'edges', 'resources', 'node_resources')
                         order by a.id desc limit 20""")
    return {"counts": counts, "totals": totals, "recent": recent, "role": role(conn)}


# ---------------------------------------------------------------------------
# API tokens (MCP) and memberships
# ---------------------------------------------------------------------------

def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_token(conn, actor: Actor, body: dict) -> dict:
    """The raw token is returned ONCE and never stored."""
    require(conn, "viewer", "creating an API token")
    if actor.actor_type == "ai":
        raise Forbidden("an AI client cannot mint tokens")
    name = v.text(body, "name", required=True, max_len=80, allow_empty=False)
    days = body.get("expires_in_days", 90)
    if days is not None and (not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365):
        raise Invalid("expires_in_days must be 1-365", field="expires_in_days")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    with _translate(conn, "token"):
        row = _q1(conn, """insert into kb.api_tokens (user_id, name, token_hash, prefix, expires_at)
                           values (kb.actor_id(), %s, %s, %s, case when %s::int is null then null
                                   else now() + make_interval(days => %s::int) end)
                           returning id, name, prefix, expires_at, created_at""",
                  (name, hash_token(raw), raw[:12], days, days))
    row["token"] = raw
    return row


def list_tokens(conn) -> list[dict]:
    return _q(conn, """select id, name, prefix, expires_at, last_used_at, revoked_at, created_at
                       from kb.api_tokens where user_id = kb.actor_id() order by created_at desc""")


def revoke_token(conn, actor: Actor, token_id: str) -> dict:
    with _translate(conn, "token"):
        row = _q1(conn, "update kb.api_tokens set revoked_at = now() where id = %s and user_id = kb.actor_id() "
                        "and revoked_at is null returning id, revoked_at", (v.uid(token_id, "id"),))
    if not row:
        raise NotFound("no live token with that id")
    return row


def list_members(conn) -> list[dict]:
    require(conn, "admin", "listing roles")
    # Emails through kb.people(): profiles are self-only under RLS, so a plain
    # join showed an admin every OTHER member as a bare uuid.
    return _q(conn, """select m.user_id, m.role, m.version, m.updated_at, p.email
                       from kb.memberships m left join kb.people() p on p.user_id = m.user_id
                       order by m.role, p.email""")


def set_role(conn, actor: Actor, user_id: str, new_role: str) -> dict:
    require(conn, "admin", "granting roles")
    if new_role not in ROLES[1:]:
        raise Invalid("role must be viewer, contributor, editor or admin", field="role")
    with _translate(conn, "membership"):
        return _q1(conn, """insert into kb.memberships (user_id, role) values (%s, %s)
                            on conflict (user_id) do update set role = excluded.role
                            returning user_id, role, version""", (v.uid(user_id, "user_id"), new_role))


def me(conn) -> dict:
    return {"user_id": (_q1(conn, "select kb.actor_id() as u") or {}).get("u"), "role": role(conn)}


# ---------------------------------------------------------------------------
# import support (pipeline/kb_import_sheets.py) — same rules, import attribution
# ---------------------------------------------------------------------------

def import_lookup_node(conn, external_id: str) -> dict | None:
    return _q1(conn, """select n.id, n.name, n.summary, n.version, n.imported_version, n.archived_at, n.scope_id,
                               t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                        where n.external_id = %s""", (external_id,))


def import_find_live(conn, type_key: str, name: str, scope_id=None) -> dict | None:
    return _existing_by_name(conn, _type_id(conn, type_key), scope_id, name)


def import_create_node(conn, actor: Actor, *, type_key: str, name: str, summary=None,
                       scope_id=None, external_id: str) -> dict:
    require(conn, "admin", "importing")
    return _insert_node(conn, type_key=type_key, name=v.name({"name": name}), summary=summary,
                        scope_id=scope_id, external_id=external_id, imported=True)


def import_update_node(conn, actor: Actor, node_id, expected_version: int, *, name: str, summary) -> bool:
    """Apply sheet values ONLY if nobody edited the record in the app since the
    last import (version == imported_version, checked again in the WHERE)."""
    require(conn, "admin", "importing")
    with _translate(conn, "record"):
        with conn.cursor() as cur:
            cur.execute("""update kb.nodes set name = %s, summary = %s, imported_at = now(),
                                  imported_version = version + 1
                           where id = %s and version = %s and version = imported_version
                             and archived_at is null""",
                        (v.name({"name": name}), summary, node_id, expected_version))
            return cur.rowcount == 1


def import_lookup_resource(conn, external_id: str) -> dict | None:
    return _q1(conn, "select id, url, title, kind, version, imported_version, archived_at from kb.resources "
                     "where external_id = %s", (external_id,))


def import_create_resource(conn, actor: Actor, *, url: str, title: str, kind: str, external_id: str) -> dict:
    require(conn, "admin", "importing")
    with _translate(conn, "resource"):
        return _q1(conn, """insert into kb.resources (url, title, kind, external_id, imported_at, imported_version)
                            values (%s,%s,%s,%s,now(),1) returning id""", (url, title, kind, external_id))


def import_update_resource(conn, actor: Actor, rid, expected_version: int, *, title: str, kind: str) -> bool:
    require(conn, "admin", "importing")
    with _translate(conn, "resource"):
        with conn.cursor() as cur:
            cur.execute("""update kb.resources set title = %s, kind = %s, imported_at = now(),
                                  imported_version = version + 1
                           where id = %s and version = %s and version = imported_version and archived_at is null""",
                        (title, kind, rid, expected_version))
            return cur.rowcount == 1


def import_edge_exists(conn, type_key: str, source_id, target_id) -> bool:
    return bool(_q1(conn, """select 1 as x from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                             where et.key = %s and e.source_id = %s and e.target_id = %s
                               and e.archived_at is null""", (type_key, source_id, target_id)))


def import_attachment_exists(conn, node_id, resource_id) -> bool:
    return bool(_q1(conn, "select 1 as x from kb.node_resources where node_id = %s and resource_id = %s "
                          "and archived_at is null", (node_id, resource_id)))


# ---------------------------------------------------------------------------
# validation tools (MCP + data quality)
# ---------------------------------------------------------------------------

def find_missing_resources(conn, type_key: str | None = None, limit: int = 100) -> list[dict]:
    return _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                       where n.archived_at is null and (%s::text is null or t.key = %s)
                         and not exists (select 1 from kb.node_resources nr where nr.node_id = n.id
                                          and nr.archived_at is null)
                       order by t.sort_order, n.name_norm limit %s""", (type_key, type_key, min(limit, 500)))


def find_duplicate_nodes(conn, threshold: float = 0.6, limit: int = 50) -> list[dict]:
    """Near-duplicates by trigram similarity within a type. RANKS; never merges."""
    threshold = min(max(float(threshold), 0.3), 0.99)
    return _q(conn, """select a.id as a_id, a.name as a_name, b.id as b_id, b.name as b_name, t.key as type,
                              round(extensions.similarity(a.name_norm, b.name_norm)::numeric, 3) as similarity
                       from kb.nodes a join kb.nodes b on a.type_id = b.type_id and a.id < b.id
                       join kb.node_types t on t.id = a.type_id
                       where a.archived_at is null and b.archived_at is null
                         and extensions.similarity(a.name_norm, b.name_norm) >= %s
                       order by similarity desc limit %s""", (threshold, min(limit, 200)))


def validate_course_structure(conn, course_id: str) -> dict:
    node = get_node(conn, course_id)
    if node["type"] not in ("course", "program"):
        raise Invalid("validate_course_structure takes a course or program")
    children = _q(conn, """select n.id, n.name, t.key as type,
                                  (select count(*) from kb.node_resources nr where nr.node_id = n.id and nr.archived_at is null) as resources
                           from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                           join kb.nodes n on n.id = e.target_id join kb.node_types t on t.id = n.type_id
                           where e.source_id = %s and e.archived_at is null and n.archived_at is null
                           union
                           select n.id, n.name, t.key, (select count(*) from kb.node_resources nr
                                  where nr.node_id = n.id and nr.archived_at is null)
                           from kb.nodes n join kb.node_types t on t.id = n.type_id
                           where n.scope_id = %s and n.archived_at is null""", (node["id"], node["id"]))
    issues = []
    if not node["summary"]:
        issues.append({"severity": "warn", "issue": "no summary"})
    if not node["resources"]:
        issues.append({"severity": "warn", "issue": "no resources attached to the course itself"})
    if not children:
        issues.append({"severity": "error", "issue": "no modules or contents"})
    for c in children:
        if not c["resources"]:
            issues.append({"severity": "warn", "issue": f"{c['type']} {c['name']!r} has no resources",
                           "node_id": c["id"]})
    taught = [e for e in node["incoming"] if e["type"] == "teaches"]
    if not taught:
        issues.append({"severity": "info", "issue": "no instructor linked by `teaches`"})
    filled = sum(1 for c in children if c["resources"]) + (1 if node["resources"] else 0)
    score = round(100 * filled / (len(children) + 1)) if children else 0
    return {"course": {"id": node["id"], "name": node["name"], "type": node["type"]},
            "children": len(children), "issues": issues, "completeness": score}


def find_instructors(conn, *, course_id: str | None = None, q: str | None = None, limit: int = 50) -> list[dict]:
    """Instructors (node type `instructor`, names only) with what they teach.
    Filter by a course/module they teach, or by name."""
    where, args = ["i.archived_at is null", "it.key = 'instructor'"], []
    if course_id:
        where.append("""exists (select 1 from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                        where et.key = 'teaches' and e.source_id = i.id and e.target_id = %s
                          and e.archived_at is null)""")
        args.append(v.uid(course_id, "course_id"))
    if q:
        where.append("(i.name_norm like %s or i.search @@ websearch_to_tsquery('simple', %s))")
        args += ["%" + kb_like(q[:200]) + "%", q[:200]]
    rows = _q(conn, f"""select i.id, i.name, i.summary from kb.nodes i join kb.node_types it on it.id = i.type_id
                        where {' and '.join(where)} order by i.name_norm limit %s""", (*args, min(int(limit), 200)))
    for r in rows:
        r["teaches"] = _q(conn, """select n.id, n.name, t.key as type from kb.edges e
                                   join kb.edge_types et on et.id = e.edge_type_id and et.key = 'teaches'
                                   join kb.nodes n on n.id = e.target_id join kb.node_types t on t.id = n.type_id
                                   where e.source_id = %s and e.archived_at is null and n.archived_at is null
                                   order by n.name_norm""", (r["id"],))
    return rows


def quality_overview(conn, limit: int = 50) -> dict:
    """The data-quality dashboard: counts first, then the records to act on.
    Completeness per course/program = share of its contents (contains edges or
    scoped records) plus itself that carry at least one resource."""
    totals = _q1(conn, """select
        (select count(*) from kb.nodes n where n.archived_at is null) as live,
        (select count(*) from kb.nodes n where n.archived_at is null and not exists (
            select 1 from kb.edges e where e.archived_at is null and (e.source_id = n.id or e.target_id = n.id))) as orphans,
        (select count(*) from kb.nodes n where n.archived_at is null and n.owner_id is null) as no_owner,
        (select count(*) from kb.nodes n where n.archived_at is null and not exists (
            select 1 from kb.node_resources r where r.node_id = n.id and r.archived_at is null)) as no_resources,
        (select count(*) from kb.nodes n where n.archived_at is null and coalesce(btrim(n.summary), '') = '') as no_summary""")
    orphans = _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                          where n.archived_at is null and not exists (select 1 from kb.edges e where e.archived_at is null
                                and (e.source_id = n.id or e.target_id = n.id))
                          order by n.updated_at desc limit %s""", (limit,))
    courses = _q(conn, """
        with c as (select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                   where n.archived_at is null and t.is_container),
        kids as (select c.id as cid, k.id as kid from c
                 join kb.edges e on e.source_id = c.id and e.archived_at is null
                 join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                 join kb.nodes k on k.id = e.target_id and k.archived_at is null
                 union
                 select c.id, k.id from c join kb.nodes k on k.scope_id = c.id and k.archived_at is null),
        members as (select cid, kid as nid from kids union select id, id from c)
        select c.id, c.name, c.type, count(m.nid) - 1 as contents,
               round(100.0 * count(m.nid) filter (where exists (select 1 from kb.node_resources r
                     where r.node_id = m.nid and r.archived_at is null)) / count(m.nid)) as completeness
        from c join members m on m.cid = c.id group by c.id, c.name, c.type
        order by completeness asc, c.name limit %s""", (limit,))
    unowned = _q(conn, """select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                          where n.archived_at is null and n.owner_id is null
                          order by t.sort_order, n.name_norm limit %s""", (limit,))
    links = _q1(conn, """select count(*) as resources,
                                count(lc.resource_id) as checked,
                                count(*) filter (where lc.status = 'ok') as ok,
                                count(*) filter (where lc.status = 'needs_auth') as needs_auth,
                                count(*) filter (where lc.status in ('broken', 'forbidden', 'timeout', 'unreachable')) as problems
                         from kb.resources r left join kb.link_checks lc on lc.resource_id = r.id
                         where r.archived_at is null""")
    links["items"] = _q(conn, """select r.id, r.title, r.url, r.kind, lc.status, lc.http_status, lc.checked_at
                                 from kb.resources r join kb.link_checks lc on lc.resource_id = r.id
                                 where r.archived_at is null
                                   and lc.status in ('broken', 'forbidden', 'timeout', 'unreachable')
                                 order by lc.checked_at desc limit %s""", (limit,))
    return {"totals": totals, "orphans": orphans, "courses": courses, "unowned": unowned,
            "links": links, "duplicates": find_duplicate_nodes(conn, 0.6, 20)}


def record_link_results(conn, actor: Actor, results) -> dict:
    """Store the LAST check result per resource (kb.link_checks). The checking
    itself happens client-side (the MCP tool check_broken_links): this server
    never fetches a user-supplied URL."""
    require(conn, "editor", "recording link-check results")
    if not isinstance(results, list) or not results:
        raise Invalid("results must be a non-empty list", field="results")
    if len(results) > 200:
        raise Invalid("at most 200 results per call", field="results")
    saved = 0
    for r in results:
        if not isinstance(r, dict):
            raise Invalid("each result must be an object", field="results")
        rid = v.uid(r.get("id"), "id")
        status = v.choice(r, "status", v.LINK_STATUSES)
        if not status:
            raise Invalid("each result needs a status", field="status")
        http = r.get("http")
        if http is not None and (not isinstance(http, int) or not 100 <= http <= 599):
            raise Invalid("http must be an HTTP status code", field="http")
        final = v.text(r, "redirected_to", max_len=v.URL_MAX)
        with _translate(conn, "link check"):
            with conn.cursor() as cur:
                cur.execute("""insert into kb.link_checks (resource_id, status, http_status, final_url, checked_by)
                               select id, %s, %s, %s, kb.actor_id() from kb.resources where id = %s
                               on conflict (resource_id) do update set status = excluded.status,
                                   http_status = excluded.http_status, final_url = excluded.final_url,
                                   checked_at = now(), checked_by = excluded.checked_by""",
                            (status, http, final, rid))
                saved += cur.rowcount
    return {"saved": saved}


def people(conn) -> list[dict]:
    """Members (id, email, role) for showing owners by name. Viewer+."""
    require(conn, "viewer", "listing people")
    return _q(conn, "select user_id, email, role from kb.people()")


def resources_for_link_check(conn, limit: int = 50, offset: int = 0) -> list[dict]:
    return _q(conn, "select id, url, title from kb.resources where archived_at is null "
                    "order by updated_at desc limit %s offset %s", (min(int(limit), 50), max(int(offset), 0)))


__all__ = [n for n in dir() if not n.startswith("_")] + ["KbError"]
