"""AUDIT §6.2 — pipeline/README.md must be checkable against the pipeline.

It declared passes 1-5 "**not built**" for the entire life of the project while
all five were built, tested and shipping. Nobody noticed, because prose is not
executed.

These tests execute the claims that have a machine-readable counterpart: which
scripts exist, and which environment variables the pipeline actually reads. They
do not police wording.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PIPELINE_README = REPO / "pipeline" / "README.md"


def test_every_pipeline_script_is_listed():
    """Caught query.py, which was undocumented — not stale, simply absent."""
    text = PIPELINE_README.read_text(encoding="utf-8")
    missing = [p.name for p in sorted((REPO / "pipeline").glob("*.py"))
               if p.name not in text]
    assert not missing, f"pipeline scripts absent from pipeline/README.md: {missing}"


def test_no_script_is_described_as_not_built():
    """The exact stale claim. 00_fetch_drive is 'never run', which is different."""
    for line in PIPELINE_README.read_text(encoding="utf-8").splitlines():
        if "not built" in line.lower():
            raise AssertionError(f"stale 'not built' claim: {line.strip()}")


def test_documented_env_vars_are_the_ones_the_pipeline_reads():
    """Drift either way is a bug: an undocumented knob, or a phantom one."""
    documented = set(re.findall(r"`(NP_[A-Z_]+)`",
                                PIPELINE_README.read_text(encoding="utf-8")))
    used = set()
    for py in sorted((REPO / "pipeline").rglob("*.py")):
        used |= set(re.findall(r"environ(?:\.get)?[(\[]\s*[\"'](NP_[A-Z_]+)[\"']",
                               py.read_text(encoding="utf-8")))
    assert used <= documented, f"env vars read but undocumented: {sorted(used - documented)}"
    assert documented <= used, f"env vars documented but never read: {sorted(documented - used)}"
