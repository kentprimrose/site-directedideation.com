# Production review and shortest safe path to `mcp.directedideation.com`

Reviewed 2026-11-04 against the repository at `a35fc4b` and current WorkOS
documentation. The working tree was clean and `uv run --frozen pytest -q`
passed all 188 tests. Live DNS, WorkOS settings, the droplet, and installed
deployment artifacts were not inspected. This review does not authorize or
perform deployment changes.

## Recommendation

Move the existing authenticated pilot to
`https://mcp.directedideation.com/mcp`, retaining its small subject allowlist,
current host, nginx, and loopback backend on port 8765. The application already
supports this hostname through `STAGING_MCP_HOST`; no new application features
are required for the hostname change.

Distinguish continued internal testing from customer-facing use. For real end
users, configure WorkOS production and rebuild the allowlist with production
user IDs. WorkOS explicitly says staging is not intended for customer-facing
traffic; calling the deployment a pilot does not establish an exception. WorkOS
environments are isolated, and users do not automatically carry over.

Source: [WorkOS environment guidance](https://workos.com/docs/authkit/environments).

The broader launch still requires the security, legal/privacy, operational, and
client-validation gates documented in `docs/PLAN.md`. The hostname move itself does
not require new hosting, a replacement reverse proxy, billing, or the entire
team-management roadmap. Any narrower launch scope must be reconciled explicitly
with those documented gates.

## Findings in the existing plans

### 1. Retaining WorkOS staging is unsuitable for customer-facing production

Both `PROD_DEPLOY_CLAUDE.md` and `PROD_DEPLOY_GEMINI.md` recommend keeping the
staging issuer for the renamed pilot. That is appropriate only for continued
testing within WorkOS's supported scope. For customer-facing use, configure the
production environment, its exact resource indicator, and its actual user IDs.

The application accepts a configured canonical HTTPS issuer; the
`WORKOS_STAGING_ISSUER` variable name does not technically restrict it to staging.
Renaming variables is not necessary for this cutover. Verify the production
issuer, JWKS discovery, actual token claims, and client authorization flow before
relying on this configuration.

### 2. A separate nginx file leaves the existing emergency closure incomplete

Gemini's plan suggests adding a separate production-host config while preserving
the old public file. The existing `shared-nginx-test/di-shared-test` rollback
removes only `di-staging-public-test.conf`; it would leave a separate new route
active. Its successful exit would therefore not prove public closure.

Editing the old file, including removing its `default_server` block, changes its
pinned digest and makes the existing script refuse it. Reusing the rate-limit
zone declarations in two loaded files also introduces duplicate declarations.

Prepare reviewed procedures for both emergency public closure and restoration of
the previous working endpoint. They must cover the exact files installed during
cutover, preserve the appropriate fail-closed listener, and account for the
complete shared nginx configuration. Validate installed bytes and any updated
digests; do not assume the repository matches the host.

### 3. Build instructions resolve the generated context in the wrong directory

Gemini's proposed build uses `/etc/di-staging/compose.yaml`. Its relative
`.build-context` resolves under `/etc/di-staging`, while
`scripts/prepare_staging_build_context.py` generates the context under the
checkout's `staging_mcp/` directory.

If an image build is necessary, generate the context and build using the reviewed
checkout's Compose file. Recreate the deployment using the trusted installed
Compose file with `--no-build --pull never`. Preserve the running image first,
verify its relationship to the local tag, and hold the documented staging lock
for image/tag or deployment mutations.

### 4. The uncommitted-work blocker is stale; changing defaults is unnecessary

Hostname support and the supporting deployment tooling are committed, and the
reviewed working tree is clean. The plans' uncommitted-work claims are historical.

Claude's proposed change to the default hostname is unnecessary: pass
`STAGING_MCP_HOST=mcp.directedideation.com` explicitly. Editing Compose would
invalidate the digest pinned in `add-allowed-user.sh` and require another reviewed
helper/configuration update. Preserve the current defaults and pinned file for
the shortest route.

### 5. The existing proxy rehearsal does not exercise the proposed new artifacts

`scripts/test_staging_proxy_isolated.py` hardcodes the staging hostname and loads
the current nginx example. Running it unchanged does not validate a new-host
configuration or the new deployment's rollback coverage.

Adapt the rehearsal to exercise the actual proposed hostname and proxy artifacts,
including closure and restoration. Its injected verification key and disposable
network do not establish live WorkOS, DNS, certificate renewal, or host routing
behavior; verify those separately.

## Shortest safe cutover sequence

### 1. Inventory the live deployment

Record the running image identity, whether it supports `STAGING_MCP_HOST`,
installed Compose file and project directory, nginx configuration, issuer,
allowlist, certificate renewal setup, and rollback dependencies. Preserve
configuration and identity values securely without dumping tokens or environment
contents into logs.

Check that ports 8001 and 8765 remain private, and establish the current health of
unrelated services. Repository history does not establish the installed state.

### 2. Prepare one reviewed cutover package

Prepare new-host HTTP-01 and TLS configurations, a certificate renewal hook,
the exact deployment command, and procedures for emergency closure and restoring
the old hostname, image, issuer, allowlist, and proxy configuration.

Preserve the fail-closed default listener and avoid duplicate rate-limit zones.
Validate against the complete shared nginx configuration and rehearse the actual
new artifacts. Follow the existing staging deployment lock and proxy transition
lock requirements, coordinating operations so rollback cannot race the change.

### 3. Pre-provision DNS, TLS, and OAuth

Verify the intended host address before creating the new DNS record. Verify
IPv4/IPv6 routing explicitly; do not publish an AAAA record for an IPv4-only
service. Pre-provision the matching certificate through the reviewed ACME-only
route without allowing Certbot to rewrite unrelated nginx configuration. Verify
renewal scheduling and the lineage-scoped nginx reload hook.

Register the exact resource indicator
`https://mcp.directedideation.com/mcp`. For customer-facing use, configure WorkOS
production, the required MCP client-registration settings, and a production
subject allowlist. Preserve the old environment and resource for rollback.
Verify actual access-token semantics and plan client reauthorization.

Source: [WorkOS MCP guidance](https://workos.com/docs/authkit/mcp).

### 4. Reuse the deployed image if it supports the hostname switch

Avoid rebuilding solely to change environment settings. If the deployed image
lacks hostname support, build once from the reviewed commit using the checkout's
generated context, preserve the previous running image, and verify the new image.

The existing GitHub Actions workflow deploys the separate unauthenticated private
service; pushing to `main` does not deploy this authenticated pilot.

### 5. Perform a brief scheduled cutover

Under the documented locks, explicitly set the new hostname, selected issuer,
and exact subject allowlist; recreate only the authenticated backend and activate
the reviewed proxy configuration. Wait for health and inspect the effective
configuration before declaring success.

The backend accepts exactly one hostname and one resource audience. Switching
it ends service at the old hostname and makes old-audience tokens unusable at the
new endpoint. Expect a brief outage and client reauthorization; no fixed
sub-minute completion time is established.

Keep nginx pointed at `127.0.0.1:8765`. Never route the public hostname to port
8001, which serves the unauthenticated private prototype.

### 6. Verify externally and restore on failure

Verify:

- DNS and certificate identity, including the intended IPv6 behavior.
- Correct protected-resource metadata and exact authorization-server issuer.
- Anonymous requests return 401; wrong-issuer, old-audience, expired, and
  non-allowlisted tokens are rejected.
- Unknown/missing SNI and unexpected Host cannot reach either backend.
- Authorized pilot clients reauthorize and successfully discover and invoke
  `ping`, all four guidance tools, and stage-filtered supplementary guidance.
- Invalid tool inputs are rejected without echoing sensitive values.
- Refresh/expiry behavior, effective public rate limiting, and logging controls.
- No external access to ports 8001/8765 and no disruption to unrelated services.

On failure, use the prepared procedure to close unsafe public access or restore
the exact prior image, hostname, issuer, allowlist, and proxy configuration.
Keep the old resource registered; verify the restored endpoint end to end and
account for client configuration, cached DNS, existing connections, and token
lifetimes. Restoring an image alone is not a complete rollback.

## Evidence and remaining limits

All 188 repository tests passed during this review, including the offline test
that pins Host, audience, and metadata to the new hostname. These tests do not
establish live deployment readiness, production WorkOS interoperability, public
abuse protection, or a completed independent security review.

No live infrastructure was inspected or changed. Before execution, reconcile
this plan with the actual host state and the launch gates in `docs/PLAN.md` and
`docs/staging_mcp/DEPLOYMENT.md`.
