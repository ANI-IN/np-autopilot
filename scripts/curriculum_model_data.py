#!/usr/bin/env python3
"""Convert existing knowledge-base data to the run-C curriculum model (migration 0039).

    python scripts/curriculum_model_data.py plan   --db local|dev   # counts only
    python scripts/curriculum_model_data.py apply  --db local|dev   # one transaction
    python scripts/curriculum_model_data.py revert --db local|dev   # one transaction, from the saved before-state

APPLY (owner decisions 2026-11-07):
  1. Domains: exactly four, named Fullstack, Frontend, Backend, Test (config/kb-curriculum-scope.yaml).
     The old names and the SD1-SD4 codes become HIDDEN search aliases (kb.nodes.search_aliases), never
     displayed.
  2. Domain is a classification: each "domain contains module" link becomes "module in_domain domain".
  3. SMEs: each "instructor teaches module" link becomes an SME assignment with a role. The current
     mastersheet's roles map P -> primary, B1/B2/B3 -> backup with order 1/2/3. A link with only an older
     sheet's role gets that role, named as found ("older sheets: primary"); nothing is promoted.
  4. Owners: the run-5 "owner by role" fields held INSTRUCTORS (the module's primary and backups). They
     are cleared after checking that every value is one of the module's SME assignments (so nothing is
     lost). Owners are NP team members from now on (owned_by -> team_member).

The before-state is written to .measure/private/ (gitignored, local). REVERT restores names, relationships
and the owner-by-role fields from it. Order: `pipeline/migrate.py down` (0039) first, which re-allows the
old shapes, then `revert`.

--db local = the local real-data copy (kb_realdata); --db dev = DEV_SUPABASE_DB_URL from .env (read
here, never printed). The production project is refused outright.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg
import yaml

REPO = Path(__file__).resolve().parent.parent
PRIVATE = REPO / ".measure" / "private"
sys.path.insert(0, str(REPO))
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402

SCOPE = yaml.safe_load((REPO / "config" / "kb-curriculum-scope.yaml").read_text(encoding="utf-8"))
NOTE = "converted to the run-C model (2026-11-07)"
LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"


def db_url(which: str) -> tuple[str, str]:
    if which == "local":
        return LOCAL, "local"
    if which == "dev":
        from dotenv import dotenv_values
        url = dotenv_values(REPO / ".env").get("DEV_SUPABASE_DB_URL") or ""
        if not url:
            sys.exit("DEV_SUPABASE_DB_URL is not set")
        return url, "dev"
    return which, ("local" if ("127.0.0.1" in which or "localhost" in which) else "other")


def _attribute(conn):
    conn.execute("select set_config('kb.actor_type', 'import', true), set_config('kb.actor_id', '', true), "
                 "set_config('request.jwt.claims', '', true), set_config('kb.operator', 'on', true)")


def counts(conn) -> dict:
    q = lambda s, *a: conn.execute(s, a).fetchone()[0]                # noqa: E731
    shape = """select count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
               join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
               join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
               where e.archived_at is null and et.key = %s and st.key = %s and tt.key = %s"""
    return {
        "domains": q("select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'domain' and n.archived_at is null"),
        "domain_names": sorted(r[0] for r in conn.execute("select n.name from kb.nodes n join kb.node_types t on t.id = n.type_id where t.key = 'domain' and n.archived_at is null")),
        "domain_contains_module": q(shape, "contains", "domain", "module"),
        "module_in_domain": q(shape, "in_domain", "module", "domain"),
        "teaches_module": q(shape, "teaches", "instructor", "module"),
        "sme_module": q(shape, "sme", "instructor", "module"),
        "owner_by_role_set": q("select count(*) from kb.nodes where owner_record_id is not null or cardinality(co_owner_record_ids) > 0"),
        "nodes_live": q("select count(*) from kb.nodes where archived_at is null"),
        "edges_live": q("select count(*) from kb.edges where archived_at is null"),
    }


def _etype(conn, key):
    r = conn.execute("select id from kb.edge_types where key = %s", (key,)).fetchone()
    if not r:
        sys.exit(f"relationship type {key!r} is missing: apply migration 0039 first")
    return r[0]


def _match_domain(name: str, slug: str | None):
    for d in SCOPE["domains"]:
        if slug and slug == d["slug"]:
            return d
    for d in SCOPE["domains"]:
        if name.lower() in [a.lower() for a in [d["name"]] + d["aliases"]]:
            return d
    return None


def role_of(props: dict) -> dict | None:
    r = (props or {}).get("role")
    if r == "primary":
        return {"role": "primary"}
    if r and r.startswith("backup_") and r[7:].isdigit():
        return {"role": "backup", "rank": int(r[7:])}
    older = (props or {}).get("older_role")
    if older:
        return {"role": f"older sheets: {older}"}
    return None


def apply(conn, label) -> dict:
    _attribute(conn)
    if (PRIVATE / f"run-c-model-before-{label}.json").exists():
        raise SystemExit("refused: a before-state from an earlier apply exists; revert first (or move that file away "
                         "deliberately). Applying twice would overwrite it.")
    before = {"domains": [], "edges_archived": [], "edges_created": [], "owner_by_role": []}
    res = {"domains_renamed": 0, "in_domain_created": 0, "sme_created": 0, "teaches_without_role": 0,
           "owner_by_role_cleared": 0}
    # 1. domains
    for nid, name, props, aliases in conn.execute("""select n.id, n.name, n.props, n.search_aliases from kb.nodes n
            join kb.node_types t on t.id = n.type_id where t.key = 'domain' and n.archived_at is null""").fetchall():
        d = _match_domain(name, (props or {}).get("slug"))
        if d is None:
            raise SystemExit(f"a live domain is not one of the four: rename or remove it first ({len(name)} chars)")
        al = " ".join(dict.fromkeys([name] + d["aliases"]))
        before["domains"].append({"id": str(nid), "name": name, "search_aliases": aliases, "props": props})
        if name != d["name"] or aliases != al:
            conn.execute("update kb.nodes set name = %s, search_aliases = %s where id = %s", (d["name"], al, nid))
            res["domains_renamed"] += 1
    # 1b. a domain is not a container: records scoped to a domain lose that scope (kept in the before-state)
    before["scopes_cleared"] = []
    for nid, scope in conn.execute("""select n.id, n.scope_id from kb.nodes n join kb.nodes s on s.id = n.scope_id
            join kb.node_types st on st.id = s.type_id where st.key = 'domain' and n.archived_at is null""").fetchall():
        conn.execute("update kb.nodes set scope_id = null where id = %s", (nid,))
        before["scopes_cleared"].append({"id": str(nid), "scope_id": str(scope)})
    res["domain_scopes_cleared"] = len(before["scopes_cleared"])
    # 2. domain contains module -> module in_domain domain
    in_dom, contains, teaches, sme = (_etype(conn, k) for k in ("in_domain", "contains", "teaches", "sme"))
    for eid, src, tgt in conn.execute("""select e.id, e.source_id, e.target_id from kb.edges e
            join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
            join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
            where e.archived_at is null and e.edge_type_id = %s and st.key = 'domain' and tt.key = 'module'""", (contains,)).fetchall():
        new = conn.execute("""insert into kb.edges (edge_type_id, source_id, target_id, props, note)
                              values (%s, %s, %s, %s, %s) on conflict do nothing returning id""",
                           (in_dom, tgt, src, json.dumps({"converted_from": str(eid)}), NOTE)).fetchone()
        conn.execute("update kb.edges set archived_at = now(), status = 'archived' where id = %s", (eid,))
        before["edges_archived"].append(str(eid))
        if new:
            before["edges_created"].append(str(new[0]))
            res["in_domain_created"] += 1
    # 3. instructor teaches module -> SME with a role
    for eid, src, tgt, props, note in conn.execute("""select e.id, e.source_id, e.target_id, e.props, e.note from kb.edges e
            join kb.nodes t on t.id = e.target_id join kb.node_types tt on tt.id = t.type_id
            where e.archived_at is null and e.edge_type_id = %s and tt.key = 'module'""", (teaches,)).fetchall():
        role = role_of(props)
        if role is None:
            res["teaches_without_role"] += 1            # kept as it is; reported (no role to give it)
            continue
        p = dict(role, converted_from=str(eid), **{k: v for k, v in (props or {}).items() if k in ("tier", "older_role")})
        new = conn.execute("""insert into kb.edges (edge_type_id, source_id, target_id, props, note)
                              values (%s, %s, %s, %s, %s) on conflict do nothing returning id""",
                           (sme, src, tgt, json.dumps(p), note)).fetchone()
        conn.execute("update kb.edges set archived_at = now(), status = 'archived' where id = %s", (eid,))
        before["edges_archived"].append(str(eid))
        if new:
            before["edges_created"].append(str(new[0]))
            res["sme_created"] += 1
    # 4. owner-by-role fields that hold instructors -> must equal the module's SMEs, then cleared
    rows = conn.execute("""select n.id, n.owner_record_id, n.co_owner_record_ids from kb.nodes n
                           where n.owner_record_id is not null or cardinality(n.co_owner_record_ids) > 0""").fetchall()
    for nid, o, co in rows:
        smes = {r[0] for r in conn.execute("""select source_id from kb.edges where edge_type_id = %s and target_id = %s
                                              and archived_at is null""", (sme, nid))}
        missing = [str(x) for x in [o] + list(co or []) if x and x not in smes]
        if missing:
            raise SystemExit(f"refused: {len(missing)} owner-by-role value(s) on a record are not SME assignments; "
                             "nothing was changed (check the data first)")
        before["owner_by_role"].append({"id": str(nid), "owner_record_id": str(o) if o else None,
                                        "co_owner_record_ids": [str(x) for x in co or []]})
        conn.execute("update kb.nodes set owner_record_id = null, co_owner_record_ids = '{}' where id = %s", (nid,))
        res["owner_by_role_cleared"] += 1
    PRIVATE.mkdir(parents=True, exist_ok=True)
    out = PRIVATE / f"run-c-model-before-{label}.json"
    out.write_text(json.dumps(before, indent=1), encoding="utf-8")
    res["before_state_file"] = str(out.relative_to(REPO))
    return res


def revert(conn, label) -> dict:
    _attribute(conn)
    f = PRIVATE / f"run-c-model-before-{label}.json"
    if not f.exists():
        raise SystemExit(f"no before-state file for {label}: nothing to revert")
    b = json.loads(f.read_text(encoding="utf-8"))
    retired = conn.execute("""select r.archived_at is not null from kb.edge_type_rules r join kb.edge_types e on e.id = r.edge_type_id
        join kb.node_types s on s.id = r.source_type_id join kb.node_types t on t.id = r.target_type_id
        where e.key = 'contains' and s.key = 'domain' and t.key = 'module'""").fetchone()
    if retired and retired[0]:
        raise SystemExit("migration 0039 is still applied: run `pipeline/migrate.py down` (0039) first, then revert")
    has_aliases = conn.execute("""select 1 from information_schema.columns where table_schema = 'kb'
                                  and table_name = 'nodes' and column_name = 'search_aliases'""").fetchone()
    res = {"domains_restored": 0, "edges_removed": 0, "edges_restored": 0, "owner_by_role_restored": 0}
    for d in b["domains"]:
        if has_aliases:
            conn.execute("update kb.nodes set name = %s, search_aliases = %s where id = %s", (d["name"], d["search_aliases"] or "", d["id"]))
        else:
            conn.execute("update kb.nodes set name = %s where id = %s", (d["name"], d["id"]))
        res["domains_restored"] += 1
    for s in b.get("scopes_cleared", []):
        conn.execute("update kb.nodes set scope_id = %s where id = %s", (s["scope_id"], s["id"]))
    res["scopes_restored"] = len(b.get("scopes_cleared", []))
    for o in b["owner_by_role"]:
        conn.execute("update kb.nodes set owner_record_id = %s, co_owner_record_ids = %s::uuid[] where id = %s",
                     (o["owner_record_id"], o["co_owner_record_ids"], o["id"]))
        res["owner_by_role_restored"] += 1
    res["before_state_moved_to"] = str(f.with_suffix(".reverted.json").relative_to(REPO))
    if b["edges_created"]:
        res["edges_removed"] = conn.execute("update kb.edges set archived_at = now(), status = 'archived' where id = any(%s::uuid[]) and archived_at is null",
                                            (b["edges_created"],)).rowcount
    if b["edges_archived"]:
        res["edges_restored"] = conn.execute("update kb.edges set archived_at = null, status = 'active' where id = any(%s::uuid[])",
                                             (b["edges_archived"],)).rowcount
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "apply", "revert"))
    ap.add_argument("--db", required=True, help="local | dev")
    a = ap.parse_args()
    url, label = db_url(a.db)
    if PRODUCTION_REF in url:
        print("refused: that is the production database"); return 2
    if label == "other":
        print("refused: use --db local or --db dev"); return 2
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("set statement_timeout = '300s'")
        print("before:", json.dumps(counts(conn)))
        if a.cmd == "plan":
            conn.rollback(); return 0
        t0 = time.monotonic()
        res = (apply if a.cmd == "apply" else revert)(conn, label)
        after = counts(conn)
        conn.commit()
        if a.cmd == "revert":            # only after the revert committed: the next apply may write a new one
            f = PRIVATE / f"run-c-model-before-{label}.json"
            f.replace(f.with_suffix(".reverted.json"))
        print(a.cmd + ":", json.dumps(res))
        print("after: ", json.dumps(after))
        print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
