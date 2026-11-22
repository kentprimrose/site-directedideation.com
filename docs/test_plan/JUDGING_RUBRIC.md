# Live MCP judging rubric

The matched library cases share the same opening statement, total unused slots, time limits, privacy rules, and success target. The causes and prior attempts differ. This tests whether the interview uncovers evidence that changes the first action instead of rewarding length or format.

## Interview audit (before judging)

For each arm, identify the first exchange in which the coordinator actually revealed the case's `decision_key`, or mark `not elicited`. Log the question and disclosed evidence. Separately mark whether the arm elicited a material prior attempt and the fixed success target, and whether its final plan used each of those facts. Record exchanges and count compound questions separately. Record stage/confirmation behavior descriptively, not as a bonus. An inadmissible pair is reported but not pooled with valid pairs.

## Blind plan score (0–10)

Give each judge only the public statement, that variant's `known_good`, this rubric, and shuffled A/B final plans. Require one evidence sentence per dimension and do not identify arms, models, or transcripts. Score independently; retain disagreement rather than overwriting it during audit.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Fit to evidence | Contradicts or misses the decisive evidence. | Targets a plausible cause but ignores important case evidence or the prior attempt. | Uses the decision-changing fact and relevant prior evidence to select a plan that is plausible at the observed volume. |
| Feasibility and safeguards | Needs unavailable resources or violates a hard safeguard. | Mostly feasible, but a staffing, privacy, or access safeguard is underspecified. | Fits resources and explicitly preserves relevant privacy, access, and operating constraints. |
| Actionability | No concrete first trial. | A trial is named, but ownership, trigger, or stopping point is unclear. | One reversible first change with owner, trigger, and concrete next action. |
| Testability | No usable measurement or decision rule. | Has a metric or threshold but omits or changes the fixed target, comparator, guardrail, or revision rule. | Retains the brief's actual target and comparable denominator/window, specifies what to measure and relevant guardrails, and names a result that changes the plan. |
| Trade-off reasoning | No credible alternative or deciding reason. | Names an alternative or an uncertainty without showing why it could matter. | Compares the strongest plausible alternative using case evidence and names an assumption that could change the choice. |

**Target fidelity is non-negotiable for full testability credit.** For these variants, tenable plans must assess **12 or fewer unused slots out of 48 across four comparable weeks**. An otherwise measurable plan that substitutes 14 or does not state the brief's target gets at most 1/2 on testability. A plan may correctly predict falling short, but must keep the target and specify when to revise. A format or option count is not evidence of plan quality.

After unblinding, check whether each arm recommends different first actions across the two variants and whether the difference is explained by elicited facts. Report interview depth and exchanges alongside plan scores. Judge agreement is not an additional trial. If two or more MCP interviews miss the same decision-critical question, propose a targeted guidance change against those traces, and test it in a separate revision rather than mixing guidance versions inside this pass.
