"""Protocol-level tests for the local directed-ideation MCP prototype."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Literal, cast

import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import TextContent

from site_directedideation_com.mcp import (
    INTERVIEW_STAGES,
    _InputBoundary,
    aggregate_counts,
    mcp,
)

Transport = Literal["memory", "http"]
pytestmark = pytest.mark.mcp

_SUPPLEMENTARY_TOOLS = [
    "get_interview_guidance",
    "get_diagnostic_checks",
    "get_alternative_techniques",
]

_INVALID_STAGE_ARGUMENTS = [
    {"stage": "SENTINEL_PROBE"},
    {"stage": ["SENTINEL_PROBE"]},
    {"stage": {"x": "SENTINEL_PROBE"}},
    {"stage": 42},
]

_EXTRA_CONTEXT_ARGUMENTS = [
    {"context": "SENTINEL_PROBE"},
]

_REJECTED_INPUT_CASES = [
    ("tool", "get_directed_ideation_method", {"extra": "SENTINEL_PROBE"}),
    *[
        ("tool", tool, args)
        for tool in _SUPPLEMENTARY_TOOLS
        for args in _INVALID_STAGE_ARGUMENTS + _EXTRA_CONTEXT_ARGUMENTS
    ],
    ("tool", "SENTINEL_PROBE", {}),
    ("prompt", "method_probe", {}),
    ("prompt", "method_probe", {"extra": "SENTINEL_PROBE"}),
    ("prompt", "SENTINEL_PROBE", {}),
]


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


def test_tool_failures_do_not_increment_counts() -> None:
    """Both exceptions and explicit error results are excluded."""
    before = aggregate_counts()
    context = cast(
        Any,
        SimpleNamespace(
            message=SimpleNamespace(name="get_interview_guidance", arguments={})
        ),
    )

    async def error_result(_context):
        return SimpleNamespace(is_error=True)

    async def exception(_context):
        raise RuntimeError("failure")

    async def check() -> None:
        boundary = _InputBoundary()
        await boundary.on_call_tool(context, error_result)
        with pytest.raises(RuntimeError):
            await boundary.on_call_tool(context, exception)

    asyncio.run(check())
    assert aggregate_counts() == before


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_aggregate_counts_are_bounded_and_exclude_rejections(
    transport: Transport,
) -> None:
    """Only bounded successful calls affect the independent aggregate totals."""
    before = aggregate_counts()

    async def check(client: Client) -> None:
        text(await client.call_tool("get_directed_ideation_method", {}))
        text(await client.call_tool("get_interview_guidance", {}))
        text(await client.call_tool("get_interview_guidance", {"stage": None}))
        text(
            await client.call_tool(
                "get_diagnostic_checks", {"stage": INTERVIEW_STAGES[0]}
            )
        )
        for operation, name, arguments in _REJECTED_INPUT_CASES:
            with pytest.raises(MCPError):
                if operation == "tool":
                    await client.call_tool(name, arguments)
                else:
                    await client.get_prompt(name, cast(Any, arguments))

    run_check(transport, check)
    after = aggregate_counts()
    assert {k: after["tools"][k] - v for k, v in before["tools"].items()} == {
        "get_directed_ideation_method": 1,
        "get_interview_guidance": 2,
        "get_diagnostic_checks": 1,
        "get_alternative_techniques": 0,
    }
    assert {
        k: after["stage_filters"][k] - v for k, v in before["stage_filters"].items()
    } == {
        INTERVIEW_STAGES[0]: 1,
        INTERVIEW_STAGES[1]: 0,
        INTERVIEW_STAGES[2]: 0,
        "unfiltered": 2,
    }
    assert "SENTINEL_PROBE" not in repr(after)
    after["tools"].clear()
    assert aggregate_counts()["tools"]


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_discovery_and_annotations(transport: Transport) -> None:
    """Both transports expose only the canonical tools and expected annotations."""

    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {
            "get_directed_ideation_method",
            "get_interview_guidance",
            "get_diagnostic_checks",
            "get_alternative_techniques",
        }
        for tool in tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is False

        method_tool = next(
            tool for tool in tools if tool.name == "get_directed_ideation_method"
        )
        assert method_tool.input_schema.get("additionalProperties") is False
        assert not method_tool.input_schema.get("properties")
        assert not method_tool.input_schema.get("required")

        for name in {
            "get_interview_guidance",
            "get_diagnostic_checks",
            "get_alternative_techniques",
        }:
            tool = next(t for t in tools if t.name == name)
            assert tool.input_schema.get("additionalProperties") is False
            assert "stage" in tool.input_schema["properties"]
            assert "stage" not in tool.input_schema.get("required", [])
            stage_schema = tool.input_schema["properties"]["stage"]
            assert any(
                sub.get("enum") == list(INTERVIEW_STAGES)
                for sub in stage_schema.get("anyOf", [])
            )
        prompts = (await client.list_prompts()).prompts
        assert prompts == []

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_complete_method(transport: Transport) -> None:
    """The canonical tool returns the full three-stage method guidance."""

    async def check(client: Client) -> None:
        result = text(await client.call_tool("get_directed_ideation_method", {}))
        assert "# Directed Ideation — complete method" in result
        assert "Stage 1: Identify opportunities" in result
        assert "Stage 2: Select goals" in result
        assert "Stage 3: Ideate with purpose" in result
        assert "confirm context" in result.lower()
        assert "one question at a time" in result.lower()
        assert "confirm it" in result.lower()
        assert "confirm or revise it" in result.lower()
        assert "First action" in result
        assert "Observable evidence" in result
        assert "Do not execute actions" in result
        assert "Do not send this record to the MCP service" in result
        assert "Optional supplementary guidance" in result
        assert "Use the complete method and your own capabilities first" in result
        assert "user explicitly requests" in result.lower()
        assert "explicitly instructs" in result.lower()
        assert "a routine step" in result.lower()
        assert "not fetch it merely because you think" in result.lower()
        assert "get_interview_guidance" in result
        assert "get_diagnostic_checks" in result
        assert "get_alternative_techniques" in result
        assert "context-free" in result
        assert "no session content" in result.lower()
        assert "does not track or store session state" in result.lower()
        assert "not advertised" in result.lower()
        assert "callable operation" in result.lower()

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
@pytest.mark.parametrize(
    "tool_name",
    [
        "get_interview_guidance",
        "get_diagnostic_checks",
        "get_alternative_techniques",
    ],
)
def test_supplementary_menus(transport: Transport, tool_name: str) -> None:
    """Each supplementary tool returns compact menus with optional stage filter."""

    async def check(client: Client) -> None:
        for arguments in ({}, {"stage": None}):
            menu = text(await client.call_tool(tool_name, arguments))
            assert all(stage in menu for stage in INTERVIEW_STAGES)
            assert "not yet implemented" in menu.lower()
            assert "not advertised" in menu.lower()
        for stage in INTERVIEW_STAGES:
            menu = text(await client.call_tool(tool_name, {"stage": stage}))
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
    _REJECTED_INPUT_CASES,
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
        assert "Invalid parameters" in str(error.value)

    run_check(transport, check)
    service_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if not record.name.startswith("mcp.client")
    )
    assert "SENTINEL_PROBE" not in service_logs
    captured = capsys.readouterr()
    assert "SENTINEL_PROBE" not in captured.out + captured.err
