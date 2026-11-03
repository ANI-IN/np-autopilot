"""Run 6 (G4): the sync behind a connector interface (web/lib/kb/connectors).
No behaviour change: tests/test_kb_sync.py, test_kb_legacy_delete.py,
test_kb_propagation.py and test_kb_one_validation.py run unchanged against the
default call. Here: the registry, the explicit NP Autopilot connector giving
the same result as the default, and a fake second source written through the
same engine path. Synthetic source (tests/test_kb_sync.py's `kbsync_src`): no
real data."""
from __future__ import annotations

import json
from collections import defaultdict

import psycopg
import pytest

from kb_support import USERS, owner, requires_kb, reset, session_dsn
from test_kb_sync import _setup, kb_count, rec, sync  # noqa: F401  (_setup: the synthetic source per test)

pytestmark = requires_kb
ADMIN = USERS["admin"]
SUMMARY = ("status", "partial", "created", "updated", "unchanged", "conflicts", "removed_at_source",
           "restored_at_source", "adopted", "skipped_archived", "conflicts_cleared", "errors", "report")


def _summary(out: dict) -> str:
    """The result without what differs between any two runs (run id, seconds)."""
    return json.dumps({k: out.get(k) for k in SUMMARY}, sort_keys=True, default=str)


def _clear_kb():
    """As test_kb_sync's fixture does between tests: the KB as before any run."""
    reset()
    with owner() as c:
        c.execute("truncate kb.sync_map, kb.sync_runs, kb.legacy_archive, kb.person_accounts")


def test_the_registry_returns_the_np_autopilot_connector():
    from lib.kb import connectors
    from lib.kb.connectors.base import Connector
    c = connectors.get("np_autopilot")
    assert isinstance(c, Connector) and isinstance(c, connectors.NpAutopilot)
    assert c.name == connectors.DEFAULT == "np_autopilot"
    assert c.actor_label == "Sync (NP Autopilot)"
    assert connectors.get() is c and "np_autopilot" in connectors.names()
    with pytest.raises(KeyError):
        connectors.get("kbtest-no-such-source")
    with pytest.raises(ValueError):
        connectors.register(connectors.NpAutopilot())        # a name is taken once


def test_the_explicit_connector_gives_the_same_result_as_the_default():
    from lib.kb import connectors
    default = sync()
    assert default["status"] == "ok" and default["created"]
    default_again = sync()
    _clear_kb()
    explicit = sync(connector=connectors.get("np_autopilot"))
    explicit_again = sync(connector=connectors.get("np_autopilot"))
    assert _summary(explicit) == _summary(default)
    assert _summary(explicit_again) == _summary(default_again)
    assert explicit_again["created"] == {} and explicit_again["updated"] == {} and explicit_again["conflicts"] == {}


class _FakeSource:
    """A second source: one record, its own (empty) configuration, no
    exclusions and no finishing step. Defined in the test only."""

    @staticmethod
    def make():
        from lib.kb.connectors.base import Connector

        class Fake(Connector):
            name = "kbtest_fake"
            actor_label = "Sync (kbtest fake)"
            calls: list = []

            def load_config(self, conn):
                self.calls.append("load_config")
                return {"new_record_types": [], "new_relationship_types": [], "type_fields": {}, "placement": {}}

            def desired_state(self, conn, config, **opts):
                self.calls.append("desired_state")
                r = {"np": "kbfake_1", "type": "topic", "src_type": "kbtest", "name": "Kbfake Topic One", "props": {},
                     "body": None, "scope_np": None, "legacy": False, "review": False, "tags": [],
                     "owner_np": None, "co_np": []}
                return {"recs": {"kbfake_1": r}, "links": {}, "rels": {}, "attachments": {}, "layout": {},
                        "report": {"read": {"items": 1}, "rejected": [], "problems": defaultdict(list)}}

            def after_run(self, conn, out):
                self.calls.append("after_run")
                out["kbtest_finished"] = True
        return Fake()


def test_a_second_connector_writes_through_the_same_engine():
    from lib.kb import connectors, sync as engine
    fake = connectors.register(_FakeSource.make())
    try:
        assert connectors.get("kbtest_fake") is fake
        with psycopg.connect(session_dsn()) as conn:
            out = engine.run(conn, trigger="cli", actor_id=ADMIN, connector=fake)
        assert out["status"] == "ok", out
        assert fake.calls == ["load_config", "desired_state", "after_run"]
        assert out["kbtest_finished"] is True and "legacy" not in out
        assert out["created"] == {"record: topic": 1}
        r = rec("kbfake_1")
        assert r is not None and r["name"] == "Kbfake Topic One" and r["legacy"] is False
        assert kb_count("sync_map", "unit = 'record' and key = 'kbfake_1'") == 1
        with owner() as c:
            assert c.execute("select count(*) from kb.audit_log where actor_type = 'sync' and table_name = 'nodes'").fetchone()[0] >= 1
        # the same diff: a second run writes nothing
        with psycopg.connect(session_dsn()) as conn:
            again = engine.run(conn, trigger="cli", actor_id=ADMIN, connector=fake)
        assert again["created"] == {} and again["updated"] == {} and again["unchanged"] == {"record": 1}
    finally:
        connectors.REGISTRY.pop("kbtest_fake", None)
    assert "kbtest_fake" not in connectors.names()
