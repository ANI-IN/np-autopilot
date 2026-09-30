"""The local review stub can never reach production (owner requirement, 2026-09-30).

eval/local_server.py signs a browser in as a local stub user and replaces
`guard.identify`. That is only acceptable because it cannot ship:

  1. the files a deploy UPLOADS (tracked files minus .vercelignore, by git's
     own matcher — the set db/window/build_artifact.sh builds from) carry no
     stub marker, no placeholder config and no identity bypass;
  2. the deploy check (db/window/check_function_map.py) FAILS an artifact that
     would upload one — shown on a synthetic artifact, so the check is proven
     to bite, not just to pass;
  3. the real app, with no stub, answers every data route 401 with its own
     body — with no session, and with the stub's own token.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHECK = _load("np_check_function_map", "db/window/check_function_map.py")
STUB = REPO / "eval" / "local_server.py"


def _tracked() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True,
                         text=True, check=True).stdout.splitlines()
    return [f for f in out if (REPO / f).is_file()]


def test_the_stub_lives_only_where_the_upload_excludes_it():
    text = STUB.read_text(encoding="utf-8")
    assert any(rx.search(text) for rx in CHECK.STUB_PATTERNS), \
        "positive control: the stub must carry what the check looks for"
    assert "eval/local_server.py" in CHECK.excluded_by(REPO / ".vercelignore",
                                                        ["eval/local_server.py"])


def test_nothing_the_deploy_uploads_carries_the_stub():
    files = _tracked()
    gone = set(CHECK.excluded_by(REPO / ".vercelignore", files))
    uploaded = [f for f in files if f not in gone]
    assert "public/index.html" in uploaded and "api/index.py" in uploaded
    assert CHECK.stub_hits(REPO, uploaded) == []


@pytest.mark.parametrize("where,content", [
    ("web/lib/local_server.py", None),                     # the stub, copied in
    ("api/extra.py", "from lib import guard\nguard.identify = lambda h: None\n"),
    ("public/index.html", "<head><script>/* NP-LOCAL-PREVIEW-STUB */</script>"),
])
def test_the_deploy_check_fails_an_artifact_that_would_ship_it(tmp_path, where, content):
    shutil.copy(REPO / ".vercelignore", tmp_path / ".vercelignore")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "index.py").write_text("# the real app\n")
    target = tmp_path / where
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content if content is not None else STUB.read_text(encoding="utf-8"))
    assert CHECK.stub_hits(tmp_path), f"{where} would have shipped the stub unnoticed"


def test_the_stub_under_eval_is_not_uploaded_even_in_an_artifact(tmp_path):
    shutil.copy(REPO / ".vercelignore", tmp_path / ".vercelignore")
    (tmp_path / "eval").mkdir()
    shutil.copy(STUB, tmp_path / "eval" / "local_server.py")
    assert CHECK.stub_hits(tmp_path) == []


def test_the_real_routes_refuse_without_a_session():
    """A fresh interpreter with NO stub and no database configured: every
    data route is 401 with the app's own body, for no token and for the
    stub's token."""
    code = r"""
import io, json, sys
sys.path[:0] = ['.', 'web', 'api']
import index as app
out = {}
for name in app.READ_NAMES:
    for auth in (None, 'Bearer local-preview'):
        env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/' + name, 'QUERY_STRING': '',
               'wsgi.input': io.BytesIO(b''), 'SERVER_NAME': 'x', 'SERVER_PORT': '443',
               'wsgi.url_scheme': 'https'}
        if auth: env['HTTP_AUTHORIZATION'] = auth
        got = {}
        body = b''.join(app.app(env, lambda s, h: got.update(s=s)))
        out[name + ('+stub' if auth else '')] = [got['s'][:3], json.loads(body).get('error')]
print(json.dumps(out))
"""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "SYSTEMROOT") if k in os.environ}
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got and all(v == ["401", "unauthorised"] for v in got.values()), got


def test_the_browser_half_runs_before_the_pages_own_gate():
    stub = _load("np_local_server_for_test", "eval/local_server.py")
    page = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    served = page.replace("<head>", "<head>" + stub.preview_script(page), 1)
    assert served.index(stub.MARKER) < served.index("sessionKey"), \
        "the stub session must be stored before the page's sign-in gate reads it"
    assert json.dumps("np_session") in stub.preview_script(page), \
        "the stub must use the page's own storage key"
    assert "LOCAL PREVIEW, not production" in stub.preview_script(page)
