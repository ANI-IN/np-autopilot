"""The LOCAL Supabase stack's endpoints and keys, read from `supabase status`.

Shared by eval/kb_demo_server.py and eval/kb_demo_seed.py. These are the local
stack's own development keys (printed by `supabase status` on any machine);
they are read in-process and never printed or written anywhere.

Refuses anything that is not a loopback stack: a demo can never be pointed at a
shared project by accident.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
CLI = ["npx", "-y", "supabase@2.118.0"]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

SESSION_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
TRANSACTION_DSN = "postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres"


class NotLocal(SystemExit):
    pass


def require_loopback(url: str, what: str) -> None:
    host = urlparse(url).hostname
    if host not in LOOPBACK:
        raise NotLocal(f"REFUSED: {what} host is {host!r}; the demo runs against the local stack only")


def status() -> dict:
    """`supabase status -o json` for db/local. Raises SystemExit if the stack is down."""
    exe = shutil.which(CLI[0]) or CLI[0]
    try:
        out = subprocess.run([exe, *CLI[1:], "status", "-o", "json", "--workdir", str(REPO / "db" / "local")],
                             capture_output=True, text=True, timeout=120, check=True).stdout
        st = json.loads(out[out.index("{"):])
    except (subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit("The local Supabase stack is not running. Start it with:\n"
                         "  npx -y supabase@2.118.0 start --workdir db/local") from exc
    require_loopback(st["API_URL"], "API_URL")
    return st


def configure_env(st: dict) -> None:
    """Point the app at the local stack: database, GoTrue and its signing keys."""
    for var, dsn in (("SUPABASE_DB_URL_SESSION", SESSION_DSN), ("SUPABASE_DB_URL_TRANSACTION", TRANSACTION_DSN)):
        current = os.environ.get(var, dsn)
        require_loopback(current, var)
        os.environ[var] = current
    os.environ["SUPABASE_URL"] = st["API_URL"]
    os.environ["SUPABASE_ANON_KEY"] = st["ANON_KEY"]
    os.environ["SUPABASE_JWT_SECRET"] = st["JWT_SECRET"]
