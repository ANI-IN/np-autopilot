"""M10 — the IK Knowledge Assistant plugin is well-formed and cannot drift.

`claude plugin validate plugins/ik-knowledge-assistant --strict` passed on
2026-11-02; these checks hold the same properties in CI without the CLI."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ik-knowledge-assistant"
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))


def test_the_bundled_server_is_byte_identical_to_the_canonical_one():
    assert (PLUGIN / "server" / "kb_server.py").read_bytes() == (REPO / "mcp_server" / "kb_server.py").read_bytes(), \
        "copy mcp_server/kb_server.py into the plugin (a plugin cannot reference files outside its root)"


def test_manifest_and_mcp_config():
    m = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", m["name"]) and m["version"]
    assert m["userConfig"]["kb_mcp_token"]["sensitive"] is True
    mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ik-kb"]
    assert mcp["args"] == ["${CLAUDE_PLUGIN_ROOT}/server/kb_server.py"]
    assert mcp["env"]["KB_MCP_TOKEN"] == "${user_config.kb_mcp_token}", "the token never lives in a file"
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert {"name": "ik-knowledge-assistant", "source": "./plugins/ik-knowledge-assistant"} in market["plugins"]


def test_skills_have_frontmatter_and_reference_only_real_tools():
    assert {p.parent.name for p in SKILLS} == {"ik-knowledge-search", "ik-course-audit"}
    src = (REPO / "mcp_server" / "kb_server.py").read_text(encoding="utf-8")
    tools = set(re.findall(r"@mcp\.tool\(\)\ndef (\w+)", src))
    for p in SKILLS:
        text = p.read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---")[1])
        assert front["name"] == p.parent.name and len(front["description"]) > 80
        called = set(re.findall(r"`(\w+)\(", text))
        assert called and called <= tools, f"{p.parent.name} names unknown tools: {called - tools}"


def test_skills_hold_no_copied_knowledge_or_contact_data():
    for p in SKILLS:
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@(?!example\.)[\w-]+\.\w+", text)
        assert "ikkb_" + "x" not in text


@pytest.mark.skipif(not shutil.which("claude"), reason="kb plugin: the claude CLI is not installed")
def test_claude_plugin_validate_strict():
    r = subprocess.run(["claude", "plugin", "validate", str(PLUGIN), "--strict"], capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0 and "Validation passed" in r.stdout, r.stdout + r.stderr
