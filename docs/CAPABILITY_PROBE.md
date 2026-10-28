# MCP capability probe

## Scope and decision

This is a **local capability probe**, not the complete directed-ideation method
or a secure hosted service. It tests the MCP prompt/tool split before building
out the product.

**Finding:** the server can expose a prompt and supplementary tool over MCP.
Pi and Codex connect and discover the tool; Codex can call it with and without
the stage filter. A usable native MCP prompt entry path has **not** been
established in either installed client. Do not silently replace the agreed
prompt entry path with a tool or count manually pasted instructions as success.

## Probe surface

In `src/site_directedideation_com/mcp/__init__.py`:

- `method_probe`: no-argument MCP prompt. Instructs the agent to ask
  `What would you like to explore? [method-probe]` and wait for an answer.
- `interview_guidance`: read-only tool returning a compact sample menu.
  Optional `stage` accepts `identify-opportunities`, `select-goals`, or
  `ideate-with-purpose`. Omitted or null means guidance across all stages.
  Detailed guidance is explicitly unavailable; no detail-retrieval operation
  is exposed.
- `hello_world`: original greeting tool, retained for scaffold compatibility.

Both tools declare read-only, non-destructive, idempotent, closed-world hints.
Hints describe intent; they are not access controls.

The probe's explicit input allowlist rejects unknown tool/prompt names, extra
arguments, and invalid stage values with a generic JSON-RPC `Invalid params`
error (`-32602`). It runs before SDK argument validation, which can otherwise
echo rejected values. FastMCP execution-error masking is also enabled.

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

To serve the probe separately, choose an unused loopback port:

```bash
uv run fastmcp run src/site_directedideation_com/mcp/__init__.py:mcp \
  --transport streamable-http --host 127.0.0.1 --port 18001
```

Alternatively, `uv run dev` starts all development services, including MCP on
8001. An already-running MCP process may still have the old scaffold loaded;
restart your own process deliberately before testing new code.

### Automated protocol evidence

Verified on 2026-10-28 with FastMCP 4.1.3 and MCP Python SDK 2.3.0:

| Check | In memory | Loopback HTTP |
|---|---|---|
| Discover both tools and read-only annotations | pass | pass |
| Discover and retrieve zero-argument `method_probe` | pass | pass |
| Retrieve distinctive question instructions | pass | pass |
| Supplementary tool with omitted/null stage | pass | pass |
| Supplementary tool with each valid stage | pass | pass |
| Reject invalid stage strings, lists, objects, and numbers | pass | pass |
| Reject extra arguments to either tool or the prompt | pass | pass |
| Reject unknown tool/prompt names | pass | pass |
| No sentinel echo in rejection errors or captured service logs | pass | pass |

Repository result: **22 tests passed**. One dependency deprecation warning
originates in `beartype`/`key_value` protocol checks under Python 3.15.

Rejection assertions execute through the MCP client, inside its lifetime, not
only through direct server calls. Logs are captured at DEBUG. Client-side
`mcp.client` logs are excluded from the service-log assertion: the HTTP client
logs its own outgoing arguments at DEBUG, and the caller controls those logs.

## Installed-client evidence

Checks used temporary client configuration and an isolated loopback server;
no model requests were made and no persistent Pi/Codex settings were changed.
These checks establish connection/API behavior, **not interactive model use**.

| Client | Connection/discovery | Supplementary call | Native MCP prompt entry path |
|---|---|---|---|
| Pi 1.4.0 | `pi mcp list --json` connected and listed both tools | Not exercised through Pi | Not found in inspected built-in integration; interactive invocation not demonstrated |
| Codex 0.165.0 | App-server connected and listed both tools | Passed through `mcpServer/tool/call`, omitted stage and `select-goals` | No prompt discovery/retrieval operation found in generated app-server API; interactive invocation not demonstrated |
| Gemini | Not tested | Not tested | Optional follow-up |

### Evidence and limitations

- Pi's installed `docs/mcp.md` describes tools/resources, not MCP prompt
  invocation. The inspected built-in MCP client
  (`dist/bundle/chunks/chunk-N43LRJ4N.js`) has tool/resource operations, but no
  `listPrompts`, `getPrompt`, `prompts/list`, or `prompts/get`. The MCP adapter
  (`chunk-EGE5YVUM.js`) discovers tools on connection. Pi's local prompt
  templates are a different feature, not proof of MCP prompt support.
- Codex's generated schema (`codex app-server generate-json-schema --out DIR`)
  exposes `mcpServerStatus/list`, `mcpServer/tool/call`, and
  `mcpServer/resource/read`, but no prompt retrieval operation. Its inventory
  relays the server's advertised `prompts` capability; that does **not** mean
  Codex makes those prompts usable.
- Codex API checks initialized an ephemeral read-only thread and invoked tool
  calls directly, without a model turn. Temporary `CODEX_HOME` isolated the
  probe because normal user configuration produced an unrelated
  `invalid transport` error in an existing MCP entry. That entry was untouched.
- Pi discovery used temporary `PI_CODING_AGENT_DIR` configuration with offline
  mode and telemetry disabled. The existing project configuration remains
  unchanged.

To complete interactive checks, connect the client to the probe, inspect its
MCP interface, and attempt native discovery/invocation of `method_probe`.
If an actual prompt path exists, confirm the marker appears without manually
pasting the prompt. Then explicitly ask the agent to fetch interview guidance
and inspect the tool call. Record failures as limitations, not as passes.

## Security limits

The probe accepts no supported session-content arguments and has no session
persistence. Its input boundary covers the listed operations only. It is not
a general schema validator, body-size limiter, or ingress hardening layer.
Malformed JSON-RPC envelopes, metadata, request-body limits, production logging,
traces, analytics, authentication, and rate limits require separate work before
hosting. Captured-log tests do not establish that arbitrary deployment telemetry
is safe. Keep this unauthenticated probe on loopback.

## Next decision

Before implementing the full method prompt, resolve how explicit invocation
works in the target clients. Options require an explicit product decision:
choose a prompt-capable client, add a client-side integration, or revise the
canonical entry path. Gemini remains an optional check, not an automatic
replacement for either required client.
