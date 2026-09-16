"""Pass 0's bookkeeping must never be discovered as corpus material.

Found the moment a `.drive-cache/` existed for the first time. Pass 0 wrote
`_manifest.json` at the cache root; pass 1 walks that root, and its skip rules
cover dot-prefixed segments and named project directories — neither of which
matched. It was discovered as a 76th corpus file.

The count check would NOT have caught it: 76 found minus the 1 excluded payroll
file is 75 file nodes, and `file` carries expect 74 with tolerance 2, so 75
passes silently. A bogus file node, a bogus `sourced_from` target, and a clean
validation report.

This is the third instance of the same class — `commands/` and `eval/` were
swept in, then NEXT.md became a file node — and the first that the file-count
check would have missed. Fixed by dot-prefixing the manifest so pass 1's
existing "the corpus has no dotfiles" rule covers it, rather than adding a
fourth special case to SKIP_DIRS.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FETCH = REPO / "pipeline" / "00_fetch_drive.py"
WALK = REPO / "pipeline" / "01_walk_corpus.py"


@pytest.fixture(scope="module")
def walker():
    spec = importlib.util.spec_from_file_location("np_walk_corpus", WALK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pass0_writes_a_dot_prefixed_manifest():
    src = FETCH.read_text(encoding="utf-8")
    assert '"_manifest.json"' not in src, (
        "pass 0 writes an undotted manifest, which pass 1 will ingest as corpus"
    )
    assert '".manifest.json"' in src


def test_walker_skips_pass0_bookkeeping(walker, tmp_path):
    """Build a cache-shaped tree and confirm only corpus files are discovered."""
    cache = tmp_path / ".drive-cache"
    (cache / "00-master").mkdir(parents=True)
    (cache / "00-master" / "Real File.xlsx").write_bytes(b"PK\x03\x04stub")
    (cache / ".manifest.json").write_text('{"files": []}', encoding="utf-8")

    found = {str(p.relative_to(cache)) for p in walker.discover(cache)}
    assert found == {"00-master/Real File.xlsx"}, (
        f"walker discovered pass-0 bookkeeping as corpus: {sorted(found)}"
    )


def test_an_undotted_manifest_would_have_been_ingested(walker, tmp_path):
    """Proves the rule is load-bearing rather than incidentally satisfied."""
    cache = tmp_path / ".drive-cache"
    (cache / "00-master").mkdir(parents=True)
    (cache / "00-master" / "Real File.xlsx").write_bytes(b"PK\x03\x04stub")
    (cache / "_manifest.json").write_text('{"files": []}', encoding="utf-8")

    found = {str(p.relative_to(cache)) for p in walker.discover(cache)}
    assert "_manifest.json" in found, (
        "the undotted name is no longer ingested — if pass 1 grew its own skip "
        "rule for it, this test and the dot-prefix are now redundant; keep one"
    )


def test_the_live_cache_has_no_undotted_manifest():
    """Skipped when no cache exists, so this runs on a fresh clone too."""
    cache = REPO / ".drive-cache"
    if not cache.is_dir():
        pytest.skip("no .drive-cache on this machine")
    assert not (cache / "_manifest.json").exists(), (
        "a stale undotted manifest is still in the cache and will be ingested"
    )
    if (cache / ".manifest.json").exists():
        manifest = json.loads((cache / ".manifest.json").read_text(encoding="utf-8"))
        assert "files" in manifest


def test_the_count_check_alone_would_not_have_caught_this():
    """Documents WHY this needed its own test rather than trusting validate.py.

    file expect 74, tolerance 2 -> 72..76 passes. One stray file gives 75.
    """
    from pipeline.lib import taxonomy
    expect = taxonomy.expected_count("file")
    tol = taxonomy.tolerance("file") or 0
    assert expect + tol >= expect + 1, (
        "tolerance is 0, so the count check WOULD catch a single stray file "
        "and this test's premise no longer holds"
    )
