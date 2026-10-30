"""Local-only directed-ideation MCP prototype, not the hosted service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.shared.exceptions import MCPError

from site_directedideation_com.metrics import connect, increment, snapshot

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


@asynccontextmanager
async def _lifespan(server):
    """Fail startup if aggregate metrics cannot be configured and written."""
    try:
        connection = connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO counters VALUES (?, ?, 0) "
                "ON CONFLICT(dimension, name) DO UPDATE SET count = count",
                ("tools", "get_directed_ideation_method"),
            )
            connection.rollback()
        finally:
            connection.close()
    except Exception as exc:
        raise RuntimeError(f"MCP metrics startup validation failed: {exc}") from exc
    yield


mcp = FastMCP("site-directedideation.com", mask_error_details=True, lifespan=_lifespan)


_COMPLETE_METHOD = """\
# Directed Ideation — complete method

Use this method when the user explicitly asks for directed ideation or agrees to
try it. Do not start the method without the user's request. All session context
stays with the calling agent; this tool returns only reusable guidance.

## Before you begin: confirm context

1. Review the conversation context you already hold. Synthesize the user's
   challenge, situation, or desired outcome in one sentence.
2. Present that synthesis to the user and ask them to confirm or revise it.
   Example: "It sounds like you're trying to [outcome] in [context]. Is that
   right, or is there a better way to put it?"
3. If you have no relevant context, ask: "What would you like to explore?" Wait
   for the answer before continuing.

## Stage 1: Identify opportunities (observe)

Goal: find one concrete, evidence-based opportunity to work on.

- Ask one question at a time. Default pace is a single question; only ask a
  small group of related questions if the user asks for a faster format.
- Start with concrete observation: "Describe one recent instance where this
  friction showed up."
- Use the field-guide prompts:
  - Friction: What do people keep doing despite the inconvenience?
  - Change: What can people do now that they could not do a year ago?
  - Perspective: Whose experience have we not examined?
- Help the user capture observations as needs or tensions, not as solutions.
  Example: "New team members cannot tell which decision is current," not "We
  need a new dashboard."
- When the user names more than one opportunity, briefly list them and ask which
  one to focus on first. Do not decide for the user.
- Before leaving this stage, state the chosen opportunity and ask the user to
  confirm it. Example: "The opportunity we're focusing on is [description]. Is
  that the right framing?"

## Stage 2: Select goals (decide)

Goal: choose one worthwhile, testable goal tied to the confirmed opportunity.

- Use the four criteria from the field guide:
  - Value: Who would benefit, and how much would their experience improve?
  - Evidence: What have you observed? What assumption still needs testing?
  - Agency: What can you change with the time, access, and resources available?
  - Learning: Can a small experiment reveal whether this is worth a larger
    effort?
- Ask one question at a time. Synthesize the user's answers into the goal
  formula:
  "Help [specific people] achieve [valuable outcome] in [context], while
  respecting [key constraint]."
- Present the synthesized goal and ask the user to confirm or revise it. Do not
  advance until the user confirms.

## Stage 3: Ideate with purpose (create)

Goal: generate multiple actionable ideas, each tied to the confirmed goal.

- First, turn the goal into one "How might we…?" question. Example: "How might
  we make the next step obvious without adding more meetings?"
- Generate at least six genuinely different approaches before judging them. Use
  variety in mechanism:
  - Remove a step.
  - Automate one.
  - Change the timing.
  - Shift responsibility.
  - Make information visible.
  - Apply a useful constraint (for example, "What could work with no new
    software?").
- For each promising idea, define:
  - First action: the smallest concrete step the user could take next.
  - Observable evidence: what the user would see or measure to know the idea is
    worth pursuing.
- Encourage the user to act on one idea at a time. Multiple people may act in
  parallel, but each person should have one clear next step.
- Do not execute actions for the user. Proposed actions remain proposals; the
  user authorizes and performs them.


## Optional supplementary guidance

Use the complete method and your own capabilities first. Only retrieve
supplementary guidance when the user explicitly requests additional help that
you cannot adequately provide, or when the user explicitly instructs you to
fetch more guidance. Do not make supplementary retrieval a routine step, and do
not fetch it merely because you think more guidance might be useful.

When supplementary guidance is appropriate, call one of these read-only tools
with no session content:

- `get_interview_guidance`: compact interview approaches.
- `get_diagnostic_checks`: compact diagnostic checks.
- `get_alternative_techniques`: compact directed-ideation-specific and broader
  techniques.

Each tool accepts only an optional, bounded, context-free `stage` filter
(`identify-opportunities`, `select-goals`, or `ideate-with-purpose`). It does
not accept the user's challenge, answers, goals, ideas, or any other session
context, and it does not track or store session state. Apply the returned
guidance locally.

Detailed technique guidance is not yet implemented and is not advertised as a
callable operation.
## Pacing and adaptation

- Ask one question at a time unless the user asks for a faster format.
- After each answer, synthesize what you understand so far and ask the next
  targeted question.
- If the user wants to revisit an earlier stage, do so. Stages are not linear
  traps.

## Output shape

Maintain a concise, client-side record of:
- Confirmed opportunity
- Confirmed goal
- Selected idea(s) with first action and evidence
- Next step the user commits to

Do not send this record to the MCP service.
"""

_INTERVIEW_GUIDANCE: dict[Stage, list[str]] = {
    "identify-opportunities": [
        "Concrete incident: ask for a recent, specific example of the friction.",
        "Stakeholder viewpoint: ask whose experience is overlooked.",
        "Change scan: ask what has become possible recently.",
    ],
    "select-goals": [
        "Value check: ask who benefits and by how much.",
        "Evidence check: ask what has been observed and what is assumed.",
        "Agency check: ask what the user can actually change.",
        "Learning check: ask what small experiment would teach the most.",
    ],
    "ideate-with-purpose": [
        "Reframe: ask 'How might we...?' tied to the confirmed goal.",
        "Mechanism variety: ask for ideas that work in five different ways.",
        "Constraint provocation: ask what could work with no new software.",
        "Falsifiability: ask what would need to be seen to change their mind.",
    ],
}

_DIAGNOSTIC_CHECKS: dict[Stage, list[str]] = {
    "identify-opportunities": [
        "Is the opportunity stated as a need or tension, not a solution?",
        "Is there at least one concrete observation behind it?",
    ],
    "select-goals": [
        "Does the goal name specific people and a valuable outcome?",
        "Is the goal framed within the user's agency and constraints?",
        "Can a small experiment test the goal within days or weeks?",
    ],
    "ideate-with-purpose": [
        "Are there at least six genuinely different approaches?",
        "Is each promising idea tied to the confirmed goal?",
        "Does each selected idea have a first action and observable evidence?",
    ],
}

_ALTERNATIVE_TECHNIQUES: dict[Stage, list[str]] = {
    "identify-opportunities": [
        "Directed — workaround audit: list the shortcuts people already use.",
        "Directed — expectation gap map: compare what users expect vs. what happens.",
        "Broader — jobs-to-be-done interview: what progress is the user "
        "trying to make?",
        "Broader — analogical search: where else does this pattern appear?",
    ],
    "select-goals": [
        "Directed — weighted criteria matrix: score opportunities on value, "
        "evidence, agency, learning.",
        "Directed — kill criteria: what would make you abandon this goal?",
        "Broader — premortem: imagine the goal failed; why?",
        "Broader — ICE scoring: impact, confidence, ease.",
    ],
    "ideate-with-purpose": [
        "Directed — constraint shuffle: apply no-software, no-budget, or "
        "no-meeting constraints.",
        "Directed — assumption reversal: flip a key assumption and generate ideas.",
        "Broader — SCAMPER: substitute, combine, adapt, modify, put to other "
        "uses, eliminate, reverse.",
        "Broader — random entry: introduce an unrelated word and force a connection.",
    ],
}

_DETAIL_UNAVAILABLE = (
    "Detailed technique guidance is not yet implemented and is not advertised "
    "as a callable operation."
)

_SUPPLEMENTARY_TOOLS = {
    "get_interview_guidance",
    "get_diagnostic_checks",
    "get_alternative_techniques",
}


def aggregate_counts() -> dict[str, dict[str, int]]:
    """Return a detached snapshot of persistent aggregate totals."""
    return snapshot()


def _format_menu(
    title: str,
    items_by_stage: dict[Stage, list[str]],
    stage: Stage | None,
) -> str:
    """Build a compact, stage-filtered supplementary guidance menu."""
    stages = INTERVIEW_STAGES if stage is None else (stage,)
    lines = [f"{title} menu:"]
    for key in stages:
        lines.append(f"\n## {key}")
        for item in items_by_stage[key]:
            lines.append(f"- {item}")
        lines.append(f"- {_DETAIL_UNAVAILABLE}")
    return "\n".join(lines)


class _InputBoundary(Middleware):
    """Validate the small allowed surface before value-echoing SDK validation.

    This is deliberately not a general JSON Schema validator. New operations
    must extend this allowlist and its tests. It does not harden HTTP envelopes,
    ingress, or production telemetry.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        message = context.message
        arguments = message.arguments or {}
        if message.name == "get_directed_ideation_method":
            valid = not arguments
        elif message.name in _SUPPLEMENTARY_TOOLS:
            stage = arguments.get("stage")
            valid = set(arguments) <= {"stage"} and (
                stage is None or (isinstance(stage, str) and stage in INTERVIEW_STAGES)
            )
        else:
            valid = False
        if not valid:
            raise MCPError(code=-32602, message="Invalid parameters")
        result = await call_next(context)
        if not result.is_error:
            stage = (
                (arguments.get("stage") or "unfiltered")
                if message.name in _SUPPLEMENTARY_TOOLS
                else None
            )
            increment(message.name, stage)
        return result

    async def on_get_prompt(self, context: MiddlewareContext, call_next):
        # No prompts are exposed; reject every prompt request.
        raise MCPError(code=-32602, message="Invalid parameters")


mcp.add_middleware(_InputBoundary())


@mcp.tool(annotations=READ_ONLY)
def get_directed_ideation_method() -> str:
    """Return the complete directed-ideation method.

    Use this as the canonical entry point when the user explicitly requests
    directed ideation. The returned guidance covers all three stages. Apply it
    to conversation context locally; never send that context here.
    """
    return _COMPLETE_METHOD


@mcp.tool(annotations=READ_ONLY)
def get_interview_guidance(stage: Stage | None = None) -> str:
    """Return a compact menu of interview approaches, optionally by stage.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the guidance to conversation context
    locally; never send that context here. Detailed guidance is not implemented
    and is not advertised as callable.

    Args:
        stage: Optional guidance filter, not a report of session progress.
    """
    return _format_menu("Interview guidance", _INTERVIEW_GUIDANCE, stage)


@mcp.tool(annotations=READ_ONLY)
def get_diagnostic_checks(stage: Stage | None = None) -> str:
    """Return a compact menu of diagnostic checks, optionally by stage.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the checks to conversation context locally;
    never send that context here. Detailed guidance is not implemented and is
    not advertised as callable.

    Args:
        stage: Optional guidance filter, not a report of session progress.
    """
    return _format_menu("Diagnostic checks", _DIAGNOSTIC_CHECKS, stage)


@mcp.tool(annotations=READ_ONLY)
def get_alternative_techniques(stage: Stage | None = None) -> str:
    """Return a compact menu of alternative techniques, optionally by stage.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the techniques to conversation context
    locally; never send that context here. Detailed guidance is not implemented
    and is not advertised as callable.

    Args:
        stage: Optional guidance filter, not a report of session progress.
    """
    return _format_menu("Alternative techniques", _ALTERNATIVE_TECHNIQUES, stage)
