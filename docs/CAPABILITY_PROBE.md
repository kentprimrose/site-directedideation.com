# MCP capability and method prototype

## Scope and decision

This document records the **local MCP prototype** for the directed-ideation
method. It is not the secure hosted service.

**Decision:** the canonical explicit-invocation path is a single read-only,
no-argument MCP tool named `get_directed_ideation_method`. This supersedes the
earlier probe's `method_probe` MCP prompt. Native MCP prompt support and custom
client-side integration are not prerequisites for the first prototype. Gemini
remains an optional third smoke test, not a replacement for Pi or Codex.

The server returns reusable stage guidance; the calling agent owns all session
context and never sends it to the service.

## Current prototype surface

In `src/site_directedideation_com/mcp/__init__.py`:

- `get_directed_ideation_method`: read-only, no-argument MCP tool. Returns the
  complete three-stage method guidance (identify opportunities, select goals,
  ideate with purpose), including context synthesis confirmation, one-question
  pacing, opportunity/goal confirmation, first action and observable evidence
  per idea, and the no-execution rule.
- `get_interview_guidance`: read-only tool returning a compact menu of
  interview approaches. Optional `stage` accepts `identify-opportunities`,
  `select-goals`, or `ideate-with-purpose`. Omitted or null means guidance
  across all stages.
- `get_diagnostic_checks`: read-only tool returning a compact menu of
  diagnostic checks. Optional `stage` filter as above.
- `get_alternative_techniques`: read-only tool returning a compact menu of
  directed-ideation-specific and broader creativity techniques. Optional
  `stage` filter as above.

All tools declare read-only, non-destructive, idempotent, closed-world hints.
Hints describe intent; they are not access controls.

No MCP prompts are exposed; prompt requests are rejected at the input boundary.
There is no duplicate prompt entry path.

Detailed technique guidance is explicitly unavailable; no detail-retrieval
operation is exposed or advertised as callable.

## Run and reproduce server checks

From the repository root:

```bash
uv sync --all-groups --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

The test suite exercises the real `mcp.client.Client` over in-memory and
Streamable HTTP transports. HTTP binds **127.0.0.1 on an OS-assigned port** and
shuts down afterward; it does not stop or replace the dev server on port 8001.

To serve the prototype separately, choose an unused loopback port:

```bash
uv run fastmcp run src/site_directedideation_com/mcp/__init__.py:mcp \
  --transport streamable-http --host 127.0.0.1 --port 18001
```

Alternatively, `uv run dev` starts all development services, including MCP on
8001. An already-running MCP process may still have the old scaffold loaded;
restart your own process deliberately before testing new code.

## Automated protocol evidence

Verified on 2026-10-28 with FastMCP 4.1.3 and MCP Python SDK 2.3.0:

| Check | In memory | Loopback HTTP |
|---|---|---|
| Discover four canonical tools and read-only annotations | pass | pass |
| No prompts discovered | pass | pass |
| Retrieve zero-argument `get_directed_ideation_method` | pass | pass |
| Complete method contains all three stages, context confirmation, pacing, confirmations, first action/evidence, no execution | pass | pass |
| Supplementary tools return menus for omitted/null stage | pass | pass |
| Supplementary tools filter to each valid stage | pass | pass |
| Reject invalid stage strings, lists, objects, and numbers | pass | pass |
| Reject extra arguments to complete-method tool and supplementary tools | pass | pass |
| Reject unknown tool names | pass | pass |
| Reject prompt requests (no prompt path exposed) | pass | pass |
| No sentinel echo in rejection errors or captured service logs | pass | pass |

Repository result: **52 tests passed**. One dependency deprecation warning
originates in `beartype`/`key_value` protocol checks under Python 3.15.

Rejection assertions execute through the MCP client, inside its lifetime, not
only through direct server calls. Logs are captured at DEBUG. Client-side
`mcp.client` logs are excluded from the service-log assertion: the HTTP client
logs its own outgoing arguments at DEBUG, and the caller controls those logs.

## Installed-client evidence

Final-code model-driven conversational checks passed in **Pi 1.4.0** and **Codex 0.165.0**
on 2026-10-28 using a fresh loopback HTTP server, temporary client homes, and a
synthetic volunteer-handoff challenge. The clients retrieved the method from
MCP; no method instructions were pasted into the conversation. Real model
requests were made. Persistent client configuration and the existing server on
port 8001 were left unchanged; temporary credential copies were removed.

| Client | Standard interface used | Model | Result |
|---|---|---|---|
| Pi 1.4.0 | `pi --mode rpc --no-session`, six sequential `prompt` commands, waiting for `agent_settled` | `openai/gpt-6.1-terra`, low thinking | All six conversational turns passed |
| Codex 0.165.0 | `codex exec --json --sandbox read-only`, followed by five `codex exec resume --json` turns in the same thread | `gpt-6.1-sol`, low reasoning | All six conversational turns passed |

These are automated, interactive **conversation-level** checks using standard
client interfaces, not direct MCP API calls. Human-operated terminal UI rendering,
menus, and keystrokes were **not** tested. Pi used direct tool exposure and only
the four MCP tools; Codex used its normal MCP discovery in an empty temporary
working directory with a read-only sandbox. Custom client integrations were not
required. Deferred/codemode Pi exposure remains untested.

### Conversation and tool-call evidence

Each client received the same sequence of synthetic user turns:

1. Explicitly request directed ideation for a fictional six-person volunteer
   group with missed Saturday-event handoffs, no new-software budget, and a
   two-week trial. Both models called `get_directed_ideation_method` with `{}`
   and asked for confirmation of their context synthesis.
2. Confirm the synthesis and describe two volunteers each assuming the other
   collected the keys. Both synthesized one opportunity and asked for its
   confirmation rather than advancing immediately.
3. Confirm the opportunity and propose a goal with value, evidence, agency, and
   learning constraints. Both synthesized the goal and waited for confirmation.
4. Confirm the goal and request at least six mechanisms, first actions, evidence,
   and one proposed test. Both returned seven approaches, a goal-linked
   "How might we" question, first actions, observable evidence, and one proposed
   test (Pi: owner-confirmed checklist; Codex: receiver acknowledgment). Neither
   executed actions or called supplementary
   tools during these first four turns.
5. Explicitly request interview guidance across all stages, omitting the filter.
   Both called `get_interview_guidance` with `{}` and summarized the menu.
6. Explicitly request goal diagnostics and ideation alternatives. Both called
   `get_diagnostic_checks` with `{"stage":"select-goals"}` and
   `get_alternative_techniques` with `{"stage":"ideate-with-purpose"}`. Both
   explained that detailed technique retrieval is unavailable.

The complete observed MCP call sequence in each conversation was:

```text
get_directed_ideation_method({})
get_interview_guidance({})
get_diagnostic_checks({"stage":"select-goals"})
get_alternative_techniques({"stage":"ideate-with-purpose"})
```

All four calls succeeded in each client. Inspection of the JSON event streams
confirmed that no challenge text, answers, goals, ideas, or session identifiers
were sent in these tool arguments. This is evidence for one scripted example,
not a general guarantee of model adherence. The user turns explicitly reinforced
context boundaries and confirmation gates; unprompted adherence, varied challenges,
limited-capability coverage, and usefulness evaluation remain follow-up work.

### Reproduce the conversational check

Start a fresh loopback server with the command above. In a temporary directory,
configure only that server in temporary Pi `mcp.json` or Codex `config.toml`,
using temporary `PI_CODING_AGENT_DIR` / `CODEX_HOME` values. Supply credentials
securely without printing them and remove temporary copies afterward. For Pi,
load only `builtin:mcp`, disable context files, skills, and prompt templates,
use direct exposure, and restrict tools to `mcp__directed_ideation__*`. For Codex,
use an empty working directory and the read-only sandbox. Run the six user turns
above through RPC or exec/resume, recording JSON tool events and assistant
messages. Check actual arguments and responses, not just process exit status.

### Historical probe evidence

The earlier capability probe (commit `fdab1ad`) used a `method_probe` prompt and
one `interview_guidance` tool. Its protocol tests passed, Pi discovered both
scaffold tools, and Codex called supplementary guidance through app-server
without a model turn. Native prompt invocation was not established in either
client. That limitation led to the explicitly approved tool-based entry path;
it is not a remaining prerequisite. Gemini remains optional and untested.

## Security limits

The prototype accepts no supported session-content arguments and has no session
persistence. Its input boundary covers the listed operations only. It is not
a general schema validator, body-size limiter, or ingress hardening layer.
Malformed JSON-RPC envelopes, metadata, request-body limits, production logging,
traces, analytics, authentication, and rate limits require separate work before
hosting. Captured-log tests do not establish that arbitrary deployment telemetry
is safe. Keep this unauthenticated prototype on loopback.

## Next steps

1. Expand conversational checks to less-directed user turns, varied challenges,
   and limited-capability clients before fixing the permanent surface.
2. Optionally smoke-test the human-operated Pi/Codex terminal UIs and alternative
   Pi exposure modes; the current evidence covers RPC and CLI conversations.
3. Evaluate method usefulness without collecting real user session content in
   the service. Full technique details and the hosted security slice remain
   separate work.
