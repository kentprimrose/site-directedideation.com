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

### Less-directed follow-up (2026-10-29; partial, mixed result)

Two fictional challenges were run against a freshly started, unauthenticated
loopback-only server, in empty temporary working directories and client homes.
No method instructions or confirmation-gate instructions were pasted into the
conversations. Both clients used the same versions and models as above. These
model requests were sent to the configured model provider; “client-side” here
means **not sent to this MCP service**, not offline or private from the model
provider. Credentials were copied to temporary homes and removed with them; the
existing port-8001 server, client configuration, and staged skill were untouched.

- **Pi, seed library:** The initial request was “Please help me with directed
  ideation. Our fictional neighborhood seed library struggles to get borrowed
  seeds returned; it has only volunteers and no budget.” The only observed MCP
  call was `get_directed_ideation_method({})`, which succeeded. Pi asked to
  confirm the context, then asked about forgetting versus the hidden return box.
  In a first four-turn attempt, two ambiguous “Yes”/“go ahead” replies did not
  identify which opportunity the user wanted; Pi repeated the choice and then
  chose the return box itself and asked for an example. It did not reach a goal.
- **Pi follow-up, same challenge:** A separate run used the same first two turns,
  then selected the return-box issue, supplied an example, and gave short
  affirmations. Pi proposed an opportunity and asked for confirmation; it later
  proposed a no-budget goal and asked for confirmation. It ultimately offered
  six directions and two proposed tests, with a first action and observation for
  those two tests, but not for each of the six directions. The ideas were
  plausibly relevant to volunteer and budget constraints, though the signs and
  arrows overlap. No action was executed. **This is not a clean gate pass:** a
  harness buffering/timeout fault disrupted turn synchronization, and a generic
  affirmation intended for the goal arrived before the goal was proposed; the
  later “Please go ahead” was treated as assent. The requested supplementary
  turn did not run. Do not use this attempt to infer strict goal confirmation or
  precise latency.
- **Codex, museum:** The first user turn was “Please use directed ideation to
  help our fictional small museum reduce long waits for wheelchair users at its
  crowded entrance, without buying equipment.” It immediately proposed a target,
  six ideas and a pilot without a context, opportunity, or goal confirmation.
  After the user clarified that deliveries shared the accessible entrance and
  only one attendant was available, it revised the ideas and dropped an
  impractical extra-staff suggestion. It proposed delivery scheduling, visitor
  priority and wait/interruption observations; feasibility and accessibility
  require real stakeholder assessment. Across four turns there were **no MCP
  tool-call events**. Thus the method was not demonstrated, the confirmation
  gates failed for this less-directed request, and no argument privacy claim can
  be inferred from absence of calls. The setup does not prove whether the tool
  was discoverable but ignored, or unavailable to this model turn. A planned
  follow-up explicitly asking for MCP retrieval never started because the Pi
  harness failed.

**Reproduction:** Use the loopback server command above on an unused port and
create isolated client homes. Put only `{"mcpServers":{"directed_ideation":
{"url":"http://127.0.0.1:PORT/mcp","exposure":"direct"}}}` in Pi's
`mcp.json` and `[mcp_servers.directed_ideation]` plus
`url = "http://127.0.0.1:PORT/mcp"` in Codex's `config.toml`. Securely copy
only the necessary existing auth files into the temporary homes and remove the
homes after the run. Set `PI_CODING_AGENT_DIR` and `CODEX_HOME` accordingly.
Run Pi RPC with `--no-session --no-extensions -e builtin:mcp --no-skills
--no-prompt-templates --no-context-files --tools 'mcp__directed_ideation__*'
--model openai/gpt-6.1-terra --thinking low`. Send JSON `prompt` commands and
wait for `agent_settled` before the next turn. For Codex run `codex exec --json
--skip-git-repo-check --sandbox read-only -m gpt-6.1-sol -c
'model_reasoning_effort="low"'` in the empty directory, then use `codex exec
resume THREAD_ID --json --skip-git-repo-check -m gpt-6.1-sol -c
'model_reasoning_effort="low"'` for later turns. Supply the fictional initial
requests above; follow up naturally, confirming or revising what the agent
actually asks rather than supplying gate instructions. Inspect JSON tool events,
arguments, outcomes and each confirmation before advancing. A harness must drain
stdout continuously: the prior select/readline implementation is a plausible
cause of its false timeouts and subsequent broken pipe (see the follow-up below).
The server was stopped and temporary homes removed; no unrelated process was stopped.

The first Pi conversation used four model turns; the interrupted follow-up
produced seven assistant turns. Pi's reported estimated model cost was about
$0.038 and $0.041 respectively (provider-reported estimates, not invoices).
Codex reported per-turn input/output tokens of 18,404/441, 37,275/741,
62,241/877, and 87,356/1,087, including cached input; no monetary cost was
reported. No reliable latency or full pilot usefulness score is claimed. These
are small, unpaired synthetic examples, not the approximately 20 varied
challenges and repeated paired runs in the plan.

**Limited-capability partial evidence:** `uv run pytest tests/test_mcp.py -q`
passed 53 tests on 2026-10-29. Its real MCP Python client extracts and asserts
single `TextContent` results for the method and menus, including over loopback
HTTP. This exercises a text-only consumption path but is **not** an independent
limited-capability interactive model client, nor does it show a model can use
text without structured content. That coverage and both clients' less-directed
complete flows and supplementary retrieval remain open before fixing the surface.


### Continued validation (2026-10-29)

A fresh loopback server on 127.0.0.1:18973, isolated temporary homes and empty
working directory were used with the same client versions and models. Model
requests went to the provider. The server and temporary credential copies were
removed afterward; port 8001, persistent settings, and the staged skill were
not changed. These are small synthetic checks, not a usefulness evaluation.

**Synchronization diagnosis and replacement.** A controlled local pipe test
wrote two lines together. After one text `readline`, `select` reported no
readable bytes while the second line was immediately available in Python's
buffer. This reproduces the proposed failure mechanism, but does not prove the
exact historical timeout cause because the old event stream was not retained.
`docs/pi_rpc_probe.py` continuously drains Pi stdout in a reader thread into a
queue, uses an absolute monotonic 120-second deadline per turn (overridable with
`PROBE_TIMEOUT`), waits for `agent_settled`, and terminates/kills the child on
failure. Seven turns settled in each of two new Pi runs with a 90-second bound.
The harness takes a JSON array of prompts on stdin and emits JSON events that
include prompts and responses; protect or delete those logs. Run it only with an
isolated `PI_CODING_AGENT_DIR`. Predetermined prompts are not adaptive and can
themselves misalign with what the model asks, as the first run demonstrated.

**Pi:** Both runs retrieved `get_directed_ideation_method({})` and confirmed
context. In the first, Pi proposed and got confirmation of the opportunity.
The next scripted reply affirmed a goal before one had been proposed, in response
to a question about box location; Pi then produced seven ideas without asking
for goal confirmation. It later acknowledged the goal had not been explicitly
confirmed. This is a synchronized run but **not a clean goal-gate pass**, and
the premature reply limits interpretation. An explicit supplementary request
produced successful `get_interview_guidance({})`, `get_diagnostic_checks`
with `{"stage":"select-goals"}`, and `get_alternative_techniques` with
`{"stage":"ideate-with-purpose"}`; Pi summarized the menus and said detailed
guidance is unavailable. A second run supplied an actual example, confirmed the
opportunity, and provided resource constraints; by turn seven Pi had proposed a
goal and asked for confirmation. It did not reach ideas because the fixed
replies did not answer its questions about beneficiaries and evidence. No action
was executed. A complete adaptive less-directed Pi flow remains open.

**Codex:** In a new museum conversation the first turn again produced seven ideas
and a pilot, without MCP calls or confirmation gates. On the next turn the user
provided the delivery/single-attendant constraint and explicitly requested the
configured MCP method. Codex successfully called
`get_directed_ideation_method({})` and asked to confirm context; it then asked
about the incident. Thus the tool was available in the *same thread* on the
next turn; this supports an ignored-or-not-selected interpretation for the
first turn but does not establish precisely what the model was shown at that
turn. A later explicit request successfully retrieved all three supplementary
menus with the same empty and bounded stage arguments listed above, and Codex
summarized them. The resumed method flow was not continued through confirmed
goal and ideas. In both clients all observed MCP arguments in these runs were
empty or the listed stage filters; no challenge or session context was sent in
them. This is example-specific, not a general privacy guarantee.

**Text fallback:** A separate minimal Python MCP SDK consumer on loopback called
all four tools, checked the single text content item and relevant markers, and
did not read structured content. It passed after correcting two harness API
mistakes (the transport yields two streams, and the error attribute is
`is_error`). The server still returned structured content; this demonstrates
that a consumer can ignore it, not that an independent limited-capability
interactive model can use a text-only server. That model-client exercise and
adaptive full flows remain gaps.
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
