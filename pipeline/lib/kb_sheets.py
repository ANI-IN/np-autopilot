"""Google Sheets → KB import: stage, validate, plan, apply (M8).

The source is the Sheets API `spreadsheets.values.batchGet` response shape —
{"spreadsheetId", "valueRanges": [{"range": "Tab!A1:Z", "values": [[...]]}]} —
whether it came from the live API or from a fixture file. Nothing here talks to
Google; pipeline/kb_import_sheets.py fetches.

Rules this module enforces, each tested in tests/test_kb_import.py:
  * ALLOW-LIST of columns (config/kb-sheets-mapping.yaml). A contact-shaped
    header is refused even if mapped — CLAUDE.md §2.
  * Cells are read POSITIONALLY; blanks are never compacted (CLAUDE.md, R5).
  * Multi-value cells split on ',' only; an empty token fails the ROW.
  * external_id = '<sheet id>:<tab>:<normalised key>' → re-running creates
    nothing new.
  * A record edited in the app since its last import (version moved past
    imported_version) is NEVER overwritten: it is reported as a conflict.
  * A live app record with the same name but no import identity is a
    DUPLICATE: reported, not created, not adopted.
  * Validation output COUNTS; it enumerates only rows a person must act on
    (CLAUDE.md §5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: Headers that look like contact data. Refused at mapping load AND at read.
CONTACT_HEADER = re.compile(r"e-?mail|phone|mobile|whats\s*app|linked\s*in|contact|address", re.I)
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*\.[^\s]*$", re.I)


def norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


class MappingError(Exception):
    pass


def load_mapping(path: Path) -> dict:
    m = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for tab, spec in (m.get("tabs") or {}).items():
        cols = list((spec.get("fields") or {}).values()) + list(spec.get("key") or [])
        cols += [l["column"] for l in spec.get("links") or []] + [l.get("scope_column") for l in spec.get("links") or []]
        cols += [a["column"] for a in spec.get("attach") or []] + [a.get("scope_column") for a in spec.get("attach") or []]
        if spec.get("scope"):
            cols.append(spec["scope"]["column"])
        bad = [c for c in cols if c and CONTACT_HEADER.search(c)]
        if bad:
            raise MappingError(f"tab {tab!r} maps contact-shaped column(s) {bad}; refused (CLAUDE.md §2)")
    return m


def parse_tabs(batch: dict) -> dict[str, dict]:
    """{tab: {"headers": [...], "rows": [(sheet_row_number, [cells...]), ...]}}."""
    out = {}
    for vr in batch.get("valueRanges") or []:
        tab = vr["range"].split("!")[0].strip("'")
        values = vr.get("values") or []
        if not values:
            out[tab] = {"headers": [], "rows": []}
            continue
        headers = [str(h).strip() for h in values[0]]
        rows = []
        for i, r in enumerate(values[1:], start=2):
            cells = [str(c) if c is not None else "" for c in r] + [""] * (len(headers) - len(r))
            if not any(c.strip() for c in cells):
                continue                      # a fully blank row is not a record
            rows.append((i, cells))
        out[tab] = {"headers": headers, "rows": rows}
    return out


@dataclass
class Staged:
    tab: str
    row: int
    entity: str
    type: str | None
    external_id: str | None
    values: dict
    links: list = field(default_factory=list)       # (edge, direction, other_type, name, scope_name)
    attach: list = field(default_factory=list)      # (type, name, scope_name)
    scope: tuple | None = None                      # (type, name)
    errors: list = field(default_factory=list)
    status: str = "pending"                         # create|update|unchanged|duplicate|conflict|invalid
    note: str = ""


def stage(mapping: dict, tabs: dict, sheet_id: str) -> list[Staged]:
    staged: list[Staged] = []
    for tab, spec in mapping["tabs"].items():
        data = tabs.get(tab)
        if data is None:
            continue
        idx = {norm(h): i for i, h in enumerate(data["headers"])}

        def cell(cells, col, _idx=idx):
            if not col:
                return ""
            i = _idx.get(norm(col))
            return cells[i].strip() if i is not None and i < len(cells) else ""

        for header in data["headers"]:
            if CONTACT_HEADER.search(header) and norm(header) in {norm(c) for c in (spec.get("fields") or {}).values()}:
                raise MappingError(f"{tab}: refusing contact-shaped column {header!r}")
        seen: dict[str, int] = {}
        for rownum, cells in data["rows"]:
            key_parts = [cell(cells, k) for k in spec["key"]]
            s = Staged(tab=tab, row=rownum, entity=spec["entity"], type=spec.get("type"), external_id=None,
                       values={f: cell(cells, c) for f, c in (spec.get("fields") or {}).items()})
            if not all(key_parts):
                s.errors.append(f"missing key column(s): {', '.join(k for k, p in zip(spec['key'], key_parts) if not p)}")
            else:
                key = "|".join(norm(p) for p in key_parts)
                s.external_id = f"{sheet_id}:{tab}:{key}"
                if key in seen:
                    s.errors.append(f"duplicate of row {seen[key]} (same {', '.join(spec['key'])})")
                else:
                    seen[key] = rownum
            if spec.get("scope"):
                sc = cell(cells, spec["scope"]["column"])
                s.scope = (spec["scope"]["type"], sc) if sc else None
            for l in spec.get("links") or []:
                raw = cell(cells, l["column"])
                if not raw:
                    continue
                names = [t.strip() for t in raw.split(",")] if l.get("multi") else [raw]
                if any(not t for t in names):
                    s.errors.append(f"{l['column']}: empty value in a list ({raw!r})")
                    continue
                for nm in names:
                    if "from_type" in l:
                        s.links.append((l["edge"], "in", l["from_type"], nm, cell(cells, l.get("scope_column"))))
                    else:
                        s.links.append((l["edge"], "out", l["to_type"], nm, cell(cells, l.get("scope_column"))))
            for a in spec.get("attach") or []:
                if a.get("only_if_blank") and cell(cells, a["only_if_blank"]):
                    continue
                nm = cell(cells, a["column"])
                if nm:
                    s.attach.append((a["type"], nm, cell(cells, a.get("scope_column"))))
            _validate_values(s)
            if s.errors:
                s.status = "invalid"
            staged.append(s)
    return staged


def _validate_values(s: Staged) -> None:
    if s.entity == "node":
        name = s.values.get("name", "")
        if not name:
            s.errors.append("name is blank")
        elif "@" in name or re.search(r"https?://", name, re.I):
            s.errors.append("name contains an address or URL")
        elif len(name) > 300:
            s.errors.append("name longer than 300 characters")
        if len(s.values.get("summary") or "") > 2000:
            s.errors.append("summary longer than 2000 characters")
    else:
        url = s.values.get("url", "")
        if not URL_RE.match(url) or len(url) > 2048:
            s.errors.append(f"invalid URL {url[:80]!r}")
        if not s.values.get("title"):
            s.errors.append("title is blank")
        kind = (s.values.get("kind") or "link").lower()
        if kind not in ("link", "doc", "sheet", "slides", "video", "pdf", "folder", "other"):
            s.errors.append(f"unknown kind {kind!r}")
        s.values["kind"] = kind


# ---------------------------------------------------------------------------
# plan + apply (need a connection scoped to the importing admin)
# ---------------------------------------------------------------------------

ORDER = {"program": 0, "course": 1, "module": 2, "topic": 3, "instructor": 4, "process": 5}


def _resolve(conn, svc, staged_by_name, type_key, name, scope_name=None):
    """Find a node by type + name (+ scope) — first among live DB rows, then
    among valid staged rows (which will exist after apply)."""
    scope_id = None
    if scope_name:
        sc = None
        for t in ("course", "program"):
            sc = svc.import_find_live(conn, t, scope_name)
            if sc:
                break
        if not sc:
            return ("staged" if (type_key, norm(name), norm(scope_name)) in staged_by_name else None)
        scope_id = sc["id"]
    hit = svc.import_find_live(conn, type_key, name, scope_id)
    if hit:
        return hit["id"]
    return "staged" if (type_key, norm(name), norm(scope_name or "")) in staged_by_name else None


def plan(conn, svc, staged: list[Staged]) -> dict:
    staged_by_name = {(s.type, norm(s.values.get("name", "")), norm(s.scope[1]) if s.scope else "")
                      for s in staged if s.entity == "node" and s.status != "invalid"}
    broken_refs = []
    for s in staged:
        if s.status == "invalid":
            continue
        if s.entity == "node":
            cur = svc.import_lookup_node(conn, s.external_id)
            if cur is None:
                scope_id = None
                if s.scope:
                    r = _resolve(conn, svc, staged_by_name, s.scope[0], s.scope[1])
                    if r is None:
                        s.status, s.note = "invalid", f"{s.scope[0]} {s.scope[1]!r} does not exist in the sheet or the app"
                        continue
                    scope_id = None if r == "staged" else r
                live = svc.import_find_live(conn, s.type, s.values["name"], scope_id) if (scope_id or not s.scope) else None
                if live:
                    s.status, s.note = "duplicate", f"a live {s.type} {live['name']!r} already exists in the app (id {live['id']}) without an import identity"
                else:
                    s.status = "create"
            elif cur["archived_at"]:
                s.status, s.note = "conflict", "archived in the app since import; not re-created"
            elif cur["version"] != cur["imported_version"]:
                s.status, s.note = "conflict", (f"edited in the app since the last import (v{cur['imported_version']} → "
                                                f"v{cur['version']}); sheet values NOT applied")
            elif cur["name"] != s.values["name"] or (cur["summary"] or "") != (s.values.get("summary") or ""):
                s.status = "update"
                s.note = "changed: " + ", ".join(f for f in ("name", "summary")
                                                 if (cur[f] or "") != (s.values.get(f) or ""))
            else:
                s.status = "unchanged"
        else:
            cur = svc.import_lookup_resource(conn, s.external_id)
            if cur is None:
                existing = svc.find_resource_by_url(conn, s.values["url"])
                s.status = "duplicate" if existing else "create"
                if existing:
                    s.note = f"URL already in the library as {existing['title']!r}; it will be linked, not re-created"
            elif cur["archived_at"]:
                s.status, s.note = "conflict", "archived in the app since import"
            elif cur["version"] != cur["imported_version"]:
                s.status, s.note = "conflict", "edited in the app since the last import; sheet values NOT applied"
            elif cur["title"] != s.values["title"] or cur["kind"] != s.values["kind"]:
                s.status = "update"
            else:
                s.status = "unchanged"
        for (edge, direction, other_type, nm, scope_nm) in s.links:
            if _resolve(conn, svc, staged_by_name, other_type, nm, scope_nm or None) is None:
                broken_refs.append({"tab": s.tab, "row": s.row, "edge": edge, "missing": f"{other_type} {nm!r}"
                                    + (f" in {scope_nm!r}" if scope_nm else "")})
        for (t, nm, scope_nm) in s.attach:
            if _resolve(conn, svc, staged_by_name, t, nm, scope_nm or None) is None:
                broken_refs.append({"tab": s.tab, "row": s.row, "attach": f"{t} {nm!r}" + (f" in {scope_nm!r}" if scope_nm else "")})
    return _report(staged, broken_refs)


def _report(staged, broken_refs) -> dict:
    counts = {k: 0 for k in ("create", "update", "unchanged", "duplicate", "conflict", "invalid")}
    for s in staged:
        counts[s.status] = counts.get(s.status, 0) + 1
    counts["broken_references"] = len(broken_refs)
    act_on = [{"tab": s.tab, "row": s.row, "status": s.status, "why": "; ".join(s.errors) or s.note}
              for s in staged if s.status in ("invalid", "conflict", "duplicate")]
    return {"counts": counts, "rows_needing_attention": act_on, "broken_references": broken_refs,
            "creates_by_tab": _by_tab(staged, "create"), "updates_by_tab": _by_tab(staged, "update")}


def _by_tab(staged, status):
    out = {}
    for s in staged:
        if s.status == status:
            out[s.tab] = out.get(s.tab, 0) + 1
    return out


def apply(conn, svc, actor, staged: list[Staged]) -> dict:
    """Execute a plan. Nodes in dependency order, then links, then resources and
    attachments. Every write goes through the service under the admin's RLS."""
    written = {"nodes_created": 0, "nodes_updated": 0, "edges_created": 0, "resources_created": 0,
               "resources_updated": 0, "attachments_created": 0, "skipped_races": 0}
    nodes = sorted((s for s in staged if s.entity == "node"), key=lambda s: ORDER.get(s.type, 9))
    for s in nodes:
        if s.status == "create":
            scope_id = None
            if s.scope:
                scope_id = _resolve(conn, svc, set(), s.scope[0], s.scope[1])
                if scope_id in (None, "staged"):
                    s.status, s.note = "invalid", "scope missing at apply time"
                    continue
            svc.import_create_node(conn, actor, type_key=s.type, name=s.values["name"],
                                   summary=s.values.get("summary") or None, scope_id=scope_id,
                                   external_id=s.external_id)
            written["nodes_created"] += 1
        elif s.status == "update":
            cur = svc.import_lookup_node(conn, s.external_id)
            if svc.import_update_node(conn, actor, cur["id"], cur["version"], name=s.values["name"],
                                      summary=s.values.get("summary") or None):
                written["nodes_updated"] += 1
            else:
                written["skipped_races"] += 1
    for s in nodes:
        if s.status in ("invalid", "conflict", "duplicate"):
            continue
        me = svc.import_lookup_node(conn, s.external_id)
        for (edge, direction, other_type, nm, scope_nm) in s.links:
            other = _resolve(conn, svc, set(), other_type, nm, scope_nm or None)
            if other in (None, "staged"):
                continue
            src, dst = (other, me["id"]) if direction == "in" else (me["id"], other)
            if not svc.import_edge_exists(conn, edge, src, dst):
                svc.create_edge(conn, actor, {"type": edge, "source_id": str(src), "target_id": str(dst)})
                written["edges_created"] += 1
    for s in staged:
        if s.entity != "resource" or s.status in ("invalid", "conflict"):
            continue
        if s.status == "create":
            svc.import_create_resource(conn, actor, url=s.values["url"], title=s.values["title"],
                                       kind=s.values["kind"], external_id=s.external_id)
            written["resources_created"] += 1
        elif s.status == "update":
            cur = svc.import_lookup_resource(conn, s.external_id)
            if svc.import_update_resource(conn, actor, cur["id"], cur["version"], title=s.values["title"],
                                          kind=s.values["kind"]):
                written["resources_updated"] += 1
        res = svc.import_lookup_resource(conn, s.external_id) or svc.find_resource_by_url(conn, s.values["url"])
        for (t, nm, scope_nm) in s.attach:
            nid = _resolve(conn, svc, set(), t, nm, scope_nm or None)
            if nid in (None, "staged") or not res:
                continue
            if not svc.import_attachment_exists(conn, nid, res["id"]):
                svc.attach_resource(conn, actor, str(nid), {"resource_id": str(res["id"]),
                                                            "note": f"imported from {s.tab} row {s.row}"})
                written["attachments_created"] += 1
    return written
