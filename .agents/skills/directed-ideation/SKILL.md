---
name: directed-ideation
description: Conduct a guided directed-ideation session using the local MCP method. Use when the user explicitly requests directed ideation or invokes this skill.
---

# Directed ideation

1. Call the `directed-ideation` MCP tool `get_directed_ideation_method` with no arguments. Use its returned guidance as the authority for conducting the session.
2. Apply the method conversationally to the user's goal or problem. If none is provided, ask for one. Follow the method's pacing and confirmation gates, and carry the conversation through its stages rather than presenting the entire process as a questionnaire.
3. When supplementary guidance is useful or requested, call `get_interview_guidance`, `get_diagnostic_checks`, or `get_alternative_techniques`. Supply only an optional stage filter supported by the tool. Apply the returned guidance to the conversation locally.

Keep the user's topic, answers, goals, ideas, and other session context in the conversation; never send them as MCP tool arguments. Do not execute proposed actions on the user's behalf as part of the ideation process.

If the MCP tool is unavailable or fails, explain that the method could not be retrieved rather than claiming to conduct the MCP-backed process. Ask the user to start the project's local services, trust the project in Pi, and run `/reload` or restart Pi; then retry when the tool is available.
