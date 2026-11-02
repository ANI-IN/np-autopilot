"""Custom types (C2): record types with fields, relationship types, link kinds.

Admins change types directly; an editor's change becomes a `type_change`
proposal that an admin approves (decide_proposal → apply_type_change). The
database enforces the shape (0027: kb.check_type_def, kb.check_node_props,
kb.check_edge cardinality); this module adds the rules that need to look at
existing DATA before a change is allowed:

  - a field key never changes; removing a field ARCHIVES it (hidden, data kept,
    restorable by un-archiving);
  - a field's kind may change only if every stored value converts — otherwise
    the change is refused with the failing records listed;
  - removing a select option that is in use needs a replacement;
  - a new required field never blocks: existing records are flagged on Data quality;
  - narrowing placement or relationship rules never deletes anything: the
    response lists what no longer fits, and Data quality shows it;
  - a type with live records cannot be archived until they are moved with
    change_records_type (with a field mapping); core types cannot be archived.
"""
from __future__ import annotations

import json
import re

from . import validate as v
from .errors import Conflict, Duplicate, Forbidden, Invalid, NeedsApproval, NotFound
from .service import ROLES, Actor, _q, _q1, _translate, role, require

FIELD_KINDS = ("short_text", "long_text", "number", "date", "datetime", "duration", "url",
               "single_select", "multi_select", "person", "reference", "checkbox")
#: One accessible palette for every record type's icon and dot (no purple;
#: 0028 moved the built-in types onto it). AA non-text contrast on white.
PALETTE = ("#1d4ed8", "#0369a1", "#0e7490", "#0f766e", "#15803d", "#4d7c0f", "#a16207",
           "#b45309", "#c2410c", "#b91c1c", "#be123c", "#475569")
CARDINALITIES = ("many_to_many", "one_to_many", "many_to_one", "one_to_one")
TYPE_FIELDS = {"label", "plural", "description", "icon", "color", "fields", "allowed_parents",
               "parent_required", "default_status", "owner_rule", "is_container", "key"}


def slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "t_" + s
    return s[:40]


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def all_types(conn, include_archived: bool = False) -> dict:
    arch = "" if include_archived else "where t.archived_at is null"
    nts = _q(conn, f"""select t.id, t.key, t.label, t.plural, t.description, t.icon, t.color, t.is_container,
                              t.fields, t.allowed_parents, t.parent_required, t.default_status, t.owner_rule,
                              t.is_core, t.sort_order, t.version, t.archived_at,
                              (select count(*) from kb.nodes n where n.type_id = t.id and n.archived_at is null) as records
                       from kb.node_types t {arch} order by t.sort_order, t.label""")
    ets = _q(conn, f"""select t.id, t.key, t.label, t.inverse_label, t.description, t.allow_self, t.cardinality,
                              t.is_core, t.version, t.archived_at,
                              (select count(*) from kb.edges e where e.edge_type_id = t.id and e.archived_at is null) as edges
                       from kb.edge_types t {arch} order by t.label""")
    rules = _q(conn, """select r.id, r.edge_type_id, s.key as source, t.key as target from kb.edge_type_rules r
                        join kb.node_types s on s.id = r.source_type_id join kb.node_types t on t.id = r.target_type_id
                        where r.archived_at is null""")
    for t in ets:
        t["rules"] = [{"id": r["id"], "source": r["source"], "target": r["target"]}
                      for r in rules if r["edge_type_id"] == t["id"]]
    lks = _q(conn, f"""select id, key, label, icon, patterns, defaults, sort_order, is_core, version, archived_at
                       from kb.link_kinds t {arch} order by sort_order, label""")
    return {"node_types": nts, "edge_types": ets, "link_kinds": lks,
            "resource_kinds": list(v.RESOURCE_KINDS), "field_kinds": list(FIELD_KINDS), "palette": list(PALETTE)}


def _type(conn, key: str, *, lock: bool = False) -> dict:
    row = _q1(conn, "select * from kb.node_types where key = %s" + (" for update" if lock else ""), (key,))
    if not row:
        raise NotFound(f"no record type {key!r}")
    return row


# ---------------------------------------------------------------------------
# admin gate: admins apply, editors propose
# ---------------------------------------------------------------------------

def _gate(conn, actor: Actor, op: str, args: dict) -> None:
    """Admin → proceed. Editor (human) → record a type_change proposal (202)."""
    r = role(conn)
    if r == "admin" and actor.actor_type != "ai":
        return
    if ROLES.index(r) >= ROLES.index("editor"):
        with _translate(conn, "proposal"):
            row = _q1(conn, "insert into kb.proposals (action, target_table, target_id, reason, payload, actor_type) "
                            "values ('type_change', %s, null, %s, %s, %s) returning id",
                      ({"node": "node_types", "edge": "edge_types", "link": "link_kinds"}[op.split("_")[0]],
                       args.get("reason") or op.replace("_", " "), json.dumps({"op": op, "args": args}, default=str),
                       actor.actor_type))
        raise NeedsApproval("type change recorded as a proposal; an admin must approve it in Approvals",
                            proposal_id=row["id"])
    raise Forbidden(f"changing types needs the admin role (editors can propose); you are {r}",
                    required_role="admin", role=r)


def apply_type_change(conn, actor: Actor, payload: dict):
    """Run an approved type_change proposal as the approving admin."""
    require(conn, "admin", "approving a type change")
    op, args = payload.get("op"), payload.get("args") or {}
    fn = OPS.get(op)
    if not fn:
        raise Invalid(f"unknown type change {op!r}")
    return fn(conn, actor, approved=True, **args)


# ---------------------------------------------------------------------------
# record types
# ---------------------------------------------------------------------------

def _clean_field(f: dict, i: int) -> dict:
    if not isinstance(f, dict):
        raise Invalid(f"field {i + 1} must be an object", field="fields")
    label = v.text(f, "label", required=True, max_len=80, allow_empty=False)
    kind = v.choice(f, "kind", FIELD_KINDS)
    if not kind:
        raise Invalid(f"field {label!r} needs a kind", field="fields")
    out = {"key": f.get("key") or slug(label), "label": label, "kind": kind,
           "help": v.text(f, "help", max_len=300), "required": bool(f.get("required")),
           "archived": bool(f.get("archived"))}
    if "default" in f and f["default"] not in (None, ""):
        out["default"] = f["default"]
    if kind in ("single_select", "multi_select"):
        opts = f.get("options") or []
        clean = []
        for o in opts:
            o = {"value": o, "label": o} if isinstance(o, str) else o
            val = str(o.get("value") or slug(str(o.get("label") or ""))).strip()
            if val:
                clean.append({"value": val, "label": str(o.get("label") or val)[:80]})
        if not clean:
            raise Invalid(f"select field {label!r} needs at least one option", field="fields")
        if len({o["value"] for o in clean}) != len(clean):
            raise Invalid(f"select field {label!r} has duplicate options", field="fields")
        out["options"] = clean
    if kind == "reference":
        rt = [str(x) for x in (f.get("ref_types") or [])]
        if not rt:
            raise Invalid(f"reference field {label!r} must name the record types it may point at", field="fields")
        out["ref_types"] = rt
    return out


def _clean_fields(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise Invalid("fields must be a list", field="fields")
    fields = [_clean_field(f, i) for i, f in enumerate(raw)]
    keys = [f["key"] for f in fields]
    if len(set(keys)) != len(keys):
        raise Invalid("two fields share the same key; give one a different label", field="fields")
    return fields


def _type_values(conn, body: dict, *, partial: bool) -> dict:
    out = {}
    if not partial or "label" in body:
        out["label"] = v.text(body, "label", required=True, max_len=80, allow_empty=False)
    if "plural" in body or not partial:
        out["plural"] = v.text(body, "plural", max_len=80) or (out.get("label", "") + "s")
    for k, mx in (("description", 500), ("icon", 40)):
        if k in body:
            out[k] = v.text(body, k, max_len=mx)
    if "color" in body:
        c = body.get("color")
        if c not in PALETTE:
            raise Invalid("pick a colour from the palette", field="color")
        out["color"] = c
    if "allowed_parents" in body:
        ap = body.get("allowed_parents") or []
        if not isinstance(ap, list):
            raise Invalid("allowed_parents must be a list of type keys", field="allowed_parents")
        known = {r["key"] for r in _q(conn, "select key from kb.node_types where archived_at is null")}
        bad = [k for k in ap if k not in known]
        if bad:
            raise Invalid(f"unknown parent type(s): {', '.join(bad)}", field="allowed_parents")
        out["allowed_parents"] = ap
    for k in ("parent_required", "is_container"):
        if k in body:
            out[k] = bool(body[k])
    if "default_status" in body:
        out["default_status"] = v.choice(body, "default_status", ("draft", "active"))
    if "owner_rule" in body:
        out["owner_rule"] = v.choice(body, "owner_rule", ("creator", "none"))
    if "fields" in body:
        out["fields"] = _clean_fields(body["fields"])
    return out


def _sync_parent_rules(conn, key: str, parents: list[str]) -> None:
    """Placement = `contains` from each allowed parent type. Adds missing rules;
    never removes (narrowing is reported, not enforced retroactively)."""
    for p in parents:
        _q(conn, """insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
                    select e.id, s.id, t.id from kb.edge_types e, kb.node_types s, kb.node_types t
                    where e.key = 'contains' and s.key = %s and t.key = %s
                    on conflict (edge_type_id, source_type_id, target_type_id) do update set archived_at = null""",
           (p, key))


def create_node_type(conn, actor: Actor, body: dict, approved: bool = False) -> dict:
    require(conn, "editor", "adding a record type")
    v.only(body, TYPE_FIELDS | {"reason"})
    vals = _type_values(conn, body, partial=False)
    key = body.get("key") or slug(vals["label"])
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", key):
        raise Invalid("key must be lowercase letters, digits and _", field="key")
    if _q1(conn, "select 1 from kb.node_types where lower(label) = lower(%s) and archived_at is null", (vals["label"],)):
        raise Duplicate(f"a record type called {vals['label']!r} already exists", field="label")
    if _q1(conn, "select 1 from kb.node_types where key = %s", (key,)):
        raise Duplicate(f"the key {key!r} is taken; choose another label", field="label")
    if not approved:
        _gate(conn, actor, "node_create", {**body, "key": key})
    vals.setdefault("color", PALETTE[len(_q(conn, "select 1 from kb.node_types")) % len(PALETTE)])
    vals.setdefault("icon", "box")
    cols = ["key"] + list(vals)
    with _translate(conn, "record type"):
        row = _q1(conn, f"insert into kb.node_types ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                        "returning key",
                  [key] + [json.dumps(x) if k == "fields" else x for k, x in vals.items()])
        _sync_parent_rules(conn, key, vals.get("allowed_parents") or [])
    return _type_out(conn, row["key"])


def _type_out(conn, key: str) -> dict:
    return next(t for t in all_types(conn, include_archived=True)["node_types"] if t["key"] == key)


def _convert(kind: str, val):
    """Convert one stored value to `kind`; raise ValueError if it cannot."""
    if val is None:
        return None
    if kind in ("short_text", "long_text"):
        if isinstance(val, list):
            return ", ".join(map(str, val))
        s = str(val).lower() if isinstance(val, bool) else str(val)
        if kind == "short_text" and len(s) > 300:
            raise ValueError("longer than 300 characters")
        return s
    if kind in ("number", "duration"):
        if isinstance(val, bool):
            raise ValueError("a checkbox is not a number")
        n = float(val) if not isinstance(val, (int, float)) else val
        if kind == "duration" and n < 0:
            raise ValueError("negative")
        return int(n) if float(n).is_integer() else n
    if kind == "checkbox":
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ("true", "yes", "1", "y"):
            return True
        if s in ("false", "no", "0", "n", ""):
            return False
        raise ValueError("not yes/no")
    if kind == "date":
        import datetime as dt
        return dt.date.fromisoformat(str(val)[:10]).isoformat()
    if kind == "datetime":
        import datetime as dt
        return dt.datetime.fromisoformat(str(val)).isoformat()
    if kind == "url":
        s = str(val).strip()
        if not re.match(r"^https?://\S+\.\S+", s):
            raise ValueError("not a URL")
        return s
    raise ValueError(f"cannot convert to {kind}")


def update_node_type(conn, actor: Actor, key: str, body: dict, approved: bool = False) -> dict:
    """Safe changes only; see the module docstring. Body may carry
    `replacements: {field_key: {old_option: new_option}}` for removed options."""
    require(conn, "editor", "changing a record type")
    v.only(body, TYPE_FIELDS | {"version", "replacements", "reason"})
    cur = _type(conn, key, lock=True)
    if "key" in body and body["key"] != key:
        raise Invalid("a type key never changes; rename the label instead", field="key")
    expected = v.version(body)
    if cur["version"] != expected:
        raise Conflict("This type changed since you opened it. Your change was NOT saved.",
                       current=_type_out(conn, key), your_version=expected)
    vals = _type_values(conn, body, partial=True)
    if "label" in vals and _q1(conn, "select 1 from kb.node_types where lower(label) = lower(%s) and key <> %s "
                                     "and archived_at is null", (vals["label"], key)):
        raise Duplicate(f"a record type called {vals['label']!r} already exists", field="label")
    warnings, rewrites = [], {}
    if "fields" in vals:
        old = {f["key"]: f for f in cur["fields"]}
        new = {f["key"]: f for f in vals["fields"]}
        # removed → archived, never dropped
        for k, f in old.items():
            if k not in new:
                vals["fields"].append({**f, "archived": True})
                new[k] = vals["fields"][-1]
        repl = body.get("replacements") or {}
        rows = _q(conn, "select id, name, props from kb.nodes where type_id = %s", (cur["id"],))
        failures = []
        for k, nf in new.items():
            of = old.get(k)
            if not of:
                if nf.get("required") and not nf.get("archived"):
                    missing = sum(1 for r in rows if r["props"].get(k) in (None, "", []))
                    if missing:
                        warnings.append(f"{missing} existing record(s) do not have the new required field "
                                        f"{nf['label']!r}; they are flagged on Data quality")
                continue
            if nf["kind"] != of["kind"]:
                for r in rows:
                    if k in r["props"] and r["props"][k] not in (None, ""):
                        try:
                            rewrites.setdefault(r["id"], dict(r["props"]))[k] = _convert(nf["kind"], r["props"][k])
                        except (ValueError, TypeError) as exc:
                            failures.append({"id": r["id"], "name": r["name"], "field": nf["label"],
                                             "value": r["props"][k], "why": str(exc)})
            if nf["kind"] in ("single_select", "multi_select") and of["kind"] in ("single_select", "multi_select"):
                gone = {o["value"] for o in of.get("options", [])} - {o["value"] for o in nf.get("options", [])}
                for r in rows:
                    val = r["props"].get(k)
                    used = set(val if isinstance(val, list) else [val]) & gone
                    for g in used:
                        to = (repl.get(k) or {}).get(g)
                        if to is None:
                            failures.append({"id": r["id"], "name": r["name"], "field": nf["label"], "value": g,
                                             "why": f"option {g!r} is in use; choose a replacement"})
                            continue
                        if to not in {o["value"] for o in nf.get("options", [])}:
                            raise Invalid(f"replacement {to!r} is not an option of {nf['label']!r}", field="replacements")
                        props = rewrites.setdefault(r["id"], dict(r["props"]))
                        props[k] = ([to if x == g else x for x in props[k]] if isinstance(props[k], list) else to)
            if nf.get("required") and not of.get("required") and not nf.get("archived"):
                missing = sum(1 for r in rows if r["props"].get(k) in (None, "", []))
                if missing:
                    warnings.append(f"{missing} existing record(s) are missing {nf['label']!r}, now required; "
                                    "they are flagged on Data quality")
        if failures:
            raise Invalid(f"{len(failures)} value(s) cannot be converted or replaced; nothing was changed",
                          field="fields", failures=failures[:100])
    if "allowed_parents" in vals:
        dropped = set(cur["allowed_parents"]) - set(vals["allowed_parents"])
        if dropped:
            n = (_q1(conn, """select count(*) as c from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                              join kb.nodes s on s.id = e.source_id join kb.node_types st on st.id = s.type_id
                              join kb.nodes t on t.id = e.target_id
                              where et.key = 'contains' and e.archived_at is null and t.type_id = %s
                                and st.key = any(%s)""", (cur["id"], list(dropped))) or {}).get("c", 0)
            if n:
                warnings.append(f"{n} existing placement(s) under {', '.join(sorted(dropped))} no longer fit; "
                                "they are kept and listed on Data quality")
    if not approved:
        _gate(conn, actor, "node_update", {**body, "key": key})
    if not vals:
        raise Invalid("nothing to change")
    sets = ", ".join(f"{k} = %s" for k in vals)
    with _translate(conn, "record type"):
        _q(conn, f"update kb.node_types set {sets} where key = %s",
           [json.dumps(x) if k == "fields" else x for k, x in vals.items()] + [key])
        for nid, props in rewrites.items():
            _q(conn, "update kb.nodes set props = %s where id = %s", (json.dumps(props), nid))
        if "allowed_parents" in vals:
            _sync_parent_rules(conn, key, vals["allowed_parents"])
    out = _type_out(conn, key)
    out["warnings"] = warnings
    out["converted_records"] = len(rewrites)
    return out


def archive_node_type(conn, actor: Actor, key: str, approved: bool = False) -> dict:
    require(conn, "editor", "archiving a record type")
    cur = _type(conn, key, lock=True)
    if cur["is_core"]:
        raise Invalid("core types can be edited but not deleted or archived")
    n = (_q1(conn, "select count(*) as c from kb.nodes where type_id = %s and archived_at is null", (cur["id"],)) or {})["c"]
    if n:
        raise Conflict(f"{n} live record(s) use this type; move them with “Change type of {n} records” first",
                       current={"records": n})
    if not approved:
        _gate(conn, actor, "node_archive", {"key": key})
    with _translate(conn, "record type"):
        _q(conn, "update kb.node_types set archived_at = now(), status = 'archived' where key = %s", (key,))
    return _type_out(conn, key)


def restore_node_type(conn, actor: Actor, key: str, approved: bool = False) -> dict:
    require(conn, "editor", "restoring a record type")
    _type(conn, key)
    if not approved:
        _gate(conn, actor, "node_restore", {"key": key})
    with _translate(conn, "record type"):
        _q(conn, "update kb.node_types set archived_at = null, status = 'active' where key = %s", (key,))
    return _type_out(conn, key)


def duplicate_node_type(conn, actor: Actor, key: str, approved: bool = False) -> dict:
    src = _type(conn, key)
    n, label = 1, f"{src['label']} (copy)"
    while _q1(conn, "select 1 from kb.node_types where lower(label) = lower(%s)", (label,)):
        n += 1
        label = f"{src['label']} (copy {n})"
    return create_node_type(conn, actor, {
        "label": label, "plural": f"{src['plural']} (copy)" if n == 1 else f"{src['plural']} (copy {n})",
        "description": src["description"], "icon": src["icon"], "color": src["color"],
        "fields": [f for f in src["fields"] if not f.get("archived")], "allowed_parents": src["allowed_parents"],
        "parent_required": src["parent_required"], "default_status": src["default_status"],
        "owner_rule": src["owner_rule"], "is_container": src["is_container"]}, approved=approved)


def change_records_type(conn, actor: Actor, key: str, body: dict, approved: bool = False) -> dict:
    """Move records of type `key` to type `to`, mapping fields old_key → new_key.
    All or nothing: if a moved record's relationships or placement would break a
    rule, nothing moves and the conflicts are listed."""
    require(conn, "editor", "changing the type of records")
    v.only(body, {"to", "ids", "field_map", "reason"})
    src, dst = _type(conn, key), _type(conn, v.text(body, "to", required=True, max_len=40))
    if dst["archived_at"]:
        raise Invalid("the target type is archived", field="to")
    if src["key"] == dst["key"]:
        raise Invalid("choose a different type", field="to")
    fmap = body.get("field_map") or {}
    dst_keys = {f["key"] for f in dst["fields"]}
    bad = [t for t in fmap.values() if t and t not in dst_keys]
    if bad:
        raise Invalid(f"unknown target field(s): {', '.join(bad)}", field="field_map")
    ids = body.get("ids")
    where, args = "n.type_id = %s and n.archived_at is null", [src["id"]]
    if ids:
        where += " and n.id = any(%s)"
        args.append([v.uid(i, "ids") for i in ids])
    rows = _q(conn, f"select n.id, n.name, n.props from kb.nodes n where {where}", args)
    if not rows:
        raise Invalid("no records to move")
    if not approved:
        _gate(conn, actor, "node_change_records", {**body, "key": key})
    moved = 0
    with _translate(conn, "record"):
        for r in rows:
            props = {}
            for old_k, val in r["props"].items():
                new_k = fmap.get(old_k, old_k if old_k in dst_keys else None)
                if new_k:
                    props[new_k] = val
            _q(conn, "update kb.nodes set type_id = %s, props = %s where id = %s",
               (dst["id"], json.dumps(props), r["id"]))
            moved += 1
        broken = _q(conn, """select e.id, s.name as source, t.name as target, et.label from kb.edges e
                             join kb.edge_types et on et.id = e.edge_type_id
                             join kb.nodes s on s.id = e.source_id join kb.nodes t on t.id = e.target_id
                             where e.archived_at is null and (e.source_id = any(%s) or e.target_id = any(%s))
                               and not exists (select 1 from kb.edge_type_rules r where r.edge_type_id = e.edge_type_id
                                   and r.archived_at is null and r.source_type_id = s.type_id and r.target_type_id = t.type_id)""",
                    ([r["id"] for r in rows], [r["id"] for r in rows]))
    if broken:
        # Undo inside this request: the caller's transaction is rolled back by the
        # route on any KbError, so raising here moves nothing.
        raise Invalid(f"{len(broken)} relationship(s) would break the rules of {dst['label']}; nothing was moved",
                      failures=[{"relationship": f"{b['source']} {b['label']} {b['target']}"} for b in broken[:100]])
    return {"moved": moved, "to": dst["key"]}


# ---------------------------------------------------------------------------
# relationship types and rules
# ---------------------------------------------------------------------------

EDGE_FIELDS = {"label", "inverse_label", "description", "cardinality", "allow_self", "rules", "key"}


def _edge_vals(body: dict, partial: bool) -> dict:
    out = {}
    if not partial or "label" in body:
        out["label"] = v.text(body, "label", required=True, max_len=80, allow_empty=False)
    for k in ("inverse_label", "description"):
        if k in body:
            out[k] = v.text(body, k, max_len=300)
    if "cardinality" in body:
        out["cardinality"] = v.choice(body, "cardinality", CARDINALITIES)
    if "allow_self" in body:
        out["allow_self"] = bool(body["allow_self"])
    return out


def _set_rules(conn, ekey: str, rules) -> list[str]:
    """Replace the allowed pairs. Removed pairs are archived (not deleted) and
    the existing relationships that no longer fit are reported, never removed."""
    if not isinstance(rules, list) or not rules:
        raise Invalid("a relationship type needs at least one allowed source → target pair", field="rules")
    want = set()
    for r in rules:
        if not isinstance(r, dict) or not r.get("source") or not r.get("target"):
            raise Invalid("each rule needs a source and a target type", field="rules")
        want.add((r["source"], r["target"]))
    known = {x["key"] for x in _q(conn, "select key from kb.node_types where archived_at is null")}
    bad = sorted({k for p in want for k in p} - known)
    if bad:
        raise Invalid(f"unknown type(s) in rules: {', '.join(bad)}", field="rules")
    have = {(r["source"], r["target"]): r["id"] for r in _q(conn, """
        select r.id, s.key as source, t.key as target from kb.edge_type_rules r join kb.edge_types e on e.id = r.edge_type_id
        join kb.node_types s on s.id = r.source_type_id join kb.node_types t on t.id = r.target_type_id
        where e.key = %s and r.archived_at is null""", (ekey,))}
    warnings = []
    for pair, rid in have.items():
        if pair not in want:
            n = (_q1(conn, """select count(*) as c from kb.edges x join kb.edge_types e on e.id = x.edge_type_id
                              join kb.nodes s on s.id = x.source_id join kb.node_types st on st.id = s.type_id
                              join kb.nodes t on t.id = x.target_id join kb.node_types tt on tt.id = t.type_id
                              where e.key = %s and st.key = %s and tt.key = %s and x.archived_at is null""",
                     (ekey, *pair)) or {})["c"]
            if n:
                warnings.append(f"{n} existing {pair[0]} → {pair[1]} relationship(s) no longer fit the rules; "
                                "they are kept and listed on Data quality")
            _q(conn, "update kb.edge_type_rules set archived_at = now(), status = 'archived' where id = %s", (rid,))
    for s, t in want - set(have):
        _q(conn, """insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
                    select e.id, s.id, t.id from kb.edge_types e, kb.node_types s, kb.node_types t
                    where e.key = %s and s.key = %s and t.key = %s
                    on conflict (edge_type_id, source_type_id, target_type_id) do update set archived_at = null, status = 'active'""",
           (ekey, s, t))
    return warnings


def _edge_out(conn, key: str) -> dict:
    return next(t for t in all_types(conn, include_archived=True)["edge_types"] if t["key"] == key)


def create_edge_type(conn, actor: Actor, body: dict, approved: bool = False) -> dict:
    require(conn, "editor", "adding a relationship type")
    v.only(body, EDGE_FIELDS | {"reason"})
    vals = _edge_vals(body, partial=False)
    key = body.get("key") or slug(vals["label"])
    if _q1(conn, "select 1 from kb.edge_types where lower(label) = lower(%s) and archived_at is null", (vals["label"],)):
        raise Duplicate(f"a relationship type called {vals['label']!r} already exists", field="label")
    if _q1(conn, "select 1 from kb.edge_types where key = %s", (key,)):
        raise Duplicate(f"the key {key!r} is taken; choose another name", field="label")
    if not isinstance(body.get("rules"), list) or not body["rules"]:
        raise Invalid("a relationship type needs at least one allowed source → target pair", field="rules")
    if not approved:
        _gate(conn, actor, "edge_create", {**body, "key": key})
    cols = ["key"] + list(vals)
    with _translate(conn, "relationship type"):
        _q(conn, f"insert into kb.edge_types ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
           [key] + list(vals.values()))
        _set_rules(conn, key, body["rules"])
    return _edge_out(conn, key)


def update_edge_type(conn, actor: Actor, key: str, body: dict, approved: bool = False) -> dict:
    require(conn, "editor", "changing a relationship type")
    v.only(body, EDGE_FIELDS | {"version", "reason"})
    cur = _q1(conn, "select * from kb.edge_types where key = %s for update", (key,))
    if not cur:
        raise NotFound(f"no relationship type {key!r}")
    if cur["version"] != v.version(body):
        raise Conflict("This relationship type changed since you opened it.", current=_edge_out(conn, key))
    vals = _edge_vals(body, partial=True)
    if "label" in vals and _q1(conn, "select 1 from kb.edge_types where lower(label) = lower(%s) and key <> %s "
                                     "and archived_at is null", (vals["label"], key)):
        raise Duplicate(f"a relationship type called {vals['label']!r} already exists", field="label")
    if "cardinality" in vals and vals["cardinality"] != cur["cardinality"]:
        side = {"one_to_many": "target_id", "many_to_one": "source_id"}
        checks = [side[vals["cardinality"]]] if vals["cardinality"] in side else (
            ["target_id", "source_id"] if vals["cardinality"] == "one_to_one" else [])
        for col in checks:
            n = (_q1(conn, f"""select count(*) as c from (select {col} from kb.edges where edge_type_id = %s
                               and archived_at is null group by {col} having count(*) > 1) x""", (cur["id"],)) or {})["c"]
            if n:
                raise Invalid(f"{n} record(s) already have more than one such relationship; "
                              "the cardinality cannot be narrowed until they are fixed", field="cardinality")
    if not approved:
        _gate(conn, actor, "edge_update", {**body, "key": key})
    warnings = []
    with _translate(conn, "relationship type"):
        if vals:
            _q(conn, f"update kb.edge_types set {', '.join(f'{k} = %s' for k in vals)} where key = %s",
               list(vals.values()) + [key])
        if "rules" in body:
            warnings = _set_rules(conn, key, body["rules"])
    out = _edge_out(conn, key)
    out["warnings"] = warnings
    return out


def archive_edge_type(conn, actor: Actor, key: str, approved: bool = False) -> dict:
    require(conn, "editor", "archiving a relationship type")
    cur = _q1(conn, "select * from kb.edge_types where key = %s", (key,))
    if not cur:
        raise NotFound(f"no relationship type {key!r}")
    if cur["is_core"]:
        raise Invalid("core relationship types can be edited but not deleted or archived")
    n = (_q1(conn, "select count(*) as c from kb.edges where edge_type_id = %s and archived_at is null", (cur["id"],)) or {})["c"]
    if n:
        raise Conflict(f"{n} live relationship(s) use this type; remove them first", current={"edges": n})
    if not approved:
        _gate(conn, actor, "edge_archive", {"key": key})
    _q(conn, "update kb.edge_types set archived_at = now(), status = 'archived' where key = %s", (key,))
    return _edge_out(conn, key)


# ---------------------------------------------------------------------------
# link kinds
# ---------------------------------------------------------------------------

def _link_vals(body: dict, partial: bool) -> dict:
    out = {}
    if not partial or "label" in body:
        out["label"] = v.text(body, "label", required=True, max_len=80, allow_empty=False)
    if "icon" in body:
        out["icon"] = v.text(body, "icon", max_len=40) or "link"
    if "patterns" in body:
        pats = body.get("patterns") or []
        if not isinstance(pats, list) or not all(isinstance(p, str) and p.strip() for p in pats):
            raise Invalid("patterns must be a list of regular expressions", field="patterns")
        for p in pats:
            try:
                re.compile(p)
            except re.error as exc:
                raise Invalid(f"pattern {p!r} is not a valid regular expression: {exc}", field="patterns") from None
        out["patterns"] = [p.strip() for p in pats]
    if "defaults" in body:
        d = body.get("defaults") or {}
        if not isinstance(d, dict) or (d.get("kind") and d["kind"] not in v.RESOURCE_KINDS):
            raise Invalid("defaults.kind must be a resource kind", field="defaults")
        out["defaults"] = json.dumps(d)
    if "sort_order" in body:
        out["sort_order"] = int(body["sort_order"])
    return out


def create_link_kind(conn, actor: Actor, body: dict, approved: bool = False) -> dict:
    require(conn, "editor", "adding a link kind")
    v.only(body, {"label", "icon", "patterns", "defaults", "sort_order", "key", "reason"})
    vals = _link_vals(body, partial=False)
    key = body.get("key") or slug(vals["label"])
    if _q1(conn, "select 1 from kb.link_kinds where lower(label) = lower(%s) and archived_at is null", (vals["label"],)):
        raise Duplicate(f"a link kind called {vals['label']!r} already exists", field="label")
    if not approved:
        _gate(conn, actor, "link_create", {**body, "key": key})
    cols = ["key"] + list(vals)
    with _translate(conn, "link kind"):
        _q(conn, f"insert into kb.link_kinds ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
           [key] + list(vals.values()))
    return next(x for x in all_types(conn, True)["link_kinds"] if x["key"] == key)


def update_link_kind(conn, actor: Actor, key: str, body: dict, approved: bool = False) -> dict:
    require(conn, "editor", "changing a link kind")
    v.only(body, {"label", "icon", "patterns", "defaults", "sort_order", "version", "reason"})
    cur = _q1(conn, "select * from kb.link_kinds where key = %s for update", (key,))
    if not cur:
        raise NotFound(f"no link kind {key!r}")
    if cur["version"] != v.version(body):
        raise Conflict("This link kind changed since you opened it.", current=cur)
    vals = _link_vals(body, partial=True)
    if not approved:
        _gate(conn, actor, "link_update", {**body, "key": key})
    with _translate(conn, "link kind"):
        _q(conn, f"update kb.link_kinds set {', '.join(f'{k} = %s' for k in vals)} where key = %s",
           list(vals.values()) + [key])
    return next(x for x in all_types(conn, True)["link_kinds"] if x["key"] == key)


def archive_link_kind(conn, actor: Actor, key: str, approved: bool = False) -> dict:
    require(conn, "editor", "archiving a link kind")
    cur = _q1(conn, "select * from kb.link_kinds where key = %s", (key,))
    if not cur:
        raise NotFound(f"no link kind {key!r}")
    if cur["is_core"]:
        raise Invalid("built-in link kinds can be edited but not deleted or archived")
    if not approved:
        _gate(conn, actor, "link_archive", {"key": key})
    _q(conn, "update kb.resources set link_kind = 'website' where link_kind = %s", (key,))
    _q(conn, "update kb.link_kinds set archived_at = now(), status = 'archived' where key = %s", (key,))
    return next(x for x in all_types(conn, True)["link_kinds"] if x["key"] == key)


def detect_link_kind(conn, url: str) -> str:
    for lk in _q(conn, "select key, patterns from kb.link_kinds where archived_at is null order by sort_order"):
        for p in lk["patterns"]:
            try:
                if re.search(p, url, re.I):
                    return lk["key"]
            except re.error:
                continue
    return "website"


OPS = {
    "node_create": lambda conn, actor, approved, **a: create_node_type(conn, actor, a, approved=approved),
    "node_update": lambda conn, actor, approved, key, **a: update_node_type(conn, actor, key, a, approved=approved),
    "node_archive": lambda conn, actor, approved, key, **a: archive_node_type(conn, actor, key, approved=approved),
    "node_restore": lambda conn, actor, approved, key, **a: restore_node_type(conn, actor, key, approved=approved),
    "node_change_records": lambda conn, actor, approved, key, **a: change_records_type(conn, actor, key, a, approved=approved),
    "edge_create": lambda conn, actor, approved, **a: create_edge_type(conn, actor, a, approved=approved),
    "edge_update": lambda conn, actor, approved, key, **a: update_edge_type(conn, actor, key, a, approved=approved),
    "edge_archive": lambda conn, actor, approved, key, **a: archive_edge_type(conn, actor, key, approved=approved),
    "link_create": lambda conn, actor, approved, **a: create_link_kind(conn, actor, a, approved=approved),
    "link_update": lambda conn, actor, approved, key, **a: update_link_kind(conn, actor, key, a, approved=approved),
    "link_archive": lambda conn, actor, approved, key, **a: archive_link_kind(conn, actor, key, approved=approved),
}
