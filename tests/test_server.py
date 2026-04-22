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


async def test_every_tool_carries_standard_annotations() -> None:
    """All tools are read-only + non-destructive + idempotent + open-world."""
    tools = await mcp.list_tools()
    for t in tools:
        ann = t.annotations
        assert ann is not None, f"Tool {t.name} has no annotations"
        assert ann.readOnlyHint is True
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True
        assert ann.openWorldHint is True
