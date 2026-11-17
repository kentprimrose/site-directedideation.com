# MCP tool responses

This document captures the text returned by the local directed-ideation MCP prototype. The implementation in `src/site_directedideation_com/mcp/__init__.py` is authoritative; update this reference when its responses change.

The three supplementary tools accept an optional `stage`: `identify-opportunities`, `select-goals`, or `ideate-with-purpose`. The outputs below omit the filter (equivalent to `null`); supplying a stage returns the same menu title and only that stage’s section. No session context is sent to the tools.

## `get_directed_ideation_method`

```text
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
```

## `get_interview_guidance`

```text
Interview guidance menu:

## identify-opportunities
- Observation: what happened in a recent, specific example?
- Assumption: what are we inferring rather than observing?
- Perspective: whose experience or workaround have we missed?
- Compare framings: what other need or tension could explain this?
- Confirm: which framing best fits, and would you revise it?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Value and agency: who benefits, and what can you influence?
- Constraints: which limits are fixed, and which are assumed?
- Compare: which opportunity offers the most value and learning?
- Tradeoffs: what would you give up by choosing this goal?
- Success: what observable sign would show progress?
- Confirm: is this a useful, revisable goal?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## ideate-with-purpose
- Reframe: what 'How might we...?' follows from the confirmed goal?
- Diverge: what approaches use genuinely different mechanisms?
- Provoke: what could work without new software or budget?
- Compare: which ideas best fit the goal, constraints, and tradeoffs?
- Act: what is the first small action, and what evidence will you look for?
- Learn: what happened, and should the idea, goal, or framing change?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.
```

## `get_diagnostic_checks`

```text
Diagnostic checks menu:

## identify-opportunities
- Is the opportunity stated as a need or tension, not a solution?
- Is there at least one concrete observation behind it?
- Have assumptions and alternative framings been made visible?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Does the goal name specific people and a valuable outcome?
- Is the goal framed within the user's agency and constraints?
- Can a small experiment test the goal within days or weeks?
- Has the user confirmed the goal and its tradeoffs as a revisable direction?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## ideate-with-purpose
- Are there at least six genuinely different approaches?
- Is each promising idea tied to the confirmed goal?
- Does each selected idea have a first action and observable evidence?
- After learning, should the idea, goal, or opportunity be revised?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.
```

## `get_alternative_techniques`

```text
Alternative techniques menu:

## identify-opportunities
- Directed — workaround audit: list the shortcuts people already use.
- Directed — expectation gap map: compare what users expect vs. what happens.
- Broader — jobs-to-be-done interview: what progress is the user trying to make?
- Broader — analogical search: where else does this pattern appear?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Directed — weighted criteria matrix: score opportunities on value, evidence, agency, learning.
- Directed — kill criteria: what would make you abandon this goal?
- Broader — premortem: imagine the goal failed; why?
- Broader — ICE scoring: impact, confidence, ease.
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## ideate-with-purpose
- Directed — constraint shuffle: apply no-software, no-budget, or no-meeting constraints.
- Directed — assumption reversal: flip a key assumption and generate ideas.
- Broader — SCAMPER: substitute, combine, adapt, modify, put to other uses, eliminate, reverse.
- Broader — random entry: introduce an unrelated word and force a connection.
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.
```
