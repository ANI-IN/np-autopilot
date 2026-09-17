"""GET /api/aliases — aliases awaiting a human decision.

F3. The surface exists so a decision can be RECORDED; it deliberately does not
make one. `lib/resolve.py` returns Ambiguous rather than picking because three
shipped bugs came from picking with no signal, and a UI that ranked candidates
would reintroduce exactly that one layer up.

Admin only — this is the curation surface, and members have no read access to
curation tables at all.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import curation_service as cs                                 # noqa: E402
from lib.guard import serve                                            # noqa: E402


def _aliases(conn, identity, params):
    rows = cs.ambiguous_aliases(conn)
    return {
        "unresolved": rows,
        "count": len(rows),
        "note": ("These are UNRESOLVED on purpose. Each failed the "
                 "sibling-domain test: more than one domain could plausibly be "
                 "meant. Recording a decision needs a program owner, not a "
                 "heuristic — nothing here ranks the candidates."),
    }, len(rows)


handler = serve("aliases", _aliases)
