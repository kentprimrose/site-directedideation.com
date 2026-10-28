# Session handoff

## Resume here

Resume the **design interview about the explicit-invocation entry path**.
Implementation of the full method waits for the user's decision on that path.

1. Check the current branch, working tree, and recent commits.
2. Read `PLAN.md` for agreed product decisions and
   `docs/CAPABILITY_PROBE.md` for test evidence, commands, and limitations.
3. Present the entry-path options and continue interviewing one question at a
   time. Record the user's decision before implementing it.

## Completed checkpoint

**`fdab1ad` on `main`**, pushed to `origin`: local MCP capability probe, tests,
client-compatibility evidence, and the preceding planning-interview updates.
The working tree was clean before this handoff was added; recheck on resume.

- Probe surface: `method_probe` prompt, `interview_guidance` tool with optional
  stage filter, and retained `hello_world` scaffold tool. This is smaller than
  the planned method prototype, not the complete method or tool library.
- Fresh independent review found no blocking defects. Small annotation-coverage
  and integration-marker findings were addressed.
- **22 tests passed**; Ruff lint/format, ty, active LSP diagnostics, and
  `git diff --check` passed. One dependency deprecation warning remains under
  Python 3.15 (`beartype`/`key_value` protocol checking).

## Finding that determines the next step

Server-side MCP prompt discovery/retrieval and supplementary-tool behavior
pass protocol tests over in-memory and loopback HTTP transports. However,
**native interactive MCP prompt invocation has not been demonstrated in either
required client**:

- **Pi 1.4.0:** connected and discovered both tools through its CLI. No prompt
  path was found in the inspected built-in integration. Tool calls through Pi
  and interactive prompt use remain untested.
- **Codex 0.165.0:** app-server connected, discovered both tools, and called
  supplementary guidance with omitted stage and `select-goals`, without a
  model turn. No prompt retrieval operation was found in its generated API.
- **Gemini:** optional, not tested; not an approved replacement for Pi or Codex.

Discuss: investigate a prompt-capable client (possibly Gemini), add client-side
integration, or explicitly revise the canonical entry path. A tool fallback or
manually pasted prompt is not an approved substitute or evidence of prompt
support. Required end-to-end client validation remains incomplete.

## Guardrails and operational notes

- Preserve the agreed context boundary: all ideation context stays with the
  calling agent; MCP requests use bounded, context-free selectors only.
- Keep the unauthenticated probe loopback-only. Production ingress, metadata,
  payload limits, telemetry, authentication, and rate limits remain separate
  work; see the probe document's security limits.
- Client checks used temporary isolated settings and no model calls. Normal
  Codex configuration had an unrelated invalid MCP transport entry; it was
  left unchanged. No persistent client settings were changed.
- An existing dev server on port 8001 was left running and may still contain
  the old scaffold. Inspect processes before testing. Automated HTTP tests
  use an OS-assigned loopback port.

## Suggested opening request

> Read HANDOFF.md, PLAN.md, and docs/CAPABILITY_PROBE.md. Check current repository
> state, then resume the design interview where we paused. Don't implement
> further changes until we resolve the explicit-invocation entry path.
