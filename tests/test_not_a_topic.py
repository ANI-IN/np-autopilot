"""D1 — a person's name is not a topic.

Pass 7 takes slide titles as topics, and an instructor's intro slide is titled
with their name. module_merge.mark_person_name_topics marks such a topic
`not_a_topic: person_name` inside merge(), which every reader and the
projection call. Marked, not deleted: provenance stays. Held back from ranking
and panels, and every consumer says how many it held back.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, module_merge as mm, taxonomy        # noqa: E402

T_TOPIC = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_topic"))[1]
T_INS = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_instructor"))[1]
T_PERSON = taxonomy.edge_endpoints(taxonomy.edge_for_role("domain_primary"))[1]


def _g(*nodes):
    return {"nodes": [dict(n) for n in nodes], "edges": []}


def test_a_topic_that_is_a_known_name_is_marked_and_kept():
    g = _g({"id": "i1", "type": T_INS, "label": "Synthetic Instructor"},
           {"id": "t1", "type": T_TOPIC, "label": "  synthetic   INSTRUCTOR "},
           {"id": "t2", "type": T_TOPIC, "label": "REST Constraints"})
    assert mm.mark_person_name_topics(g) == ["t1"]
    by = {n["id"]: n for n in g["nodes"]}
    assert by["t1"][mm.NOT_A_TOPIC] == mm.PERSON_NAME
    assert mm.NOT_A_TOPIC not in by["t2"]
    assert len(g["nodes"]) == 3, "marked, never deleted"


def test_person_nodes_count_as_names_too():
    g = _g({"id": "p1", "type": T_PERSON, "label": "Synthetic Staff"},
           {"id": "t1", "type": T_TOPIC, "label": "Synthetic Staff"})
    assert mm.mark_person_name_topics(g) == ["t1"]


def test_a_withheld_name_never_changes_the_public_graph():
    g = _g({"id": "i1", "type": T_INS, "label": "Synthetic Withheld", "sensitive": True},
           {"id": "t1", "type": T_TOPIC, "label": "Synthetic Withheld"})
    assert mm.mark_person_name_topics(g) == []


def test_no_fuzzy_matching():
    g = _g({"id": "i1", "type": T_INS, "label": "Synthetic Instructor"},
           {"id": "t1", "type": T_TOPIC, "label": "Synthetic Instructors"},
           {"id": "t2", "type": T_TOPIC, "label": "Synthetic"})
    assert mm.mark_person_name_topics(g) == []


# The REVIEWED set (owner review, Animesh Kumar, 2026-09-30). A change to it
# is a change to what the checklist shows and must be looked at, not absorbed.
REVIEWED_PERSON_NAME = {
    # a bare name
    "Robert Kreznarich", "Zeki Sherif", "Krishnamoorthy Venkatraman", "Nikhil Kolekar",
    # a title that CONTAINS a known multi-word name
    "Introduction – Konstantinos Pappas", "Introduction – Mike Dolt",
    "Your Instructor: Bill Ogden", "I’ll Go First - Hi, I’m JD Kilby!",
    # a known first name as an @mention or a trailing ": NAME" presenter tag;
    # every one of these subjects is also a plain title in the same module
    "Availability, Reliability, Scalability & Replication: @SURUCHI",
    "Load Balancer: SURUCHI", "Proxies: HETAL",
    "Messages - Pub-sub, Polling, Streaming: HETAL",
    "Compute: BALAJI", "Storage: BALAJI", "Caching: BALAJI", "Databases: BALAJI"}
REVIEWED_PERSON_BIO = {"Worked at Amazon, Apple, among others, as a software engineer"}


def test_the_projected_graph_marks_exactly_the_reviewed_titles():
    g = graphio.load_merged(include_sensitive=False)
    marked = [n for n in g["nodes"] if n.get(mm.NOT_A_TOPIC)]
    by = {}
    for n in marked:
        by.setdefault(n[mm.NOT_A_TOPIC], set()).add(n["label"])
    assert by.get(mm.PERSON_NAME) == REVIEWED_PERSON_NAME
    assert by.get(mm.PERSON_BIO) == REVIEWED_PERSON_BIO
    assert g["meta"]["not_a_topic"] == len(marked)
    assert all(n.get("sources") for n in marked), "provenance must be kept"


def test_a_contained_multi_word_name_is_marked_but_a_first_name_alone_is_not():
    g = _g({"id": "i1", "type": T_INS, "label": "Synthetic Instructor"},
           {"id": "t1", "type": T_TOPIC, "label": "Introduction – Synthetic Instructor"},
           {"id": "t2", "type": T_TOPIC, "label": "Caching: SYNTHETIC"},
           {"id": "t3", "type": T_TOPIC, "label": "Ask @synthetic"},
           {"id": "t4", "type": T_TOPIC, "label": "Synthetic data generation"},
           {"id": "t5", "type": T_TOPIC, "label": "Synthetic: monitoring"})
    assert mm.mark_person_name_topics(g) == ["t1", "t2", "t3"]


def test_the_checklist_never_lists_a_name_as_a_topic():
    g = graphio.load_merged(include_sensitive=False)
    names = {n["label"] for n in g["nodes"] if n.get(mm.NOT_A_TOPIC)}
    text = (REPO / "docs" / "ACCEPTANCE-CHECKLIST.md").read_text(encoding="utf-8")
    listed = [l for b in text.split("**Top")[1:] for l in b.split("\n\n", 2)[1].split("\n")]
    assert not [l for l in listed for n in names if l.split(". ", 1)[-1].startswith(n + " —")]
    assert "held back as a person's name" in text
