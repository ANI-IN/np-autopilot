"""The connector interface: what a source must give the one sync engine
(web/lib/kb/sync.py `run`). The engine does the rest, unchanged for every
source: the lock, the run log, the diff against kb.sync_map, the batched
phases (records -> owners -> links -> relationships -> attachments ->
removed), conflicts (an app edit is never overwritten), "removed at source",
the time budget and resume, the layout, and the attribution to actor_type
'sync'.

Today only NP Autopilot (connectors/np_autopilot.py) implements it, and the
interface holds exactly the steps that sync performs. docs/VISION_AND_ROADMAP.md
§3 describes where it goes next.

NOT part of the interface yet (a future connector such as Google Drive,
Uplevel LMS or Atlassian will need them; nothing here implements them):
  - an incremental CURSOR: today every run rebuilds the full desired state and
    the engine diffs it from scratch. A connector with a change feed (Drive's
    startPageToken) would add `changes(conn, cursor) -> (items, new_cursor)`,
    stored per connector (a kb.connectors table: a migration);
  - source PERMISSIONS: `acl(items) -> {source_key: [principal]}`, so a record
    is visible in the KB only to who may see it at the source (kb.source_acl);
  - RETRIES and back-off for a source API (rate limits, 5xx), and a job queue.
    Today a failed run is recorded in kb.sync_runs and the next one starts over;
  - NAMESPACING: kb.sync_map, kb.sync_runs and kb.sync_exclusions have no
    `source` column, the external id prefix is 'np:' and there is one lock
    (sync.LOCK_KEY). Two connectors writing to the same database would see each
    other's units as "removed at source". Roadmap item 4 adds the column (an
    additive migration) before a second connector runs for real.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Connector(ABC):
    """One source of KB records. Subclass it and register an instance
    (connectors.register)."""

    #: The registry key ('np_autopilot'; later e.g. 'gdrive').
    name: str = ""
    #: How Activity names the writes of this source.
    actor_label: str = ""

    @abstractmethod
    def load_config(self, conn) -> dict:
        """The source's mapping, checked against config/taxonomy.yaml (raise on
        a bad one: the run is then recorded as failed). The engine reads these
        keys from it to create the KB configuration the source needs
        (sync.ensure_config): `new_record_types`, `new_relationship_types`,
        `type_fields`, `placement` (each may be empty)."""

    @abstractmethod
    def desired_state(self, conn, config: dict, **opts) -> dict:
        """What the KB should hold for this source, with the source's own
        rules applied (what is current, what is legacy, who owns what, and
        the exclusions). Returns a dict with:
          recs         {key: {"np", "type", "src_type", "name", "props", "body",
                              "scope_np", "legacy", "review", "tags",
                              "owner_np", "co_np"}}   ("np" is the source key)
          links        {url_norm: {"url", "title", "kind", "tags"}}
          rels         {key: {"type", "src", "tgt", "props", "note", "edges"}}
          attachments  {key: {"rec", "link", "note"}}
          layout       {source key: (x, y)}
          report       {"read": {...}, "rejected": [...], "problems": defaultdict(list), ...}
        `opts` are the run's source options (today: `source`, the schema of the
        old tables)."""

    def exclusions(self, conn) -> tuple[bool, set]:
        """(rule on?, source keys never to create again): the permanent
        exclusions (kb.sync_exclusions) the connector applies while building
        its desired state. Default: none."""
        return False, set()

    def after_run(self, conn, out: dict) -> None:
        """The source's finishing step, inside the run's last transaction
        (never cut off by the time budget). It may add keys to `out`.
        Default: nothing."""
        return None
