# Live MCP evaluation

Compare a model that uses live directed-ideation MCP with the same model working directly. This is not the [method-text benchmark](../IDEATION_EVALUATION.md): the treatment calls the live server, and the control gets neither its tools nor the method text.

## Cases

Start with one case and one pair. For broader coverage, use all three fictional cases in [`live_cases/`](live_cases/).

| Case | What the interview needs to discover |
|---|---|
| `01-pantry` | Exceptions, not routine check-ins, take most of the check-in time. A previous second-station trial failed for specific operational reasons. |
| `02-library` | A proposed scheduling fix addresses the wrong kind of missed visit, and a prior intervention has useful evidence of benefit and harm. |
| `03-repair-cafe` | Averages obscure where visitors give up; a change that helps throughput could make access worse. |

Each case uses `id`, `statement`, `hidden_brief`, and `known_good`. The answerer gets only the statement. The coordinator gets the hidden brief; the plan judge gets the statement and known-good reference. Keep briefs, the judging key, and the other arm's answers out of the answerer sessions.

## Native harnesses in Herdr

Run Codex, Gemini, and Claude in separate Herdr sessions using their native CLIs. Do not route these roles through Pi-Bolt, OpenCode, or OpenRouter by default. If a native harness, requested model, or authentication is unavailable, log the blocker rather than silently switching models or providers.

| Family | Native harness | Last verified judge model | Effort |
|---|---|---|---|
| OpenAI | Codex CLI (`codex`) | `gpt-6.1-sol` | Medium |
| Google | Gemini via Antigravity CLI (`agy`) | `gemini-4-neon-medium` | Medium |
| Anthropic | Claude Code (`claude`) | `claude-sonnet-4-6` | Medium |

Pin and log the exact model, effort, and harness version before each pass. Use the same answerer model, effort, and native harness in both arms. Each answerer family is a separate paired pass. Use a human or the same isolated model-driven coordinator for both arms. For plan scoring, use the native Codex, Gemini, and Claude judge sessions; select a different judge model if a judge would otherwise score its own answer. Keep judge sessions independent even when they run in parallel.

## Run a pair

Before launching a pair, open a new record using the [run log template](logs/TEMPLATE.md). The [log index](logs/README.md) lists past runs.

1. Launch two fresh sessions in separate Herdr workspaces with the same native harness, pinned model, and effort. Use isolated session settings: connect the enabled arm to the project's directed-ideation MCP endpoint; start the control with that server and any directed-ideation skill disabled. Keep other tools and unrelated context unavailable in both arms. Verify tool availability before sending the case, and save both traces. Do not resume, fork, or reuse an earlier chat. If the harness cannot isolate the two conditions, log the setup failure and skip the pair.

2. Send the same `statement` followed by this exact instruction to both:

   > If the directed-ideation MCP is available, call `get_directed_ideation_method` before your first question and use its guidance; otherwise work directly. Ask at most two questions per turn. Wait for my replies and use at least three and at most six interview exchanges before your final recommendation. Requests for confirmation count toward the exchange limit. After your sixth reply from me, finalize with the best plan you can offer and state what remains uncertain. Tell me what to try, why it beats the strongest alternative, what to measure, and what would make us revise it.

3. Use one coordinator and the same fixed brief for both. Answer the question asked, including direct follow-ups, but do not volunteer unrelated facts, relay the other arm's conclusions, or invent missing data. If asked to confirm a summary, confirm it only if it is consistent with the brief; correct relevant errors. An exchange is one answerer turn requesting input and one coordinator reply; tool calls alone do not count. Stop at the first final recommendation. Record early finalization, an exceeded budget, failed tools, or a control tool call as protocol deviations; don't silently repair or rerun an arm.
4. Check the traces: the enabled arm must have a successful `get_directed_ideation_method` result before its first question; the control must have no tool calls. If this fails, report a setup or adherence failure separately. Do not score it as a clean use-vs-no-use pair.

## Score separately

**Interview:** Before reading the plans, use the bracketed keys in `hidden_brief` as a checklist. Mark each as uncovered or not uncovered by the end of the interview; count it only if the model's question or confirmation elicited the relevant fact. Log the first exchange where it surfaced, total exchanges, and whether any corrections were incorporated. Report each key as well as the total so a missed prior attempt isn't hidden by a higher aggregate score.

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
