"""B5: two runs over unchanged input must produce byte-identical output."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOLVED = REPO / "knowledge" / "resolved.json"


def _sha() -> str:
    return hashlib.sha256(RESOLVED.read_bytes()).hexdigest()


def _run() -> None:
    r = subprocess.run([sys.executable, "pipeline/03_resolve.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def test_resolve_is_byte_identical_across_runs() -> None:
    _run()
    first = _sha()
    _run()
    second = _sha()
    assert first == second, (
        f"resolved.json differs between runs:\n  run1 {first}\n  run2 {second}\n"
        "IDs must be a hash of (type, canonical name) and nothing else — no "
        "timestamps, no iteration order, no randomness."
    )


def test_ids_are_derived_from_canonical_not_raw() -> None:
    import json
    nodes = json.loads(RESOLVED.read_text(encoding="utf-8"))["nodes"]
    by_id = {}
    for n in nodes:
        by_id.setdefault(n["id"], set()).add(n["label"])
    collisions = {i: v for i, v in by_id.items() if len(v) > 1}
    assert not collisions, f"one id maps to several labels: {collisions}"

    expected = hashlib.sha256(b"person\x00Animesh Kumar").hexdigest()[:16]
    animesh = [n for n in nodes if n["label"] == "Animesh Kumar"]
    assert animesh, "Animesh Kumar missing from resolved nodes"
    assert animesh[0]["id"] == f"per_{expected}", (
        "id is not sha256(type + canonical) — a label edit would orphan edges"
    )
