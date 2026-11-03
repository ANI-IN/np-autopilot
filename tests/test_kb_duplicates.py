"""Run 6 (B5): near-duplicate detection (web/lib/kb/duplicates.py) returns
EXACTLY what the all-pairs SQL it replaces returned, without comparing every
pair, and its cache follows the change feed. Local DB only."""
from __future__ import annotations

import itertools
import random
import string

import pytest

from kb_support import USERS, as_user, ensure_users, owner, requires_kb, reset

from lib.kb import duplicates

ALL_PAIRS_SQL = """
    select a.id as a_id, a.name as a_name, b.id as b_id, b.name as b_name, t.key as type,
           round(extensions.similarity(a.name_norm, b.name_norm)::numeric, 3) as similarity
    from kb.nodes a join kb.nodes b on a.type_id = b.type_id and a.id < b.id
    join kb.node_types t on t.id = a.type_id
    where a.archived_at is null and b.archived_at is null
      and extensions.similarity(a.name_norm, b.name_norm) >= %s"""


def _jaccard(a: set, b: set) -> float:
    return duplicates._f32(len(a & b) / len(a | b))


@pytest.mark.parametrize("threshold", [0.3, 0.5, 0.6, 0.75, 0.9])
def test_similar_pairs_is_exact_against_brute_force(threshold):
    rng = random.Random(int(threshold * 100))
    vocab = ["".join(rng.choice(string.ascii_lowercase[:6]) for _ in range(3)) for _ in range(40)]
    recs = []
    for _ in range(400):
        grams = set(rng.sample(vocab, rng.randint(1, 12)))
        recs.append((rng.choice("ab"), sorted(grams)))
    recs.append(("a", []))                              # an empty name: never a duplicate
    got = {(min(i, j), max(i, j)): s for i, j, s in duplicates.similar_pairs(recs, threshold)}
    want = {(i, j): _jaccard(set(recs[i][1]), set(recs[j][1]))
            for i, j in itertools.combinations(range(len(recs)), 2)
            if recs[i][0] == recs[j][0] and recs[i][1] and recs[j][1]
            and _jaccard(set(recs[i][1]), set(recs[j][1])) >= threshold}
    assert got == want


@requires_kb
class TestAgainstTheDatabase:
    @pytest.fixture(autouse=True)
    def _setup(self):
        ensure_users()
        reset()
        duplicates._CACHE.clear()
        rng = random.Random(7)
        words = ["intro", "advanced", "systems", "design", "graphs", "data", "python", "sql", "week",
                 "part", "review", "mock", "interview", "ml", "llm"]
        with owner() as c:
            c.execute("select set_config('kb.actor_type', 'system', false)")
            for tkey in ("module", "program"):
                names = set()
                while len(names) < 150:
                    names.add(" ".join(rng.sample(words, rng.randint(1, 4))) + rng.choice(["", " 1", " 2", "s"]))
                for n in names:
                    c.execute("insert into kb.nodes (type_id, name) values "
                              "((select id from kb.node_types where key = %s), %s)", (tkey, n))
            c.execute("update kb.nodes set archived_at = now(), status = 'archived' where id in "
                      "(select id from kb.nodes order by id limit 10)")
        yield
        reset()

    @pytest.mark.parametrize("threshold", [0.3, 0.6, 0.8])
    def test_same_pairs_and_scores_as_the_all_pairs_sql(self, threshold):
        with as_user(USERS["viewer"]) as conn:
            pass
        with as_user(USERS["editor"]) as conn:
            with conn.cursor() as cur:
                cur.execute(ALL_PAIRS_SQL, (threshold,))
                cols = [d.name for d in cur.description]
                want = {(r[0], r[2]): dict(zip(cols, r)) for r in cur.fetchall()}
            got = duplicates.find(conn, threshold, 200)
            full = duplicates._all_pairs(conn, threshold)
        assert want, "the fixture must produce duplicates"
        assert {(p["a_id"], p["b_id"]): p for p in full} == want
        assert got == full[:200]
        sims = [p["similarity"] for p in got]
        assert sims == sorted(sims, reverse=True)

    def test_cache_follows_the_change_feed(self):
        with as_user(USERS["editor"]) as conn:
            first = duplicates.find(conn, 0.6, 5)
        assert first
        victim = first[0]["a_id"]
        with owner() as c:
            c.execute("update kb.nodes set archived_at = now(), status = 'archived' where id = %s", (victim,))
        with as_user(USERS["editor"]) as conn:
            again = duplicates.find(conn, 0.6, 200)
        assert victim not in {p["a_id"] for p in again} | {p["b_id"] for p in again}

    def test_a_non_member_sees_nothing(self):
        from kb_support import OUTSIDER
        with as_user(OUTSIDER) as conn:
            assert duplicates.find(conn, 0.6, 50) == []
