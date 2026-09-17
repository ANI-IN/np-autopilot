"""GET /api/coverage — whole-graph gaps. SQL, per DECISIONS §C.2."""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import data                                                   # noqa: E402


def _coverage(conn, identity, params):
    return data.coverage(conn), 1


#: (endpoint name, read function). The HTTP shell lives in api/index.py:
#: one entry point, so there is no route that can forget the guard.
ENDPOINT = ("coverage", _coverage)
