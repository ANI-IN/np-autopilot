"""GET /api/structure — the whole structure layer, which is the default view.

REPLACES THE BOUNDED OVERVIEW, as a recorded owner decision
(docs/DEFAULT-VIEW.md D1/D2). `/api/overview` caps at 60-odd nodes and stays
for compatibility; this returns the structure layer entire, because a capped
landing view showed a shape the graph does not have.

NO PARAMETERS, for the reason `overview` has none: the node types are a module
constant in `data.py`, not values a caller supplies, so this cannot be widened
into an arbitrary-subgraph endpoint. Provenance is excluded, so the file hubs
stay unreachable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402


def _structure(conn, identity, params):
    out = data.structure(conn)
    return out, out["n"]


#: B3. The router answers If-None-Match with a 304 from `etag` alone — one
#: small query instead of the payload — and compresses the body. `private`
#: because the graph is behind auth: a browser may keep it, a shared cache may
#: not. Five minutes, then revalidate (docs/DEFAULT-VIEW.md D3).
ENDPOINT = ("structure", _structure,
            {"etag": data.structure_etag,
             "cache": "private, max-age=300, must-revalidate",
             "compress": True})
