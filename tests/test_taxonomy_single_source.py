"""B2: taxonomy strings live in exactly one place.

Fails if any node-type name, edge-type name or vocabulary value is written as a
string literal outside config/taxonomy.yaml and pipeline/lib/taxonomy.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import taxonomy                                   # noqa: E402
from pipeline.lib.paths import REPO_ROOT, TAXONOMY_FILE             # noqa: E402

ALLOWED = {TAXONOMY_FILE, REPO_ROOT / "pipeline" / "lib" / "taxonomy.py"}
SEARCH_GLOBS = ("pipeline/**/*.py", "tests/**/*.py", "commands/**/*.md", "skills/**/*.md")

# Generic words that are ordinary English and would produce noise.
IGNORE = {"file", "program", "covers", "contains", "teaches", "person", "module",
          "theme", "domain", "workflow", "instructor", "np", "other", "delivery"}


def _guarded_strings() -> set[str]:
    out: set[str] = set()
    out |= set(taxonomy.node_type_names())
    out |= set(taxonomy.edge_type_names())
    for v in ("tool", "doctype", "family", "cadence", "stage", "team", "seniority"):
        out |= set(taxonomy.vocabulary(v))
    return {s for s in out if s.lower() not in IGNORE and len(s) > 2}


def _files_to_scan() -> list[Path]:
    seen: list[Path] = []
    for pattern in SEARCH_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            if p.is_file() and p.resolve() not in ALLOWED:
                seen.append(p)
    return seen


def test_no_taxonomy_literals_outside_the_single_source() -> None:
    guarded = _guarded_strings()
    offences: list[str] = []

    for path in _files_to_scan():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]           # comments are documentation
            if not code.strip():
                continue
            for term in guarded:
                if re.search(rf'["\']{re.escape(term)}["\']', code):
                    offences.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno} literal "
                        f"{term!r} — import it from pipeline.lib.taxonomy"
                    )

    assert not offences, (
        "taxonomy strings must come from pipeline.lib.taxonomy:\n  "
        + "\n  ".join(sorted(offences))
    )


def test_taxonomy_loads_and_is_self_consistent() -> None:
    assert taxonomy.version() == 2

    names = taxonomy.node_type_names()
    assert len(names) == len(set(names)), "duplicate node type"

    edges = taxonomy.edge_type_names()
    assert len(edges) == len(set(edges)), "duplicate edge type"

    # Every non-wildcard endpoint must name a real node type.
    for edge in edges:
        src, dst = taxonomy.edge_endpoints(edge)
        if not taxonomy.has_wildcard_source(edge):
            assert src in names, f"{edge}: from {src!r} is not a node type"
        assert dst in names, f"{edge}: to {dst!r} is not a node type"

    # Exactly one edge may use the wildcard, and it must be the provenance edge.
    wild = taxonomy.wildcard_edge_names()
    assert len(wild) == 1, f"expected exactly one wildcard edge, got {wild}"
    # Its target must still be a declared node type — the wildcard relaxes the
    # source only. (Not positional: node order in the file is not a contract.)
    assert taxonomy.edge_endpoints(wild[0])[1] in names


def test_expect_is_null_where_coverage_is_incomplete() -> None:
    """person/instructor/module are floors over 50 of 75 files, not counts."""
    for name in ("person", "instructor", "module"):
        assert taxonomy.expected_count(name) is None, (
            f"{name}.expect must stay null until B4 reads all 75 files"
        )


def test_excluded_field_matching_is_case_insensitive() -> None:
    assert taxonomy.is_excluded_field("Personal Email")
    assert taxonomy.is_excluded_field("  linkedin profile url  ")
    assert not taxonomy.is_excluded_field("Session_Title")
    assert not taxonomy.is_excluded_field("Coach")
