"""Protocol-level tests for the local directed-ideation MCP prototype."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
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
    PHASE_METHODS,
    Stage,
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
    ("tool", "get_lateral_thinking_guidance", {"context": "SENTINEL_PROBE"}),
    ("tool", "get_lateral_thinking_guidance", {"stage": "SENTINEL_PROBE"}),
    ("tool", "get_requirements_clarification_guidance", {"context": "SENTINEL_PROBE"}),
    ("tool", "get_requirements_clarification_guidance", {"stage": "SENTINEL_PROBE"}),
    ("tool", "get_strategic_thinking_guidance", {"context": "SENTINEL_PROBE"}),
    ("tool", "get_strategic_thinking_guidance", {"stage": "SENTINEL_PROBE"}),
    ("tool", "get_phase_guidance", {}),
    ("tool", "get_phase_guidance", {"phase": "SENTINEL_PROBE"}),
    (
        "tool",
        "get_phase_guidance",
        {"phase": "frame", "method": "SENTINEL_PROBE"},
    ),
    (
        "tool",
        "get_phase_guidance",
        {"phase": "frame", "method": "ooda-loop"},
    ),
    (
        "tool",
        "get_phase_guidance",
        {"phase": "frame", "extra": "SENTINEL_PROBE"},
    ),
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
        await boundary.on_call_tool(context, cast(Any, error_result))
        with pytest.raises(RuntimeError):
            await boundary.on_call_tool(context, cast(Any, exception))

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
        text(
            await client.call_tool(
                "get_phase_guidance", {"phase": "frame", "method": "cynefin"}
            )
        )
        text(await client.call_tool("get_lateral_thinking_guidance", {}))
        text(await client.call_tool("get_requirements_clarification_guidance", {}))
        text(await client.call_tool("get_strategic_thinking_guidance", {}))
        text(await client.call_tool("get_interview_guidance", {}))
        text(await client.call_tool("get_interview_guidance", {"stage": None}))
        text(
            await client.call_tool(
                "get_diagnostic_checks", {"stage": INTERVIEW_STAGES[1]}
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
        "get_phase_guidance": 1,
        "get_interview_guidance": 2,
        "get_diagnostic_checks": 1,
        "get_alternative_techniques": 0,
        "get_lateral_thinking_guidance": 1,
        "get_requirements_clarification_guidance": 1,
        "get_strategic_thinking_guidance": 1,
    }
    assert {
        k: after["stage_filters"][k] - v for k, v in before["stage_filters"].items()
    } == {
        "frame": 1,
        "diagnose": 1,
        "generate": 0,
        "evaluate": 0,
        "decide-and-stress-test": 0,
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
            "get_phase_guidance",
            "get_interview_guidance",
            "get_diagnostic_checks",
            "get_alternative_techniques",
            "get_lateral_thinking_guidance",
            "get_requirements_clarification_guidance",
            "get_strategic_thinking_guidance",
        }
        for tool in tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is False

        for no_arg_name in (
            "get_directed_ideation_method",
            "get_lateral_thinking_guidance",
            "get_requirements_clarification_guidance",
            "get_strategic_thinking_guidance",
        ):
            tool = next(t for t in tools if t.name == no_arg_name)
            assert tool.input_schema.get("additionalProperties") is False
            assert not tool.input_schema.get("properties")
            assert not tool.input_schema.get("required")

        phase_tool = next(t for t in tools if t.name == "get_phase_guidance")
        assert phase_tool.input_schema.get("additionalProperties") is False
        assert phase_tool.input_schema.get("required") == ["phase"]
        assert phase_tool.input_schema["properties"]["phase"]["enum"] == list(
            INTERVIEW_STAGES
        )
        assert "method" in phase_tool.input_schema["properties"]

        for name in _SUPPLEMENTARY_TOOLS:
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
    """The canonical tool returns the full five-phase method guidance."""

    async def check(client: Client) -> None:
        result = text(await client.call_tool("get_directed_ideation_method", {}))
        assert "# Directed Ideation — complete five-phase method" in result
        assert "Phase 1: Frame" in result
        assert "Phase 2: Diagnose" in result
        assert "Phase 3: Generate" in result
        assert "Phase 4: Evaluate" in result
        assert "Phase 5: Decide and stress-test" in result
        lower = result.lower()
        for phrase in (
            "confirm context",
            "one question at a time",
            "direction is a compass, not a track",
            "cynefin",
            "situation appraisal",
            "socratic questioning",
            "five whys",
            "current reality tree",
            "leverage points",
            "scamper",
            "synectics",
            "morphological",
            "triz",
            "toulmin",
            "pyramid principle",
            "analysis of competing hypotheses",
            "scenario planning",
            "six thinking hats",
            "decision analysis",
            "decision trees",
            "premortem",
            "fmea",
            "ooda",
            "do not invent evidence",
            "do not claim an",
            "ideas considered",
            "first action",
            "observable evidence",
            "do not execute actions",
            "do not send this record to the mcp service",
            "get_phase_guidance",
            "get_interview_guidance",
            "get_diagnostic_checks",
            "get_alternative_techniques",
            "get_lateral_thinking_guidance",
            "get_requirements_clarification_guidance",
            "get_strategic_thinking_guidance",
            "none of these is a phase of",
            "additional tools",
            "blockages",
            "william dettmer",
            "roger von oech",
            "edward de bono",
            "context-free",
        ):
            assert phrase in lower, f"Missing phrase in complete method: {phrase}"

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_phase_guidance_covers_all_phases_and_methods(transport: Transport) -> None:
    """Every phase and every bounded method selector returns focused guidance."""

    async def check(client: Client) -> None:
        for phase, methods in PHASE_METHODS.items():
            overview = text(
                await client.call_tool("get_phase_guidance", {"phase": phase})
            )
            for method_id, (label, _guidance) in methods.items():
                assert method_id in overview
                assert label in overview
                focused = text(
                    await client.call_tool(
                        "get_phase_guidance", {"phase": phase, "method": method_id}
                    )
                )
                assert label in focused
                assert method_id in focused
                assert "never send session context" in focused.lower()

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
@pytest.mark.parametrize("tool_name", _SUPPLEMENTARY_TOOLS)
def test_supplementary_menus(transport: Transport, tool_name: str) -> None:
    """Each supplementary tool returns compact menus with optional phase filter."""

    async def check(client: Client) -> None:
        for arguments in ({}, {"stage": None}):
            menu = text(await client.call_tool(tool_name, arguments))
            assert all(f"## {stage}\n" in menu for stage in INTERVIEW_STAGES)
            assert "get_phase_guidance" in menu
        unfiltered = text(await client.call_tool(tool_name, {}))
        for stage in INTERVIEW_STAGES:
            menu = text(await client.call_tool(tool_name, {"stage": stage}))
            title, sections = unfiltered.split("\n\n", 1)
            expected = next(
                part
                for part in sections.split("\n\n")
                if part.startswith(f"## {stage}\n")
            )
            assert menu == f"{title}\n\n{expected}"
            assert f"## {stage}\n" in menu
            assert all(
                f"## {other}\n" not in menu
                for other in INTERVIEW_STAGES
                if other != stage
            )

    run_check(transport, check)


@pytest.mark.parametrize(
    ("stage", "phrases"),
    [
        (
            "frame",
            ("recent, specific", "cynefin", "is / is not", "inferring", "best fit"),
        ),
        (
            "diagnose",
            ("root cause", "few factors", "core problem", "feedback loop", "leverage"),
        ),
        (
            "generate",
            ("how might we", "different mechanisms", "recombine", "conflict"),
        ),
        (
            "evaluate",
            ("grounds", "competing hypotheses", "plausible future", "tradeoffs"),
        ),
        (
            "decide-and-stress-test",
            ("must limits", "odds or payoffs", "premortem", "first action", "ooda"),
        ),
    ],
)
def test_interview_guidance_covers_five_phases(
    stage: Stage, phrases: tuple[str, ...]
) -> None:
    """Each phase menu offers that phase's core iterative questions."""
    from site_directedideation_com.mcp import get_interview_guidance

    menu = get_interview_guidance(stage).lower()
    assert all(phrase in menu for phrase in phrases if phrase)


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


def test_documented_tool_responses_match_implementation() -> None:
    """The checked-in reference captures the actual unfiltered responses."""
    from site_directedideation_com.mcp import (
        get_alternative_techniques,
        get_diagnostic_checks,
        get_directed_ideation_method,
        get_interview_guidance,
        get_lateral_thinking_guidance,
        get_phase_guidance,
        get_requirements_clarification_guidance,
        get_strategic_thinking_guidance,
    )

    reference = (
        Path(__file__).resolve().parents[1] / "docs/MCP_TOOL_RESPONSES.md"
    ).read_text()
    for tool in (
        get_directed_ideation_method,
        get_interview_guidance,
        get_diagnostic_checks,
        get_alternative_techniques,
        get_lateral_thinking_guidance,
        get_requirements_clarification_guidance,
        get_strategic_thinking_guidance,
    ):
        assert f"## `{tool.__name__}`\n\n```text\n{tool().rstrip()}\n```" in reference
    for phase in INTERVIEW_STAGES:
        assert (
            f'### `phase="{phase}"`\n\n```text\n'
            f"{get_phase_guidance(phase).rstrip()}\n```" in reference
        )


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_lateral_guidance_protocol(transport: Transport) -> None:
    """Exercise guidance is available over each protocol transport."""

    async def check(client: Client) -> None:
        result = text(
            await client.call_tool("get_lateral_thinking_guidance", {})
        ).lower()
        for phrase in (
            "additional tool separate from the core five-phase",
            "blockage encountered during the directed-ideation",
            "not a phase of directed",
            "thinking exercise",
            "one question at a time",
            "skip, stop",
            "edward de bono",
            "roger von oech",
            "mental locks",
            "second right answer",
            "artist",
            "judge",
            "warrior",
            "alternatives, possibilities, choices",
            "provocation",
            "reverse assumptions",
            "random stimulus",
            "perspective",
            "remove or exaggerate",
            "analogy",
            "useful principle",
            "user's direction",
            "private context",
        ):
            assert phrase in result

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_requirements_clarification_protocol(transport: Transport) -> None:
    """Six Sigma-inspired clarification guidance works over each transport."""

    async def check(client: Client) -> None:
        result = text(
            await client.call_tool("get_requirements_clarification_guidance", {})
        ).lower()
        for phrase in (
            "additional tool separate from the core",
            "not a phase of directed ideation",
            "clarifying exercise",
            "one question at a time",
            "skip, stop",
            "five whys",
            "voc to ctq",
            "sipoc",
            "ishikawa / fishbone",
            "operational definition",
            "lightweight fmea",
            "observations from assumptions",
            "active phase",
            "private context",
        ):
            assert phrase in result

    run_check(transport, check)


@pytest.mark.parametrize(
    "transport", ["memory", pytest.param("http", marks=pytest.mark.integration)]
)
def test_strategic_thinking_protocol(transport: Transport) -> None:
    """Dettmer, de Bono, and von Oech strategic guidance works over each transport."""

    async def check(client: Client) -> None:
        result = text(
            await client.call_tool("get_strategic_thinking_guidance", {})
        ).lower()
        for phrase in (
            "additional tool separate from the core",
            "not a phase of directed",
            "strategic exercise",
            "one question at a time",
            "skip, stop",
            "william dettmer",
            "logical thinking process",
            "goal tree",
            "current reality tree",
            "evaporating cloud",
            "future reality tree",
            "negative branch",
            "prerequisite tree",
            "transition tree",
            "categories of legitimate",
            "edward de bono",
            "six thinking hats",
            "consider all factors",
            "plus, minus, interesting",
            "alternatives, possibilities, choices",
            "roger von oech",
            "explorer",
            "artist",
            "judge",
            "warrior",
            "observations from assumptions",
            "active phase",
            "private",
        ):
            assert phrase in result

    run_check(transport, check)
