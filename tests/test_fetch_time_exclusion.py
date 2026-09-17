"""R17 — an excluded file must never reach the disk, not merely never reach the graph.

The exclusion list was enforced by pass 1, two passes after pass 0 had already
downloaded the bytes. A service account that can read
`US Instructor Cost Analysis.xlsx` — 5,387 names, employment status including
"Exited (Terminated)", per-labour-code rates — fetched it on every run and relied
on a later pass to ignore it. 23 MB of HR payroll data sat in `.drive-cache/`.

Confirmed live before the fix: the validate assertion added here fired on the
real cache, and pass 0 then purged the file.

NOT TWO INDEPENDENT LAYERS, and the tests say so. Pass 0 and pass 1 both read
`taxonomy.yaml -> excluded.files`, so a wrong entry in that list defeats both
(DECISIONS §A.7a). They are two layers against a bug in ONE PASS, which is the
narrower and honest claim — the shape the refresh.py bug taught us to check for.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import taxonomy                                      # noqa: E402

FETCH = REPO / "pipeline" / "00_fetch_drive.py"
VALIDATE = REPO / "pipeline" / "validate.py"
CACHE = REPO / ".drive-cache"


def test_there_is_something_to_exclude():
    """A rule with an empty list cannot fail, and would make the rest vacuous."""
    assert taxonomy.excluded_files(), "excluded.files is empty"


def test_the_excluded_file_is_absent_from_the_cache():
    """The assertion that matters. Skipped where there is no cache."""
    if not CACHE.is_dir():
        pytest.skip("no .drive-cache on this machine")
    present = [p for p in taxonomy.excluded_files() if (CACHE / p).exists()]
    assert not present, (
        f"excluded file(s) present in the cache: {present}. Pass 0 fetched them "
        "despite the exclusion list — the bytes are on disk, which is what "
        "matters once this runs unattended on shared infrastructure."
    )


def test_pass0_filters_before_fetching_not_after():
    """Order is the whole fix: skipping after the download changes nothing."""
    src = FETCH.read_text(encoding="utf-8")
    body = src.split("def main(", 1)[1]
    excl_at = body.index("excluded = set(taxonomy.excluded_files())")
    fetch_at = body.index("ok, note = fetch(")
    assert excl_at < fetch_at, (
        "pass 0 consults the exclusion list after fetching, which is the bug"
    )


def test_pass0_purges_an_excluded_file_already_in_the_cache():
    """A fix that only helps a fresh machine is not a fix for this machine."""
    src = FETCH.read_text(encoding="utf-8")
    assert "PURGED from the existing cache" in src


def test_validate_asserts_against_the_cache_not_only_the_manifest():
    """The old check proved it never became a node. That was never the question."""
    src = VALIDATE.read_text(encoding="utf-8")
    assert "PRESENT IN THE CACHE" in src
    assert ".drive-cache" in src


def test_both_layers_read_the_same_list_and_that_is_documented():
    """Honest scoping, per DECISIONS §A.7a.

    If these ever become genuinely independent — say pass 0 keys on a sha256
    while pass 1 keys on a path — this test should be updated to say so. Until
    then it pins the weaker claim so nobody repeats "defence in depth" about it.
    """
    fetch_src = FETCH.read_text(encoding="utf-8")
    assert "taxonomy.excluded_files()" in fetch_src
    assert "NOT two independent layers" in fetch_src, (
        "the shared-source-of-truth caveat has been removed from pass 0"
    )


def test_the_exclusion_list_is_not_reachable_by_a_wrong_path_silently():
    """A rename un-excludes the file. Pin that this is still only path-keyed.

    Not a bug to fix here — it is recorded as the top unmitigated item in R17 —
    but it must not be forgotten by someone reading the two layers as robust.
    """
    entries = taxonomy._raw().get("excluded", {}).get("files", [])
    assert entries, "no excluded files configured"
    for e in entries:
        assert "path" in e, "an excluded entry has no path"
        assert "sha256" not in e, (
            "an excluded entry now carries a sha256 — the exclusion is no longer "
            "path-keyed, so R17's rename failure mode may be closed. Update the "
            "risk register and this test together."
        )
