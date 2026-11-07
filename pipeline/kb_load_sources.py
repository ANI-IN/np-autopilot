#!/usr/bin/env python3
"""Load the source catalog (registry crawl + KYP pages) into kb.sources, and link the Drive folders the
registry names to their domain and module.

    python pipeline/kb_load_sources.py plan  --db local|dev
    python pipeline/kb_load_sources.py apply --db local|dev

Inputs (local, gitignored): .measure/sources/catalog.json and failures.json (pipeline/kb_registry_crawl.py),
.measure/kyp-c/curriculum.json (pipeline/kb_kyp_extract.py).

kb.sources (migration 0040): one row per (provider, resource id) with the LIVE url, version / modified
time, size, provenance (how the registry reaches it) and status. A re-load updates rows by id (a new
version or modified time sets last_changed) and marks a source the crawl no longer reached as removed
(kept, never deleted). Every access failure is a row with its reason.

Folder links (traceable, no guessing): under a domain folder the registry names ("SD3: Backend
Engineering" -> Backend, by the hidden aliases in config/kb-curriculum-scope.yaml):
  * the domain folder itself is attached to the domain;
  * a sub-folder named "Module-<n>: <name>" is attached to the module with exactly that name that is
    classified in that domain.
Anything that does not match exactly is left alone (and counted).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipeline.lib.db import PROD_PROJECT_REF as PRODUCTION_REF       # noqa: E402

LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
SCOPE = yaml.safe_load((REPO / "config" / "kb-curriculum-scope.yaml").read_text(encoding="utf-8"))
G = "application/vnd.google-apps."
KIND = {G + "folder": "folder", G + "document": "document", G + "presentation": "presentation", G + "spreadsheet": "spreadsheet",
        G + "form": "form", G + "shortcut": "shortcut", "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "powerpoint",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
        "application/msword": "word (legacy)", "application/vnd.ms-powerpoint": "powerpoint (legacy)",
        "application/vnd.ms-excel": "excel (legacy)"}
NOTE_DOMAIN = "Domain folder (registry)"
NOTE_MODULE = "Module folder (registry)"


def db_url(which):
    if which == "local":
        return LOCAL
    if which == "dev":
        from dotenv import dotenv_values
        u = dotenv_values(REPO / ".env").get("DEV_SUPABASE_DB_URL") or ""
        if not u:
            sys.exit("DEV_SUPABASE_DB_URL is not set")
        return u
    sys.exit("use --db local or --db dev")


def kind_of(mime: str | None, fallback: str | None = None) -> str:
    m = mime or ""
    if m in KIND:
        return KIND[m]
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "video"
    if m.startswith("image/"):
        return "image"
    return fallback or "other"


def domain_of_folder(name: str) -> str | None:
    for d in SCOPE["domains"]:
        for a in d["aliases"]:
            if ":" in a and name.strip().lower() == a.lower():
                return d["name"]
    return None


def rows_from_inputs() -> tuple[list[dict], dict]:
    cat = json.loads((REPO / ".measure/sources/catalog.json").read_text(encoding="utf-8"))
    fails = json.loads((REPO / ".measure/sources/failures.json").read_text(encoding="utf-8"))
    cur = json.loads((REPO / ".measure/kyp-c/curriculum.json").read_text(encoding="utf-8"))
    out, seen = [], set()
    fail_by_id = {}
    for f in fails:
        if f.get("resource_id"):
            fail_by_id.setdefault(f["resource_id"], f)
    for it in cat["items"]:
        ex = it.get("extract") or {}
        f = fail_by_id.get(it["resource_id"])
        status = it["status"] if it["status"] in ("extracted", "extracted_empty", "listed", "media_listed", "failed") else "listed"
        out.append({"provider": "drive", "resource_id": it["resource_id"], "kind": kind_of(it["mime"]), "title": it.get("title"),
                    "url": it["url"], "mime": it["mime"], "version": str(it.get("version") or "") or None,
                    "modified_at": it.get("modified_time"), "size_bytes": it.get("size"), "md5": it.get("md5"),
                    "parent_resource_id": it.get("parent_id"), "provenance": it.get("provenance") or [],
                    "status": status, "failure_reason": (f or {}).get("reason") if status == "failed" else None,
                    "text_chars": ex.get("chars"), "text_sha1": ex.get("sha1"), "extracted_at": ex.get("at")})
        seen.add(("drive", it["resource_id"]))
    for f in fails:
        rid = f.get("resource_id")
        prov = "drive" if rid else "web"
        rid = rid or "url:" + hashlib.sha1(f["link"].encode()).hexdigest()[:20]
        if (prov, rid) in seen:
            continue
        seen.add((prov, rid))
        out.append({"provider": prov, "resource_id": rid, "kind": kind_of(None, f.get("kind") or "link"), "title": None,
                    "url": f["link"], "mime": None, "version": None, "modified_at": None, "size_bytes": None, "md5": None,
                    "parent_resource_id": None, "provenance": [f.get("context") or ""], "status": "failed",
                    "failure_reason": f["reason"], "text_chars": None, "text_sha1": None, "extracted_at": None})
    imported = {pv["page_id"] for k in ("programs", "courses") for x in cur[k]
                for pv in ([x["provenance"]] + x.get("also_from", []))}
    for p in cur["pages"]:
        status = "do_not_use" if p["do_not_use"] else "deferred" if p["deferred"] else "imported" if p["page_id"] in imported else "listed"
        out.append({"provider": "confluence", "resource_id": p["page_id"], "kind": "page", "title": p["title"], "url": p["url"],
                    "mime": None, "version": str(p["version"]), "modified_at": p.get("modified"), "size_bytes": None, "md5": None,
                    "parent_resource_id": None, "provenance": [p["root"] or ""], "status": status,
                    "failure_reason": None, "text_chars": None, "text_sha1": None, "extracted_at": None})
        imported.discard(None)
    for pid in sorted(imported - {p["page_id"] for p in cur["pages"]}):      # included pages (outlines, domain courses)
        pv = next(pv for k in ("programs", "courses") for x in cur[k] for pv in ([x["provenance"]] + x.get("also_from", [])) if pv["page_id"] == pid)
        out.append({"provider": "confluence", "resource_id": pid, "kind": "page", "title": pv["page_title"], "url": pv["url"], "mime": None,
                    "version": str(pv["page_version"]), "modified_at": pv.get("page_modified"), "size_bytes": None, "md5": None,
                    "parent_resource_id": None, "provenance": ["included by a KYP page"], "status": "imported",
                    "failure_reason": None, "text_chars": None, "text_sha1": None, "extracted_at": None})
    for a in cur["attachments"]:
        rid = "att:" + a["on_page_id"] + ":" + hashlib.sha1((a.get("name") or "").encode()).hexdigest()[:12]
        out.append({"provider": "confluence", "resource_id": rid, "kind": "attachment", "title": a.get("name"),
                    "url": next((p["url"] for p in cur["pages"] if p["page_id"] == a["on_page_id"]), "confluence:page:" + a["on_page_id"]),
                    "mime": a.get("media_type"), "version": None, "modified_at": None, "size_bytes": a.get("size_bytes"), "md5": None,
                    "parent_resource_id": a["on_page_id"], "provenance": [a.get("on_page_title") or ""], "status": "attachment_listed",
                    "failure_reason": None, "text_chars": None, "text_sha1": None, "extracted_at": None})
    return out, {"catalog_generated": cat["generated"], "kyp_generated": cur["generated"]}


COLS = ("provider", "resource_id", "kind", "title", "url", "mime", "version", "modified_at", "size_bytes", "md5",
        "parent_resource_id", "provenance", "status", "failure_reason", "text_chars", "text_sha1", "extracted_at")


def load(conn, rows) -> dict:
    st = Counter()
    have = {(p, r): (v, m) for p, r, v, m in conn.execute("select provider, resource_id, version, modified_at::text from kb.sources")}
    for r in rows:
        key = (r["provider"], r["resource_id"])
        vals = [r[c] for c in COLS]
        if key not in have:
            conn.execute(f"insert into kb.sources ({', '.join(COLS)}) values ({', '.join(['%s'] * len(COLS))})", vals)
            st["new"] += 1
            continue
        old_v, old_m = have[key]
        changed = (str(old_v or "") != str(r["version"] or "")) or (bool(r["modified_at"]) and (old_m or "")[:19].replace(" ", "T") != str(r["modified_at"])[:19])
        sets = ", ".join(f"{c} = %s" for c in COLS[2:])
        conn.execute(f"""update kb.sources set {sets}, last_seen = now(), removed_at = null,
                         last_changed = case when %s then now() else last_changed end
                         where provider = %s and resource_id = %s""", vals[2:] + [changed, key[0], key[1]])
        st["changed" if changed else "unchanged"] += 1
    keys = [(r["provider"], r["resource_id"]) for r in rows]
    for prov in ("drive", "confluence", "web"):
        ids = [k[1] for k in keys if k[0] == prov]
        st[f"removed_{prov}"] = conn.execute("""update kb.sources set removed_at = now() where provider = %s and removed_at is null
                                                and not (resource_id = any(%s))""", (prov, ids)).rowcount
    return dict(st)


def link_folders(conn, rows) -> dict:
    st = Counter()
    doms = {n: str(i) for i, n in conn.execute("""select n.id, n.name from kb.nodes n join kb.node_types t on t.id = n.type_id
                                                   where t.key = 'domain' and n.archived_at is null""")}
    folders = [r for r in rows if r["provider"] == "drive" and r["kind"] == "folder"]
    by_id = {r["resource_id"]: r for r in folders}

    def attach(node_id, r, note):
        res = conn.execute("select id from kb.resources where url = %s and archived_at is null", (r["url"],)).fetchone()
        if res is None:
            res = conn.execute("insert into kb.resources (url, title, kind, link_kind) values (%s, %s, 'folder', 'drive_folder') returning id",
                               (r["url"], r["title"])).fetchone()
            st["resource_created"] += 1
        if not conn.execute("select 1 from kb.node_resources where node_id = %s and resource_id = %s and archived_at is null", (node_id, res[0])).fetchone():
            conn.execute("insert into kb.node_resources (node_id, resource_id, note) values (%s, %s, %s)", (node_id, res[0], note))
            st["attached"] += 1
        else:
            st["already_attached"] += 1

    for r in folders:
        d = domain_of_folder(r["title"] or "")
        if d and d in doms:
            attach(doms[d], r, NOTE_DOMAIN)
            st["domain_folders"] += 1
            continue
        m = re.match(r"^\s*Module\s*-?\s*\d+\s*:\s*(.+?)\s*$", r["title"] or "", re.I)
        if not m:
            continue
        parent = by_id.get(r.get("parent_resource_id"))
        d = domain_of_folder((parent or {}).get("title") or "")
        if not d or d not in doms:
            st["module_folder_no_domain_parent"] += 1
            continue
        mod = conn.execute("""select n.id from kb.nodes n join kb.node_types t on t.id = n.type_id and t.key = 'module'
                              join kb.edges e on e.source_id = n.id and e.archived_at is null and e.target_id = %s
                              join kb.edge_types et on et.id = e.edge_type_id and et.key = 'in_domain'
                              where n.archived_at is null and n.name_norm = kb.norm(%s)""", (doms[d], m.group(1))).fetchall()
        if len(mod) == 1:
            attach(str(mod[0][0]), r, NOTE_MODULE)
            st["module_folders"] += 1
        else:
            st["module_folder_unmatched"] += 1
    return dict(st)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "apply"))
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    url = db_url(a.db)
    if PRODUCTION_REF in url:
        print("refused: that is the production database"); return 2
    rows, meta = rows_from_inputs()
    print("inputs:", json.dumps(meta), json.dumps(Counter(f"{r['provider']}:{r['status']}" for r in rows)))
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("set statement_timeout = '600s'")
        conn.execute("select set_config('kb.actor_type', 'import', true), set_config('kb.operator', 'on', true)")
        t0 = time.monotonic()
        print("sources:", json.dumps(load(conn, rows)))
        print("folders:", json.dumps(link_folders(conn, rows)))
        if a.cmd == "plan":
            conn.rollback(); print("plan only: rolled back")
        else:
            conn.commit()
        print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
