"""C4 — the migration verifier must pass on the reference and fail on damage.

Written while the graph is still only files, and proven file-against-file, so
that when the Supabase projection exists the script is already known-good. A
verification script first exercised during a migration is debugged during the
migration — exactly when nobody can tell whether the script or the migration is
at fault.

The four injections are the migration mistakes that would actually happen:

  merge_dupes  collapsing the 1,687 duplicate (source,target,rel) triples,
               because a relational instinct says that is the primary key. It
               is not — 1,665 are sourced_from emitting one edge per cited row,
               and 22 are expert_in asserting the same pair with a different
               basis. Both are evidence /staffing exists to keep apart.
  strip_hand   a projection that keeps only corpus provenance, silently undoing
               AUDIT §A.5 the moment the data moves.
  drop_node    an off-by-one in a batched insert.
  cut_edge     a single lost relationship.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GRAPH = REPO / "knowledge" / "graph.json"
BASELINE = REPO / "config" / "migration-baseline.yaml"
VERIFIER = REPO / "pipeline" / "verify_migration.py"


@pytest.fixture(scope="module")
def verify():
    spec = importlib.util.spec_from_file_location("np_verify_migration", VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def baseline():
    import yaml
    return yaml.safe_load(BASELINE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def graph():
    """The UNION. The baseline pins the whole graph; RLS separates the halves
    in Postgres, not the filesystem."""
    from pipeline.lib import graphio
    return graphio.load_graph()


def _checked(baseline):
    return {k: baseline[k] for k in
            ("content_hash", "totals", "node_counts", "edge_counts",
             "duplicates", "provenance", "components") if k in baseline}


def test_the_baseline_exists_and_is_committed():
    assert BASELINE.exists(), "no frozen reference — run verify_migration.py --freeze"


def test_the_reference_graph_verifies(verify, baseline, graph):
    """It has passed at least once. That is the bar the docstring sets."""
    rows = verify.compare(_checked(baseline), verify.measure(graph))
    failed = [(p, d) for ok, p, d in rows if not ok]
    assert not failed, f"the frozen baseline no longer matches graph.json: {failed}"
    assert len(rows) >= 30, f"only {len(rows)} checks — the baseline lost coverage"


def test_expected_values_are_not_hardcoded_in_the_script():
    """Q7's aliases will move these. They must move in config, not in code."""
    src = VERIFIER.read_text(encoding="utf-8")
    for figure in ("5048", "36677", "32656", "1687", "26448"):
        assert figure not in src, (
            f"{figure} is hardcoded in verify_migration.py; it belongs in "
            "config/migration-baseline.yaml"
        )


def test_the_baseline_records_what_will_move_it(baseline):
    assert baseline.get("open_questions_that_will_move_these"), (
        "the baseline does not say what would legitimately change it, so a "
        "future mismatch has no context"
    )
    assert baseline.get("built_as_of"), "the baseline does not record its as-of date"


# --------------------------------------------------------------------------
# it must FAIL on damage
# --------------------------------------------------------------------------

def _mismatches(verify, baseline, mutate):
    from pipeline.lib import graphio
    g = graphio.load_graph()
    mutate(g)
    rows = verify.compare(_checked(baseline), verify.measure(g))
    return [p for ok, p, _ in rows if not ok]


def test_collapsing_duplicate_triples_is_caught(verify, baseline):
    """The most likely migration mistake, and the most damaging."""
    def mutate(g):
        seen, out = set(), []
        for e in g["edges"]:
            k = (e["source"], e["target"], e["rel"])
            if k in seen:
                continue
            seen.add(k)
            out.append(e)
        g["edges"] = out
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "collapsing 26,448 duplicate rows went undetected"
    assert any("duplicates" in p for p in failed)


def test_dropping_hand_provenance_is_caught(verify, baseline):
    """A projection that keeps only corpus sources silently undoes §A.5."""
    from pipeline.lib import taxonomy
    hand = taxonomy.origin_hand()

    def mutate(g):
        for n in g["nodes"]:
            n["sources"] = [s for s in n.get("sources", []) if s.get("origin") != hand]
    failed = _mismatches(verify, baseline, mutate)
    assert any("provenance" in p for p in failed), (
        "hand provenance can be dropped without the verifier noticing"
    )


def test_losing_one_node_is_caught(verify, baseline):
    def mutate(g):
        idx = next(i for i, n in enumerate(g["nodes"]) if n["type"] == "person")
        g["nodes"].pop(idx)
    assert _mismatches(verify, baseline, mutate)


def test_losing_one_edge_is_caught(verify, baseline):
    from pipeline.lib import taxonomy
    rel = taxonomy.edge_for_role("instructor_module")

    def mutate(g):
        idx = next(i for i, e in enumerate(g["edges"]) if e["rel"] == rel)
        g["edges"].pop(idx)
    failed = _mismatches(verify, baseline, mutate)
    assert failed and any("edge_counts" in p or "totals" in p for p in failed)


def test_component_structure_is_checked(verify, baseline):
    """Counts alone would miss a rewiring that preserves them."""
    from pipeline.lib import taxonomy
    rel = taxonomy.edge_for_role("workflow_theme")

    def mutate(g):
        # rewire one workflow->theme edge: counts identical, shape not
        e = next(e for e in g["edges"] if e["rel"] == rel)
        themes = [n["id"] for n in g["nodes"] if n["type"] == "theme"]
        e["target"] = next(t for t in themes if t != e["target"])
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "a rewiring that preserves every count went undetected"
    assert any("content_hash" in p or "components" in p for p in failed)
