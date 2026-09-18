"""GET /api/overview — the default view. Every domain, and who owns or delivers it.

No parameters, by design. `data.overview()` names the node type and the two
relations as module constants rather than reading them from the query string,
so this cannot be widened into a general subgraph endpoint by a caller. The
reasoning is in that function's docstring and it is load-bearing: §A.3 made the
provenance join unwriteable server-side, but a client that downloads a whole
graph in bulk walks what it holds instead of asking SQL, and routes around that
guarantee entirely.
"""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402


def _overview(conn, identity, params):
    out = data.overview(conn)
    if out["truncated"]:
        out["note"] = (f"default view hit the {data.OVERVIEW_CAP}-node cap — a "
                       "TOOLING limit, not the shape of the graph. The landing "
                       "view is meant to be small; this means the projection "
                       "grew and the cap needs a deliberate decision.")
    return out, len(out["nodes"])


#: (endpoint name, read function). The HTTP shell lives in api/index.py:
#: one entry point, so there is no route that can forget the guard.
ENDPOINT = ("overview", _overview)
