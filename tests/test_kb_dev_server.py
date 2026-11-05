"""The local server takes the page's burst of module requests. Its listen queue
was socketserver's default of 5: the burst overflowed it, Windows refused the
connections, and a page intermittently stayed blank (found in the local
end-to-end run of 2026-11-05)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import kb_dev_server                                                   # noqa: E402


def test_listen_queue_holds_a_burst_of_module_requests():
    modules = sum(1 for _ in (Path(__file__).resolve().parent.parent / "public" / "kb" / "js").rglob("*.js"))
    assert kb_dev_server._Threaded.request_queue_size >= 2 * modules
