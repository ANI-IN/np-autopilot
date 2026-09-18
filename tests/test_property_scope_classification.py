"""Every projected property must declare a scope. Absence is a build failure.

WHY THIS GUARD EXISTS. Three widening requests in a row moved the same boundary
and none of them looked wrong individually. The mechanism was the DEFAULT: a new
field landed in the public half — `knowledge/graph.json`, a tracked file —
unless somebody actively remembered otherwise. Widening therefore defaulted
toward exposure and required an act of memory not to. DECISIONS §A.7b's
permissive-reading failure, applied to policy rather than code.

So these assert the default is now nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import taxonomy                                      # noqa: E402

RESERVED = {"id", "type", "label", "label_raw", "sensitive", "sources",
            "source", "target", "rel"}


def _keys_in(path: Path) -> set[str]:
    g = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in g.get("nodes", []):
        out |= set(n) - RESERVED
    for e in g.get("edges", []):
        out |= set(e) - RESERVED
    return out


def test_every_property_in_the_built_graph_is_classified():
    """The positive control, and the one a new extractor field trips."""
    scopes = taxonomy.property_scopes()
    assert scopes, "property_scopes is empty — has the config key moved?"

    unclassified = sorted(_keys_in(REPO / "knowledge" / "graph.json") - set(scopes))
    assert not unclassified, (
        f"properties in graph.json with no scope: {unclassified}. Classify each "
        "in config/taxonomy.yaml -> property_scopes before it can project.")


def test_the_sensitive_half_is_classified_too():
    """It is gitignored, so it is the half most likely to drift unnoticed."""
    sensitive = REPO / "knowledge" / "graph-sensitive.json"
    if not sensitive.exists():
        pytest.skip("graph-sensitive.json not present")
    unclassified = sorted(_keys_in(sensitive) - set(taxonomy.property_scopes()))
    assert not unclassified, (
        f"properties in the SENSITIVE half with no scope: {unclassified}")


def test_an_unclassified_property_refuses_the_projection():
    """NEGATIVE CONTROL, per §A.7b rule 1.

    A test that classified properties pass proves nothing about the guard —
    everything is classified. This breaks the thing the guard watches and
    asserts it goes red, by calling the real refusal with a synthetic graph
    rather than by trusting the code reads correctly.
    """
    sys.path.insert(0, str(REPO / "pipeline"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "np_project_graph", REPO / "pipeline" / "project_graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Derived, not quoted: `cadence` values are taxonomy vocabulary, and the
    # single-source guard (rightly) refuses one written as a literal here.
    clean = {"nodes": [{"id": "n1", "type": "domain", "label": "x",
                        "sensitive": False,
                        "cadence": taxonomy.cadences()[0]}],
             "edges": []}
    mod._refuse_unclassified_properties(clean)      # classified: must not raise

    dirty = {"nodes": [{"id": "n1", "type": "domain", "label": "x",
                        "sensitive": False, "pay_rate": 120}],
             "edges": []}
    with pytest.raises(SystemExit) as exc:
        mod._refuse_unclassified_properties(dirty)
    assert "pay_rate" in str(exc.value)
    assert "unclassified" in str(exc.value).lower()


def test_a_sensitive_property_on_a_public_row_refuses():
    """The other half of the rule, and the one the payroll reversal needs.

    Classifying a field `sensitive` is worthless if it can still be attached to
    a row anybody can read.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "np_project_graph2", REPO / "pipeline" / "project_graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Pretend `title` is sensitive, then put it on a public row.
    real = taxonomy.property_scopes
    taxonomy.property_scopes = lambda: {**real(), "title": "sensitive"}
    try:
        graph = {"nodes": [{"id": "p1", "type": "person", "label": "x",
                            # Not a vocabulary value: the taxonomy guard
                            # (rightly) refuses one written as a literal here.
                            "sensitive": False, "title": "Head of Widgets"}],
                 "edges": []}
        with pytest.raises(SystemExit) as exc:
            mod._refuse_unclassified_properties(graph)
        assert "title" in str(exc.value)
    finally:
        taxonomy.property_scopes = real


def test_scope_full_refuses_and_says_why():
    """It must refuse, and the reason must be the true one.

    The previous refusal was hardcoded and claimed the recruiting RLS path "does
    not exist yet". It does. A guard that asserts a conclusion instead of
    checking one is wrong in whichever direction the world moves — it blocked
    correct work, and had the policy been DROPPED it would have waved the
    projection through.
    """
    r = subprocess.run([sys.executable, "pipeline/project_graph.py",
                        "--scope", "full", "--dry-run"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode != 0, "--scope full must refuse"
    out = r.stdout + r.stderr
    assert "does not exist yet" not in out, (
        "the refusal still claims the recruiting RLS path is missing; it is not")
    assert "INGEST-SCOPE-REVERSAL" in out, (
        "the refusal must point at the record that would authorise it")
