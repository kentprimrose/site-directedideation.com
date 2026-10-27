# Directed-Ideation MCP Plan

## Goal and assumptions

Build an agent-facing MCP server for purposeful exploration under explicit goals and constraints. Start with one trusted local operator. The host agent supplies idea generation and subjective judgments; the server structures the workflow, validates submissions, and preserves context. The MCP is separate from the static field-guide website and does not require adding a backend to it.

Hosted collaboration and autonomous execution of proposed experiments are out of scope initially. Validate that the method is useful before committing to hosted infrastructure.

## Architecture

- Build a model-independent MCP server over stdio, using an official MCP SDK in the selected implementation language.
- Separate the MCP adapter, workflow engine, versioned method definitions, and session store.
- Use a flexible, versioned workflow: frame the challenge, explore distinct directions, develop or combine ideas, evaluate, and propose experiments. Allow documented skipping and revisiting rather than enforcing a rigid wizard.
- Return structured guidance with current stage, requested action, expected submission shape, constraints, and completion conditions. Include concise text for clients with limited structured-output support.
- Keep idea generation and subjective evaluation in the host agent. The server validates structure, preserves evidence, and supplies prompts and rubrics; it must not present deterministic checks as judgments of creativity.

## Initial MCP tools

- `start_session`: capture challenge, constraints, exclusions, success criteria, and exploration budget; return a session ID and first guidance.
- `get_next_step`: return read-only guidance, including the input schema, relevant context, and bounded exploration lenses.
- `submit_step`: record framing, ideas, evaluations, or experiment proposals; support explicit advance, skip, and revisit actions. Use an expected revision and idempotency key to prevent stale writes and duplicate retries.
- `get_session`: retrieve a compact summary or full export, including provenance and unresolved assumptions.

Use a discriminated submission schema, stable error codes, and accurate MCP tool annotations. Do not depend on optional MCP client capabilities.

## State and safety

- Store sessions in local SQLite with schema and method versions, revision, stable idea IDs, and compact change history. Make mutations transactional; avoid distributed infrastructure.
- Make persistence explicit. Provide retention, deletion, and export controls before use with sensitive material.
- Treat submitted and imported text as untrusted content, not executable instructions. Preserve origin when returning it to agents.
- Do not allow arbitrary URL fetching, filesystem access, or experiment execution. Proposed next actions remain proposals requiring separate authorization.
- Bound payload size, idea count, returned history, and exploration rounds. Surface budget exhaustion rather than looping indefinitely.

## Phased plan

1. **Method contract:** define stage definitions, tool schemas, representative challenge fixtures, and an evaluation rubric. Walk through several sessions manually before implementation.
2. **Local vertical slice:** implement the four tools, SQLite persistence, revision-safe submissions, export and deletion controls, and one end-to-end workflow. Verify with two MCP clients and an automated protocol harness.
3. **Agent pilot:** compare guided sessions against the same agent using a static ideation prompt, with matched model and token budget. Refine tool guidance and descriptions from traces.
4. **Expand only on evidence:** add optional methods and branching first. Add hosted HTTP, authentication, tenant isolation, quotas, and operational controls only when real multi-user requirements justify them.

## Verification and success criteria

Test invalid submissions, stale revisions, retry idempotency, restart and resume, deletion, and bounded responses. Pilot on approximately 20 varied challenges with repeated paired runs and blinded assessment. Score constraint adherence, distinctness of approaches, usefulness, and experiment actionability; track tokens, latency, and unrecovered tool errors separately.

Provisional value gate: guided output is preferred in at least 60% of blinded comparisons at matched token budget, without worse constraint adherence. Report uncertainty; a small pilot is directional, not conclusive. Also target at least 90% of pilot sessions reaching an actionable experiment proposal without manual repair of tool calls. All deterministic state-integrity and deletion tests must pass.

## Main risk

Workflow ceremony may increase tool calls and produce homogeneous ideas without improving outcomes. Compare against the simpler prompt baseline before expanding the system. Keep server-owned multi-agent generation and hosted infrastructure out of the initial pilot.
