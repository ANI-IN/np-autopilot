"""The structure view's layout, computed once at projection time (B3).

The client used to run this simulation on every page load — 366 frames, ~6.4 s
to settle — to recompute coordinates for a graph that only changes when the
projection runs. project_graph.py now runs it once and stores the result in
`node_layout` (migration 0021); /api/structure ships it; the client starts
frozen.

IT IS THE CLIENT'S OWN SIMULATION, PORTED — public/index.html `step()`: the
same anchor pull, the same windowed repulsion (each node against the next 11
in order), the same springs (rest length 58), the same cooling (x0.985 from 1
to below 0.004). Within one frame the client only ACCUMULATES velocities and
moves every node at the end, so a vectorised frame is the same arithmetic,
not an approximation of it.

What differs, on purpose: the starting scatter is derived from each node's id
instead of Math.random(), and nodes are ordered by id rather than by whatever
order the API returned them in — so the same graph always lays out the same
way, and a re-projection of identical content moves nothing.

STRUCTURE TYPES live here, not in web/lib/data.py: the projection and the API
must agree on which nodes the structure view holds, and the pipeline must not
import the web layer.
"""
from __future__ import annotations

import hashlib
import math

from pipeline.lib import taxonomy as _tax

ALPHA_DECAY, ALPHA_MIN = 0.985, 0.004
WINDOW = 12                  # j in (i, i+12): each node repels the next 11
REPULSE, REPULSE_RANGE2 = 110.0, 5000.0
SPRING, REST = 0.006, 58.0
ANCHOR = 0.006
DAMPING = 0.85


def structure_types() -> tuple[set, set]:
    """(shown by default, behind a toggle). Derived from edge endpoints."""
    def tgt(role):
        return _tax.edge_endpoints(_tax.edge_for_role(role))[1]

    def src(role):
        return _tax.edge_endpoints(_tax.edge_for_role(role))[0]

    # DECKS ARE CORE since the owner review of 2026-09-30: the default map
    # shows current decks linked to their session or module, and a Decks chip
    # that read 0 until a module was opened was reporting the payload, not
    # the graph. Topics, files, repos and curriculum docs stay deferred.
    core = {"domain", "program", "module", "person", "instructor", "theme",
            "workflow",
            tgt("module_week"), tgt("module_session"),
            tgt("module_assignment"), tgt("assignment_reviewed_in"),
            tgt("module_deck")}
    deferred = {"file", tgt("module_topic"),
                src("curriculum_module"), tgt("module_repo")}
    return core, deferred


def _unit(node_id: str, salt: str) -> float:
    """A deterministic stand-in for Math.random(), in [0, 1)."""
    h = hashlib.sha256(f"{salt}:{node_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def compute(node_ids: list[str], edge_pairs: list[tuple[str, str]]) -> dict:
    """{node_id: (x, y)} for the structure view. Deterministic."""
    import numpy as np

    ids = sorted(set(node_ids))
    n = len(ids)
    if n == 0:
        return {}
    ix = {v: i for i, v in enumerate(ids)}
    rad = max(30.0, math.sqrt(n) * 10.0)
    x = np.array([(_unit(i, "x") - .5) * rad for i in ids])
    y = np.array([(_unit(i, "y") - .5) * rad for i in ids])
    vx = np.zeros(n)
    vy = np.zeros(n)

    pairs = [(ix[s], ix[t]) for s, t in edge_pairs if s in ix and t in ix]
    es = np.array([p[0] for p in pairs], dtype=np.int64)
    et = np.array([p[1] for p in pairs], dtype=np.int64)
    ri = np.concatenate([np.arange(n - k) for k in range(1, WINDOW)])
    rj = np.concatenate([np.arange(k, n) for k in range(1, WINDOW)])

    alpha = 1.0
    while True:
        k = alpha
        vx *= DAMPING
        vy *= DAMPING
        vx += (0.0 - x) * ANCHOR * k          # every anchor is the origin
        vy += (0.0 - y) * ANCHOR * k
        if len(ri):
            dx = x[ri] - x[rj]
            dy = y[ri] - y[rj]
            d2 = dx * dx + dy * dy
            d2[d2 == 0] = 1.0
            near = d2 < REPULSE_RANGE2
            f = np.where(near, REPULSE / d2 * k, 0.0)
            np.add.at(vx, ri, dx * f)
            np.add.at(vy, ri, dy * f)
            np.add.at(vx, rj, -dx * f)
            np.add.at(vy, rj, -dy * f)
        if len(es):
            dx = x[et] - x[es]
            dy = y[et] - y[es]
            d = np.hypot(dx, dy)
            d[d == 0] = 1.0
            f = (d - REST) * SPRING * k
            np.add.at(vx, es, dx / d * f)
            np.add.at(vy, es, dy / d * f)
            np.add.at(vx, et, -dx / d * f)
            np.add.at(vy, et, -dy / d * f)
        x += vx
        y += vy
        alpha *= ALPHA_DECAY
        if alpha < ALPHA_MIN:
            break
    return {i: (float(x[k]), float(y[k])) for i, k in ix.items()}


def for_graph(graph: dict) -> dict:
    """The layout of `graph`'s structure layer — the nodes and edges
    /api/structure serves (web/lib/data.py::structure)."""
    core, _ = structure_types()
    prov = _tax.edge_for_role("provenance")
    ids = [n["id"] for n in graph["nodes"] if n["type"] in core]
    keep = set(ids)
    pairs = [(e["source"], e["target"]) for e in graph["edges"]
             if e["rel"] != prov and e["source"] in keep and e["target"] in keep]
    return compute(ids, pairs)
