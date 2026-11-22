# 2026-11-22 — Codex and Gemini rescoring

Rescored the three saved pairs at about 00:55 UTC; no interviews were rerun. The original [Claude Code scores](README.md) are unchanged. Each judge received only the case statement, known-good reference, five-dimension rubric, and independently shuffled A/B plans. Each pair ran in a fresh session. No tool calls were observed in the scoring traces. Pantry and library scores remain exploratory because the control exceeded the interview question limit.

| Judge | Herdr pane | Harness | Model | Effort |
|---|---|---|---|---|
| Codex | `wH:p1` | Codex CLI 0.171.0 | `gpt-6.1-sol` | Medium |
| Gemini | `wJ:p1` | `agy` 1.5.14 | `gemini-4-neon-medium` | Medium |

## Totals

Scores are out of 10, listed as **MCP / control**. Claude is shown for comparison, not included in this rescore.

| Case | Claude Code | Codex | Gemini |
|---|---:|---:|---:|
| [Pantry](2026-11-22-03-01-pantry.md) (exploratory) | 10 / 9 | 9 / 9 | 10 / 9 |
| [Library](2026-11-22-04-02-library.md) (exploratory) | 10 / 10 | 10 / 9 | 10 / 10 |
| [Repair café](2026-11-22-05-03-repair-cafe.md) | 10 / 10 | 9 / 8 | 9 / 8 |

## Score breakdown

Each dimension is 0–2. A/B labels are as submitted; the arm column gives the mapping after scoring. Evidence below summarizes the judges' reasons for deductions.

| Case | Judge | Plan | Arm | Fit | Safeguards | Action | Testability | Trade-offs |
|---|---|---|---|---:|---:|---:|---:|---:|
| Pantry | Codex | A | Control | 2 | 2 | 2 | 1 | 2 |
| Pantry | Codex | B | MCP | 2 | 2 | 2 | 1 | 2 |
| Pantry | Gemini | A | Control | 2 | 2 | 2 | 1 | 2 |
| Pantry | Gemini | B | MCP | 2 | 2 | 2 | 2 | 2 |
| Library | Codex | A | Control | 2 | 2 | 2 | 1 | 2 |
| Library | Codex | B | MCP | 2 | 2 | 2 | 2 | 2 |
| Library | Gemini | A | MCP | 2 | 2 | 2 | 2 | 2 |
| Library | Gemini | B | Control | 2 | 2 | 2 | 2 | 2 |
| Repair café | Codex | A | MCP | 2 | 2 | 2 | 1 | 2 |
| Repair café | Codex | B | Control | 2 | 1 | 2 | 1 | 2 |
| Repair café | Gemini | A | Control | 2 | 1 | 2 | 1 | 2 |
| Repair café | Gemini | B | MCP | 1 | 2 | 2 | 2 | 2 |

- **Pantry:** Both judges deducted from the control's testability score because it omitted the 20-minute wait target and a throughput guardrail. Codex also deducted from the MCP plan because it did not specify sample size or who would record timestamps; Gemini did not.
- **Library:** Codex deducted from the control because its 14-unused-slot target was weaker than the brief's 12. Gemini, like Claude, gave full credit for an explicit measurable threshold despite that mismatch.
- **Repair café:** Codex and Gemini both deducted from the control for not specifying accessibility safeguards, the departure target, and checks on assisted-routing outcomes. They penalized the MCP plan on different dimensions: Codex wanted systematic door-to-bench timing; Gemini wanted the plan to address the reported wait statistic's exclusion of people who left and distinguish intake from electrical capacity.

## Trace references

| Case | Codex thread ID | Gemini conversation ID |
|---|---|---|
| Pantry | `01a200bf-7ec8-7591-8338-8c4b2345ec74` | `4c705ec5-699d-496e-b46a-96d6e7bb20fe` |
| Library | `01a200bf-7ec8-7893-aeac-a8bf07bb95c5` | `8135515e-70c7-46d1-b457-95a3a2b34054` |
| Repair café | `01a200bf-7ec8-74b2-9938-920fd6431a8c` | `a398b57e-2bf4-4bd3-bbfb-e3311255f2f4` |

The `agy` run completed all three judgments. The initial wrapper failed to recognize its final-event format; the validated scores above were recovered from those original streams without resubmitting any prompts.

## Takeaway

On the only pair that stayed within the protocol, Codex and Gemini preferred the MCP plan by one point; Claude tied the pair. The close scores and disagreement over whether a changed success target deserves full credit point to a rubric clarification for future runs: score against the target in the brief, not merely against whether the plan contains a number. These are three judgments of the same interviews, not additional independent trials.
