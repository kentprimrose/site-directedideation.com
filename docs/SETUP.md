## Local setup

Install Node.js, then run:

```bash
npm --prefix site install
npm --prefix site run dev
```

The local server serves `site/public/` and reloads the browser when files change. For hosting, upload the contents of `site/public/` to the NameHero domain's document root (typically `public_html` for the primary domain).


## Setup

```bash
uv sync --all-groups --locked
source .venv/bin/activate
```

If you use direnv:

```bash
direnv allow
```

## MCP HTTP request boundary

The local MCP HTTP app limits each request body to 65,536 bytes, including
streamed/chunked bodies and requests without `Content-Length`. It checks a
single valid decimal `Content-Length` early, then counts actual received bytes
before passing the complete body to the MCP transport. Oversized bodies receive
HTTP 413; malformed or duplicate length headers receive HTTP 400. These boundary
responses are fixed text and do not include or log the body. Requests at or below
the limit still go through normal MCP validation. The limit applies to both
streamable HTTP and legacy SSE HTTP endpoints, not in-memory or stdio transport.

This is not authentication, rate limiting, a connection or read timeout, or a
limit on concurrent requests, headers, server/proxy buffering, or logging by
other components. A slow sender can hold a connection; each concurrent request
can consume up to the limit plus server buffers. HTTP framing is handled by the
ASGI server. Keep the MCP service local and do not send sensitive session
context; this pilot measure does not make it production-ready.

## MCP aggregate metrics and admin

Copy `.env.example` to `.env`, create `.dev` (`mkdir -p .dev`), and restart
MCP. Both MCP and admin use python-dotenv's default upward search from the
metrics module's directory to locate `.env` (existing process environment takes
precedence). Set `METRICS_DB` to the same SQLite
file in both processes; its parent directory must already exist and be writable.
`METRICS_ENV` must explicitly be `development` or `production`. Missing or
invalid configuration fails closed. The database must be on a local filesystem;
restrict its directory and backups to the service account. SQLite locks and
transactions combine workers and atomically increment both independent totals.
A database write failure fails the MCP call; monitor disk space and backups.

The `uv run dev` foreground and managed lifecycle also starts the dashboard at
<http://127.0.0.1:8002/>. To start the separate local read-only dashboard alone:

```bash
uv run uvicorn site_directedideation_com.admin:app --host 127.0.0.1 --port 8002
```

In explicitly configured development it has no login; never expose it to an
untrusted network. In production startup requires `METRICS_ADMIN_USER_SHA256`
and `METRICS_ADMIN_PASSWORD_SCRYPT` (format `salt_hex:digest_hex`). Generate
these hashes offline, using a unique random 16-byte salt and a high-entropy
password, for example in a private Python session:

```python
import hashlib, secrets

user = input("User ID: ")
from getpass import getpass

password = getpass("Password: ")
salt = secrets.token_bytes(16)
print("METRICS_ADMIN_USER_SHA256=" + hashlib.sha256(user.encode()).hexdigest())
print(
    "METRICS_ADMIN_PASSWORD_SCRYPT="
    + salt.hex()
    + ":"
    + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
)
```

Store hashes securely in the service environment, not in source control. Basic
auth requires HTTPS at a trusted reverse proxy, network restrictions, request
rate limiting, and log redaction; the app itself provides none of these. Keep
it bound to loopback behind that proxy. The MCP server is a local prototype and
is **not** authenticated or production-hardened: do not expose it publicly.
The static site is not an admin hosting environment. An operator must deploy
and protect this separate Python service. Counters contain no per-call records,
identifiers, timestamps, request bodies, or session context, but small counts and
repeated snapshots can reveal usage. SQLite files, backups and filesystem
metadata require access controls and retention policies. Counts are not users
or sessions; no historical reporting is provided.
