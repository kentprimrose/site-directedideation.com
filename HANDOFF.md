# Session handoff

## Resume here

The user resolved the explicit-invocation decision: **prioritize standard
Pi/Codex support and approve a tool-based entry path**. `PLAN.md` records this
approval. The earlier instruction to wait for that decision is superseded.

Next action: implement the local complete-method prototype using one read-only,
no-argument MCP tool as the canonical entry point. It retrieves reusable method
instructions, not a server-side session. Keep supplementary tools separate and
all ideation context client-side.

1. Check the current branch, working tree, and recent commits.
2. Read `PLAN.md` for agreed product decisions and
   `docs/CAPABILITY_PROBE.md` for historical probe evidence and security limits.
3. Replace the probe-only prompt entry path with the complete-method tool;
   do not retain a duplicate prompt entry path. Choose and test a clear tool
   name and strict empty argument schema.
4. Implement the complete three-stage guidance and small supplementary menus
   described in the plan, using the field-guide site as the method source.
   Preserve context synthesis, user confirmations, interview pacing, and the
   supplementary-retrieval policy. Detailed technique retrieval remains ToDo.
5. Extend protocol and negative-input tests, including no rejected-value echo
   or service logging. Run the existing quality checks.
6. Validate interactive discovery, method retrieval/application, supplementary
   retrieval, and stage filtering in both Pi and Codex. Record limitations
   honestly; API-only tests are not evidence of interactive model use.

## Approved decision and evidence boundary

The canonical entry point is now an MCP tool, not an MCP prompt. Native prompt
support and custom client-side integration are not prerequisites. Gemini remains
an optional third smoke test, not a replacement for either required client.

`docs/CAPABILITY_PROBE.md` describes the earlier prompt-based probe. Its warning
against an unapproved tool fallback and its unresolved "Next decision" section
are historical and superseded by this explicit approval. Its recorded test
results remain evidence only for the existing probe; the new entry tool and
complete method have not yet been implemented or validated.

## Completed checkpoint

**`fdab1ad` on `main`**, pushed to `origin`: local MCP capability probe, tests,
client-compatibility evidence, and preceding planning-interview updates.
**`bf86001`** added the original handoff. At this decision checkpoint, `main`
was clean and reported no divergence from `origin/main` before documentation
edits. Recheck on resume; the decision documentation has not been committed.

- Probe surface: `method_probe` prompt, `interview_guidance` tool with optional
  stage filter, and retained `hello_world` scaffold tool. This is not the
  complete method or tool library.
- Prior fresh independent review found no blocking defects. Small annotation-
  coverage and integration-marker findings were addressed.
- Prior result: **22 tests passed**; Ruff lint/format, ty, active LSP diagnostics,
  and `git diff --check` passed. Tests were not rerun for this decision-only
  update. One dependency deprecation warning remains under Python 3.15
  (`beartype`/`key_value` protocol checking).
- Server-side prompt and tool behavior passed in-memory and loopback HTTP
  protocol tests. Pi discovered both tools; Codex discovered and called
  supplementary guidance without a model turn. Neither client's interactive
  complete-method flow has been demonstrated.

## Guardrails and operational notes

- Preserve the agreed context boundary: all ideation context stays with the
  calling agent; MCP requests use no arguments for the method and bounded,
  context-free selectors for supplementary guidance.
- Keep the unauthenticated prototype loopback-only. Production ingress,
  metadata, payload limits, telemetry, authentication, and rate limits remain
  separate work; see the probe document's security limits.
- Prior client checks used temporary isolated settings and no model calls.
  Normal Codex configuration had an unrelated invalid MCP transport entry;
  it was left unchanged. No persistent client settings were changed.
- An existing dev server on port 8001 was left running and may still contain
  the old scaffold. Inspect processes before testing. Automated HTTP tests
  use an OS-assigned loopback port.
