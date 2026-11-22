# Staging deployment preparation — small public pilot

These artifacts describe a separate authenticated staging application exposing the four canonical directed-ideation tools and ping, not a staging copy
of the private service. Staging has been tested on the droplet as described
below. The authorized small, non-sensitive public pilot using the authenticated guidance
application is active. The earlier ping-only exception is closed. General production
remains **BLOCKED**.
WorkOS staging is for testing only; WorkOS recommends production environments for
customer-facing use. Use a limited, explicitly approved subject allowlist and do
not put sensitive material into the pilot. Authentication limitations and remaining
risks still apply. Read README.md for the authentication limitations.

## Approved trusted-user pilot migration (not yet performed)

G1 and G2 are approved: the intended address is `https://mcp.directedideation.com/mcp`, using **WorkOS production**, a new production issuer, and an explicit allowlist of production user IDs for approximately 2–5 personally approved trusted users. This non-sensitive pilot accepts the risk of deferring legal and independent security reviews, privacy/subprocessor disclosures, US eligibility controls, and broad client validation; these are not waived and must be completed before commercial release or access outside the trusted set. General availability remains blocked. The existing WorkOS staging environment is retained for rollback, not reused as the new issuer.

The approved process is to inventory the live state read-only, preserve and verify rollback artifacts, prepare and rehearse closure and full restoration, then pre-provision, cut over and verify as described in `docs/PROD_DEPLOY_PLAN.md`. Process approval is not authorization to execute individual live changes; obtain a separate go-ahead for each. Existing examples, commands, proxy configurations and rollback artifacts below describe the current staging deployment unless explicitly stated otherwise. Do not silently replace their recorded digests.

For cutover, register the new resource in WorkOS production, collect the exact production identities through a supported controlled flow, deploy the reviewed backend with the new host, production issuer and production allowlist together, and coordinate proxy, DNS, TLS and client changes. Users must change the URL and reauthorize; old resource tokens fail audience validation. Host and audience are not accepted simultaneously. Do not put tokens in logs or command arguments.
Verify externally and on the private boundary: DNS A/AAAA and certificate identity,
no direct backend exposure, host rejection, healthy container, protected-resource
metadata and exact production issuer/resource, unauthenticated 401, rejection of
old-audience/wrong-issuer/non-allowlisted tokens, and successful authorized pilot
client discovery, reauthorization, `ping` and guidance calls. Check logging,
rate limits, refresh and expiry behavior without exposing credentials. Stop and
roll back on failure; record evidence and any residual risks.

Rollback using the previously verified live image, configuration and proxy/TLS
artifacts and restore prior DNS routing as approved; set the hostname back to
`mcp-staging.directedideation.com` (or unset it) and ensure the old WorkOS
resource remains available. Clients must return to the old endpoint and obtain
old-audience tokens again. Account for DNS caches and existing token lifetimes;
verify the old endpoint and access controls end-to-end. Do not overwrite reviewed
rollback artifacts or assert new digests without independently checking them.

## Isolation and local preparation

The staging build uses a generated isolated context containing only explicitly listed staging inputs and four canonical Python files. Run the preparation command immediately before every build; it replaces the entire generated directory. Do not add files to that directory or use named contexts, whose ignore rules may be ignored by the builder. Environment files, credentials, metrics data, and deployment scripts are excluded. The canonical module imports the metrics code but staging does not invoke its metrics middleware or lifespan. It has no mounts, volumes, Docker
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
it does not have an egress firewall. The direct backend buffers and limits
`/mcp` and `/mcp/` descendant request bodies to 64 KiB; oversized bodies are
rejected. This is not a general body limit for other paths and does not provide
direct-backend header, concurrency, timeout or rate/abuse limits. The example
proxy also caps bodies at 64 KiB; do not treat direct network access as safe.
Limits and runtime behavior must be verified on the target
Docker/Compose version. The build uses a hash-checked export of all repository runtime dependencies,
including packages not needed by staging. Regenerate it after lock changes with
`uv export --locked --no-dev --no-emit-project --no-header -o staging_mcp/requirements.lock`.
Both build stages pin the official `docker.io/library/python:3.11-slim` OCI
index digest `sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893`.
The Docker Hub registry returned this digest for the tag; its raw index bytes
also hash to that digest. `podman manifest inspect` by digest lists Linux amd64
manifest `sha256:6d10e720318bd84cc3d88af92bb5a47189222e17620a2fd214da6445e4afb679`
and Linux arm64/v8 manifest `sha256:8f867a1f16776618234a2d0ef41fbb991d0bd0b142c8a95bc37456d8e47104cf`.
The tag can move; periodically review and update the pin in both stages, verify
its registry identity and platform manifests, and rebuild for security updates.
A digest pin is not a security review or proof of provenance. Binary wheels are
required; an unsupported target may fail the build. Build with a trusted package source.
The local HTTP healthcheck expects an unauthenticated 401; it is only a
liveness check, not proof of JWKS availability, valid tokens or external access.

On a local machine only, from the repository root, with Docker and Compose v2:

```sh
export WORKOS_STAGING_ISSUER=https://YOUR-STAGING-ISSUER
export WORKOS_STAGING_ALLOWED_SUBJECTS=user_EXAMPLE
# Replace both placeholders with non-production values; never commit credentials.
python scripts/prepare_staging_build_context.py
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

## Target host update (operator only)

For a future update requiring public closure, from a reviewed checkout on the target
host confirm public routing is closed, port 8765 and the existing `di-staging` project are the intended staging resources,
and preserve the prior image for rollback with `docker image tag directed-ideation-staging-mcp:local directed-ideation-staging-mcp:rollback` after confirming the source image is the running staging image. Transfer/update this checkout including
`src/site_directedideation_com/__init__.py`, `src/site_directedideation_com/mcp`,
`src/site_directedideation_com/metrics.py`, `scripts/prepare_staging_build_context.py`
and `staging_mcp/`; the generated build context requires the repository layout and
the preparation command above. In a clean shell set only the existing
staging issuer and allowlisted subject IDs (do not print secrets). Run the three
Compose commands in Local preparation above, then inspect `ps`, health and loopback
401, and use an approved non-production token via a secure client to verify tool
listing, all four calls, stage filtering and invalid-input denial. Do not record
tokens or user content. Verify the private service and public closure independently.
If checks fail, restore the prior image with `docker image tag directed-ideation-staging-mcp:rollback directed-ideation-staging-mcp:local` and run `docker compose -p di-staging -f staging_mcp/compose.yaml up -d --no-build --pull never --force-recreate`; verify the rollback and public closure. Recreate only `di-staging`; do not change nginx, firewall or the private service.
The previous ping-only exception has ended. The requested small pilot is a separate
scope and must use the authenticated guidance application, not the old ping-only build.

## Staging evidence and remaining scope

Private live checks with a real WorkOS token returned 200 for the approved
user; tools/list and filtered guidance matched expectations. A second user and
one sampled ID token returned 401. Following a rebuild, exact issuer matching
was also verified against the droplet. These observations do not establish
general access-token versus ID-token semantics for every token or replace
independent review. Do not record tokens or user content.

Tests against the actual droplet nginx on loopback using the real certificate
returned 401 for an unauthenticated request and 200 for metadata; unknown or
missing SNI was rejected at TLS, a wrong Host was dropped, and rate limiting
returned 429. These are loopback observations, not proof of public routing,
external reachability, effective inherited settings on every listener, or
client compatibility. Broader external and Claude testing and full nginx inheritance
and listener review remain incomplete. These loopback observations alone do not
establish public compatibility or authorize production changes.

## Public pilot and rollback

The authorized small public pilot is active for non-sensitive use with the
actual authenticated guidance tools and a limited WorkOS staging subject allowlist.
The prior one-time ping-only test is closed: on 2026-11-04 UTC it ran approximately
03:40–03:50:45, and external TCP 443 was refused after rollback. A Claude Desktop
Code connector showed Ping and pong during that test; it did not establish regular
Claude chat compatibility. Its timer was stopped. This historical test is not a
pilot launch; the current authenticated pilot is separate.

An operator should check the actual authenticated build and allowlist, TLS and
routing, denial of anonymous and unapproved users, and external reachability when
enabling the pilot. Keep the pilot small and monitor availability, authentication
failures, abuse/rate limits and resource/error signals. Never log bearer tokens,
credentials or user content; check inherited logs and redaction with synthetic
credentials. WorkOS staging is testing only, not a substitute for the production
environment WorkOS recommends for customer-facing use.

Rollback is operator-managed; **no rollback timer is planned for the pilot**.
For any future reopening, the operator must verify the installed
`/usr/local/sbin/di-shared-test-rollback` is available and that its expected
configuration digest matches the configuration to be rolled back. Keep host
access and the rollback procedure ready throughout the pilot. On unsafe behavior
or when stopping, run the installed rollback procedure, then independently verify
external closure and that unrelated services remain healthy. A digest mismatch or
unavailable rollback means resolve it before opening; do not assume rollback
succeeded without checking. Do not disclose secrets in commands, logs or tickets.

General production remains blocked pending independent security review, broader
client testing, token-semantics verification, and review and testing of proxy,
host and direct-backend request limits. Pilot use accepts these residual risks
within the narrow non-sensitive scope; it does not resolve them or authorize a
general production launch. The proxy's loopback 429 observation is not proof of
effective public abuse limiting, and direct-backend header, concurrency and
timeout limits remain incomplete.

For pilot routing, an administrator may adapt `nginx.conf.example` in the
`http` context of the existing reviewed nginx configuration, without replacing
other sites or routing to the private MCP at 8001. Review the complete nginx
configuration, listener precedence, SNI and Host routing, inherited real-IP and
logging settings, TLS, firewall, and IPv4/IPv6 exposure. The proxy must be the
outermost peer; stop if inherited real-IP settings or an upstream proxy rewrite
its remote address. Verify independently that missing or unknown SNI and unexpected
Host cannot route to staging or a private service on each exposed address family.
The example listens on IPv4 only; verify no AAAA record or IPv6 listener routes to
this service. Validate the complete configuration before reload and avoid changes
to unrelated sites. If routing or rollback cannot be verified, do not open access.

Only where review confirms there is no conflicting explicit default and this will
not alter existing sites' required behavior, an operator may add a separate
fail-closed default for the exact IPv4 listener, using nginx 1.19.4 or newer:

```nginx
server {
    listen 0.0.0.0:443 ssl default_server;
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
to the actual binary remote address: 60 requests/minute with a burst of 20,
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

### Pilot rate adjustment: live status

The Pi coding agent observed 429s at 10r/m with burst 5. The reviewed new
public file is `shared-nginx-test/tests/reviewed-public-test.conf` (SHA-256
`7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530`):
60r/m with burst 20; connection, body and timeout limits are unchanged. The
companion `shared-nginx-test/di-shared-test` permits rollback of that file or
the previous exact file (SHA-256
`814b89c83fcc507d773cb73fee5f77a1a727d45da48b03927cf5959f4d32d3f4`).
The installed public config was verified at the new digest above, and the
installed dual-digest rollback script at SHA-256
`214f63c23fae0f10867bead0aa290ebb59a5c2ce663749860360d1adc3b2ef05`.
Nginx is active. Eight anonymous public requests returned 401; the private
loopback listener returned 400, which is not a full health check. Staged
backups are in `/var/lib/di-shared-test/rate-transition.SUyLNlyZ`. After the
rate change, the operator reported that Pi using the Gmail account retrieved the
complete method. This single successful call does not establish public rate-limit
enforcement or unrelated-service health.

The following procedure documents the transition and is not an instruction to
repeat it against the already-adjusted live configuration. For a future similar
change, an authorized operator should reassess the current state and procedure,
using a root shell and console access:

1. Review both artifacts, the complete `nginx -T`, installed rollback wrapper
   and `/usr/local/libexec/di-shared-test`; confirm the wrapper executes that
   script. Confirm the live `/etc/nginx/conf.d/di-staging-public-test.conf`
   hashes to the old digest above, the loopback `.disabled` backup is intact,
   and the existing rollback procedure and external closure path are ready.
   If any differ, stop and reconcile; do not substitute a digest blindly.
2. Stage the new config and script in a root-owned non-web-accessible directory
   **outside** nginx's include tree. Verify both hashes/content against the
   reviewed checkout and ownership, and back up the installed script and live
   config outside the include tree. Ensure no timer or other process can invoke
   rollback during the transition; a process that loaded the old script before
   locking could otherwise reject the new digest. Coordinate any timer rather
   than silently disabling a safety mechanism.
3. Acquire `/var/lib/di-shared-test/lock` with `flock` for the entire change;
   prevent new rollback invocations until the lock is released. Atomically install
   the reviewed dual-digest script first (root:root 0755, temporary file on the
   same filesystem followed by rename), and verify the installed bytes. Only
   then atomically rename a root:root 0644 staged copy of the new config into
   the public path (temporary file in the same directory with a name not ending
   in `.conf`). Never edit the live file in place. Run `nginx -t`, then reload
   nginx only on success. On failure, atomically restore the saved old config,
   validate and reload; if recovery fails, use the independently prepared closure
   path. Do not invoke the lock-taking rollback while holding the lock.
4. Release the lock, restore any coordinated safety timer, verify installed
   digests and nginx status, and test externally that authorized access works,
   rate rejection remains effective and unrelated routes are unaffected. Keep
   the dual-digest rollback installed; on unsafe behavior invoke the wrapper and
   independently verify external closure. Do not test destructive rollback on a
   live pilot unless prepared to close it.

A reload can fail or leave old workers/connections alive, and rate-zone state may
persist across reload; enforcement and closure are not instantaneous guarantees.
A crash between steps requires checking both disk hashes and effective nginx
state before recovery. The higher shared-IP budget increases abuse exposure and
may still produce 429s; monitor and revisit with real traffic. The isolated
tests alone cannot validate the host, timer state, installed digest or firewall.

### Separately approved HTTP-01 certificate bootstrap and renewal

General production remains BLOCKED. A public ACME-only HTTP
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
it never redirects or proxies to MCP. For the scoped pilot, the TLS example may be installed, validated
and reloaded as described above once the operator checks and rollback are ready. Verify HTTPS and hostname independently.

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

### Locked staging operations and pilot user helper

All operators and automation that deploy, recreate, stop, remove, retag or otherwise
change this staging container, its image tag, or its Compose inputs **must hold**
`/run/lock/di-staging-allowlist.lock` exclusively for the entire operation. For
manual commands, run a root shell with `sudo flock -x /run/lock/di-staging-allowlist.lock
/bin/bash`, then perform the complete operation and exit that shell. Do not invoke
the helper inside that shell: it acquires the same non-reentrant lock itself.
The earlier deployment and teardown commands must also be run inside this lock.
Uncooperative root or Docker-privileged operations cannot be prevented by this
advisory lock; they can race the checks and cause disruption.

Before using the helper, explicitly migrate the staging deployment (a recreation,
requiring separate authorization and a rollback plan) under that lock. Install the
reviewed `staging_mcp/compose.yaml` as `/etc/di-staging/compose.yaml`, with `/etc`,
`/etc/di-staging`, and the file root-owned, not group/other writable, and without
symlinks; do not create `/etc/di-staging/.env`. Verify the copy byte-for-byte against
the reviewed repository file and verify its SHA-256 against the helper's pinned
digest. Changes to the reviewed Compose file require updating that digest after
review. Recreate the project using that exact file and `/etc/di-staging` project
directory, the existing issuer and current allowlist, project `di-staging`, and
the existing `directed-ideation-staging-mcp:local` image. Verify the running
container and service before releasing the lock. Preserve credentials securely,
and ensure future deployments preserve the updated allowlist. The old temporary
checkout deployment does not meet these requirements and the helper refuses it.

Install the reviewed helper as a root-owned, non-writable-by-others executable in
a root-trusted directory. Then run (replace the example user ID):

```sh
sudo /usr/local/sbin/add-allowed-user user_00000000000000000000000000
```

The helper reads issuer and allowlist from the container without printing them,
uses the local Docker Unix socket and a clean environment, verifies the trusted
Compose copy, configuration hash, running image ID and tag, and rechecks drift
before recreation. It never builds or pulls. A changed Compose version or other
drift may cause refusal; investigate rather than bypass. A failed recreation or
post-check can leave the service unavailable or changed; inspect and recover under
the lock. Process environments remain visible to privileged observers.
