# Staging deployment preparation — NOT approved for public exposure

These are local preparation artifacts only. Nothing here changes the droplet,
DNS, firewall, existing private receiver, workflow, or private MCP. This is a
separate ping-only application, not a staging copy of the private service. Do
not activate the nginx site until the explicit gate below is satisfied and an
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
explicit approval; no artifact here grants it. The example contains preliminary proxy limits, not evidence that effective
rate/abuse limiting has been tested or that direct-backend limits exist. Document ownership, monitoring, incident response and revocation
before approval. Do not expose the service in order to perform these checks.

Only after approval, an administrator may adapt `nginx.conf.example` in the
`http` context of the existing reviewed nginx configuration, without replacing
other sites or routing to the private MCP at 8001. It is a single HTTPS
host-specific server, not a default server; review all server precedence, SNI,
default hosts and global/inherited settings in the complete configuration. Inspect
`nginx -T` and enabled modules for inherited real-IP settings and listeners: the
proxy must be the outermost peer, with no `real_ip_header`, `set_real_ip_from`,
PROXY protocol or upstream proxy rewriting its remote address. The example does
not override inherited real-IP settings; do not activate if they apply. Incoming
forwarded IP headers are overwritten, not trusted. Authorization must continue
to pass through to the backend. If a proxy is introduced, stop and independently
redesign and test client identity and limiting. The example listens on IPv4 only,
matching current staging DNS; verify there is no AAAA record or other IPv6
listener routing to this service. Before enabling IPv6, independently design and
test prefix-aware limiting: full IPv6 address keys allow /64 address rotation.
Before activation, the operator **must** identify the effective default server for
every applicable address and port in the complete `nginx -T` output, including
implicit defaults (the first server for a listener), wildcard and specific-address
listeners, and any IPv6 listeners. Verify that missing or unknown SNI cannot route
to staging or a private service, and that unexpected Host headers cannot route
there either. From an independent client, test no SNI, an unknown SNI, and the
staging SNI with an unexpected Host; check both handshake and HTTP routing without
sending credentials. Test each exposed address family and listener. If any check
fails, stop: do not activate until the host's owner has reviewed and corrected
routing without disrupting existing sites.

Only where review confirms there is no conflicting explicit default and this will
not alter existing sites' required behavior, an operator may add a separate
fail-closed default for the exact IPv4 listener, using nginx 1.19.4 or newer:

```nginx
server {
    listen 443 ssl default_server;
    ssl_reject_handshake on;
    return 444;
}
```

This is deliberately not included in the example: adding a default can conflict
with an existing default or change an implicit default and disrupt other sites.
The HTTP return also denies requests selected into this server after a successful
handshake; it does not replace the mandatory SNI and Host tests. Review other
listeners separately; do not enable IPv6 merely to install this block. Validate
the complete configuration and repeat the independent checks after any authorized
reload. Also inspect the full host configuration for inherited TLS settings and
HSTS; the example requires TLS 1.2 or newer but does not enable HSTS. Decide and
test HSTS scope and rollout separately to avoid affecting other hosts.

The example keys nginx's built-in shared-memory limit_req and limit_conn zones
to the actual binary remote address: 10 requests/minute with a burst of 5,
and 4 concurrent requests per address, returning 429 on rejection. Shared NAT
clients share a budget; HTTP/2 concurrent requests count individually. Rejections
have no `Retry-After` header: verify pilot clients tolerate bare 429 responses and
back off appropriately. Limiter rejections log at warn with client IPs. These
are preliminary conservative values, not a DDoS defense, and require real
workload and rejection testing. Each zone uses 10 MB; zone exhaustion and
restarts can affect enforcement. The 64 KB body limit, header/body timeouts,
keepalive and upstream timeouts are not a complete defense; inspect inherited
header size and connection settings and test slow clients, streaming and the
direct backend separately. The 300-second upstream read timeout is an idle
interval, not a total stream lifetime.

### Separately approved HTTP-01 certificate bootstrap and renewal

The MCP public activation gate above remains BLOCKED. A public ACME-only HTTP
route requires its own explicit operator/security approval; it does not approve
public MCP access. Before any change, the authorized DNS operator must verify
the staging A record points to the intended host and that no AAAA record directs
validation elsewhere. Verify external TCP port 80 reachability and firewall policy;
obtain separate authorization for any DNS or firewall change. Do not perform these
changes from this repository. The CA must be able to retrieve the challenge over
public HTTP. Never place credentials or application content in the webroot.

First inspect `nginx -T`, every port 80 listener and effective default (including
implicit defaults, specific addresses and IPv6), existing challenge locations,
server names and inherited configuration. The standalone
`nginx-http01.conf.example` is an IPv4-only, exact-host server serving only
`/.well-known/acme-challenge/` from the dedicated
`/var/lib/di-staging-acme` webroot; other paths return 404, and it never proxies.
Its Host guard rejects missing or unexpected Host values when selected. It cannot
control what an existing default server does for unknown hosts: verify unknown and
missing Host requests fail closed without reaching staging or private services on
all relevant listeners. If a new default is necessary, stop unless the host owner
explicitly approves a separately reviewed change that cannot disrupt other sites;
adding a default can replace an implicit default or conflict with an explicit one.
Do not install this example if any conflict or inherited behavior makes it unsafe.
Do not change or replace existing sites. Review URI handling, symlinks, access
permissions and inherited nginx settings; keep the dedicated webroot writable only
by the privileged Certbot process and readable by nginx, never by the backend.

After that separate approval, create the dedicated webroot under host policy,
install only the HTTP example as a separate site, validate the *complete* config
with `nginx -t` and reload only if validation succeeds. Independently test the
exact hostname and a disposable challenge file from outside, verify non-challenge
paths return 404, and test missing/unknown Host and all exposed address families.
Remove the disposable file. Do not send bearer tokens over HTTP. Then an authorized
operator may issue the certificate (substitute a monitored contact email):

```sh
sudo certbot certonly --webroot -w /var/lib/di-staging-acme \
  -d mcp-staging.directedideation.com --email YOUR-EMAIL --agree-tos
```

Do not use `certbot --nginx`: it can rewrite existing configuration. Confirm the
issued certificate and both files under
`/etc/letsencrypt/live/mcp-staging.directedideation.com/` exist before even
validating the TLS example. This ordering avoids nginx startup/reload depending on
nonexistent certificate files. Leave the HTTP challenge route available for renewals;
it never redirects or proxies to MCP. Only after the separate MCP activation gate
is satisfied may the TLS example be installed, validated and reloaded as described
above. Verify HTTPS and hostname independently.

Use the distribution's Certbot renewal timer, verify it is enabled and scheduled
(e.g. `systemctl is-enabled certbot.timer` and `systemctl list-timers --all`),
and monitor timer failures and certificate expiry. Install a root-owned,
non-writable-by-others executable deploy hook under
`/etc/letsencrypt/renewal-hooks/deploy/`, scoped to the staging lineage so it
does not reload for unrelated certificates:

```sh
#!/bin/sh
set -eu
[ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/mcp-staging.directedideation.com ] || exit 0
nginx -t && systemctl reload nginx
```

Review the distribution's Certbot and systemd integration before installation.
Test the hook's failed-validation path (no reload) and successful path safely;
test `certbot renew --dry-run --run-deploy-hooks` where supported, inspecting
output, timer status and nginx reload logs. Dry-run hooks may use existing live
certificates and a dry run does not prove future production renewal. Independently
inspect the served certificate after an actual renewal and alert on failures. If
the timer, hook or dry run cannot be verified, stop and resolve it before relying
on automatic renewal. Preserve other certificate lineages and services.

The example disables nginx access logs and Uvicorn access logs are disabled;
verifier claim-bearing logs are suppressed. This is not a guarantee of redaction:
nginx error logs (including limiter rejections), inherited logging, other
middleware and operators can still record sensitive IPs, URLs, headers,
exceptions or token data. Independently inspect and test logging with synthetic
credentials before activation; do not log request headers/bodies or bearer tokens
and avoid query-string credentials. Log rotation limits disk usage, not data
sensitivity. Do not rely on suppressing all error logs as an audit system.

## Teardown

If a site was separately activated, first remove only its staging nginx site,
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
