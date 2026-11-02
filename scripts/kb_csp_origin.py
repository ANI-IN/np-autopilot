#!/usr/bin/env python3
"""Put the Supabase Realtime origin into vercel.json's connect-src — from
configuration, never by hand (brief D2).

    python scripts/kb_csp_origin.py                 # read KB_REALTIME_ORIGIN from the environment
    python scripts/kb_csp_origin.py https://<ref>.supabase.co
    python scripts/kb_csp_origin.py --clear         # back to polling only
    python scripts/kb_csp_origin.py --check         # exit 1 if vercel.json is malformed

Adds exactly `https://<ref>.supabase.co wss://<ref>.supabase.co` after
'self', replacing any Supabase origin written before. Set the same value as
KB_REALTIME_ORIGIN in the Vercel project: /api/kb/realtime only hands the
browser a socket configuration when that variable names the origin the page
is allowed to connect to; otherwise the browser polls. Prints the policy; it
never deploys anything.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

VERCEL = Path(__file__).resolve().parent.parent / "vercel.json"
SUPA = re.compile(r"\s(?:https|wss)://[a-z0-9-]+\.supabase\.co")
ORIGIN = re.compile(r"^https://[a-z0-9-]+\.supabase\.co$")


def _csp(cfg: dict) -> dict:
    for rule in cfg["headers"]:
        if rule.get("source") == "/(.*)":
            for h in rule["headers"]:
                if h["key"].lower() == "content-security-policy":
                    return h
    raise SystemExit("vercel.json has no content-security-policy header for /(.*)")


def apply(origin: str | None, path: Path = VERCEL) -> str:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    h = _csp(cfg)
    policy = SUPA.sub("", h["value"])
    if origin:
        origin = origin.rstrip("/")
        if not ORIGIN.match(origin):
            raise SystemExit(f"not a Supabase project origin: {origin!r} (expected https://<ref>.supabase.co)")
        ws = "wss://" + origin[len("https://"):]
        policy = policy.replace("connect-src 'self'", f"connect-src 'self' {origin} {ws}", 1)
    h["value"] = policy
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return policy


def check(path: Path = VERCEL) -> list[str]:
    """Problems with connect-src: a Supabase origin without its wss twin (or vice versa)."""
    value = _csp(json.loads(path.read_text(encoding="utf-8")))["value"]
    m = re.search(r"connect-src ([^;]+)", value)
    srcs = m.group(1).split() if m else []
    https = {s[len("https://"):] for s in srcs if s.startswith("https://") and s.endswith(".supabase.co")}
    wss = {s[len("wss://"):] for s in srcs if s.startswith("wss://")}
    probs = []
    if "'self'" not in srcs:
        probs.append("connect-src lost 'self'")
    if https != wss:
        probs.append(f"Supabase https/wss origins do not pair up: https={sorted(https)} wss={sorted(wss)}")
    return probs


def main(argv: list[str]) -> int:
    if argv[:1] == ["--check"]:
        probs = check()
        print("\n".join(probs) or "vercel.json connect-src OK")
        return 1 if probs else 0
    origin = None if argv[:1] == ["--clear"] else (argv[0] if argv else os.environ.get("KB_REALTIME_ORIGIN"))
    if not origin and argv[:1] != ["--clear"]:
        raise SystemExit("give the origin (https://<ref>.supabase.co) or set KB_REALTIME_ORIGIN; --clear removes it")
    print(apply(origin))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
