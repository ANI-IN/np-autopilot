#!/usr/bin/env python3
"""Retire the week, workflow (process) and theme sections of the knowledge base
(owner decision, 2026-11-07). Reversible; nothing is deleted.

    python scripts/retire_legacy_sections.py plan    --db URL   # counts only, no writes
    python scripts/retire_legacy_sections.py apply   --db URL   # one transaction
    python scripts/retire_legacy_sections.py revert  --db URL   # one transaction, the exact inverse

APPLY, in one transaction, with fixed markers so REVERT touches only what APPLY did:
  1. Owner suggestions: every process record's `suggested_owner` is written to
     an admin-only local file OUTSIDE git (.measure/private/, gitignored) and
     then removed from the record (archived records stay readable by viewers).
     The source table public.workflow_owners is not touched (admin-only).
  2. Schedules: each week record's number is copied onto its module's link from
     its course/domain ("contains"), as props.schedule = {week, program: null,
     from_week_record}. The week records name no program (they came from one
     sheet's schedule), so the program is left empty for the KYP import to fill;
     the number is kept on the LINK, never on the reusable module.
  3. Records: live week, process and theme records are archived with one
     timestamp (ARCHIVED_AT). Their relationships are archived with them by the
     database's cascade (archived_with), and come back with them.
  4. Types: the week, process and theme record types are archived, so they leave
     the legend, the type lists and "New record".

The sync does not bring them back: it skips archived records, and
config/kb-projection-mapping.yaml lists these source types under `retired_types`,
which the sync never imports.

Prints before/after counts. Refuses a database that is not loopback unless
--remote-ok is given (DEV only; never production: the production project ref is
refused outright).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parent.parent
PRIVATE = REPO / ".measure" / "private"
ARCHIVED_AT = "2026-11-07 12:00:00+00"       # the marker REVERT looks for
sys.path.insert(0, str(REPO))
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402  (the one place it is spelled)


def _config():
    import yaml
    m = yaml.safe_load((REPO / "config" / "kb-projection-mapping.yaml").read_text(encoding="utf-8"))
    retired_src = m.get("retired_types") or []
    kb_types = sorted({m["types"][t] for t in retired_src if t in m["types"]})
    return kb_types


def counts(conn, kb_types) -> dict:
    out = {}
    for k in kb_types:
        live, arch = conn.execute("""select count(*) filter (where n.archived_at is null), count(*) filter (where n.archived_at = %s)
                                     from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = %s""", (ARCHIVED_AT, k)).fetchone()
        out[f"{k}_live"], out[f"{k}_archived_by_this"] = live, arch
        row = conn.execute("select archived_at is not null from kb.node_types where key = %s", (k,)).fetchone()
        out[f"{k}_type_archived"] = row[0] if row else None          # None: this database has no such type
    out["edges_live_touching"] = conn.execute("""select count(*) from kb.edges e where e.archived_at is null and exists (
        select 1 from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = any(%s) and n.id in (e.source_id, e.target_id))""", (kb_types,)).fetchone()[0]
    out["suggested_owner_props"] = conn.execute("""select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
        where t.key = 'process' and n.props ? 'suggested_owner'""").fetchone()[0]
    out["links_with_schedule"] = conn.execute("select count(*) from kb.edges where props ? 'schedule' and props->'schedule' ? 'from_week_record'").fetchone()[0]
    out["nodes_live_total"] = conn.execute("select count(*) from kb.nodes where archived_at is null").fetchone()[0]
    out["edges_live_total"] = conn.execute("select count(*) from kb.edges where archived_at is null").fetchone()[0]
    return out


def _attribute(conn):
    conn.execute("select set_config('kb.actor_type', 'sync', true), set_config('kb.actor_id', '', true), "
                 "set_config('request.jwt.claims', '', true), set_config('kb.operator', 'on', true)")


def _label(url: str) -> str:
    return "local" if ("127.0.0.1" in url or "localhost" in url) else "dev"


def apply(conn, kb_types, label) -> dict:
    _attribute(conn)
    # 1. owner suggestions -> local admin-only file, then off the records
    rows = conn.execute("""select n.id::text, n.external_id, n.props->>'workflow_id', n.props->>'suggested_owner'
                           from kb.nodes n join kb.node_types t on t.id = n.type_id
                           where t.key = 'process' and n.props ? 'suggested_owner' order by n.external_id""").fetchall()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    dest = PRIVATE / f"workflow-owner-suggestions-{label}.json"
    if rows:
        dest.write_text(json.dumps([{"node_id": r[0], "external_id": r[1], "workflow_id": r[2], "suggested_owner": r[3]} for r in rows],
                                   indent=1), encoding="utf-8")
    conn.execute("""update kb.nodes n set props = n.props - 'suggested_owner' from kb.node_types t
                    where t.id = n.type_id and t.key = 'process' and n.props ? 'suggested_owner'""")
    # 2. week numbers -> the module's link from its course/domain
    moved = conn.execute("""
        with w as (
          select w.id as week_id, (w.props->>'week_number')::int as week, me.source_id as module_id
          from kb.nodes w join kb.node_types t on t.id = w.type_id and t.key = 'week'
          join kb.edges me on me.target_id = w.id and me.archived_at is null
          where w.archived_at is null and w.props ? 'week_number')
        update kb.edges de set props = coalesce(de.props, '{}'::jsonb) || jsonb_build_object('schedule',
               jsonb_build_object('week', w.week, 'program', null, 'from_week_record', w.week_id::text))
        from w, kb.node_types st, kb.nodes s
        where de.target_id = w.module_id and de.archived_at is null
          and de.edge_type_id = (select id from kb.edge_types where key = 'contains')
          and s.id = de.source_id and st.id = s.type_id and st.key in ('domain', 'course')
        returning de.id""").fetchall()
    # 3. records (the cascade archives their relationships with them)
    conn.execute("""update kb.nodes n set archived_at = %s, status = 'archived' from kb.node_types t
                    where t.id = n.type_id and t.key = any(%s) and n.archived_at is null""", (ARCHIVED_AT, kb_types))
    # 4. the types
    conn.execute("update kb.node_types set archived_at = %s, status = 'archived' where key = any(%s) and archived_at is null",
                 (ARCHIVED_AT, kb_types))
    return {"suggestions_exported": len(rows), "suggestions_file": (str(dest.relative_to(REPO)) if dest.is_relative_to(REPO) else str(dest)) if rows else None, "links_scheduled": len(moved)}


def revert(conn, kb_types, label) -> dict:
    _attribute(conn)
    conn.execute("update kb.node_types set archived_at = null, status = 'active' where key = any(%s) and archived_at = %s",
                 (kb_types, ARCHIVED_AT))
    conn.execute("""update kb.nodes n set archived_at = null, status = 'active' from kb.node_types t
                    where t.id = n.type_id and t.key = any(%s) and n.archived_at = %s""", (kb_types, ARCHIVED_AT))
    unsched = conn.execute("""update kb.edges set props = props - 'schedule'
                              where props ? 'schedule' and props->'schedule' ? 'from_week_record' returning id""").fetchall()
    src = PRIVATE / f"workflow-owner-suggestions-{label}.json"
    back = 0
    if src.exists():
        for r in json.loads(src.read_text(encoding="utf-8")):
            back += conn.execute("""update kb.nodes set props = props || jsonb_build_object('suggested_owner', %s::text)
                                    where id = %s and not props ? 'suggested_owner'""", (r["suggested_owner"], r["node_id"])).rowcount
    return {"links_unscheduled": len(unsched), "suggestions_restored": back}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "apply", "revert"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--remote-ok", action="store_true", help="allow a non-loopback database (DEV only)")
    a = ap.parse_args()
    if PRODUCTION_REF in a.db:
        print("refused: that is the production database"); return 2
    if _label(a.db) != "local" and not a.remote_ok:
        print("refused: not a loopback database (pass --remote-ok for DEV)"); return 2
    kb_types = _config()
    if not kb_types:
        print("nothing to retire: config/kb-projection-mapping.yaml has no retired_types"); return 1
    with psycopg.connect(a.db) as conn:
        conn.execute("set statement_timeout = '120s'")
        before = counts(conn, kb_types)
        print("types:", ", ".join(kb_types))
        print("before:", json.dumps(before))
        if a.cmd == "plan":
            conn.rollback(); return 0
        t0 = time.monotonic()
        res = (apply if a.cmd == "apply" else revert)(conn, kb_types, _label(a.db))
        after = counts(conn, kb_types)
        conn.commit()
        print(a.cmd + ":", json.dumps(res))
        print("after: ", json.dumps(after))
        print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
