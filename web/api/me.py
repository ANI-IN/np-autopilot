"""GET /api/me — who the server thinks you are, and what that gets you.

Exists so the explorer can tell three states apart that all look like an empty
graph from the outside:

    no session          -> 401, sign in
    session, no profile -> 200 with role 'none' and a sentence saying so
    session and profile -> 200 with the role

The middle state is the one worth building an endpoint for. Without it, a newly
signed-in employee sees an empty canvas and has no way to distinguish "you have
not been granted access" from "the explorer is broken" — and this project has a
standing rule against states that present as absence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.guard import serve                                            # noqa: E402


def _me(conn, identity, params):
    with conn.cursor() as cur:
        cur.execute("select np_role()")
        role = cur.fetchone()[0]
        cur.execute("select count(*) from nodes")
        visible = cur.fetchone()[0]
    return {
        "subject": identity.subject,
        "email": identity.email,
        "shared_account": identity.is_shared_account,
        "role": role,
        "visible_nodes": visible,
        "note": None if role != "none" else (
            "You are signed in, and you can read nothing. That is not a fault: "
            "a session proves identity, a profile grants access, and this "
            "account has no profile. Ask an administrator."),
    }, 1


handler = serve("me", _me)
