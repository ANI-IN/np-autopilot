"""Drive FOLDER links for row-B modules and sessions (B4 (i), 2026-09-30).

pipeline/list_folders.py records every row-B folder (id, name, path, parent).
This decides which folder belongs to which module and which session, from the
folder PATHS — the same module shapes pass 7 uses for files
(content_model.parse_module), so a file and its folder can never disagree about
the module they are in.

A MODULE has up to two folders: its content folder ("Module-3: API Design",
"Content Repo/Week 3/5 - …") and its "Uplevel Shared/Week N/…" folder. Both
are linked, content first.

A SESSION's folder is a FIRST-LEVEL subfolder of one of its module's folders,
matched by name (SESSION_RULES). Where nothing matches, the session carries an
empty list and the UI says "No folder for this session" — never a guess, never
the module folder standing in for it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.lib import content_model as cm

FOLDER_URL = "https://drive.google.com/drive/folders/{}"

#: session kind -> subfolder-name pattern. Reviewed against all 479 row-B
#: folders on 2026-09-30. Assignment REVIEWS have no folder of their own
#: anywhere in row B, so they have no rule: absence is the answer.
SESSION_RULES = {
    "pre_class": re.compile(r"foundation(al)?\s+materials?", re.I),
    "class": re.compile(r"live[\s_]*class|^slides?$", re.I),
    "alternate_class": re.compile(r"live[\s_]*class|^slides?$", re.I),
    "task": re.compile(r"assignment|timed[\s-]*test", re.I),
    "post_class": re.compile(r"practice\s+problem", re.I),
}
_UPLEVEL = re.compile(r"/uplevel shared/", re.I)


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


def _entry(fid: str, v: dict, where: str) -> dict:
    return {"url": FOLDER_URL.format(fid), "name": _norm(v["name"]), "where": where}


def module_folders(folders: dict) -> dict:
    """{(domain folder, sequence): [{url, name, where, id}]}, content first."""
    out: dict = {}
    for fid, v in folders.items():
        ref = cm.parse_module(v["path"])
        if not ref:
            continue
        parent = v["path"].rsplit("/", 1)[0]
        if cm.parse_module(parent) == ref:
            continue                                  # inside the module, not its root
        where = "uplevel shared" if _UPLEVEL.search(v["path"] + "/") else "content"
        out.setdefault((ref.domain, ref.sequence), []).append(
            dict(_entry(fid, v, where), id=fid))
    for k in out:
        out[k].sort(key=lambda e: (e["where"] != "content", e["name"]))
    return out


def session_folders(folders: dict, modules: dict | None = None) -> dict:
    """{(domain folder, sequence, kind): [{url, name, where}]} — only matches."""
    modules = modules if modules is not None else module_folders(folders)
    children: dict = {}
    for fid, v in folders.items():
        children.setdefault(v["parent"], []).append((fid, v))
    out: dict = {}
    for key, roots in modules.items():
        for root in roots:
            for fid, v in sorted(children.get(root["id"], []), key=lambda x: x[1]["name"]):
                for kind, rx in SESSION_RULES.items():
                    if rx.search(_norm(v["name"])):
                        out.setdefault((*key, kind), []).append(
                            _entry(fid, v, root["where"]))
    return out


def public(entries: list) -> list:
    """What goes on a node: url, name, where — never the internal id."""
    return [{k: e[k] for k in ("url", "name", "where")} for e in entries]
