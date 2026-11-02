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
  POST   /quality/link-results   (editor; records a link checker's results)
  GET    /people   (members' ids + emails, for owner names)
  GET    /types   POST /types/node|edge|link   PATCH /types/{node|edge|link}/{key}
  POST   /types/node/{key}/archive|restore|duplicate|change-type   /types/{edge|link}/{key}/archive
         (admin applies; an editor's call becomes a type_change proposal, 202)
  GET    /nodes/check-name?type=&name=&scope=    POST /nodes/bulk | /nodes/bulk-archive
  GET    /nodes/{id}/completeness | /delete-impact      GET /archived?kind=records|resources|relationships
  GET    /outline?root=   POST /outline/reorder
  GET    /flags?status=   POST /flags   POST /flags/{id}/resolve|dismiss
  GET    /templates   POST /templates   POST /templates/{id}/instantiate|archive
  GET    /views   POST /views   PATCH|DELETE /views/{id}
  PATCH  /attachments/{id}   (purpose note)

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

from lib.kb import activity as act                                    # noqa: E402
from lib.kb import service as svc                                      # noqa: E402
from lib.kb import typedefs as td                                      # noqa: E402
from lib.kb import workspace as ws                                     # noqa: E402
from lib.kb.errors import KbError, NotFound, Invalid                    # noqa: E402

TYPED = {"courses": "course", "programs": "program"}


# Short-lived read cache (run 3, Phase C) for the heaviest reads every page
# makes: the dashboard, the sidebar counts and the type configuration. Keyed by
# the caller (RLS scopes what each person sees), the role, and the newest
# change-feed id, so ANY audited write invalidates it at once; the TTL bounds
# staleness for what the feed does not carry (link-check results).
_CACHE: dict = {}
CACHE_TTL = 15.0


def _cached(conn, actor, name: str, fn):
    import time as _t
    head_id = svc._q1(conn, "select coalesce(max(id), 0) as m from kb.changes")["m"]
    key = (name, str(actor.user_id), actor.actor_type, svc.role(conn), head_id)
    hit = _CACHE.get(key)
    now = _t.monotonic()
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[key] = (now, val)
    return val


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
        return _types(conn, actor, method, rest, params, body)
    if head == "nodes" and rest == ["check-name"] and method == "GET":
        return 200, svc.check_name(conn, params)
    if head == "nodes" and rest == ["bulk"] and method == "POST":
        return 200, ws.bulk_update(conn, actor, body)
    if head == "nodes" and rest == ["bulk-archive"] and method == "POST":
        return 200, ws.bulk_archive(conn, actor, body)
    if head == "nodes" and len(rest) == 2 and rest[1] == "completeness" and method == "GET":
        return 200, ws.completeness(conn, rest[0])
    if head in ("nodes", "resources") and len(rest) == 2 and rest[1] == "delete-impact" and method == "GET":
        return 200, ws.delete_impact(conn, head, rest[0])
    if head == "resources" and len(rest) == 2 and rest[1] == "completeness" and method == "GET":
        return 200, ws.resource_completeness(conn, rest[0])
    if head == "archived" and method == "GET":
        return 200, ws.archived(conn, params)
    if head == "outline":
        if method == "GET" and not rest:
            return 200, ws.outline(conn, params)
        if method == "POST" and rest == ["reorder"]:
            return 200, ws.reorder(conn, actor, body)
    if head == "flags":
        if method == "GET" and not rest:
            return 200, {"items": ws.list_flags(conn, params)}
        if method == "POST" and not rest:
            return 201, ws.create_flag(conn, actor, body)
        if method == "POST" and len(rest) == 2 and rest[1] in ("resolve", "dismiss"):
            return 200, ws.resolve_flag(conn, actor, rest[0], body,
                                        "resolved" if rest[1] == "resolve" else "dismissed")
    if head == "templates":
        if method == "GET" and not rest:
            return 200, {"items": ws.list_templates(conn)}
        if method == "POST" and not rest:
            return 201, ws.create_template(conn, actor, body)
        if method == "POST" and len(rest) == 2 and rest[1] == "instantiate":
            return 201, ws.instantiate_template(conn, actor, rest[0], body)
        if method == "POST" and len(rest) == 2 and rest[1] == "archive":
            return 200, ws.archive_template(conn, actor, rest[0])
        if method == "POST" and len(rest) == 2 and rest[1] == "restore":
            return 200, ws.restore_template(conn, actor, rest[0])
        if method == "PATCH" and len(rest) == 1:
            return 200, ws.rename_template(conn, actor, rest[0], body)
    if head == "views":
        if method == "GET" and not rest:
            return 200, {"items": ws.list_views(conn)}
        if method == "POST" and not rest:
            return 201, ws.save_view(conn, actor, body)
        if method == "PATCH" and len(rest) == 1:
            return 200, ws.save_view(conn, actor, body, rest[0])
        if method == "DELETE" and len(rest) == 1:
            return 200, ws.delete_view(conn, actor, rest[0])
    if head == "realtime" and method == "GET" and not rest:
        return 200, _realtime_config()
    if head == "attachments" and method == "PATCH" and len(rest) == 1:
        return 200, svc.update_attachment(conn, actor, rest[0], body)
    if head == "dashboard" and method == "GET":
        def _dash():
            out = svc.dashboard(conn)
            out["attention"] = ws.needs_attention(conn)
            out["completeness"] = ws.course_completeness(conn)
            return out
        return 200, _cached(conn, actor, "dashboard", _dash)
    if head == "counts" and method == "GET":
        # Sidebar counts: the same totals and attention numbers as the dashboard, without the lists.
        return 200, _cached(conn, actor, "counts", lambda: {**svc.dashboard_totals(conn), "attention": ws.attention_counts(conn)})
    if head == "tags" and method == "GET" and not rest:
        return 200, {"items": svc.list_tags(conn)}
    if head == "tags" and len(rest) >= 1:
        if method == "PATCH" and len(rest) == 1:
            return 200, ws.update_tag(conn, actor, rest[0], body)
        if method == "GET" and rest[1:] == ["impact"]:
            return 200, ws.tag_impact(conn, rest[0])
        if method == "POST" and rest[1:] == ["merge"]:
            return 200, ws.merge_tag(conn, actor, rest[0], body)
        if method == "POST" and rest[1:] == ["archive"]:
            return 200, ws.archive_tag(conn, actor, rest[0])
        if method == "POST" and rest[1:] == ["restore"]:
            return 200, ws.restore_tag(conn, actor, rest[0], body)
    if head == "search" and method == "GET":
        types = params.get("types")
        return 200, svc.search(conn, params.get("q", ""),
                               types=str(types).split(",") if types else None,
                               limit=_int(params.get("limit"), 20))
    if head == "graph" and rest == ["positions"]:
        if method == "GET":
            return 200, ws.graph_positions(conn, params)
        if method in ("PUT", "POST"):
            return 200, ws.save_graph_positions(conn, actor, body)
        if method == "DELETE":
            return 200, ws.reset_graph_positions(conn, actor, params)
    if head == "activity" and method == "GET" and not rest:
        if params.get("format") == "csv":
            return 200, {"filename": "activity.csv", "csv": act.activity_csv(conn, params)}
        return 200, act.activity(conn, params)
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
    if head == "quality" and method == "POST" and rest == ["link-results"]:
        return 200, svc.record_link_results(conn, actor, (body or {}).get("results"))
    if head == "people" and method == "GET" and not rest:
        return 200, {"items": svc.people(conn)}
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
            return 200, svc.decide_proposal(conn, actor, rest[0], rest[1] == "approve",
                                            {k: body[k] for k in ("label", "inverse_label", "merge_into") if k in (body or {})} or None)
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
        if method == "POST" and len(rest) == 2 and rest[1] == "remove":
            return 200, ws.remove_member(conn, actor, rest[0])
    raise NotFound(f"no KB route {method} /api/kb/{'/'.join(parts)}")


def _realtime_config() -> dict:
    """Supabase Realtime for live updates (D2), ONLY when the deployment names
    the origin it also allows in the security policy's connect-src
    (KB_REALTIME_ORIGIN, e.g. https://<ref>.supabase.co). Otherwise {} and the
    browser keeps polling /changes. The anon key is public by design (it is the
    key a browser holds) and grants nothing without a session: Realtime applies
    the caller's RLS to every change it forwards."""
    import os
    origin = os.environ.get("KB_REALTIME_ORIGIN", "").rstrip("/")
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not (origin and url and key and url == origin):
        return {}
    return {"url": url, "key": key}


def _types(conn, actor, method, rest, params, body):
    if method == "GET" and not rest:
        arch = params.get("archived") in ("1", "true")
        return 200, _cached(conn, actor, "types" + ("+archived" if arch else ""), lambda: td.all_types(conn, include_archived=arch))
    if method == "POST" and rest == ["rule"]:
        return 201, svc.add_edge_rule(conn, actor, body)
    if method == "GET" and rest == ["edge-similar"]:
        return 200, {"existing": td.similar_edge_type(conn, params.get("label"), params.get("inverse_label"))}
    kinds = {"node": (td.create_node_type, td.update_node_type),
             "edge": (td.create_edge_type, td.update_edge_type),
             "link": (td.create_link_kind, td.update_link_kind)}
    if rest and rest[0] in kinds:
        create, update = kinds[rest[0]]
        if method == "POST" and len(rest) == 1:
            return 201, create(conn, actor, body)
        if method == "PATCH" and len(rest) == 2:
            return 200, update(conn, actor, rest[1], body)
        if method == "POST" and len(rest) == 3:
            key, act = rest[1], rest[2]
            ops = {("node", "archive"): lambda: td.archive_node_type(conn, actor, key),
                   ("node", "restore"): lambda: td.restore_node_type(conn, actor, key),
                   ("node", "duplicate"): lambda: td.duplicate_node_type(conn, actor, key),
                   ("node", "change-type"): lambda: td.change_records_type(conn, actor, key, body),
                   ("edge", "archive"): lambda: td.archive_edge_type(conn, actor, key),
                   ("edge", "merge"): lambda: td.merge_edge_type(conn, actor, key, body),
                   ("link", "archive"): lambda: td.archive_link_kind(conn, actor, key)}
            fn = ops.get((rest[0], act))
            if fn:
                return 200, fn()
    raise NotFound(f"no KB route {method} /types/{'/'.join(rest)}")


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
        return 200, svc.neighbourhood(conn, nid, params.get("depth", 1), limit=_int(params.get("limit"), svc.MAX_NEIGHBOURHOOD),
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
    if method == "POST" and sub == ["retype"]:
        return 201, ws.retype_edge(conn, actor, eid, body)
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
