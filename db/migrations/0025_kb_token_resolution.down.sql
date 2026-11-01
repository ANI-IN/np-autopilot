-- Reverses 0025. MCP clients then need the direct-database mode again.
revoke execute on function kb.resolve_token(text) from authenticated;
