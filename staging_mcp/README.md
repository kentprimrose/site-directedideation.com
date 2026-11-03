# Independent staging MCP test service

Code only: this does not deploy, configure DNS, provision WorkOS, or touch the
private application. It has only `ping` returning `pong`. No production
credentials or data. It must not be exposed until the integration and security
checks below have been completed. Install the repository dependencies (tested
with FastMCP 4.1.3). Run as an ASGI factory, e.g. `uvicorn
staging_mcp.server:create_app --factory --host 127.0.0.1 --port 8765` for local
inspection; the fixed Host and OAuth resource remain the staging hostname.
A separate TLS-terminating proxy and deployment are necessary for public use.

Set `WORKOS_STAGING_ISSUER` to the exact HTTPS AuthKit Connect issuer origin for
a disposable staging environment, using a lowercase ASCII DNS hostname without
path, slash, port, whitespace or credentials. Set `WORKOS_STAGING_ALLOWED_SUBJECTS` to comma-separated exact WorkOS user IDs
(e.g. `user_ABC,user_DEF`, no spaces). Missing/invalid configuration fails
startup. Allowlist is frozen at startup; restart to change it. Register exactly
`https://mcp-staging.directedideation.com/mcp` as a WorkOS resource indicator;
clients must request it, or it must be configured as the default. WorkOS issues
access tokens with that resource as `aud`. The service verifies RS256 signature
against issuer `/oauth2/jwks`, exact issuer and single-string audience, required
future expiry, optional not-before and the signed `sub`. WorkOS's MCP guide
uses access-token `payload.sub` as `userId`; allowlist actual staging user IDs,
not email, OAuth client ID, or an unverified profile claim. See
https://workos.com/docs/authkit/mcp and
https://workos.com/docs/authkit/connect/oauth/verifying-tokens .

The resource audience separates resource access tokens from ordinary OIDC ID
tokens whose audience is the OAuth client ID. This is not a cryptographic token
type discriminator: if the issuer can issue an ID token with this exact resource
audience and matching subject, it could be accepted. Confirm WorkOS tenant token
semantics before exposure. Do not invent a `typ` claim requirement: WorkOS has
not been verified to provide one. Stateless HTTP requires bearer authentication
on each request; there is no session authorization cache. Revocation is not
immediate: accepted tokens remain usable until expiry, and JWKS keys can be
cached by FastMCP. There is no rate limiting, WAF, audit, or abuse protection.
A bearer token is usable by anyone possessing it. Never log tokens; disable
proxy access/header/body logging and avoid debug logs. The verifier suppresses
its own claim-bearing logs, but framework/proxy logging must be independently
reviewed. Host validation is not a substitute for TLS or trusted proxy controls.

Offline tests use generated keys; no live WorkOS, OAuth client, proxy, TLS or
public endpoint has been tested. FastMCP 4.1.3 may serialize discovery's
issuer origin with a trailing slash; test strict client discovery against the
actual WorkOS staging tenant. Verify real claims, resource audience, user ID
mapping, token refresh, metadata, JWKS failure/rotation, client interoperability,
network controls and logging before any exposure. This is not a production
security review or a complete deployment plan.
