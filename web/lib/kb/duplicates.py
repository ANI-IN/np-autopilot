"""Near-duplicate records: same type, trigram similarity of the normalised
name >= a threshold (run 6, B5).

The same answer as the SQL it replaces,

    select ... from kb.nodes a join kb.nodes b on a.type_id = b.type_id and a.id < b.id
    where ... and extensions.similarity(a.name_norm, b.name_norm) >= %s
    order by similarity desc limit %s

which compared EVERY pair of same-type records: 3.7 million similarity() calls
for the 2,733 topics of the real data, 25-30 s per Data quality load (the
trigram index cannot help: RLS keeps the non-leakproof `%` operator out of the
index scan). Here the database returns each live record's trigram set once
(`show_trgm`, so the trigrams are pg_trgm's own), and a prefix-filtered
similarity join (PPJoin: Xiao et al., 2008) finds exactly the pairs whose
Jaccard similarity -- which is what pg_trgm's similarity() computes -- reaches
the threshold, comparing only pairs that share a rare trigram. The similarity
is rounded through float4, as pg_trgm returns it, so boundary cases agree.

Runs as the caller under RLS (one SELECT). Results are cached per caller and
role, keyed by the newest kb.changes id, so any audited write (a rename, an
archive, a type change) invalidates them at once; the pattern of
api/kb_routes.py `_cached`.
"""
from __future__ import annotations

import heapq
import math
import struct
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from .errors import Invalid

_EPS = 1e-9
_CACHE: dict = {}
_CACHE_MAX = 32
MAX_LIMIT = 200


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def _numeric3(sim: float) -> Decimal:
    """`round(similarity(...)::numeric, 3)`: float4 -> numeric keeps 6
    significant digits, then numeric rounding (half away from zero)."""
    return Decimal(f"{sim:.6g}").quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def similar_pairs(records: list[tuple], threshold: float):
    """records: (group, trigrams). Yields (i, j, similarity) for every pair of
    records in the same group whose trigram-set Jaccard similarity, as float4,
    is >= threshold. Exact (no pair is missed): the prefix, length and
    positional filters only discard pairs that cannot reach the threshold."""
    t = float(threshold)
    freq: dict = defaultdict(int)
    for _, grams in records:
        for g in set(grams):
            freq[g] += 1
    rank = {g: n for n, g in enumerate(sorted(freq, key=lambda g: (freq[g], g)))}
    recs = sorted(((i, grp, sorted({rank[g] for g in grams})) for i, (grp, grams) in enumerate(records) if grams),
                  key=lambda r: len(r[2]))
    sets = [frozenset(r[2]) for r in recs]
    coef = t / (1 + t)
    index: dict = defaultdict(list)
    ceil = math.ceil
    for xi, (orig, grp, s) in enumerate(recs):
        k = len(s)
        probe = k - ceil(t * k - _EPS) + 1
        minlen = t * k - _EPS
        overlap: dict = {}
        for pos in range(probe):
            entries = index.get((grp, s[pos]))
            if not entries:
                continue
            rest = k - pos - 1
            for yi, ypos, ky in entries:
                a = overlap.get(yi, 0)
                if a < 0 or ky < minlen:
                    continue
                if a + 1 + min(rest, ky - ypos - 1) >= ceil(coef * (k + ky) - _EPS):
                    overlap[yi] = a + 1
                else:
                    overlap[yi] = -1
        for pos in range(k - ceil(2 * coef * k - _EPS) + 1):
            index[(grp, s[pos])].append((xi, pos, k))
        sx = sets[xi]
        for yi, a in overlap.items():
            if a > 0:
                sy = sets[yi]
                inter = len(sx & sy)
                sim = _f32(inter / (k + len(sy) - inter))
                if sim >= t:
                    yield recs[yi][0], orig, sim


def _all_pairs(conn, threshold: float, keep: int | None = MAX_LIMIT) -> list[dict]:
    """The `keep` most similar pairs (all of them when keep is None), most
    similar first, then by record id. Memory stays bounded by `keep` however
    many pairs qualify (a type full of near-identical names)."""
    with conn.cursor() as cur:
        cur.execute("""select n.id, n.name, t.key as type, n.type_id, extensions.show_trgm(n.name_norm) as grams
                       from kb.nodes n join kb.node_types t on t.id = n.type_id
                       where n.archived_at is null order by n.id""")
        rows = cur.fetchall()
    # Rows are in id order, so the lower index is the lower id (the `a` side).
    found = ((min(i, j), max(i, j), _numeric3(sim))
             for i, j, sim in similar_pairs([(r[3], r[4]) for r in rows], threshold))
    rank = lambda p: (p[2], -p[0], -p[1])                                   # noqa: E731
    best = sorted(found, key=rank, reverse=True) if keep is None else heapq.nlargest(keep, found, key=rank)
    return [{"a_id": rows[i][0], "a_name": rows[i][1], "b_id": rows[j][0], "b_name": rows[j][1],
             "type": rows[i][2], "similarity": sim} for i, j, sim in best]


def find(conn, threshold: float = 0.6, limit: int = 50) -> list[dict]:
    """Near-duplicates by trigram similarity within a type. RANKS; never merges.
    Same contract as service.find_duplicate_nodes."""
    try:
        threshold, limit = float(threshold), int(limit)
    except (TypeError, ValueError):
        raise Invalid("threshold must be a number and limit a whole number", field="threshold") from None
    if not math.isfinite(threshold):
        raise Invalid("threshold must be a number between 0.3 and 0.99", field="threshold")
    threshold = min(max(threshold, 0.3), 0.99)
    limit = max(0, min(limit, MAX_LIMIT))
    with conn.cursor() as cur:
        cur.execute("""select coalesce((select max(id) from kb.changes), 0),
                              current_setting('request.jwt.claims', true), kb.role()""")
        head, claims, role = cur.fetchone()
    key = (head, claims, role, threshold)
    pairs = _CACHE.get(key)
    if pairs is None:
        pairs = _all_pairs(conn, threshold)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = pairs
    return [dict(p) for p in pairs[:limit]]
