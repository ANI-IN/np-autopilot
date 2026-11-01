"""The knowledge-base workspace: authored records in the `kb` schema.

`service` is the ONE module that holds KB business logic. The HTTP routes
(api/kb_routes.py) and the MCP server (mcp_server/kb_server.py) both call it;
neither validates, checks permissions or writes SQL of its own.
"""
