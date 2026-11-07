#!/usr/bin/env python3
"""Remove obsolete knowledge-base data safely (owner decision 2026-11-07, run C).

    python scripts/cleanup_obsolete.py plan    --db local|dev     # what would go, with counts; no writes
    python scripts/cleanup_obsolete.py export  --db local|dev     # every affected row -> backups/ (gitignored)
    python scripts/cleanup_obsolete.py archive --db local|dev     # step 1: archive (reversible in the app)
    python scripts/cleanup_obsolete.py verify  --db local|dev     # graph checks after archiving
    python scripts/cleanup_obsolete.py delete  --db local|dev --export backups/<file>.json
    python scripts/cleanup_obsolete.py restore --db local|dev --export backups/<file>.json

THE SAFETY SEQUENCE (the owner's): a restore-TESTED backup (scripts/verify_backup_restore.py) -> export
-> archive -> verify graph and counts -> permanent delete. Production only at go-live with the owner's
approval (GO_LIVE step 6b); this script refuses the production project outright.

What is OBSOLETE (each rule says why; nothing is removed by a name guess):
  nodes.archived    records already archived: the retired weeks, workflows and themes (run B) and the
                    legacy instructors (run 6). Permanently deleted.
  nodes.old_program program records with no KYP behind them: the NP Autopilot corpus listed KYP and
                    curriculum DOCUMENTS as programs. The current programs come from the KYPs
                    (pipeline/kb_import_curriculum.py); a document-named program the import did not
                    adopt is obsolete. Deferred families (EdgeUp, Agentic AI, PM/TPM/EM) are rebuilt from
                    the Confluence KYPs when they come into scope.
  edges.archived    relationships already archived (converted to the run-C model, or archived with a
                    record) whose two records stay.
  edges.old_contains a KYP program's direct "contains module" links that the KYPs do not state (left over
                    from the corpus document): the KYP structure is Program -> Course -> Module.
  resources.lone    links attached ONLY to records deleted here.
What STAYS, flagged for review when it is valid but no current source states it:
  modules with no KYP behind them (they hold SME assignments and topics): flagged "not in the current
  KYPs", with the closest KYP module named when there is one. Live instructors, team members, topics
  and sessions stay (disconnected ones are counted, not deleted).
Never re-created: every deleted record the sync knew is added to kb.sync_exclusions, and so is every deleted
relationship, link and attachment it knew (by its source key, migration 0041).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web")]
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402
from pipeline.lib import taxonomy as _tax                            # noqa: E402

OWNED_BY = _tax.edge_for_role("domain_primary")
from lib.kb.legacy_delete import _json_default, _rows, _writable_cols  # noqa: E402

LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
FORMAT = "kb-cleanup-run-c-1"
ARCHIVED_AT = "2026-11-07 18:00:00+00"          # the marker this script's archive step uses
FLAG_NOT_IN_KYP = "Not in the current KYPs (run C cleanup kept it: it holds SME assignments or topics)."
CASCADED = (("edges", "source_id"), ("edges", "target_id"), ("node_resources", "node_id"), ("node_tags", "node_id"),
            ("graph_positions", "node_id"), ("legacy_archive", "node_id"), ("person_accounts", "node_id"))


def db_url(which):
    if which == "local":
        return LOCAL, "local"
    if which == "dev":
        from dotenv import dotenv_values
        u = dotenv_values(REPO / ".env").get("DEV_SUPABASE_DB_URL") or ""
        if not u:
            sys.exit("DEV_SUPABASE_DB_URL is not set")
        return u, "dev"
    sys.exit("use --db local or --db dev")


def _ids(conn, sql, p=()):
    return [str(r[0]) for r in conn.execute(sql, p).fetchall()]


def plan(conn) -> dict:
    archived = _ids(conn, "select id from kb.nodes where archived_at is not null and archived_at <> %s", (ARCHIVED_AT,))
    archived_by_us = _ids(conn, "select id from kb.nodes where archived_at = %s", (ARCHIVED_AT,))
    old_prog = _ids(conn, """select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id
                             where t.key = 'program' and not (n.props ? 'kyp_key')
                               and (n.archived_at is null or n.archived_at = %s)""", (ARCHIVED_AT,))
    nodes = sorted(set(archived) | set(archived_by_us) | set(old_prog))
    old_contains = _ids(conn, """select e.id from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                                 join kb.nodes p on p.id = e.source_id join kb.node_types pt on pt.id = p.type_id and pt.key = 'program'
                                 join kb.nodes m on m.id = e.target_id join kb.node_types mt on mt.id = m.type_id and mt.key = 'module'
                                 where (p.props ? 'kyp_key') and not (e.props ? 'provenance')
                                   and (e.archived_at is null or e.archived_at = %s)""", (ARCHIVED_AT,))
    arch_edges = _ids(conn, """select e.id from kb.edges e join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
                               where e.archived_at is not null and not (s.id = any(%s::uuid[])) and not (t.id = any(%s::uuid[]))""",
                      (nodes, nodes))
    edges = sorted(set(old_contains) | set(arch_edges))
    lone = _ids(conn, """select r.id from kb.resources r
                         where exists (select 1 from kb.node_resources nr where nr.resource_id = r.id and nr.node_id = any(%s::uuid[]))
                           and not exists (select 1 from kb.node_resources nr where nr.resource_id = r.id and not (nr.node_id = any(%s::uuid[])))""",
                (nodes, nodes))
    keep_flag = _rows(conn, """select m.id, m.name,
              (select k.name from kb.nodes k join kb.node_types kt on kt.id = k.type_id and kt.key = 'module'
                where (k.props ? 'kyp_key') and k.archived_at is null and k.scope_id is null
                  and extensions.similarity(k.name_norm, m.name_norm) > 0.35
                order by extensions.similarity(k.name_norm, m.name_norm) desc limit 1) as closest
            from kb.nodes m join kb.node_types mt on mt.id = m.type_id and mt.key = 'module'
            where m.archived_at is null and not (m.props ? 'kyp_key')""")
    by_type = dict(conn.execute("""select t.key, count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
                                   where n.id = any(%s::uuid[]) group by 1""", (nodes,)).fetchall())
    return {"nodes": nodes, "edges": edges, "lone_resources": lone, "keep_and_flag": keep_flag,
            "counts": {"nodes": len(nodes), "nodes_by_type": by_type, "nodes_archived_before": len(archived),
                       "old_programs": len(old_prog), "edges_old_program_contains": len(old_contains),
                       "edges_archived": len(arch_edges), "lone_resources": len(lone), "kept_and_flagged_modules": len(keep_flag)}}


def counts(conn) -> dict:
    q = lambda s: conn.execute(s).fetchone()[0]                         # noqa: E731
    return {"nodes_live": q("select count(*) from kb.nodes where archived_at is null"),
            "nodes_archived": q("select count(*) from kb.nodes where archived_at is not null"),
            "edges_live": q("select count(*) from kb.edges where archived_at is null"),
            "edges_archived": q("select count(*) from kb.edges where archived_at is not null"),
            "resources": q("select count(*) from kb.resources"),
            "by_type": dict(conn.execute("""select t.key, count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
                                            where n.archived_at is null group by 1 order by 1""").fetchall())}


def verify(conn) -> dict:
    """Graph checks: exactly four domains; no week structure; owners only team members; SMEs only with a
    role; no live edge to an archived record; no live duplicate; disconnected live records counted."""
    q = lambda s: conn.execute(s).fetchone()[0]                         # noqa: E731
    out = {
        "domains_live": q("select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'domain' and n.archived_at is null"),
        "domain_names": [r[0] for r in conn.execute("select n.name from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'domain' and n.archived_at is null order by 1")],
        "week_records_live": q("select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'week' and n.archived_at is null"),
        "live_edges_to_week_records": q("""select count(*) from kb.edges e join kb.nodes n on n.id in (e.source_id, e.target_id)
                                           join kb.node_types t on t.id = n.type_id where t.key = 'week' and e.archived_at is null"""),
        "owners_not_team_members": q(f"""select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = '{OWNED_BY}'
                                        join kb.nodes o on o.id = e.target_id join kb.node_types ot on ot.id = o.type_id
                                        where e.archived_at is null and ot.key <> 'team_member'"""),
        "owner_by_role_fields_set": q("select count(*) from kb.nodes where owner_record_id is not null or cardinality(co_owner_record_ids) > 0"),
        "smes_without_role": q("""select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'sme'
                                  where e.archived_at is null and coalesce(e.props->>'role', '') = ''"""),
        "smes_not_instructor_to_module": q("""select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'sme'
                                  join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
                                  join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
                                  where e.archived_at is null and (st.key <> 'instructor' or tt.key <> 'module')"""),
        "live_edges_touching_archived": q("""select count(*) from kb.edges e join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
                                             where e.archived_at is null and (s.archived_at is not null or t.archived_at is not null)"""),
        "live_duplicate_edges": q("""select count(*) from (select 1 from kb.edges where archived_at is null
                                     group by edge_type_id, source_id, target_id having count(*) > 1) d"""),
        "programs_without_kyp": q("""select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
                                     where t.key = 'program' and n.archived_at is null and not (n.props ? 'kyp_key')"""),
        "curriculum_edges_without_provenance": q("""select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                                     join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
                                     where e.archived_at is null and st.key in ('program', 'course') and not (e.props ? 'provenance')"""),
    }
    out["disconnected_live_by_type"] = dict(conn.execute("""select t.key, count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
        where n.archived_at is null and not exists (select 1 from kb.edges e where e.archived_at is null and (e.source_id = n.id or e.target_id = n.id))
        group by 1 order by 1""").fetchall())
    out["ok"] = (out["domains_live"] == 4 and out["week_records_live"] == 0 and out["live_edges_to_week_records"] == 0
                 and out["owners_not_team_members"] == 0 and out["smes_without_role"] == 0 and out["smes_not_instructor_to_module"] == 0
                 and out["live_edges_touching_archived"] == 0 and out["live_duplicate_edges"] == 0 and out["owner_by_role_fields_set"] == 0)
    return out


def export(conn, p: dict) -> dict:
    ids = p["nodes"]
    out = {"format": FORMAT, "made_at": datetime.now(timezone.utc).isoformat(), "plan": p, "tables": {}}
    out["tables"]["nodes"] = _rows(conn, "select * from kb.nodes where id = any(%s::uuid[])", (ids,))
    for table, col in CASCADED:
        rows = _rows(conn, f"select * from kb.{table} where {col} = any(%s::uuid[])", (ids,))
        have = out["tables"].setdefault(table, [])
        seen = {str(r["id"]) if "id" in r else json.dumps(r, default=str, sort_keys=True) for r in have}
        have += [r for r in rows if (str(r["id"]) if "id" in r else json.dumps(r, default=str, sort_keys=True)) not in seen]
    seen = {str(r["id"]) for r in out["tables"]["edges"]}
    out["tables"]["edges"] += [r for r in _rows(conn, "select * from kb.edges where id = any(%s::uuid[])", (p["edges"],)) if str(r["id"]) not in seen]
    out["tables"]["resources"] = _rows(conn, "select * from kb.resources where id = any(%s::uuid[])", (p["lone_resources"],))
    out["tables"]["node_resources"] += [r for r in _rows(conn, "select * from kb.node_resources where resource_id = any(%s::uuid[])",
                                                         (p["lone_resources"],)) if str(r["id"]) not in {str(x["id"]) for x in out["tables"]["node_resources"]}]
    out["tables"]["sync_map"] = _rows(conn, "select * from kb.sync_map where kb_id = any(%s::uuid[])",
                                      (ids + [str(r["id"]) for r in out["tables"]["edges"]] + [str(r["id"]) for r in out["tables"]["node_resources"]]
                                       + p["lone_resources"],))
    return out


def archive(conn, p: dict) -> dict:
    n = conn.execute("""update kb.nodes set archived_at = %s, status = 'archived' where id = any(%s::uuid[]) and archived_at is null""",
                     (ARCHIVED_AT, p["nodes"])).rowcount
    e = conn.execute("""update kb.edges set archived_at = %s, status = 'archived' where id = any(%s::uuid[]) and archived_at is null""",
                     (ARCHIVED_AT, p["edges"])).rowcount
    f = 0
    for m in p["keep_and_flag"]:
        reason = FLAG_NOT_IN_KYP + (f" Closest KYP module: {m['closest']}." if m.get("closest") else "")
        if not conn.execute("select 1 from kb.flags where target_id = %s and reason like %s and status = 'open'",
                            (m["id"], FLAG_NOT_IN_KYP[:30] + "%")).fetchone():
            conn.execute("insert into kb.flags (target_table, target_id, reason) values ('nodes', %s, %s)", (m["id"], reason))
            f += 1
    return {"records_archived": n, "relationships_archived": e, "modules_flagged": f}


def delete(conn, p: dict, data: dict) -> dict:
    ext = [r["external_id"][3:] for r in data["tables"]["nodes"] if (r.get("external_id") or "").startswith("np:")]
    conn.cursor().executemany("insert into kb.sync_exclusions (unit, key, reason) values ('record', %s, 'deleted by the run-C cleanup') "
                              "on conflict do nothing", [(k,) for k in ext])
    # relationships / links / attachments the sync knew: excluded by their source key (0041), so a sync never
    # writes them again even though both records stay
    keys = [(r["unit"], r["key"]) for r in data["tables"]["sync_map"] if r["unit"] in ("relationship", "link", "attachment")]
    conn.cursor().executemany("insert into kb.sync_exclusions (unit, key, reason) values (%s, %s, 'deleted by the run-C cleanup') "
                              "on conflict do nothing", keys)
    conn.execute("delete from kb.sync_map where kb_id = any(%s::uuid[])", ([str(r["kb_id"]) for r in data["tables"]["sync_map"]],))
    e = conn.execute("delete from kb.edges where id = any(%s::uuid[])", (p["edges"],)).rowcount
    n = conn.execute("delete from kb.nodes where id = any(%s::uuid[])", (p["nodes"],)).rowcount
    r = conn.execute("delete from kb.resources where id = any(%s::uuid[])", (p["lone_resources"],)).rowcount
    return {"records_deleted": n, "relationships_deleted": e, "resources_deleted": r, "sync_exclusions_added": len(ext),
            "sync_key_exclusions_added": len(keys)}


def restore(conn, data: dict) -> dict:
    if data.get("format") != FORMAT:
        raise SystemExit("REFUSED: not a run-C cleanup export")
    from psycopg.types.json import Jsonb
    T, counts_ = data["tables"], {}
    nodes = T["nodes"]
    ids = {str(r["id"]) for r in nodes}
    ordered, placed = [], set()
    while len(ordered) < len(nodes):
        before = len(ordered)
        for r in nodes:
            rid, sc = str(r["id"]), (str(r["scope_id"]) if r.get("scope_id") else None)
            if rid not in placed and (sc is None or sc not in ids or sc in placed):
                ordered.append(r); placed.add(rid)
        if len(ordered) == before:
            raise SystemExit("REFUSED: scopes form a cycle")
    for table, rows in (("nodes", ordered), ("resources", T.get("resources", [])),
                        *[(t, T.get(t, [])) for t in ("edges", "node_resources", "node_tags", "graph_positions", "legacy_archive", "person_accounts", "sync_map")]):
        if not rows:
            counts_[table] = 0
            continue
        typed = [(c, t) for c, t in _writable_cols(conn, table) if c in rows[0]]
        cols = [c for c, _ in typed]
        conn.cursor().executemany(f"insert into kb.{table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) on conflict do nothing",
                                  [[Jsonb(r[c]) if t in ("jsonb", "json") and r[c] is not None else r[c] for c, t in typed] for r in rows])
        counts_[table] = len(rows)
    ext = [r["external_id"][3:] for r in nodes if (r.get("external_id") or "").startswith("np:")]
    conn.execute("delete from kb.sync_exclusions where unit = 'record' and key = any(%s) and reason = 'deleted by the run-C cleanup'", (ext,))
    keys = [r["key"] for r in T.get("sync_map", []) if r["unit"] in ("relationship", "link", "attachment")]
    conn.execute("delete from kb.sync_exclusions where unit in ('relationship', 'link', 'attachment') and key = any(%s) "
                 "and reason = 'deleted by the run-C cleanup'", (keys,))
    return counts_


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "export", "archive", "verify", "delete", "restore", "exclusions"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--export", help="the export file (delete, restore)")
    a = ap.parse_args()
    url, label = db_url(a.db)
    if PRODUCTION_REF in url:
        print("refused: that is the production database"); return 2
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("set statement_timeout = '600s'")
        conn.execute("select set_config('kb.actor_type', 'system', true), set_config('kb.operator', 'on', true)")
        print("before:", json.dumps(counts(conn)))
        if a.cmd == "exclusions":
            # (re)write the sync exclusions an export implies, for a cleanup deleted before 0041 existed
            data = json.loads(Path(a.export).read_text(encoding="utf-8"))
            if data.get("format") != FORMAT:
                print("refused: not a run-C cleanup export"); return 2
            rows = [("record", r["external_id"][3:]) for r in data["tables"]["nodes"] if (r.get("external_id") or "").startswith("np:")]
            rows += [(r["unit"], r["key"]) for r in data["tables"]["sync_map"] if r["unit"] in ("relationship", "link", "attachment")]
            before = conn.execute("select count(*) from kb.sync_exclusions").fetchone()[0]
            conn.cursor().executemany("insert into kb.sync_exclusions (unit, key, reason) values (%s, %s, 'deleted by the run-C cleanup') "
                                      "on conflict do nothing", rows)
            print("exclusions:", json.dumps({"implied": len(rows), "added": conn.execute("select count(*) from kb.sync_exclusions").fetchone()[0] - before}))
            conn.commit(); return 0
        if a.cmd == "verify":
            print("verify:", json.dumps(verify(conn), default=str)); conn.rollback(); return 0
        p = plan(conn)
        print("plan:", json.dumps(p["counts"]))
        if a.cmd == "plan":
            for m in p["keep_and_flag"]:
                print("  keep+flag module:", m["name"], "| closest KYP module:", m["closest"])
            conn.rollback(); return 0
        if a.cmd == "export":
            data = export(conn, p)
            out = REPO / "backups" / f"cleanup_run_c_{label}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(data, default=_json_default), encoding="utf-8")
            print("export:", out.relative_to(REPO), {k: len(v) for k, v in data["tables"].items()})
            conn.rollback(); return 0
        if a.cmd == "archive":
            res = archive(conn, p)
        else:
            if not a.export:
                print("--export <file> is required"); return 2
            data = json.loads(Path(a.export).read_text(encoding="utf-8"))
            if a.cmd == "delete":
                if data.get("format") != FORMAT:
                    print("refused: not a run-C cleanup export"); return 2
                missing = set(p["nodes"]) - {str(r["id"]) for r in data["tables"]["nodes"]}
                if missing or set(p["edges"]) - {str(r["id"]) for r in data["tables"]["edges"]}:
                    print(f"refused: the export does not cover the current plan ({len(missing)} records missing); export again"); return 2
                live = conn.execute("select count(*) from kb.nodes where id = any(%s::uuid[]) and archived_at is null", (p["nodes"],)).fetchone()[0]
                if live:
                    print(f"refused: {live} record(s) in the plan are not archived yet; run archive and verify first"); return 2
                res = delete(conn, p, data)
            else:
                res = restore(conn, data)
        print(a.cmd + ":", json.dumps(res))
        print("after: ", json.dumps(counts(conn)))
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
