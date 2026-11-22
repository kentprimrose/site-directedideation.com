# Native harness setup for live MCP pairs

Use this with the [evaluation protocol](LIVE_MCP.md). Run the same model and effort in both arms of a pair. The enabled arm should have only the directed-ideation MCP server; the control should have no MCP servers. Do not disable or stop the server process itself to create the control condition.

## Common setup

- Open the [run log](logs/TEMPLATE.md) before starting. Record native CLI versions, exact model IDs, effort, arm order, config scope, and the MCP endpoint. When doing repeats, alternate which arm goes first.
- Run both arms from separate, empty working directories outside the repository. Do not put the case bank, method text, assessments, or the other arm's transcript there. Send the case statement and the shared protocol prompt through Herdr only after preflight. Do not load directed-ideation skills or other instructions that would give the control the method.
- The local server is currently `http://127.0.0.1:8001/mcp` (see the repo's [Pi-Bolt MCP config](../../.pi/mcp.json) for the current URL). Native harnesses do **not** inherit that config; use it as the source for the endpoint only. If the endpoint requires credentials, use the harness's supported auth and keep secrets out of commands that will be logged.
- In Herdr, create a separate workspace for each arm, with that arm's working directory as its `--cwd`. Run the appropriate native launch command in its root pane. The snippets below are shell commands for those panes; define `MCP_URL`, `RUN_ROOT`, and model variables in each pane as needed. `RUN_ROOT` is a private directory outside the repository shared by the test operator, not the answerer's current directory. Keep profile and artifact files outside the answerers' working directories.

```sh
RUN_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/live-mcp.XXXXXX")
mkdir "$RUN_ROOT/enabled" "$RUN_ROOT/control"
herdr workspace create --cwd "$RUN_ROOT/enabled" --label 'Live MCP — enabled' --env RUN_ROOT="$RUN_ROOT" --no-focus
herdr workspace create --cwd "$RUN_ROOT/control" --label 'Live MCP — control' --env RUN_ROOT="$RUN_ROOT" --no-focus
```

Use the returned root pane IDs. Keep the answerers' directories empty even when storing traces or later starting judges.

## Claude Code: session-local MCP config

Pass the intended configuration explicitly to both arms. `--strict-mcp-config` ignores other MCP sources; `--tools ""` disables built-in tools, not tools from the explicitly configured MCP server. Disable skill and slash-command expansion in both arms.

```sh
MCP_URL=http://127.0.0.1:8001/mcp
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MCP_ON=$(jq -cn --arg url "$MCP_URL" \
  '{mcpServers:{"directed-ideation":{type:"http",url:$url}}}')

# Enabled arm, in its Herdr workspace
claude --model "$CLAUDE_MODEL" --effort medium --setting-sources '' --no-chrome \
  --disable-slash-commands --tools '' --strict-mcp-config --mcp-config "$CLAUDE_MCP_ON"

# Control arm, in its Herdr workspace
claude --model "$CLAUDE_MODEL" --effort medium --setting-sources '' --no-chrome \
  --disable-slash-commands --tools '' --strict-mcp-config --mcp-config '{"mcpServers":{}}'
```

Check the explicit config before launch. If startup doesn't expose usable tool status with slash commands disabled, use a **throwaway preflight session** on each exact launch configuration, then start fresh for the case. The enabled preflight must show that the canonical tool can be called; the control must show that it cannot. Do not use preflight turns as part of the interview.

## Codex CLI: isolated profile and per-server flag

Use a dedicated `HOME` and `CODEX_HOME` for both arms. Provision auth for the test profile using supported Codex login. Do not copy credentials into test artifacts. Configure only `directed-ideation` in the test profile. The enabled and disabled flags below are per-invocation; `-c 'mcp_servers={}'` does **not** clear configured servers. Disable hosted apps as well: the native rerun found that a hosted `codex_apps` connector could provide the same method even with the local MCP entry disabled.

```sh
MCP_URL=http://127.0.0.1:8001/mcp
CODEX_MODEL=gpt-6.1-sol
export HOME="$RUN_ROOT/codex-profile"
export CODEX_HOME="$HOME/.codex"
mkdir -p "$CODEX_HOME"
codex mcp add directed-ideation --url "$MCP_URL"

# Verify each command's effective server settings; expect true, then false.
codex -c 'mcp_servers.directed-ideation.enabled=true' mcp list --json
codex -c 'mcp_servers.directed-ideation.enabled=false' mcp list --json

# Enabled arm
codex --model "$CODEX_MODEL" -c 'model_reasoning_effort="medium"' \
  --disable plugins --disable apps --disable shell_tool --enable skip_host_skill_discovery \
  -c 'mcp_servers.directed-ideation.enabled=true' --sandbox read-only --ask-for-approval never

# Control arm
codex --model "$CODEX_MODEL" -c 'model_reasoning_effort="medium"' \
  --disable plugins --disable apps --disable shell_tool --enable skip_host_skill_discovery \
  -c 'mcp_servers.directed-ideation.enabled=false' --sandbox read-only --ask-for-approval never
```

Set the same `HOME` and `CODEX_HOME` in both Herdr panes. The matching feature flags prevent hosted-app and shell access and limit unrelated skills. Verify that the control cannot find the method by any route, including hosted apps and host skills. If the installed version cannot enforce this, skip the pair. Do not use `--ignore-user-config` in only one arm. The sandbox alone does not disable MCP. Check the native session's `/mcp` view and actual discovery/call trace; a local `mcp list` does not prove that hosted apps are disabled.

## Gemini via `agy`: isolated home, sequential arms

`agy mcp enable` and `agy mcp disable` change the profile's config; they are not launch flags. Separate Herdr workspaces alone do not isolate config. The installed `agy` CLI was verified to keep MCP registrations separate between different `HOME` values. Authentication and live tool discovery still need to be verified in the test profile before using it for a real pair.

Use one dedicated `agy` home and run the arms **sequentially**. Set the same home in all setup, launch, and verification commands for this pair. If supported auth cannot be established there, log a setup blocker instead of toggling the user's everyday profile. Do not change the profile while an answerer or judge is still running under it.

```sh
MCP_URL=http://127.0.0.1:8001/mcp
AGY_MODEL=gemini-4-neon-medium
AGY_HOME="$RUN_ROOT/agy-home"
mkdir -p "$AGY_HOME"
HOME="$AGY_HOME" agy mcp add --type http directed-ideation "$MCP_URL"

# Enabled arm: enable, verify, launch. Exit before changing the state.
HOME="$AGY_HOME" agy mcp enable directed-ideation
HOME="$AGY_HOME" agy mcp list
HOME="$AGY_HOME" agy --model "$AGY_MODEL" --effort medium --mode plan --sandbox

# Control arm: disable, verify, launch fresh.
HOME="$AGY_HOME" agy mcp disable directed-ideation
HOME="$AGY_HOME" agy mcp list
HOME="$AGY_HOME" agy --model "$AGY_MODEL" --effort medium --mode plan --sandbox
```

If the control goes first, perform its entire block first after registration. Check `/mcp` or the native trace in each fresh session: connected and exposing the canonical tool in the enabled arm; disabled or absent in the control. Plan mode and sandboxing do not disable MCP, and `--disable-slash-commands` only applies to `agy` print mode. Keep the dedicated profile free of custom skills and other MCP servers. If concurrency is needed later, use two separately authenticated, verified homes rather than toggling one shared profile.

For headless `agy --print`, use an explicit session-only `--settings` permissions allowlist for the intended MCP calls, for example `mcp(directed-ideation/get_directed_ideation_method)` under `permissions.allow`. Headless MCP permissions otherwise cannot prompt. Do not use blanket permission bypass. Treat `agy` reads of the enabled server's own generated MCP tool descriptors as discovery; log them separately from unrelated file or web tool use. In print mode, verify settings from the actual launch and stream events rather than relying on plan mode to restrict tools.

## Acceptance checks before sending the case

1. Record each arm's config/discovery evidence. A configured URL alone is not proof the server is connected. If necessary, run a throwaway positive/negative discovery probe with the exact launch settings (no case or hidden brief); then close it. An assistant's claim that a tool is missing is not configuration evidence.
2. Start fresh answerer sessions. Send identical case prompts; do not coach either arm about setup in its evaluation transcript. Audit the traces afterward: successful canonical method call before the first question in the enabled arm, no tool calls in the control, and no unrelated tools in either arm. Treat ambiguous or failed verification as a setup/adherence failure, not as a clean negative result.
3. Start judges in fresh, separate Herdr sessions using the **control** config or another verified MCP-free profile. Pass only the blind judge inputs. Verify scores and evidence are saved before closing each finished Herdr workspace. Keep unfinished or unrelated sessions open.

References: [Claude Code CLI flags](https://code.claude.com/docs/en/cli-reference), [Codex CLI options](https://learn.chatgpt.com/docs/cli/reference), [Antigravity MCP configuration](https://antigravity.google/docs/mcp). Installed CLI help takes precedence if flags change.
