"""Local-only MCP capability probe, not the hosted ideation service."""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.shared.exceptions import MCPError

Stage = Literal["identify-opportunities", "select-goals", "ideate-with-purpose"]
INTERVIEW_STAGES: tuple[Stage, ...] = (
    "identify-opportunities",
    "select-goals",
    "ideate-with-purpose",
)
READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

mcp = FastMCP("site-directedideation.com", mask_error_details=True)


class _ProbeInputBoundary(Middleware):
    """Validate the probe's small allowlist before value-echoing SDK validation.

    This is deliberately not a general JSON Schema validator. New operations
    must extend this allowlist and its tests. It does not harden HTTP envelopes,
    ingress, or production telemetry.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        message = context.message
        arguments = message.arguments or {}
        if message.name == "hello_world":
            valid = not arguments
        elif message.name == "interview_guidance":
            stage = arguments.get("stage")
            valid = set(arguments) <= {"stage"} and (
                stage is None or (isinstance(stage, str) and stage in INTERVIEW_STAGES)
            )
        else:
            valid = False
        if not valid:
            raise MCPError(code=-32602, message="Invalid probe parameters")
        return await call_next(context)

    async def on_get_prompt(self, context: MiddlewareContext, call_next):
        message = context.message
        if message.name != "method_probe" or message.arguments:
            raise MCPError(code=-32602, message="Invalid probe parameters")
        return await call_next(context)


mcp.add_middleware(_ProbeInputBoundary())


@mcp.tool(annotations=READ_ONLY)
def hello_world() -> str:
    """Return a greeting."""
    return "Hello, world!"


@mcp.tool(annotations=READ_ONLY)
def interview_guidance(stage: Stage | None = None) -> str:
    """Get a compact menu of interview approaches, optionally filtered by stage.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the guidance to conversation context locally;
    never send that context here. Detailed guidance is not implemented yet.

    Args:
        stage: Optional guidance filter, not a report of session progress.
    """
    guidance = {
        "identify-opportunities": (
            "Concrete incident: ask for an observed instance of recurring friction, "
            "then distinguish observation from assumptions. "
            "Detail placeholder: not yet implemented."
        ),
        "select-goals": (
            "Outcome clarification: ask what observable improvement would matter, "
            "then help synthesize one goal for the user's confirmation. "
            "Detail placeholder: not yet implemented."
        ),
        "ideate-with-purpose": (
            "Constraint provocation: ask what different approaches could work with "
            "no new software; relate each to the confirmed goal and identify "
            "a first action and observable evidence. "
            "Detail placeholder: not yet implemented."
        ),
    }
    stages = INTERVIEW_STAGES if stage is None else (stage,)
    return "Interview guidance menu:\n" + "\n".join(
        f"- {key}: {guidance[key]}" for key in stages
    )


@mcp.prompt()
def method_probe() -> str:
    """Test explicit MCP prompt invocation without accepting session context."""
    return (
        "This is a capability probe, not the complete directed-ideation method. "
        "Ask the user exactly this question, then wait for their answer: "
        "What would you like to explore? [method-probe]"
    )
