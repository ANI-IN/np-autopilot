#!/usr/bin/env python3
"""Migrate the existing projection (public.nodes / edges / node_sources /
node_layout / people / workflow_owners / domain_aliases ...) into the KB
(`kb` schema). docs/MIGRATION_MAPPING.md is the mapping; this is its code.

    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_import_projection.py preview --as <admin email> [--report out.json]
    SUPABASE_DB_URL_SESSION=<db> python pipeline/kb_import_projection.py apply   --as <admin email> [--report out.json]

- ONE transaction. `preview` runs every step and ROLLS BACK, printing what
  apply would do; `apply` commits the same work.
- Idempotent: every record, link and relationship carries
  external_id = 'np:<projection id>'; a re-run creates nothing that exists.
- Never overwrites an edit made in the app: an existing record is refreshed
  only while its version still equals the version the import left
  (imported_version); otherwise it is counted as "kept (edited in the app)".
- The database's own rules apply (types, fields, relationship rules, names):
  the import writes through the kb tables and their triggers, attributed to
  the named admin with actor_type 'import' (Activity shows "Import (run by …)").
- Output: counts and record ids only. No names, no values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# pipeline/lib would shadow web/lib (the KB service), as in kb_import_sheets.py.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO / "pipeline"]
sys.path[:0] = [str(REPO), str(REPO / "web")]

# ---------------------------------------------------------------------------- the mapping
# Lives in config/kb-projection-mapping.yaml: it names taxonomy types, and
# config/taxonomy.yaml is their single source, so the names are checked
# against the taxonomy here instead of being written as literals in code.
MAPPING_FILE = REPO / "config" / "kb-projection-mapping.yaml"


def load_mapping() -> dict:
    import yaml
    from pipeline.lib import taxonomy
    m = yaml.safe_load(MAPPING_FILE.read_text(encoding="utf-8"))
    ntypes, etypes = set(taxonomy.node_type_names()), set(taxonomy.edge_type_names())
    named_types = set(m["types"]) | set(m["artifacts"]) | set(m["artifact_kind"]) | set(m["mapped_props"])
    named_types |= {r[k] for r in m["relationships"] + m["attachments"] for k in ("source", "target")}
    named_types |= {m["roles"][k] for k in ("topic", "person", "workflow")}
    named_rels = {r["rel"] for r in m["relationships"] + m["attachments"]} | set(m["roles"]["placement"])
    named_rels |= {m["roles"][k] for k in ("week_link", "teaching", "teaching_reversed")}
    bad = sorted(named_types - ntypes) + sorted(named_rels - etypes)
    if bad:
        raise SystemExit(f"{MAPPING_FILE.name} names what config/taxonomy.yaml does not define: {', '.join(bad)}")
    return m


M = load_mapping()
TYPE_MAP = M["types"]
ARTIFACTS = tuple(M["artifacts"])
ARTIFACT_KIND = M["artifact_kind"]
ROLE = M["roles"]
EDGE_MAP = {(r["rel"], r["source"], r["target"]): (r["kb"], bool(r.get("flip"))) for r in M["relationships"]}
ATTACH_MAP = {(r["rel"], r["source"], r["target"]): ("source" if r["record"] == "source" else "target",
                                                      "target" if r["record"] == "source" else "source", r["note"])
              for r in M["attachments"]}

NEW_TYPES = [
    {"key": "team_member", "label": "Team member", "plural": "Team members", "icon": "users", "color": "#475569",
     "description": "An IK team member named in the corpus (owner, supporter or deliverer of a domain or process).",
     "fields": [{"label": "Team", "kind": "short_text"}, {"label": "Title", "kind": "short_text"},
                {"label": "Seniority", "kind": "short_text"}, {"label": "Also known as", "kind": "long_text"}]},
    {"key": "theme", "label": "Theme", "plural": "Themes", "icon": "shapes", "color": "#0e7490",
     "description": "A group of operational processes (workflows).", "fields": [{"label": "Theme id", "kind": "short_text"}]},
]
TYPE_FIELDS = {   # built-in types gain these fields (additive, safe)
    "program": [{"label": "Family", "kind": "short_text"}, {"label": "Document type", "kind": "short_text"}],
    "domain": [{"label": "Cadence", "kind": "short_text"}, {"label": "Stage", "kind": "short_text"},
               {"label": "Also known as", "kind": "long_text"}],
    "module": [{"label": "Granularity", "kind": "short_text"}, {"label": "Sequence", "kind": "short_text"}],
    "session": [{"label": "Session kind", "kind": "short_text"}, {"label": "Resource type", "kind": "short_text"}],
    "week": [{"label": "Week number", "kind": "number"}],
    "process": [{"label": "Workflow id", "kind": "short_text"}, {"label": "Effort", "kind": "short_text"},
                {"label": "Steps", "kind": "long_text"}, {"label": "Alerts", "kind": "long_text"},
                {"label": "Tools", "kind": "long_text"}, {"label": "Suggested owner", "kind": "short_text",
                                                          "help": "Unconfirmed suggestion from the workflow-owner sheet; not an owner."}],
}
NEW_EDGES = M["new_relationship_types"]
PLACEMENT = {"process": ["theme"], "week": ["module", "course"]}   # allowed_parents additions

UNMAPPED_TABLES = {
    "edges.props": "per-edge evidence (rank, sources, slide, deck_drive_url, provenance, tier, page...); one KB relationship per pair. Kept: teaches role and class dates (relationship note).",
    "profiles": "sign-in accounts of the original site; KB roles are granted separately (pipeline/kb_admins.py). Every profile already reads the KB as a viewer.",
    "shared_accounts": "auth control of the original site",
    "auth_hook_refusals": "auth log of the original site (0 rows)",
    "curation_audit": "audit log of the original curation tools (0 rows)",
    "projection_meta": "build metadata of the projection",
    "np_schema_migrations": "migration bookkeeping",
    "node_types": "the projection's own type list (mapped through TYPE_MAP)",
    "edge_rels": "the projection's own relationship list (mapped through EDGE_MAP / ATTACH_MAP)",
    "files": "the citation registry: its Drive URLs reach the KB through the artifact records that cite them",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _mime_kind(m: str | None) -> str:
    m = m or ""
    if m.startswith("video/") or m == "image/x-quicktime":
        return "video"
    if m.startswith("audio/"):
        return "recording"
    if "presentation" in m or "keynote" in m:
        return "slides"
    if "spreadsheet" in m or m == "text/csv":
        return "sheet"
    if m == "application/pdf":
        return "pdf"
    if "document" in m or m in ("text/plain", "text/markdown"):
        return "doc"
    return "other"


def _text(v) -> str | None:
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, list):
        return "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in v)[:20000]
    return str(v)[:20000] if not isinstance(v, (dict,)) else json.dumps(v, ensure_ascii=False)[:20000]


# ---------------------------------------------------------------------------- run
def run(conn, admin_email: str, apply: bool) -> dict:
    from lib.kb import typedefs as td
    from lib.kb.service import Actor
    q = lambda sql, p=(): conn.execute(sql, p).fetchall()                 # noqa: E731
    rep: dict = {"mode": "apply" if apply else "preview", "read": {}, "created": Counter(), "existing": Counter(),
                 "kept_app_edits": Counter(), "merged": Counter(), "rejected": [], "unmapped_columns": {},
                 "unmapped_tables": UNMAPPED_TABLES, "links": {}, "problems": {}}
    admin = q("select p.user_id from public.profiles p join kb.memberships m on m.user_id = p.user_id "
              "where lower(p.email) = lower(%s) and m.role = 'admin' and m.archived_at is null", (admin_email,))
    if not admin:
        raise SystemExit("--as must name a KB admin (pipeline/kb_admins.py, or eval/kb_realdata_db.py admin locally)")
    uid = str(admin[0][0])
    # Attribution: the admin, as an IMPORT (kb.actor_id() falls back to this GUC
    # when there is no verified JWT; the type service checks the admin role).
    conn.execute("select set_config('request.jwt.claims', %s, true), set_config('kb.actor_type', 'import', true), "
                 "set_config('kb.actor_id', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}), uid))

    # 1. configuration (idempotent) ------------------------------------------------
    types = {t["key"]: t for t in td.all_types(conn, include_archived=True)["node_types"]}
    for nt in NEW_TYPES:
        if nt["key"] not in types:
            body = {k: v for k, v in nt.items() if k != "key"}
            td.create_node_type(conn, Actor(uid, "human"), body, approved=True)
            rep["created"]["record type"] += 1
    types = {t["key"]: t for t in td.all_types(conn, include_archived=True)["node_types"]}
    for key, fields in TYPE_FIELDS.items():
        t = types[key]
        have = {f["key"] for f in t["fields"]}
        add = [f for f in fields if td.slug(f["label"]) not in have]
        parents = sorted(set(t.get("allowed_parents") or []) | set(PLACEMENT.get(key, [])))
        if add or parents != sorted(t.get("allowed_parents") or []):
            td.update_node_type(conn, Actor(uid, "human"), key, {"version": t["version"], "fields": t["fields"] + add,
                                                                   "allowed_parents": parents}, approved=True)
            rep["created"]["field"] += len(add)
    for key in PLACEMENT:
        if key not in TYPE_FIELDS:
            t = {x["key"]: x for x in td.all_types(conn, include_archived=True)["node_types"]}[key]
            parents = sorted(set(t.get("allowed_parents") or []) | set(PLACEMENT[key]))
            if parents != sorted(t.get("allowed_parents") or []):
                td.update_node_type(conn, Actor(uid, "human"), key, {"version": t["version"], "allowed_parents": parents}, approved=True)
    ekeys = {e["key"] for e in td.all_types(conn, include_archived=True)["edge_types"]}
    for et in NEW_EDGES:
        if et["key"] not in ekeys:
            td.create_edge_type(conn, Actor(uid, "human"), dict(et), approved=True)
            rep["created"]["relationship type"] += 1
    types = {t["key"]: t for t in td.all_types(conn)["node_types"]}
    type_id = {k: t["id"] for k, t in types.items()}
    edge_type_id = {e["key"]: e["id"] for e in td.all_types(conn)["edge_types"]}
    rules = {(r["source"], r["target"], e["key"]) for e in td.all_types(conn)["edge_types"] for r in e["rules"]}

    # 2. read the projection -------------------------------------------------------------
    nodes = {r[0]: {"id": r[0], "type": r[1], "label": r[2], "props": r[3] or {}}
             for r in q("select id, type, label, props from public.nodes where not sensitive")}
    edges = q("select id, rel, source_id, target_id from public.edges order by id")
    # The projection keeps one edge row per piece of evidence (6,271 covers_topic
    # rows are 2,770 pairs). One KB relationship per pair; for "teaches" the
    # role and class dates of every row become the relationship's note.
    edge_note = defaultdict(lambda: {"role": set(), "dates": set()})
    for eid, rel, s_, t_, p in q("select id, rel, source_id, target_id, props from public.edges where rel in (%s, %s)",
                                 (ROLE["teaching"], ROLE["teaching_reversed"])):
        k = (s_, t_) if rel == ROLE["teaching"] else (t_, s_)
        if (p or {}).get("role"):
            edge_note[k]["role"].add(str(p["role"]))
        for d in (p or {}).get("class_dates") or []:
            edge_note[k]["dates"].add(str(d))
    rep["read"] = {t: n for t, n in q("""select 'nodes', count(*) from public.nodes union all select 'edges', count(*) from public.edges
        union all select 'node_sources', count(*) from public.node_sources union all select 'node_layout', count(*) from public.node_layout
        union all select 'people', count(*) from public.people union all select 'people_aliases', count(*) from public.people_aliases
        union all select 'workflow_owners', count(*) from public.workflow_owners union all select 'domain_aliases', count(*) from public.domain_aliases
        union all select 'curation_notes', count(*) from public.curation_notes union all select 'files', count(*) from public.files
        union all select 'profiles', count(*) from public.profiles""")}
    rep["read"]["nodes (sensitive, not read)"] = q("select count(*) from public.nodes where sensitive")[0][0]
    people = {r[0]: r for r in q("select canonical, team, title, seniority from public.people")}
    aliases = defaultdict(list)
    for a, c in q("select alias, canonical from public.people_aliases"):
        aliases[c].append(a)
    dom_alias = defaultdict(list)
    for a, d in q("select alias, domain from public.domain_aliases"):
        dom_alias[_norm(d)].append(a)
    wf_owner = {str(r[0]): r[1] for r in q("select workflow_id, suggestion from public.workflow_owners where suggestion is not null")}

    # 3. plan records: reject, merge, scope, unique names ------------------------------------
    used_keys = defaultdict(set)
    reject = lambda nid, why: rep["rejected"].append({"id": nid, "reason": why})   # noqa: E731
    recs: dict[str, dict] = {}     # canonical np id -> record plan
    alias_of: dict[str, str] = {}  # np id -> canonical np id (merges)
    topic_groups = defaultdict(list)
    for n in nodes.values():
        if n["type"] not in TYPE_MAP:
            continue
        p = n["props"]
        if n["type"] == ROLE["topic"]:
            if p.get("not_a_topic"):
                reject(n["id"], f"marked not_a_topic ({p['not_a_topic']}) by the pipeline: a person, not a topic")
                continue
        lab = (n["label"] or "").strip()
        if not lab:
            reject(n["id"], "empty name"); continue
        if "@" in lab or re.search(r"https?://", lab, re.I):
            reject(n["id"], "name contains an e-mail address or a URL (KB names may not)"); continue
        if len(lab) > 300:
            reject(n["id"], "name longer than 300 characters"); continue
        if n["type"] == ROLE["topic"]:
            topic_groups[_norm(lab)].append(n["id"])
            continue
        recs[n["id"]] = {"np": n["id"], "type": TYPE_MAP[n["type"]], "name": lab, "src": n}
    for key, ids in topic_groups.items():
        ids.sort()
        canon = ids[0]
        recs[canon] = {"np": canon, "type": "topic", "name": nodes[canon]["label"].strip(), "src": nodes[canon], "merged": ids[1:]}
        for i in ids[1:]:
            alias_of[i] = canon
        if len(ids) > 1:
            rep["merged"]["topic (same name)"] += len(ids) - 1
    canon_of = lambda nid: alias_of.get(nid, nid)                                    # noqa: E731

    # scope: the single container a record sits in (weeks: their module; sessions/modules: a lone parent)
    parents = defaultdict(set)
    for _, rel, s, t in edges:
        if rel in ROLE["placement"]:
            # parent -> child, except week_link (module -> week), where the week sits in its module
            child, parent = t, s
            parents[child].add(parent)
    for r in recs.values():
        ps = [canon_of(x) for x in parents.get(r["np"], ()) if canon_of(x) in recs]
        r["scope_np"] = ps[0] if len(ps) == 1 and r["type"] in ("week", "session", "module") else None
    # names unique per (type, scope): a clash among DIFFERENT records keeps both, marked for review
    for r in sorted(recs.values(), key=lambda x: x["np"]):
        k = (r["type"], r.get("scope_np"), _norm(r["name"]))
        if k in used_keys:
            i = 2
            while (r["type"], r.get("scope_np"), _norm(f"{r['name']} ({i})")) in used_keys:
                i += 1
            r["name"] = f"{r['name']} ({i})"
            r["review"] = True
            rep["problems"].setdefault("same_name_kept_apart", []).append(r["np"])
            k = (r["type"], r.get("scope_np"), _norm(r["name"]))
        used_keys[k] = True

    # fields + review flags
    for r in recs.values():
        p, t = r["src"]["props"], r["type"]
        f = {}
        if t == "program":
            f = {"family": p.get("family"), "document_type": p.get("doctype")}
        elif t == "domain":
            f = {"cadence": p.get("cadence"), "stage": p.get("stage"), "also_known_as": _text(dom_alias.get(_norm(r["name"])))}
        elif t == "module":
            f = {"granularity": p.get("granularity"), "sequence": _text(p.get("sequence"))}
        elif t == "session":
            f = {"session_kind": p.get("session_kind"), "resource_type": p.get("resource_type")}
        elif t == "week":
            f = {"week_number": p.get("number")}
        elif t == "process":
            f = {"workflow_id": _text(p.get("workflow_id")), "effort": _text(p.get("effort")), "steps": _text(p.get("steps")),
                 "alerts": _text(p.get("alerts")), "tools": _text(p.get("tools")),
                 "suggested_owner": _text(wf_owner.get(str(p.get("workflow_id"))))}
        elif t == "team_member":
            pr = people.get(r["name"])
            f = {"team": (pr[1] if pr else None) or p.get("team"), "title": (pr[2] if pr else None) or p.get("title"),
                 "seniority": (pr[3] if pr else None) or p.get("seniority"), "also_known_as": _text(aliases.get(r["name"]))}
        elif t == "theme":
            f = {"theme_id": _text(p.get("theme_id"))}
        r["props"] = {k: (str(v) if not isinstance(v, (int, float)) or isinstance(v, bool) else v)
                      for k, v in f.items() if v not in (None, "", [])}
        if t == "week" and "week_number" in r["props"]:
            try:
                r["props"]["week_number"] = int(r["props"]["week_number"])
            except ValueError:
                r["props"].pop("week_number")
        r["review"] = r.get("review") or bool(p.get("review")) or bool(p.get("boilerplate"))
        r["tags"] = ["boilerplate"] if p.get("boilerplate") else []
    rep["unmapped_columns"] = _unmapped(nodes)

    # 4. write records (two passes: then scopes) -------------------------------------------
    existing = {r[0]: (r[1], r[2], r[3]) for r in q("select external_id, id, version, imported_version from kb.nodes where external_id like 'np:%%'")}
    kb_id: dict[str, str] = {}
    # Containers first, so a record's scope exists when it is written (names are
    # unique per type AND scope: two "Week 1"s in different modules are fine).
    order = {"program": 0, "domain": 0, "theme": 0, "team_member": 0, "instructor": 0, "topic": 0, "process": 1,
             "module": 1, "session": 2, "week": 2}
    for r in sorted(recs.values(), key=lambda x: (order.get(x["type"], 3), x["np"])):
        ext = "np:" + r["np"]
        if ext in existing:
            nid, ver, iver = existing[ext]
            kb_id[r["np"]] = str(nid)
            if iver is not None and ver != iver:
                rep["kept_app_edits"]["record"] += 1
            else:
                rep["existing"]["record"] += 1
            continue
        scope = kb_id.get(r["scope_np"]) if r.get("scope_np") else None
        # imported_version = 1: the version the insert stamps. Recorded IN the write
        # (a separate UPDATE would bump version past it: the stamp trigger).
        row = q("""insert into kb.nodes (type_id, name, props, external_id, review_status, status, imported_at, scope_id, imported_version)
                   values (%s, %s, %s, %s, %s, 'active', now(), %s, 1) returning id""",
                (type_id[r["type"]], r["name"], json.dumps(r["props"]), ext, "needs_review" if r["review"] else "none", scope))
        kb_id[r["np"]] = str(row[0][0])
        rep["created"][f"record: {r['type']}"] += 1
    for np_id in alias_of:
        kb_id[np_id] = kb_id.get(canon_of(np_id))
    # tags
    tagged = [(kb_id[r["np"]], t) for r in recs.values() for t in r["tags"]]
    for nid, t in tagged:
        tid = q("insert into kb.tags (name) select %s where not exists (select 1 from kb.tags where name_norm = kb.norm(%s) and archived_at is null) returning id", (t, t))
        tid = tid[0][0] if tid else q("select id from kb.tags where name_norm = kb.norm(%s) and archived_at is null", (t,))[0][0]
        conn.execute("insert into kb.node_tags (node_id, tag_id) values (%s, %s) on conflict do nothing", (nid, tid))

    # 5. links: one per URL (artifacts sharing a Drive URL merge) --------------------------
    by_url = defaultdict(list)
    for n in nodes.values():
        if n["type"] in ARTIFACTS and n["props"].get("drive_url"):
            by_url[n["props"]["drive_url"].strip()].append(n)
    res_of_np: dict[str, str] = {}
    for url, group in by_url.items():
        group.sort(key=lambda n: (ARTIFACTS.index(n["type"]), n["id"]))
        lead = group[0]
        title = (lead["label"] or "").strip() or url
        truncated = len(title) > 300
        title = title[:297] + "…" if truncated else title
        if truncated:
            rep["problems"].setdefault("link_title_truncated", []).append(lead["id"])
        kind = ARTIFACT_KIND.get(lead["type"]) or _mime_kind(lead["props"].get("mime"))
        tags = sorted({"historical" for n in group if n["props"].get("historical")} |
                      {"unavailable" for n in group if n["props"].get("content_available") is False})
        row = q("""insert into kb.resources (url, title, kind, external_id, tags, imported_at, imported_version)
                   values (%s, %s, %s, %s, %s, now(), 1)
                   on conflict (url_norm) where archived_at is null do nothing returning id""",
                (url, title, kind, "np:" + lead["id"], tags))
        if row:
            rid = str(row[0][0])
            rep["created"]["link"] += 1
        else:
            rid = _res_by_url(q, url)
            rep["existing"]["link"] += 1
        if len(group) > 1:
            rep["merged"]["link (same URL)"] += len(group) - 1
        for n in group:
            res_of_np[n["id"]] = rid
    # UpLevel links and Drive folders on modules, sessions and domains
    extra_links = 0
    for r in recs.values():
        p = r["src"]["props"]
        urls = []
        if isinstance(p.get("uplevel_link"), str):
            urls.append((p["uplevel_link"], "live_class_link", "UpLevel"))
        for f in p.get("drive_folders") or []:
            if isinstance(f, str):
                urls.append((f, "folder", "Drive folder"))
            elif isinstance(f, dict) and f.get("url"):
                urls.append((f["url"], "folder", "Drive folder"))
        if isinstance(p.get("drive_folder_url"), str):
            urls.append((p["drive_folder_url"], "folder", "Drive folder"))
        for url, kind, note in urls:
            if not re.match(r"^https?://\S+$", url.strip()):
                rep["problems"].setdefault("malformed_url_skipped", []).append(r["np"]); continue
            row = q("""insert into kb.resources (url, title, kind, external_id, imported_at, imported_version)
                       values (%s, %s, %s, %s, now(), 1) on conflict (url_norm) where archived_at is null do nothing returning id""",
                    (url.strip(), f"{note}: {r['name']}"[:300], kind, "np:" + r["np"] + ":" + hashlib.sha1(url.encode()).hexdigest()[:10]))
            rid = row[0][0] if row else _res_by_url(q, url)
            if row:
                rep["created"]["link"] += 1
                extra_links += 1
            _attach(conn, rep, kb_id[r["np"]], rid, note)
    rep["links"]["uplevel_and_folder_links_created"] = extra_links

    # 6. relationships and attachments ------------------------------------------------------
    for eid, rel, s, t in edges:
        st, tt = nodes.get(s, {}).get("type"), nodes.get(t, {}).get("type")
        key = (rel, st, tt)
        if key in ATTACH_MAP:
            rec_side, art_side, note = ATTACH_MAP[key]
            rec_np, art_np = (s, t) if rec_side == "source" else (t, s)
            rid, nid = res_of_np.get(art_np), kb_id.get(canon_of(rec_np))
            if rid and nid:
                _attach(conn, rep, nid, rid, note)
            else:
                rep["problems"].setdefault("attachment_without_record_or_link", []).append(f"edge {eid}")
            continue
        if key not in EDGE_MAP:
            rep["problems"].setdefault("relationship_shape_unmapped", []).append(f"edge {eid} ({rel})")
            continue
        etype, flip = EDGE_MAP[key]
        a, b = kb_id.get(canon_of(s)), kb_id.get(canon_of(t))
        if not a or not b:
            rep["problems"].setdefault("relationship_end_rejected", []).append(f"edge {eid}")
            continue
        src, tgt = (b, a) if flip else (a, b)
        stype, ttype = TYPE_MAP[tt if flip else st], TYPE_MAP[st if flip else tt]
        if (stype, ttype, etype) not in rules:
            rep["problems"].setdefault("relationship_not_allowed", []).append(f"edge {eid}")
            continue
        if src == tgt:
            rep["merged"]["relationship (self after merge)"] += 1
            continue
        note = None
        if etype == "teaches":
            en = edge_note.get((t, s) if flip else (s, t))
            if en and (en["role"] or en["dates"]):
                note = "; ".join(x for x in (("role: " + ", ".join(sorted(en["role"]))) if en["role"] else "",
                                             ("class dates: " + ", ".join(sorted(en["dates"]))) if en["dates"] else "") if x)[:2000]
        row = q("""insert into kb.edges (edge_type_id, source_id, target_id, external_id, note) values (%s, %s, %s, %s, %s)
                   on conflict do nothing returning id""", (edge_type_id[etype], src, tgt, f"np:e{eid}", note))
        if row:
            rep["created"][f"relationship: {etype}"] += 1
        elif q("select 1 from kb.edges where external_id = %s", (f"np:e{eid}",)):
            rep["existing"]["relationship"] += 1
        else:
            rep["merged"]["relationship (same pair and type)"] += 1

    # 7. provenance: every cited file becomes a "Source" link on the record ------------------
    file_res = {}
    for n in nodes.values():
        if n["type"] in ARTIFACTS and n["id"] in res_of_np:
            for k in ("relative_path", "path"):
                if n["props"].get(k):
                    file_res[n["props"][k].lstrip("/")] = res_of_np[n["id"]]
    cites = q("select distinct node_id, file from public.node_sources where file is not null")
    unres = 0
    for np_id, f in cites:
        nid, rid = kb_id.get(canon_of(np_id)), file_res.get(f)
        if nid and rid:
            _attach(conn, rep, nid, rid, "Source")
        elif nid:
            unres += 1
    rep["links"]["citations_read"] = len(cites)
    rep["links"]["citations_without_a_link"] = unres

    # 7b. curation notes -> the body of the person or process they are about (author e-mail left out)
    notes = q("""select n.scope, n.row_key, n.note from public.curation_notes n order by n.scope, n.row_key, n.position, n.id""")
    by_rec, unplaced = defaultdict(list), 0
    person_np = {nodes[x]["label"]: x for x in nodes if nodes[x]["type"] == ROLE["person"]}
    wf_np = {str(nodes[x]["props"].get("workflow_id")): x for x in nodes if nodes[x]["type"] == ROLE["workflow"]}
    for scope, key, note in notes:
        np_id = person_np.get(key) if scope == "people.yaml" else wf_np.get(str(key)) if scope == "workflow-owners.yaml" else None
        if np_id and kb_id.get(np_id) and note:
            by_rec[kb_id[np_id]].append(str(note))
        else:
            unplaced += 1
    for nid, ns in by_rec.items():
        body = "Curation notes (from the original site):\n" + "\n".join("- " + x for x in ns)
        conn.execute("""update kb.nodes set body = %s, imported_version = version + 1 where id = %s
                        and body is distinct from %s and version = coalesce(imported_version, version)""",
                     (body[:100000], nid, body[:100000]))
    rep["links"]["curation_notes_placed"] = sum(len(v) for v in by_rec.values())
    rep["links"]["curation_notes_not_placed"] = unplaced

    # 8. layout -> the shared graph layout (only where nobody has placed the record yet)
    lay = q("select node_id, x, y from public.node_layout")
    pts = [(kb_id[canon_of(n)], x, y) for n, x, y in lay if kb_id.get(canon_of(n)) and x is not None and y is not None]
    if pts:
        conn.execute("""insert into kb.graph_positions (layout, node_id, x, y)
                        select 'default', n, x * 4, y * 4 from unnest(%s::uuid[], %s::float8[], %s::float8[]) u(n, x, y)
                        on conflict (layout, node_id) do nothing""",
                     ([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]))
    rep["links"]["graph_positions_read"] = len(lay)

    # 9. what the KB now holds, and its gaps --------------------------------------------------
    rep["kb_totals"] = dict(zip(("records", "relationships", "links", "attachments"),
                                q("""select (select count(*) from kb.nodes where archived_at is null),
                                            (select count(*) from kb.edges where archived_at is null),
                                            (select count(*) from kb.resources where archived_at is null),
                                            (select count(*) from kb.node_resources where archived_at is null)""")[0]))
    rep["no_owner"] = q("select count(*) from kb.nodes where archived_at is null and owner_id is null")[0][0]
    rep["no_placement"] = dict(q("""select t.key, count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
        where n.archived_at is null and t.key in ('module', 'session', 'week', 'domain')
          and not exists (select 1 from kb.edges e join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
                          where e.target_id = n.id and e.archived_at is null) group by 1"""))
    rep["not_connected"] = q("""select count(*) from kb.nodes n where n.archived_at is null and not exists
        (select 1 from kb.edges e where e.archived_at is null and (e.source_id = n.id or e.target_id = n.id))""")[0][0]
    rep["needs_review"] = q("select count(*) from kb.nodes where review_status = 'needs_review' and archived_at is null")[0][0]
    for k in ("created", "existing", "kept_app_edits", "merged"):
        rep[k] = dict(rep[k])
    return rep


def _res_by_url(q, url):
    """The live link with this URL, matched the way kb.resources.url_norm is computed."""
    return str(q("select id from kb.resources where archived_at is null and url_norm = lower(regexp_replace(btrim(%s), '/+$', ''))",
                 (url,))[0][0])


def _attach(conn, rep, node_id, res_id, note):
    row = conn.execute("""insert into kb.node_resources (node_id, resource_id, note) values (%s, %s, %s)
                          on conflict do nothing returning id""", (node_id, res_id, note)).fetchall()
    rep["created"]["attachment" if row else "attachment (already there)"] += 1


MAPPED_PROPS = {t: set(v) for t, v in M["mapped_props"].items()}


def _unmapped(nodes) -> dict:
    out = defaultdict(Counter)
    for n in nodes.values():
        for k, v in (n["props"] or {}).items():
            if v not in (None, "", [], {}) and k not in MAPPED_PROPS.get(n["type"], set()):
                out[n["type"]][k] += 1
    return {t: dict(c) for t, c in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["preview", "apply"])
    ap.add_argument("--as", dest="admin", required=True, help="e-mail of a KB admin; the import is attributed to them")
    ap.add_argument("--report", help="write the report (counts and ids only) as JSON here")
    a = ap.parse_args()
    url = os.environ.get("SUPABASE_DB_URL_SESSION")
    if not url:
        raise SystemExit("SUPABASE_DB_URL_SESSION is not set")
    import psycopg
    with psycopg.connect(url) as conn:
        rep = run(conn, a.admin, a.mode == "apply")
        if a.mode == "apply":
            conn.commit()
        else:
            conn.rollback()
    printable = {k: v for k, v in rep.items() if k not in ("rejected", "problems", "unmapped_tables")}
    printable["rejected"] = len(rep["rejected"])
    printable["problems"] = {k: len(v) for k, v in rep["problems"].items()}
    print(json.dumps(printable, indent=1, default=str))
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
