#!/usr/bin/env python3
"""Run 5 proof of the sync on the LOCAL real-data copy (:8766), end to end
through the app's own routes (POST /api/kb/sync/run = "Sync now"):

  1. change a row at the source (a current session's label)    -> updated
  2. add a row (a made-up session under a current module)       -> created
  3. remove a row (a topic, with its edges)                     -> flagged "removed at source", not deleted
  4. edit a record in the app, then change it at the source     -> conflict, the app edit kept
  5. put every source row back, undo the app edit, Sync now      -> back to the start (conflict cleared,
                                                                  removed row restored; the made-up row
                                                                  stays flagged "removed at source")
Prints ids and counts only. Writes only to kb_realdata (local).
"""
from __future__ import annotations

import json
import sys
import urllib.request

import psycopg

sys.path[:0] = [str(__import__("pathlib").Path(__file__).resolve().parents[1]), str(__import__("pathlib").Path(__file__).resolve().parents[1] / "web")]
from lib.kb.sync import load_mapping                                   # noqa: E402

R = load_mapping()["roles"]          # projection names, from the mapping (checked against the taxonomy)
BASE = "http://127.0.0.1:8766"
DB = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
PROOF_ID = "ses_0000000000c0ffee"          # matches public.nodes id_shape; made up


def token() -> str:
    req = urllib.request.Request(BASE + "/local-login/session", method="POST", headers={"content-type": "application/json"},
                                 data=json.dumps({"email": "realdata-admin@interviewkickstart.com", "password": "ik-realdata-local"}).encode())
    return json.load(urllib.request.urlopen(req))["access_token"]


def api(tok, method, path, body=None):
    req = urllib.request.Request(BASE + "/api/kb" + path, method=method,
                                 headers={"authorization": "Bearer " + tok, "content-type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        return json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path}: HTTP {e.code}")


def sync_now(tok, label):
    r = api(tok, "POST", "/sync/run", {})
    keep = {k: r.get(k) for k in ("status", "partial", "created", "updated", "conflicts", "removed_at_source",
                                  "restored_at_source", "conflicts_cleared", "seconds")}
    print(f"[{label}] Sync now:", json.dumps(keep))
    if r.get("status") != "ok" or r.get("partial"):
        raise SystemExit("sync did not finish")
    return r


def main() -> int:
    c = psycopg.connect(DB, autocommit=True)
    def q(sql, p=()):
        cur = c.execute(sql, p)
        return cur.fetchall() if cur.description else []
    # an interrupted earlier run: undo its source changes first
    for suffix in (" (renamed at source)", " (changed at source)"):
        q("update public.nodes set label = left(label, length(label) - %s) where right(label, %s) = %s", (len(suffix), len(suffix), suffix))
    q("delete from public.edges where target_id = %s", (PROOF_ID,))
    q("delete from public.nodes where id = %s", (PROOF_ID,))
    kb = lambda np: q("select id, name, version, review_status, archived_at from kb.nodes where external_id = %s", ("np:" + np,))  # noqa: E731
    # pick rows by id (first current module with sessions; a topic with no other ties)
    mod = q("""select e.source_id from public.edges e join public.nodes m on m.id = e.source_id
               where e.rel = %s and m.props ? 'domain_slug' order by 1 limit 1""", (R["session_link"],))[0][0]
    ses_a, ses_b = [r[0] for r in q("select distinct target_id from public.edges where rel = %s and source_id = %s and target_id <> %s order by 1 limit 2", (R["session_link"], mod, PROOF_ID))]
    topic = q("""select n.id from public.nodes n where n.type = %s and not coalesce((n.props->>'not_a_topic') is not null, false)
                 and exists (select 1 from kb.nodes k where k.external_id = 'np:' || n.id and k.archived_at is null)
                 order by n.id limit 1""", (R["topic"],))[0][0]
    print("rows used (ids):", {"module": mod, "changed": ses_a, "conflict": ses_b, "removed": topic, "added": PROOF_ID})
    saved = {"a": q("select label from public.nodes where id = %s", (ses_a,))[0][0],
             "b": q("select label from public.nodes where id = %s", (ses_b,))[0][0],
             "topic": q("select id, type, label, props, sensitive from public.nodes where id = %s", (topic,))[0],
             "topic_edges": q("select rel, source_id, target_id, props from public.edges where source_id = %s or target_id = %s", (topic, topic))}
    tok = token()
    sync_now(tok, "0 baseline")
    # 1-4 ------------------------------------------------------------------------
    q("update public.nodes set label = label || ' (renamed at source)' where id = %s", (ses_a,))
    q("insert into public.nodes (id, type, label, props, sensitive) values (%s, %s, 'Sync proof session', '{}', false)", (PROOF_ID, R["session"]))
    q("insert into public.edges (rel, source_id, target_id, props) values (%s, %s, %s, '{}')", (R["session_link"], mod, PROOF_ID))
    q("delete from public.edges where source_id = %s or target_id = %s", (topic, topic))
    q("delete from public.node_sources where node_id = %s", (topic,))
    q("delete from public.nodes where id = %s", (topic,))
    kid, _, ver, _, _ = kb(ses_b)[0]
    api(tok, "PATCH", f"/nodes/{kid}", {"version": ver, "name": saved["b"] + " (edited in the app)"})
    q("update public.nodes set label = label || ' (changed at source)' where id = %s", (ses_b,))
    r = sync_now(tok, "1-4 change/add/remove/conflict")
    checks = {
        "changed row applied": kb(ses_a)[0][1].endswith("(renamed at source)"),
        "added row created": bool(kb(PROOF_ID)),
        "removed row kept, flagged": bool(kb(topic)) and kb(topic)[0][4] is None and kb(topic)[0][3] == "needs_review"
        and q("select removed_at is not null from kb.sync_map where unit = 'record' and key = %s", (topic,))[0][0],
        "app edit kept": kb(ses_b)[0][1].endswith("(edited in the app)"),
        "conflict flagged": q("select conflict_at is not null from kb.sync_map where unit = 'record' and key = %s", (ses_b,))[0][0],
    }
    att = api(tok, "GET", "/counts")["attention"]["counts"]
    checks["Data quality shows them"] = att["sync_conflicts"] >= 1 and att["removed_at_source"] >= 1
    checks["Activity says Sync"] = any(x["actor_label"].startswith("Sync") for x in api(tok, "GET", "/activity?source=sync")["items"])
    print("checks after 1-4:", checks)
    # 5: undo --------------------------------------------------------------------------
    q("update public.nodes set label = %s where id = %s", (saved["a"], ses_a))
    q("update public.nodes set label = %s where id = %s", (saved["b"], ses_b))
    t = saved["topic"]
    q("insert into public.nodes (id, type, label, props, sensitive) values (%s, %s, %s, %s, %s)",
      (t[0], t[1], t[2], json.dumps(t[3]), t[4]))
    for rel, s, tg, p in saved["topic_edges"]:
        q("insert into public.edges (rel, source_id, target_id, props) values (%s, %s, %s, %s)", (rel, s, tg, json.dumps(p)))
    q("delete from public.edges where target_id = %s", (PROOF_ID,))
    q("delete from public.nodes where id = %s", (PROOF_ID,))
    kid, _, ver, _, _ = kb(ses_b)[0]
    api(tok, "PATCH", f"/nodes/{kid}", {"version": ver, "name": saved["b"]})
    sync_now(tok, "5 undo")
    back = {"changed row back": not kb(ses_a)[0][1].endswith("(renamed at source)"),
            "conflict cleared": not q("select conflict_at is not null from kb.sync_map where unit = 'record' and key = %s", (ses_b,))[0][0],
            "removed row restored": not q("select removed_at is not null from kb.sync_map where unit = 'record' and key = %s", (topic,))[0][0],
            "made-up row flagged removed (never deleted)": bool(kb(PROOF_ID))}
    print("checks after 5:", back)
    ok = all(checks.values()) and all(back.values())
    print("PROOF:", "PASS" if ok else "FAIL")
    del r
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
