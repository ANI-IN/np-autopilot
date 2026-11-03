"""Activity log (run 3, B4) and the collaboration change feed.

Every entry comes from kb.audit_log, written only by the kb.audit() trigger and
append-only (0029). Who may read which rows is decided by the database: the
audit_log_select policy (admin: all; editor: their own actions and their
scope) and kb.record_history() for a single record's History tab. Nothing here
widens that; filters only narrow it.

Each entry carries a named actor (owner bug A2): a person, the AI assistant
acting for a named person, an import (Sheets or the projection), or the system. "Someone" never
appears.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from . import validate as v
from .errors import Invalid

SOURCES = {"app": ("human",), "ai": ("ai",), "import": ("import",), "sync": ("sync",), "system": ("system",)}
ACTIONS = ("insert", "update", "delete")
TABLES = ("nodes", "edges", "resources", "node_resources", "node_tags", "node_types", "edge_types",
          "edge_type_rules", "link_kinds", "proposals", "flags", "templates", "saved_views", "memberships",
          "api_tokens", "import_runs", "tags")
# Columns that change on every write and say nothing to a reader.
NOISE = {"version", "updated_at", "updated_by", "search", "name_norm"}


def _q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _person(email: str | None) -> str | None:
    if not email:
        return None
    return " ".join(w.capitalize() for w in email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ").split())


def label_actors(conn, rows: list[dict]) -> list[dict]:
    ids = list({str(r["actor_id"]) for r in rows if r.get("actor_id")})
    names = {}
    if ids:
        names = {str(x["user_id"]): x["email"] for x in _q(conn, "select user_id, email from kb.actor_emails(%s::uuid[])", (ids,))}
    for r in rows:
        email = names.get(str(r.get("actor_id"))) if r.get("actor_id") else None
        person = _person(email) or ("A former member" if r.get("actor_id") else None)
        t = r.get("actor_type")
        if t == "ai":
            r["actor_label"] = "AI assistant" + (f" (for {person})" if person else "")
        elif t == "import":
            r["actor_label"] = "Import" + (f" (run by {person})" if person else "")
        elif t == "sync":
            # the scheduled sync from the original site; "Sync now" names who started it
            r["actor_label"] = "Sync" + (f" (started by {person})" if person else "")
        elif t == "system" or not r.get("actor_id"):
            r["actor_label"] = "System"
        else:
            r["actor_label"] = person
        r["actor_email"] = email
        r["source"] = {"human": "app", "ai": "ai", "import": "import", "sync": "sync"}.get(t, "system")
    return rows


def diff(before: dict | None, after: dict | None) -> list[dict]:
    """Field-by-field before -> after for an update (props flattened)."""
    if not before or not after:
        return []
    out = []
    keys = sorted(set(before) | set(after))
    for k in keys:
        if k in NOISE:
            continue
        a, b = before.get(k), after.get(k)
        if k == "props" and isinstance(a, dict) and isinstance(b, dict):
            for pk in sorted(set(a) | set(b)):
                if a.get(pk) != b.get(pk):
                    out.append({"field": "props." + pk, "before": a.get(pk), "after": b.get(pk)})
        elif a != b:
            out.append({"field": k, "before": a, "after": b})
    return out


def _shape(rows: list[dict]) -> list[dict]:
    for r in rows:
        b, a = r.get("before"), r.get("after")
        src = a or b or {}
        r["label"] = src.get("name") or src.get("title") or src.get("label") or src.get("email")
        r["changes"] = diff(b, a) if r["action"] == "update" else []
    return rows


def name_links(conn, rows: list[dict]) -> list[dict]:
    """A link attached to (or detached from) a record, and a tag on a record,
    read as "“Deck” on “Week 1”" instead of an anonymous row. One query each
    for the records and the links involved, whatever the page size."""
    nids, rids, tids = set(), set(), set()
    for r in rows:
        if r["table_name"] in ("node_resources", "node_tags"):
            src = r.get("after") or r.get("before") or {}
            if src.get("node_id"):
                nids.add(src["node_id"])
            if src.get("resource_id"):
                rids.add(src["resource_id"])
            if src.get("tag_id"):
                tids.add(src["tag_id"])
    if not (nids or rids or tids):
        return rows
    names = {}
    if nids:
        names.update({str(x["id"]): x["name"] for x in _q(conn, "select id, name from kb.nodes where id = any(%s::uuid[])", (list(nids),))})
    if rids:
        names.update({str(x["id"]): x["title"] for x in _q(conn, "select id, title from kb.resources where id = any(%s::uuid[])", (list(rids),))})
    if tids:
        names.update({str(x["id"]): "#" + x["name"] for x in _q(conn, "select id, name from kb.tags where id = any(%s::uuid[])", (list(tids),))})
    for r in rows:
        if r["table_name"] in ("node_resources", "node_tags"):
            src = r.get("after") or r.get("before") or {}
            what = names.get(str(src.get("resource_id") or src.get("tag_id") or ""))
            on = names.get(str(src.get("node_id") or ""))
            if what or on:
                r["label"] = f"{what or 'a link'} on {on or 'a record'}"
    return rows


def history(conn, row_id: str, limit: int = 50) -> list[dict]:
    rows = _q(conn, """select id, at, actor_id, actor_type, table_name, row_id, action, before, after
                       from kb.record_history(%s, %s)""",
              (v.uid(row_id, "id"), max(1, min(int(limit), 200))))
    return label_actors(conn, name_links(conn, _shape(rows)))


def changes(conn, since: int | None, limit: int = 200) -> dict:
    """The change feed clients poll for collaboration (M7). Cursor = audit id.
    Reads kb.changes (no row content), so every member may follow it."""
    if since is None:
        last = _q(conn, "select coalesce(max(id), 0) as m from kb.changes")
        return {"cursor": last[0]["m"], "changes": []}
    rows = _q(conn, """select id, at, actor_id, actor_type, table_name, row_id, action, version, kind, node_ids
                       from kb.changes where id > %s order by id limit %s""",
              (int(since), max(1, min(int(limit), 500))))
    return {"cursor": rows[-1]["id"] if rows else int(since), "changes": rows}


def recent(conn, limit: int = 20) -> list[dict]:
    rows = _q(conn, """select a.id, a.at, a.actor_id, a.actor_type, a.table_name, a.row_id, a.action,
                              coalesce(a.after ->> 'name', a.before ->> 'name', a.after ->> 'title',
                                       a.before ->> 'title') as label,
                              exists (select 1 from kb.nodes n where n.id = a.row_id) or
                              exists (select 1 from kb.resources r where r.id = a.row_id) as exists_now
                       from kb.audit_log a where a.table_name in ('nodes', 'edges', 'resources')
                       order by a.id desc limit %s""", (limit,))
    return label_actors(conn, rows)


def _ts(val, name):
    if val in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"{name} must be an ISO date or time", field=name) from None


def activity(conn, params: dict) -> dict:
    """The Activity page. Filters narrow what RLS already allows; cursor = the
    last id seen (newest first)."""
    where, args = [], []
    if params.get("actor"):
        where.append("a.actor_id = %s"); args.append(v.uid(params["actor"], "actor"))
    if params.get("action"):
        acts = [x for x in str(params["action"]).split(",") if x]
        if any(x not in ACTIONS for x in acts):
            raise Invalid("action must be insert, update or delete", field="action")
        where.append("a.action = any(%s)"); args.append(acts)
    if params.get("table"):
        tabs = [x for x in str(params["table"]).split(",") if x]
        if any(x not in TABLES for x in tabs):
            raise Invalid("unknown entity type", field="table")
        where.append("a.table_name = any(%s)"); args.append(tabs)
    if params.get("source"):
        srcs = [x for x in str(params["source"]).split(",") if x]
        if any(x not in SOURCES for x in srcs):
            raise Invalid("source must be app, ai, import or system", field="source")
        where.append("a.actor_type = any(%s)"); args.append([t for s in srcs for t in SOURCES[s]])
    if params.get("record"):
        rid = v.uid(params["record"], "record")
        where.append("""(a.row_id = %s or (a.table_name = 'edges' and %s::text in (coalesce(a.after, a.before) ->> 'source_id',
                         coalesce(a.after, a.before) ->> 'target_id'))
                         or (a.table_name in ('node_resources', 'node_tags') and %s::text in
                         (coalesce(a.after, a.before) ->> 'node_id', coalesce(a.after, a.before) ->> 'resource_id')))""")
        args += [rid, rid, rid]
    if (f := _ts(params.get("from"), "from")):
        where.append("a.at >= %s"); args.append(f)
    if (t := _ts(params.get("to"), "to")):
        where.append("a.at <= %s"); args.append(t)
    if params.get("q"):
        where.append("(coalesce(a.after, a.before)::text ilike %s)"); args.append("%" + str(params["q"])[:100] + "%")
    if params.get("cursor"):
        try:
            where.append("a.id < %s"); args.append(int(params["cursor"]))
        except ValueError:
            raise Invalid("cursor must be a number", field="cursor") from None
    limit = max(1, min(int(params.get("limit") or 50), 5000 if params.get("format") == "csv" else 200))
    rows = _q(conn, f"""select a.id, a.at, a.actor_id, a.actor_type, a.table_name, a.row_id, a.action, a.before, a.after,
                               case when a.table_name = 'nodes' then exists (select 1 from kb.nodes n where n.id = a.row_id)
                                    when a.table_name = 'resources' then exists (select 1 from kb.resources r where r.id = a.row_id)
                                    else null end as exists_now
                        from kb.audit_log a {('where ' + ' and '.join(where)) if where else ''}
                        order by a.id desc limit %s""", (*args, limit + 1))
    more = len(rows) > limit
    rows = label_actors(conn, name_links(conn, _shape(rows[:limit])))
    return {"items": rows, "next_cursor": rows[-1]["id"] if more and rows else None}


def _cell(x) -> str:
    """Spreadsheet-safe: a cell starting with = + - @ is not run as a formula."""
    s = "" if x is None else str(x)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def activity_csv(conn, params: dict) -> str:
    items = activity(conn, {**params, "format": "csv", "limit": params.get("limit") or 5000})["items"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "at", "actor", "source", "action", "entity_type", "entity_id", "entity", "changes"])
    for r in items:
        ch = "; ".join(f"{c['field']}: {c['before']!r} -> {c['after']!r}" for c in r["changes"])
        w.writerow([_cell(x) for x in (r["id"], r["at"].isoformat(), r["actor_label"], r["source"], r["action"],
                                        r["table_name"], r["row_id"], r["label"], ch)])
    return buf.getvalue()
