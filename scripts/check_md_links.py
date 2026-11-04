#!/usr/bin/env python3
"""Fail if a Markdown file in this repository links to a file that does not exist.

    python scripts/check_md_links.py        # prints `file:line -> target` per broken link; exit 1 if any

What is checked: every inline link and image, `[text](target)` and
`![alt](target)`, in every Markdown file git knows about (tracked, plus
untracked files that are not gitignored, so a new doc is checked before its
first commit). Fenced code blocks and inline code spans are skipped.

How a target resolves:
- `http(s):`, `mailto:` and any other `scheme:` target is skipped, and so is a
  target that is only an anchor (`#section`).
- `#anchor` and `?query` are stripped; the anchor itself is not checked.
- A target starting with `/` is relative to the repository root, except in a
  file under public/: the app serves public/ as the site root, so there `/`
  means public/ (public/kb/guide.md links `/kb/guide/*.png`). Anything else
  is relative to the file that contains the link.
- The target must be a file or directory in the same set git knows about
  (tracked or untracked-not-ignored). A gitignored local file does not count:
  a fresh clone would not have it.

docs/project-history/ is checked like every other folder. Its records stay as
written, but a link in them to a file that was later deleted was turned into
plain text (2026-11-04 cleanup) rather than allowed here, so this script has
no exceptions: every remaining link must resolve.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath
from urllib.parse import unquote

REPO = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                      text=True, check=True).stdout.strip()

#: `[text](target)` or `![alt](target)`; the target may be `<...>` and may carry a "title".
LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[\"'(][^)]*)?\s*\)")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def known_paths() -> tuple[list[str], set[str]]:
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=REPO, capture_output=True, check=True).stdout.decode("utf-8")
    files = sorted({f for f in out.split("\0") if f})
    paths = set(files)
    for f in files:
        parent = PurePosixPath(f).parent
        while str(parent) not in (".", ""):
            paths.add(str(parent))
            parent = parent.parent
    return [f for f in files if f.lower().endswith(".md")], paths


def normalise(path: PurePosixPath) -> str | None:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None                      # escapes the repository
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def links(text: str):
    fenced = None
    for n, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if m:
            if fenced is None:
                fenced = m.group(1)
            elif m.group(1) == fenced:
                fenced = None
            continue
        if fenced:
            continue
        for lm in LINK.finditer(CODE_SPAN.sub("", line)):
            yield n, lm.group(1).strip("<>")


def broken(md: str, paths: set[str], text: str):
    for n, target in links(text):
        if not target or target.startswith("#") or SCHEME.match(target):
            continue
        rel = unquote(re.split(r"[#?]", target, maxsplit=1)[0])
        if not rel:
            continue
        if rel.startswith("/"):
            base = PurePosixPath("public") if md.startswith("public/") else PurePosixPath(".")
        else:
            base = PurePosixPath(md).parent
        resolved = normalise(base / rel.lstrip("/"))
        if resolved is None or (resolved and resolved not in paths):
            yield n, target


def main() -> int:
    mds, paths = known_paths()
    bad = 0
    for md in mds:
        try:
            with open(f"{REPO}/{md}", encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:                # deleted in the working tree, not yet staged
            continue
        for n, target in broken(md, paths, text):
            print(f"{md}:{n} -> {target}")
            bad += 1
    print(f"{len(mds)} Markdown files checked, {bad} broken link(s)", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
