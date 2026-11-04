"""The legacy step (run 5, Part 3): archive what belongs only to the older
sheets, reversibly. Re-runnable (the sync calls it on every run), and one
command restores everything (`restore`, pipeline/kb_legacy.py).

Rules, in the KB's own terms (is_legacy follows NP Autopilot: sync.np_categories):
  - every legacy DOMAIN is archived, except one a current item is connected
    to (today: current instructors' declared expertise, `sme`): archiving it
    would archive that connection too (the cascade), so it stays and is
    reported (domains_with_current_connections);
  - a legacy MODULE is archived when the domains it belongs to (directly, or
    through a programme that covers the domain and contains the module, as
    NP Autopilot's model() does) are all legacy, AND it is connected to no
    current item;
  - a legacy INSTRUCTOR likewise: its domains (declared expertise, and the
    domains of the modules it teaches) are all legacy, and no current item;
  - "current item" = a live, non-legacy domain, module, instructor, session
    or week (the categories NP Autopilot splits into current and legacy).
  Never archived: anything connected to a current item (reported), and legacy
  modules or instructors with no domain at all (NP Autopilot's "unlinked";
  reported, left as they are).
Archiving goes through kb.nodes (the cascade trigger archives their
relationships and links and restores exactly those). Nothing is deleted.
"""
from __future__ import annotations

from collections import defaultdict

CURRENT_TYPES = ("domain", "module", "instructor", "session", "week")


def _q(conn, sql, p=()):
    return conn.execute(sql, p).fetchall()


def plan(conn) -> dict:
    nodes = {str(r[0]): {"type": r[1], "legacy": r[2]} for r in _q(conn, """
        select n.id, t.key, n.is_legacy from kb.nodes n join kb.node_types t on t.id = n.type_id where n.archived_at is null""")}
    edges = [(str(s), str(t), k) for s, t, k in _q(conn, """
        select e.source_id, e.target_id, et.key from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
        where e.archived_at is null""")]
    typ = lambda i: nodes.get(i, {}).get("type")                            # noqa: E731
    covers = defaultdict(set)                                              # programme -> domains
    for s, t, k in edges:
        if k == "covers" and typ(s) == "program" and typ(t) == "domain":
            covers[s].add(t)
    mod_dom = defaultdict(set)
    for s, t, k in edges:
        if k == "contains" and typ(t) == "module":
            if typ(s) == "domain":
                mod_dom[t].add(s)
            elif typ(s) == "program":
                mod_dom[t] |= covers.get(s, set())
    ins_dom = defaultdict(set)
    for s, t, k in edges:
        if typ(s) == "instructor" and k == "sme" and typ(t) == "domain":
            ins_dom[s].add(t)
        if typ(s) == "instructor" and k == "teaches" and typ(t) == "module":
            ins_dom[s] |= mod_dom.get(t, set())
    nbrs = defaultdict(set)
    for s, t, _ in edges:
        nbrs[s].add(t); nbrs[t].add(s)
    is_current = lambda i: i in nodes and nodes[i]["type"] in CURRENT_TYPES and not nodes[i]["legacy"]   # noqa: E731
    out = {"domains": [], "modules": [], "instructors": [], "kept_connected_to_current": [], "no_domain_left_as_is": [],
           "domains_with_current_connections": []}
    for i, n in nodes.items():
        if n["type"] == "domain" and n["legacy"]:
            if any(is_current(x) for x in nbrs[i]):
                out["domains_with_current_connections"].append(i)
            else:
                out["domains"].append(i)
    for i, n in nodes.items():
        if not n["legacy"] or n["type"] not in ("module", "instructor"):
            continue
        doms = mod_dom[i] if n["type"] == "module" else ins_dom[i]
        if not doms:
            out["no_domain_left_as_is"].append(i); continue
        if any(not nodes.get(d, {}).get("legacy", True) for d in doms):
            continue                                                       # belongs to a current domain too
        if any(is_current(x) for x in nbrs[i]):
            out["kept_connected_to_current"].append(i); continue
        out["modules" if n["type"] == "module" else "instructors"].append(i)
    return out


def archive(conn, *_ignored) -> dict:
    """Archive per plan(); re-runnable (already-archived records are skipped).
    Returns counts (and ids in the lists)."""
    p = plan(conn)
    done = {"domains": 0, "modules": 0, "instructors": 0}
    for kind in ("modules", "instructors", "domains"):                    # dependents first, then domains
        ids = [str(r[0]) for r in conn.execute("""update kb.nodes set archived_at = now(), status = 'archived'
                                                   where id = any(%s::uuid[]) and archived_at is null returning id""",
                                                (p[kind],)).fetchall()]
        conn.execute("""insert into kb.legacy_archive (node_id, reason) select unnest(%s::uuid[]), %s
                        on conflict (node_id) do nothing""", (ids, f"legacy {kind[:-1]}"))
        done[kind] = len(ids)
    return {"archived_now": done, "planned": {k: len(v) for k, v in p.items()},
            "kept_connected_to_current": p["kept_connected_to_current"],
            "domains_with_current_connections": p["domains_with_current_connections"]}


def restore(conn) -> dict:
    """Undo every archive the legacy step made, in ONE statement: the cascade
    trigger restores a relationship only when both ends are live, and row
    triggers of a single UPDATE run after all its rows changed, so links
    between two legacy records come back too (one by one, they would not)."""
    ids = [str(r[0]) for r in _q(conn, "select node_id from kb.legacy_archive")]
    n = conn.execute("""update kb.nodes set archived_at = null, status = 'active'
                        where id = any(%s::uuid[]) and archived_at is not null""", (ids,)).rowcount
    conn.execute("delete from kb.legacy_archive where node_id = any(%s::uuid[])", (ids,))
    return {"restored": n, "entries_cleared": len(ids)}
