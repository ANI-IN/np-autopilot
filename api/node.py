"""GET /api/node?id= — one node, with its provenance in both shapes."""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402
from lib.kb import npmap                                               # noqa: E402


def _src():
    """kb (default) or the old tables (NP_MAP_SOURCE=old, the rollback switch)."""
    return npmap if npmap.enabled() else data


def _node(conn, identity, params):
    node_id = (params.get("id") or "").strip()
    src = _src()
    n = src.node(conn, node_id)
    if n is None:
        # Indistinguishable from "exists but you may not see it", deliberately.
        # Saying "forbidden" would confirm the row exists, which for a withheld
        # hiring rejection is the disclosure itself.
        return {"error": "not_found"}, 0
    out = {"node": n, "provenance": src.provenance(conn, node_id)}
    # B3, lazy panels: what the bulk /api/structure left out, on click.
    if str(params.get("detail") or "") == "1":
        out.update(src.node_detail(conn, node_id))
    return out, 1


#: (endpoint name, read function). The HTTP shell lives in api/index.py:
#: one entry point, so there is no route that can forget the guard.
#: Compressed (B3): with ?detail=1 a heavy module's panel is ~75 KB of JSON.
#: NOT cached — no etag, no cache option, so it stays `private, no-store`.
ENDPOINT = ("node", _node, {"compress": True})
