"""GET /api/search?q=&types=&limit= — bounded label search."""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402


def _search(conn, identity, params):
    q = (params.get("q") or "").strip()
    if len(q) < 2:
        return {"results": [], "note": "query must be at least 2 characters"}, 0
    types = [t for t in (params.get("types") or "").split(",") if t]
    rows = data.search(conn, q, types or None, params.get("limit", 50))
    return {"results": rows, "count": len(rows)}, len(rows)


#: (endpoint name, read function). The HTTP shell lives in api/index.py:
#: one entry point, so there is no route that can forget the guard.
ENDPOINT = ("search", _search)
