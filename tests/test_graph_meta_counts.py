"""AUDIT §6.1 — meta.node_counts must count every node in the graph.

04_build_graph.py builds `by_type` from resolved.json, then appends the 74 file
nodes, then wrote node_counts from the stale `by_type`. meta.nodes said 5,048
(correct) while node_counts summed to 4,974, and gen_index.py — whose entire
stated purpose is "NEVER hand-write counts here" — published `file | 0 | 74`.

The reference implementation shipped 1,072 files / 61 clients / 773 instructors
against a real 1,833 / 32 / 351, roughly 70% wrong and published. A generated
count that disagrees with the artefact it was generated from is that failure
with the automation still attached, which is worse: it looks trustworthy.

These assertions are structural — they hold for any graph, not just today's —
so they keep holding after the Drive migration changes the numbers.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import taxonomy                                     # noqa: E402

GRAPH = REPO / "knowledge" / "graph.json"
INDEX = REPO / "knowledge" / "INDEX.md"


@pytest.fixture(scope="module")
def graph():
    return json.loads(GRAPH.read_text(encoding="utf-8"))


def test_node_counts_cover_every_type_present(graph):
    present = {n["type"] for n in graph["nodes"]}
    counted = set(graph["meta"]["node_counts"])
    assert present <= counted, (
        f"types present in nodes but missing from meta.node_counts: "
        f"{sorted(present - counted)}"
    )


def test_node_counts_sum_to_meta_nodes(graph):
    total = sum(graph["meta"]["node_counts"].values())
    assert total == graph["meta"]["nodes"] == len(graph["nodes"]), (
        f"meta.node_counts sums to {total}, meta.nodes is "
        f"{graph['meta']['nodes']}, len(nodes) is {len(graph['nodes'])}"
    )


def test_every_node_count_matches_a_recount(graph):
    actual = Counter(n["type"] for n in graph["nodes"])
    for t, claimed in graph["meta"]["node_counts"].items():
        assert claimed == actual[t], f"{t}: meta says {claimed}, recount says {actual[t]}"


def test_edge_counts_sum_to_meta_edges(graph):
    total = sum(graph["meta"]["edge_counts"].values())
    assert total == graph["meta"]["edges"] == len(graph["edges"])


def _node_section(text: str) -> str:
    """Just the Nodes table. INDEX.md has an Edges table with the same shape."""
    return text.split("## Nodes", 1)[1].split("## Edges", 1)[0]


def test_index_md_reports_no_zero_for_a_type_that_exists(graph):
    """The published symptom: `| `file` | 0 | 74 |` in an auto-generated table."""
    rows = dict(re.findall(r"^\|\s*`(\w+)`\s*\|\s*(\d+)\s*\|",
                           _node_section(INDEX.read_text(encoding="utf-8")), re.M))
    actual = Counter(n["type"] for n in graph["nodes"])
    wrong = {t: (int(n), actual[t]) for t, n in rows.items() if int(n) != actual[t]}
    assert not wrong, (
        "INDEX.md disagrees with graph.json — {type: (published, actual)}: "
        f"{wrong}. Regenerate with pipeline/gen_index.py."
    )


def test_index_md_never_publishes_zero_against_a_nonzero_expect(graph):
    """A count of 0 beside an expect of 74 is the shape that must never ship."""
    text = _node_section(INDEX.read_text(encoding="utf-8"))
    for t in taxonomy.node_type_names():
        exp = taxonomy.expected_count(t)
        if not exp:
            continue
        m = re.search(rf"^\|\s*`{re.escape(t)}`\s*\|\s*(\d+)\s*\|", text, re.M)
        assert m, f"{t} has no row in INDEX.md"
        assert int(m.group(1)) != 0, (
            f"INDEX.md publishes `{t}` as 0 while taxonomy expects {exp}"
        )
