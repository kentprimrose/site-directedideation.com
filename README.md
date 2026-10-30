# site-directedideation.com

A static, single-page field guide to directed ideation. The deployable site is in `site/public/` and consists of plain HTML and CSS; it has no framework or backend runtime.

## Local development

Requirements: Node.js, npm, and [uv](https://docs.astral.sh/uv/).

Install the static-site development dependency once:

```bash
npm --prefix site install
```

Configure metrics before starting MCP; tool calls require explicit `METRICS_ENV`
and `METRICS_DB` settings and a writable database directory. From the repository
root, create the local defaults once (do not overwrite an existing `.env`):

```bash
cp .env.example .env
mkdir -p .dev
```

Start all four local services from the repository root:

```bash
uv run dev
```

The command starts:

- FastAPI at <http://127.0.0.1:8000>
- FastMCP over Streamable HTTP at <http://127.0.0.1:8001/mcp>
- The read-only admin dashboard at <http://127.0.0.1:8002/>
- The static site at <http://127.0.0.1:3000>

Press Ctrl-C to stop all four. Foreground mode also catches `SIGTERM`, so no
orphan process groups are left behind when the command is terminated by a
supervisor or shell.

#### Background lifecycle

Run the services in the background and return to your shell:

```bash
uv run dev start
```

Restart or stop the tracked servers:

```bash
uv run dev restart
uv run dev stop
```

An optional `servers` alias exposes the same subcommands (`uv run servers start`,
etc.).

State, logs, and the runtime lock live under `.dev/` (ignored by git):

- `.dev/dev-server-state.json` – PIDs, process groups, ports, and recorded command
  signatures for the current run.
- `.dev/logs/` – one log file per service, including `admin.log`.
- `.dev/dev-server.lock` – prevents concurrent `start`/`restart`/`stop` calls.

`start` pre-flights all dev ports (8000, 8001, 8002, 3000) before launching anything. If a
port is occupied, it aborts and prints the offending port. It does **not** kill
untracked or orphan processes automatically; investigate with
`lsof -i :<port>` and stop them manually before trying again.

After launching, `start` waits up to 30 seconds for every service to bind its
port. If any service exits or fails to become ready in time, the command stops
anything that was already launched, removes the state file, and reports the
failure with log paths.

`stop` and `restart` only terminate processes that can be verified as owned:
the recorded PID must equal its process group, the process group must still
exist, and the running command line must contain a unique identity token that
was injected at launch. Processes that cannot be verified (stale or reused
PIDs, missing identity, inaccessible command line) are skipped and left in the
state file; `stop`/`restart` return a non-zero exit code so the user can
investigate before retrying.
Pi is configured to connect to the MCP endpoint through `.pi/mcp.json`. Trust
this project in Pi and run `/reload` (or restart Pi) after starting the
services.

### MCP prototype surface

The local MCP server exposes one canonical explicit-invocation tool,
`get_directed_ideation_method`, plus three supplementary read-only tools:
`get_interview_guidance`, `get_diagnostic_checks`, and `get_alternative_techniques`.
All context stays client-side; the tools accept no session content and the
supplementary tools accept only an optional stage filter. See
`docs/CAPABILITY_PROBE.md` for the full surface, test results, and successful
Pi/Codex conversational validation, including its limitations.

#### Local aggregate telemetry

The prototype counts successful guidance tool calls by fixed tool name, and
successful supplementary calls by fixed stage filter (or `unfiltered` for
omitted/null). These are separate totals, not tool-by-stage records. Rejected
calls and tool errors do not count. It records no request bodies, free text,
identifiers, account associations, timestamps, connections, or call sequences.
These totals are usage counts, not session or user counts; a stage filter is
not evidence of progress. Low counts can still reveal usage to someone with
access, and repeated snapshots can reveal changes over time.

Counters are persisted as independent bounded totals in SQLite, shared between
workers and process restarts. The separate read-only admin dashboard displays
them; see [SETUP.md](SETUP.md#mcp-aggregate-metrics-and-admin) for explicit
environment configuration, authentication and important security limitations.
The MCP server remains a local-only prototype, not a public production service.

## Deploy to NameHero

Upload the **contents** of `site/public/` to the document root for the domain in NameHero cPanel. For the primary domain this is usually `public_html`; addon domains and subdomains use their configured document root. The document root should contain `index.html` and a `site/` subdirectory with the stylesheet. No build, Node installation, or server-side application is required on the hosting account.


## Requirements

- The exact Python version recorded in `.python-version`
- [uv](https://docs.astral.sh/uv/)
- Optional: [direnv](https://direnv.net/)


## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Apply automatic formatting and safe lint fixes:

```bash
uv run ruff format .
uv run ruff check --fix .
```


## CI

Install exactly the dependencies recorded in `uv.lock`:

```bash
uv sync --all-groups --frozen
```
