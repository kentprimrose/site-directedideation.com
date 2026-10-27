"""Local FastMCP development scaffold."""

from fastmcp import FastMCP

mcp = FastMCP("site-directedideation.com")


@mcp.tool
def hello_world() -> str:
    """Return a greeting."""
    return "Hello, world!"
