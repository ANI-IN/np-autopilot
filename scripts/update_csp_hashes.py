#!/usr/bin/env python3
"""Recompute the map's inline-script hashes in vercel.json's CSP (public/index.html
has inline <script> blocks; the CSP allows exactly their SHA-256 hashes).
Run after editing an inline script; tests/test_login_flow.py checks the result.

    python scripts/update_csp_hashes.py
"""
import base64
import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
html = (REPO / "public" / "index.html").read_bytes().decode("utf-8")
want = ["'sha256-" + base64.b64encode(hashlib.sha256(b.encode()).digest()).decode() + "'"
        for b in re.findall(r"<script>([\s\S]*?)</script>", html)]
vj = REPO / "vercel.json"
txt = vj.read_bytes().decode("utf-8")
new, n = re.subn(r"(script-src 'self' [^;']*?)((?: ?'sha256-[A-Za-z0-9+/=]+')+)", lambda m: m.group(1).rstrip() + ' ' + ' '.join(want), txt)
if n != 1:
    raise SystemExit(f"expected one script-src with hashes in vercel.json, found {n}")
vj.write_bytes(new.encode("utf-8"))
print(f"vercel.json: {len(want)} inline-script hash(es) set")
