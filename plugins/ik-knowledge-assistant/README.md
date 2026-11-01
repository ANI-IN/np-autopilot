# IK Knowledge Assistant (Claude Code plugin)

Bundles the `ik-kb` MCP server and two skills:

- `ik-knowledge-search`: answer questions from the live KB and add or connect records on request.
- `ik-course-audit`: completeness, link and duplicate audit of a course or program.

Install from this repo's marketplace, then supply the two prompted values (KB URL
and your personal API token from the KB app → Settings → API tokens). Needs
Python 3.12+ with `mcp` and `httpx` (`pip install mcp==1.30.0 httpx==0.28.1`).

`server/kb_server.py` is a copy of `mcp_server/kb_server.py` (a plugin cannot
reference files outside its own root). `tests/test_kb_plugin.py` fails if the
two differ. See docs/MCP.md for behaviour and security.
