"""AUDIT §6.3 — README.md must not hand-write counts or a plugin version.

README published `5,048 nodes · 36,677 edges` at plugin `v0.1.2` while
plugin.json said 0.1.4. Two bumps stale, and nothing would have caught it.

Its node table was also wrong in the same way as AUDIT §6.1: it omitted `file`,
so it summed to 4,974 against its own stated 5,048.

gen_index.py exists because "the reference implementation hand-wrote 1,072 files
/ 61 clients / 773 instructors into plugin.json and its website while the actual
graph held 1,833 / 32 / 351". Its docstring says never hand-write a count.
README was the one place still doing it, so the block is now generated and
refresh.py regenerates it on every build.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

README = REPO / "README.md"
GRAPH = REPO / "knowledge" / "graph.json"
PLUGIN = REPO / ".claude-plugin" / "plugin.json"
OPEN_MARK, CLOSE_MARK = "<!-- generated:counts -->", "<!-- /generated:counts -->"


def _block() -> str:
    text = README.read_text(encoding="utf-8")
    assert OPEN_MARK in text and CLOSE_MARK in text, (
        "README.md has no generated counts block — run pipeline/gen_index.py"
    )
    return text.split(OPEN_MARK, 1)[1].split(CLOSE_MARK, 1)[0]


def test_readme_names_the_current_plugin_version():
    version = json.loads(PLUGIN.read_text(encoding="utf-8"))["version"]
    assert f"v{version}" in _block(), (
        f"README does not name plugin version {version}. This is the exact "
        "drift that left v0.1.2 published against a 0.1.4 manifest."
    )


def test_readme_totals_match_the_graph():
    meta = json.loads(GRAPH.read_text(encoding="utf-8"))["meta"]
    block = _block()
    assert f"{meta['nodes']:,} nodes" in block
    assert f"{meta['edges']:,} edges" in block


def test_every_published_count_matches_a_recount():
    """Node AND edge rows, checked against the graph rather than against meta.

    Recounting is the point: meta itself was wrong in §6.1, so a test that
    compared README to meta would have agreed with the bug.
    """
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    actual = Counter(n["type"] for n in g["nodes"])
    actual.update(Counter(e["rel"] for e in g["edges"]))
    published = re.findall(r"^\|\s*([a-z_]+)\s*\|\s*([\d,]+)\s*\|$", _block(), re.M)
    assert published, "no count rows found in the generated block"
    for name, n in published:
        assert int(n.replace(",", "")) == actual[name], (
            f"README publishes {name}={n}, graph has {actual[name]}"
        )


def test_readme_publishes_every_node_type_present():
    """The omission that made the old table sum to 4,974: `file` was missing."""
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    present = {n["type"] for n in g["nodes"]}
    published = {m[0] for m in re.findall(r"^\|\s*([a-z_]+)\s*\|\s*([\d,]+)\s*\|$",
                                          _block(), re.M)}
    assert present <= published, f"node types missing from README: {sorted(present - published)}"


def test_no_hand_written_version_outside_the_generated_block():
    text = README.read_text(encoding="utf-8")
    outside = text.split(OPEN_MARK, 1)[0] + text.split(CLOSE_MARK, 1)[-1]
    stray = re.findall(r"\bv\d+\.\d+\.\d+\b", outside)
    assert not stray, (
        f"hand-written version string(s) in README prose: {stray}. "
        "Versions belong in the generated block."
    )
