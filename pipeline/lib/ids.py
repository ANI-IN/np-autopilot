"""The ONE node-id minting function, for every pass.

MOVED HERE FROM `pipeline/03_resolve.py`, unchanged, on 2026-09-29. It had
lived in a pass script, which meant pass 7 could not import it — a module whose
name starts with a digit is not importable — so pass 7 grew its own, and the
two drifted:

    pass 3   `mod_4626b0a141705837`   type prefix + 16 hex
    pass 7   `4626b0a1...` (64 hex)   no prefix

`db/migrations/0002_graph_schema.up.sql` constrains every id to
`^[a-z]{3}_[0-9a-f]{16}$`, so all 5,811 content nodes were unprojectable. The
constraint was right and the second implementation was the defect; widening it
would have removed the only proof that every id in the table came from one
function.

THE PREFIX IS A READING AID, NOT IDENTITY. `program` and `program_week` both
shorten to `pro`, and `assignment` and `assignment_review` both to `ass`. That
is harmless: the digest hashes the FULL node type, so two types never collide
on the same canonical. Do not be tempted to disambiguate the prefix — changing
it changes every id of that type.
"""
from __future__ import annotations

import hashlib


def node_id(node_type: str, canonical: str) -> str:
    """Deterministic id. Hash of type + canonical name, never of the raw label.

    The reference implementation derived ids from the raw label ('I:workflows
    are powerful'), so any label edit silently created a new node and orphaned
    every edge pointing at the old one.
    """
    digest = hashlib.sha256(f"{node_type}\x00{canonical}".encode()).hexdigest()
    return f"{node_type[:3]}_{digest[:16]}"


def compound(node_type: str, *parts) -> str:
    """An id for a node keyed on several values rather than one name.

    The parts are joined with `|` before hashing, so the canonical string stays
    readable in a debugger and two different groupings cannot collide.
    """
    return node_id(node_type, "|".join(str(p) for p in parts))
