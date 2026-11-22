# 2026-11-22 — Matched library cases, native harness rotation

- **Inputs:** [04-library-reminders](../live_cases/04-library-reminders.json), [05-library-cancellations](../live_cases/05-library-cancellations.json), [judging rubric](../JUDGING_RUBRIC.md), and identical public opening across both variants.
- **Design:** Three answerer harnesses × two scenarios × two conditions. Score each verified pair with the other two harnesses as independent blind judges. Coordinator: Codex `gpt-6.1-sol` at low effort with the same fixed brief per variant. Answerers and judges: Claude Code `claude-sonnet-4-6`, Codex `gpt-6.1-sol`, Gemini `gemini-4-neon-medium`, all medium. Endpoint `http://127.0.0.1:8001/mcp`; the method text is unchanged for this pass.
- **Status:** Complete. Twelve final interviews and twelve blind judgments are retained. Only one of six pairs satisfied the interview protocol; the other scores are exploratory. Two initial Codex judge timeouts were retried on request, without rerunning interviews.

## Recorded results

See the [evidence archive](2026-11-22-matched-native-library-evidence.json) for interviews, plans, tool-free retry inputs and responses, and blind scoring rationales. The [interview audit](2026-11-22-matched-native-library-audit.md) identifies elicited evidence and protocol deviations. Totals are MCP / control, out of 10. Only the bolded pair is admissible.

| Answerer | Case | Exchanges | Claude judge | Codex judge | Gemini judge |
|---|---|---:|---:|---:|---:|
| **Claude** | **Reminders** | 6 / 5 | — | 4 / 7 | 6 / 8 |
| Claude | Cancellations | 5 / 6 | — | 9 / 5 | 8 / 4 |
| Codex | Reminders | 6 / 3 | 10 / 6 | — | 7 / 7 |
| Codex | Cancellations | 6 / 3 | 9 / 9 | — | 7 / 8 |
| Gemini | Reminders | 5 / 4 | 10 / 10 | 10 / 9 | — |
| Gemini | Cancellations | 5 / 3 | 9 / 10 | 7 / 10 | — |

The initial four Codex interviews are retained separately as invalid: both controls retrieved the method through a hosted `codex_apps` connector despite the local entry being disabled, and both enabled sessions read a host skill. The retry isolated the native profile, disabled hosted apps and shell tooling, and passed positive and negative preflight probes. Gemini required a targeted headless permission for the MCP call; its enabled trace also read only generated descriptors from the registered server. The Gemini control contained no tool events; an initial parser misclassified system messages and the archived record reflects the corrected audit. No MCP guidance change was deployed or tested in this pass.

## Final outcome

This pass does **not** establish that live MCP improves plan selection. In the one admissible pair, both judges preferred the Claude control's reminder pilot to the MCP arm's 24-hour booking cutoff. Neither arm uncovered why eight of ten patrons missed their appointments. The five other pairs exceeded the two-question budget in at least one arm, so they cannot support a pooled comparison. The contrasting Claude cancellations result is useful for hypothesis generation: the MCP arm discovered the two-hour refill window and prior reminder process, and both judges preferred its plan, but the control interview breached the question limit.

Across all six pairs, the exact target (at most 12 unused of 48 slots across four comparable weeks) appeared in two MCP plans and three controls. Two MCP interviews per variant missed the same kind of decision-changing evidence: reasons for no-shows, or historical refill-eligible volume and existing reminders. The next guidance test should reserve a question for evidence that distinguishes the leading options and one for the success target. Enforce the compound-question limit and tighten coordinator disclosure before testing the revision. This run kept the guidance fixed.

**Closeout:** The initial ten evaluation workspaces were closed. The two missing Codex judgments were then retried sequentially in fresh native sessions in `wZ`, with tools disabled and a 360-second per-call deadline instead of 115 seconds. Both returned without tool calls. The initial failures and successful retries are archived separately. Closed `wZ` after archiving the evidence; left parent `w1` open.
