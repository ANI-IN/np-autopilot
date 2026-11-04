#!/usr/bin/env python3
"""Parity: NP Autopilot's map vs the KB, on the LOCAL real-data copy (:8766).

NP's side is read from NP Autopilot ITSELF: the page at / is opened signed in,
and its own model() and currentInstructors() (public/index.html) are evaluated
in the browser. Per-module sessions, decks and weeks use NP's BY_MODULE
relationships (delivers_session, presented_with, scheduled_in) on the same
tables NP reads. The KB side is read from kb.* (external_id 'np:<id>' ties the
two). Every difference is listed with its reason; an unexplained difference
fails the run (exit 1).

    python eval/kb_parity.py [--write .measure/parity.json]

Output: ids and counts only, never names or values.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8766"
DB = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web")]
from lib.kb.sync import load_mapping                                   # noqa: E402

R = load_mapping()["roles"]          # projection names, from the mapping (checked against the taxonomy)
ROLES = ("primary", "backup_1", "backup_2", "backup_3")
SHORT = {"primary": "P", "backup_1": "B1", "backup_2": "B2", "backup_3": "B3"}

NP_JS = """() => {
  const M = model(), ci = currentInstructors();
  const ids = (a) => a.map((n) => n.id);
  const roles = {};
  for (const e of D.edges) if (e.r === '__TAUGHT_BY__' && e.p && e.p.tier === 'mastersheet')
    (roles[e.s] = roles[e.s] || []).push([e.t, e.p.instructor_role]);
  const legacyMods = D.nodes.filter((n) => n.t === 'module' && n.legacy).length;
  return {
    current_domains: ids(M.current), other_domains: ids(M.other),
    current_modules: Object.fromEntries(M.current.map((d) => [d.id, ids(M.cur.get(d.id) || [])])),
    legacy_modules: legacyMods, unlinked_modules: M.unlinked.length,
    legacy_by_domain: Object.fromEntries(M.domains.map((d) => [d.id, (M.legacy.get(d.id) || []).length])),
    instructors_current: D.nodes.filter((n) => n.t === 'instructor' && ci.has(n.id)).map((n) => n.id),
    instructors_total: D.nodes.filter((n) => n.t === 'instructor').length,
    programmes: D.nodes.filter((n) => n.t === 'program').length,
    people_by_domain: Object.fromEntries(M.domains.map((d) => [d.id, (M.people.get(d.id) || []).length])),
    roles,
  };
}"""


def np_side() -> dict:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        page = b.new_page()
        page.goto(BASE + "/local-login")
        page.fill("#password", "ik-realdata-local")
        page.click("#submit")
        page.wait_for_url("**/kb/**")
        page.goto(BASE + "/")
        page.wait_for_function("() => typeof model === 'function' && typeof D !== 'undefined' && D.nodes && D.nodes.length > 1000"
                               " && D.nodes.some((n) => n.t === 'domain')", timeout=120000)
        page.wait_for_timeout(1500)
        out = page.evaluate(NP_JS.replace("__TAUGHT_BY__", R["teaching_reversed"]))
        b.close()
    return out


def kb_side(c) -> dict:
    q = lambda sql, p=(): c.execute(sql, p).fetchall()                    # noqa: E731
    node = {r[0]: {"id": str(r[1]), "type": r[2], "legacy": r[3], "archived": r[4] is not None,
                   "owner": str(r[5]) if r[5] else None, "co": [str(x) for x in r[6]]}
            for r in q("""select substr(n.external_id, 4), n.id, t.key, n.is_legacy, n.archived_at, n.owner_record_id, n.co_owner_record_ids
                          from kb.nodes n join kb.node_types t on t.id = n.type_id where n.external_id like 'np:%%'""")}
    np_of = {v["id"]: k for k, v in node.items()}
    edges = q("""select e.source_id, e.target_id, et.key, e.props, e.archived_at from kb.edges e
                 join kb.edge_types et on et.id = e.edge_type_id""")
    att = q("""select nr.node_id, nr.note, nr.archived_at from kb.node_resources nr""")
    return {"node": node, "np_of": np_of, "edges": edges, "att": att}


def projection(c) -> dict:
    rows = c.execute("select rel, source_id, target_id from public.edges where rel = any(%s)",
                     ([R["session_link"], R["deck_link"], R["week_link"]],)).fetchall()
    by = defaultdict(lambda: defaultdict(set))
    for rel, s, t in rows:
        by[rel][s].add(t)
    return by


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write")
    a = ap.parse_args()
    NP = np_side()
    c = psycopg.connect(DB)
    K = kb_side(c)
    P = projection(c)
    node, np_of = K["node"], K["np_of"]
    unexplained, rows = [], []

    def cmp(label, np_val, kb_val, why=""):
        ok = np_val == kb_val
        rows.append((label, np_val, kb_val, "same" if ok else why))
        if not ok and not why:
            unexplained.append(label)

    # categories -----------------------------------------------------------
    kb_dom = [k for k, v in node.items() if v["type"] == "domain"]
    cmp("Current domains", len(NP["current_domains"]), sum(1 for k in kb_dom if not node[k]["legacy"]))
    cmp("Legacy domains", len(NP["other_domains"]), sum(1 for k in kb_dom if node[k]["legacy"]))
    cmp("Current domains: same ids", sorted(NP["current_domains"]), sorted(k for k in kb_dom if not node[k]["legacy"]))
    np_cur_mods = sorted({m for v in NP["current_modules"].values() for m in v})
    kb_mod = [k for k, v in node.items() if v["type"] == "module"]
    cmp("Current modules", len(np_cur_mods), sum(1 for k in kb_mod if not node[k]["legacy"]))
    cmp("Current modules: same ids", np_cur_mods, sorted(k for k in kb_mod if not node[k]["legacy"]))
    cmp("Legacy modules", NP["legacy_modules"], sum(1 for k in kb_mod if node[k]["legacy"]))
    kb_ins = [k for k, v in node.items() if v["type"] == "instructor"]
    cmp("Instructors (all)", NP["instructors_total"], len(kb_ins))
    cmp("Current instructors", len(NP["instructors_current"]), sum(1 for k in kb_ins if not node[k]["legacy"]))
    cmp("Current instructors: same ids", sorted(NP["instructors_current"]), sorted(k for k in kb_ins if not node[k]["legacy"]))
    cmp("Programmes (older sheets)", NP["programmes"], sum(1 for v in node.values() if v["type"] == "program" and v["legacy"]))
    # roles ----------------------------------------------------------------
    np_roles = Counter(r for lst in NP["roles"].values() for _, r in lst)
    kb_teach = [(np_of.get(str(s)), np_of.get(str(t)), (p or {}).get("role")) for s, t, k, p, arch in K["edges"] if k == "teaches"]
    kb_roles = Counter(r for _, _, r in kb_teach if r)
    for r in ROLES:
        cmp(f"Role {SHORT[r]} (mastersheet)", np_roles[r], kb_roles[r])
    np_pairs = sorted((i, m, r) for m, lst in NP["roles"].items() for i, r in lst)
    kb_pairs = sorted((s, t, r) for s, t, r in kb_teach if r)
    cmp("Role edges: same (instructor, module, role)", np_pairs, kb_pairs)
    # owners from roles ------------------------------------------------------
    own_ok = 0
    for m, lst in NP["roles"].items():
        lst = sorted(lst, key=lambda x: (ROLES.index(x[1]), x[0]))
        want_o = node[lst[0][0]]["id"] if lst and lst[0][1] == "primary" else None
        if node.get(m) and node[m]["owner"] == want_o:
            own_ok += 1
    cmp("Modules whose owner record = the mastersheet primary", len(NP["roles"]), own_ok)

    # every category: the old tables NP reads vs KB records (rejections explained)
    rej = Counter()
    rep = json.loads((REPO / "backups" / "sync-apply.json").read_text(encoding="utf-8"))
    rej_ids = {r["id"] for r in rep.get("rejected_ids") or []}
    src = Counter(); src_rej = Counter()
    for nid, typ in c.execute("select id, type from public.nodes where not sensitive").fetchall():
        src[typ] += 1
        if nid in rej_ids:
            src_rej[typ] += 1
    kb_by = Counter(np_type for np_type in (c.execute("select type from public.nodes where id = any(%s)", (list(node),)).fetchall()))
    kb_by = Counter(t for (t,) in kb_by.elements())
    for typ in sorted(src):
        if typ in kb_by or src_rej[typ]:
            why = (f"{src_rej[typ]} rejected by the import's shape rules (not_a_topic, an e-mail or URL in the name, empty): listed by id in the run report"
                   if src[typ] - src_rej[typ] == kb_by[typ] and src_rej[typ] else "")
            cmp(f"Records from '{typ}'", src[typ], kb_by[typ], why)
    del rej

    # side by side ----------------------------------------------------------
    live_att = defaultdict(Counter)
    for nid, note, arch in K["att"]:
        if arch is None:
            live_att[str(nid)][note] += 1
    contains = defaultdict(lambda: defaultdict(int))
    for s, t, k, p, arch in K["edges"]:
        if k == "contains" and arch is None:
            tn = np_of.get(str(t))
            if tn:
                contains[str(s)][node[tn]["type"]] += 1
    side_dom = []
    for d in NP["current_domains"]:
        kd = node[d]
        side_dom.append({"np_id": d, "kb_id": kd["id"],
                         "np_current_modules": len(NP["current_modules"][d]), "kb_current_modules": sum(
                             1 for m in NP["current_modules"][d] if m in node and not node[m]["legacy"]),
                         "kb_contains_modules": contains[kd["id"]]["module"],
                         "np_people": NP["people_by_domain"][d], "kb_owner": 1 if kd["owner"] else 0, "kb_backups": len(kd["co"]),
                         "np_legacy_modules_via_programmes": NP["legacy_by_domain"][d]})
    side_mod = []
    for m in np_cur_mods[:10]:
        km = node[m]
        roles = sorted(NP["roles"].get(m, []), key=lambda x: (ROLES.index(x[1]), x[0]))   # = the engine's order
        side_mod.append({"np_id": m, "kb_id": km["id"],
                         "np_sessions": len(P[R["session_link"]].get(m, ())), "kb_sessions": contains[km["id"]]["session"],
                         "np_decks": len(P[R["deck_link"]].get(m, ())), "kb_decks": live_att[km["id"]]["Slides"],
                         "np_weeks": len(P[R["week_link"]].get(m, ())), "kb_weeks": contains[km["id"]]["week"],
                         "np_roles": " ".join(SHORT[r] for _, r in roles),
                         "kb_owner_is_P": bool(roles and roles[0][1] == "primary" and km["owner"] == node[roles[0][0]]["id"]),
                         "kb_backups": len(km["co"])})
    for s in side_mod:
        for k in ("sessions", "decks", "weeks"):
            if s["np_" + k] != s["kb_" + k]:
                unexplained.append(f"module {s['np_id']} {k}")
    for s in side_dom:
        if s["np_current_modules"] != s["kb_current_modules"]:
            unexplained.append(f"domain {s['np_id']} modules")

    # archive state ------------------------------------------------------------
    arch = Counter(v["type"] for v in node.values() if v["archived"])
    res = {"rows": rows, "domains": side_dom, "modules": side_mod, "archived": dict(arch), "unexplained": unexplained}
    for label, a_, b_, why in rows:
        show = lambda x: (f"{len(x)} ids" if isinstance(x, list) else x)       # noqa: E731
        print(f"{'OK ' if why == 'same' else 'DIFF'} {label}: NP {show(a_)} | KB {show(b_)}" + ("" if why == "same" else f" ({why or 'UNEXPLAINED'})"))
    print("current domains side by side:", json.dumps(side_dom))
    print("10 current modules side by side:", json.dumps(side_mod))
    print("archived by the legacy step (by type):", dict(arch))
    print("UNEXPLAINED:", unexplained or "none")
    if a.write:
        Path(a.write).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return 1 if unexplained else 0


if __name__ == "__main__":
    sys.exit(main())
