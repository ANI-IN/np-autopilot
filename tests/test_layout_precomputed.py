"""pipeline/lib/layout.py — the client's simulation, run once at projection.

The vectorised version must be the SAME arithmetic as public/index.html
`step()`, not an approximation of it. So it is checked against a line-by-line
transliteration of that loop — nested, sequential, no numpy — on a small graph
where the loop is cheap.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import layout                                       # noqa: E402

INDEX = (REPO / "public" / "index.html").read_text(encoding="utf-8")


def _transliterated(ids, pairs):
    """public/index.html step(), as written, over the same start positions."""
    ids = sorted(set(ids))
    n = len(ids)
    rad = max(30.0, math.sqrt(n) * 10.0)
    A = [{"id": i, "x": (layout._unit(i, "x") - .5) * rad,
          "y": (layout._unit(i, "y") - .5) * rad, "vx": 0.0, "vy": 0.0} for i in ids]
    by = {a["id"]: a for a in A}
    E = [(s, t) for s, t in pairs if s in by and t in by]
    alpha, frames = 1.0, 0
    while True:
        K = alpha
        for a in A:
            a["vx"] *= .85; a["vy"] *= .85
            a["vx"] += (0 - a["x"]) * .006 * K; a["vy"] += (0 - a["y"]) * .006 * K
        for i in range(n):
            a = A[i]
            for j in range(i + 1, min(n, i + 12)):
                b = A[j]
                dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                d2 = dx * dx + dy * dy or 1
                if d2 < 5000:
                    f = 110 / d2 * K
                    a["vx"] += dx * f; a["vy"] += dy * f
                    b["vx"] -= dx * f; b["vy"] -= dy * f
        for s, t in E:
            a, b = by[s], by[t]
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            d = math.hypot(dx, dy) or 1
            f = (d - 58) * .006 * K
            a["vx"] += dx / d * f; a["vy"] += dy / d * f
            b["vx"] -= dx / d * f; b["vy"] -= dy / d * f
        for a in A:
            a["x"] += a["vx"]; a["y"] += a["vy"]
        frames += 1
        alpha *= .985
        if alpha < .004:
            break
    return {a["id"]: (a["x"], a["y"]) for a in A}, frames


def _graph(n=60, m=90, seed=7):
    rnd = random.Random(seed)
    ids = [f"n{i:03d}" for i in range(n)]
    pairs = [(rnd.choice(ids), rnd.choice(ids)) for _ in range(m)]
    return ids, [(s, t) for s, t in pairs if s != t]


def _worst(got, want):
    return max(math.hypot(got[i][0] - want[i][0], got[i][1] - want[i][1]) for i in want)


def _for_frames(ids, pairs, frames, monkeypatch):
    """Both simulations, stopped after `frames` frames instead of 366."""
    stop = 0.985 ** frames * 1.0000001
    monkeypatch.setattr(layout, "ALPHA_MIN", stop)
    got = layout.compute(ids, pairs)
    src = Path(__file__).read_text(encoding="utf-8").replace(
        "if alpha < .004:", f"if alpha < {stop!r}:")
    ns = {"__file__": __file__, "__name__": "transliterated"}
    exec(compile(src, __file__, "exec"), ns)
    want, n = ns["_transliterated"](ids, pairs)
    assert n == frames
    return got, want


def test_the_vectorised_layout_is_the_clients_arithmetic(monkeypatch):
    """Frame by frame the two agree to float rounding (measured: 3e-14 after one
    frame). The system is chaotic, so rounding in a different SUMMATION ORDER
    grows ~2x every 15 frames — that is not a difference in the arithmetic, and
    the client's own JS sums in yet another order. So: exact over 20 frames..."""
    ids, pairs = _graph()
    got, want = _for_frames(ids, pairs, 20, monkeypatch)
    assert _worst(got, want) < 1e-9


def test_after_full_cooling_the_drift_is_far_below_a_pixel():
    """...and after all 366, the rounding drift stays far below a node's radius
    (3 world units at the smallest). Measured 0.036 on this graph."""
    ids, pairs = _graph()
    want, _ = _transliterated(ids, pairs)
    assert _worst(layout.compute(ids, pairs), want) < 0.5


def test_it_cools_for_exactly_the_clients_frame_count():
    _, frames = _transliterated(*_graph(n=5, m=4))
    assert frames == 366
    assert math.ceil(math.log(0.004) / math.log(0.985)) == 366


def test_the_constants_are_the_clients():
    """If the client's simulation is retuned, the precomputed one must follow."""
    for js in ("ALPHA_DECAY=0.985", "ALPHA_MIN=0.004", "i+12", "110/d2",
               "(d-58)*.006", "*.006*K", "n.vx*=.85"):
        assert js in INDEX, f"public/index.html no longer contains {js!r}"


def test_the_same_graph_always_lays_out_the_same():
    ids, pairs = _graph()
    assert layout.compute(ids, pairs) == layout.compute(list(reversed(ids)), pairs)


def test_an_empty_or_edgeless_graph_is_fine():
    assert layout.compute([], []) == {}
    out = layout.compute(["a", "b"], [])
    assert set(out) == {"a", "b"} and all(map(math.isfinite, out["a"]))


def test_the_structure_types_are_what_the_api_serves():
    """One definition: the projection lays out exactly the nodes structure() serves."""
    sys.path.insert(0, str(REPO / "web"))
    from lib import data
    assert data.STRUCTURE_TYPES == layout.structure_types()[0]
