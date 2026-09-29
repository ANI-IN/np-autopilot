"""Accuracy item 3, as a test so it runs in CI rather than only by hand.

`eval/mastersheet_rederive.py` re-reads the workbook with openpyxl and its own
cell logic, deliberately NOT importing `pipeline/lib/mastersheet.py`. Running
the pipeline's parser against the pipeline's output would show the code is
self-consistent, which is not the question.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SHEET = (REPO / ".drive-cache" / "02-curriculum" /
         "Resource Collection Mastersheet (Software + System).xlsx")
GRAPH = REPO / "knowledge" / "content_graph.json"

pytestmark = pytest.mark.skipif(
    not (SHEET.exists() and GRAPH.exists()),
    reason="needs the corpus cache and a built content graph")


def test_the_rederivation_finds_no_unexplained_difference(capsys):
    mod = runpy.run_path(str(REPO / "eval" / "mastersheet_rederive.py"))
    rc = mod["main"]()
    out = capsys.readouterr().out
    assert rc == 0, f"the re-derivation reported differences:\n{out}"
    assert "0 unexplained differences" in out


def test_the_diff_does_not_import_the_pipeline_parser():
    """The independence is the point; assert it rather than trust it."""
    src = (REPO / "eval" / "mastersheet_rederive.py").read_text(encoding="utf-8")
    assert "import mastersheet" not in src and "lib.mastersheet" not in src, (
        "the re-derivation imports the parser it is supposed to check")
    assert "import openpyxl" in src


def test_it_can_actually_report_a_difference(monkeypatch, capsys):
    """Mutation: a diff that cannot fail is worth nothing. Perturb the graph
    reading and the run must report a difference and exit non-zero."""
    mod = runpy.run_path(str(REPO / "eval" / "mastersheet_rederive.py"))
    real = mod["from_graph"]

    def broken():
        g = real()
        k = sorted(g)[0]
        g[k] = dict(g[k], primary=list(g[k]["primary"]) + ["Injected Person"])
        return g

    mod["from_graph"] = broken
    import types
    ns = types.SimpleNamespace(**mod)
    # re-run main() with the patched reader in its own globals
    fn = mod["main"]
    fn.__globals__["from_graph"] = broken
    rc = fn()
    out = capsys.readouterr().out
    assert rc == 1, "the diff passed with an injected instructor"
    assert "DIFFERENCE" in out
