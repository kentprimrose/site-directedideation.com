# Session handoff

## Current checkpoint

The approved tool-based local complete-method prototype is implemented in the
working tree on `main`, based on `ff0012f` (the entry-path decision). No
implementation commit or push has been made. Recheck status before resuming.

Read `PLAN.md` for the product contract and `docs/CAPABILITY_PROBE.md` for the
surface, protocol evidence, client checks, and security limits.

## Implemented surface

- `get_directed_ideation_method`: read-only, no-argument complete-method tool.
  Covers all three stages, existing-context synthesis, one-question pacing,
  opportunity/goal confirmation, distinct ideas, first action/evidence, and no
  autonomous execution.
- `get_interview_guidance`, `get_diagnostic_checks`, and
  `get_alternative_techniques`: separate compact supplementary menus with an
  optional bounded `stage` selector. No detail-retrieval operation exists.
- Removed the old `method_probe` prompt and scaffold tools. No duplicate prompt
  entry path is exposed. Native MCP prompt support is no longer required.
- Protocol tests exercise discovery, method content, stage filtering, rejected
  inputs, and absence of rejected sentinel values from errors/service logs over
  in-memory and loopback HTTP transports.

## Client validation completed

Real model-driven conversations passed in **Pi 1.4.0** (RPC) and **Codex 0.165.0**
(CLI exec/resume), using the same fictional volunteer-handoff challenge.
Each client completed six conversational turns: method retrieval, context /
opportunity / goal confirmations, seven distinct actionable approaches, and
explicitly requested supplementary retrieval with omitted and selected stages.
All four MCP calls per client succeeded and used only `{}` or allowed stage
selectors. No example context was transmitted in tool arguments.

These are conversation-level checks, not a human-operated terminal UI test.
The scripted user turns reinforced constraints and confirmations; varied,
less-directed challenges and limited-capability coverage remain follow-up work.
Pi used direct tool exposure. Deferred/codemode exposure and Gemini are untested.
See the probe document for models, call arguments, and reproduction guidance.

## Verification and review

Final verification: **52 passing tests**, Ruff lint/format, ty, active LSP
checks for source/tests, and `git diff --check` all passed. One pre-existing
`beartype`/`key_value` protocol-checking deprecation warning remains under
Python 3.15.

Independent review identified one substantive issue: the complete method needed
the supplementary-retrieval policy in its own returned text. That was fixed and
pinned by protocol assertions. Negative tests now cover invalid stages and extra
context fields for every supplementary tool on both transports. The reviewer
approved the closure check with no new blockers. Both client conversations were
rerun successfully against the final code after this fix.

## Guardrails and operational notes

- All ideation context stays client-side. MCP accepts no challenge, answers,
  goals, ideas, history, or ideation-session IDs. Tools return reusable guidance;
  they do not start or store sessions.
- The unauthenticated prototype stays loopback-only. Production ingress/body
  limits, metadata, telemetry, authentication, and rate limits remain separate
  work; the current tests are not evidence of hosted security readiness.
- Client validation used temporary isolated settings and real model requests.
  Persistent Pi/Codex configuration was not changed, and temporary credential
  copies were removed. The unrelated invalid normal Codex MCP entry was not
  touched.
- Existing dev services on ports 8000/8001 were left untouched. The separate
  loopback validation server was stopped after final checks. Automated HTTP
  tests manage their own ports.

## Development-server lifecycle command

`pyproject.toml` now registers both `dev` and `servers` entrypoints. Use
`uv run dev start|restart|stop` for tracked background services, or plain
`uv run dev` for foreground operation. Runtime state and per-service logs are
under ignored `.dev/`. Untracked listeners are never killed automatically;
older pre-lifecycle services must be stopped manually before the first start.
See `README.md` for usage and safety behaviour.

The parent verified real API/MCP/npm start, duplicate-start refusal, restart,
stop, and repeated stop with temporary state and ephemeral ports, leaving normal
services untouched. Latest full suite: **80 tests passed**; Ruff lint/format,
ty, active LSP checks for dev source/tests, and `git diff --check` passed.
The parent also reproduced and fixed Ctrl-C during startup leaving live,
untracked children; interruption and post-readiness state-write failures now
have real-process rollback tests.
Independent closure review confirmed the lifecycle blockers resolved with no
remaining blockers; its isolated dev test run passed all 28 tests.


## Next action after final verification

Review/commit the prototype if accepted. Continue phase 1 with less-directed,
varied-challenge and limited-capability validation before fixing the permanent
surface or moving to the secure hosted slice. Detailed technique guidance,
agent-initiated discovery, account/team service features, and hosted pilot
readiness are not implemented by this local prototype.
