"""The gap between Realtime's join and its subscription. After idle, Realtime
acknowledges the channel join seconds before it can deliver a change (2.7 s
measured locally). The page must keep polling fast until "Subscribed to
PostgreSQL", or a change made in the gap shows up to 20 s late. Found in the
local end-to-end run of 2026-11-05. A scripted socket, because a real cold
Realtime can't be produced on demand; tests/test_kb_realtime.py covers the real one.
"""
from __future__ import annotations

import json

import pytest

from kb_support import requires_kb
from test_kb_e2e import CONTEXTS, _data, page_as  # noqa: F401  (_data: the per-test reset)

pytest.importorskip("playwright.sync_api", reason="kb e2e: needs the playwright package")
from playwright.sync_api import sync_playwright                        # noqa: E402

pytestmark = [requires_kb]

SOCKET = """
window.WebSocket = class {
  constructor() { this.readyState = 0; window.__ws = this; setTimeout(() => { this.readyState = 1; this.onopen(); }, 0); }
  send(raw) {
    const m = JSON.parse(raw);
    if (m.event === 'phx_join') setTimeout(() => this.onmessage({ data: JSON.stringify(
      { event: 'phx_reply', topic: m.topic, ref: m.ref, payload: { status: 'ok' } }) }), 0);
  }
  close() {}
};
"""
SUBSCRIBED = json.dumps({"event": "system", "payload": {"extension": "postgres_changes", "status": "ok",
                                                        "message": "Subscribed to PostgreSQL"}})


@pytest.fixture(scope="module")
def server():
    from kb_support import dev_server
    with dev_server() as base:
        yield base + "/kb/"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(autouse=True)
def _close_pages():
    yield
    while CONTEXTS:
        CONTEXTS.pop().close()


def _scripted_socket(ctx):
    ctx.add_init_script(SOCKET)
    ctx.route("**/api/kb/realtime", lambda r: r.fulfill(json={"url": "http://127.0.0.1:9", "key": "k"}))


def test_polling_stays_fast_until_the_subscription_is_confirmed(server, browser):
    page = page_as(browser, server, "viewer", before=_scripted_socket)
    polls = []
    page.on("request", lambda r: "/api/kb/changes?since=" in r.url and polls.append(r.url))
    page.wait_for_timeout(9000)
    assert len(polls) >= 3, f"joined but not subscribed: {len(polls)} polls in 9 s, the fallback slowed too early"

    before = len(polls)
    page.evaluate("(m) => window.__ws.onmessage({ data: m })", SUBSCRIBED)
    page.wait_for_timeout(1000)
    assert len(polls) > before, "no fetch on subscribing: a change just before it would wait for the slow poll"

    settled = len(polls)
    page.wait_for_timeout(9000)
    assert len(polls) == settled, "subscribed, so polling should have slowed"
    assert page.errors == []
