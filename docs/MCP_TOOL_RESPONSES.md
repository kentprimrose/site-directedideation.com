# MCP tool responses

This document captures the text returned by the local directed-ideation MCP prototype. The implementation in `src/site_directedideation_com/mcp/__init__.py` is authoritative; update this reference when its responses change.

The three supplementary tools accept an optional `stage`: `identify-opportunities`, `select-goals`, or `ideate-with-purpose`. The outputs below omit the filter (equivalent to `null`); supplying a stage returns the same menu title and only that stage’s section. Separately from the core three-stage method, the additional `get_lateral_thinking_guidance`, `get_requirements_clarification_guidance`, and `get_strategic_thinking_guidance` tools accept no arguments or stage filter and assist users past blockages encountered during the process. No session context is sent to the tools.

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

When supplementary guidance for the three stages is appropriate, call one of
these read-only tools with no session content:

- `get_interview_guidance`: compact interview approaches.
- `get_diagnostic_checks`: compact diagnostic checks.
- `get_alternative_techniques`: compact directed-ideation-specific and broader
  techniques.

These three tools accept only an optional, bounded, context-free `stage` filter
(`identify-opportunities`, `select-goals`, or `ideate-with-purpose`). It does
not accept the user's challenge, answers, goals, ideas, or any other session
context, and it does not track or store session state. Apply the returned
guidance locally.

Detailed technique guidance is not yet implemented and is not advertised as a
callable operation.

## Additional tools for blockages

Lateral thinking, requirements clarification, and strategic thinking are
separate, additional tools offered alongside the method to assist the user past
blockages encountered during the MCP process (or when explicitly requested).
None of these is a stage of directed ideation, and all three accept no
arguments and no session context:

- `get_lateral_thinking_guidance`: optional creative-thinking exercises
  drawing on Edward de Bono (provocations/"po", movement, random stimulus,
  APC) and Roger von Oech (breaking mental locks and separating the Artist from
  the Judge) for creative or framing blockages. Introduce each explicitly as a
  thinking exercise, let the user choose, and bring any useful principle back
  to serve the user's direction.
- `get_requirements_clarification_guidance`: optional Six Sigma-inspired
  clarifying exercises (such as Five Whys, VOC to CTQ trees, SIPOC,
  Ishikawa/Fishbone, scope and operational definitions, and lightweight FMEA)
  for ambiguity, symptom-vs-cause, or vague-requirement blockages. Introduce
  each explicitly as a clarifying exercise, distinguish observations from
  assumptions, and carry the confirmed clarification back into the active
  directed-ideation stage.
- `get_strategic_thinking_guidance`: optional strategic and systems-thinking
  exercises drawing on William Dettmer's Logical Thinking Process (Goal Tree,
  Current Reality Tree, Evaporating Cloud, Future Reality Tree, Prerequisite
  Tree, and Categories of Legitimate Reservation), Edward de Bono's Six
  Thinking Hats and direct-attention tools (CAF, PMI, APC), and Roger von
  Oech's creative-to-execution roles (Explorer, Artist, Judge, Warrior) for
  entrenched conflicts, systems root causes, unintended side effects, or
  execution-obstacle blockages. Introduce each explicitly as a strategic
  exercise, distinguish observations from assumptions, and carry the confirmed
  insight back into the active directed-ideation stage.

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
- Core cause and factors: what shared cause links these symptoms, and what factor have we left out?
- Compare framings: what other need or tension could explain this?
- Confirm: which framing best fits, and would you revise it?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Value and agency: who benefits, and what can you influence?
- Constraints: which limits are fixed, and which are assumed?
- Conflict check: what hidden assumption creates a tradeoff between two things you need?
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
- Side effects and obstacles: what unintended negative branch or obstacle could block this first step?
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
- Have we checked whether multiple symptoms share a core cause or overlooked factor (e.g., CRT or CAF)?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Does the goal name specific people and a valuable outcome?
- Is the goal framed within the user's agency and constraints?
- Can a small experiment test the goal within days or weeks?
- Have hidden conflicts or assumed rules been surfaced rather than accepted as fixed tradeoffs?
- Has the user confirmed the goal and its tradeoffs as a revisable direction?
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## ideate-with-purpose
- Are there at least six genuinely different approaches?
- Did we separate idea generation from critique (Artist/Green Hat before Judge/Black Hat)?
- Is each promising idea tied to the confirmed goal?
- Does each selected idea have a first action, observable evidence, and a check for unintended negative side effects or obstacles?
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
- Broader — Current Reality Tree (Dettmer): link observed undesirable effects to a shared core cause.
- Broader — Consider All Factors / CAF (de Bono): list overlooked stakeholders, variables, and constraints.
- Broader — Explorer role (von Oech): step outside your familiar domain to gather fresh raw material.
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## select-goals
- Directed — weighted criteria matrix: score opportunities on value, evidence, agency, learning.
- Directed — kill criteria: what would make you abandon this goal?
- Broader — premortem: imagine the goal failed; why?
- Broader — ICE scoring: impact, confidence, ease.
- Broader — Goal Tree and Evaporating Cloud (Dettmer): define necessary conditions and expose hidden assumptions behind goal conflicts.
- Broader — PMI and Six Thinking Hats (de Bono): scan Plus, Minus, and Interesting points or separate White, Yellow, and Black Hat views.
- Broader — Judge role (von Oech): evaluate feasibility and tradeoffs deliberately once exploration is sufficient.
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.

## ideate-with-purpose
- Directed — constraint shuffle: apply no-software, no-budget, or no-meeting constraints.
- Directed — assumption reversal: flip a key assumption and generate ideas.
- Broader — SCAMPER: substitute, combine, adapt, modify, put to other uses, eliminate, reverse.
- Broader — random entry: introduce an unrelated word and force a connection.
- Broader — Future Reality and Prerequisite Trees (Dettmer): trim unintended negative branches and map obstacles to intermediate objectives.
- Broader — Po provocation and APC (de Bono): use a deliberate provocation for movement and force multiple alternatives before choosing.
- Broader — Artist-to-Warrior handoff and mental locks (von Oech): look for the second right answer without premature judging, then commit to clearing execution obstacles.
- Detailed technique guidance is not yet implemented and is not advertised as a callable operation.
```

## `get_lateral_thinking_guidance`

```text
# Lateral-thinking exercises (additional unblocking tool)

Lateral thinking is an additional tool separate from the core three-stage
directed-ideation method. Use it when the user requests lateral thinking or
when it may assist them past a blockage encountered during the directed-ideation
MCP process (or outside it). Do not send private context to the tool; apply
this guidance locally. These optional exercises are not a stage of directed
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
they are in a directed-ideation session, return to the active stage once the
blockage clears. Treat practicality and constraints as something to check
together, not as proven.
```

## `get_requirements_clarification_guidance`

```text
# Requirements-clarification exercises (additional Six Sigma-inspired tool)

Requirements clarification is an additional tool separate from the core
three-stage directed-ideation method. Use it when the user requests it or when
ambiguity, symptom-vs-cause confusion, or vague requirements block progress
during the directed-ideation MCP process (or outside it). Apply this
guidance locally; do not send private context to the tool. These optional
exercises are not a stage of directed ideation and must not invent evidence.

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
confirmed clarification back into the active stage (opportunity framing, goal
selection, or test evidence) and resume the method.
```

## `get_strategic_thinking_guidance`

```text
# Strategic-thinking exercises (additional systems and parallel-thinking tool)

Strategic thinking is an additional tool separate from the core three-stage
directed-ideation method. Use it when the user requests it or when entrenched
conflicts, systems-level cause-and-effect, unintended side effects, lopsided
evaluation, or execution obstacles block progress during the directed-ideation
MCP process (or outside it). Apply this guidance locally; do not send private
context to the tool. These optional exercises are not a stage of directed
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
active stage and resume the method.
```
