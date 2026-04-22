"""Smoke tests for the FastMCP server registration."""

from __future__ import annotations

from acuminator_mcp.server import mcp


async def test_expected_tools_are_registered() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {"analyze_project", "analyze_snippet", "get_diagnostic_docs"}


async def test_tool_descriptions_mention_acuminator() -> None:
    tools = await mcp.list_tools()
    for t in tools:
        assert t.description, f"Tool {t.name} has no description"
        assert "Acum" in t.description
