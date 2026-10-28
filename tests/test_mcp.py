"""Protocol-level tests for the local MCP capability probe."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import TextContent

from site_directedideation_com.mcp import INTERVIEW_STAGES, mcp

Transport = Literal["memory", "http"]
pytestmark = pytest.mark.mcp


@asynccontextmanager
async def probe_client(transport: Transport) -> AsyncGenerator[Client]:
    """Connect through the MCP protocol, with an OS-assigned HTTP port if needed."""
    if transport == "memory":
        async with Client(mcp._mcp_server) as client:
            yield client
        return

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        config = uvicorn.Config(mcp.http_app(), log_level="warning", access_log=False)
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if task.done():
                        await task
                        pytest.fail("HTTP probe exited before starting")
                    await asyncio.sleep(0.01)
            url = f"http://127.0.0.1:{port}/mcp"
            async with Client(streamable_http_client(url)) as client:
                yield client
        finally:
            server.should_exit = True
            try:
                async with asyncio.timeout(5):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)


def run_check(transport: Transport, check: Callable[[Client], Awaitable[None]]) -> None:
    """Run assertions inside the client lifetime to avoid teardown error groups."""

    async def run() -> None:
        async with probe_client(transport) as client:
            await check(client)

    asyncio.run(run())


def text(result) -> str:
    """Extract a successful single-text tool result."""
    assert not result.is_error
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    return result.content[0].text


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_probe_discovery_and_successful_calls(transport: Transport) -> None:
    """Both transports expose the prompt, read-only tools, and optional filter."""

    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {"hello_world", "interview_guidance"}
        tool = next(tool for tool in tools if tool.name == "interview_guidance")
        for discovered_tool in tools:
            assert discovered_tool.annotations is not None
            assert discovered_tool.annotations.read_only_hint is True
            assert discovered_tool.annotations.destructive_hint is False
            assert discovered_tool.annotations.idempotent_hint is True
            assert discovered_tool.annotations.open_world_hint is False
        assert tool.input_schema.get("additionalProperties") is False
        assert "stage" not in tool.input_schema.get("required", [])
        assert "stage" in tool.input_schema["properties"]

        prompts = (await client.list_prompts()).prompts
        prompt = next(prompt for prompt in prompts if prompt.name == "method_probe")
        assert not prompt.arguments
        result = await client.get_prompt("method_probe")
        assert len(result.messages) == 1
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "Ask the user exactly this question" in content.text
        assert "What would you like to explore? [method-probe]" in content.text

        assert text(await client.call_tool("hello_world", {})) == "Hello, world!"
        for arguments in ({}, {"stage": None}):
            menu = text(await client.call_tool("interview_guidance", arguments))
            assert all(stage in menu for stage in INTERVIEW_STAGES)
        for stage in INTERVIEW_STAGES:
            menu = text(await client.call_tool("interview_guidance", {"stage": stage}))
            assert stage in menu
            assert all(
                other not in menu for other in INTERVIEW_STAGES if other != stage
            )

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
@pytest.mark.parametrize(
    ("operation", "name", "arguments"),
    [
        ("tool", "interview_guidance", {"stage": "SENTINEL_PROBE"}),
        ("tool", "interview_guidance", {"SENTINEL_PROBE": "SENTINEL_PROBE"}),
        ("tool", "interview_guidance", {"stage": ["SENTINEL_PROBE"]}),
        ("tool", "interview_guidance", {"stage": {"x": "SENTINEL_PROBE"}}),
        ("tool", "interview_guidance", {"stage": 42}),
        ("tool", "hello_world", {"extra": "SENTINEL_PROBE"}),
        ("tool", "SENTINEL_PROBE", {}),
        ("prompt", "method_probe", {"extra": "SENTINEL_PROBE"}),
        ("prompt", "SENTINEL_PROBE", {}),
    ],
)
def test_rejected_inputs_do_not_echo_over_protocol(
    transport: Transport,
    operation: str,
    name: str,
    arguments: dict,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rejected values and names are absent from wire errors and captured logs."""
    caplog.set_level(logging.DEBUG)

    async def check(client: Client) -> None:
        with pytest.raises(MCPError) as error:
            if operation == "tool":
                await client.call_tool(name, arguments)
            else:
                await client.get_prompt(name, arguments)
        assert error.value.code == -32602
        assert "SENTINEL_PROBE" not in str(error.value)
        assert "Invalid probe parameters" in str(error.value)

    run_check(transport, check)
    # The caller controls client-side logs; the HTTP client logs its own outgoing
    # messages at DEBUG. Inspect service-side logs without hiding server DEBUG.
    service_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if not record.name.startswith("mcp.client")
    )
    assert "SENTINEL_PROBE" not in service_logs
    captured = capsys.readouterr()
    assert "SENTINEL_PROBE" not in captured.out + captured.err
