# Live MCP evaluation log

One Markdown file per paired run, including smoke tests and failed setups. Copy [TEMPLATE.md](TEMPLATE.md) to `YYYY-MM-DD-NN-case-id.md` (UTC start date, increasing sequence) before launching a pair. Use the [live-MCP protocol](../LIVE_MCP.md) for execution and scoring. This log does not track offline pytest results or runs of the separate method-text benchmark.

1. **Before the run:** Record the exact prompt or its retained location, the case/brief revision, model and settings, exchange budget, and start order. For a changed case, keep a separate snapshot or byte-level digest so later edits aren't mistaken for the original inputs.
2. **After the interviews:** Record the two trace IDs or safe artifact references, tool verification, exchange counts, protocol deviations, and coverage by hidden-brief key. Record the first exchange that elicited each fact; note relevant details still missing. Keep failed/incomplete runs in the log rather than replacing them with retries.
3. **Before unblinding:** Save the judge's A/B scores and evidence from the two final plans. Keep the A/B-to-arm mapping out of the judge input. Afterward, record the mapping and pair-level takeaway. Use `Not scored` if there was no independent judge; don't turn a retrospective observation into a numeric score.
4. **Closeout:** Verify all findings, scores, disagreements, and trace references are saved outside Herdr. Close the finished evaluation workspaces you created, record their IDs, and leave unrelated or unfinished workspaces alone.

The record is a summary and audit trail, not a transcript dump. Keep raw traces and judge inputs in approved local storage if they contain sensitive material. Don't put credentials, real participant details, or secret-bearing paths in this directory. Pi-Bolt session IDs are usable with `pi-bolt --session <id>` from the original directory if retained locally.

## Runs

| Run | Case | Outcome |
|---|---|---|
| [2026-11-22-01](2026-11-22-01-pantry-smoke.md) | Simple pantry smoke test | Both recommended the same staffing change; only the control elicited the wait target. Supplemental tool only, not a full-method comparison. |
| [2026-11-22-02](2026-11-22-02-01-pantry.md) | Richer pantry pilot | Full method verified. Different plans after six and four exchanges; neither asked about the prior second-station trial. No independent scores. |
| [2026-11-22-03](2026-11-22-03-01-pantry.md) | Food pantry | MCP 10/10, control 9/10. Exploratory: control exceeded the question budget. |
| [2026-11-22-04](2026-11-22-04-02-library.md) | Library appointments | Both 10/10. Exploratory: control exceeded the question budget. |
| [2026-11-22-05](2026-11-22-05-03-repair-cafe.md) | Repair café | Both 10/10. Both followed the interview protocol. |

**Initial scoring:** OpenCode returned HTTP 403 (model access disabled) for the configured judge `opencode/claude-sonnet-4-6`.

**Scoring retry (2026-11-22 00:45 UTC):** Resubmitted each pair's saved plans to the same judge with shuffled A/B labels. All three requests again returned HTTP 403 (model access disabled). No scores were produced, no alternate route was used, and no interviews were rerun.

**OpenRouter scoring attempt (2026-11-22 00:47 UTC):** At the user's request, submitted all three saved pairs to `openrouter/anthropic/claude-sonnet-4.6`. OpenRouter returned HTTP 402 (billing/credit limit) for all three, both through Pi-Bolt and with an explicit 650-output-token cap. No scores were produced, no interviews were rerun, and the suite's default routing was not changed.

**Claude Code scoring (2026-11-22 00:50 UTC):** At the user's request, Claude Code 2.1.330 in Herdr workspace `wG` scored all three saved pairs with `claude-sonnet-4-6` (medium effort), in three isolated, tool-free sessions. Each saw only the statement, reference, rubric, and shuffled A/B plans. No interviews were rerun and default routing was unchanged. Two control plans received full testability marks despite missing their brief's exact target; the individual logs note those discrepancies and preserve the judge's scores.

**Codex and Gemini rescoring (2026-11-22 00:55 UTC):** Both harnesses scored all three saved pairs from separate Herdr workspaces. See the [cross-judge score comparison](2026-11-22-cross-judge-rescoring.md) for model and effort settings, A/B mappings, dimension scores, and trace IDs.

The [judge evidence archive](2026-11-22-judge-evidence.json) preserves the exact scores and evidence for all nine successful judgments across the three native harnesses.

**Closeout (2026-11-22 01:00 UTC):** Verified that the ten Pi-Bolt interview traces were saved and that all nine judge responses were archived. Closed completed evaluation workspaces `w6`, `w7`, `w8`, `w9`, `wA`–`wF`, `wG`, `wH`, and `wJ`. The parent workspace `w1` was left open.

**Matched native rerun:** [Final results](2026-11-22-matched-native-library.md) and [protocol audit](2026-11-22-matched-native-library-audit.md). Twelve interviews and twelve judgments are archived, including the two Codex judge retries. Only one of six pairs met the interview protocol. All workspaces created for the run were closed.

**Gemini Herdr authentication smoke check (2026-11-22 13:01 UTC):** Native `agy` 1.5.14 with `gemini-4-neon-medium` responded to one-line probes in both an interactive Herdr session (`wX`) and a print-mode Herdr session (`wY`) using the existing Google login. The interactive session initially displayed a local workspace-trust prompt, not a Google credential prompt; print mode recorded zero tool steps. This was an authentication and launch check, not an MCP-mode evaluation. Both completed workspaces were closed.
