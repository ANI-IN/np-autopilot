"""uv.lock is what Vercel installs, and it must match pyproject.toml.

Vercel's Python build installs "required dependencies from uv.lock", not from
pyproject.toml. B3 added Brotli to pyproject.toml and never re-locked: the
prebuilt artifact shipped without it, and /api/structure would have fallen back
to gzip in production with nothing to say so. Found building the window's
artifact, 2026-09-30.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIN = re.compile(r"\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned() -> dict[str, str]:
    deps = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]
    out = {}
    for d in deps:
        m = PIN.match(d)
        assert m, f"pyproject dependency is not pinned with ==: {d!r}"
        out[_norm(m.group(1))] = m.group(2)
    return out


def locked(text: str) -> dict[str, str]:
    return {_norm(p["name"]): p["version"]
            for p in tomllib.loads(text).get("package", [])}


def mismatches(pins: dict, lock: dict) -> list[str]:
    return [f"{n}: pyproject {v}, uv.lock {lock.get(n, 'MISSING')}"
            for n, v in sorted(pins.items()) if lock.get(n) != v]


def test_every_pyproject_pin_is_locked_at_that_version():
    bad = mismatches(pinned(), locked((REPO / "uv.lock").read_text()))
    assert not bad, "run `uv lock` and commit uv.lock:\n  " + "\n  ".join(bad)


def test_the_check_catches_a_missing_package():
    """Non-vacuity: the exact shape of the bug — a pin absent from the lock."""
    lock = locked((REPO / "uv.lock").read_text())
    lock.pop("brotli")
    assert mismatches(pinned(), lock) == ["brotli: pyproject 1.2.0, uv.lock MISSING"]
