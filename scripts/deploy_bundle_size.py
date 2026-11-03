#!/usr/bin/env python3
"""What the deploy ships, counted: files and bytes, and the dependency count
(run 6, F6; recorded in docs/LEGACY_REMOVAL.md before and after the cleanup).

THE SET. vercel.json serves public/ as static files and bundles the Python
function from api/, whose imports reach web/, pipeline/lib/ (and
pipeline/__init__.py) and config/ (.vercelignore's header). Inside those roots
.vercelignore still applies (`*.md` except README.md and public/kb/guide.md,
`pipeline/*.py` except pipeline/__init__.py), so it is applied here too, with
the gitignore rules the file uses: last match wins, `!` re-includes, a trailing
`/` is a directory, a pattern with no `/` matches the base name.

Counts TRACKED files of a git revision (default HEAD), so a past state can be
measured exactly: `--rev <commit>`. No network, no database.

    python scripts/deploy_bundle_size.py               # HEAD
    python scripts/deploy_bundle_size.py --rev 36aad36 --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOTS = ("api/", "web/", "pipeline/lib/", "pipeline/__init__.py", "config/", "public/")
VENDOR = "public/vendor/"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def _ignore_rules(rev: str) -> list[tuple[bool, str]]:
    try:
        text = _git("show", f"{rev}:.vercelignore")
    except subprocess.CalledProcessError:
        return []
    rules = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        neg = ln.startswith("!")
        rules.append((neg, ln[1:] if neg else ln))
    return rules


def _glob(pattern: str, path: str) -> bool:
    """fnmatch, except that `*` and `?` never cross a `/` (gitignore)."""
    rx = "".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, path) is not None


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3].lstrip("/") + "/")
    if pattern.endswith("/"):
        d = pattern.rstrip("/").lstrip("/")
        return path.startswith(d + "/") or ("/" + d + "/") in ("/" + path)
    if "/" in pattern.rstrip("/"):
        return _glob(pattern.lstrip("/"), path)
    return _glob(pattern, path.rsplit("/", 1)[-1])


def ignored(path: str, rules: list[tuple[bool, str]]) -> bool:
    out = False
    for neg, pat in rules:
        if _matches(pat, path):
            out = not neg
    return out


def shipped(rev: str) -> list[tuple[str, int]]:
    rules = _ignore_rules(rev)
    listing = _git("ls-tree", "-r", "-l", rev, "--", *ROOTS)
    files = []
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        size = meta.split()[3]
        if size == "-" or ignored(path, rules):
            continue
        files.append((path, int(size)))
    return files


def python_requirements(rev: str) -> dict:
    req = _git("show", f"{rev}:requirements.txt")
    entries = [ln.split("#")[0].strip() for ln in req.splitlines()]
    entries = [e for e in entries if e and not e.startswith("-")]
    pyproject = _git("show", f"{rev}:pyproject.toml")
    block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", pyproject, re.S | re.M)
    function_deps = re.findall(r'"([^"]+)"', block.group(1)) if block else []
    try:
        lock = _git("show", f"{rev}:uv.lock")
        locked = re.findall(r'^\[\[package\]\]\nname = "([^"]+)"', lock, re.M)
    except subprocess.CalledProcessError:
        locked = []
    return {"requirements_txt": len(entries), "pyproject_function": len(function_deps),
            "uv_lock_packages": len(locked), "requirements_names": [re.split(r"[=<>\[]", e)[0] for e in entries]}


def vendored(files: list[tuple[str, int]]) -> list[str]:
    """One library per vendored payload: a file or a directory under public/vendor/,
    licences not counted."""
    libs = set()
    for path, _ in files:
        if not path.startswith(VENDOR):
            continue
        rest = path[len(VENDOR):]
        if "/" in rest:
            libs.add(rest.split("/", 1)[0])
        elif "LICENSE" not in rest.upper():
            libs.add(rest.rsplit(".", 2)[0].split(".")[0].replace("-sprite", ""))
    return sorted(libs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files = shipped(a.rev)
    by_root: dict[str, list[int]] = {}
    for path, size in files:
        root = next(r for r in ROOTS if path == r or path.startswith(r))
        agg = by_root.setdefault(root, [0, 0])
        agg[0] += 1
        agg[1] += size
    deps = python_requirements(a.rev)
    libs = vendored(files)
    out = {"rev": _git("rev-parse", "--short", a.rev).strip(), "files": len(files),
           "bytes": sum(s for _, s in files), "by_root": by_root,
           "python": {k: v for k, v in deps.items() if k != "requirements_names"},
           "vendored_js": libs, "dependencies_total": deps["requirements_txt"] + len(libs)}
    if a.json:
        print(json.dumps(out, indent=1))
        return 0
    print(f"rev {out['rev']}: {out['files']} files, {out['bytes']:,} bytes shipped")
    for root, (n, b) in by_root.items():
        print(f"  {root:<22} {n:>4} files {b:>12,} bytes")
    print(f"python: requirements.txt {deps['requirements_txt']} entries, function (pyproject) "
          f"{deps['pyproject_function']}, uv.lock {deps['uv_lock_packages']} packages")
    print(f"vendored JS/asset libraries: {len(libs)} ({', '.join(libs)})")
    print(f"dependencies (requirements.txt entries + vendored libraries): {out['dependencies_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
