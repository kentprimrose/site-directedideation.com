# Session handoff

## Current checkpoint

The local complete-method prototype, directed-ideation skill, dev-server lifecycle,
and SQLite aggregate metrics are implemented. The static field guide is deployable
separately; the unauthenticated MCP server remains a loopback-only prototype, not
a hosted production service. Recheck `git status` and history before resuming; do
not assume this handoff describes the current working tree.

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

The latest full suite run passed **92 tests**, with one `beartype`/`key_value`
protocol-checking deprecation warning under Python 3.15. Ruff lint/format, ty,
and `git diff --check` passed after formatting the Python example in `SETUP.md`.
The historical client conversations and independent reviews were not rerun in
that check.

Earlier independent review identified a missing supplementary-retrieval policy
in the complete method; it was added and pinned by protocol assertions. Negative
tests cover invalid stages and extra context fields for every supplementary tool
on both transports. The reviewed policy has since been superseded in `PLAN.md`:
agent-initiated supplementary retrieval is permitted when useful or needed. The
MCP method response and its documented response and protocol tests now reflect
that policy.

## Guardrails and operational notes

- All ideation context stays client-side. MCP accepts no challenge, answers,
  goals, ideas, history, or ideation-session IDs. Tools return reusable guidance;
  they do not start or store sessions.
- The unauthenticated prototype stays loopback-only. Production ingress/body
  limits, production telemetry controls, authentication, and rate limits remain
  separate work; the current tests are not evidence of hosted security readiness.
- Successful calls increment independent bounded tool and stage-filter totals in
  SQLite; a separate read-only admin dashboard displays them. Configure both with
  explicit metrics settings and protect the database and backups. See `SETUP.md`
  for dashboard authentication and its production limitations.
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
services untouched. At that historical checkpoint, 80 tests passed, along with
Ruff lint/format, ty, active LSP checks for dev source/tests, and `git diff --check`.
The parent also reproduced and fixed Ctrl-C during startup leaving live,
untracked children; interruption and post-readiness state-write failures now
have real-process rollback tests.
Independent closure review confirmed the lifecycle blockers resolved with no
remaining blockers; its isolated dev test run passed all 28 tests.

Later tests and checks are summarized above; historical client conversations and
independent reviews have not been repeated for the latest changes.


## Next actions

1. Validate the updated supplementary retrieval policy in real client sessions;
   the MCP method, response documentation, and protocol tests now permit
   agent-initiated retrieval without sending session context.
2. Continue phase 1 with adaptive, less-directed, varied-challenge and
   limited-capability interactive-client validation before fixing the permanent
   surface. Later partial Pi/Codex checks and text-only consumer evidence are in
   `docs/CAPABILITY_PROBE.md`; complete adaptive flows remain open.
3. Plan and implement the secure hosted service slice, then complete the legal,
   operational, privacy and independent security work required for the US pilot
   in `PLAN.md`. Do not expose the current MCP prototype publicly.

Detailed technique guidance, agent-initiated discovery, account/team service
features, and hosted pilot readiness are not implemented by this local
prototype.
