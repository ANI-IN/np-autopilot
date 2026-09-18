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

#: Directories that are not this project's source. Everything else is scanned.
#:
#: THE SCOPE IS DERIVED, NOT LISTED, AND THAT IS THE POINT. This was
#: ("pipeline/**/*.py", "tests/**/*.py", ...) — an allow-list of directories —
#: and `web/` and `api/` were simply not in it. The rule said "anywhere"; the
#: guard checked four directories and reported as though it had checked the
#: repository. It passed for months while five literals sat in `web/lib/`, and
#: it only surfaced because a sixth was written in a file that happened to be
#: inside the list. DECISIONS §A.7b instance 8.
#:
#: A deny-list inverts the failure: a new directory is covered by default, and
#: the way to lose coverage is to add a name here deliberately.
NOT_SOURCE = {".git", ".vercel", "node_modules", "__pycache__", ".pytest_cache",
              "venv", ".venv", "build", "dist", ".drive-cache", "knowledge"}

#: Markdown stays an allow-list, deliberately and for a different reason: prose
#: documentation SHOULD name edge and node types, and `docs/` is nothing but
#: prose. `commands/` and `skills/` are executable instructions, so a literal
#: there is a second source of truth in the same way code is.
MARKDOWN_GLOBS = ("commands/**/*.md", "skills/**/*.md")

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
    """Every .py in the repository, plus the executable markdown."""
    seen: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        rel = p.relative_to(REPO_ROOT)
        if any(part in NOT_SOURCE for part in rel.parts):
            continue
        if p.is_file() and p.resolve() not in ALLOWED:
            seen.append(p)
    for pattern in MARKDOWN_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            if p.is_file() and p.resolve() not in ALLOWED:
                seen.append(p)
    return seen


def test_the_scan_actually_reaches_the_shipped_web_code() -> None:
    """The negative control for the scope itself, per §A.7b rule 1.

    The previous version of this guard passed while never opening `web/` or
    `api/`. A test that the scan FINDS things is not enough — it found plenty.
    This asserts it reaches the specific directories whose absence was the bug.
    """
    scanned = {p.relative_to(REPO_ROOT).parts[0] for p in _files_to_scan()}
    for required in ("web", "api", "pipeline", "tests"):
        assert required in scanned, (
            f"the taxonomy scan no longer reaches {required}/. The rule is "
            "'nowhere outside taxonomy.py'; a guard that checks a subset and "
            "reports success is §A.7b instance 8."
        )


#: An explicit, reasoned exemption for a value that is NOT a taxonomy
#: reference. The eval harness needs it: an expected ANSWER that happens to
#: equal a vocabulary value must stay a literal, because resolving it through
#: taxonomy.vocabulary() would make the eval assert that the graph agrees with
#: the taxonomy rather than with a known-correct answer, and it would then pass
#: even if both changed together, which is the failure the harness exists to
#: catch. A reason is REQUIRED; a bare marker is itself an offence, so this
#: cannot become a silent opt-out.
MARKER = "taxonomy-literal-ok"


def _exemptions(lines):
    """Line numbers a marker covers, and markers written without a reason."""
    exempt = set()
    unreasoned = []
    for i, raw in enumerate(lines, 1):
        if MARKER not in raw:
            continue
        if not raw.split(MARKER, 1)[1].lstrip(":").strip():
            unreasoned.append(i)
            continue
        exempt.add(i)
        # ...and the next line that is actually code, so a marker may sit in a
        # comment block above a long expression instead of trailing it.
        for j in range(i, len(lines)):
            nxt = lines[j]
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            exempt.add(j + 1)
            break
    return exempt, unreasoned


def test_no_taxonomy_literals_outside_the_single_source() -> None:
    guarded = _guarded_strings()
    offences: list[str] = []

    for path in _files_to_scan():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        exempt, unreasoned = _exemptions(lines)
        rel = path.relative_to(REPO_ROOT)
        for lineno in unreasoned:
            offences.append(f"{rel}:{lineno} bare {MARKER!r} with no reason - "
                            "say why this is not a taxonomy reference")
        for lineno, line in enumerate(lines, 1):
            if lineno in exempt:
                continue
            code = line.split("#", 1)[0]           # comments are documentation
            if not code.strip():
                continue
            for term in guarded:
                if re.search(rf'["\']{re.escape(term)}["\']', code):
                    offences.append(
                        f"{rel}:{lineno} literal "
                        f"{term!r} - import it from pipeline.lib.taxonomy"
                    )

    assert not offences, (
        "taxonomy strings must come from pipeline.lib.taxonomy:\n  "
        + "\n  ".join(sorted(offences))
    )


def test_a_bare_exemption_marker_is_itself_an_offence() -> None:
    """Negative control for the escape hatch, per DECISIONS A.7b rule 1.

    An exemption mechanism with no cost is a hole. This asserts the marker is
    honoured only when it carries a reason.
    """
    # Derived, not quoted: the guard's own test must not need the guard's own
    # escape hatch to pass.
    term = taxonomy.edge_for_role("instructor_domain")
    with_reason = [f"x = '{term}'  # " + MARKER + ": it is an expected answer"]
    without = [f"x = '{term}'  # " + MARKER]
    assert _exemptions(with_reason) == ({1}, [])
    assert _exemptions(without) == (set(), [1])


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
