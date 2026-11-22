# 2026-11-22-01 — Simple pantry smoke test

- **Started (UTC):** 2026-11-22 00:16:27 (November 21 local time).
- **Case:** Ad hoc simple food-pantry case, before the checked-in case bank. The prompt asked for a first plan to shorten long Saturday pickup lines, to ask questions first, and to consult a planning-guidance tool if available.
- **Client and model:** Pi-Bolt in separate Herdr workspaces; `openai/gpt-6.2-sol`, medium thinking, both fresh sessions. Same visible prompt, no exchange bounds beyond asking questions first. The assistant played the coordinator from a fixed brief and answered only what was asked.
- **Status:** Both completed; smoke-only. The prompt did not require the complete method tool.

## Trace checks

| Arm | Workspace / Pi-Bolt session ID | Tool result before first question | Exchanges | Final received? |
|---|---|---|---:|---|
| MCP | `w6:p1` / `01a2009c-85d9-74cb-b2ba-e065cb0ba5f2` | Successful `get_interview_guidance`; no `get_directed_ideation_method` call | 1 | Yes |
| Control | `w7:p1` / `01a2009c-85dc-729a-ba3e-2ed355191c99` | None (`--no-mcp`) | 1 | Yes |

## Interview and outcome

Both asked where and when the line formed and what the pantry could change. Both heard that 70 of about 120 households arrived in the first hour, peak waits were around 35 minutes, one check-in volunteer took about two minutes per household, handoff was generally clear, and a floater could be reassigned. Walk-up access and client choice had to stay. Only the control asked what improvement would count and heard the **20-minute peak wait target**, no reduction in households served, and no handoff backup.

Both plans added a second check-in station for the first hour, staffed by the floater, with one shared line. The MCP plan set a **25-minute** threshold and checked for a downstream queue but did not check total households served. The control used **20 minutes**, checked households served and the handoff queue, and specified what to investigate if the pilot missed the target.

**Blind judgment:** Not scored. This record summarizes observable differences; there was no independent judge.

**Takeaway:** The control elicited a useful requirement the MCP arm missed. Both could identify the obvious first action after one exchange. This verified that one arm used live supplementary MCP guidance and the other did not; it does not evaluate the complete method. The short interview and straightforward bottleneck motivated the richer follow-up.
