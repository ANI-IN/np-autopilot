"""GET /api/node?id= — one node, with its provenance in both shapes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import data                                                   # noqa: E402
from lib.guard import serve                                            # noqa: E402


def _node(conn, identity, params):
    node_id = (params.get("id") or "").strip()
    n = data.node(conn, node_id)
    if n is None:
        # Indistinguishable from "exists but you may not see it", deliberately.
        # Saying "forbidden" would confirm the row exists, which for a withheld
        # hiring rejection is the disclosure itself.
        return {"error": "not_found"}, 0
    return {"node": n, "provenance": data.provenance(conn, node_id)}, 1


handler = serve("node", _node)
