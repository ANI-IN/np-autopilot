"""NP Autopilot: the original site's tables (public.nodes, edges, ...) -> the
KB. Thin wrappers: the logic stays where it is (sync.load_mapping,
sync.desired_state, legacy_delete.excluded, legacy.archive), so this
connector behaves exactly as the sync always has.

The functions are looked up on their modules at call time (`sync.load_mapping`,
not a reference taken at import), so a test that replaces one still reaches it.
"""
from __future__ import annotations

from .base import Connector


class NpAutopilot(Connector):
    name = "np_autopilot"
    actor_label = "Sync (NP Autopilot)"         # = activity._actor_label for actor_type 'sync'

    def load_config(self, conn) -> dict:
        """config/kb-projection-mapping.yaml, checked against config/taxonomy.yaml."""
        from .. import sync
        return sync.load_mapping()

    def desired_state(self, conn, config: dict, **opts) -> dict:
        """sync.desired_state, with this connector's exclusions."""
        from .. import sync
        return sync.desired_state(conn, config, opts.get("source", "public"), exclusions=self.exclusions(conn))

    def exclusions(self, conn) -> tuple[bool, set]:
        """The owner-approved deletion's rule and deleted ids (0037)."""
        from .. import legacy_delete
        return legacy_delete.excluded(conn)

    def after_run(self, conn, out: dict) -> None:
        """The legacy rules (pipeline/kb_legacy.py), on every run. Once adopted
        (kb.legacy_archive has rows), the legacy step applies on every run;
        after `pipeline/kb_legacy.py restore` (which empties it) the sync stops
        re-archiving until the step is run again."""
        from .. import legacy as lg
        if conn.execute("select exists (select 1 from kb.legacy_archive)").fetchone()[0]:
            out["legacy"] = lg.archive(conn)
