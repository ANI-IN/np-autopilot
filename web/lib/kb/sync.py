"""The sync: the original site's tables (public.nodes, edges, node_sources,
node_layout, people, ...) -> the knowledge base, until the KB becomes the only
place to edit. One engine for the first import (pipeline/kb_import_projection.py,
CLI) and the scheduled runs (pg_cron -> POST /api/cron/kb-sync, or "Sync now"
-> /api/kb/sync).

Every run:
  1. builds the DESIRED KB state from the old tables, with NP Autopilot's own
     rules (public/index.html: adaptNode / model / currentInstructors) for what
     is current and what is legacy, and its roles (P, B1-B3);
  2. compares it, unit by unit (record, link, relationship, link-on-a-record),
     with kb.sync_map: the source checksum, and a hash of what the sync last
     WROTE to the KB;
  3. writes only what changed. A unit whose KB copy was edited in the app
     since the sync wrote it is NOT overwritten: it is flagged as a conflict
     (Data quality). A unit that disappeared from the source is flagged
     "removed at source": records are never deleted; relationships and links on
     records are archived (reversible). Records created in the KB are never
     touched (they have no sync_map row).
  4. re-applies the legacy rules (kb.legacy_archive, pipeline/kb_legacy.py).

One run at a time (a lock taken in its own short transaction, so it works
through the transaction pooler), batches committed as it goes, a time budget
(the cron route stops in time and the next run carries on: the diff is
recomputed from scratch each run). KB_SYNC_ENABLED=false turns it off.
Writes are attributed to actor_type 'sync' (Activity: "Sync").
Output: counts and ids only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from . import validate as kbv

REPO = Path(__file__).resolve().parents[3]
MAPPING_FILE = REPO / "config" / "kb-projection-mapping.yaml"
LOCK_KEY = 7302026          # pg advisory lock id for "kb sync"
STALE_MINUTES = 20          # a "running" run older than this is considered dead
LAYOUT_SCALE = 4            # projection layout -> the KB graph's coordinates (npmap reads it back)
SOURCE_NOTE = "Source"      # the note on a record's provenance links (one per cited file)


# ---------------------------------------------------------------------------- mapping
def load_mapping() -> dict:
    """config/kb-projection-mapping.yaml, checked against config/taxonomy.yaml."""
    import yaml
    from pipeline.lib import taxonomy
    m = yaml.safe_load(MAPPING_FILE.read_text(encoding="utf-8"))
    ntypes, etypes = set(taxonomy.node_type_names()), set(taxonomy.edge_type_names())
    named_types = set(m["types"]) | set(m["artifacts"]) | set(m["artifact_kind"]) | set(m["mapped_props"])
    named_types |= {r[k] for r in m["relationships"] + m["attachments"] for k in ("source", "target")}
    named_types |= {v for k, v in m["roles"].items() if k in ("topic", "person", "workflow", "module", "domain",
                                                              "instructor", "programme", "session", "deck")}
    named_rels = {r["rel"] for r in m["relationships"] + m["attachments"]} | set(m["roles"]["placement"])
    named_rels |= {m["roles"][k] for k in ("week_link", "teaching", "teaching_reversed", "domain_offers", "programme_covers",
                                           "programme_contains", "session_link", "topic_link", "owner_link", "co_owner_link",
                                           "deck_link", "expertise")}
    bad = sorted(named_types - ntypes) + sorted(named_rels - etypes)
    if bad:
        raise RuntimeError(f"{MAPPING_FILE.name} names what config/taxonomy.yaml does not define: {', '.join(bad)}")
    return m


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _url_norm(u: str) -> str:          # = kb.resources.url_norm
    return re.sub(r"/+$", "", (u or "").strip()).lower()


def _h(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _text(v) -> str | None:
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, list):
        return "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in v)[:20000]
    return json.dumps(v, ensure_ascii=False)[:20000] if isinstance(v, dict) else str(v)[:20000]


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


# ---------------------------------------------------------------------------- NP Autopilot's rules
def np_categories(nodes: dict, edges: list, R: dict) -> dict:
    """Current vs legacy, exactly as public/index.html decides it:
      - module legacy  = no `domain_slug` prop                    (adaptNode)
      - domain current = offers at least one current module       (model(): M.cur / M.other)
      - instructor current = an end of an edge with tier 'mastersheet' (currentInstructors())
      - every programme is from the older sheets                  ('Programmes (older sheets)')
      - a legacy module's domain = through a programme covering the domain
        and containing the module (model(): M.legacy / domOf); M.unlinked has none."""
    mod, dom, ins, prog = R["module"], R["domain"], R["instructor"], R["programme"]
    legacy = set()
    for n in nodes.values():
        if n["type"] == mod and "domain_slug" not in (n["props"] or {}):
            legacy.add(n["id"])
        if n["type"] == prog:
            legacy.add(n["id"])
    current_dom = {s for _, rel, s, t, _p in edges if rel == R["domain_offers"] and nodes.get(t, {}).get("type") == mod
                   and t not in legacy and nodes.get(s, {}).get("type") == dom}
    for n in nodes.values():
        if n["type"] == dom and n["id"] not in current_dom:
            legacy.add(n["id"])
    with_role = set()
    for _, rel, s, t, p in edges:
        if (p or {}).get("tier") == "mastersheet":
            with_role.update((s, t))
    for n in nodes.values():
        if n["type"] == ins and n["id"] not in with_role:
            legacy.add(n["id"])
    # domains of legacy modules (through programmes), for the legacy step
    covers = defaultdict(set)        # programme -> domains
    for _, rel, s, t, _p in edges:
        if rel == R["programme_covers"] and nodes.get(s, {}).get("type") == prog:
            covers[s].add(t)
    mod_domains = defaultdict(set)
    for _, rel, s, t, _p in edges:
        if rel == R["programme_contains"] and nodes.get(t, {}).get("type") == mod:
            mod_domains[t] |= covers.get(s, set())
        if rel == R["domain_offers"] and nodes.get(t, {}).get("type") == mod:
            mod_domains[t].add(s)
    return {"legacy": legacy, "current_domains": current_dom, "instructors_with_role": with_role,
            "module_domains": mod_domains}


# ---------------------------------------------------------------------------- desired state
def desired_state(conn, M: dict, source: str = "public", exclusions: tuple | None = None) -> dict:
    """`source`: the schema holding the old tables (tests use a synthetic one).
    `exclusions`: (rule on?, excluded ids) as legacy_delete.excluded returns
    them (the NP Autopilot connector passes them); None reads them here."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", source):
        raise ValueError("bad source schema name")
    q = lambda sql, p=(): conn.execute(sql.replace("public.", source + "."), p).fetchall()     # noqa: E731
    R, TYPE_MAP = M["roles"], M["types"]
    ARTIFACTS, ARTIFACT_KIND = tuple(M["artifacts"]), M["artifact_kind"]
    EDGE_MAP = {(r["rel"], r["source"], r["target"]): (r["kb"], bool(r.get("flip"))) for r in M["relationships"]}
    ATTACH_MAP = {(r["rel"], r["source"], r["target"]): (r["record"], r["note"]) for r in M["attachments"]}
    nodes = {r[0]: {"id": r[0], "type": r[1], "label": r[2], "props": r[3] or {}}
             for r in q("select id, type, label, props from public.nodes where not sensitive")}
    edges = q("select id, rel, source_id, target_id, props from public.edges order by id")
    cat = np_categories(nodes, edges, R)
    people = {r[0]: r for r in q("select canonical, team, title, seniority from public.people")}
    aliases = defaultdict(list)
    for a, c in q("select alias, canonical from public.people_aliases order by alias"):
        aliases[c].append(a)
    dom_alias = defaultdict(list)
    for a, d in q("select alias, domain from public.domain_aliases order by alias"):
        dom_alias[_norm(d)].append(a)
    wf_owner = {str(r[0]): r[1] for r in q("select workflow_id, suggestion from public.workflow_owners where suggestion is not null")}
    rep = {"read": {"nodes": len(nodes), "edges": len(edges)}, "rejected": [], "problems": defaultdict(list)}

    # records -----------------------------------------------------------------
    recs: dict[str, dict] = {}
    RETIRED = set(M.get("retired_types") or ())      # never imported (2026-11-07: weeks, workflows, themes)
    for n in nodes.values():
        if n["type"] not in TYPE_MAP or n["type"] in RETIRED:
            continue
        p, lab = n["props"], (n["label"] or "").strip()
        if n["type"] == R["topic"] and p.get("not_a_topic"):
            rep["rejected"].append({"id": n["id"], "reason": f"marked not_a_topic ({p['not_a_topic']}) by the pipeline"}); continue
        # THE API's name rule (validate.name_problem), not a copy of it (run 6, F4).
        problem = kbv.name_problem(lab)
        if problem:
            rep["rejected"].append({"id": n["id"], "reason": problem}); continue
        recs[n["id"]] = {"np": n["id"], "type": TYPE_MAP[n["type"]], "src_type": n["type"], "name": lab, "src": n,
                         "legacy": n["id"] in cat["legacy"]}
    # Permanent exclusions (0037; run 6 R3, the owner-approved deletion of the
    # legacy domains and modules): once the rule is on, a domain NP Autopilot
    # does not count as current and a legacy module are never created again,
    # and neither is any source id the deletion removed. Their relationships
    # and attachments then have a missing end and are left out with them.
    from .legacy_delete import excluded as _excluded
    rule_on, gone = exclusions if exclusions is not None else _excluded(conn)
    excluded_np: set = set()
    if rule_on or gone:
        drop = [k for k, r in recs.items() if k in gone or (rule_on and (
            (r["src_type"] == R["domain"] and k not in cat["current_domains"]) or
            (r["src_type"] == R["module"] and r["legacy"])))]
        for k in drop:
            del recs[k]
        excluded_np = set(drop)
        rep["excluded"] = len(drop)
    # scope: the one container a record sits in (NP: a generic name always sits under what it belongs to)
    parents = defaultdict(set)
    for _, rel, s, t, _p in edges:
        if rel in R["placement"] or rel == R["topic_link"]:
            parents[t].add(s)
    for r in recs.values():
        ps = sorted(x for x in parents.get(r["np"], ()) if x in recs)
        r["scope_np"] = ps[0] if len(ps) == 1 and r["type"] in ("week", "session", "module", "topic") else None
    used = set()
    for r in sorted(recs.values(), key=lambda x: x["np"]):
        k = (r["type"], r["scope_np"], _norm(r["name"]))
        if k in used:
            i = 2
            while (r["type"], r["scope_np"], _norm(f"{r['name']} ({i})")) in used:
                i += 1
            r["name"] = f"{r['name']} ({i})"
            r["review"] = True
            rep["problems"]["same_name_kept_apart"].append(r["np"])
            k = (r["type"], r["scope_np"], _norm(r["name"]))
        used.add(k)
    # owners by role (NP: taught_by tier 'mastersheet', instructor_role primary / backup_1..3)
    owner, co = {}, defaultdict(list)
    rank = {"primary": 0, "backup_1": 1, "backup_2": 2, "backup_3": 3}
    roles_of = defaultdict(list)
    for eid, rel, s, t, p in edges:
        p = p or {}
        if rel == R["teaching_reversed"] and p.get("tier") == "mastersheet" and p.get("instructor_role") in rank:
            roles_of[s].append((rank[p["instructor_role"]], t, p["instructor_role"]))
        if rel == R["owner_link"]:
            owner.setdefault(s, t)          # a domain's owner (first by edge id)
        if rel == R["co_owner_link"]:
            co[s].append(t)
    for m, lst in roles_of.items():
        lst.sort()
        prim = [x for x in lst if x[0] == 0]
        if prim:
            owner[m] = prim[0][1]
        co[m] = [x[1] for x in lst if x not in prim[:1]]
    dom_slug = {}                   # a current domain's mastersheet slug (from the modules it offers)
    for _, rel, s, t, _p in edges:
        slug = (nodes.get(t, {}).get("props") or {}).get("domain_slug")
        if rel == R["domain_offers"] and slug:
            dom_slug.setdefault(s, slug)
    for r in recs.values():
        p, t = r["src"]["props"], r["type"]
        f = {}
        if t == "program":
            f = {"family": p.get("family"), "document_type": p.get("doctype")}
        elif t == "domain":
            f = {"cadence": p.get("cadence"), "stage": p.get("stage"), "also_known_as": _text(dom_alias.get(_norm(r["name"]))),
                 "slug": dom_slug.get(r["np"])}
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
        props = {k: (v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)) for k, v in f.items() if v not in (None, "", [])}
        if t == "week" and "week_number" in props:
            try:
                props["week_number"] = int(props["week_number"])
            except ValueError:
                props.pop("week_number")
        r["props"] = props
        r["review"] = bool(r.get("review") or p.get("review") or p.get("boilerplate"))
        r["tags"] = sorted((["boilerplate"] if p.get("boilerplate") else []) + (["legacy"] if r["legacy"] else []))
        r["owner_np"] = owner.get(r["np"]) if owner.get(r["np"]) in recs else None
        r["co_np"] = [x for x in co.get(r["np"], []) if x in recs and x != r["owner_np"]]
    # THE API's typed-field rule (service.field_errors -> kb.field_value_error,
    # the function the database trigger runs), for every record in one query.
    # A value the KB would refuse is rejected with the API's own sentence
    # (problems.field_value_rejected) and left out; the record itself is kept,
    # so it is never flagged "removed at source" for one bad cell, and the run
    # no longer fails the whole batch inside the trigger.
    field_problems(conn, recs, rep)
    # curation notes -> body
    person_np = {n["label"]: n["id"] for n in nodes.values() if n["type"] == R["person"]}
    wf_np = {str(n["props"].get("workflow_id")): n["id"] for n in nodes.values() if n["type"] == R["workflow"]}
    notes = defaultdict(list)
    for scope, key, note in q("select scope, row_key, note from public.curation_notes order by scope, row_key, position, id"):
        np_id = person_np.get(key) if scope == "people.yaml" else wf_np.get(str(key)) if scope == "workflow-owners.yaml" else None
        if np_id in recs and note:
            notes[np_id].append(str(note))
        else:
            rep["problems"]["curation_note_not_placed"].append(f"{scope}:{key}")
    for np_id, ns in notes.items():
        recs[np_id]["body"] = ("Curation notes (from the original site):\n" + "\n".join("- " + x for x in ns))[:100000]

    # links ---------------------------------------------------------------------
    links: dict[str, dict] = {}
    res_of_np: dict[str, str] = {}
    by_url = defaultdict(list)
    for n in nodes.values():
        if n["type"] in ARTIFACTS and n["props"].get("drive_url"):
            by_url[_url_norm(n["props"]["drive_url"])].append(n)
    for key, group in by_url.items():
        group.sort(key=lambda n: (ARTIFACTS.index(n["type"]), n["id"]))
        lead = group[0]
        title = (lead["label"] or "").strip() or lead["props"]["drive_url"]
        if len(title) > 300:
            title = title[:297] + "…"
            rep["problems"]["link_title_truncated"].append(lead["id"])
        links[key] = {"url": lead["props"]["drive_url"].strip(), "title": title,
                      "kind": ARTIFACT_KIND.get(lead["type"]) or _mime_kind(lead["props"].get("mime")),
                      "tags": sorted({"historical" for n in group if n["props"].get("historical")} |
                                     {"unavailable" for n in group if n["props"].get("content_available") is False}),
                      "sources": sorted(n["id"] for n in group), "source_types": sorted({n["type"] for n in group})}
        for n in group:
            res_of_np[n["id"]] = key
    attachments: dict[str, dict] = {}

    def attach(rec_np, link_key, note):
        k = f"{rec_np}|{link_key}"
        if k not in attachments:
            attachments[k] = {"rec": rec_np, "link": link_key, "note": note}
    for r in recs.values():
        p = r["src"]["props"]
        urls = []
        if isinstance(p.get("uplevel_link"), str):
            urls.append((p["uplevel_link"], "live_class_link", "UpLevel"))
        for f in p.get("drive_folders") or []:
            u = f if isinstance(f, str) else (f.get("url") if isinstance(f, dict) else None)
            if u:
                urls.append((u, "folder", "Drive folder"))
        if isinstance(p.get("drive_folder_url"), str):
            urls.append((p["drive_folder_url"], "folder", "Drive folder"))
        for url, kind, note in urls:
            url = url.strip()
            if not re.match(r"^https?://\S+$", url):
                rep["problems"]["malformed_url_skipped"].append(r["np"]); continue
            key = _url_norm(url)
            links.setdefault(key, {"url": url, "title": f"{note}: {r['name']}"[:300], "kind": kind, "tags": [],
                                   "sources": [r["np"]], "source_types": [r["src_type"]]})
            attach(r["np"], key, note)

    # relationships and links on records -------------------------------------------------
    rels: dict[str, dict] = {}
    for eid, rel, s, t, p in edges:
        st, tt = nodes.get(s, {}).get("type"), nodes.get(t, {}).get("type")
        key3 = (rel, st, tt)
        if key3 in ATTACH_MAP:
            side, note = ATTACH_MAP[key3]
            rec_np, art_np = (s, t) if side == "source" else (t, s)
            if rec_np in recs and art_np in res_of_np:
                attach(rec_np, res_of_np[art_np], note)
            elif rec_np in excluded_np:
                rep["excluded_attachments"] = rep.get("excluded_attachments", 0) + 1
            else:
                rep["problems"]["attachment_without_record_or_link"].append(f"edge {eid}")
            continue
        if key3 not in EDGE_MAP:
            rep["problems"]["relationship_shape_unmapped"].append(f"edge {eid}"); continue
        etype, flip = EDGE_MAP[key3]
        if s not in recs or t not in recs:
            if s in excluded_np or t in excluded_np:
                rep["excluded_relationships"] = rep.get("excluded_relationships", 0) + 1; continue
            rep["problems"]["relationship_end_rejected"].append(f"edge {eid}"); continue
        src, tgt = (t, s) if flip else (s, t)
        if src == tgt:
            continue
        k = f"{etype}|{src}|{tgt}"
        d = rels.setdefault(k, {"type": etype, "src": src, "tgt": tgt, "roles": set(), "older_roles": set(), "dates": set(),
                                "tiers": set(), "edges": []})
        p = p or {}
        d["edges"].append(eid)
        if p.get("tier"):
            d["tiers"].add(str(p["tier"]))
        # NP Autopilot: P / B1-B3 come ONLY from the current mastersheet
        # (taught_by, tier 'mastersheet', instructor_role). The older sheets'
        # 'role' (primary/backup) is kept apart, never mixed into it.
        if p.get("instructor_role") and p.get("tier") == "mastersheet":
            d["roles"].add(str(p["instructor_role"]))
        if p.get("role"):
            d["older_roles"].add(str(p["role"]))
        for x in p.get("class_dates") or []:
            d["dates"].add(str(x))
    for d in rels.values():
        role = sorted(d["roles"], key=lambda x: rank.get(x, 9))
        older = sorted(d["older_roles"])
        d["props"] = {k: v for k, v in {"role": role[0] if role and role[0] in rank else None,
                                       "older_role": ", ".join(older) or None,
                                       "tier": "mastersheet" if "mastersheet" in d["tiers"] else ("older_sheets" if d["type"] == "teaches" else None)}.items() if v}
        note = "; ".join(x for x in (("role: " + ", ".join(role)) if role else "",
                                     ("older sheets: " + ", ".join(older)) if older else "",
                                     ("class dates: " + ", ".join(sorted(d["dates"]))) if d["dates"] else "") if x)
        d["note"] = note[:2000] or None
    # provenance: every cited file -> a "Source" link on the record
    file_link = {}
    for n in nodes.values():
        if n["type"] in ARTIFACTS and n["id"] in res_of_np:
            for k in ("relative_path", "path"):
                if n["props"].get(k):
                    file_link[n["props"][k].lstrip("/")] = res_of_np[n["id"]]
    cites = q("select distinct node_id, file from public.node_sources where file is not null")
    unres = 0
    for np_id, f in cites:
        if np_id in recs and f in file_link:
            attach(np_id, file_link[f], SOURCE_NOTE)
        elif np_id in recs:
            unres += 1
    rep["read"].update({"citations": len(cites), "citations_without_a_link": unres})
    layout = {r[0]: (r[1], r[2]) for r in q("select node_id, x, y from public.node_layout") if r[1] is not None and r[2] is not None}
    return {"recs": recs, "links": links, "rels": rels, "attachments": attachments, "layout": layout,
            "categories": cat, "nodes": nodes, "edges": edges, "report": rep}


def field_problems(conn, recs: dict, rep: dict) -> int:
    """Leave out (and report) every prop value that breaks a typed field of the
    record's KB type, by the same function the API uses (svc.field_errors).
    Returns how many values were left out; on valid data it changes nothing."""
    from . import service as svc
    fields_of = {k: f for k, f in conn.execute(
        "select key, fields from kb.node_types where archived_at is null").fetchall()}
    pending = [r for r in recs.values() if r.get("props")]
    dropped = 0
    while pending:                       # one failing field per record per pass
        bad = svc.field_errors(conn, [(fields_of.get(r["type"]) or [], r["props"]) for r in pending])
        nxt = []
        for ix, (key, message) in sorted(bad.items()):
            r = pending[ix]
            r["props"] = {k: x for k, x in r["props"].items() if k != key}
            rep["problems"]["field_value_rejected"].append(f"{r['np']}: {message}")
            dropped += 1
            nxt.append(r)
        pending = nxt
    return dropped


def _rec_content(r, kb_scope, kb_owner, kb_co):
    return {"name": r["name"], "props": r["props"], "scope": kb_scope, "body": r.get("body"),
            "legacy": r["legacy"], "review": r["review"], "tags": r["tags"], "owner": kb_owner, "co": kb_co}


# ---------------------------------------------------------------------------- the run
class SyncDisabled(Exception):
    pass


def enabled() -> bool:
    return os.environ.get("KB_SYNC_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")


def start_run(conn, trigger: str, actor_id: str | None) -> int | None:
    """One run at a time: a transaction-scoped advisory lock around claiming
    the run row (works through the transaction pooler). Returns the run id, or
    None when another run is already going."""
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        busy = conn.execute("""select id from kb.sync_runs where status = 'running'
                               and started_at > now() - make_interval(mins => %s)""", (STALE_MINUTES,)).fetchone()
        if busy:
            conn.execute("""insert into kb.sync_runs (trigger, actor_id, status, finished_at, message)
                            values (%s, %s, 'skipped', now(), %s)""", (trigger, actor_id, f"run {busy[0]} is still going"))
            return None
        conn.execute("""update kb.sync_runs set status = 'error', finished_at = now(), message = 'abandoned (stale)'
                        where status = 'running'""")
        return conn.execute("insert into kb.sync_runs (trigger, actor_id) values (%s, %s) returning id",
                            (trigger, actor_id)).fetchone()[0]


#: The order a run works in. A run that reaches its time budget saves the
#: phase and the last key it finished (kb.sync_runs.resume, 0033); the next run
#: continues there instead of walking every unit again (resumable sync, run 6).
PHASES = ("records", "owners", "links", "relationships", "attachments", "removed")


def resume_point(conn) -> dict | None:
    """Where the last finished run stopped, when it stopped early (else None:
    the next run starts a new pass from the beginning)."""
    row = conn.execute("""select resume from kb.sync_runs where status not in ('skipped', 'running')
                          order by id desc limit 1""").fetchone()
    r = row[0] if row else None
    return r if isinstance(r, dict) and r.get("phase") in PHASES else None


def run(conn, *, trigger: str = "cli", actor_id: str | None = None, apply: bool = True,
        budget_seconds: float | None = None, batch: int = 400, source: str = "public",
        mapping: dict | None = None, operator: bool = False, resume: bool = True, connector=None) -> dict:
    """The whole sync. `conn` must be able to write the kb tables as their
    owner (CLI: the session pooler login; the API route resets the request
    role for an authorised caller). Preview (apply=False) runs everything in
    one transaction and rolls back. `connector` (web/lib/kb/connectors): the
    source's steps (configuration, desired state, exclusions, finishing step);
    default NP Autopilot, the only one today."""
    from . import typedefs as td
    from . import connectors
    src_conn = connector or connectors.get(connectors.DEFAULT)
    if not enabled():
        raise SyncDisabled("KB_SYNC_ENABLED is false: the sync is switched off")
    t0 = time.monotonic()
    conn.autocommit = False
    run_id = None
    if apply:
        conn.autocommit = True
        run_id = start_run(conn, trigger, actor_id)
        if run_id is None:
            return {"status": "skipped", "message": "another sync is running"}
        conn.autocommit = False
    out = {"run_id": run_id, "created": Counter(), "updated": Counter(), "unchanged": Counter(), "conflicts": Counter(),
           "removed_at_source": Counter(), "restored_at_source": Counter(), "adopted": Counter(), "skipped_archived": Counter(),
           "conflicts_cleared": Counter(), "errors": [], "partial": False, "resume": None, "resumed_from": None}

    def attribute():
        conn.execute("select set_config('kb.actor_type', 'sync', true), set_config('kb.actor_id', %s, true), "
                      "set_config('request.jwt.claims', %s, true), set_config('kb.operator', %s, true)",
                      (actor_id or "", json.dumps({"sub": actor_id, "role": "authenticated"}) if actor_id else "",
                       "on" if operator else ""))

    try:
        # inside the logged part: a bad mapping is a failed run (run log, admin banner), not a silent one
        M = mapping or src_conn.load_config(conn)
        attribute()
        ensure_config(conn, M, actor_id, operator)
        D = src_conn.desired_state(conn, M, source=source)
        out["report"] = D["report"]
        q = lambda sql, p=(): conn.execute(sql, p).fetchall()             # noqa: E731
        types = {t["key"]: t["id"] for t in td.all_types(conn)["node_types"]}
        etypes = {e["key"]: e["id"] for e in td.all_types(conn)["edge_types"]}
        # The relationship type rules, by the API's own check (service.edge_rule_problem).
        from . import service as svc
        rules = svc.edge_rules(conn)
        smap = {(u, k): {"kb_id": str(i) if i else None, "checksum": c, "kb_checksum": kc, "removed": ra, "conflict": ca}
                for u, k, i, c, kc, ra, ca in q("select unit, key, kb_id, checksum, kb_checksum, removed_at, conflict_at from kb.sync_map")}
        writes = 0
        start = resume_point(conn) if (apply and resume) else None
        out["resumed_from"] = start
        start_ix = PHASES.index(start["phase"]) if start else 0
        pos = dict(start) if start else {"phase": PHASES[0], "after": None}   # the last unit finished
        flusher = [None]                               # the current phase's queue, flushed before stopping
        stopping = [False]

        def done_before(phase, key) -> bool:
            """True for a unit the run we continue already finished."""
            if start is None:
                return False
            i = PHASES.index(phase)
            if i != start_ix:
                return i < start_ix
            after = start.get("after")
            return after is not None and _key(key) <= _key(after)

        def at(phase, key=None):
            pos["phase"], pos["after"] = phase, key

        def checkpoint(force=False):
            nonlocal writes
            if not apply:
                return
            if force or writes >= batch:
                conn.commit(); writes = 0; attribute()
            if budget_seconds and time.monotonic() - t0 > budget_seconds and not stopping[0]:
                # Stop at a clean point: write what is queued, commit, save where we are.
                stopping[0] = True
                if flusher[0]:
                    flusher[0]()
                conn.commit(); attribute()
                out["resume"] = dict(pos)
                raise _OutOfTime()

        def mark(unit, key, kb_table, kb_id, checksum, kb_checksum):
            conn.execute("""insert into kb.sync_map (unit, key, kb_table, kb_id, checksum, kb_checksum, last_written)
                            values (%s, %s, %s, %s, %s, %s, now())
                            on conflict (unit, key) do update set kb_id = excluded.kb_id, checksum = excluded.checksum,
                              kb_checksum = excluded.kb_checksum, last_seen = now(), last_written = now(),
                              removed_at = null, conflict_at = null, conflict_checksum = null""",
                         (unit, key, kb_table, kb_id, checksum, kb_checksum))

        def seen(unit, key):
            """Unchanged: nothing is written (removal is detected by set difference)."""

        def mark_many(rows):
            """mark() for many units in one round trip (executemany is pipelined):
            a first import over a distant pooler is round trips, not work."""
            if rows:
                conn.cursor().executemany("""insert into kb.sync_map (unit, key, kb_table, kb_id, checksum, kb_checksum, last_written)
                                             values (%s, %s, %s, %s, %s, %s, now())
                                             on conflict (unit, key) do update set kb_id = excluded.kb_id, checksum = excluded.checksum,
                                               kb_checksum = excluded.kb_checksum, last_seen = now(), last_written = now(),
                                               removed_at = null, conflict_at = null, conflict_checksum = null""", rows)

        tag_ids = _sync_tags(conn)

        def conflict(unit, key, checksum):
            conn.execute("""update kb.sync_map set conflict_at = coalesce(conflict_at, now()), conflict_checksum = %s,
                            last_seen = now() where unit = %s and key = %s""", (checksum, unit, key))

        # -- records: containers first so scopes exist ------------------------------------
        order = {"program": 0, "domain": 0, "theme": 0, "team_member": 0, "instructor": 0, "process": 1, "module": 1,
                 "topic": 2, "session": 2, "week": 2}
        kb_rec: dict[str, str] = {k: v["kb_id"] for (u, k), v in smap.items() if u == "record" and v["kb_id"]}
        ext = {r[0][3:]: str(r[1]) for r in q("select external_id, id from kb.nodes where external_id like 'np:%%'")}
        recs = sorted(D["recs"].values(), key=lambda x: (order.get(x["type"], 3), x["np"]))
        new_recs: list = []

        def flush_recs():
            """Insert the queued new records (ids made here, so a record and the
            container it sits in can go in the same batch, container first)."""
            nonlocal writes
            if not new_recs:
                return
            cur = conn.cursor()
            cur.executemany("""insert into kb.nodes (id, type_id, name, props, external_id, review_status, status, imported_at,
                                                     scope_id, body, is_legacy, imported_version)
                               values (%s, %s, %s, %s, %s, %s, 'active', now(), %s, %s, %s, 1)""",
                            [(nid, types[r["type"]], r["name"], json.dumps(r["props"]), "np:" + r["np"],
                              "needs_review" if r["review"] else "none", scope, r.get("body"), r["legacy"])
                             for r, nid, scope, cs in new_recs])
            cur.executemany("insert into kb.node_tags (node_id, tag_id) values (%s, %s) on conflict do nothing",
                            [(nid, tag_ids[t]) for r, nid, scope, cs in new_recs for t in r["tags"]])
            have = _kb_records(conn, [nid for _, nid, _, _ in new_recs])
            mark_many([("record", r["np"], "nodes", nid, cs, _h(have[nid])) for r, nid, scope, cs in new_recs])
            for r, _, _, _ in new_recs:
                out["created"][f"record: {r['type']}" + (" (legacy)" if r["legacy"] else "")] += 1
            writes += len(new_recs)
            new_recs.clear()
            checkpoint()

        # owners refer to records, so they are written in a second pass
        flusher[0] = flush_recs
        for r in recs:
            key = r["np"]
            rkey = [order.get(r["type"], 3), key]
            if done_before("records", rkey):
                m = smap.get(("record", key))
                if m or key in ext:
                    kb_rec[key] = m["kb_id"] if m else ext[key]
                continue
            at("records", rkey)
            scope = kb_rec.get(r["scope_np"]) if r["scope_np"] else None
            content = {"name": r["name"], "props": r["props"], "scope": scope, "body": r.get("body"), "legacy": r["legacy"],
                       "tags": r["tags"], "review": r["review"], "type": r["type"]}
            cs = _h(content)
            m = smap.get(("record", key))
            if m is None and key in ext:                      # written by the first import: adopt it
                kb_rec[key] = ext[key]
                cur = _kb_record(conn, ext[key])
                mark("record", key, "nodes", ext[key], "adopted", _h(cur["content"]))
                m = {"kb_id": ext[key], "checksum": "adopted", "kb_checksum": _h(cur["content"]), "removed": None, "conflict": None}
                out["adopted"]["record"] += 1
            if m is None:
                kb_rec[key] = nid = str(uuid.uuid4())
                new_recs.append((r, nid, scope, cs))
                if len(new_recs) >= batch:
                    flush_recs()
                continue
            kb_rec[key] = m["kb_id"]
            if m["removed"]:
                out["restored_at_source"]["record"] += 1
            if m["checksum"] == cs and not m["removed"]:
                if m["conflict"]:
                    # the source went back to what the sync last wrote: nothing to reconcile any more
                    conn.execute("update kb.sync_map set conflict_at = null, conflict_checksum = null where unit = 'record' and key = %s", (key,))
                    out["conflicts_cleared"]["record"] += 1
                out["unchanged"]["record"] += 1; seen("record", key); continue
            flush_recs()                                    # an update may point at a queued container
            cur = _kb_record(conn, m["kb_id"])
            if cur is None:
                out["errors"].append(f"record {key}: its KB record is gone"); continue
            if cur["archived"]:
                out["skipped_archived"]["record"] += 1; seen("record", key); continue
            if m["kb_checksum"] and _h(cur["content"]) != m["kb_checksum"]:
                conflict("record", key, cs); out["conflicts"]["record"] += 1; continue
            conn.execute("""update kb.nodes set name = %s, props = %s, scope_id = %s, body = %s, is_legacy = %s,
                            review_status = case when %s then 'needs_review' else review_status end
                            where id = %s""",
                         (r["name"], json.dumps(r["props"]), scope, r.get("body"), r["legacy"], r["review"], m["kb_id"]))
            _set_tags(conn, m["kb_id"], r["tags"], tag_ids)
            mark("record", key, "nodes", m["kb_id"], cs, _h(_kb_record(conn, m["kb_id"])["content"]))
            out["updated"]["record"] += 1
            writes += 1; checkpoint()
        flush_recs()
        # owners by role (second pass): only where the KB owner-by-role was not changed in the app
        owners_now = {str(i): (o, c, a) for i, o, c, a in q("""select id, owner_record_id, co_owner_record_ids, archived_at
                                                               from kb.nodes where external_id like 'np:%%'""")}
        flusher[0] = None
        for r in recs:
            nid = kb_rec.get(r["np"])
            if not nid or done_before("owners", [order.get(r["type"], 3), r["np"]]):
                continue
            at("owners", [order.get(r["type"], 3), r["np"]])
            want_o = kb_rec.get(r["owner_np"]) if r["owner_np"] else None
            want_c = [kb_rec[x] for x in r["co_np"] if x in kb_rec]
            okey = r["np"] + "#owners"
            ocs = _h({"o": want_o, "c": want_c})
            m = smap.get(("record", okey))
            cur = owners_now.get(nid)
            if not cur or cur[2]:
                continue
            have = {"o": str(cur[0]) if cur[0] else None, "c": [str(x) for x in cur[1]]}
            if m and m["checksum"] == ocs:
                seen("record", okey); continue
            if m and m["kb_checksum"] and _h(have) != m["kb_checksum"]:
                conflict("record", okey, ocs); out["conflicts"]["owners"] += 1; continue
            if not want_o and not want_c and not m:
                continue
            conn.execute("update kb.nodes set owner_record_id = %s, co_owner_record_ids = %s::uuid[] where id = %s",
                         (want_o, want_c, nid))
            conn.execute("select kb.apply_person_owner(x) from unnest(%s::uuid[]) x",
                         ([x for x in [want_o] + want_c if x],))
            mark("record", okey, "nodes", nid, ocs, _h({"o": want_o, "c": want_c}))
            out["updated" if m else "created"]["owners by role"] += 1
            writes += 1; checkpoint()

        # -- links ------------------------------------------------------------------------------
        kb_link: dict[str, str] = {}
        kinds = [(k, pats) for k, pats in q("select key, patterns from kb.link_kinds where archived_at is null order by sort_order")]

        def detect(url):                     # = typedefs.detect_link_kind, with the patterns read once
            for k, pats in kinds:
                for pat in pats:
                    try:
                        if re.search(pat, url, re.I):
                            return k
                    except re.error:
                        continue
            return "website"
        res_now = {r[0]: r[1:] for r in q("select url_norm, id, title, kind, link_kind, tags from kb.resources")}
        new_links: list = []

        def flush_links():
            nonlocal writes
            if not new_links:
                return
            conn.cursor().executemany("""insert into kb.resources (id, url, title, kind, link_kind, tags, external_id, imported_at,
                                                                   imported_version) values (%s, %s, %s, %s, %s, %s, %s, now(), 1)""",
                                      [(rid, L["url"], L["title"], L["kind"], lk, L["tags"],
                                        "np:url:" + hashlib.sha1(key.encode()).hexdigest()[:20]) for key, L, lk, rid, cs in new_links])
            have = _kb_links(conn, [rid for *_, rid, _ in new_links])
            mark_many([("link", key, "resources", rid, cs, _h(have[rid])) for key, L, lk, rid, cs in new_links])
            out["created"]["link"] += len(new_links)
            writes += len(new_links)
            new_links.clear()
            checkpoint()
        flusher[0] = flush_links
        for key, L in sorted(D["links"].items()):
            if done_before("links", key):
                m = smap.get(("link", key))
                hit = res_now.get(key)
                if m or hit:
                    kb_link[key] = m["kb_id"] if m else str(hit[0])
                continue
            at("links", key)
            lk = detect(L["url"])
            content = {"url": L["url"], "title": L["title"], "kind": L["kind"], "link_kind": lk, "tags": L["tags"]}
            cs = _h(content)
            m = smap.get(("link", key))
            if m is None:
                hit = res_now.get(key)
                if hit:                                         # already in the KB (made by hand, or an earlier import)
                    kb_link[key] = str(hit[0])
                    mark("link", key, "resources", kb_link[key], cs if tuple(hit[1:5]) == (L["title"], L["kind"], lk, L["tags"]) else "adopted",
                         _h(_kb_link(conn, kb_link[key])))
                    out["adopted"]["link"] += 1
                    continue
                kb_link[key] = rid = str(uuid.uuid4())
                res_now[key] = (rid, L["title"], L["kind"], lk, L["tags"])
                new_links.append((key, L, lk, rid, cs))
                if len(new_links) >= batch:
                    flush_links()
                continue
            kb_link[key] = m["kb_id"]
            if m["checksum"] == cs and not m["removed"]:
                out["unchanged"]["link"] += 1; seen("link", key); continue
            have = _kb_link(conn, m["kb_id"])
            if m["kb_checksum"] and _h(have) != m["kb_checksum"]:
                conflict("link", key, cs); out["conflicts"]["link"] += 1; continue
            conn.execute("update kb.resources set title = %s, kind = %s, link_kind = %s, tags = %s where id = %s",
                         (L["title"], L["kind"], lk, L["tags"], m["kb_id"]))
            mark("link", key, "resources", m["kb_id"], cs, _h(_kb_link(conn, m["kb_id"])))
            out["updated"]["link"] += 1; writes += 1; checkpoint()

        flush_links()
        # -- relationships ---------------------------------------------------------------------
        edges_now = {(str(t), str(s_), str(g)): str(i) for i, t, s_, g in
                     q("select id, edge_type_id, source_id, target_id from kb.edges where archived_at is null")}
        new_rels: list = []

        def flush_rels():
            nonlocal writes
            if not new_rels:
                return
            conn.cursor().executemany("""insert into kb.edges (id, edge_type_id, source_id, target_id, note, props, external_id)
                                         values (%s, %s, %s, %s, %s, %s, %s)""",
                                      [(eid, etypes[d["type"]], src, tgt, d["note"], json.dumps(d["props"]), "np:e" + str(d["edges"][0]))
                                       for key, d, src, tgt, eid, cs in new_rels])
            have = _kb_edges(conn, [x[4] for x in new_rels])
            mark_many([("relationship", key, "edges", eid, cs, _h(have[eid])) for key, d, src, tgt, eid, cs in new_rels])
            for _, d, *_ in new_rels:
                out["created"][f"relationship: {d['type']}"] += 1
            writes += len(new_rels)
            new_rels.clear()
            checkpoint()
        flusher[0] = flush_rels
        for key, d in sorted(D["rels"].items()):
            if done_before("relationships", key):
                continue
            at("relationships", key)
            src, tgt = kb_rec.get(d["src"]), kb_rec.get(d["tgt"])
            if not src or not tgt:
                continue
            stype, ttype = D["recs"][d["src"]]["type"], D["recs"][d["tgt"]]["type"]
            if svc.edge_rule_problem(rules, d["type"], stype, ttype):
                out["report"]["problems"]["relationship_not_allowed"].append(key); continue
            content = {"props": d["props"], "note": d["note"]}
            cs = _h(content)
            m = smap.get(("relationship", key))
            if m is None:
                hit = edges_now.get((str(etypes[d["type"]]), src, tgt))
                if hit:
                    eid = hit
                    conn.execute("update kb.edges set props = %s, note = coalesce(%s, note) where id = %s",
                                 (json.dumps(d["props"]), d["note"], eid))
                    mark("relationship", key, "edges", eid, cs, _h(_kb_edge(conn, eid)))
                    out["adopted"]["relationship"] += 1; writes += 1; checkpoint(); continue
                eid = str(uuid.uuid4())
                edges_now[(str(etypes[d["type"]]), src, tgt)] = eid
                new_rels.append((key, d, src, tgt, eid, cs))
                if len(new_rels) >= batch:
                    flush_rels()
                continue
            if m["checksum"] == cs and not m["removed"]:
                out["unchanged"]["relationship"] += 1; seen("relationship", key); continue
            have = _kb_edge(conn, m["kb_id"])
            if have is None:
                continue
            if have.get("archived") and not m["removed"]:
                # archived in the KB (by hand, or with a legacy record): left as it is
                out["skipped_archived"]["relationship"] += 1; continue
            if m["removed"] and have.get("archived"):
                conn.execute("update kb.edges set archived_at = null, status = 'active' where id = %s", (m["kb_id"],))
                out["restored_at_source"]["relationship"] += 1
            elif m["kb_checksum"] and _h(have) != m["kb_checksum"]:
                conflict("relationship", key, cs); out["conflicts"]["relationship"] += 1; continue
            conn.execute("update kb.edges set props = %s, note = %s where id = %s", (json.dumps(d["props"]), d["note"], m["kb_id"]))
            mark("relationship", key, "edges", m["kb_id"], cs, _h(_kb_edge(conn, m["kb_id"])))
            out["updated"]["relationship"] += 1; writes += 1; checkpoint()

        flush_rels()
        # -- links on records ---------------------------------------------------------------------
        att_now: dict = {}
        for i, n_, r_, arch in q("select id, node_id, resource_id, archived_at from kb.node_resources order by archived_at nulls first"):
            att_now.setdefault((str(n_), str(r_)), (str(i), arch))
        new_att: list = []

        def flush_att():
            nonlocal writes
            if not new_att:
                return
            conn.cursor().executemany("insert into kb.node_resources (id, node_id, resource_id, note) values (%s, %s, %s, %s)",
                                      [(aid, nid, rid, a["note"]) for key, a, nid, rid, aid, cs in new_att])
            mark_many([("attachment", key, "node_resources", aid, cs, cs) for key, a, nid, rid, aid, cs in new_att])
            out["created"]["attachment"] += len(new_att)
            writes += len(new_att)
            new_att.clear()
            checkpoint()
        flusher[0] = flush_att
        for key, a in sorted(D["attachments"].items()):
            if done_before("attachments", key):
                continue
            at("attachments", key)
            nid, rid = kb_rec.get(a["rec"]), kb_link.get(a["link"])
            if not nid or not rid:
                continue
            cs = _h({"note": a["note"]})
            m = smap.get(("attachment", key))
            if m and m["checksum"] == cs and not m["removed"]:
                out["unchanged"]["attachment"] += 1; seen("attachment", key); continue
            h = att_now.get((nid, rid))
            hit = [h] if h else []
            if hit and hit[0][1] is not None and m and not m["removed"]:
                out["skipped_archived"]["attachment"] += 1; continue
            if hit and hit[0][1] is None:
                aid = str(hit[0][0])
                if m is None:
                    out["adopted"]["attachment"] += 1
            elif hit and m and m["removed"]:
                aid = str(hit[0][0])
                conn.execute("update kb.node_resources set archived_at = null, status = 'active' where id = %s", (aid,))
                out["restored_at_source"]["attachment"] += 1
            else:
                aid = str(uuid.uuid4())
                att_now[(nid, rid)] = (aid, None)
                new_att.append((key, a, nid, rid, aid, cs))
                if len(new_att) >= batch:
                    flush_att()
                continue
            mark("attachment", key, "node_resources", aid, cs, cs)
            writes += 1; checkpoint()
        flush_att()

        # -- removed at source --------------------------------------------------------------
        live = {("record", k) for k in D["recs"]} | {("record", k + "#owners") for k in D["recs"]} | \
               {("link", k) for k in D["links"]} | {("relationship", k) for k in D["rels"]} | \
               {("attachment", k) for k in D["attachments"]}
        flusher[0] = None
        for (unit, key), m in sorted(smap.items()):
            if done_before("removed", unit + "|" + key):
                continue
            at("removed", unit + "|" + key)
            if (unit, key) in live or m["removed"] or key.endswith("#owners"):
                continue
            conn.execute("update kb.sync_map set removed_at = now() where unit = %s and key = %s", (unit, key))
            if unit == "record" and m["kb_id"]:
                # flagged, never deleted: shown on Data quality, marked for review
                conn.execute("update kb.nodes set review_status = 'needs_review' where id = %s and archived_at is null", (m["kb_id"],))
            elif unit == "relationship" and m["kb_id"]:
                conn.execute("update kb.edges set archived_at = now(), status = 'archived' where id = %s and archived_at is null", (m["kb_id"],))
            elif unit == "attachment" and m["kb_id"]:
                conn.execute("update kb.node_resources set archived_at = now(), status = 'archived' where id = %s and archived_at is null", (m["kb_id"],))
            out["removed_at_source"][unit] += 1
            writes += 1; checkpoint()

        # The rest (layout, legacy rules) is the run's short finish: it is never cut off.
        stopping[0] = True
        # -- layout: only where nobody placed the record yet --------------------------------------
        pts = [(kb_rec[n], x, y) for n, (x, y) in D["layout"].items() if n in kb_rec]
        if pts:
            conn.execute("""insert into kb.graph_positions (layout, node_id, x, y)
                            select 'default', n, x * %s, y * %s from unnest(%s::uuid[], %s::float8[], %s::float8[]) u(n, x, y)
                            on conflict (layout, node_id) do nothing""",
                         (LAYOUT_SCALE, LAYOUT_SCALE, [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]))
        # -- the connector's finishing step (NP Autopilot: the legacy rules,
        # pipeline/kb_legacy.py, on every run once adopted) --------------------------------
        src_conn.after_run(conn, out)
        checkpoint(force=True)
        out["status"] = "ok"
    except _OutOfTime:
        out["status"], out["partial"] = "ok", True
        out["message"] = (f"time budget reached in {(out.get('resume') or {}).get('phase', 'setup')}; "
                          "the next run continues from there")
    except Exception as exc:                                        # noqa: BLE001 - recorded, then re-raised
        conn.rollback()
        out["status"] = "error"
        out["errors"].append(f"{type(exc).__name__}: {str(exc)[:300]}")
        if run_id:
            _finish(conn, run_id, out)
        raise
    if not apply:
        conn.rollback()
    elif run_id:
        _finish(conn, run_id, out)
    for k in ("created", "updated", "unchanged", "conflicts", "removed_at_source", "restored_at_source", "adopted", "skipped_archived",
              "conflicts_cleared"):
        out[k] = dict(out[k])
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


class _OutOfTime(Exception):
    pass


def _key(k):
    """Resume keys compare as JSON stores them (a record's key is [order, id])."""
    return tuple(k) if isinstance(k, (list, tuple)) else (k,)


def _finish(conn, run_id, out):
    conn.rollback()
    conn.autocommit = True
    counts = {k: dict(out[k]) for k in ("created", "updated", "conflicts", "removed_at_source", "restored_at_source", "adopted",
                                        "conflicts_cleared")}
    counts["partial"] = out.get("partial", False)
    # An error keeps the previous resume point: the next run retries from where
    # the last good run stopped (its committed batches are kept either way).
    resume = out.get("resume") if out["status"] == "ok" else out.get("resumed_from")
    conn.execute("""update kb.sync_runs set finished_at = now(), status = %s, counts = %s, conflicts = %s, errors = %s, message = %s,
                           resume = %s
                    where id = %s""",
                 (out["status"], json.dumps(counts, default=str), sum(dict(out["conflicts"]).values()),
                  json.dumps(out["errors"]), out.get("message"), json.dumps(resume) if resume else None, run_id))
    conn.autocommit = False


def _kb_record(conn, nid):
    r = conn.execute("""select n.name, n.props, n.scope_id, n.body, n.is_legacy, n.archived_at,
                               coalesce(array(select g.name from kb.node_tags nt join kb.tags g on g.id = nt.tag_id
                                              where nt.node_id = n.id and g.name in ('legacy', 'boilerplate') order by g.name), '{}')
                        from kb.nodes n where n.id = %s""", (nid,)).fetchone()
    if not r:
        return None
    return {"content": {"name": r[0], "props": r[1], "scope": str(r[2]) if r[2] else None, "body": r[3],
                        "legacy": r[4], "tags": list(r[6])}, "archived": r[5] is not None}


def _kb_records(conn, ids) -> dict:
    """_kb_record's content for many records, in one query."""
    rows = conn.execute("""select n.id, n.name, n.props, n.scope_id, n.body, n.is_legacy,
                                  coalesce(array(select g.name from kb.node_tags nt join kb.tags g on g.id = nt.tag_id
                                                 where nt.node_id = n.id and g.name in ('legacy', 'boilerplate') order by g.name), '{}')
                           from kb.nodes n where n.id = any(%s::uuid[])""", (ids,)).fetchall()
    return {str(r[0]): {"name": r[1], "props": r[2], "scope": str(r[3]) if r[3] else None, "body": r[4],
                        "legacy": r[5], "tags": list(r[6])} for r in rows}


def _kb_links(conn, ids) -> dict:
    rows = conn.execute("select id, title, kind, link_kind, tags from kb.resources where id = any(%s::uuid[])", (ids,)).fetchall()
    return {str(r[0]): {"title": r[1], "kind": r[2], "link_kind": r[3], "tags": list(r[4] or [])} for r in rows}


def _kb_edges(conn, ids) -> dict:
    rows = conn.execute("select id, props, note, archived_at from kb.edges where id = any(%s::uuid[])", (ids,)).fetchall()
    return {str(r[0]): {"props": r[1], "note": r[2], "archived": r[3] is not None} for r in rows}


def _sync_tags(conn) -> dict:
    """The sync's own tags (legacy, boilerplate): their ids, created once."""
    out = {}
    for t in ("legacy", "boilerplate"):
        row = conn.execute("select id from kb.tags where name_norm = kb.norm(%s) and archived_at is null", (t,)).fetchone()
        if not row:
            row = conn.execute("insert into kb.tags (name) values (%s) returning id", (t,)).fetchone()
        out[t] = row[0]
    return out


def _kb_link(conn, rid):
    r = conn.execute("select title, kind, link_kind, tags from kb.resources where id = %s", (rid,)).fetchone()
    return {"title": r[0], "kind": r[1], "link_kind": r[2], "tags": list(r[3] or [])} if r else None


def _kb_edge(conn, eid):
    r = conn.execute("select props, note, archived_at from kb.edges where id = %s", (eid,)).fetchone()
    return {"props": r[0], "note": r[1], "archived": r[2] is not None} if r else None


def _set_tags(conn, nid, tags, tag_ids):
    """The sync's own tags (legacy, boilerplate) follow the source; other tags are the app's."""
    for t, tid in tag_ids.items():
        if t in tags:
            conn.execute("insert into kb.node_tags (node_id, tag_id) values (%s, %s) on conflict do nothing", (nid, tid))
        else:
            conn.execute("delete from kb.node_tags where node_id = %s and tag_id = %s", (nid, tid))


def ensure_config(conn, M, actor_id, operator=False):
    """The record types, fields and relationship types the mapping needs.
    Created once (by an admin: the CLI's --as, or "Sync now"); a scheduled run
    without them stops and says so."""
    from . import typedefs as td
    from .service import Actor
    types = {t["key"]: t for t in td.all_types(conn, include_archived=True)["node_types"]}
    edges = {e["key"] for e in td.all_types(conn, include_archived=True)["edge_types"]}
    missing_types = [nt for nt in M["new_record_types"] if nt["key"] not in types]
    missing_edges = [et for et in M["new_relationship_types"] if et["key"] not in edges]
    missing_fields = {k: [f for f in fs if td.slug(f["label"]) not in {x["key"] for x in types[k]["fields"]}]
                      for k, fs in M["type_fields"].items() if k in types}
    missing_parents = {k: ps for k, ps in M["placement"].items() if k in types and not set(ps) <= set(types[k].get("allowed_parents") or [])}
    if not (missing_types or missing_edges or any(missing_fields.values()) or missing_parents):
        return
    if not actor_id and not operator:
        raise RuntimeError("the KB configuration for the sync is missing; run the first import "
                           "(pipeline/kb_import_projection.py apply --as <admin> or --operator)")
    admin = Actor(actor_id, "human")
    for nt in missing_types:
        td.create_node_type(conn, admin, {k: v for k, v in nt.items() if k != "key"}, approved=True)
    types = {t["key"]: t for t in td.all_types(conn, include_archived=True)["node_types"]}
    for key in set(M["type_fields"]) | set(M["placement"]):
        t = types[key]
        have = {f["key"] for f in t["fields"]}
        add = [f for f in M["type_fields"].get(key, []) if td.slug(f["label"]) not in have]
        parents = sorted(set(t.get("allowed_parents") or []) | set(M["placement"].get(key, [])))
        if add or parents != sorted(t.get("allowed_parents") or []):
            td.update_node_type(conn, admin, key, {"version": t["version"], "fields": t["fields"] + add,
                                                   "allowed_parents": parents}, approved=True)
    for et in missing_edges:
        td.create_edge_type(conn, admin, dict(et), approved=True)
