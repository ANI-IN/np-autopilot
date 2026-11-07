"""The owner-approved PERMANENT deletion of the legacy domains and legacy
modules (run 6 resume, R3). CLI: pipeline/kb_legacy_delete.py.

What goes:
  - every domain that is not one of the four current ones (Full Stack, Backend,
    Frontend, Test Engineering: matched by name in the data, and they must be
    exactly the non-legacy domains, or nothing happens);
  - every legacy module (NP Autopilot's own rule: no domain_slug; is_legacy);
  - with them, by the database's cascades: their relationships (a current
    instructor's expertise link to a legacy domain goes; the instructor stays),
    their attachments, tags, saved positions and legacy-archive rows.
What stays:
  - legacy instructors, topics, sessions, programmes and everything else;
  - records that sat INSIDE a deleted record (scope) are detached, not deleted,
    and flagged for Data quality; links that were attached only to deleted
    records are flagged the same way.
Never re-created: kb.sync_exclusions (0037) switches on the sync's rule
(NP Autopilot's legacy logic for domains and modules) and lists every deleted
source id. The old tables (public.*) are not touched.

Before anything is deleted, `export` writes every affected row to a JSON file
(backups/, gitignored: it holds real data). `restore` puts every row back from
that file, with the same ids, and switches the exclusions off.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

RULE = "np_legacy_domains_modules"
CURRENT_DOMAINS = ("full stack", "backend", "frontend", "test engineering")     # the owner's list, matched by prefix
FLAG_REASON = "Its parent was permanently deleted with the legacy domains and modules (run 6). Give it a new parent, or archive it."
# Tables whose rows go with a deleted record (by FK cascade), exported so they can come back.
CASCADED = (("edges", "source_id"), ("edges", "target_id"), ("node_resources", "node_id"), ("node_tags", "node_id"),
            ("graph_positions", "node_id"), ("legacy_archive", "node_id"), ("person_accounts", "node_id"))


def _rows(conn, sql, p=()):
    cur = conn.execute(sql, p)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _norm(name: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", (name or "").strip().lower())


def _writable_cols(conn, table: str) -> list[tuple[str, str]]:
    """(column, data type) for every column except generated ones (recomputed on insert)."""
    return [(r[0], r[1]) for r in conn.execute(
        """select column_name, data_type from information_schema.columns
           where table_schema = 'kb' and table_name = %s and is_generated = 'NEVER'
             and (identity_generation is null or identity_generation = 'BY DEFAULT')
           order by ordinal_position""", (table,)).fetchall()]


def plan(conn, current_names: tuple = CURRENT_DOMAINS) -> dict:
    doms = _rows(conn, """select n.id, n.name, n.is_legacy, n.external_id from kb.nodes n join kb.node_types t on t.id = n.type_id
                          where t.key = 'domain'""")
    current = [d for d in doms if any(_norm(d["name"]).startswith(c) for c in current_names) and not d["is_legacy"]]
    if len(current) != len(current_names) or {_norm(d["name"]).split()[0] for d in current} != {c.split()[0] for c in current_names}:
        raise SystemExit(f"REFUSED: expected exactly the {len(current_names)} current domains {current_names}, "
                         f"found {len(current)} matching non-legacy domains; nothing deleted")
    keep = {str(d["id"]) for d in current}
    unexpected = [str(d["id"]) for d in doms if not d["is_legacy"] and str(d["id"]) not in keep]
    if unexpected:
        raise SystemExit(f"REFUSED: {len(unexpected)} non-legacy domain(s) outside the owner's list (ids: {unexpected[:5]}); nothing deleted")
    dom_ids = [str(d["id"]) for d in doms if str(d["id"]) not in keep]
    mod_ids = [str(r[0]) for r in conn.execute("""select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
                                                  where t.key = 'module' and n.is_legacy""").fetchall()]
    ids = dom_ids + mod_ids
    orphans = [str(r[0]) for r in conn.execute(
        "select id from kb.nodes where scope_id = any(%s::uuid[]) and not (id = any(%s::uuid[]))", (ids, ids)).fetchall()]
    lone_links = [str(r[0]) for r in conn.execute(
        """select distinct nr.resource_id from kb.node_resources nr
           where nr.node_id = any(%s::uuid[])
             and not exists (select 1 from kb.node_resources o where o.resource_id = nr.resource_id
                             and not (o.node_id = any(%s::uuid[])))""", (ids, ids)).fetchall()]
    expertise = conn.execute(
        """select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
           where et.key = 'sme' and e.target_id = any(%s::uuid[])""", (dom_ids,)).fetchone()[0]
    return {"current_domains": sorted(d["name"] for d in current), "domains": dom_ids, "modules": mod_ids,
            "orphans": orphans, "lone_links": lone_links, "expertise_links": expertise}


def export(conn, p: dict) -> dict:
    ids = p["domains"] + p["modules"]
    out = {"format": "kb-legacy-delete-1", "made_at": datetime.now(timezone.utc).isoformat(),
           "plan": {k: v for k, v in p.items()}, "tables": {}}
    out["tables"]["nodes"] = _rows(conn, "select * from kb.nodes where id = any(%s::uuid[])", (ids,))
    for table, col in CASCADED:
        rows = _rows(conn, f"select * from kb.{table} where {col} = any(%s::uuid[])", (ids,))
        have = out["tables"].setdefault(table, [])
        seen = {json.dumps(r, default=str, sort_keys=True) for r in have}
        have += [r for r in rows if json.dumps(r, default=str, sort_keys=True) not in seen]
    out["tables"]["orphan_scopes"] = _rows(conn, "select id, scope_id from kb.nodes where id = any(%s::uuid[])", (p["orphans"],))
    out["tables"]["sync_map"] = _rows(conn, "select * from kb.sync_map where kb_id = any(%s::uuid[])",
                                      ([str(r["id"]) for r in out["tables"]["edges"]] + ids
                                       + [str(r["id"]) for r in out["tables"]["node_resources"]],))
    return out


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, (UUID, Decimal)):
        return str(o)
    raise TypeError(type(o).__name__)


def write_export(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=_json_default, indent=0), encoding="utf-8")


def delete(conn, p: dict, data: dict) -> dict:
    """In the caller's transaction. Order: exclusions, detach the orphans (and
    refresh their sync checksum so the next sync sees no false conflict), flag
    them and the lone links, delete (cascades), drop the sync_map rows."""
    from . import sync as engine
    ids = p["domains"] + p["modules"]
    conn.execute("select set_config('kb.actor_type', 'system', true)")
    conn.execute("insert into kb.sync_exclusions (unit, key, reason) values ('rule', %s, %s) on conflict do nothing",
                 (RULE, "owner-approved permanent deletion of the legacy domains and modules (run 6)"))
    ext = [r["external_id"][3:] for r in data["tables"]["nodes"] if (r.get("external_id") or "").startswith("np:")]
    conn.cursor().executemany("insert into kb.sync_exclusions (unit, key, reason) values ('record', %s, 'deleted with the legacy cleanup') "
                              "on conflict do nothing", [(k,) for k in ext])
    conn.execute("update kb.nodes set scope_id = null where id = any(%s::uuid[])", (p["orphans"],))
    for nid in p["orphans"]:
        cur = engine._kb_record(conn, nid)
        if cur:
            conn.execute("update kb.sync_map set kb_checksum = %s where unit = 'record' and kb_id = %s", (engine._h(cur["content"]), nid))
    flags = [("nodes", nid) for nid in p["orphans"]] + [("resources", rid) for rid in p["lone_links"]]
    conn.cursor().executemany("insert into kb.flags (target_table, target_id, reason) values (%s, %s, %s)",
                              [(t, i, FLAG_REASON) for t, i in flags])
    sm = [r["kb_id"] for r in data["tables"]["sync_map"]]
    conn.execute("delete from kb.sync_map where kb_id = any(%s::uuid[])", (sm,))
    n = conn.execute("delete from kb.nodes where id = any(%s::uuid[])", (ids,)).rowcount
    return {"deleted_records": n, "domains": len(p["domains"]), "modules": len(p["modules"]),
            "relationships": len(data["tables"]["edges"]), "attachments": len(data["tables"]["node_resources"]),
            "expertise_links": p["expertise_links"], "detached_and_flagged": len(p["orphans"]),
            "links_flagged": len(p["lone_links"]), "excluded_source_ids": len(ext)}


def restore(conn, data: dict) -> dict:
    """Every exported row back, same ids; the exclusions and the flags go."""
    if data.get("format") != "kb-legacy-delete-1":
        raise SystemExit("REFUSED: not a legacy-delete export")
    conn.execute("select set_config('kb.actor_type', 'system', true)")
    T = data["tables"]
    counts = {}
    nodes = T["nodes"]
    ids = {str(r["id"]) for r in nodes}
    # containers before what sits in them (a deleted module may sit in a deleted domain)
    ordered, placed = [], set()
    while len(ordered) < len(nodes):
        before = len(ordered)
        for r in nodes:
            rid = str(r["id"])
            if rid in placed:
                continue
            sc = str(r["scope_id"]) if r.get("scope_id") else None
            if sc is None or sc not in ids or sc in placed:
                ordered.append(r); placed.add(rid)
        if len(ordered) == before:
            raise SystemExit("REFUSED: the export's scopes form a cycle")
    for table, rows in (("nodes", ordered), *[(t, T.get(t, [])) for t in
                        ("edges", "node_resources", "node_tags", "graph_positions", "legacy_archive", "person_accounts", "sync_map")]):
        if not rows:
            counts[table] = 0
            continue
        from psycopg.types.json import Jsonb
        typed = [(c, t) for c, t in _writable_cols(conn, table) if c in rows[0]]
        cols = [c for c, _ in typed]
        sql = f"insert into kb.{table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) on conflict do nothing"
        vals = [[Jsonb(r[c]) if t in ("jsonb", "json") and r[c] is not None else r[c] for c, t in typed] for r in rows]
        conn.cursor().executemany(sql, vals)
        counts[table] = len(rows)
    for r in T.get("orphan_scopes", []):
        conn.execute("update kb.nodes set scope_id = %s where id = %s", (r["scope_id"], r["id"]))
    conn.execute("delete from kb.flags where reason = %s", (FLAG_REASON,))
    conn.execute("delete from kb.sync_exclusions")
    return counts


def excluded_keys(conn) -> dict[str, set]:
    """{unit: source keys} for the relationship / link / attachment exclusions (0041); {} before 0041."""
    if not conn.execute("select to_regclass('kb.sync_exclusions') is not null").fetchone()[0]:
        return {}
    out: dict[str, set] = {}
    for u, k in conn.execute("select unit, key from kb.sync_exclusions where unit in ('relationship', 'link', 'attachment')").fetchall():
        out.setdefault(u, set()).add(k)
    return out


def excluded(conn) -> tuple[bool, set]:
    """(rule on?, excluded source ids) for the sync; (False, set()) before 0037."""
    if not conn.execute("select to_regclass('kb.sync_exclusions') is not null").fetchone()[0]:
        return False, set()
    rows = conn.execute("select unit, key from kb.sync_exclusions").fetchall()
    return any(u == "rule" and k == RULE for u, k in rows), {k for u, k in rows if u == "record"}
