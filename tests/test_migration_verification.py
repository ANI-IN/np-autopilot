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
    """The UNION, and now the MERGED union.

    The baseline pins what `project_graph.py` actually writes; RLS separates
    the halves in Postgres, not the filesystem. This read `load_graph` until
    2026-09-29, so it pinned knowledge/graph.json while the projection had
    become both graphs merged on the answered REVIEW-QUEUE rows — the test
    compared the baseline against a graph nobody projects.
    """
    from pipeline.lib import graphio
    return graphio.load_merged(include_sensitive=True)


def _checked(baseline):
    return {k: baseline[k] for k in
            ("content_hash", "totals", "node_counts", "edge_counts",
             "duplicates", "provenance", "components") if k in baseline}


def test_the_baseline_exists_and_is_committed():
    assert BASELINE.exists(), "no frozen reference — run verify_migration.py --freeze"


#: The frozen baseline pins the FULL merged graph, withheld halves included —
#: what project_graph.py would write with --scope full. Both withheld halves are
#: gitignored (named external people), so a clone without them cannot measure
#: the graph the baseline describes. No synthetic stand-in can: the assertion
#: IS that the real graph still matches.
_WITHHELD = [REPO / "knowledge" / "graph-sensitive.json",
             REPO / "knowledge" / "content_graph-sensitive.json"]


@pytest.mark.skipif(not all(p.exists() for p in _WITHHELD),
                    reason="needs the gitignored withheld halves "
                           "(knowledge/*-sensitive.json): the frozen baseline "
                           "pins the full graph")
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
    g = graphio.load_merged(include_sensitive=True)
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


# ---------------------------------------------------------------------------
# B2.5 — the checker was changed to normalise three things before comparing.
# Each normalisation is a place a real discrepancy could now hide, so each one
# gets a mutation proving it does not.
#
# What was normalised, and why (pipeline/verify_migration.py has the detail):
#   provenance edges  pass 4 materialises `sourced_from`, pass 7 does not —
#                     DECISIONS §A.3 moved provenance out of edges. Both sides
#                     now DERIVE the shape from `sources`.
#   ordinal           pass 4 writes 0 explicitly, pass 7 omits it, the column
#                     is NOT NULL DEFAULT 0. Both sides fill the default.
#   content_hash      hashed over the normalised graph, not the raw one.
# ---------------------------------------------------------------------------

def test_a_lost_provenance_record_is_still_caught(verify, baseline):
    """Deriving provenance edges must not make a missing citation invisible."""
    def mutate(g):
        for n in g["nodes"]:
            if len(n.get("sources") or []) > 1:
                n["sources"] = n["sources"][:-1]
                return
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "dropping a provenance record went undetected"


def test_dropping_every_content_citation_is_still_caught(verify, baseline):
    """The exact shape of the bug this normalisation was introduced around:
    content provenance vanishing on projection."""
    def mutate(g):
        for n in g["nodes"]:
            srcs = n.get("sources") or []
            if srcs:
                n["sources"] = [s for s in srcs
                                if s.get("slide") is None and s.get("tab") is None]
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "removing every slide and tab citation went undetected"


def test_a_changed_locator_is_still_caught(verify, baseline):
    """A slide number is the whole value of a topic citation."""
    def mutate(g):
        for n in g["nodes"]:
            for s in (n.get("sources") or []):
                if s.get("slide") is not None:
                    s["slide"] = s["slide"] + 1000
                    return
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "changing a slide locator went undetected"


def test_a_changed_owner_domain_is_still_caught(verify, baseline):
    """D4: the file owner is recorded as a domain. Losing or altering it is
    the thing migration 0019 exists to keep possible."""
    def mutate(g):
        for n in g["nodes"]:
            for s in (n.get("sources") or []):
                if s.get("owner_domain"):
                    s["owner_domain"] = "mutated.example"
                    return
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "changing an owner_domain went undetected"


def test_a_nonzero_ordinal_is_still_caught(verify, baseline):
    """Filling the DEFAULT must not mean ignoring the field.

    EVERY ordinal in the graph is currently 0 — measured, 41,528 of 41,528 —
    so the first version of this test looked for a non-zero one to perturb,
    found none, mutated nothing and passed against an unmodified graph. It
    asserted that the checker catches a change that was never made.

    So the mutation INTRODUCES a non-zero ordinal. Filling a default must not
    become ignoring the field, and the only way to show that is to set one.
    """
    def mutate(g):
        for n in g["nodes"]:
            for s in (n.get("sources") or []):
                s["ordinal"] = 77
                return
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "introducing a non-zero ordinal went undetected"


def test_normalising_ordinal_does_not_hide_a_missing_entry(verify, baseline):
    """An entry whose ordinal was the only difference is still an entry."""
    def mutate(g):
        for n in g["nodes"]:
            srcs = n.get("sources") or []
            if len(srcs) > 2:
                n["sources"] = srcs[:1]
                return
    failed = _mismatches(verify, baseline, mutate)
    assert failed, "truncating a node's sources went undetected"
