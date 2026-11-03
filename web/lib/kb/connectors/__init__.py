"""The sources the sync engine (web/lib/kb/sync.py) can run: name -> connector.
The interface is connectors/base.py; docs/ARCHITECTURE.md, "Connectors",
says how a new source plugs in."""
from __future__ import annotations

from .base import Connector
from .np_autopilot import NpAutopilot

DEFAULT = NpAutopilot.name

REGISTRY: dict[str, Connector] = {}


def register(connector: Connector) -> Connector:
    """Add a connector under its name (a name is taken once)."""
    if not connector.name:
        raise ValueError("a connector needs a name")
    if connector.name in REGISTRY and REGISTRY[connector.name] is not connector:
        raise ValueError(f"a connector named {connector.name!r} is already registered")
    REGISTRY[connector.name] = connector
    return connector


def get(name: str = DEFAULT) -> Connector:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"no connector named {name!r} (known: {', '.join(sorted(REGISTRY))})") from None


def names() -> list[str]:
    return sorted(REGISTRY)


register(NpAutopilot())

__all__ = ["Connector", "NpAutopilot", "DEFAULT", "REGISTRY", "register", "get", "names"]
