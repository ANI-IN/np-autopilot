"""Two read-only views over the KB (run 5, Part 5). They read through the
caller's connection, so RLS decides what is visible.

  teaching_matrix   "Who teaches what": instructors x modules (and the
                    sessions they teach), each cell the role from the current
                    mastersheet (P Primary, B1-B3 Backups) or "teaches"
                    (older sheets). Current only by default, like NP Autopilot.
  programme_timeline "Programme timeline": each programme's modules by week
                    (module -> week, week number), with the module's sessions
                    and slide decks.
"""
from __future__ import annotations

from collections import defaultdict

from .errors import Invalid
from .service import _q

ROLE_ORDER = {"primary": 0, "backup_1": 1, "backup_2": 2, "backup_3": 3}


def _legacy_param(params) -> str:
    lg = str(params.get("legacy") or "current")
    if lg not in ("current", "all"):
        raise Invalid("legacy must be current or all", field="legacy")
    return lg


def teaching_matrix(conn, params: dict) -> dict:
    lg = _legacy_param(params)
    role = params.get("role") or None
    if role and role not in ROLE_ORDER and role != "any_role":
        raise Invalid("role must be primary, backup_1, backup_2, backup_3 or any_role", field="role")
    rows = _q(conn, """
        select e.source_id as instructor_id, i.name as instructor, i.is_legacy as instructor_legacy,
               e.target_id as target_id, m.name as target, tt.key as target_type, m.is_legacy as target_legacy,
               e.props ->> 'role' as role, coalesce(e.props ->> 'tier', '') as tier
          from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'teaches'
          join kb.nodes i on i.id = e.source_id join kb.node_types it on it.id = i.type_id and it.key = 'instructor'
          join kb.nodes m on m.id = e.target_id join kb.node_types tt on tt.id = m.type_id and tt.key in ('module', 'session')
         where e.archived_at is null and i.archived_at is null and m.archived_at is null""")
    if lg == "current":
        rows = [r for r in rows if not r["instructor_legacy"] and not r["target_legacy"]]
    if role == "any_role":
        rows = [r for r in rows if r["role"]]
    elif role:
        rows = [r for r in rows if r["role"] == role]
    # a module's domains (domain contains module), and a session's module
    doms = defaultdict(list)
    for r in _q(conn, """select e.target_id, d.id, d.name from kb.edges e
                          join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                          join kb.nodes d on d.id = e.source_id join kb.node_types dt on dt.id = d.type_id and dt.key = 'domain'
                         where e.archived_at is null and d.archived_at is null"""):
        doms[str(r["target_id"])].append({"id": str(r["id"]), "name": r["name"]})
    parent_mod = {}
    for r in _q(conn, """select e.target_id, e.source_id from kb.edges e
                          join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                          join kb.nodes m on m.id = e.source_id join kb.node_types mt on mt.id = m.type_id and mt.key = 'module'
                          join kb.nodes s on s.id = e.target_id join kb.node_types st on st.id = s.type_id and st.key = 'session'
                         where e.archived_at is null"""):
        parent_mod.setdefault(str(r["target_id"]), str(r["source_id"]))
    if params.get("domain"):
        want = str(params["domain"])
        rows = [r for r in rows if any(d["id"] == want for d in doms.get(str(parent_mod.get(str(r["target_id"]), r["target_id"])), []))]
    if params.get("q"):
        q = str(params["q"]).strip().lower()[:100]
        rows = [r for r in rows if q in r["instructor"].lower() or q in r["target"].lower()]
    instructors, columns, cells = {}, {}, {}
    for r in rows:
        iid, tid = str(r["instructor_id"]), str(r["target_id"])
        instructors[iid] = {"id": iid, "name": r["instructor"], "legacy": r["instructor_legacy"]}
        mid = parent_mod.get(tid, tid)
        columns[tid] = {"id": tid, "name": r["target"], "type": r["target_type"], "legacy": r["target_legacy"],
                        "module_id": mid if r["target_type"] == "session" else None,
                        "domains": doms.get(mid, [])}
        k = f"{iid}|{tid}"
        cur = cells.get(k)
        new = {"instructor_id": iid, "target_id": tid, "role": r["role"], "tier": r["tier"] or "older_sheets"}
        if cur is None or ROLE_ORDER.get(r["role"] or "", 9) < ROLE_ORDER.get(cur["role"] or "", 9):
            cells[k] = new
    first_role = defaultdict(lambda: 9)
    for c in cells.values():
        first_role[c["instructor_id"]] = min(first_role[c["instructor_id"]], ROLE_ORDER.get(c["role"] or "", 9))
    inst = sorted(instructors.values(), key=lambda x: (first_role[x["id"]], x["name"].lower()))
    cols = sorted(columns.values(), key=lambda x: (x["type"] != "module", (x["domains"][0]["name"].lower() if x["domains"] else "~"),
                                                   x["name"].lower()))
    all_domains = sorted({d["id"]: d for c in cols for d in c["domains"]}.values(), key=lambda d: d["name"].lower())
    return {"instructors": inst, "columns": cols, "cells": list(cells.values()), "domains": all_domains, "legacy": lg,
            "counts": {r: sum(1 for c in cells.values() if c["role"] == r) for r in ROLE_ORDER} |
                      {"teaches_without_role": sum(1 for c in cells.values() if not c["role"])}}


def programme_timeline(conn, params: dict) -> dict:
    """Programmes (all from the older sheets in today's data, so legacy is
    shown here, badged) -> modules -> the weeks they are scheduled in."""
    progs = _q(conn, """select n.id, n.name, n.is_legacy from kb.nodes n join kb.node_types t on t.id = n.type_id
                         where t.key = 'program' and n.archived_at is null order by n.name_norm""")
    if params.get("program"):
        progs = [p for p in progs if str(p["id"]) == str(params["program"])]
    contains = defaultdict(list)
    for r in _q(conn, """select e.source_id, o.id, o.name, ot.key as type, o.is_legacy, o.props
                          from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                          join kb.nodes o on o.id = e.target_id join kb.node_types ot on ot.id = o.type_id
                         where e.archived_at is null and o.archived_at is null and ot.key in ('module', 'week', 'session')"""):
        contains[str(r["source_id"])].append(r)
    decks = defaultdict(list)
    for r in _q(conn, """select nr.node_id, r.id, r.title, r.url from kb.node_resources nr join kb.resources r on r.id = nr.resource_id
                         where nr.archived_at is null and r.archived_at is null and (r.kind = 'slides' or nr.note = 'Slides')"""):
        decks[str(r["node_id"])].append({"id": str(r["id"]), "title": r["title"], "url": r["url"]})
    out = []
    for p in progs:
        weeks = defaultdict(list)
        for m in (x for x in contains[str(p["id"])] if x["type"] == "module"):
            mid = str(m["id"])
            entry = {"id": mid, "name": m["name"], "legacy": m["is_legacy"],
                     "sessions": [{"id": str(s["id"]), "name": s["name"]} for s in contains[mid] if s["type"] == "session"],
                     "decks": decks.get(mid, [])}
            wk = [w for w in contains[mid] if w["type"] == "week"]
            nums = sorted({(w["props"] or {}).get("week_number") for w in wk if isinstance((w["props"] or {}).get("week_number"), int)})
            for n in nums or [None]:
                weeks[n].append(entry)
        out.append({"id": str(p["id"]), "name": p["name"], "legacy": p["is_legacy"],
                    "weeks": [{"week": k, "modules": sorted(v, key=lambda e: e["name"].lower())}
                              for k, v in sorted(weeks.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))]})
    return {"programmes": out}
