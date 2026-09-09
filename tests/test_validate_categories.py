"""B6: prove every validation category actually fires.

A clean report means nothing unless the checks have been shown to catch the
faults they exist for. Each test below corrupts a copy of the real graph in one
specific way and asserts the matching category fires.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.validate import categories_fired                         # noqa: E402

GRAPH = REPO / "knowledge" / "graph.json"


def _mutate(tmp_path: Path, fn) -> Path:
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    fn(g)
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "graph.json"
    out.write_text(json.dumps(g), encoding="utf-8")
    return out


def _first(g, node_type):
    return next(n for n in g["nodes"] if n["type"] == node_type)


def test_baseline_is_clean_for_injected_categories():
    fired = categories_fired(GRAPH)
    for cat in ("provenance", "sensitive-flag", "cadence-collision", "endpoint-type",
                "absolute-path", "excluded-file", "excluded-field", "duplicate-id"):
        assert cat not in fired, f"{cat} fires on the real graph; injection proves nothing"


@pytest.mark.parametrize("category,mutate", [
    ("provenance",        lambda g: _first(g, "person").__setitem__("sources", [])),
    ("sensitive-flag",    lambda g: _first(g, "person").pop("sensitive")),
    ("absolute-path",     lambda g: _first(g, "person")["sources"].append(
                              {"origin": "corpus", "file": "/Users/someone/secret.xlsx"})),
    ("excluded-file",     lambda g: _first(g, "person")["sources"].append(
                              {"origin": "corpus", "file": taxonomy.excluded_files()[0]})),
    ("excluded-field",    lambda g: _first(g, "person").__setitem__(
                              taxonomy.excluded_field_patterns()[0], "someone@example.com")),
    ("duplicate-id",      lambda g: g["nodes"].append(dict(_first(g, "person")))),
    ("cadence-collision", lambda g: _first(g, "person").__setitem__(
                              "label", taxonomy.cadences()[0])),
    ("endpoint-type",     lambda g: g["edges"].append({
                              "source": _first(g, "person")["id"],
                              "target": _first(g, "person")["id"],
                              "rel": taxonomy.edge_for_role("workflow_theme")})),
])
def test_category_fires_when_fault_injected(tmp_path, category, mutate):
    fired = categories_fired(_mutate(tmp_path, mutate))
    assert category in fired, (
        f"injected a {category} fault and the check did NOT fire — "
        "the check is broken, not the graph"
    )


def test_all_categories_are_exercised_across_the_suite(tmp_path):
    """Union of real-graph findings and every injection must cover all categories."""
    fired = set(categories_fired(GRAPH))
    injections = [
        lambda g: _first(g, "person").__setitem__("sources", []),
        lambda g: _first(g, "person").pop("sensitive"),
        lambda g: _first(g, "person")["sources"].append(
            {"origin": "corpus", "file": "/abs/path.xlsx"}),
        lambda g: _first(g, "person")["sources"].append(
            {"origin": "corpus", "file": taxonomy.excluded_files()[0]}),
        lambda g: _first(g, "person").__setitem__(
            taxonomy.excluded_field_patterns()[0], "x@y.com"),
        lambda g: g["nodes"].append(dict(_first(g, "person"))),
        lambda g: _first(g, "person").__setitem__("label", taxonomy.cadences()[0]),
        lambda g: g["edges"].append({"source": _first(g, "person")["id"],
                                     "target": _first(g, "person")["id"],
                                     "rel": taxonomy.edge_for_role("workflow_theme")}),
    ]
    for i, fn in enumerate(injections):
        fired |= set(categories_fired(_mutate(tmp_path / str(i), fn)))
    _, _, _, _, _, categories = __import__("pipeline.validate", fromlist=["_run"])._run(GRAPH)
    missing = sorted(set(categories) - fired)
    assert not missing, f"never exercised, even under injection: {missing}"
