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
from pipeline.validate import categories_fired, failures                         # noqa: E402

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


def _hand_person(g):
    """A person whose title rests on out-of-corpus evidence (AUDIT §A.5)."""
    hand = taxonomy.origin_hand()
    return next(n for n in g["nodes"]
                if n["type"] == "person"
                and any(s.get("origin") == hand for s in n.get("sources", [])))


def _strip_hand_sources(g):
    """Exactly the pre-fix behaviour: copy the title, drop the provenance.

    This is what 03_resolve.py did for the entire life of the project, and what
    nothing could detect. If this mutation stops firing hand-provenance, the
    rule has gone vacuous again.
    """
    hand = taxonomy.origin_hand()
    n = _hand_person(g)
    n["sources"] = [s for s in n["sources"] if s.get("origin") != hand]


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
    # index rather than unpack: _run's arity changed once already, and a
    # positional unpack turns that into a confusing ValueError in an unrelated test
    categories = __import__("pipeline.validate", fromlist=["_run"])._run(GRAPH)[5]
    missing = sorted(set(categories) - fired)
    assert not missing, f"never exercised, even under injection: {missing}"


# --------------------------------------------------------------------------
# AUDIT §A.5 — hand provenance. Asserted at FAIL level, deliberately.
#
# This category emits an unconditional INFO line, so it is ALWAYS present in
# categories_fired(). Adding it to the parametrised list above produced three
# tests that passed against the clean graph — coverage-shaped and worth nothing.
# Caught by checking rather than trusting the green tick.
# --------------------------------------------------------------------------

def test_clean_graph_has_no_hand_provenance_failures():
    """The baseline. Without this the injections below prove nothing."""
    assert failures(GRAPH, "hand-provenance") == []


def test_dropping_hand_sources_is_caught(tmp_path):
    """Exactly the pre-fix behaviour: copy the title, drop the provenance.

    03_resolve.py did this for the life of the project and nothing could see it.
    """
    out = _mutate(tmp_path, _strip_hand_sources)
    found = failures(out, "hand-provenance")
    assert found, "stripping hand provenance from a person went undetected"
    assert any("must never be presentable" in m for _, m in found)


def test_hand_source_without_evidence_is_caught(tmp_path):
    def mutate(g):
        for s in _hand_person(g)["sources"]:
            if s.get("origin") == taxonomy.origin_hand():
                s.pop("evidence", None)
    assert failures(_mutate(tmp_path, mutate), "hand-provenance"), \
        "a hand source with no evidence is unfalsifiable and must fail"


def test_hand_source_naming_a_file_is_caught(tmp_path):
    """A hand source that names a file would emit a sourced_from edge.

    That is precisely the disguise the rule exists to prevent: out-of-corpus
    evidence presented with a citation to a corpus file.
    """
    def mutate(g):
        for s in _hand_person(g)["sources"]:
            if s.get("origin") == taxonomy.origin_hand():
                s["file"] = "00-master/made-up.xlsx"
    found = failures(_mutate(tmp_path, mutate), "hand-provenance")
    prov = taxonomy.edge_for_role("provenance")
    assert found and any(prov in m for _, m in found)


def test_the_rule_is_not_vacuous_on_the_real_graph():
    """Something must actually carry hand provenance, or the check is theatre."""
    import json
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    hand = taxonomy.origin_hand()
    carriers = [n for n in g["nodes"]
                if any(s.get("origin") == hand for s in n.get("sources", []))]
    assert carriers, (
        "no node carries hand provenance, so hand-provenance can never fail. "
        "This is the state the graph was in before AUDIT §A.5 was fixed."
    )
