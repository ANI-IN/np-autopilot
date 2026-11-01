"""/api/kb/* — the KB workspace's HTTP surface. A thin adapter over
web/lib/kb/service.py: parse, call, shape. No SQL, no permission logic here.

It never opens a connection. api/index.py identifies the caller FIRST, opens a
connection scoped to them, and hands it in — the same single front door every
other route uses (tests/test_login_flow.py, tests/test_lazy_route_table.py).

Routes (method, path after /api/kb):
  GET    /me | /types | /dashboard | /tags | /search?q= | /changes?since=
  GET    /nodes?type=&scope=&q=&status=&tag=&owner=&sort=&cursor=&limit=
  POST   /nodes                         create (inline scope/resources/edges)
  GET    /nodes/{id}                    detail: relationships, resources, tags
  PATCH  /nodes/{id}[?force=1]          update; needs `version`; 409 on conflict
  GET    /nodes/{id}/impact | /history | /neighbourhood?depth=&types=
  POST   /nodes/{id}/archive | /restore | /duplicate | /resources | /tags
  DELETE /nodes/{id}/tags/{tag}         untag
  DELETE /nodes/{id}                    hard delete (admin, archived only)
  (same shape for /edges, /resources; /courses and /programs are /nodes with
   the type fixed)
  POST   /attachments/{id}/detach
  GET    /proposals   POST /proposals/{id}/approve | /reject
  GET    /tokens      POST /tokens      POST /tokens/{id}/revoke
  GET    /members     POST /members/{user_id}   (admin)
  GET    /instructors?course=&q=   /nodes/{id}/validate
  GET    /quality/missing-resources | /quality/duplicates | /quality/link-candidates

Authorization: a Supabase session token (browser), or a per-user KB API token
(`ikkb_…`, MCP clients) which api/index.py resolves to its owner; token callers
are attributed as actor_type 'ai', so their archive/delete requests become
proposals.
  POST   /types/node  POST /types/rule          (admin)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

from lib.kb import service as svc                                      # noqa: E402
from lib.kb.errors import KbError, NotFound, Invalid                    # noqa: E402

TYPED = {"courses": "course", "programs": "program"}


def handle(conn, actor: svc.Actor, method: str, parts: list[str], params: dict,
           body: dict | None) -> tuple[int, dict]:
    """Returns (status, payload). Raises KbError for the caller to translate."""
    svc.begin(conn, actor)
    body = body or {}
    head = parts[0] if parts else ""
    rest = parts[1:]
    force = params.get("force") in ("1", "true")

    if head == "me" and method == "GET":
        return 200, svc.me(conn)
    if head == "types":
        if method == "GET" and not rest:
            return 200, {"node_types": svc.node_types(conn), "edge_types": svc.edge_types(conn)}
        if method == "POST" and rest == ["node"]:
            return 201, svc.create_node_type(conn, actor, body)
        if method == "POST" and rest == ["rule"]:
            return 201, svc.add_edge_rule(conn, actor, body)
    if head == "dashboard" and method == "GET":
        return 200, svc.dashboard(conn)
    if head == "tags" and method == "GET":
        return 200, {"items": svc.list_tags(conn)}
    if head == "search" and method == "GET":
        types = params.get("types")
        return 200, svc.search(conn, params.get("q", ""),
                               types=str(types).split(",") if types else None,
                               limit=_int(params.get("limit"), 20))
    if head == "changes" and method == "GET":
        since = params.get("since")
        return 200, svc.changes(conn, _int(since, None) if since not in (None, "") else None)

    if head == "quality" and method == "GET" and not rest:
        return 200, svc.quality_overview(conn)
    if head == "quality" and method == "GET" and rest == ["missing-resources"]:
        return 200, {"items": svc.find_missing_resources(conn, params.get("type"), _int(params.get("limit"), 100))}
    if head == "quality" and method == "GET" and rest == ["duplicates"]:
        return 200, {"items": svc.find_duplicate_nodes(conn, float(params.get("threshold", 0.6)),
                                                       _int(params.get("limit"), 50))}
    if head == "quality" and method == "GET" and rest == ["link-candidates"]:
        return 200, {"items": svc.resources_for_link_check(conn, _int(params.get("limit"), 50),
                                                           _int(params.get("offset"), 0))}
    if head == "instructors" and method == "GET" and not rest:
        return 200, {"items": svc.find_instructors(conn, course_id=params.get("course"), q=params.get("q"),
                                                   limit=_int(params.get("limit"), 50))}

    if head in ("nodes", "courses", "programs"):
        return _nodes(conn, actor, method, rest, params, body, force, TYPED.get(head))
    if head == "edges":
        return _edges(conn, actor, method, rest, params, body)
    if head == "resources":
        return _resources(conn, actor, method, rest, params, body, force)
    if head == "attachments" and method == "POST" and len(rest) == 2 and rest[1] == "detach":
        return 200, svc.detach_resource(conn, actor, rest[0])
    if head == "proposals":
        if method == "GET" and not rest:
            return 200, {"items": svc.list_proposals(conn, params.get("status", "pending"))}
        if method == "POST" and len(rest) == 2 and rest[1] in ("approve", "reject"):
            return 200, svc.decide_proposal(conn, actor, rest[0], rest[1] == "approve")
    if head == "tokens":
        if method == "GET" and not rest:
            return 200, {"items": svc.list_tokens(conn)}
        if method == "POST" and not rest:
            return 201, svc.create_token(conn, actor, body)
        if method == "POST" and len(rest) == 2 and rest[1] == "revoke":
            return 200, svc.revoke_token(conn, actor, rest[0])
    if head == "members":
        if method == "GET" and not rest:
            return 200, {"items": svc.list_members(conn)}
        if method == "POST" and len(rest) == 1:
            return 200, svc.set_role(conn, actor, rest[0], body.get("role"))
    raise NotFound(f"no KB route {method} /api/kb/{'/'.join(parts)}")


def _int(raw, default):
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise Invalid(f"expected a number, got {raw!r}") from None


def _nodes(conn, actor, method, rest, params, body, force, fixed_type):
    if not rest:
        if method == "GET":
            if fixed_type:
                params = {**params, "type": fixed_type}
            return 200, svc.list_nodes(conn, params)
        if method == "POST":
            if fixed_type:
                body = {**body, "type": fixed_type}
            return 201, svc.create_node(conn, actor, body)
    nid = rest[0] if rest else None
    sub = rest[1:] if rest else []
    if not sub:
        if method == "GET":
            node = svc.get_node(conn, nid)
            if fixed_type and node["type"] != fixed_type:
                raise NotFound(f"no {fixed_type} with id {nid}")
            return 200, node
        if method == "PATCH":
            return 200, svc.update_node(conn, actor, nid, body, force=force)
        if method == "DELETE":
            return 200, svc.hard_delete(conn, actor, "nodes", nid)
    action = sub[0]
    if method == "GET" and action == "validate":
        return 200, svc.validate_course_structure(conn, nid)
    if method == "GET" and action == "impact":
        return 200, svc.archive_impact(conn, nid)
    if method == "GET" and action == "history":
        return 200, {"items": svc.history(conn, nid)}
    if method == "GET" and action == "neighbourhood":
        types = params.get("types")
        return 200, svc.neighbourhood(conn, nid, params.get("depth", 1),
                                      types=str(types).split(",") if types else None)
    if method == "POST" and action == "archive":
        return 200, svc.archive_node(conn, actor, nid, body)
    if method == "POST" and action == "restore":
        return 200, svc.restore_node(conn, actor, nid)
    if method == "POST" and action == "duplicate":
        return 201, svc.duplicate_node(conn, actor, nid)
    if method == "POST" and action == "resources":
        return 201, svc.attach_resource(conn, actor, nid, body)
    if method == "POST" and action == "tags":
        return 201, svc.tag_node(conn, actor, nid, body)
    if method == "DELETE" and action == "tags" and len(sub) == 2:
        return 200, svc.untag_node(conn, actor, nid, sub[1])
    raise NotFound(f"no KB route {method} {action}")


def _edges(conn, actor, method, rest, params, body):
    if not rest:
        if method == "GET":
            return 200, svc.list_edges(conn, params)
        if method == "POST":
            return 201, svc.create_edge(conn, actor, body)
    eid, sub = rest[0], rest[1:]
    if not sub:
        if method == "GET":
            return 200, svc.get_edge(conn, eid)
        if method == "PATCH":
            return 200, svc.update_edge(conn, actor, eid, body)
        if method == "DELETE":
            return 200, svc.hard_delete(conn, actor, "edges", eid)
    if method == "POST" and sub == ["archive"]:
        return 200, svc.archive_edge(conn, actor, eid, body)
    if method == "POST" and sub == ["restore"]:
        return 200, svc.restore_edge(conn, actor, eid)
    if method == "GET" and sub == ["history"]:
        return 200, {"items": svc.history(conn, eid)}
    raise NotFound("no such relationship route")


def _resources(conn, actor, method, rest, params, body, force):
    if not rest:
        if method == "GET":
            return 200, svc.list_resources(conn, params)
        if method == "POST":
            return 201, svc.create_resource(conn, actor, body)
    rid, sub = rest[0], rest[1:]
    if not sub:
        if method == "GET":
            return 200, svc.get_resource(conn, rid)
        if method == "PATCH":
            return 200, svc.update_resource(conn, actor, rid, body, force=force)
        if method == "DELETE":
            return 200, svc.hard_delete(conn, actor, "resources", rid)
    if method == "POST" and sub == ["archive"]:
        return 200, svc.archive_resource(conn, actor, rid, body)
    if method == "POST" and sub == ["restore"]:
        return 200, svc.restore_resource(conn, actor, rid)
    if method == "GET" and sub == ["history"]:
        return 200, {"items": svc.history(conn, rid)}
    raise NotFound("no such resource route")


__all__ = ["handle", "KbError"]
