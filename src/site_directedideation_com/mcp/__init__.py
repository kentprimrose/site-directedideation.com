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

Stage = Literal["frame", "diagnose", "generate", "evaluate", "decide-and-stress-test"]
INTERVIEW_STAGES: tuple[Stage, ...] = (
    "frame",
    "diagnose",
    "generate",
    "evaluate",
    "decide-and-stress-test",
)

PhaseMethod = Literal[
    # Phase 1: Frame
    "cynefin",
    "kt-situation-appraisal",
    "socratic-questioning",
    # Phase 2: Diagnose
    "five-whys",
    "six-sigma-dmaic",
    "current-reality-tree",
    "systems-thinking",
    # Phase 3: Generate
    "brainstorming-checklist",
    "scamper",
    "synectics-analogies",
    "morphological-analysis",
    "triz-principles",
    "lateral-provocation",
    # Phase 4: Evaluate
    "toulmin-argument",
    "pyramid-principle",
    "competing-hypotheses",
    "scenario-planning",
    "six-thinking-hats",
    # Phase 5: Decide and stress-test
    "kt-decision-analysis",
    "decision-trees",
    "premortem",
    "fmea",
    "ooda-loop",
]

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
# Directed Ideation — complete five-phase method

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

## Five iterative loops: direction is a compass, not a track

Use these five phases to orient the work, not as a rigid sequence or a promise
to stay on the first path. The user chooses the direction and can revise any
output. Work with what is known, distinguish observations from assumptions, and
revisit an earlier phase whenever new evidence or the user's priorities warrant
it.

## Phase 1: Frame (define the real question)

Goal: clarify what kind of situation this is, separate what the problem is from
what it is not, and confirm a worthwhile, testable direction.

- Ask one question at a time; offer a small group only if the user asks to go
  faster. Start with a recent, specific instance of friction or a concrete
  decision to make.
- Classify the situation's complexity (Cynefin: Clear/Simple, Complicated,
  Complex, or Chaotic) so Phases 2 through 5 match the domain:
  - Clear/Simple: confirm facts quickly, apply known practices, check failure
    modes lightly.
  - Complicated: lean on root-cause diagnosis (Six Sigma DMAIC, Current Reality
    Tree), argument scrutiny (Toulmin, Pyramid Principle), and weighted
    decision analysis or decision trees.
  - Complex: probe through safe-to-fail experiments, emphasize systems thinking
    and leverage points, divergent generation, competing hypotheses, scenario
    planning, and fast OODA learning loops.
  - Chaotic: stabilize first with a tight OODA loop and immediate containment
    before deeper diagnosis.
- Separate what the problem is from what it is not (Situation Appraisal), probe
  purpose, assumptions, and evidence (Socratic questioning), and state the
  issue as a need or tension rather than a premature solution.
- Explore value, evidence, agency, and learning, then sharpen a working goal:
  "Help [specific people] achieve [valuable outcomes] in [context], while
  respecting [key constraints]."
- Output: observations, assumptions, complexity classification, confirmed
  problem framing, and working goal. Ask the user to confirm or revise before
  advancing; do not invent evidence.

## Phase 2: Diagnose (find root causes and structure)

Goal: uncover underlying causes, system structure, and leverage points before
generating solutions.

- Move beneath surface symptoms using methods matched to the Phase 1 framing:
  Five Whys, Six Sigma DMAIC (Measure and Analyze: Pareto, fishbone, control
  charts), Current Reality Tree (Logical Thinking Process), and Systems
  Thinking / leverage points (feedback loops, delays, stocks and flows).
- Mark every causal link as observed versus assumed; do not invent evidence or
  force a single linear cause when multiple factors interact.
- If diagnosis shows weak evidence or low agency, revisit Phase 1 to reframe
  the question or narrow the working goal.
- Output: candidate root causes, key system dynamics or leverage points,
  verified observations versus assumptions, and any revised working goal. Ask
  the user to confirm or revise before advancing.

## Phase 3: Generate (produce options)

Goal: diverge broadly before judging so genuinely different mechanisms are on
the table in service of the working goal.

- Turn the working goal into a "How might we...?" question and check its
  framing with the user. Separate generation from critique (keep the Artist /
  Green Hat separate from the Judge / Black Hat).
- Generate at least six genuinely different approaches using methods suited to
  the challenge: brainstorming rules and checklist questions, SCAMPER,
  Synectics analogies (direct, personal, symbolic, fantasy), morphological
  analysis, TRIZ inventive principles for resolving contradictions, or lateral
  provocation ("po" and movement).
- Output: the full set of ideas considered across varied mechanisms without
  prematurely filtering them. Re-diverge if options cluster around one pattern.

## Phase 4: Evaluate (test options against evidence and scenarios)

Goal: scrutinize promising options against logic, evidence, perspectives, and
plausible futures to reduce confirmation bias.

- Compare promising options with the user rather than deciding for them using
  Toulmin argument checks (claim, grounds, warrant, rebuttal), Pyramid
  Principle logic tests, Analysis of Competing Hypotheses (weighting
  disconfirming evidence), Scenario Planning across plausible futures, and
  Six Thinking Hats (White, Red, Black, Yellow, Green, Blue).
- Make tradeoffs, constraints, and remaining assumptions explicit. Combining,
  adapting, or setting aside options is welcome; return to Phase 3 if options
  are weak.
- Output: shortlisted option(s), supporting and challenging evidence, key
  tradeoffs, scenario sensitivities, and open assumptions. Ask the user to
  confirm the shortlist before advancing.

## Phase 5: Decide and stress-test (commit and check failure modes)

Goal: commit to a clear choice, stress-test how it could fail, define a
smallest concrete first action, and run a fast learning loop.

- Compare finalists rigorously using Kepner-Tregoe Decision Analysis (weighted
  criteria) and Potential Problem Analysis, Decision Trees and expected value
  for uncertain payoffs, Premortem (working backward from an assumed failure),
  FMEA (Severity, Occurrence, Detection), and the OODA loop (Observe, Orient,
  Decide, Act) for fast adaptation under changing conditions.
- For each selected option, define:
  - First action: the smallest concrete step the user could take next.
  - Observable evidence: what the user would see or measure to know the option
    is working, including evidence that would challenge it.
- Learn: after an authorized action or experiment, compare observations with
  expectations, capture what was learned, and ask whether to adapt, try another
  option, re-diverge, or revisit the diagnosis or framing. Do not claim an
  action happened or a result was observed before the user reports it.
- Output: ideas considered, selected option(s), decision rationale, stress-test
  risks and mitigations, first action, observable evidence, and—once reported—
  learning and revisions.
- Encourage one idea at a time; multiple people may act in parallel, but each
  person should have one clear next step. Do not execute actions for the user.
  Proposed actions remain proposals; the user authorizes and performs them.

## Phase-specific and supplementary guidance

Retrieve phase or supplementary guidance when you judge it useful or needed, or
when the user requests it. You may do so on your own initiative; an explicit
user request is not required.

All read-only guidance tools accept only bounded, context-free selectors—never
the user's challenge, answers, goals, ideas, or session state. Apply all
returned guidance locally:

- `get_phase_guidance`: detailed facilitation guidance for a phase (`frame`,
  `diagnose`, `generate`, `evaluate`, or `decide-and-stress-test`) and an
  optional `method` selector for that phase.
- `get_interview_guidance`: compact interview questions, optionally filtered by
  `stage`.
- `get_diagnostic_checks`: compact quality checks, optionally filtered by
  `stage`.
- `get_alternative_techniques`: compact technique menu, optionally filtered by
  `stage`.

## Additional tools for blockages

Lateral thinking, requirements clarification, and strategic thinking are
separate, additional tools offered alongside the core five-phase method to
assist the user past blockages encountered during the MCP process (or when
explicitly requested). None of these is a phase of directed ideation, and all
three accept no arguments and no session context:

- `get_lateral_thinking_guidance`: optional creative-thinking exercises drawing
  on Edward de Bono (provocations/"po", movement, random stimulus, APC) and
  Roger von Oech (breaking mental locks and separating the Artist from the
  Judge) for creative or framing blockages.
- `get_requirements_clarification_guidance`: optional Six Sigma-inspired
  clarifying exercises (Five Whys, VOC to CTQ trees, SIPOC, Ishikawa/Fishbone,
  scope and operational definitions, and lightweight FMEA) for ambiguity,
  symptom-vs-cause, or vague-requirement blockages.
- `get_strategic_thinking_guidance`: optional strategic and systems-thinking
  exercises drawing on William Dettmer's Logical Thinking Process (Goal Tree,
  Current Reality Tree, Evaporating Cloud, Future Reality Tree, Prerequisite
  Tree, Categories of Legitimate Reservation), Edward de Bono's Six Thinking
  Hats and direct-attention tools (CAF, PMI, APC), and Roger von Oech's
  Explorer, Artist, Judge, and Warrior roles.

## Pacing and adaptation

- Ask one question at a time unless the user asks for a faster format.
- After each answer, synthesize what you understand so far and ask the next
  targeted question.
- If the user wants to revisit an earlier phase, do so. Phases are not linear
  traps.

## Output shape

Maintain a concise, client-side record of:
- Observations, assumptions, complexity class, and confirmed framing/goal
- Root causes, system dynamics, and leverage points
- Ideas considered across varied mechanisms
- Evaluation findings, tradeoffs, and scenario or perspective checks
- Selected option(s), stress-test risks, first action, observable evidence, and
  learning revisions

Do not send this record to the MCP service.
"""

_PHASE_TITLES: dict[Stage, str] = {
    "frame": "Phase 1: Frame — define the real question",
    "diagnose": "Phase 2: Diagnose — find root causes and structure",
    "generate": "Phase 3: Generate — produce options",
    "evaluate": "Phase 4: Evaluate — test options against evidence and scenarios",
    "decide-and-stress-test": (
        "Phase 5: Decide and stress-test — commit and check failure modes"
    ),
}

_PHASE_OVERVIEWS: dict[Stage, str] = {
    "frame": (
        "Define what kind of situation you face, separate what the problem is from "
        "what it is not, probe assumptions, and confirm a working goal. Use the "
        "Cynefin classification to route Phases 2-5 (Clear: light checks; "
        "Complicated: analytical diagnosis and decision modeling; Complex: "
        "systems leverage, safe-to-fail probes, competing hypotheses, scenarios, "
        "and OODA; Chaotic: immediate stabilization via OODA)."
    ),
    "diagnose": (
        "Uncover root causes, variation, causal chains, and system leverage points "
        "before inventing solutions. Distinguish verified observations from "
        "assumptions at every causal link."
    ),
    "generate": (
        "Diverge before judging to produce at least six genuinely different "
        "approaches across distinct mechanisms. Keep generation separate from "
        "critique."
    ),
    "evaluate": (
        "Test candidate options against reasoning quality, disconfirming evidence, "
        "plausible futures, and distinct stakeholder perspectives to counter "
        "confirmation bias."
    ),
    "decide-and-stress-test": (
        "Commit against explicit criteria, quantify key uncertainties when "
        "warranted, surface failure modes before launch, define one concrete "
        "first action with observable evidence, and adapt rapidly after results "
        "are reported."
    ),
}

PHASE_METHODS: dict[Stage, dict[PhaseMethod, tuple[str, str]]] = {
    "frame": {
        "cynefin": (
            "Cynefin framework",
            "Sort the situation into Clear/Simple (known cause-effect), "
            "Complicated (analyzable with expertise), Complex (cause-effect clear "
            "only in retrospect; requires safe-to-fail probes), or Chaotic "
            "(act immediately to stabilize). Ask what evidence supports the "
            "domain choice and use it to select methods for Phases 2-5.",
        ),
        "kt-situation-appraisal": (
            "Kepner-Tregoe Situation Appraisal",
            "List separate concerns, split compound issues apart, clarify what "
            "the problem IS versus what it IS NOT (where, when, who, extent), "
            "and prioritize by timing, trend, and impact before diagnosing.",
        ),
        "socratic-questioning": (
            "Socratic questioning and elements of reasoning",
            "Probe one element at a time: purpose, the exact question at issue, "
            "observed information versus inference, underlying assumptions, key "
            "concepts, overlooked points of view, and implications.",
        ),
    },
    "diagnose": {
        "five-whys": (
            "Five Whys",
            "Start from one concrete observed symptom and ask 'Why did that "
            "happen?' iteratively up to five times. Mark every link as observed "
            "or assumed, and allow branching causes rather than forcing a single "
            "linear chain.",
        ),
        "six-sigma-dmaic": (
            "Six Sigma DMAIC tools (Measure and Analyze)",
            "Quantify the gap before assuming causes: identify the vital few "
            "drivers (Pareto principle), group potential causes across categories "
            "(fishbone / cause-and-effect), and distinguish ordinary variation "
            "from special-cause shifts (control-chart thinking).",
        ),
        "current-reality-tree": (
            "Current Reality Tree (Logical Thinking Process)",
            "List observed Undesirable Effects (symptoms), connect them with "
            "if-then cause-and-effect chains down to a shared core root cause, "
            "and test each arrow with Categories of Legitimate Reservation "
            "(clarity, existence, causality, sufficiency).",
        ),
        "systems-thinking": (
            "Systems thinking and leverage points",
            "Map reinforcing and balancing feedback loops, information delays, "
            "incentives, and bottlenecks to find leverage points where a small, "
            "focused shift changes system behavior sustainably.",
        ),
    },
    "generate": {
        "brainstorming-checklist": (
            "Brainstorming rules and checklist questions",
            "Defer judgment completely during divergence, aim for volume and "
            "wild combinations, build on earlier ideas, and prompt across varied "
            "mechanisms (remove, automate, resequence, shift ownership, expose "
            "information, add a constraint).",
        ),
        "scamper": (
            "SCAMPER",
            "Transform the current workflow or artifact systematically across "
            "seven lenses: Substitute, Combine, Adapt, Modify/Magnify, Put to "
            "other uses, Eliminate, and Reverse/Rearrange.",
        ),
        "synectics-analogies": (
            "Synectics analogies",
            "Make the familiar strange and the strange familiar using four "
            "analogy types: Direct (how nature or another field solves it), "
            "Personal (imagine being the component or user), Symbolic (a vivid "
            "compressed paradox), and Fantasy (ideal world without limits), then "
            "extract a practical mechanism.",
        ),
        "morphological-analysis": (
            "Morphological analysis",
            "Break the solution space into 3-5 independent dimensions (such as "
            "trigger, actor, channel, cadence, artifact), list 3-4 options per "
            "dimension, and combine unexpected cells into distinct concepts.",
        ),
        "triz-principles": (
            "TRIZ inventive principles",
            "State the contradiction explicitly ('improving X worsens Y'), then "
            "apply inventive principles—such as segmentation, taking out, "
            "asymmetry, prior action, dynamics, or separation in time/space—to "
            "resolve the conflict without weak compromise.",
        ),
        "lateral-provocation": (
            "Lateral provocation",
            "Introduce a deliberate 'Po:' statement as an unlikely stepping stone "
            "(explicitly framed as a thinking exercise), use movement (extract a "
            "principle or trace moment-to-moment consequences) before judging, "
            "and test how the extracted principle serves the goal.",
        ),
    },
    "evaluate": {
        "toulmin-argument": (
            "Toulmin argument model",
            "Test each promising recommendation by separating its Claim, "
            "Grounds (observed evidence), Warrant (why those grounds support the "
            "claim), Backing, Qualifier (degree of certainty), and Rebuttal "
            "(conditions under which the claim fails).",
        ),
        "pyramid-principle": (
            "Pyramid Principle",
            "State the recommended conclusion first, group supporting reasons "
            "so they are mutually exclusive and collectively exhaustive (MECE), "
            "and verify that every lower-level fact actually supports the point "
            "above it.",
        ),
        "competing-hypotheses": (
            "Analysis of Competing Hypotheses",
            "List mutually exclusive explanations or candidate options across "
            "columns and key evidence across rows. Score each piece of evidence "
            "for consistency or inconsistency—focusing on disconfirming evidence "
            "to counter confirmation bias.",
        ),
        "scenario-planning": (
            "Scenario planning",
            "Identify two high-impact, high-uncertainty external drivers, sketch "
            "3-4 plausible futures, and stress-test how each option performs "
            "across scenarios to find robust or adaptable choices.",
        ),
        "six-thinking-hats": (
            "Six Thinking Hats",
            "Examine candidate options one parallel mode at a time: White "
            "(facts and gaps), Red (intuition without forced justification), "
            "Black (caution and risks), Yellow (logical value), Green "
            "(improvements and alternatives), and Blue (summary and next step).",
        ),
    },
    "decide-and-stress-test": {
        "kt-decision-analysis": (
            "Kepner-Tregoe Decision Analysis",
            "Separate non-negotiable MUST constraints (pass/fail) from weighted "
            "WANT criteria (scored 1-10), evaluate finalists transparently, then "
            "run Potential Problem Analysis to list likely threats plus "
            "preventive and contingent actions.",
        ),
        "decision-trees": (
            "Decision trees and expected value",
            "Map decision branches, key chance events with explicit rough "
            "probabilities, and outcomes/costs so uncertain tradeoffs and the "
            "value of running a small information-gathering test become visible.",
        ),
        "premortem": (
            "Premortem",
            "Assume the chosen plan has already failed weeks or months from now, "
            "work backward to list the most plausible causes of failure, and "
            "strengthen the first action or add kill criteria before starting.",
        ),
        "fmea": (
            "FMEA",
            "List concrete ways the chosen approach could fail, rate Severity, "
            "Occurrence, and Detection (1-10 or High/Medium/Low), prioritize the "
            "highest-risk modes, and assign a mitigation or early warning signal.",
        ),
        "ooda-loop": (
            "OODA loop",
            "Run a fast Observe -> Orient -> Decide -> Act cycle around one "
            "small authorized step: gather fresh observations after action, "
            "re-orient mental models against disconfirming evidence, decide "
            "whether to adapt or pivot, and propose the next concrete step.",
        ),
    },
}

_LATERAL_THINKING_GUIDANCE = """\
# Lateral-thinking exercises (additional unblocking tool)

Lateral thinking is an additional tool separate from the core five-phase
directed-ideation method. Use it when the user requests lateral thinking or
when it may assist them past a blockage encountered during the directed-ideation
MCP process (or outside it). Do not send private context to the tool; apply
this guidance locally. These optional exercises are not a phase of directed
ideation and are not instructions to act on implausible ideas.

Whenever offering a prompt, explicitly introduce it as a thinking exercise,
for example: "Let's try a thinking exercise: ..." Ask one question at a time
and wait for the answer. The user may choose a technique, skip, stop, or return
to their own direction; do not pressure them to participate.

Choose or offer one of these creative-thinking prompts (drawing on Edward de
Bono and Roger von Oech):
- Provocation and movement (Edward de Bono): Use "po" to signal a provocation,
  a deliberately unlikely starting point rather than a claim, then use movement
  (extract a principle or trace it moment-to-moment) before judging. Try: "Po:
  the waiting room moves to the visitor. What possibility does that suggest?"
- Reverse assumptions: "What if the opposite of an assumption were true?"
- Random stimulus (de Bono): "What connection can you make between a
  lighthouse and this challenge?" Let the user choose another unrelated word if
  preferred.
- Alternatives, Possibilities, Choices / APC (de Bono): Look beyond the first
  satisfactory path by listing genuinely different explanations or mechanisms.
- Perspective: "How might someone with a very different role see this?"
- Remove or exaggerate: "What changes if one familiar constraint disappears?"
  Alternatively, exaggerate one feature and explore what that reveals.
- Analogy: "Where else is a similar tension handled differently?"
- Unlock mental locks (Roger von Oech): Name and loosen a habitual lock that
  blocks fresh options—such as stopping at "the right answer" (hunt for the
  "second right answer"), "follow the rules" (separate assumed conventions from
  fixed limits), "be practical" (defer feasibility checks while exploring),
  "that's not my area" (borrow from another field), or "to err is wrong" (treat
  small tests as learning).
- Separate creative roles (Roger von Oech): Keep the Artist (play, recombine,
  ask "What if?") free from premature interruption by the Judge (critique and
  select); shift to the Judge only after options exist, and to the Warrior when
  ready to overcome obstacles and act.

After the response, help extract a potentially useful principle from the
exercise and ask how, if at all, it might serve the user's direction—and if
they are in a directed-ideation session, return to the active phase once the
blockage clears. Treat practicality and constraints as something to check
together, not as proven.
"""

_REQUIREMENTS_CLARIFICATION_GUIDANCE = """\
# Requirements-clarification exercises (additional Six Sigma-inspired tool)

Requirements clarification is an additional tool separate from the core
five-phase directed-ideation method. Use it when the user requests it or when
ambiguity, symptom-vs-cause confusion, or vague requirements block progress
during the directed-ideation MCP process (or outside it). Apply this
guidance locally; do not send private context to the tool. These optional
exercises are not a phase of directed ideation and must not invent evidence.

Whenever offering a prompt, explicitly introduce it as a clarifying exercise,
for example: "Let's try a clarifying exercise: ..." Ask one question at a time
and wait for the answer. Distinguish verified observations from assumptions at
every step. The user may choose a technique, skip, stop, or return to their
own direction; do not pressure them to participate.

Choose or offer one of these Six Sigma-inspired approaches:
- Five Whys (root cause): Starting from one concrete observed symptom, ask
  "Why did that happen?" up to five times. Mark each link as observed or
  assumed, and allow branching causes rather than forcing a single chain.
- VOC to CTQ tree (measurable requirements): Turn a vague stakeholder want
  (Voice of the Customer) into a Need -> Driver -> Critical-to-Quality
  measurable requirement.
- SIPOC (process boundaries): Sketch the high-level Suppliers, Inputs,
  Process (5-7 steps), Outputs, and Customers to expose handoffs, scope,
  and user agency.
- Ishikawa / Fishbone categories (multi-factor causes): When a single causal
  chain stalls, scan People, Process, Tools/Systems, Policy/Constraints,
  Information/Measurement, and Environment for overlooked factors.
- Scope and operational definition (clear boundaries): State explicitly what
  is in scope versus out of scope, and define ambiguous terms by what is
  directly observable.
- Lightweight FMEA (pre-test failure modes): Before testing an idea, name the
  top two or three ways it could fail, how severe or likely each is, and an
  early signal that would warn you.

After the exercise, synthesize the clarified cause, boundary, or measurable
requirement—distinguishing observations from assumptions—and ask the user to
confirm or revise it. If they are in a directed-ideation session, carry the
confirmed clarification back into the active phase (framing, diagnosis,
evaluation, or test criteria) and resume the method.
"""

_STRATEGIC_THINKING_GUIDANCE = """\
# Strategic-thinking exercises (additional systems and parallel-thinking tool)

Strategic thinking is an additional tool separate from the core five-phase
directed-ideation method. Use it when the user requests it or when entrenched
conflicts, systems-level cause-and-effect, unintended side effects, lopsided
evaluation, or execution obstacles block progress during the directed-ideation
MCP process (or outside it). Apply this guidance locally; do not send private
context to the tool. These optional exercises are not a phase of directed
ideation and must not invent evidence.

Whenever offering a prompt, explicitly introduce it as a strategic exercise,
for example: "Let's try a strategic exercise: ..." Ask one question at a time
and wait for the answer. Distinguish observations from assumptions at every
step. The user may choose a technique, skip, stop, or return to their own
direction; do not pressure them to participate.

## Systems logic and change (William Dettmer's Logical Thinking Process)
Use these tools to answer what to change, what to change to, and how to cause
the change, checking each causal claim with Categories of Legitimate
Reservation (clarity, entity existence, causality, and sufficiency):
- Goal Tree: Before diagnosing problems, define the system's ultimate Goal,
  Critical Success Factors, and Necessary Conditions that must hold for success.
- Current Reality Tree: Link observed Undesirable Effects (symptoms) through
  cause-and-effect logic to a small number of core root causes rather than
  treating isolated symptoms.
- Evaporating Cloud (Conflict Resolution Diagram): Map a persistent dilemma
  (shared Objective -> two needed Requirements -> conflicting Prerequisites),
  expose the hidden assumptions behind the arrows, and challenge one assumption
  to dissolve the conflict without a weak compromise.
- Future Reality Tree and Negative Branch Reservation: Trace how a proposed
  change (injection) produces Desirable Effects, then proactively scan for
  unintended negative side effects (negative branches) and trim them before
  acting.
- Prerequisite Tree and Transition Tree: List concrete obstacles blocking the
  chosen change, name an Intermediate Objective to overcome each obstacle, and
  sequence the immediate next steps.

## Parallel and direct-attention thinking (Edward de Bono)
- Six Thinking Hats: Explore one mode at a time so critique does not crowd out
  discovery—White Hat (facts and information gaps), Red Hat (intuition and
  feelings without forced justification), Black Hat (caution, risks, and
  constraints), Yellow Hat (value and logical benefits), Green Hat (fresh
  alternatives and provocations), and Blue Hat (process control and next step).
- Direct-attention tools:
  - Consider All Factors (CAF): List overlooked stakeholders, constraints, and
    variables before locking a framing or decision.
  - Plus, Minus, Interesting (PMI): Evaluate an option across positives,
    negatives, and interesting sparks worth exploring before saying yes or no.
  - Alternatives, Possibilities, Choices (APC): Deliberately generate multiple
    strategic paths before committing to the first acceptable one.

## Creative-to-execution role pacing (Roger von Oech)
- Match the mindset to the work and avoid role collision: Explorer (gather raw
  evidence and outside perspective), Artist (recombine options freely without
  self-censorship), Judge (weigh evidence, risks, and tradeoffs objectively),
  and Warrior (overcome internal and external obstacles to execute the next
  concrete step).

After the exercise, synthesize the resulting goal conditions, core cause,
dissolved conflict, trimmed risks, or obstacle plan—distinguishing observations
from assumptions—and ask the user to confirm or revise it. If they are in a
directed-ideation session, carry the confirmed strategic insight back into the
active phase and resume the method.
"""


_INTERVIEW_GUIDANCE: dict[Stage, list[str]] = {
    "frame": [
        "Observation: what happened in a recent, specific example?",
        "Complexity (Cynefin): is cause-and-effect clear, analyzable, emergent, "
        "or chaotic?",
        "Is / Is Not: what specifically is part of this problem, and what is not?",
        "Assumption: what are we inferring rather than observing?",
        "Value, agency, and goal: who benefits, what can you influence, and "
        "which constraints are fixed versus assumed?",
        "Confirm: which problem framing and working goal best fit, and would "
        "you revise them?",
    ],
    "diagnose": [
        "Root cause: why did that observed symptom happen, and which causal "
        "links are observed versus assumed?",
        "Variation and drivers: which few factors account for most of the pain?",
        "Shared cause: what underlying core problem links separate symptoms?",
        "System dynamics: what feedback loop, delay, or incentive keeps this "
        "pattern in place?",
        "Leverage: where could a small intervention shift the outcome?",
        "Confirm: does this diagnosis hold up, or should we revisit the framing?",
    ],
    "generate": [
        "Reframe: what 'How might we...?' follows from the confirmed goal and "
        "diagnosis?",
        "Diverge: what approaches use genuinely different mechanisms?",
        "Transform and combine: what happens if we substitute, eliminate, "
        "reverse, or recombine dimensions?",
        "Contradictions: where do two desirable properties conflict, and how "
        "could we separate or resolve that conflict?",
        "Analogy and provocation: where else is a similar tension solved, or "
        "what works with no new software or budget?",
    ],
    "evaluate": [
        "Argument check: what concrete grounds and warrant actually support "
        "this recommendation, and what rebuttal could weaken it?",
        "Competing hypotheses: what evidence is inconsistent with each option?",
        "Scenarios: which plausible future changes would break or strengthen "
        "each candidate?",
        "Perspectives: what do neutral facts, intuition, caution, and benefits "
        "each highlight when examined separately?",
        "Tradeoffs: what would you give up by shortlisting these options?",
    ],
    "decide-and-stress-test": [
        "Decision criteria: which MUST limits are non-negotiable, and how do "
        "finalists score on weighted WANT criteria?",
        "Uncertainty: where do odds or payoffs matter most, and what small test "
        "would reduce uncertainty?",
        "Premortem and failure modes: if this failed a month from now, why, and "
        "which failure modes are most severe or hardest to detect?",
        "First action and evidence: what is the smallest concrete next step, "
        "and what observable evidence would confirm or challenge it?",
        "Learn (OODA): after an authorized action, what happened, and should "
        "the option, diagnosis, or framing change?",
    ],
}

_DIAGNOSTIC_CHECKS: dict[Stage, list[str]] = {
    "frame": [
        "Is the issue stated as a need or tension rather than a solution?",
        "Has the situation's complexity (Cynefin) been checked to guide later phases?",
        "Are observations separated from assumptions, and is scope (is / is "
        "not) clear?",
        "Does the working goal name specific people, valuable outcomes, "
        "agency, and key constraints?",
    ],
    "diagnose": [
        "Are candidate causes backed by at least one concrete observation?",
        "Have assumed causal links been explicitly flagged rather than invented?",
        "Have shared core causes, feedback loops, or leverage points been checked?",
        "Does the diagnosis confirm the working goal, or require reframing?",
    ],
    "generate": [
        "Are there at least six genuinely different approaches across varied "
        "mechanisms?",
        "Was idea generation separated from critique (Artist/Green Hat before "
        "Judge/Black Hat)?",
        "Are generated options tied to the confirmed goal and diagnosed causes?",
    ],
    "evaluate": [
        "Has each shortlisted option been tested for logical backing and "
        "disconfirming evidence?",
        "Have options been checked across more than one plausible future or "
        "stakeholder perspective?",
        "Are tradeoffs and open assumptions visible to the user?",
    ],
    "decide-and-stress-test": [
        "Did the user confirm the decision criteria, tradeoffs, and selected option?",
        "Have failure modes, negative side effects, and execution obstacles "
        "been stress-tested before acting?",
        "Does the selected option have one concrete first action and observable "
        "confirming and challenging evidence?",
        "After reported results, should the option, diagnosis, or framing be revised?",
    ],
}

_ALTERNATIVE_TECHNIQUES: dict[Stage, list[str]] = {
    "frame": [
        "Phase tool — Cynefin framework (`cynefin`): classify Clear, "
        "Complicated, Complex, or Chaotic to route Phases 2-5.",
        "Phase tool — Kepner-Tregoe Situation Appraisal "
        "(`kt-situation-appraisal`): separate what the problem is from what it "
        "is not and set priorities.",
        "Phase tool — Socratic questioning (`socratic-questioning`): probe "
        "purpose, assumptions, inferences, and evidence.",
        "Directed — workaround audit and expectation gap map: inspect current "
        "shortcuts and user expectation gaps.",
        "Broader — Explorer role (von Oech) and CAF (de Bono): gather outside "
        "raw material and list overlooked factors.",
    ],
    "diagnose": [
        "Phase tool — Five Whys (`five-whys`): iterative root-cause "
        "questioning with observed-vs-assumed links.",
        "Phase tool — Six Sigma DMAIC Measure/Analyze (`six-sigma-dmaic`): "
        "Pareto focus, fishbone diagrams, and variation analysis.",
        "Phase tool — Current Reality Tree (`current-reality-tree`): link "
        "undesirable effects to a shared core cause (Dettmer).",
        "Phase tool — Systems thinking and leverage points "
        "(`systems-thinking`): map feedback loops, delays, and high-leverage "
        "interventions.",
        "Broader — Evaporating Cloud (Dettmer) and jobs-to-be-done: surface "
        "hidden conflict assumptions and underlying user progress.",
    ],
    "generate": [
        "Phase tool — Brainstorming checklist (`brainstorming-checklist`): "
        "defer judgment and vary solution mechanisms.",
        "Phase tool — SCAMPER (`scamper`): substitute, combine, adapt, modify, "
        "put to other uses, eliminate, reverse.",
        "Phase tool — Synectics analogies (`synectics-analogies`): direct, "
        "personal, symbolic, and fantasy analogies.",
        "Phase tool — Morphological analysis (`morphological-analysis`): map "
        "solution dimensions and systematically recombine options.",
        "Phase tool — TRIZ inventive principles (`triz-principles`): resolve "
        "contradictions where X and Y conflict.",
        "Phase tool — Lateral provocation (`lateral-provocation`): deliberate "
        "'po' statements and movement (de Bono).",
        "Broader — constraint shuffle and mental locks (von Oech): force "
        "no-software/no-budget ideas and seek the second right answer.",
    ],
    "evaluate": [
        "Phase tool — Toulmin argument model (`toulmin-argument`): audit "
        "claim, grounds, warrant, qualifier, and rebuttal.",
        "Phase tool — Pyramid Principle (`pyramid-principle`): test "
        "conclusion-first MECE argument structure.",
        "Phase tool — Analysis of Competing Hypotheses "
        "(`competing-hypotheses`): weigh evidence across alternatives to "
        "counter confirmation bias.",
        "Phase tool — Scenario planning (`scenario-planning`): stress-test "
        "options against multiple plausible futures.",
        "Phase tool — Six Thinking Hats (`six-thinking-hats`): separate facts, "
        "intuition, caution, benefits, alternatives, and process (de Bono).",
        "Broader — PMI (de Bono) and Future Reality Tree (Dettmer): scan "
        "Plus/Minus/Interesting and trace negative branches.",
    ],
    "decide-and-stress-test": [
        "Phase tool — Kepner-Tregoe Decision Analysis (`kt-decision-analysis`): "
        "MUST/WANT weighted criteria plus Potential Problem Analysis.",
        "Phase tool — Decision trees and expected value (`decision-trees`): "
        "quantify uncertain branches, odds, and test value.",
        "Phase tool — Premortem (`premortem`): assume failure and work backward "
        "to blind spots and kill criteria.",
        "Phase tool — FMEA (`fmea`): score failure modes by severity, "
        "occurrence, and detection.",
        "Phase tool — OODA loop (`ooda-loop`): fast Observe, Orient, Decide, "
        "Act adaptation under changing conditions.",
        "Broader — Prerequisite Tree (Dettmer) and Warrior role (von Oech): "
        "map execution obstacles to intermediate objectives and commit.",
    ],
}

_PHASE_GUIDANCE_HINT = (
    "Call `get_phase_guidance` with `phase` and an optional `method` selector "
    "for step-by-step facilitation guidance on any phase tool."
)

_SUPPLEMENTARY_TOOLS = {
    "get_interview_guidance",
    "get_diagnostic_checks",
    "get_alternative_techniques",
}

_NO_ARG_TOOLS = {
    "get_directed_ideation_method",
    "get_lateral_thinking_guidance",
    "get_requirements_clarification_guidance",
    "get_strategic_thinking_guidance",
}


def is_valid_phase_method(phase: object, method: object) -> bool:
    """Validate bounded ``phase`` and optional ``method`` without echoing values."""
    if not isinstance(phase, str) or phase not in PHASE_METHODS:
        return False
    return method is None or (
        isinstance(method, str) and method in PHASE_METHODS[phase]
    )


def aggregate_counts() -> dict[str, dict[str, int]]:
    """Return a detached snapshot of persistent aggregate totals."""
    return snapshot()


def _format_menu(
    title: str,
    items_by_stage: dict[Stage, list[str]],
    stage: Stage | None,
) -> str:
    """Build a compact, phase-filtered supplementary guidance menu."""
    stages = INTERVIEW_STAGES if stage is None else (stage,)
    lines = [f"{title} menu:"]
    for key in stages:
        lines.append(f"\n## {key}")
        for item in items_by_stage[key]:
            lines.append(f"- {item}")
        lines.append(f"- {_PHASE_GUIDANCE_HINT}")
    return "\n".join(lines)


def _format_phase_guidance(phase: Stage, method: PhaseMethod | None) -> str:
    """Build bounded facilitation guidance for a phase or one method within it."""
    methods = PHASE_METHODS[phase]
    lines = [f"# {_PHASE_TITLES[phase]}", "", _PHASE_OVERVIEWS[phase]]
    if method is None:
        lines.append("\nAvailable method selectors for this phase:")
        for key, (label, guidance) in methods.items():
            lines.append(f"- `{key}` ({label}): {guidance}")
    else:
        label, guidance = methods[method]
        lines.extend(
            [
                f"\n## Method: {label} (`{method}`)",
                guidance,
                "",
                "Facilitation rules: introduce the exercise clearly, ask one "
                "question at a time, separate observations from assumptions, do "
                "not invent evidence, and confirm outputs with the user before "
                "advancing. Apply locally; never send session context to the MCP.",
            ]
        )
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
        if message.name in _NO_ARG_TOOLS:
            valid = not arguments
        elif message.name in _SUPPLEMENTARY_TOOLS:
            stage = arguments.get("stage")
            valid = set(arguments) <= {"stage"} and (
                stage is None or (isinstance(stage, str) and stage in INTERVIEW_STAGES)
            )
        elif message.name == "get_phase_guidance":
            valid = (
                "phase" in arguments
                and set(arguments) <= {"phase", "method"}
                and is_valid_phase_method(
                    arguments.get("phase"), arguments.get("method")
                )
            )
        else:
            valid = False
        if not valid:
            raise MCPError(code=-32602, message="Invalid parameters")
        result = await call_next(context)
        if not result.is_error:
            stage = None
            if message.name in _SUPPLEMENTARY_TOOLS:
                stage = arguments.get("stage") or "unfiltered"
            elif message.name == "get_phase_guidance":
                stage = arguments["phase"]
            increment(message.name, stage)
        return result

    async def on_get_prompt(self, context: MiddlewareContext, call_next):
        # No prompts are exposed; reject every prompt request.
        del context, call_next
        raise MCPError(code=-32602, message="Invalid parameters")


mcp.add_middleware(_InputBoundary())


@mcp.tool(annotations=READ_ONLY)
def get_directed_ideation_method() -> str:
    """Return the complete five-phase directed-ideation method.

    Use this as the canonical entry point when the user explicitly requests
    directed ideation. The returned guidance covers all five phases and Cynefin
    routing. Apply it to conversation context locally; never send that context
    here.
    """
    return _COMPLETE_METHOD


@mcp.tool(annotations=READ_ONLY)
def get_phase_guidance(phase: Stage, method: PhaseMethod | None = None) -> str:
    """Return facilitation guidance for one phase and optional phase method.

    Select a phase (`frame`, `diagnose`, `generate`, `evaluate`, or
    `decide-and-stress-test`) and optionally one method selector belonging to
    that phase. Apply the returned guidance locally; never send session context
    here.

    Args:
        phase: Fixed phase identifier to retrieve guidance for.
        method: Optional fixed method identifier belonging to ``phase``.
    """
    if not is_valid_phase_method(phase, method):
        raise MCPError(code=-32602, message="Invalid parameters")
    return _format_phase_guidance(phase, method)


@mcp.tool(annotations=READ_ONLY)
def get_interview_guidance(stage: Stage | None = None) -> str:
    """Return a compact menu of interview approaches, optionally by phase.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the guidance to conversation context
    locally; never send that context here.

    Args:
        stage: Optional phase filter, not a report of session progress.
    """
    return _format_menu("Interview guidance", _INTERVIEW_GUIDANCE, stage)


@mcp.tool(annotations=READ_ONLY)
def get_diagnostic_checks(stage: Stage | None = None) -> str:
    """Return a compact menu of diagnostic checks, optionally by phase.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the checks to conversation context locally;
    never send that context here.

    Args:
        stage: Optional phase filter, not a report of session progress.
    """
    return _format_menu("Diagnostic checks", _DIAGNOSTIC_CHECKS, stage)


@mcp.tool(annotations=READ_ONLY)
def get_alternative_techniques(stage: Stage | None = None) -> str:
    """Return a compact menu of phase tools and broader techniques.

    Use when the user explicitly requests more guidance, or asks for help you
    cannot adequately provide. Apply the techniques to conversation context
    locally; never send that context here.

    Args:
        stage: Optional phase filter, not a report of session progress.
    """
    return _format_menu("Alternative techniques", _ALTERNATIVE_TECHNIQUES, stage)


@mcp.tool(annotations=READ_ONLY)
def get_lateral_thinking_guidance() -> str:
    """Return creative and lateral-thinking exercises as an additional unblocking tool.

    Separate from the core five-phase directed-ideation method; draws on Edward
    de Bono and Roger von Oech to assist the user past creative or framing
    blockages encountered during the MCP process. Apply locally; never send
    private context here.
    """
    return _LATERAL_THINKING_GUIDANCE


@mcp.tool(annotations=READ_ONLY)
def get_requirements_clarification_guidance() -> str:
    """Return Six Sigma-inspired exercises for clarifying requirements and causes.

    Separate from the core five-phase directed-ideation method; use on request
    or to assist the user past ambiguity, symptom-vs-cause, or vague-requirement
    blockages encountered during the MCP process. Apply it locally; never send
    private context here.
    """
    return _REQUIREMENTS_CLARIFICATION_GUIDANCE


@mcp.tool(annotations=READ_ONLY)
def get_strategic_thinking_guidance() -> str:
    """Return strategic and systems-thinking exercises as an additional tool.

    Separate from the core five-phase directed-ideation method; draws on
    William Dettmer's Logical Thinking Process, Edward de Bono's Six Thinking
    Hats and direct-attention tools, and Roger von Oech's creative-to-execution
    roles to resolve entrenched conflicts, systems root causes, negative side
    effects, or execution obstacles. Apply locally; never send private context.
    """
    return _STRATEGIC_THINKING_GUIDANCE
