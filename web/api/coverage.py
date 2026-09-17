"""GET /api/coverage — whole-graph gaps. SQL, per DECISIONS §C.2."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import data                                                   # noqa: E402
from lib.guard import serve                                            # noqa: E402


def _coverage(conn, identity, params):
    return data.coverage(conn), 1


handler = serve("coverage", _coverage)
