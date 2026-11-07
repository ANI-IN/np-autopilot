#!/usr/bin/env python3
"""Write the KYP curriculum (pipeline/kb_kyp_extract.py) into the knowledge base.

    python pipeline/kb_import_curriculum.py plan  --db local|dev [--in .measure/kyp-c/curriculum.json]
    python pipeline/kb_import_curriculum.py apply --db local|dev

Owner decisions 2026-11-07 (run C): KYPs are the primary reference for curriculum structure. In scope:
the four domains (Fullstack, Backend, Frontend, Test). Agentic AI, EdgeUp and other combined programs are
deferred and never written here.

What it writes, all attributed to actor 'import', every record and relationship carrying its provenance
(props.provenance: Confluence page id, version, heading, table, row):
  program --contains (order, optional program-specific schedule)--> course --contains (order, schedule)-->
  module --contains (order)--> topic;  program/course/module --in_domain--> domain;
  module variant --variant_of--> canonical module;  instructor --teaches {role: listed instructor}--> program;
  resources (live links found on the pages) attached to their program.

Idempotent. A record is found again by props.kyp_key. An existing record with the same name and type is
UPDATED, not duplicated (for example the modules NP Autopilot already had): it keeps its id, its other
relationships and its SME assignments, and gains the KYP provenance. Modules are reusable: an identical
module (same title and topics) in several programs is one record; same title with other topics is a variant
scoped to the course it first appears in. A record this tool created earlier that is no longer in the KYPs
is reported ("removed at source") and flagged for review, never deleted by this tool.

Never prints connection details. Refuses the production project.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402

LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"


def db_url(which: str) -> str:
    if which == "local":
        return LOCAL
    if which == "dev":
        from dotenv import dotenv_values
        url = dotenv_values(REPO / ".env").get("DEV_SUPABASE_DB_URL") or ""
        if not url:
            sys.exit("DEV_SUPABASE_DB_URL is not set")
        return url
    if which.startswith("postgresql://postgres:postgres@127.0.0.1"):
        return which                     # a local test database (the test suite)
    sys.exit("use --db local or --db dev")


class Importer:
    def __init__(self, conn, data: dict):
        self.c, self.D = conn, data
        self.stats = Counter()
        self.T = {k: i for k, i in conn.execute("select key, id from kb.node_types where archived_at is null")}
        self.E = {k: i for k, i in conn.execute("select key, id from kb.edge_types where archived_at is null")}
        for need in ("program", "course", "module", "topic", "domain", "instructor"):
            if need not in self.T:
                sys.exit(f"record type {need!r} is missing")
        for need in ("contains", "in_domain", "variant_of", "teaches"):
            if need not in self.E:
                sys.exit(f"relationship type {need!r} is missing: apply migration 0039 first")
        self.ids: dict[str, str] = {}          # kyp key -> node id
        self.touched: set[str] = set()

    # ---------------- records ----------------
    def node(self, kyp_key: str, tkey: str, name: str, *, scope=None, props=None, adopt=True) -> str:
        props = dict(props or {}, kyp_key=kyp_key)
        tid = self.T[tkey]
        row = self.c.execute("select id, props, name, is_legacy from kb.nodes where type_id = %s and props->>'kyp_key' = %s and archived_at is null",
                             (tid, kyp_key)).fetchone()
        if row is None and adopt:
            row = self.c.execute("""select id, props, name, is_legacy from kb.nodes where type_id = %s and archived_at is null
                                    and name_norm = kb.norm(%s) and coalesce(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)
                                        = coalesce(%s::uuid, '00000000-0000-0000-0000-000000000000'::uuid)""",
                                 (tid, name, scope)).fetchone()
            if row is not None:
                self.stats[f"{tkey}_adopted"] += 1
        if row is None:
            nid = self.c.execute("""insert into kb.nodes (type_id, name, scope_id, props, external_id)
                                    values (%s, %s, %s, %s, %s) returning id""",
                                 (tid, name[:300], scope, json.dumps(props), kyp_key[:200])).fetchone()[0]
            self.stats[f"{tkey}_created"] += 1
        else:
            nid, old, oldname, legacy = row
            merged = dict(old or {})
            merged.update(props)
            # a record a current KYP states is current, whatever the older sheets said (is_legacy off)
            if merged != (old or {}) or oldname != name[:300] or legacy:
                self.c.execute("update kb.nodes set props = %s, name = %s, is_legacy = false where id = %s",
                               (json.dumps(merged), name[:300], nid))
                self.stats[f"{tkey}_updated"] += 1
                if legacy:
                    self.stats[f"{tkey}_legacy_flag_cleared"] += 1
            else:
                self.stats[f"{tkey}_unchanged"] += 1
        nid = str(nid)
        self.ids[kyp_key] = nid
        self.touched.add(nid)
        return nid

    def edge(self, ekey: str, src: str, tgt: str, *, props=None, position=None):
        eid = self.E[ekey]
        props = props or {}
        row = self.c.execute("select id, props, position from kb.edges where edge_type_id = %s and source_id = %s and target_id = %s and archived_at is null",
                             (eid, src, tgt)).fetchone()
        if row is None:
            self.c.execute("insert into kb.edges (edge_type_id, source_id, target_id, props, position) values (%s, %s, %s, %s, %s)",
                           (eid, src, tgt, json.dumps(props), position))
            self.stats[f"edge_{ekey}_created"] += 1
        else:
            merged = dict(row[1] or {})
            merged.update(props)
            if merged != (row[1] or {}) or (position is not None and row[2] != position):
                self.c.execute("update kb.edges set props = %s, position = coalesce(%s, position) where id = %s",
                               (json.dumps(merged), position, row[0]))
                self.stats[f"edge_{ekey}_updated"] += 1
            else:
                self.stats[f"edge_{ekey}_unchanged"] += 1

    def resource(self, url: str, title: str | None, node_id: str, prov: dict):
        row = self.c.execute("select id from kb.resources where url_norm = kb.norm_url(%s) and archived_at is null", (url,)).fetchone() \
            if self._has_norm_url() else self.c.execute("select id from kb.resources where url = %s and archived_at is null", (url,)).fetchone()
        if row is None:
            rid = self.c.execute("insert into kb.resources (url, title, kind) values (%s, %s, %s) returning id",
                                 (url, (title or url)[:300], self._kind(url))).fetchone()[0]
            self.stats["resource_created"] += 1
        else:
            rid = row[0]
            self.stats["resource_reused"] += 1
        if not self.c.execute("select 1 from kb.node_resources where node_id = %s and resource_id = %s and archived_at is null",
                              (node_id, rid)).fetchone():
            self.c.execute("insert into kb.node_resources (node_id, resource_id, note) values (%s, %s, %s)",
                           (node_id, rid, f"Linked from the KYP ({prov.get('heading') or 'page'})"[:500]))
            self.stats["resource_attached"] += 1

    _norm_url = None

    def _has_norm_url(self):
        if self._norm_url is None:
            self._norm_url = bool(self.c.execute("select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'kb' and p.proname = 'norm_url'").fetchone())
        return self._norm_url

    @staticmethod
    def _kind(url: str) -> str:
        if "/folders/" in url:
            return "folder"
        if "/document/" in url:
            return "doc"
        if "/presentation/" in url:
            return "slides"
        if "/spreadsheets/" in url:
            return "sheet"
        return "other"

    # ---------------- run ----------------
    def run(self):
        D = self.D
        dom = {n: str(i) for i, n in self.c.execute("""select n.id, n.name from kb.nodes n where n.type_id = %s and n.archived_at is null""",
                                                    (self.T["domain"],))}
        missing = {p["domain"] for p in D["programs"]} - set(dom)
        if missing:
            sys.exit(f"domains missing (run scripts/curriculum_model_data.py apply first): {sorted(missing)}")
        prog_name = {}
        for p in D["programs"]:
            pid = self.node(p["key"], "program", p["name"], props={
                "family": p["family"], "provenance": [p["provenance"]] + p.get("also_from", []),
                **({"weekly_cadence": p["attributes"]["weekly_cadence"]} if p["attributes"].get("weekly_cadence") else {})})
            prog_name[p["key"]] = p["name"]
            self.edge("in_domain", pid, dom[p["domain"]], props={"provenance": p["provenance"]})
        # courses: program courses scoped to their program; reusable domain courses unscoped
        for c in D["courses"]:
            scope = self.ids.get(c["program"]) if c.get("program") else None
            cid = self.node(c["key"], "course", c["name"], scope=scope,
                            props={"provenance": [c["provenance"]], **({"reusable": True} if c.get("reusable") else {})})
            if c.get("domain"):
                self.edge("in_domain", cid, dom[c["domain"]], props={"provenance": c["provenance"]})
        for pc in D["program_courses"]:
            c = next(x for x in D["courses"] if x["key"] == pc["course"])
            sched = [s for s in (c.get("schedule_rows") or []) if s]
            props = {"provenance": pc["provenance"]}
            if sched:
                props["schedule"] = {"program": prog_name[pc["program"]], "rows": sched}
            self.edge("contains", self.ids[pc["program"]], self.ids[pc["course"]], props=props, position=pc["order"])
        # modules: canonical first (unscoped, adopt existing by name), then variants scoped to their first course
        first_container = {}
        for pl in D["placements"]:
            first_container.setdefault(pl["module"], pl.get("course") or pl.get("program"))
        canon = [m for m in D["modules"] if not m.get("variant_of")]
        variants = [m for m in D["modules"] if m.get("variant_of")]
        for m in canon + variants:
            scope = self.ids[first_container[m["key"]]] if m.get("variant_of") else None
            mid = self.node(m["key"], "module", m["name"], scope=scope,
                            props={"provenance": m["provenance"][:20], "content_sig": m["content_sig"]})
            for d in m["domains"]:
                if len(m["domains"]) == 1:
                    self.edge("in_domain", mid, dom[d], props={"provenance": m["provenance"][0]})
            if m.get("variant_of"):
                self.edge("variant_of", mid, self.ids[m["variant_of"]], props={"provenance": m["provenance"][0],
                                                                                 "reason": "same title, different topics"})
        topics_by_module = {}
        for t in D["topics"]:
            topics_by_module.setdefault(t["module"], []).append(t)
        for mk, ts in topics_by_module.items():
            mid = self.ids[mk]
            for t in ts:
                tid = self.node(t["key"], "topic", t["name"], scope=mid, props={"provenance": [t["provenance"]]})
                self.edge("contains", mid, tid, props={"provenance": t["provenance"]}, position=t["order"])
        for pl in D["placements"]:
            src = self.ids[pl.get("course") or pl.get("program")]
            props = {"provenance": pl["provenance"]}
            sched = pl.get("schedule_rows") or ([pl["schedule"]] if pl.get("schedule") else [])
            sched = [s for s in sched if s and any(v for k, v in s.items() if k != "label") or (s and s.get("label"))]
            if sched:
                owner_prog = pl.get("program") or next((x["program"] for x in D["courses"] if x["key"] == pl.get("course")), None)
                props["schedule"] = {"program": prog_name.get(owner_prog), "rows": sched}
            self.edge("contains", src, self.ids[pl["module"]], props=props, position=pl["order"])
        # listed instructors (program level; the KYPs do not map them to modules)
        listed = {}
        for i in D["instructors"]:
            listed.setdefault(i["name"], []).append(i)
        for name, rows in sorted(listed.items()):
            iid = self.node("kyp:instructor:" + re.sub(r"[^a-z0-9]+", "-", name.lower()), "instructor", name,
                            props={"provenance": [r["provenance"] for r in rows]})
            for i in rows:
                self.edge("teaches", iid, self.ids[i["program"]], props={"role": "listed instructor", "provenance": i["provenance"]})
        for r in D["resources"]:
            self.resource(r["url"], r.get("title"), self.ids[r["program"]], r["provenance"])
        # removed at source: records this tool created before that the KYPs no longer have
        gone = self.c.execute("""select id from kb.nodes where archived_at is null and props ? 'kyp_key'
                                 and not (id = any(%s::uuid[]))""", (list(self.touched),)).fetchall()
        for (gid,) in gone:
            self.c.execute("""update kb.nodes set review_status = 'needs_review',
                              props = props || jsonb_build_object('removed_at_source', now()::text) where id = %s""", (gid,))
        self.stats["removed_at_source_flagged"] = len(gone)
        return dict(sorted(self.stats.items()))


def counts(conn) -> dict:
    return dict(conn.execute("""select t.key, count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
                                where n.archived_at is null group by 1 order by 1""").fetchall())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "apply"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--in", dest="inp", default=str(REPO / ".measure" / "kyp-c" / "curriculum.json"))
    a = ap.parse_args()
    url = db_url(a.db)
    if PRODUCTION_REF in url:
        print("refused: that is the production database"); return 2
    data = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("set statement_timeout = '600s'")
        conn.execute("select set_config('kb.actor_type', 'import', true), set_config('kb.actor_id', '', true), "
                     "set_config('request.jwt.claims', '', true), set_config('kb.operator', 'on', true)")
        before = counts(conn)
        t0 = time.monotonic()
        res = Importer(conn, data).run()
        after = counts(conn)
        print("before:", json.dumps(before))
        print(a.cmd + ":", json.dumps(res))
        print("after: ", json.dumps(after))
        if a.cmd == "plan":
            conn.rollback()
            print("plan only: rolled back")
        else:
            conn.commit()
        print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
