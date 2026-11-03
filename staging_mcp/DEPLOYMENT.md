# Staging deployment preparation — NOT approved for public exposure

These are local preparation artifacts only. Nothing here changes the droplet,
DNS, firewall, existing private receiver, workflow, or private MCP. This is a
separate ping-only application, not a staging copy of the private service. Do
not activate the Caddy site until the explicit gate below is satisfied and an
operator approves it. The remaining WorkOS token-type semantics, rate limiting,
and independent public security review are **not complete**. It is not ready
for internet exposure. Read README.md for the authentication limitations.

## Isolation and local preparation

The staging build context is only this directory, further restricted by its
`.dockerignore`; it does not include production source, environment files,
credentials, metrics, or deployment scripts. It has no mounts, volumes, Docker
socket, or production secrets. Compose uses a distinct project/network and
loopback host port 8765, not the private service's 8001. Containers on the
staging network and host users can reach the backend directly; Docker/root
administrators can bypass isolation. Docker Engine 28+ and independent host,
cloud, IPv4 and IPv6 network checks are required; older Docker can expose
localhost-published ports to adjacent hosts. Do not attach other containers.
Loopback is not authentication. This is not VM-level isolation; use a separate
host if that is required. Confirm port 8765 is unused before starting.

The image runs as an unprivileged numeric user, uses a read-only root with a
size-limited /tmp tmpfs, drops
capabilities, disables privilege escalation and has CPU, memory, PID and log
rotation limits. It needs outbound HTTPS to the staging issuer's JWKS endpoint;
it does not have an egress firewall. The direct backend has no request-body size
limit; the example proxy caps bodies at 64 KB, so do not treat direct network
access as safe. Limits and runtime behavior must be verified on the target
Docker/Compose version. The build uses a hash-checked export of all repository runtime dependencies,
including packages not needed by staging. Regenerate it after lock changes with
`uv export --locked --no-dev --no-emit-project --no-header -o staging_mcp/requirements.lock`.
The base image tag remains mutable: no digest was verified, so select and verify
a real digest before any trusted deployment. Binary wheels are required; an
unsupported target may fail the build. Build with a trusted package source.
The local HTTP healthcheck expects an unauthenticated 401; it is only a
liveness check, not proof of JWKS availability, valid tokens or external access.

On a local machine only, from the repository root, with Docker and Compose v2:

```sh
export WORKOS_STAGING_ISSUER=https://YOUR-STAGING-ISSUER
export WORKOS_STAGING_ALLOWED_SUBJECTS=user_EXAMPLE
# Replace both placeholders with non-production values; never commit credentials.
docker compose -p di-staging -f staging_mcp/compose.yaml config --quiet
docker compose -p di-staging -f staging_mcp/compose.yaml build
docker compose -p di-staging -f staging_mcp/compose.yaml up -d
```

Issuer must be a canonical lowercase HTTPS origin; subjects must be exact
comma-separated WorkOS user IDs, without spaces or wildcards. Missing values
fail Compose interpolation and malformed values fail application startup.
Allowlist changes require recreation. Do not source the production `.env`; run
from a clean environment and use only staging tenant settings. The Compose
configuration contains no OAuth client secret or token. Treat subject IDs and
operator environment as sensitive, and do not paste rendered config or tokens
into logs or tickets. Confirm the actual listener and process with `docker
compose -p di-staging -f staging_mcp/compose.yaml ps` and `docker inspect`;
check startup failed for invalid settings, test authentication and verify both
IPv4 and IPv6 from an independent host. An HTTP request must use Host
`mcp-staging.directedideation.com`; do not put bearer tokens on a command line
or send them over untrusted plaintext. Local loopback HTTP is not TLS.

## Explicit public activation gate — currently BLOCKED

A qualified operator must first independently review the app, dependencies,
image, proxy and host, verify real WorkOS access-token versus ID-token semantics
and issuer/JWKS behavior, implement and test bounded request handling (including direct-backend body,
header, concurrency and timeout limits) and effective rate/abuse limiting, and
complete a public security review. Test auth, denial, oversized bodies, TLS,
redaction, resource isolation, IPv4/IPv6 exposure, failure and teardown. Obtain
explicit approval; no artifact here grants it. No rate limiting is provided by
the example. Document ownership, monitoring, incident response and revocation
before approval. Do not expose the service in order to perform these checks.

Only after approval, an administrator may adapt `Caddyfile.example` as a
separate site in the existing reviewed Caddy configuration, without replacing
other sites or routing to the private MCP at 8001. Validate and reload using the
host's own Caddy installation procedure and verify the resulting complete
configuration, including site precedence and any global logging directives.
Confirm Caddy supports `request_body` (Caddy 2.10+); this limits body reads, not
headers, connection counts or request rate. Configure and test additional
limits separately. Caddy automatic public HTTPS requires the staging hostname's
DNS to point to the host and successful ACME validation over port 80/443 (or a
separately configured DNS challenge). Preserve existing DNS/firewall rules and
services; do not change them without separate authorization. Verify a trusted
certificate and hostname from an independent client, and never fall back to
public plaintext. A proxy on the host must connect to 127.0.0.1:8765; a proxy in
a container needs a separately reviewed network design, not this address.

No Caddy access `log` directive is included and Uvicorn access logs are disabled;
verifier claim-bearing logs are suppressed. This is not a guarantee of redaction:
existing global Caddy logging, errors, other middleware and operators can still
record sensitive URL, header, exception or token data. Independently inspect and
test logging with synthetic credentials before activation; do not log request
headers/bodies or bearer tokens and avoid query-string credentials. Log rotation
limits disk usage, not data sensitivity. Do not rely on suppressing all error
logs as an audit system.

## Teardown

If a site was separately activated, first remove only its staging Caddy site,
validate and reload the existing configuration, and externally verify it no
longer routes. Follow separately authorized DNS/certificate cleanup as needed;
never alter the private site's configuration. Then, from the same checkout and
with the two staging variables set, run:

```sh
docker compose -p di-staging -f staging_mcp/compose.yaml down --remove-orphans
```

This removes only that explicitly named project and its network; it does not
remove images or touch the private project. Inspect for remaining staging
containers, listeners, logs and images, and clean them up individually according
to host policy. Unset the staging environment variables. Never run broad Docker
prune or volume deletion on the shared host.
