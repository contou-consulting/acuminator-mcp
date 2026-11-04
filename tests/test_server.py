"""Smoke tests for the FastMCP server registration."""

from __future__ import annotations

from acuminator_mcp.server import mcp


async def test_expected_tools_are_registered() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {"analyze_project", "analyze_snippet", "generate_suppressions", "get_diagnostic_docs"}


async def test_tool_descriptions_mention_acuminator() -> None:
    tools = await mcp.list_tools()
    for t in tools:
        assert t.description, f"Tool {t.name} has no description"
        assert "Acum" in t.description


async def test_tools_do_not_ship_an_output_schema() -> None:
    """structured_output=False keeps the per-session tool definitions small."""
    tools = await mcp.list_tools()
    for t in tools:
        assert t.outputSchema is None, f"Tool {t.name} has an outputSchema"


async def test_every_tool_carries_annotations() -> None:
    """All tools are idempotent + open-world; only generate_suppressions writes."""
    tools = await mcp.list_tools()
    for t in tools:
        ann = t.annotations
        assert ann is not None, f"Tool {t.name} has no annotations"
        writes = t.name == "generate_suppressions"
        assert ann.readOnlyHint is (not writes), t.name
        assert ann.destructiveHint is writes, t.name
        assert ann.idempotentHint is True
        assert ann.openWorldHint is True
    gen = next(t for t in tools if t.name == "generate_suppressions")
    assert gen.description.startswith("WRITES FILES")
