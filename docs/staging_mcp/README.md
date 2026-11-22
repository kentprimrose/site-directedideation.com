# Independent staging MCP test service

Code only: this does not deploy, configure DNS, provision WorkOS, or touch the
private application. It exposes the four canonical directed-ideation tools and `ping` returning `pong`, all behind the same authentication. Tool content and stage filtering come from the local prototype; no metrics are recorded by staging. No production
credentials or data. Pilot exposure remains blocked pending the integration and
security checks below; see DEPLOYMENT.md for the separately approved one-time
compatibility-test exception. Install the repository dependencies (tested
with FastMCP 4.1.3). Run as an ASGI factory, e.g. `uvicorn
staging_mcp.server:create_app --factory --host 127.0.0.1 --port 8765` for local
inspection; the default Host and OAuth resource remain the staging hostname.
For the planned hostname migration only, set `STAGING_MCP_HOST=mcp.directedideation.com`;
the only other permitted value is the default `mcp-staging.directedideation.com`.
The selected hostname pins both Host validation and the OAuth resource audience.
This setting does not change DNS, TLS, nginx, or WorkOS. See the migration plan
in DEPLOYMENT.md before changing it.
A separate TLS-terminating proxy and deployment are necessary for public use.

Set `WORKOS_STAGING_ISSUER` to the exact HTTPS AuthKit Connect issuer origin for
a disposable staging environment, using a lowercase ASCII DNS hostname without
path, slash, port, whitespace or credentials. Set `WORKOS_STAGING_ALLOWED_SUBJECTS` to comma-separated exact WorkOS user IDs
(e.g. `user_ABC,user_DEF`, no spaces). Missing/invalid configuration fails
startup. Allowlist is frozen at startup; restart to change it. Register the selected resource (`https://mcp-staging.directedideation.com/mcp`
by default, or `https://mcp.directedideation.com/mcp` after cutover) as a WorkOS resource indicator;
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
cached by FastMCP. The direct backend has no rate limiting; the example proxy
has preliminary rate and connection limits, not a complete abuse defense. There
is no WAF or complete audit system.
A bearer token is usable by anyone possessing it. Never log tokens; disable
proxy access/header/body logging and avoid debug logs. The verifier suppresses
its own claim-bearing logs, but framework/proxy logging must be independently
reviewed. Host validation is not a substitute for TLS or trusted proxy controls.

Offline tests use generated keys. Live WorkOS tokens and the droplet proxy with
TLS have also been tested on loopback as described in DEPLOYMENT.md; external
client and public endpoint compatibility testing remains incomplete. The protected-resource metadata preserves the
configured issuer without a trailing slash, tested offline with FastMCP 4.1.3;
strict client discovery still needs testing against the actual WorkOS staging
tenant. Verify real claims, resource audience, user ID
mapping, token refresh, metadata, JWKS failure/rotation, client interoperability,
network controls and logging before any exposure. This is not a production
security review or a complete deployment plan.

The backend independently caps each `/mcp` request body at 64 KiB, including
streamed bodies, before dispatch. Invalid or inconsistent Content-Length is
rejected. This is a per-request bound, not a concurrency or read-time bound:
many simultaneous or slow clients can still exhaust connection or aggregate
memory capacity. Keep the backend private behind the configured proxy and apply
connection, concurrency and timeout limits at the deployment boundary.
