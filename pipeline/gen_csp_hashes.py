#!/usr/bin/env python3
"""Recompute the CSP script hashes in vercel.json from public/index.html.

WHY THIS IS A SCRIPT AND NOT A NOTE IN A README. `script-src` has no
'unsafe-inline', so the two inline blocks are pinned by sha256. Edit the HTML
without recomputing and the DEPLOYED page silently refuses to run its own
scripts — a blank explorer with a console error nobody sees until they open
devtools. `tests/test_login_flow.py` catches it, which means the failure shows
up as a red test far from the edit that caused it.

A hand-maintained hash is a guard that stops matching the moment someone is in
a hurry. Run this instead:

    python3 pipeline/gen_csp_hashes.py           # rewrite vercel.json
    python3 pipeline/gen_csp_hashes.py --check   # CI: fail if stale
"""
from __future__ import annotations

import base64
import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = REPO / "public" / "index.html"
VERCEL = REPO / "vercel.json"


def hashes(html: str) -> list[str]:
    blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
    if len(blocks) != 2:
        raise SystemExit(f"expected 2 inline <script> blocks, found {len(blocks)}. "
                         "The CSP pins exactly two; adding a third is a "
                         "deliberate change, not a regeneration.")
    return ["'sha256-" + base64.b64encode(
        hashlib.sha256(b.encode()).digest()).decode() + "'" for b in blocks]


def main() -> int:
    check = "--check" in sys.argv
    want = hashes(HTML.read_text(encoding="utf-8"))
    conf = VERCEL.read_text(encoding="utf-8")
    have = ["'" + h + "'" for h in re.findall(r"sha256-[A-Za-z0-9+/=]+", conf)]

    missing = [h for h in want if h.strip("'") not in conf]
    if not missing:
        print(f"  CSP hashes are current ({len(want)} inline blocks)")
        return 0
    if check:
        print("  CSP hashes are STALE. Run: python3 pipeline/gen_csp_hashes.py")
        for h in want:
            print(f"    {h}")
        return 1

    # Replace the stale hashes positionally: the config lists them in the same
    # order the page defines them.
    out, i = conf, 0
    for old in re.findall(r"sha256-[A-Za-z0-9+/=]+", conf):
        if i < len(want) and old != want[i].strip("'"):
            out = out.replace(old, want[i].strip("'"), 1)
        i += 1
    VERCEL.write_text(out, encoding="utf-8")
    print(f"  rewrote {len(missing)} hash(es) in vercel.json")
    for h in want:
        print(f"    {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
