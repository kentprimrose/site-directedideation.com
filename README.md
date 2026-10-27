# site-directedideation.com

A static, single-page field guide to directed ideation. The deployable site is in `public/` and consists of plain HTML and CSS; it has no framework or backend runtime.

## Local development

Requirements: Node.js, npm, and [uv](https://docs.astral.sh/uv/).

Install the static-site development dependency once:

```bash
npm --prefix site install
```

Start all three local services from the repository root:

```bash
uv run dev
```

The command starts:

- FastAPI at <http://127.0.0.1:8000>
- FastMCP over Streamable HTTP at <http://127.0.0.1:8001/mcp>
- The static site at <http://127.0.0.1:3000>

Pi is configured to connect to the MCP endpoint through `.pi/mcp.json`. Trust this project in Pi and run `/reload` (or restart Pi) after starting the services. Press Ctrl-C to stop all three.

## Deploy to NameHero

Upload the **contents** of `public/` to the document root for the domain in NameHero cPanel. For the primary domain this is usually `public_html`; addon domains and subdomains use their configured document root. Ensure `index.html` is directly in that directory, with the `site/` asset directory alongside it. No build, Node installation, or server-side application is required on the hosting account.


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
