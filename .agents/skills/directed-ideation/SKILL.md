---
name: directed-ideation
description: Conduct a guided directed-ideation session using the local MCP method. Use when the user explicitly requests directed ideation or invokes this skill.
---

# Directed ideation

1. Call the `directed-ideation` MCP tool `get_directed_ideation_method` with no arguments. Use its returned guidance as the authority for conducting the session.
2. Apply the method conversationally to the user's goal or problem. If none is provided, ask for one. Follow the method's pacing and confirmation gates, and carry the conversation through its stages rather than presenting the entire process as a questionnaire. Track the current stage and relevant confirmations locally from the conversation; revisit earlier stages when the user wants to.
3. When supplementary guidance is useful or requested, call `get_interview_guidance`, `get_diagnostic_checks`, or `get_alternative_techniques`. Supply only an optional stage filter supported by the tool. Apply the returned guidance to the conversation locally.

When a confirmation gate has been met and the user is ready to move on, briefly announce the completed stage and name and explain the next one before continuing. Do not treat readiness as confirmation: wait for the user's confirmation where the method requires it.

When the user asks where they are, identify the current stage, what has been confirmed, and the next step. When they ask about the process, explain its stages or answer their specific questions using the retrieved method. If the current stage or a confirmation is unclear, say so and ask the user rather than guessing. Keep these explanations conversational and resume the session at the user's pace.
Keep the user's topic, answers, goals, ideas, and other session context in the conversation; never send them as MCP tool arguments. Do not execute proposed actions on the user's behalf as part of the ideation process.

If the MCP tool is unavailable or fails, explain that the method could not be retrieved rather than claiming to conduct the MCP-backed process. Diagnose using available Pi MCP status, connection errors, and project-trust information; report only what the evidence establishes:

- If project trust prevented the project MCP configuration from loading, explain that the project is not trusted for this session. Ask the user to trust it in Pi, then run `/reload` or restart Pi and retry.
- If the MCP server or service is unavailable, report that separately and include any useful error details. Do not ask the user to start the local service.
- If the cause is unclear, say so rather than guessing. A saved trust decision alone does not prove the current session's effective trust, since overrides or extensions can change it.
