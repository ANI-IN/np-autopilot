"""GET /api/neighbourhood?id=&depth=&rels= — expand around one node.

Provenance is unreachable here by construction: sourced_from is not in the
edges table at all, so the degree-18,134 file hubs cannot be walked through.
"""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402


def _neighbourhood(conn, identity, params):
    rels = [r for r in (params.get("rels") or "").split(",") if r]
    out = data.neighbourhood(conn, (params.get("id") or "").strip(),
                             depth=params.get("depth", 1),
                             rels=rels or None,
                             limit=params.get("limit", 300))
    if out["truncated"]:
        out["note"] = ("result hit the row cap — this is a TOOLING limit, not a "
                       "sparse graph. Narrow by edge type or reduce depth.")
    return out, len(out["nodes"])


#: (endpoint name, read function). The HTTP shell lives in api/index.py:
#: one entry point, so there is no route that can forget the guard.
ENDPOINT = ("neighbourhood", _neighbourhood)
