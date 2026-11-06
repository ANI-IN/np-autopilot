"""Activity log (run 3, B4; rebuilt for clarity in run 6, F3) and the
collaboration change feed.

Every entry comes from kb.audit_log, written only by the kb.audit() trigger and
append-only (0029), plus the content-free change events of 0032 (kb.changes
rows for graph_positions, person_accounts and sync_runs, which are not audited:
layout moves would flood the log, and person_accounts holds e-mail addresses).
Who may read which rows is decided by the database: the audit_log_select
policy (admin: all; editor: their own actions and their scope) and
kb.record_history() for a single record's History tab. The change-only events
are narrowed here by the same rule as the audit policy (admin: all; editor:
their own and those about records in their scope). Nothing here widens that;
filters only narrow it.

Each entry is ONE PLAIN SENTENCE built here, on the server, so the API, the
UI, the CSV export and the MCP tools say the same thing:

    WHO did WHAT to WHICH entity (old -> new where relevant)
    "Priya Sharma changed the owner of module 'Distributed Data' from Ravi to Anita"

`sentence` is the text; `parts` is the same sentence split into actor, text,
entity (with id, kind and a `deleted` mark when it no longer exists) and value
pieces, which the UI renders with textContent. Kind comes from
kb.changes.kind (0032). A named actor is always shown (owner bug A2): a
person (by name, never an e-mail address), the AI assistant acting for a named
person, an import, the sync, or the system. "Someone" never appears.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from . import validate as v
from .errors import Invalid

#: Where a change came from. "graph" is a layout move made on the Graph page
#: (layout.update). Other edits made from the Graph page go through the same
#: API calls as the rest of the app and carry no origin, so they read "app".
SOURCES = ("app", "graph", "ai", "import", "sync", "system")
ACTIONS = ("insert", "update", "delete")
CHANGE_ONLY = ("graph_positions", "person_accounts", "sync_runs")
TABLES = ("nodes", "edges", "resources", "node_resources", "node_tags", "node_types", "edge_types",
          "edge_type_rules", "link_kinds", "proposals", "flags", "templates", "saved_views", "memberships",
          "member_invites", "api_tokens", "import_runs", "tags") + CHANGE_ONLY
#: `op`: what happened, by the kind's verb (kb.changes.kind, 0032).
OPS = {
    "create": (["%.create", "%.insert"], []),
    "update": (["%.update"], ["layout.update"]),
    "owner": (["record.owner", "owner.account"], []),
    "archive": (["%.archive"], []),
    "restore": (["%.restore"], []),
    "delete": (["%.delete"], []),
    "attach": (["tag.attach", "link.attach"], []),
    "detach": (["tag.detach", "link.detach"], []),
    "layout": (["layout.update"], []),
    "sync": (["sync.run"], []),
}
# Columns that change on every write and say nothing to a reader.
NOISE = {"version", "updated_at", "updated_by", "search", "name_norm"}
# ...and columns that are bookkeeping, not something a person changed.
QUIET = NOISE | {"archived_at", "archived_with", "imported_at", "imported_version", "created_at", "created_by",
                 "url_norm", "last_used_at", "token_hash", "decided_at", "decided_by", "resolved_at", "resolved_by"}
#: Consecutive rows by the same actor doing the same thing within this many
#: seconds read as one entry ("updated 14 records"), expandable to the list.
GROUP_SECONDS = 5
GROUP_EXTEND = 500

FIELD_LABELS = {
    "name": "name", "summary": "summary", "body": "description", "status": "status",
    "review_status": "review status", "scope_id": "place", "owner_id": "owner", "co_owners": "co-owners",
    "owner_record_id": "owner by role", "co_owner_record_ids": "co-owners by role", "is_legacy": "legacy flag",
    "type_id": "record type", "external_id": "source id", "title": "title", "url": "URL", "kind": "kind",
    "link_kind": "link kind", "description": "description", "note": "note", "position": "position",
    "edge_type_id": "relationship type", "source_id": "source", "target_id": "target", "label": "label",
    "inverse_label": "inverse label", "plural": "plural label", "fields": "fields", "icon": "icon",
    "color": "colour", "shape": "shape", "line_style": "line style", "owner_expected": "owner expected",
    "allowed_parents": "allowed parents", "parent_required": "parent required", "cardinality": "cardinality",
    "merged_into": "merged into", "tags": "tags", "structure": "structure", "config": "settings",
    "shared": "sharing", "role": "role", "resolution": "resolution", "assigned_to": "assignee",
    "patterns": "patterns", "defaults": "defaults", "sort_order": "order", "default_status": "default status",
    "owner_rule": "owner rule", "is_container": "container flag", "expires_at": "expiry",
    "revoked_at": "revocation", "reason": "reason", "payload": "proposed change", "root_type": "root type",
}
# Values that are a choice from a list: shown plainly ("from active to draft"), not quoted.
ENUMS = {"status", "review_status", "kind", "link_kind", "role", "line_style", "shape", "cardinality", "icon",
         "color", "resolution", "root_type", "default_status", "owner_rule", "action", "target_table"}
USER_FIELDS = {"owner_id", "co_owners", "assigned_to", "user_id"}
RECORD_FIELDS = {"owner_record_id", "co_owner_record_ids", "scope_id", "source_id", "target_id", "node_id"}
NOUN = {"nodes": ("record", "records"), "edges": ("relationship", "relationships"), "resources": ("link", "links"),
        "node_resources": ("attachment", "attachments"), "node_tags": ("tag", "tags"), "tags": ("tag", "tags"),
        "node_types": ("record type", "record types"), "edge_types": ("relationship type", "relationship types"),
        "edge_type_rules": ("relationship rule", "relationship rules"), "link_kinds": ("link kind", "link kinds"),
        "proposals": ("proposal", "proposals"), "flags": ("flag", "flags"), "templates": ("template", "templates"),
        "saved_views": ("saved view", "saved views"), "memberships": ("member", "members"), "member_invites": ("invitation", "invitations"),
        "api_tokens": ("API token", "API tokens"), "import_runs": ("import", "imports"),
        "graph_positions": ("layout move", "layout moves"), "person_accounts": ("sign-in account", "sign-in accounts"),
        "sync_runs": ("sync run", "sync runs")}
VERB = {"create": "created", "insert": "created", "update": "updated", "archive": "archived", "restore": "restored",
        "delete": "permanently deleted", "attach": "attached", "detach": "detached", "owner": "changed the owner of"}


def _q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _person(email: str | None) -> str | None:
    """A readable name from an account, never the address itself."""
    if not email:
        return None
    return " ".join(w.capitalize() for w in email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ").split())


def user_names(conn, ids) -> dict:
    """user id -> a person's name: the person record linked to the account
    (kb.person_accounts) when there is one, else a name read from the
    account's e-mail local part. The address itself is never returned."""
    ids = sorted({str(i) for i in ids if i})
    if not ids:
        return {}
    out = {str(x["user_id"]): _person(x["email"]) for x in _q(conn, "select user_id, email from kb.actor_emails(%s::uuid[])", (ids,))}
    for x in _q(conn, """select pa.user_id, n.name from kb.person_accounts pa join kb.nodes n on n.id = pa.node_id
                         where pa.user_id = any(%s::uuid[])""", (ids,)):
        if x["name"]:
            out[str(x["user_id"])] = x["name"]
    return out


def _actor_label(r: dict, names: dict, started_by=None) -> str:
    aid = str(r["actor_id"]) if r.get("actor_id") else None
    person = names.get(aid) if aid else None
    if aid and not person:
        person = "A former member"
    t = r.get("actor_type")
    if r.get("kind") == "sync.run":
        who = names.get(str(started_by)) if started_by else None
        return "Sync (NP Autopilot" + (f", started by {who}" if who else "") + ")"
    if t == "ai":
        return "AI assistant" + (f" (for {person})" if person else "")
    if t == "import":
        return "Import" + (f" (run by {person})" if person else "")
    if t == "sync":
        # the scheduled sync from NP Autopilot; "Sync now" names who started it
        return "Sync (NP Autopilot" + (f", started by {person}" if person else "") + ")"
    if t == "system" or not aid:
        return "System"
    return person


def _source(r: dict) -> str:
    if r.get("kind") == "layout.update":
        return "graph"
    if r.get("kind") == "sync.run":
        return "sync"
    return {"human": "app", "ai": "ai", "import": "import", "sync": "sync"}.get(r.get("actor_type"), "system")


def label_actors(conn, rows: list[dict]) -> list[dict]:
    names = user_names(conn, [r.get("actor_id") for r in rows])
    for r in rows:
        r["actor_label"] = _actor_label(r, names)
        r["source"] = _source(r)
    return rows


def diff(before: dict | None, after: dict | None) -> list[dict]:
    """Field-by-field before -> after for an update (props flattened)."""
    if not before or not after:
        return []
    out = []
    keys = sorted(set(before) | set(after))
    for k in keys:
        if k in NOISE:
            continue
        a, b = before.get(k), after.get(k)
        if k == "props" and isinstance(a, dict) and isinstance(b, dict):
            for pk in sorted(set(a) | set(b)):
                if a.get(pk) != b.get(pk):
                    out.append({"field": "props." + pk, "before": a.get(pk), "after": b.get(pk)})
        elif a != b:
            out.append({"field": k, "before": a, "after": b})
    return out


# ---------------------------------------------------------------------------- the sentence
def _t(s: str) -> dict:
    return {"t": "text", "text": s}


def _val(s, quote: bool = False) -> dict:
    return {"t": "value", "text": str(s), "quote": quote}


def text_of(parts: list[dict]) -> str:
    out = []
    for p in parts:
        if p["t"] == "entity":
            out.append(f"'{p['text']}'" + (" (deleted)" if p.get("deleted") and p.get("badge", True) else ""))
        elif p["t"] == "value" and p.get("quote"):
            out.append(f"'{p['text']}'")
        else:
            out.append(p["text"])
    return "".join(out)


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _humane(s) -> str:
    return str(s).replace("_", " ")


def _field_label(f: str) -> str:
    return f[0].lower() + f[1:] if len(f) > 1 and f[1:2].islower() else f


class _Ctx:
    """Every name a page of entries needs, looked up once per page."""

    def __init__(self, conn, rows: list[dict]):
        self.conn = conn
        nids, rids, tids, uids = set(), set(), set(), set()
        exists: dict[str, set] = {}
        finished = set()
        for r in rows:
            b, a = r.get("before") or {}, r.get("after") or {}
            uids.add(r.get("actor_id"))
            for src in (b, a):
                for k in RECORD_FIELDS:
                    x = src.get(k)
                    for y in (x if isinstance(x, list) else [x]):
                        if y:
                            nids.add(str(y))
                for k in USER_FIELDS:
                    x = src.get(k)
                    for y in (x if isinstance(x, list) else [x]):
                        if y:
                            uids.add(str(y))
                if src.get("resource_id"):
                    rids.add(str(src["resource_id"]))
                if src.get("tag_id"):
                    tids.add(str(src["tag_id"]))
                if r["table_name"] in ("proposals", "flags") and src.get("target_id") and src.get("target_table") == "nodes":
                    nids.add(str(src["target_id"]))
                for co in (b.get("co_owner_record_ids") or []) + (a.get("co_owner_record_ids") or []):
                    nids.add(str(co))
            for x in r.get("node_ids") or []:
                nids.add(str(x))
            if r["table_name"] == "nodes" and r.get("row_id"):
                nids.add(str(r["row_id"]))
            if r["table_name"] in ("resources",) and r.get("row_id"):
                rids.add(str(r["row_id"]))
            if r["table_name"] == "tags" and r.get("row_id"):
                tids.add(str(r["row_id"]))
            if r["table_name"] in ("edges", "templates", "edge_types", "node_types", "saved_views", "link_kinds") and r.get("row_id"):
                exists.setdefault(r["table_name"], set()).add(str(r["row_id"]))
            if r.get("kind") == "sync.run":
                finished.add(r["at"])
        self.nodes = {str(x["id"]): x for x in _q(conn, "select id, name, type_id from kb.nodes where id = any(%s::uuid[])", (list(nids),))} if nids else {}
        missing = [i for i in nids if i not in self.nodes]
        # A record that no longer exists keeps the last name the log gave it
        # (as far as the caller may read the log).
        self.gone = {str(x["row_id"]): x for x in _q(conn, """
            select distinct on (row_id) row_id, coalesce(after, before) ->> 'name' as name,
                   coalesce(after, before) ->> 'type_id' as type_id
              from kb.audit_log where table_name = 'nodes' and row_id = any(%s::uuid[]) order by row_id, id desc""",
            (missing,))} if missing else {}
        self.resources = {str(x["id"]): x for x in _q(conn, "select id, title from kb.resources where id = any(%s::uuid[])", (list(rids),))} if rids else {}
        rmiss = [i for i in rids if i not in self.resources]
        self.gone_res = {str(x["row_id"]): x for x in _q(conn, """
            select distinct on (row_id) row_id, coalesce(after, before) ->> 'title' as title
              from kb.audit_log where table_name = 'resources' and row_id = any(%s::uuid[]) order by row_id, id desc""",
            (rmiss,))} if rmiss else {}
        self.tags = {str(x["id"]): x for x in _q(conn, "select id, name from kb.tags where id = any(%s::uuid[])", (list(tids),))} if tids else {}
        tmiss = [i for i in tids if i not in self.tags]
        self.gone_tags = {str(x["row_id"]): x for x in _q(conn, """
            select distinct on (row_id) row_id, coalesce(after, before) ->> 'name' as name
              from kb.audit_log where table_name = 'tags' and row_id = any(%s::uuid[]) order by row_id, id desc""",
            (tmiss,))} if tmiss else {}
        self.ntypes = {str(x["id"]): x for x in _q(conn, "select id, key, label, plural, fields from kb.node_types")}
        self.etypes = {str(x["id"]): x for x in _q(conn, "select id, key, label, inverse_label from kb.edge_types")}
        self.live = {}
        for table, ids in exists.items():
            self.live[table] = {str(x["id"]) for x in _q(conn, f"select id from kb.{table} where id = any(%s::uuid[])", (list(ids),))}
        self.users = user_names(conn, uids)
        # A finished sync run: its counts (admins only, by RLS). The change
        # event and the run's finished_at come from the same statement.
        self.runs = {}
        if finished:
            for x in _q(conn, """select finished_at, status, counts, actor_id, message from kb.sync_runs
                                 where finished_at = any(%s::timestamptz[])""", (list(finished),)):
                self.runs[x["finished_at"]] = x

    # -- entities
    def rec(self, nid, *, name=None, type_id=None, typed=True, badge=True) -> list[dict]:
        nid = str(nid) if nid else None
        n = self.nodes.get(nid) if nid else None
        deleted = n is None
        g = n or self.gone.get(nid) or {}
        nm = name or g.get("name") or "a deleted record"
        t = self.ntypes.get(str(type_id or g.get("type_id") or ""))
        out = [_t(t["label"].lower() + " ")] if typed and t else []
        out.append({"t": "entity", "kind": "record", "id": nid, "text": nm, "type": t["key"] if t else None,
                    "deleted": deleted, "badge": badge})
        return out

    def res(self, rid, *, title=None, badge=True) -> list[dict]:
        rid = str(rid) if rid else None
        r = self.resources.get(rid) if rid else None
        nm = title or (r or self.gone_res.get(rid) or {}).get("title") or "a deleted link"
        return [_t("the link "), {"t": "entity", "kind": "link", "id": rid, "text": nm, "deleted": r is None, "badge": badge}]

    def tag(self, tid, *, name=None, badge=True) -> list[dict]:
        tid = str(tid) if tid else None
        r = self.tags.get(tid) if tid else None
        nm = name or (r or self.gone_tags.get(tid) or {}).get("name") or "a deleted tag"
        return [{"t": "entity", "kind": "tag", "id": tid, "text": nm, "deleted": r is None, "badge": badge}]

    def thing(self, table, kind, row_id, name, *, badge=True) -> list[dict]:
        """A configuration entity named in its own row (a type, template, view...)."""
        rid = str(row_id) if row_id else None
        live = self.live.get(table)
        deleted = live is not None and rid not in live
        return [{"t": "entity", "kind": kind, "id": rid, "text": name or "unnamed", "deleted": deleted, "badge": badge}]

    def ntype(self, tid) -> str:
        t = self.ntypes.get(str(tid or ""))
        return t["label"].lower() if t else "a deleted type"

    def ntype_plural(self, tid) -> str:
        t = self.ntypes.get(str(tid or ""))
        return (t.get("plural") or t["label"] + "s").lower() if t else "records"

    def user(self, uid) -> str:
        return self.users.get(str(uid)) or "a former member"

    # -- values: a list of parts, or None when the value does not fit a sentence
    def value(self, field: str, x, *, enum: bool = False):
        base = field.split(".")[-1]
        if x in (None, "", [], {}):
            return [_val("none")]
        if base in USER_FIELDS:
            xs = x if isinstance(x, list) else [x]
            return [_val(", ".join(self.user(u) for u in xs))]
        if base in RECORD_FIELDS:
            xs = x if isinstance(x, list) else [x]
            out = []
            for i, y in enumerate(xs[:5]):
                if i:
                    out.append(_t(", "))
                out += self.rec(y)
            if len(xs) > 5:
                out.append(_t(f" and {len(xs) - 5} more"))
            return out
        if base == "type_id":
            return [_val(self.ntype(x))]
        if base == "merged_into" or base == "edge_type_id":
            et = self.etypes.get(str(x))
            return [_val(et["label"] if et else "a deleted relationship type", quote=True)]
        if isinstance(x, bool):
            return [_val("on" if x else "off")]
        if isinstance(x, (int, float)):
            return [_val(x)]
        if isinstance(x, list) and all(isinstance(y, str) for y in x):
            s = ", ".join(x)
            return [_val(s)] if len(s) <= 80 else None
        if isinstance(x, str):
            if len(x) > 80 or "\n" in x:
                return None
            if enum or base in ENUMS:
                return [_val(_humane(x))]
            return [_val(x, quote=True)]
        return None


def _changed(cx: _Ctx, ent: list[dict], ch: list[dict], *, label_of=None) -> list[dict]:
    """The sentence for an update: one field reads 'changed the X of E from A
    to B'; several read 'updated the X, Y and Z of E' (the diff lists them)."""
    ch = [c for c in ch if c["field"] not in QUIET]
    if not ch:
        return [_t("updated ")] + ent
    lab = label_of or (lambda f: FIELD_LABELS.get(f, _humane(f.split(".")[-1])))
    if len(ch) == 1:
        c = ch[0]
        f, b, a = c["field"], c["before"], c["after"]
        if f in ("name", "title", "label") and isinstance(a, str):
            return [_t("renamed ")] + ent + [_t(" to "), _val(a, quote=True)]
        if f == "scope_id":
            if not b:
                return [_t("placed ")] + ent + [_t(" in ")] + cx.rec(a)
            if not a:
                return [_t("removed ")] + ent + [_t(" from ")] + cx.rec(b)
            return [_t("moved ")] + ent + [_t(" from ")] + cx.rec(b) + [_t(" to ")] + cx.rec(a)
        name = lab(f)
        if isinstance(a, bool) and isinstance(b, (bool, type(None))):
            return [_t(f"turned {'on' if a else 'off'} {name} for ")] + ent
        bv, av = cx.value(f, b), cx.value(f, a)
        if bv is None or av is None:
            return [_t(f"changed the {name} of ")] + ent
        if b in (None, "", [], {}):
            return [_t(f"set the {name} of ")] + ent + [_t(" to ")] + av
        if a in (None, "", [], {}):
            return [_t(f"cleared the {name} of ")] + ent + [_t(" (was ")] + bv + [_t(")")]
        return [_t(f"changed the {name} of ")] + ent + [_t(" from ")] + bv + [_t(" to ")] + av
    # A rename among other edits keeps its old -> new (run 6, Section 7): "renamed E to 'B' and updated its summary".
    ren = next((c for c in ch if c["field"] in ("name", "title", "label") and isinstance(c["after"], str)), None)
    if ren:
        rest = []
        for c in ch:
            n = lab(c["field"])
            if c is not ren and n not in rest:
                rest.append(n)
        if len(rest) > 4:
            rest = rest[:3] + [f"{len(rest) - 3} more fields"]
        return [_t("renamed ")] + ent + [_t(" to "), _val(ren["after"], quote=True), _t(f" and updated its {_and(rest)}")]
    names = []
    for c in ch:
        n = lab(c["field"])
        if n not in names:
            names.append(n)
    if len(names) > 4:
        names = names[:3] + [f"{len(names) - 3} more fields"]
    return [_t(f"updated the {_and(names)} of ")] + ent


def _verb(kind: str) -> str:
    return kind.split(".")[-1] if kind else "update"


def _rel(cx: _Ctx, src: dict, *, flip: bool = False):
    """A relationship as the reader says it: the target first with the
    inverse label ('Graphs' covered by course 'DSA'); without an inverse
    label (or flipped, for the source record's History), the source first."""
    et = cx.etypes.get(str(src.get("edge_type_id"))) or {}
    inv, lab = et.get("inverse_label"), et.get("label") or "related to"
    if inv and not flip:
        return cx.rec(src.get("target_id"), typed=False), inv, cx.rec(src.get("source_id")), et
    return cx.rec(src.get("source_id"), typed=False), lab, cx.rec(src.get("target_id")), et


def _edge(cx: _Ctx, r: dict, verb: str, *, flip: bool = False) -> list[dict]:
    b, a = r.get("before") or {}, r.get("after") or {}
    src = a or b
    one, rel, two, et = _rel(cx, src, flip=flip)
    phrase = [_t("the relationship ")] + one + [_t(f" {rel} ")] + two
    if verb == "create":
        return [_t("linked ")] + one + [_t(" to ")] + two + [_t(f" as {rel}")]
    if verb == "archive":
        return [_t("archived ")] + phrase
    if verb == "restore":
        return [_t("restored ")] + phrase
    if verb == "delete":
        return [_t("permanently deleted ")] + phrase
    ch = [c for c in diff(b, a) if c["field"] not in QUIET]
    if any(c["field"] == "edge_type_id" for c in ch):
        old = cx.etypes.get(str(b.get("edge_type_id"))) or {}
        use_inv = bool(et.get("inverse_label")) and not flip
        was = (old.get("inverse_label") if use_inv else old.get("label")) or old.get("label") or "a deleted type"
        return [_t("changed the relationship between ")] + one + [_t(" and ")] + two + [_t(" from "), _val(was), _t(" to "), _val(rel)]
    return _changed(cx, phrase, ch)


def _quoted_list(xs: list[str]) -> list[dict]:
    out = []
    for i, x in enumerate(xs):
        if i:
            out.append(_t(", "))
        out.append(_val(x, quote=True))
    return out


def _fields_change(cx: _Ctx, ent: list[dict], b: list, a: list) -> list[dict]:
    old = {f.get("key"): f for f in b or [] if isinstance(f, dict)}
    new = {f.get("key"): f for f in a or [] if isinstance(f, dict)}
    lab = lambda f: f.get("label") or f.get("key")                      # noqa: E731
    added = [lab(f) for k, f in new.items() if k not in old and not f.get("archived")]
    removed = [lab(f) for k, f in new.items() if f.get("archived") and not (old.get(k) or {}).get("archived")]
    removed += [lab(f) for k, f in old.items() if k not in new]
    renamed = [(lab(old[k]), lab(f)) for k, f in new.items() if k in old and lab(old[k]) != lab(f)]
    changed = [lab(f) for k, f in new.items() if k in old and lab(old[k]) == lab(f) and f != old[k]
               and not (f.get("archived") and not old[k].get("archived"))]
    if len(added) == 1 and not (removed or renamed or changed):
        return [_t("added the field "), _val(added[0], quote=True), _t(" to ")] + ent
    if len(removed) == 1 and not (added or renamed or changed):
        return [_t("removed the field "), _val(removed[0], quote=True), _t(" from ")] + ent
    bits = []
    for word, xs in (("added", added), ("removed", removed), ("changed", changed)):
        if xs:
            bits.append([_t(word + " ")] + _quoted_list(xs))
    for x, y in renamed:
        bits.append([_t("renamed "), _val(x, quote=True), _t(" to "), _val(y, quote=True)])
    if not bits:
        return [_t("changed the fields of ")] + ent
    out = [_t("changed the fields of ")] + ent + [_t(" (")]
    for i, bit in enumerate(bits):
        out += ([_t("; ")] if i else []) + bit
    return out + [_t(")")]


def _sync_summary(run: dict | None) -> list[dict]:
    if not run:
        return [_t("finished a sync run")]
    if run.get("status") == "error":
        return [_t("finished a sync run with errors")]
    if run.get("status") == "skipped":
        return [_t("skipped a sync run (another was still going)")]
    counts = run.get("counts") or {}
    bits = []
    for word, key in (("created", "created"), ("updated", "updated"), ("adopted", "adopted"),
                      ("marked as removed at the source", "removed_at_source"), ("restored", "restored_at_source")):
        by_unit: dict[str, int] = {}
        for k, n in (counts.get(key) or {}).items():
            unit = str(k).split(":")[0].strip()
            by_unit[unit] = by_unit.get(unit, 0) + int(n or 0)
        units = [f"{n} {u}{'' if n == 1 else 's'}" for u, n in by_unit.items() if n]
        if units:
            bits.append(f"{word} {_and(units)}")
    out = [_t("finished a sync run" + (": " + "; ".join(bits) if bits else ": no changes"))]
    if counts.get("partial"):
        out.append(_t(" (stopped at its time limit; the next run continues)"))
    return out


def _describe(cx: _Ctx, r: dict, *, flip: bool = False) -> tuple[list[dict], str | None, bool | None]:
    """(the sentence after the actor, the entity's name, whether it still exists)."""
    tbl, kind = r["table_name"], r.get("kind") or f"{r['table_name']}.{r['action']}"
    verb = _verb(kind)
    b, a = r.get("before") or {}, r.get("after") or {}
    src = a or b
    gone = verb == "delete" or r["action"] == "delete"

    if tbl == "nodes":
        ent = cx.rec(r["row_id"], name=(b or a).get("name") if verb in ("update", "owner") else src.get("name"),
                     type_id=src.get("type_id"), badge=not gone)
        exists = not ent[-1]["deleted"]
        if verb == "create":
            out = [_t("created ")] + ent
            if a.get("scope_id"):
                out += [_t(" in ")] + cx.rec(a["scope_id"])
            return out, src.get("name"), exists
        if verb in ("archive", "restore"):
            return [_t(VERB[verb] + " ")] + ent, src.get("name"), exists
        if verb == "delete":
            return [_t("permanently deleted ")] + ent, src.get("name"), exists
        ch = diff(b, a)
        tdef = cx.ntypes.get(str(src.get("type_id"))) or {}
        flabels = {f.get("key"): f.get("label") for f in tdef.get("fields") or [] if isinstance(f, dict)}

        def lab(f):
            if f.startswith("props."):
                k = f[6:]
                return _field_label(flabels.get(k) or _humane(k))
            return FIELD_LABELS.get(f, _humane(f))
        return _changed(cx, ent, ch, label_of=lab), src.get("name"), exists

    if tbl == "edges":
        return _edge(cx, r, verb, flip=flip), None, None

    if tbl == "node_tags":
        on = cx.rec(src.get("node_id"))
        tg = cx.tag(src.get("tag_id"))
        name = tg[0]["text"] + " on " + on[-1]["text"]
        if verb == "attach":
            return [_t("tagged ")] + on + [_t(" with ")] + tg, name, None
        return [_t("removed the tag ")] + tg + [_t(" from ")] + on, name, None

    if tbl == "node_resources":
        on = cx.rec(src.get("node_id"))
        lk = cx.res(src.get("resource_id"))
        name = lk[-1]["text"] + " on " + on[-1]["text"]
        if verb == "attach":
            return [_t("attached ")] + lk + [_t(" to ")] + on, name, None
        if verb == "detach":
            return [_t("detached ")] + lk + [_t(" from ")] + on, name, None
        return _changed(cx, [_t("the attachment of ")] + lk[1:] + [_t(" on ")] + on, diff(b, a)), name, None

    if tbl == "resources":
        ent = cx.res(r["row_id"], title=(b or a).get("title") if verb == "update" else src.get("title"), badge=not gone)
        exists = not ent[-1]["deleted"]
        if verb == "create":
            return [_t("added ")] + ent, src.get("title"), exists
        if verb in ("archive", "restore", "delete"):
            return [_t(VERB[verb] + " ")] + ent, src.get("title"), exists
        return _changed(cx, ent, diff(b, a)), src.get("title"), exists

    if tbl == "tags":
        ent = [_t("the tag ")] + cx.tag(r["row_id"], name=(b or a).get("name") if verb == "update" else src.get("name"), badge=not gone)
        exists = not ent[-1]["deleted"]
        if verb in ("create", "archive", "restore", "delete"):
            return [_t(VERB[verb] + " ")] + ent, src.get("name"), exists
        return _changed(cx, ent, diff(b, a)), src.get("name"), exists

    if tbl == "edge_types":
        name = (b or a).get("label") if r["action"] == "update" else src.get("label")
        ent = [_t("the relationship type ")] + cx.thing(tbl, "reltype", r["row_id"], name, badge=not gone)
        exists = not ent[-1]["deleted"]
        if r["action"] == "insert":
            out = [_t("created ")] + ent
            if a.get("inverse_label"):
                out += [_t(" (inverse "), _val(a["inverse_label"], quote=True), _t(")")]
            return out, name, exists
        if r["action"] == "update" and a.get("merged_into") and not b.get("merged_into"):
            into = cx.etypes.get(str(a["merged_into"])) or {}
            return [_t("merged ")] + ent + [_t(" into "), {"t": "entity", "kind": "reltype", "id": str(a["merged_into"]),
                                                         "text": into.get("label") or "a deleted type", "deleted": not into}], name, exists
        if r["action"] == "update" and b.get("review_status") == "unreviewed" and a.get("review_status") == "reviewed" \
                and not a.get("archived_at"):
            return [_t("confirmed ")] + ent, name, exists
        if verb in ("archive", "restore", "delete"):
            return [_t(VERB[verb] + " ")] + ent, name, exists
        return _changed(cx, ent, diff(b, a)), name, exists

    if tbl == "edge_type_rules":
        et = cx.etypes.get(str(src.get("edge_type_id"))) or {}
        ent = [_t("the relationship type "), {"t": "entity", "kind": "reltype", "id": str(src.get("edge_type_id")),
                                               "text": et.get("label") or "a deleted type", "deleted": not et}]
        pair = [_val(cx.ntype(src.get("source_type_id"))), _t(" to "), _val(cx.ntype(src.get("target_type_id")))]
        on = r["action"] == "insert" or (b.get("archived_at") and not a.get("archived_at"))
        off = r["action"] == "delete" or (a.get("archived_at") and not b.get("archived_at"))
        if on:
            return [_t("allowed ")] + ent + [_t(" from ")] + pair, et.get("label"), None
        if off:
            return [_t("stopped allowing ")] + ent + [_t(" from ")] + pair, et.get("label"), None
        return [_t("changed a rule of ")] + ent, et.get("label"), None

    if tbl == "node_types":
        name = (b or a).get("label") if verb == "update" else src.get("label")
        ent = [_t("the record type ")] + cx.thing(tbl, "type", r["row_id"], name, badge=not gone)
        exists = not ent[-1]["deleted"]
        if verb in ("create", "archive", "restore", "delete"):
            return [_t(VERB[verb] + " ")] + ent, name, exists
        ch = [c for c in diff(b, a) if c["field"] not in QUIET]
        if len(ch) == 1 and ch[0]["field"] == "fields":
            return _fields_change(cx, ent, b.get("fields"), a.get("fields")), name, exists
        if len(ch) == 1 and ch[0]["field"] == "allowed_parents":
            by_key = {t["key"]: t["label"].lower() for t in cx.ntypes.values()}
            where = [by_key.get(k, k) for k in a.get("allowed_parents") or []]
            return [_t("changed where ")] + ent + [_t(" can be placed to "), _val(_and(where) if where else "anywhere")], name, exists
        return _changed(cx, ent, ch), name, exists

    if tbl == "link_kinds":
        name = (b or a).get("label") if verb == "update" else src.get("label")
        ent = [_t("the link kind ")] + cx.thing(tbl, "link_kind", r["row_id"], name, badge=not gone)
        if r["action"] == "insert":
            return [_t("created ")] + ent, name, None
        if a.get("archived_at") and not b.get("archived_at"):
            return [_t("archived ")] + ent, name, None
        if r["action"] == "delete":
            return [_t("permanently deleted ")] + ent, name, None
        return _changed(cx, ent, diff(b, a)), name, None

    if tbl == "templates":
        name = (b or a).get("name") if r["action"] == "update" else src.get("name")
        ent = [_t("the template ")] + cx.thing(tbl, "template", r["row_id"], name, badge=not gone)
        exists = not ent[-1]["deleted"]
        if r["action"] == "insert":
            out = [_t("saved ")] + ent
            if a.get("source_id"):
                out += [_t(" from ")] + cx.rec(a["source_id"])
            return out, name, exists
        if a.get("archived_at") and not b.get("archived_at"):
            return [_t("archived ")] + ent, name, exists
        if b.get("archived_at") and not a.get("archived_at"):
            return [_t("restored ")] + ent, name, exists
        if r["action"] == "delete":
            return [_t("permanently deleted ")] + ent, name, exists
        return _changed(cx, ent, diff(b, a)), name, exists

    if tbl == "saved_views":
        name = (b or a).get("name") if r["action"] == "update" else src.get("name")
        ent = [_t("the view ")] + cx.thing(tbl, "view", r["row_id"], name, badge=not gone)
        if r["action"] == "insert":
            return [_t("saved ")] + ent, name, None
        if r["action"] == "delete" or (a.get("archived_at") and not b.get("archived_at")):
            return [_t("deleted ")] + ent, name, None
        return _changed(cx, ent, diff(b, a)), name, None

    if tbl == "memberships":
        who = [_val(cx.user(src.get("user_id")))]
        if r["action"] == "insert":
            return [_t("added ")] + who + [_t(" as "), _val(_humane(a.get("role")))], None, None
        if r["action"] == "delete" or (a.get("archived_at") and not b.get("archived_at")):
            return [_t("removed ")] + who + [_t(" from the workspace")], None, None
        if b.get("archived_at") and not a.get("archived_at"):
            return [_t("brought back ")] + who + [_t(" as "), _val(_humane(a.get("role")))], None, None
        if b.get("role") != a.get("role"):
            return [_t("changed the role of ")] + who + [_t(" from "), _val(_humane(b.get("role"))), _t(" to "), _val(_humane(a.get("role")))], None, None
        return [_t("updated the membership of ")] + who, None, None

    if tbl == "member_invites":
        # The audit row carries no address (0035): the sentence names the role only.
        if r["action"] == "insert":
            st = " (applied at once: they had signed in)" if a.get("status") == "applied" else " (applied when they first sign in)"
            return [_t("invited a person as "), _val(_humane(a.get("role"))), _t(st)], None, None
        if a.get("status") == "revoked" and b.get("status") != "revoked":
            return [_t("withdrew an invitation as "), _val(_humane(b.get("role")))], None, None
        if a.get("status") == "applied" and b.get("status") != "applied":
            return [_t("an invitation as "), _val(_humane(a.get("role"))), _t(" was applied at sign-in")], None, None
        if b.get("role") != a.get("role"):
            return [_t("changed an invitation from "), _val(_humane(b.get("role"))), _t(" to "), _val(_humane(a.get("role")))], None, None
        return [_t("updated an invitation")], None, None

    if tbl == "api_tokens":
        ent = [_t("the API token "), _val(src.get("name") or "unnamed", quote=True)]
        if r["action"] == "insert":
            return [_t("created ")] + ent, src.get("name"), None
        if a.get("revoked_at") and not b.get("revoked_at"):
            return [_t("revoked ")] + ent, src.get("name"), None
        if r["action"] == "delete":
            return [_t("deleted ")] + ent, src.get("name"), None
        return [_t("updated ")] + ent, src.get("name"), None

    if tbl in ("proposals", "flags"):
        target = cx.rec(src["target_id"]) if src.get("target_table") == "nodes" and src.get("target_id") else \
            [_val(NOUN.get(src.get("target_table"), ("a change",))[0])]
        noun = "the proposal for " if tbl == "proposals" else "the flag on "
        if tbl == "proposals" and r["action"] == "insert":
            return [_t("proposed a change to ")] + target, None, None
        if tbl == "flags" and r["action"] == "insert":
            out = [_t("flagged ")] + target
            if a.get("reason") and len(str(a["reason"])) <= 80:
                out += [_t(": "), _val(a["reason"], quote=True)]
            return out, None, None
        if tbl == "proposals" and b.get("status") == "pending" and a.get("status") not in (None, "pending"):
            return [_t(("approved " if a.get("status") == "approved" else "rejected "))] + [_t("the proposal for ")] + target, None, None
        if tbl == "flags" and a.get("resolved_at") and not b.get("resolved_at"):
            return [_t("resolved the flag on ")] + target, None, None
        return _changed(cx, [_t(noun)] + target, diff(b, a)), None, None

    if tbl == "graph_positions":
        ids = [str(x) for x in r.get("node_ids") or []]
        moved = "reset the graph position of " if r["action"] == "delete" else "moved "
        if len(ids) == 1:
            return [_t(moved)] + cx.rec(ids[0]) + ([] if r["action"] == "delete" else [_t(" on the graph")]), None, None
        n = len(ids)
        return [_t(moved), _val(f"{n} records"), _t("" if r["action"] == "delete" else " on the graph")], None, None

    if tbl == "person_accounts":
        ids = [str(x) for x in r.get("node_ids") or []]
        who = cx.rec(ids[0]) if ids else [_val("a person record")]
        # Never the address: the account is named only as "a sign-in account".
        if r["action"] == "insert":
            return [_t("linked ")] + who + [_t(" to a sign-in account")], None, None
        if r["action"] == "delete":
            return [_t("unlinked the sign-in account from ")] + who, None, None
        return [_t("changed the sign-in account of ")] + who, None, None

    if tbl == "sync_runs":
        return _sync_summary(cx.runs.get(r["at"])), None, None

    noun = NOUN.get(tbl, (_humane(tbl),))[0]
    word = {"insert": "created", "update": "updated", "delete": "deleted"}.get(r["action"], r["action"])
    nm = src.get("name") or src.get("title") or src.get("label")
    return [_t(f"{word} the {noun}")] + ([_t(" "), _val(nm, quote=True)] if nm else []), nm, None


def describe(conn, rows: list[dict], *, record: str | None = None) -> list[dict]:
    """Give every row its sentence, parts, entity label, source and diff.
    `record`: in that record's History, a relationship of which it is the
    source reads from its side."""
    if not rows:
        return rows
    cx = _Ctx(conn, rows)
    for r in rows:
        r["kind"] = r.get("kind") or f"{r['table_name']}.{r['action']}"
        started_by = (cx.runs.get(r["at"]) or {}).get("actor_id") if r["kind"] == "sync.run" else None
        r["actor_label"] = _actor_label(r, cx.users, started_by)
        r["source"] = _source(r)
        flip = bool(record and r["table_name"] == "edges"
                    and str((r.get("after") or r.get("before") or {}).get("source_id")) == str(record))
        body, label, exists = _describe(cx, r, flip=flip)
        actor = {"t": "actor", "text": r["actor_label"], "id": str(r["actor_id"]) if r.get("actor_id") else None,
                 "actor_type": r.get("actor_type")}
        r["parts"] = [actor, _t(" ")] + body
        r["sentence"] = text_of(r["parts"])
        r["label"] = label
        r["exists_now"] = exists
        r["changes"] = diff(r.get("before"), r.get("after")) if r["action"] == "update" else []
        r["node_ids"] = [str(x) for x in r.get("node_ids") or []]
        r.pop("actor_email", None)
    return rows


# ---------------------------------------------------------------------------- grouping
def _gkey(r: dict):
    return (str(r.get("actor_id")), r.get("actor_type"), r.get("kind"), r["table_name"])


def _joins(prev: dict, r: dict) -> bool:
    if _gkey(prev) != _gkey(r) or r.get("kind") in ("sync.run",):
        return False
    try:
        return abs((prev["at"] - r["at"]).total_seconds()) <= GROUP_SECONDS
    except TypeError:
        return False


def group(rows: list[dict]) -> list[dict]:
    """Consecutive rows (newest first) by the same actor doing the same thing
    within GROUP_SECONDS — one bulk request, an import, a sync — become one
    group: each row keeps its own sentence and gets `group`; the response's
    `groups` carries the group's sentence ("updated 14 records")."""
    runs: list[list[dict]] = []
    for r in rows:
        if runs and _joins(runs[-1][-1], r):
            runs[-1].append(r)
        else:
            runs.append([r])
    out = []
    for run in runs:
        if len(run) < 2:
            for r in run:
                r["group"] = None
            continue
        key = f"g{run[0]['id']}"
        for r in run:
            r["group"] = key
        out.append({"key": key, "count": len(run), "ids": [r["id"] for r in run], **_group_sentence(run)})
    return out


def _group_sentence(run: list[dict]) -> dict:
    first = run[0]
    n = len(run)
    kind, tbl = first.get("kind") or "", first["table_name"]
    verb = _verb(kind)
    srcs = [(r.get("after") or r.get("before") or {}) for r in run]
    actor = next(p for p in first["parts"] if p["t"] == "actor")
    if tbl == "nodes":
        plurals = {r.get("_type_plural") for r in run}
        noun = next(iter(plurals)) if len(plurals) == 1 and None not in plurals else "records"
        scopes = {s.get("scope_id") for s in srcs}
        if verb == "create" and len(scopes) == 1 and None not in scopes:
            scope = _entity_after(first["parts"], " in ")
            if scope:
                return _gs(actor, [_t("added "), _val(f"{n} {noun}"), _t(" to "), dict(scope)])
        if verb == "owner":
            return _gs(actor, [_t("changed the owner of "), _val(f"{n} {noun}")])
        return _gs(actor, [_t(VERB.get(verb, "updated") + " "), _val(f"{n} {noun}")])
    if tbl in ("node_tags", "node_resources"):
        what = {s.get("tag_id") or s.get("resource_id") for s in srcs}
        ents = [p for p in first["parts"] if p["t"] == "entity"]
        word = {"attach": ("tagged " if tbl == "node_tags" else "attached "),
                "detach": ("removed " if tbl == "node_tags" else "detached ")}.get(verb, "updated ")
        if len(what) == 1:
            thing = next((p for p in ents if p.get("kind") in ("tag", "link")), None)
            if thing is not None:
                if tbl == "node_tags" and verb == "attach":
                    return _gs(actor, [_t("tagged "), _val(f"{n} records"), _t(" with "), dict(thing)])
                if tbl == "node_tags":
                    return _gs(actor, [_t("removed the tag "), dict(thing), _t(" from "), _val(f"{n} records")])
                return _gs(actor, [_t(word + "the link "), dict(thing), _t(" to " if verb == "attach" else " from "), _val(f"{n} records")])
        return _gs(actor, [_t(word), _val(f"{n} {NOUN[tbl][1]}")])
    if tbl == "edges":
        word = {"create": "created ", "archive": "archived ", "restore": "restored ", "delete": "permanently deleted "}.get(verb, "updated ")
        return _gs(actor, [_t(word), _val(f"{n} relationships")])
    word = VERB.get(verb, "updated")
    return _gs(actor, [_t(word + " "), _val(f"{n} {NOUN.get(tbl, ('', _humane(tbl)))[1]}")])


def _entity_after(parts: list[dict], text: str) -> dict | None:
    for i, p in enumerate(parts):
        if p["t"] == "text" and p["text"] == text:
            return next((q for q in parts[i + 1:] if q["t"] == "entity"), None)
    return None


def _gs(actor: dict, body: list[dict]) -> dict:
    parts = [actor, _t(" ")] + body
    return {"parts": parts, "sentence": text_of(parts)}


# ---------------------------------------------------------------------------- reads
def history(conn, row_id: str, limit: int = 50) -> list[dict]:
    """A record's History tab: kb.record_history() (viewer+) plus the record's
    content-free change events (layout moves, sign-in account links), which
    every member may already read in kb.changes."""
    rid = v.uid(row_id, "id")
    lim = max(1, min(int(limit), 200))
    rows = _q(conn, """select h.id, h.at, h.actor_id, h.actor_type, h.table_name, h.row_id, h.action, h.before, h.after,
                              c.kind, coalesce(c.node_ids, '{}') as node_ids
                       from kb.record_history(%s, %s) h left join kb.changes c on c.id = h.id""", (rid, lim))
    rows += _q(conn, """select c.id, c.at, c.actor_id, c.actor_type, c.table_name, c.row_id, c.action,
                               null::jsonb as before, null::jsonb as after, c.kind, c.node_ids
                        from kb.changes c where c.table_name = any(%s) and c.table_name <> 'sync_runs'
                          and %s::uuid = any(c.node_ids) order by c.id desc limit %s""", (list(CHANGE_ONLY), rid, lim))
    rows = sorted(rows, key=lambda r: r["id"], reverse=True)[:lim]
    return describe(conn, rows, record=rid)


def changes(conn, since: int | None, limit: int = 200) -> dict:
    """The change feed clients poll for collaboration (M7). Cursor = audit id.
    Reads kb.changes (no row content), so every member may follow it."""
    if since is None:
        last = _q(conn, "select coalesce(max(id), 0) as m from kb.changes")
        return {"cursor": last[0]["m"], "changes": []}
    rows = _q(conn, """select id, at, actor_id, actor_type, table_name, row_id, action, version, kind, node_ids
                       from kb.changes where id > %s order by id limit %s""",
              (int(since), max(1, min(int(limit), 500))))
    return {"cursor": rows[-1]["id"] if rows else int(since), "changes": rows}


def recent(conn, limit: int = 20) -> list[dict]:
    rows = _q(conn, """select a.id, a.at, a.actor_id, a.actor_type, a.table_name, a.row_id, a.action,
                              coalesce(a.after ->> 'name', a.before ->> 'name', a.after ->> 'title',
                                       a.before ->> 'title') as label,
                              exists (select 1 from kb.nodes n where n.id = a.row_id) or
                              exists (select 1 from kb.resources r where r.id = a.row_id) as exists_now
                       from kb.audit_log a where a.table_name in ('nodes', 'edges', 'resources')
                       order by a.id desc limit %s""", (limit,))
    return label_actors(conn, rows)


def _ts(val, name):
    if val in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"{name} must be an ISO date or time", field=name) from None


def _list(params, key) -> list[str]:
    return [x for x in str(params.get(key) or "").split(",") if x]


#: Every audit row with its kind, and the change-only events (no content) the
#: caller may see: admins all, editors their own and their scope's — the rule
#: audit_log_select applies to the audit rows (0029).
#: The two halves of the event stream. Each is filtered and limited ON ITS OWN,
#: newest first, before they are merged (2026-11-07): one UNION ALL over both,
#: sorted afterwards, read the whole audit log and change feed on every request
#: (117 ms on the real data, and growing with the log). Limited per half,
#: Postgres walks each primary key backwards and stops at the limit.
EVENTS_AUDIT = """
    select a.id, a.at, a.actor_id, a.actor_type, a.table_name, a.row_id, a.action, a.before, a.after,
           coalesce(c.kind, a.table_name || '.' || a.action) as kind, coalesce(c.node_ids, '{}') as node_ids
      from kb.audit_log a left join kb.changes c on c.id = a.id
"""
EVENTS_CHANGES = """
    select c.id, c.at, c.actor_id, c.actor_type, c.table_name, c.row_id, c.action, null::jsonb as before,
           null::jsonb as after, c.kind, c.node_ids
      from kb.changes c
     where c.table_name in ('graph_positions', 'person_accounts', 'sync_runs')
       and ((select kb.role_at_least('admin'))
            or ((select kb.role_at_least('editor'))
                and (c.actor_id = (select auth.uid()) or c.node_ids && (select kb.my_scope_ids()))))
"""
EVENTS = EVENTS_AUDIT + "    union all\n" + EVENTS_CHANGES


def _events(conn, where: list[str], args: list, fetch: int) -> list[dict]:
    """The newest `fetch` events that pass `where` (written against `e`)."""
    w = ("where " + " and ".join(where)) if where else ""
    return _q(conn, f"""select u.* from (
        (select e.* from ({EVENTS_AUDIT}) e {w} order by e.id desc limit %s)
        union all
        (select e.* from ({EVENTS_CHANGES}) e {w} order by e.id desc limit %s)) u
        order by u.id desc limit %s""", (*args, fetch, *args, fetch, fetch))


def _filters(conn, params: dict) -> tuple[list[str], list]:
    where, args = [], []
    if params.get("actor"):
        where.append("e.actor_id = %s"); args.append(v.uid(params["actor"], "actor"))
    if params.get("action"):
        acts = _list(params, "action")
        if any(x not in ACTIONS for x in acts):
            raise Invalid("action must be insert, update or delete", field="action")
        where.append("e.action = any(%s)"); args.append(acts)
    if params.get("op"):
        ops = _list(params, "op")
        if any(x not in OPS for x in ops):
            raise Invalid("op must be one of " + ", ".join(OPS), field="op")
        ors = []
        for o in ops:
            likes, nots = OPS[o]
            ors.append("(e.kind like any(%s) and not (e.kind = any(%s)))"); args += [likes, nots]
        where.append("(" + " or ".join(ors) + ")")
    if params.get("table"):
        tabs = _list(params, "table")
        if any(x not in TABLES for x in tabs):
            raise Invalid("unknown entity type", field="table")
        where.append("e.table_name = any(%s)"); args.append(tabs)
    if params.get("type"):
        keys = _list(params, "type")
        where.append("""(e.table_name = 'nodes' and coalesce(e.after, e.before) ->> 'type_id' in
                         (select t.id::text from kb.node_types t where t.key = any(%s)))"""); args.append(keys)
    if params.get("source"):
        srcs = _list(params, "source")
        if any(x not in SOURCES for x in srcs):
            raise Invalid("source must be app, graph, ai, import, sync or system", field="source")
        ors = []
        for s in srcs:
            if s == "graph":
                ors.append("e.kind = 'layout.update'")
            elif s == "sync":
                ors.append("(e.kind = 'sync.run' or (e.actor_type = 'sync' and e.kind <> 'layout.update'))")
            else:
                ors.append("(e.actor_type = %s and e.kind not in ('layout.update', 'sync.run'))")
                args.append({"app": "human"}.get(s, s))
        where.append("(" + " or ".join(ors) + ")")
    if params.get("record"):
        rid = v.uid(params["record"], "record")
        where.append("""(e.row_id = %s or (e.table_name = 'edges' and %s::text in (coalesce(e.after, e.before) ->> 'source_id',
                         coalesce(e.after, e.before) ->> 'target_id'))
                         or (e.table_name in ('node_resources', 'node_tags') and %s::text in
                         (coalesce(e.after, e.before) ->> 'node_id', coalesce(e.after, e.before) ->> 'resource_id'))
                         or (e.table_name in ('graph_positions', 'person_accounts') and %s::uuid = any(e.node_ids)))""")
        args += [rid, rid, rid, rid]
    if (f := _ts(params.get("from"), "from")):
        where.append("e.at >= %s"); args.append(f)
    if (t := _ts(params.get("to"), "to")):
        where.append("e.at <= %s"); args.append(t)
    if params.get("q"):
        # The sentence's names and values: the row itself, the records, links
        # and tags it names, and the person who made it (by name).
        q = str(params["q"])[:100]
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        actors = _actors_named(conn, q)
        where.append("""(coalesce(e.after, e.before)::text ilike %s
                         or e.actor_id = any(%s::uuid[])
                         or e.node_ids && array(select n.id from kb.nodes n where n.name ilike %s limit 500)
                         or (e.table_name = 'node_resources' and coalesce(e.after, e.before) ->> 'resource_id' in
                             (select r.id::text from kb.resources r where r.title ilike %s limit 500))
                         or (e.table_name = 'node_tags' and coalesce(e.after, e.before) ->> 'tag_id' in
                             (select g.id::text from kb.tags g where g.name ilike %s limit 500)))""")
        args += [like, actors, like, like, like]
    if params.get("cursor"):
        try:
            where.append("e.id < %s"); args.append(int(params["cursor"]))
        except ValueError:
            raise Invalid("cursor must be a number", field="cursor") from None
    return where, args


def _actors_named(conn, q: str) -> list[str]:
    """Members (as far as the caller may list them) whose name matches q."""
    ids = [str(x["user_id"]) for x in _q(conn, "select user_id from kb.memberships")]
    ids += [str(x["user_id"]) for x in _q(conn, "select user_id from kb.person_accounts where user_id is not null")]
    ql = q.lower()
    return [u for u, n in user_names(conn, ids).items() if n and ql in n.lower()]


def _plurals(conn, rows: list[dict]) -> None:
    """The plural of each record row's type, for a group's sentence."""
    if not any(r["table_name"] == "nodes" for r in rows):
        return
    pl = {str(x["id"]): (x["plural"] or x["label"] + "s").lower() for x in _q(conn, "select id, label, plural from kb.node_types")}
    for r in rows:
        if r["table_name"] == "nodes":
            src = r.get("after") or r.get("before") or {}
            r["_type_plural"] = pl.get(str(src.get("type_id")))


def activity(conn, params: dict) -> dict:
    """The Activity page. Filters narrow what RLS already allows; cursor = the
    last id seen (newest first). `group=1` (the page) keeps a group whole on
    one page; every response carries `groups` for the rows it returns."""
    where, args = _filters(conn, params)
    csv_ = params.get("format") == "csv"
    limit = max(1, min(int(params.get("limit") or 50), 5000 if csv_ else 200))
    whole = str(params.get("group") or "") in ("1", "true") and not csv_
    fetch = limit + 1 + (GROUP_EXTEND if whole else 0)
    rows = _events(conn, where, args, fetch)
    cut = min(limit, len(rows))
    if whole:
        while cut < len(rows) and cut < limit + GROUP_EXTEND and _joins(rows[cut - 1], rows[cut]):
            cut += 1
    more = len(rows) > cut
    rows = rows[:cut]
    _plurals(conn, rows)
    rows = describe(conn, rows)
    groups = [] if csv_ else group(rows)
    for r in rows:
        r.pop("_type_plural", None)
    return {"items": rows, "groups": groups, "next_cursor": rows[-1]["id"] if more and rows else None}


def _cell(x) -> str:
    """Spreadsheet-safe: a cell starting with = + - @ is not run as a formula."""
    s = "" if x is None else str(x)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def activity_csv(conn, params: dict) -> str:
    items = activity(conn, {**params, "format": "csv", "limit": params.get("limit") or 5000})["items"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "at", "actor", "source", "action", "kind", "sentence", "entity_type", "entity_id", "entity", "changes"])
    for r in items:
        ch = "; ".join(f"{c['field']}: {c['before']!r} -> {c['after']!r}" for c in r["changes"])
        w.writerow([_cell(x) for x in (r["id"], r["at"].isoformat(), r["actor_label"], r["source"], r["action"], r["kind"],
                                        r["sentence"], r["table_name"], r["row_id"], r["label"], ch)])
    return buf.getvalue()
