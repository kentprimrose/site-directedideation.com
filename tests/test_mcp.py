"""Tests for the FastMCP server."""

import asyncio

from mcp.types import TextContent

from site_directedideation_com.mcp import mcp


def test_hello_world_tool_returns_greeting() -> None:
    """The hello_world tool returns the shared greeting."""
    result = asyncio.run(mcp.call_tool("hello_world"))

    assert not result.is_error
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, TextContent)
    assert content.text == "Hello, world!"
