# Live MCP evaluation

Compare a model that uses live directed-ideation MCP with the same model working directly. This is not the [method-text benchmark](../IDEATION_EVALUATION.md): the treatment calls the live server, and the control gets neither its tools nor the method text. The plan has two distinct tracks: a paired, uncoached five-phase conversation for outcome comparison, and a separate tool-coverage sweep for exhaustive API exercise. Do not pool coverage sweeps with paired outcomes.

## Cases

Start with one case and one pair. For broader outcome coverage, use the fictional cases in [`live_cases/`](live_cases/). Reuse cases for the coverage sweep only in fresh sessions, never in a scored pair.

| Case | What the interview needs to discover |
|---|---|
| `01-pantry` | Exceptions, not routine check-ins, take most of the check-in time. A previous second-station trial failed for specific operational reasons. |
| `02-library` | A proposed scheduling fix addresses the wrong kind of missed visit, and a prior intervention has useful evidence of benefit and harm. |
| `03-repair-cafe` | Averages obscure where visitors give up; a change that helps throughput could make access worse. |
| `04-library-reminders` + `05-library-cancellations` | Identical opening and target; opposite evidence about no-shows, cancellations, and prior reminders should change the recommendation. Run both as a matched set. |

Each case uses `id`, `statement`, `hidden_brief`, and `known_good`. The answerer gets only the statement. The coordinator gets the hidden brief; the plan judge gets the statement and known-good reference. Keep briefs, the judging key, and the other arm's answers out of the answerer sessions.

## Native harnesses in Herdr

Run Codex, Gemini, and Claude in separate Herdr sessions using their native CLIs. Do not route these roles through Pi-Bolt, OpenCode, or OpenRouter by default. If a native harness, requested model, or authentication is unavailable, log the blocker rather than silently switching models or providers.

| Family | Native harness | Last verified judge model | Effort |
|---|---|---|---|
| OpenAI | Codex CLI (`codex`) | `gpt-6.1-sol` | Medium |
| Google | Gemini via Antigravity CLI (`agy`) | `gemini-4-neon-medium` | Medium |
| Anthropic | Claude Code (`claude`) | `claude-sonnet-4-6` | Medium |

Pin and log the exact model, effort, and harness version before each pass. Use the same answerer model, effort, and native harness in both arms. Each answerer family is a separate paired pass. Use a human or the same isolated model-driven coordinator for both arms. For plan scoring, use the native Codex, Gemini, and Claude judge sessions; select a different judge model if a judge would otherwise score its own answer. Keep judge sessions independent even when they run in parallel.

## Track A: paired five-phase conversation

Before launching a pair, open a new record using the [run log template](logs/TEMPLATE.md). The [log index](logs/README.md) lists past runs.

1. Follow the [native harness setup](NATIVE_HARNESS_SETUP.md) for the two fresh Herdr workspaces. Claude uses explicit session-local configs; Codex uses a per-server override in an isolated profile; `agy` uses an isolated home with sequential arms. Record both arms' preflight evidence before sending their case prompts. If the harness cannot isolate the conditions or the enabled server cannot connect, log the setup failure and skip the pair.

2. Send the same `statement` followed by this exact instruction to both:

   > If the directed-ideation MCP is available, call `get_directed_ideation_method` before your first question and use its guidance; otherwise work directly. Ask one question at a time, unless I ask to go faster. Wait for my replies. Use at least ten and at most eighteen interview exchanges before your final recommendation; confirmations count. If the method is available, work through Frame, Diagnose, Generate, Evaluate, and Decide and stress-test, confirming phase outputs where the guidance asks you to. You may revisit earlier phases when evidence warrants it. Use phase-specific or supplementary guidance when useful, not merely to fill a quota. After my eighteenth reply, finalize with the best plan you can offer and state which phases or facts remain uncertain. Tell me what to try, why it beats the strongest alternative, what to measure, what could go wrong, and what would make us revise it. Do not claim the user took an action or that results were observed.

3. Use one coordinator and the same fixed brief for both. Answer the question asked, including direct follow-ups, but do not volunteer unrelated facts, relay the other arm's conclusions, or invent missing data. Confirm a summary only when consistent with the brief; correct relevant errors. An exchange is one answerer turn requesting input and one coordinator reply; tool calls alone do not count. For the coverage of Phase 5 learning, the coordinator may report an observed result **only if** a prewritten follow-up in the case brief supplies it; otherwise score the proposed learning rule, not a fictional outcome. Stop at the first final recommendation. Record early finalization, an exceeded budget, failed tools, or a control tool call as deviations; do not silently repair or rerun an arm.
4. Audit the traces: the enabled arm must successfully call `get_directed_ideation_method` before its first question, the control must have no tool calls, and neither arm may use unrelated tools. For both arms, record evidence of each phase separately: Frame (observations/assumptions, complexity class, confirmed goal), Diagnose (candidate causes and observed vs assumed links), Generate (at least six distinct mechanisms), Evaluate (evidence against options, tradeoffs and confirmed shortlist), Decide and stress-test (choice, risks, first action, confirming and challenging evidence). Log confirmation exchanges, revisits, missing phases and whether tool guidance was applied rather than just fetched. A missing phase is a phase-coverage failure, not proof of poor plan quality. If isolation or trace checks fail, report a setup/adherence failure rather than a clean use-vs-no-use pair.

## Track B: exhaustive MCP tool coverage (not scored as a pair)

In a **fresh enabled native session for each harness**, explicitly request the following calls through the connected MCP server and retain tool-call arguments, successful result/preview, and trace references. Do not feed this checklist to either Track A answerer or judge. Run a separate control discovery probe with no MCP tools, as in [native harness setup](NATIVE_HARNESS_SETUP.md). A successful discovery listing alone is not a successful tool call.

| Tool | Required exercise |
|---|---|
| `get_directed_ideation_method` | Once; verify the complete five-phase method is returned. |
| `get_phase_guidance` | Once for **each** `phase`: `frame`, `diagnose`, `generate`, `evaluate`, `decide-and-stress-test`. Also call with a valid `method` selector for each phase (e.g. `cynefin`, `five-whys`, `scamper`, `competing-hypotheses`, `premortem`); verify focused guidance differs from the phase menu. |
| `get_interview_guidance` | Unfiltered (`stage` omitted) and filtered once for each of the five stages. |
| `get_diagnostic_checks` | Unfiltered and filtered once for each of the five stages. |
| `get_alternative_techniques` | Unfiltered and filtered once for each of the five stages. |
| `get_lateral_thinking_guidance` | Once, in a separate creative-blockage scenario. |
| `get_requirements_clarification_guidance` | Once, in a separate ambiguity or symptom-vs-cause scenario. |
| `get_strategic_thinking_guidance` | Once, in a separate systems/conflict or execution-obstacle scenario. |

For each filtered call, verify the response contains only the selected phase section; unfiltered menus should include all five. The three unfiltered blockage tools are **additional**, not phases or stage-filtered tools. Test that the agent applies their guidance locally and does not send case details or private answers as tool arguments. Coverage is complete only when all eight tools and all five phase selectors have successful calls in each harness and the conversation audit covers all five phases in at least one eligible enabled run per harness. If a call is unavailable, refused, or unverified, mark its exact cell missing and retain the failure; do not infer coverage from another harness or quietly substitute a provider. Optional negative tests (invalid phase/method) are separate from the required coverage. These deliberately prompted calls measure plumbing and instruction-following, **not** spontaneous usage or treatment benefit.
## Score separately

For a matched set, use the [judging rubric and interview audit](JUDGING_RUBRIC.md), including the `decision_key`, prior attempt, exact success target, and exchange count. Keep the MCP guidance unchanged across the pass. If traces repeatedly miss a pivotal question, test a targeted guidance revision in a later pass; do not change instructions mid-comparison.

**Interview:** Before reading the plans, use the bracketed keys in `hidden_brief` as a checklist. Mark each as uncovered or not uncovered by the end of the interview; count it only if the model's question or confirmation elicited the relevant fact. Log the first exchange where it surfaced, total exchanges, and whether any corrections were incorporated. Report each key as well as the total so a missed prior attempt isn't hidden by a higher aggregate score. Report five-phase coverage and use of any retrieved guidance separately from fact discovery and blind plan scores.

**Plan:** For each native judge, independently shuffle the final plans and label them A and B. Start a fresh Herdr judge session for each pair. Give it only the statement, `known_good`, the rubric, and the two final plans. Disable tools where supported; otherwise use an isolated working directory and verify the event trace contains no tool calls. Do not expose answerer identities, transcripts, tool traces, arm labels, or other judges' responses. Score each dimension 0–2 (0 = absent or contradicted, 1 = partial or underspecified, 2 = clearly meets the reference). Require one sentence of evidence per score. Credit defensible alternatives and check explicit targets against the brief. Preserve each judge's raw scores; report disagreement and audit findings separately.

| Dimension | What earns 2 |
|---|---|
| Fit to evidence | Targets the case-specific cause and accounts for material prior evidence. |
| Feasibility and safeguards | Fits staffing and operating limits, with an explicit safeguard for the affected group. |
| Actionability | Names one reversible first change and explains how to try it with available resources. |
| Testability | Defines the comparison, the success target, the guardrails, and a trigger for revision. |
| Trade-off reasoning | Compares against a plausible alternative and names an assumption that could change the choice. |

## Log and close

Record every result under [`logs/`](logs/README.md), including failed setup or scoring attempts, deviations, uncovered facts, final plans, each judge's scores and evidence, disagreements, and follow-up findings. Save the trace IDs or durable artifact references and the A/B-to-arm mapping after scoring. Verify that the findings and evidence are retained outside the Herdr session, then close each completed evaluation workspace the run created. Leave unrelated sessions and any unfinished assignments alone; record anything left open and why.

Report per-case differences and consistency across repeats, not a pooled win from a small sample or from multiple judgments of the same interview. Start repeats in fresh sessions, alternate launch order, and change the common exchange budget only between pairs. Note where the cap curtailed confirmation or exploration.
