# THROWAWAY LOCAL-ONLY WorkOS OAuth MCP experiment

This is independent of the deployed server. Never deploy it, tunnel it, run it in a
public container/network namespace, or use production credentials/data. It binds
only `127.0.0.1:8765`, refuses untrusted Host headers, disables proxy headers and
exposes one fixed `local_ping` tool. Other local users/processes can still connect.
It is not an authorization policy: any holder of an accepted token can use it.

## Configuration and run

Use a disposable WorkOS **development** environment. In AuthKit Connect settings,
enable CIMD and/or dynamic client registration as needed by your Pi client. Add
`http://127.0.0.1:8765/mcp` as a Resource Indicator and, if Pi omits the
`resource` parameter, set that indicator as the default. WorkOS may impose
environment-specific rules on HTTP loopback resource indicators; this has not been
verified against a tenant. No API key, secret or production database is needed.

Install the repository dependencies, then run from the repository root:

```sh
export WORKOS_AUTHKIT_ISSUER='https://YOUR_AUTHKIT_DOMAIN'
.venv/bin/python local_workos_poc/server.py
```

`WORKOS_AUTHKIT_ISSUER` is the public AuthKit Connect issuer origin, HTTPS,
without a trailing slash, path, query, or credentials. Find it in the issuer
field of `https://YOUR_AUTHKIT_DOMAIN/.well-known/oauth-authorization-server`.
The server derives `/oauth2/jwks`, pins RS256, and requires signature, exact
issuer, audience `http://127.0.0.1:8765/mcp`, and a future expiry. The endpoint
and port are deliberately fixed; no host/bind override exists. Point Pi's MCP
HTTP server configuration at `http://127.0.0.1:8765/mcp` and use its OAuth
sign-in flow; exact Pi configuration/client registration support is unverified.
Do not put tokens in commands, logs, fixtures, or the repository.

Check discovery and anonymous rejection in another terminal:

```sh
curl -sS http://127.0.0.1:8765/.well-known/oauth-protected-resource/mcp
curl -i -X POST http://127.0.0.1:8765/mcp
.venv/bin/python -m pytest -q tests/test_local_workos_poc.py
```

Expected: metadata contains the local resource and AuthKit authorization server;
the POST returns 401 and a resource_metadata challenge. Offline tests use ephemeral
RSA keys, not live WorkOS JWKS. No actual Pi or WorkOS tenant sign-in has been
tested. FastMCP 4.1.3 serializes the authorization server origin in metadata with
a trailing slash even though WorkOS documents its issuer without one; strict
client issuer matching may prevent discovery. Verify this with the real Pi client
before relying on the experiment. Other unknowns include Pi CIMD/DCR support,
loopback resource indicator acceptance, JWKS/network behavior and actual WorkOS
token claims. JWKS fetch or validation failures must not grant access. No scopes,
user allowlist, persistence, refresh handling, rate limiting or production security
review are included. FastMCP may log rejected token claim values; use only test
identities. Client-side OAuth credential storage is outside this server's control.

Provider reference: https://workos.com/docs/authkit/mcp and
https://workos.com/docs/authkit/connect/oauth/verifying-tokens .
