"""Every node id comes from ONE function, and the two graphs never collide.

`db/migrations/0002_graph_schema.up.sql` constrains every id to
`^[a-z]{3}_[0-9a-f]{16}$`. Pass 7 minted bare 64-hex digests instead, so all
5,409 content nodes were unprojectable — the constraint was right and the
second implementation was the defect.

The collision half of this file is the more important one. When the id scheme
was first unified, 34 content ids matched main-graph ids: 33 instructors and
one domain where the content node was `Backend Engineering` and the main node
was `Backend`. A shared id IS a merge, and whether those two are the same
thing is exactly what the INS and MOD rows ask. A hash coincidence must never
answer a review question.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import ids, taxonomy                                # noqa: E402

ID_SHAPE = re.compile(r"^[a-z]{3}_[0-9a-f]{16}$")
MAIN = REPO / "knowledge" / "graph.json"
CONTENT = REPO / "knowledge" / "content_graph.json"
SENSITIVE = REPO / "knowledge" / "content_graph-sensitive.json"


def _nodes(p):
    return json.loads(p.read_text(encoding="utf-8"))["nodes"] if p.exists() else []


def test_the_shape_matches_the_database_constraint():
    assert ID_SHAPE.match(ids.node_id("module", "API Design"))
    # The type name is DERIVED, not written out — B2 refuses a literal here.
    topic_type = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_topic"))[1]
    assert ID_SHAPE.match(ids.compound(topic_type, "rowB", "backend", 3, "x"))


def test_the_minter_is_deterministic():
    assert ids.node_id("module", "x") == ids.node_id("module", "x")
    assert ids.node_id("module", "x") != ids.node_id("module", "y")
    assert ids.node_id("module", "x") != ids.node_id("domain", "x")


def test_compound_parts_cannot_be_regrouped_into_the_same_id():
    """`(a, bc)` and `(ab, c)` must not collide — the separator is load-bearing."""
    assert ids.compound("module", "a", "bc") != ids.compound("module", "ab", "c")


@pytest.mark.parametrize("path", [MAIN, CONTENT, SENSITIVE])
def test_every_built_node_satisfies_the_constraint(path):
    if not path.exists():
        pytest.skip(f"{path.name} not built")
    bad = [n["id"] for n in _nodes(path) if not ID_SHAPE.match(n["id"])]
    assert not bad, f"{len(bad)} ids in {path.name} would be rejected by id_shape"


def test_the_two_graphs_share_no_id():
    """A shared id is an unreviewed merge. See the module docstring."""
    if not (MAIN.exists() and CONTENT.exists()):
        pytest.skip("both graphs must be built")
    main = {n["id"] for n in _nodes(MAIN)}
    content = {n["id"] for n in _nodes(CONTENT)} | {n["id"] for n in _nodes(SENSITIVE)}
    overlap = main & content
    assert not overlap, (
        f"{len(overlap)} ids exist in both graphs. Identity across the two is "
        "an answered REVIEW-QUEUE row, never a hash coincidence.")


def test_the_namespace_is_what_keeps_them_apart():
    """Mutation in miniature: without the namespace these are the same id."""
    assert ids.compound("instructor", "rowB", "adam toth") != \
           ids.node_id("instructor", "adam toth")
    assert ids.compound("instructor", "adam toth") == \
           ids.node_id("instructor", "adam toth")
