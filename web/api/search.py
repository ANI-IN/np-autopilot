"""GET /api/search?q=&types=&limit= — bounded label search."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import data                                                   # noqa: E402
from lib.guard import serve                                            # noqa: E402


def _search(conn, identity, params):
    q = (params.get("q") or "").strip()
    if len(q) < 2:
        return {"results": [], "note": "query must be at least 2 characters"}, 0
    types = [t for t in (params.get("types") or "").split(",") if t]
    rows = data.search(conn, q, types or None, params.get("limit", 50))
    return {"results": rows, "count": len(rows)}, len(rows)


handler = serve("search", _search)
