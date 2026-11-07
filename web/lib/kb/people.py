"""Owners become real people (run 6, B1).

A person record (an instructor, a team member) carries an e-mail address in
kb.person_accounts (0030, extended by 0033). When the account with that address
signs in, the record is linked to it and the person owns, as an account, what
the record owns by role.

  - Settings -> People (admins): every person record with its e-mail, and a
    bulk CSV upload (name,email) previewed first: exact matches, matches that
    differ only in case or spacing, suggested near matches an admin confirms,
    and names that are ambiguous or unknown. NOTHING is written before the
    admin confirms the rows (apply).
  - On sign-in: the e-mail first, else a name that matches exactly ONE unlinked
    person record (kb.auto_link_person). Two records with the same name are
    never linked automatically.
  - "Claim this profile": a proposal an admin approves in Approvals.
  - "Owned by you": records owned by your account or by your person record.

E-mail addresses are personal data: they are shown to admins only (RLS on
kb.person_accounts), never copied into the append-only audit log or kb.changes
(person_accounts writes emit change-only events, 0032), and never written into
a proposal.
"""
from __future__ import annotations

import csv
import difflib
import io
import re

from . import validate as v
from .errors import Invalid
from .service import PERSON_TYPES, Actor, _q, _q1, _translate, require
from .profile import OWNED_BY

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ROWS = 2000
NEAR = 0.82            # difflib ratio for a suggested near match (the admin confirms it)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _key(s: str) -> str:
    """= kb.person_name_key (0033): case and spacing ignored, and the " (2)" the
    import adds to keep two same-name records apart is not part of the name."""
    return _norm(re.sub(r"\s*\(\d+\)\s*$", "", s or ""))


def _persons(conn) -> list[dict]:
    return _q(conn, """select n.id, n.name, n.name_norm, t.key as type, n.is_legacy,
                              pa.email, pa.user_id, pa.linked_at, pa.linked_by
                       from kb.nodes n join kb.node_types t on t.id = n.type_id
                       left join kb.person_accounts pa on pa.node_id = n.id
                       where n.archived_at is null and t.key = any(%s)
                       order by n.is_legacy, n.name_norm""", (list(PERSON_TYPES),))


def list_people(conn, params: dict) -> dict:
    """Admins: person records with their e-mail and link state, and counts."""
    require(conn, "admin", "seeing people's e-mail addresses")
    rows = _persons(conn)
    q = _norm(params.get("q") or "")
    state = params.get("state") or ""
    if q:
        rows = [r for r in rows if q in r["name_norm"] or q in (r["email"] or "")]
    if state == "linked":
        rows = [r for r in rows if r["user_id"]]
    elif state == "waiting":
        rows = [r for r in rows if r["email"] and not r["user_id"]]
    elif state == "none":
        rows = [r for r in rows if not r["email"]]
    elif state != "all":
        rows = [r for r in rows if not r["is_legacy"] or r["email"]]
    limit = max(1, min(int(params.get("limit") or 200), 1000))
    counts = _q1(conn, """select count(*) filter (where pa.user_id is not null) as linked,
                                 count(*) filter (where pa.email is not null and pa.user_id is null) as waiting,
                                 count(*) filter (where pa.node_id is null and not n.is_legacy) as no_email
                          from kb.nodes n join kb.node_types t on t.id = n.type_id
                          left join kb.person_accounts pa on pa.node_id = n.id
                          where n.archived_at is null and t.key = any(%s)""", (list(PERSON_TYPES),))
    claims = _q(conn, """select p.id, p.target_id as node_id, n.name, p.created_by, p.created_at
                         from kb.proposals p join kb.nodes n on n.id = p.target_id
                         where p.action = 'claim' and p.status = 'pending' order by p.created_at""")
    return {"items": [{k: r[k] for k in ("id", "name", "type", "is_legacy", "email", "user_id", "linked_at", "linked_by")}
                      for r in rows[:limit]],
            "total": len(rows), "counts": counts, "claims": claims}


def _parse_csv(text: str) -> list[dict]:
    if not isinstance(text, str) or not text.strip():
        raise Invalid("paste or upload a CSV with two columns: name,email", field="csv")
    rows = list(csv.reader(io.StringIO(text.strip())))
    if rows and [c.strip().lower() for c in rows[0][:2]] == ["name", "email"]:
        rows = rows[1:]
    if len(rows) > MAX_ROWS:
        raise Invalid(f"at most {MAX_ROWS} rows at once", field="csv")
    out = []
    for i, r in enumerate(rows, 1):
        if not any(c.strip() for c in r):
            continue
        name = (r[0] if r else "").strip()
        email = (r[1] if len(r) > 1 else "").strip().lower()
        out.append({"row": i, "name": name, "email": email})
    return out


def csv_preview(conn, actor: Actor, body: dict) -> dict:
    """What a CSV would link, row by row. Writes NOTHING.

    status: exact (same name), normalised (same name ignoring case and
    spacing), suggested (a near match the admin must confirm), ambiguous (two
    or more records carry that name: the admin picks), none (no record), and
    invalid (no name, or not an e-mail address). `current_email` tells the admin
    that confirming replaces an address; `email_taken_by` that the address is
    already on another record."""
    require(conn, "admin", "linking people to sign-in accounts")
    v.only(body, {"csv"})
    rows = _parse_csv(body.get("csv"))
    persons = _persons(conn)
    by_exact, by_norm = {}, {}
    for p in persons:
        by_exact.setdefault(p["name"], []).append(p)
        by_norm.setdefault(_key(p["name"]), []).append(p)
    names = list(by_norm)
    taken = {p["email"]: p for p in persons if p["email"]}

    def brief(p):
        return {"id": p["id"], "name": p["name"], "type": p["type"], "is_legacy": p["is_legacy"]}
    out = []
    for r in rows:
        item = dict(r)
        if not r["name"] or not EMAIL.match(r["email"] or ""):
            item["status"] = "invalid"
            item["reason"] = "no name" if not r["name"] else "not an e-mail address"
            out.append(item)
            continue
        exact = by_exact.get(r["name"]) or []
        norm = by_norm.get(_key(r["name"])) or []
        if len(exact) == 1 and len(norm) == 1:
            item["status"], item["match"] = "exact", brief(exact[0])
        elif len(norm) == 1:
            item["status"], item["match"] = "normalised", brief(norm[0])
        elif len(norm) > 1:
            # never picked for the admin: two records with this name are two people
            item["status"], item["candidates"] = "ambiguous", [brief(p) for p in norm]
        else:
            near = difflib.get_close_matches(_key(r["name"]), names, n=3, cutoff=NEAR)
            cands = [p for nm in near for p in by_norm[nm]]
            item["status"] = "suggested" if cands else "none"
            if cands:
                item["candidates"] = [brief(p) for p in cands]
        m = item.get("match")
        if m:
            cur = next(p for p in persons if p["id"] == m["id"])
            if cur["email"] and cur["email"] != r["email"]:
                item["current_email"] = cur["email"]
        other = taken.get(r["email"])
        if other and (not m or other["id"] != m["id"]):
            item["email_taken_by"] = brief(other)
        out.append(item)
    summary = {}
    for it in out:
        summary[it["status"]] = summary.get(it["status"], 0) + 1
    return {"rows": out, "summary": summary, "written": 0}


def csv_apply(conn, actor: Actor, body: dict) -> dict:
    """Write the rows the admin confirmed: [{node_id, email}]. One link per
    person record and per address (the database enforces both)."""
    require(conn, "admin", "linking people to sign-in accounts")
    v.only(body, {"links"})
    links = body.get("links")
    if not isinstance(links, list) or not links or len(links) > MAX_ROWS:
        raise Invalid(f"confirm 1-{MAX_ROWS} rows", field="links")
    seen_n, seen_e, rows = set(), set(), []
    for i, ln in enumerate(links):
        if not isinstance(ln, dict):
            raise Invalid("each row needs node_id and email", field=f"links[{i}]")
        nid = str(v.uid(ln.get("node_id"), f"links[{i}].node_id"))
        email = str(ln.get("email") or "").strip().lower()
        if not EMAIL.match(email) or len(email) > 254:
            raise Invalid(f"row {i + 1}: not an e-mail address", field=f"links[{i}].email")
        if nid in seen_n or email in seen_e:
            raise Invalid(f"row {i + 1}: the same record or address appears twice", field=f"links[{i}]")
        seen_n.add(nid)
        seen_e.add(email)
        rows.append((nid, email))
    ok = {r["id"] for r in _q(conn, """select n.id::text as id from kb.nodes n join kb.node_types t on t.id = n.type_id
                                        where n.id = any(%s::uuid[]) and n.archived_at is null and t.key = any(%s)""",
                                     ([r[0] for r in rows], list(PERSON_TYPES)))}
    bad = [r[0] for r in rows if r[0] not in ok]
    if bad:
        raise Invalid(f"{len(bad)} row(s) do not point at a live instructor or team member", field="links")
    with _translate(conn, "person account"):
        _q(conn, """insert into kb.person_accounts (node_id, email, linked_by)
                    select n, e, 'csv' from unnest(%s::uuid[], %s::text[]) u(n, e)
                    on conflict (node_id) do update set email = excluded.email, linked_by = 'csv'
                    returning node_id""", ([r[0] for r in rows], [r[1] for r in rows]))
    linked = _q1(conn, """select count(*) as c from kb.person_accounts
                          where node_id = any(%s::uuid[]) and user_id is not null""", ([r[0] for r in rows],))["c"]
    return {"written": len(rows), "linked_now": linked, "waiting_for_sign_in": len(rows) - linked}


def link_me(conn, actor: Actor) -> dict:
    """The automatic link for the caller (the app asks on load; sign-in does it
    too, 0033). ambiguous -> the candidates to claim; none -> nothing found."""
    require(conn, "viewer", "linking your profile")
    with _translate(conn, "person account"):
        status = _q1(conn, "select kb.link_me() as s")["s"]
    me = _q1(conn, """select pa.node_id as id, n.name, t.key as type from kb.person_accounts pa
                      join kb.nodes n on n.id = pa.node_id join kb.node_types t on t.id = n.type_id
                      where pa.user_id = auth.uid()""")
    out = {"status": status, "person": me}
    if status == "ambiguous":
        out["candidates"] = _q(conn, "select id, name, type from kb.person_candidates_for_me()")
    out["pending_claims"] = _q(conn, """select p.id, p.target_id as node_id, n.name from kb.proposals p
                                        join kb.nodes n on n.id = p.target_id
                                        where p.action = 'claim' and p.status = 'pending' and p.created_by = auth.uid()""")
    return out


def owned_by_me(conn, actor: Actor, params: dict | None = None) -> dict:
    """Records owned by your account (owner / co-owner), records your person record OWNS (owned_by:
    an NP team member), and the modules it is an SME for (with the role)."""
    require(conn, "viewer", "listing what you own")
    limit = max(1, min(int((params or {}).get("limit") or 50), 500))
    rows = _q(conn, f"""
        with me as (select auth.uid() as uid,
                           (select node_id from kb.person_accounts where user_id = auth.uid()) as pid),
        rel as (
            select e.source_id as node_id, 'owner' as how, 0 as rank from kb.edges e cross join me
              join kb.edge_types et on et.id = e.edge_type_id and et.key = '{OWNED_BY}'
             where me.pid is not null and e.target_id = me.pid and e.archived_at is null
            union all
            select e.target_id, case e.props->>'role' when 'primary' then 'primary SME'
                                    when 'backup' then 'backup SME ' || coalesce(e.props->>'rank', '')
                                    else 'SME (' || coalesce(e.props->>'role', '') || ')' end, 1
              from kb.edges e cross join me
              join kb.edge_types et on et.id = e.edge_type_id and et.key = 'sme'
             where me.pid is not null and e.source_id = me.pid and e.archived_at is null)
        select n.id, n.name, t.key as type, n.updated_at,
               coalesce(case when n.owner_id = me.uid then 'record owner'
                             when me.uid = any(n.co_owners) then 'co-owner' end,
                        (select r.how from rel r where r.node_id = n.id order by r.rank limit 1)) as how
        from kb.nodes n join kb.node_types t on t.id = n.type_id cross join me
        where n.archived_at is null
          and (n.owner_id = me.uid or me.uid = any(n.co_owners) or exists (select 1 from rel r where r.node_id = n.id))
        order by (n.owner_id = me.uid or exists (select 1 from rel r where r.node_id = n.id and r.rank = 0)) desc,
                 n.updated_at desc""")
    me = _q1(conn, """select pa.node_id as id, n.name, t.key as type from kb.person_accounts pa
                      join kb.nodes n on n.id = pa.node_id join kb.node_types t on t.id = n.type_id
                      where pa.user_id = auth.uid()""")
    return {"items": rows[:limit], "total": len(rows), "person": me}


def legacy_expertise_domains(conn) -> dict:
    """Data quality: the legacy domains current instructors still declare as
    their expertise. They stay unarchived on purpose (D44): archiving a domain
    archives its relationships, and these are current people's claims."""
    rows = _q(conn, """
        select d.id, d.name, count(distinct i.id) as instructors
        from kb.nodes d join kb.node_types dt on dt.id = d.type_id and dt.key = 'domain'
        join kb.edges e on e.target_id = d.id and e.archived_at is null
        join kb.edge_types et on et.id = e.edge_type_id and et.key = 'sme'
        join kb.nodes i on i.id = e.source_id and i.archived_at is null and not i.is_legacy
        where d.is_legacy and d.archived_at is null
        group by d.id, d.name order by d.name""")
    return {"items": rows, "total": len(rows)}


def no_owner(conn, limit: int = 100) -> dict:
    """Data quality: current records with no owner, of the types whose
    "owner expected" is ON (0032; editable in Settings -> Types)."""
    rows = _q(conn, f"""select n.id, n.name, t.key as type from kb.nodes n join kb.node_types t on t.id = n.type_id
                       where n.archived_at is null and not n.is_legacy and t.owner_expected and t.archived_at is null
                         and n.owner_id is null and not exists (select 1 from kb.edges e join kb.edge_types et
                             on et.id = e.edge_type_id and et.key = '{OWNED_BY}' where e.source_id = n.id and e.archived_at is null)
                       order by t.sort_order, n.name_norm limit %s""", (max(1, min(int(limit), 500)),))
    total = _q1(conn, f"""select count(*) as c from kb.nodes n join kb.node_types t on t.id = n.type_id
                         where n.archived_at is null and not n.is_legacy and t.owner_expected and t.archived_at is null
                           and n.owner_id is null and not exists (select 1 from kb.edges e join kb.edge_types et
                               on et.id = e.edge_type_id and et.key = '{OWNED_BY}' where e.source_id = n.id and e.archived_at is null)""")["c"]
    return {"items": rows, "total": total}
