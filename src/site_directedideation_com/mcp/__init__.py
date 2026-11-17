"""Local-only directed-ideation MCP prototype, not the hosted service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.shared.exceptions import MCPError
from starlette.middleware import Middleware as ASGIMiddleware

from site_directedideation_com.mcp.http_boundary import RequestBodyLimit
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


class _BoundedHTTPFastMCP(FastMCP):
    def http_app(self, path=None, middleware=None, *args, **kwargs):
        return super().http_app(
            path,
            [ASGIMiddleware(RequestBodyLimit), *(middleware or [])],
            *args,
            **kwargs,
        )


mcp = _BoundedHTTPFastMCP(
    "site-directedideation.com", mask_error_details=True, lifespan=_lifespan
)


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

## Three iterative loops: direction is a compass, not a track

Use these loops to orient the work, not as a rigid sequence or a promise to stay
on the first path. The user chooses the direction and can revise any output.
Work with what is known, distinguish observations from assumptions, and revisit
an earlier loop whenever new evidence or the user's priorities warrant it.

## Stage 1: Identify opportunities (observe and reframe)

Goal: develop a concrete, evidence-based opportunity to work on.

- Ask one question at a time; offer a small group only if the user asks to go
  faster. Start with a recent, specific instance of friction.
- Explore friction, recent change, and overlooked perspectives. Capture what
  happened, who is affected, and what is observed versus assumed.
- Reframe observations as needs or tensions rather than solutions. For example,
  "New team members cannot tell which decision is current," not "We need a new
  dashboard." Consider alternative framings and what each makes visible.
- Loop between observation and reframing: identify a gap, seek another example
  or perspective, and revise the framing. Do not invent evidence.
- If there are multiple opportunities, briefly list them and ask the user which
  to focus on first; do not choose for them.
- Output: summarize the observations, assumptions and chosen opportunity
  framing. Ask the user to confirm it or revise it before proceeding; retain it
  as a working framing, open to revision.

## Stage 2: Select goals (decide and sharpen)

Goal: choose a worthwhile, testable direction tied to the working opportunity.

- Explore value (who benefits and how), evidence (observations and assumptions),
  agency (available time, access and resources), and learning (what a small
  experiment could reveal). Ask one question at a time.
- Compare possible goals with the user rather than deciding for them. Make
  tradeoffs and constraints explicit; if evidence or agency is weak, revisit
  the opportunity or seek more evidence.
- Loop between deciding and sharpening: propose a goal, check what success would
  look like and what matters most, then revise or choose another candidate.
  Use: "Help [specific people] achieve [valuable outcome] in [context], while
  respecting [key constraint]."
- Output: state the chosen goal, rationale, constraints, assumptions and a
  visible sign of progress. Ask the user to confirm or revise it; do not advance
  until they confirm. Treat the goal as a compass, not a fixed track.

## Stage 3: Ideate with purpose (diverge, converge and learn)

Goal: generate and test approaches in service of the working goal.

- Turn the goal into a "How might we…?" question, and check its framing with the
  user. Diverge before judging: generate at least six genuinely different
  approaches, varying mechanisms such as removing or automating a step, changing
  timing or responsibility, making information visible, or adding a constraint.
- Converge with the user: compare promising ideas against the goal, constraints,
  assumptions and potential learning. The user selects what to pursue; combining
  or setting aside ideas is welcome. Re-diverge if the options are weak.
- For each promising idea, define:
  - First action: the smallest concrete step the user could take next.
  - Observable evidence: what the user would see or measure to know the idea is
    worth pursuing, including evidence that would challenge it.
- Learn: after an authorized action or experiment, compare observations with
  expectations, capture what was learned, and ask whether to adapt, try another
  idea, re-diverge, or revisit the goal or opportunity. Do not claim an action
  happened or a result was observed before the user reports it.
- Output: the ideas considered, selected idea(s), rationale, first action,
  evidence to look for, and, when available, learning and any revision.
- Encourage one idea at a time; multiple people may act in parallel, but each
  person should have one clear next step. Do not execute actions for the user.
  Proposed actions remain proposals; the user authorizes and performs them.

## Optional supplementary guidance

Retrieve supplementary guidance when you judge it useful or needed, or when the
user requests it. You may do so on your own initiative; an explicit user request
is not required.

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
- Observations, assumptions and confirmed opportunity framing
- Confirmed goal, rationale, constraints and sign of progress
- Ideas considered and selected idea(s), rationale, first action and evidence
- Learning, revisions and next step the user commits to

Do not send this record to the MCP service.
"""

_INTERVIEW_GUIDANCE: dict[Stage, list[str]] = {
    "identify-opportunities": [
        "Observation: what happened in a recent, specific example?",
        "Assumption: what are we inferring rather than observing?",
        "Perspective: whose experience or workaround have we missed?",
        "Compare framings: what other need or tension could explain this?",
        "Confirm: which framing best fits, and would you revise it?",
    ],
    "select-goals": [
        "Value and agency: who benefits, and what can you influence?",
        "Constraints: which limits are fixed, and which are assumed?",
        "Compare: which opportunity offers the most value and learning?",
        "Tradeoffs: what would you give up by choosing this goal?",
        "Success: what observable sign would show progress?",
        "Confirm: is this a useful, revisable goal?",
    ],
    "ideate-with-purpose": [
        "Reframe: what 'How might we...?' follows from the confirmed goal?",
        "Diverge: what approaches use genuinely different mechanisms?",
        "Provoke: what could work without new software or budget?",
        "Compare: which ideas best fit the goal, constraints, and tradeoffs?",
        "Act: what is the first small action, and what evidence will you look for?",
        "Learn: what happened, and should the idea, goal, or framing change?",
    ],
}

_DIAGNOSTIC_CHECKS: dict[Stage, list[str]] = {
    "identify-opportunities": [
        "Is the opportunity stated as a need or tension, not a solution?",
        "Is there at least one concrete observation behind it?",
        "Have assumptions and alternative framings been made visible?",
    ],
    "select-goals": [
        "Does the goal name specific people and a valuable outcome?",
        "Is the goal framed within the user's agency and constraints?",
        "Can a small experiment test the goal within days or weeks?",
        "Has the user confirmed the goal and its tradeoffs as a revisable direction?",
    ],
    "ideate-with-purpose": [
        "Are there at least six genuinely different approaches?",
        "Is each promising idea tied to the confirmed goal?",
        "Does each selected idea have a first action and observable evidence?",
        "After learning, should the idea, goal, or opportunity be revised?",
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
        del context, call_next
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
