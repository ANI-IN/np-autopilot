"""The router imports an endpoint's module when it serves it, not before.

Importing all eleven endpoint modules at load meant a cold start serving
/api/overview also paid for `session` -> `gotrue` -> `urllib.request` and for
the curation service. Measured: 80.9 ms of import, down to 56.2 ms.

THE GUARD PROPERTY IS WHAT MUST NOT CHANGE. `api/index.py` says there is no
route that can forget the guard, because `_serve_read` is the only path from a
request to a connection and it calls identify() unconditionally. Loading a
module later must not give it a way to register its own front door — so the
table is a set of NAMES and the loader is one function, asserted below.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
API = REPO / "api"


@pytest.fixture(scope="module")
def index():
    sys.path.insert(0, str(REPO / "web"))
    sys.path.insert(0, str(API))
    import index as mod
    return mod


def test_every_route_name_matches_its_module(index):
    """A mismatch is a silent 404 on a route that looks present."""
    for path in sorted(index.READS | index.WRITES):
        name, fn = index.endpoint_for(path)
        assert name == path[len("/api/"):]
        assert callable(fn)


def test_a_mismatched_endpoint_name_is_refused(index, tmp_path, monkeypatch):
    """The failure must be loud at the route, not a 404 nobody explains."""
    bogus = tmp_path / "wrongname.py"
    bogus.write_text('ENDPOINT = ("not_wrongname", lambda *a: (None, 0))\n',
                     encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    index._ENDPOINTS.pop("wrongname", None)
    with pytest.raises(RuntimeError, match="would 404"):
        index.endpoint_for("/api/wrongname")


def test_importing_the_router_does_not_load_the_endpoint_modules():
    """The point of the change, asserted in a FRESH interpreter — the module
    cache in this one would hide it."""
    code = (
        "import sys;"
        f"sys.path.insert(0, {str(REPO / 'web')!r});"
        f"sys.path.insert(0, {str(API)!r});"
        "import index;"
        "print(','.join(sorted(m for m in "
        "('overview','search','session','curate','node','structure','staffing')"
        " if m in sys.modules)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(REPO))
    assert out.returncode == 0, out.stderr[-500:]
    loaded = [m for m in out.stdout.strip().split(",") if m]
    assert not loaded, f"these loaded at import and should not have: {loaded}"


def test_serving_a_route_loads_only_that_module():
    code = (
        "import sys;"
        f"sys.path.insert(0, {str(REPO / 'web')!r});"
        f"sys.path.insert(0, {str(API)!r});"
        "import index;"
        "index.endpoint_for('/api/overview');"
        "print('overview' in sys.modules, 'session' in sys.modules,"
        "      'curate' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(REPO))
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "True False False", out.stdout


def test_identify_is_still_called_before_the_module_is_loaded():
    """Lazy loading must not move the guard. In `_serve_read`, identify()
    must appear BEFORE endpoint_for()."""
    src = (API / "index.py").read_text(encoding="utf-8")
    body = src[src.index("def _serve_read"):]
    body = body[:body.index("\ndef ")]
    assert "identify(" in body and "endpoint_for(" in body
    assert body.index("identify(") < body.index("endpoint_for("), (
        "the endpoint module is loaded before the caller is identified")


def test_there_is_still_exactly_one_loader():
    """A second import path is a second front door."""
    src = (API / "index.py").read_text(encoding="utf-8")
    assert src.count("def endpoint_for") == 1
    assert "importlib.import_module" in src
    assert src.count("importlib.import_module") == 1
