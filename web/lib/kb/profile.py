"""One entity profile for every panel (run C, 2026-11-07).

The Graph editor, the Map, the Admin pages and the record page all render the
SAME component from the SAME data: this profile. It is computed from the
relationships, never stored, so it cannot drift from the graph.

Sections (only the ones a record has are returned non-empty):
  domains     in_domain targets (display names only; hidden aliases are never selected)
  owners      owned_by -> NP team members (many-to-many)
  owns        for a team member: what they own
  smes        for a module: SME assignments, Primary first, then Backup 1-3, then other named roles
  sme_of      for an instructor: the modules they are an SME for, with the role
  used_in     for a module: the courses that contain it and the programs those courses belong to,
              with the program-specific schedule kept on the link (week labels are program data only)
  courses     for a program: its courses in order, with module counts
  modules     for a program or course: its modules in order (schedule from the link, if any)
  topics      for a module: its topics in order (curriculum), then topics found in its content
  concepts    tools / technologies
  variants    canonical module and its variants
  listed_instructors / teaches   program-level instructor listings from the KYPs
  sources     where the record comes from: live source links with version and location (provenance)
"""
from __future__ import annotations

from typing import Any

from pipeline.lib import taxonomy as _tax

#: The KB relationship for owners: the same key as the projection's owner relation.
OWNED_BY = _tax.edge_for_role("domain_primary")


def _rows(conn, sql: str, params=()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


_EDGES = """
    select e.id as edge_id, e.version as edge_version, e.props, e.position, et.key as rel,
           o.id, o.name, o.external_id, ot.key as type, ot.label as type_label
    from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
    join kb.nodes o on o.id = e.{other} join kb.node_types ot on ot.id = o.type_id
    where e.{me} = %s and e.archived_at is null and o.archived_at is null and et.key = any(%s)
    order by e.position nulls last, o.name_norm limit 500"""


def _out(conn, nid, rels):
    return _rows(conn, _EDGES.format(other="target_id", me="source_id"), (nid, list(rels)))


def _in(conn, nid, rels):
    return _rows(conn, _EDGES.format(other="source_id", me="target_id"), (nid, list(rels)))


def sme_label(props: dict | None) -> tuple[int, str]:
    """(sort key, display label): Primary, Backup 1..3, then other named roles."""
    p = props or {}
    role = (p.get("role") or "").strip()
    if role == "primary":
        return 0, "Primary"
    if role == "backup":
        r = p.get("rank")
        return 10 + int(r or 9), f"Backup {r}" if r else "Backup"
    return 50, role[:1].upper() + role[1:] if role else "SME"


def _schedule(props: dict | None) -> dict | None:
    s = (props or {}).get("schedule")
    if not s:
        return None
    rows = s.get("rows") if isinstance(s, dict) else None
    labels = [r.get("label") for r in (rows or []) if isinstance(r, dict) and r.get("label")]
    return {"program": s.get("program"), "labels": labels} if (labels or s.get("program")) else None


def _brief(r: dict, **extra) -> dict:
    ext = r.get("external_id") or ""
    # ref = the id the Map uses for this record (the NP id the sync kept, or the uuid)
    ref = ext[3:] if ext.startswith("np:") and not ext.startswith("np:url:") else str(r["id"])
    out = {"id": str(r["id"]), "name": r["name"], "type": r["type"], "ref": ref}
    out.update({k: v for k, v in extra.items() if v not in (None, [], {})})
    return out


def sources(props: dict | None) -> list[dict]:
    seen, out = set(), []
    for p in (props or {}).get("provenance") or []:
        if not isinstance(p, dict):
            continue
        k = (p.get("page_id") or p.get("url"), p.get("heading"), p.get("row"))
        if k in seen:
            continue
        seen.add(k)
        out.append({k2: p.get(k2) for k2 in ("source", "page_title", "url", "page_version", "page_modified",
                                               "heading", "table", "row") if p.get(k2) is not None})
    return out[:30]


def entity_profile(conn, node: dict) -> dict[str, Any]:
    nid, t = str(node["id"]), node["type"]
    prof: dict[str, Any] = {}
    prof["domains"] = [_brief(r) for r in _out(conn, nid, ["in_domain"])]
    if t in ("program", "course", "module"):
        prof["owners"] = [_brief(r, edge_id=str(r["edge_id"]), edge_version=r["edge_version"])
                          for r in _out(conn, nid, [OWNED_BY]) if r["type"] == "team_member"]
    if t == "team_member":
        prof["owns"] = [_brief(r) for r in _in(conn, nid, [OWNED_BY])]
    if t == "module":
        smes = []
        for r in _in(conn, nid, ["sme"]):
            key, label = sme_label(r["props"])
            smes.append(_brief(r, role=(r["props"] or {}).get("role"), rank=(r["props"] or {}).get("rank"), label=label,
                               edge_id=str(r["edge_id"]), edge_version=r["edge_version"], _k=key))
        smes.sort(key=lambda x: (x["_k"], x["name"].lower()))
        for s in smes:
            s.pop("_k", None)
        prof["smes"] = smes
        # where it is used: courses (and their programs), and programs that hold it directly
        used = []
        for c in _in(conn, nid, ["contains"]):
            if c["type"] == "course":
                progs = [_brief(p) for p in _in(conn, str(c["id"]), ["contains"]) if p["type"] == "program"]
                used.append(_brief(c, programs=progs, schedule=_schedule(c["props"])))
            elif c["type"] == "program":
                used.append(_brief(c, schedule=_schedule(c["props"])))
        prof["used_in"] = used
        prof["topics"] = [_brief(r) for r in _out(conn, nid, ["contains"]) if r["type"] == "topic"]
        prof["content_topics"] = [_brief(r) for r in _out(conn, nid, ["covers"]) if r["type"] == "topic"][:200]
        prof["concepts"] = [_brief(r) for r in _out(conn, nid, ["covers"]) if r["type"] == "concept"]
        canon = _out(conn, nid, ["variant_of"])
        prof["variant_of"] = [_brief(r) for r in canon]
        prof["variants"] = [_brief(r) for r in _in(conn, nid, ["variant_of"])]
        prof["sessions"] = [_brief(r) for r in _out(conn, nid, ["contains"]) if r["type"] == "session"]
    if t == "instructor":
        prof["sme_of"] = sorted(
            (_brief(r, label=sme_label(r["props"])[1], role=(r["props"] or {}).get("role")) for r in _out(conn, nid, ["sme"])),
            key=lambda x: x["name"].lower())
        prof["teaches"] = [_brief(r, role=(r["props"] or {}).get("role")) for r in _out(conn, nid, ["teaches"])]
    if t == "program":
        kids = _out(conn, nid, ["contains"])
        courses = []
        for c in [k for k in kids if k["type"] == "course"]:
            n = _rows(conn, """select count(*) as n from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                               join kb.nodes m on m.id = e.target_id join kb.node_types mt on mt.id = m.type_id and mt.key = 'module'
                               where e.source_id = %s and e.archived_at is null and m.archived_at is null""", (str(c["id"]),))[0]["n"]
            courses.append(_brief(c, modules=n, schedule=_schedule(c["props"])))
        prof["courses"] = courses
        prof["modules"] = [_brief(k, schedule=_schedule(k["props"])) for k in kids if k["type"] == "module"]
        prof["listed_instructors"] = [_brief(r) for r in _in(conn, nid, ["teaches"]) if r["type"] == "instructor"]
    if t == "course":
        prof["modules"] = [_brief(k, schedule=_schedule(k["props"])) for k in _out(conn, nid, ["contains"]) if k["type"] == "module"]
        prof["programs"] = [_brief(p) for p in _in(conn, nid, ["contains"]) if p["type"] == "program"]
    if t == "topic":
        prof["modules"] = [_brief(m) for m in _in(conn, nid, ["contains", "covers"]) if m["type"] == "module"]
        prof["concepts"] = [_brief(r) for r in _out(conn, nid, ["covers"]) if r["type"] == "concept"]
    if t == "domain":
        members = _in(conn, nid, ["in_domain"])
        prof["programs"] = [_brief(r) for r in members if r["type"] == "program"]
        prof["courses"] = [_brief(r) for r in members if r["type"] == "course"]
        prof["modules"] = [_brief(r) for r in members if r["type"] == "module"]
    prof["sources"] = sources(node.get("props"))
    return {k: v for k, v in prof.items() if v not in (None, [], {})}
