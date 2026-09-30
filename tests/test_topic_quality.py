"""Topic quality — config/topic-quality.yaml is a SMALL, REVIEWED list.

Owner request (Animesh Kumar, 2026-09-30): housekeeping slides are ranked
LAST as boilerplate and never removed (CLAUDE.md §4); instructor bios are not
topics; a module's top-N shows a repeated title once. Every pattern carries
examples it must and must not match, and this file holds them to it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, module_merge as mm, taxonomy        # noqa: E402

RULES = mm.load_topic_quality()
RAW = yaml.safe_load(mm.TOPIC_QUALITY.read_text(encoding="utf-8"))
T_TOPIC = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_topic"))[1]
R_TOPIC = taxonomy.edge_for_role("module_topic")
CASES = [(kind, rid, rx, ex, want)
         for kind, rules in RULES.items() for rid, rx, r in rules
         for want, key in ((True, "match"), (False, "no_match"))
         for ex in r[key]]


@pytest.mark.parametrize("kind, rid, rx, example, want", CASES,
                         ids=[f"{c[0]}:{c[1]}:{'+' if c[4] else '-'}{c[3][:30]}" for c in CASES])
def test_every_example_agrees_with_its_pattern(kind, rid, rx, example, want):
    assert bool(rx.search(mm._fold(example))) is want


def test_every_pattern_has_both_kinds_of_example():
    for kind in ("person_bio", "boilerplate"):
        for r in RAW[kind]:
            assert r.get("match") and r.get("no_match"), r["id"]


def test_the_list_stays_small():
    """'small, reviewed' — growth past this is a design question, not an edit."""
    assert sum(len(RAW[k]) for k in ("person_bio", "boilerplate")) <= 15


def _mod(*titles, boiler=()):
    nodes = {"m": {"id": "m", "type": "module", "label": "M"}}
    edges = []
    for i, (t, extra) in enumerate(titles):
        nodes[f"t{i}"] = {"id": f"t{i}", "type": T_TOPIC, "label": t,
                          **({mm.BOILERPLATE: True} if t in boiler else {})}
        edges.append({"rel": R_TOPIC, "source": "m", "target": f"t{i}", **extra})
    return edges, nodes


def test_boilerplate_is_ranked_last_and_never_removed():
    edges, nodes = _mod(("Agenda", {"slide": 1, "rank": 1}),
                        ("Joins", {"slide": 2, "rank": 1}),
                        ("Indexes", {"slide": 3, "rank": 1}), boiler={"Agenda"})
    rows, _ = mm.rank_topics(edges, nodes)
    assert [nodes[e["target"]]["label"] for e in rows] == ["Joins", "Indexes", "Agenda"]


def test_historical_still_comes_after_housekeeping():
    edges, nodes = _mod(("Agenda", {"slide": 1}), ("Old joins", {"slide": 2, "historical": True}),
                        boiler={"Agenda"})
    rows, _ = mm.rank_topics(edges, nodes)
    assert [nodes[e["target"]]["label"] for e in rows] == ["Agenda", "Old joins"]


def test_identical_titles_show_once_and_are_counted():
    edges, nodes = _mod(("Caching", {"slide": 1}), ("  caching ", {"slide": 5}),
                        ("Sharding", {"slide": 2}))
    rows, folded = mm.rank_topics(edges, nodes)
    assert [nodes[e["target"]]["label"] for e in rows] == ["Caching", "Sharding"]
    assert folded == 1
    assert len(edges) == 3, "the graph keeps every one"


def test_not_a_topic_is_held_back_from_the_display():
    edges, nodes = _mod(("Robert Kreznarich", {"slide": 1}), ("Threads", {"slide": 2}))
    nodes["t0"][mm.NOT_A_TOPIC] = mm.PERSON_NAME
    rows, _ = mm.rank_topics(edges, nodes)
    assert [nodes[e["target"]]["label"] for e in rows] == ["Threads"]


def test_the_graph_marks_boilerplate_and_keeps_it():
    g = graphio.load_merged(include_sensitive=False)
    marked = [n for n in g["nodes"] if n.get(mm.BOILERPLATE)]
    assert marked and g["meta"]["topic_marks"][mm.BOILERPLATE] == len(marked)
    assert all(n["type"] == T_TOPIC and n.get("sources") for n in marked)
    # interview-prep content that an early pattern wrongly caught
    assert "Expectations from UI System Design interview" not in {n["label"] for n in marked}


def test_the_client_mirrors_the_ranking():
    """public/index.html::topicLinks must order like rank_topics."""
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    body = html.split("function topicLinks(", 1)[1].split("\nfunction ", 1)[0]
    for needle in ("not_a_topic", "boilerplate", "historical", "seen.has("):
        assert needle in body, needle
    # historical is the first key, boilerplate the second
    assert body.index("p.historical?1:0") < body.index("boilerplate)?1:0")
