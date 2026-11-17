# Authenticated production CI

This pipeline deploys the existing authenticated `di-staging` Compose project,
not the separate private service. It assumes the independently approved production
cutover is already complete, including WorkOS, TLS, DNS, proxy and the exact
root-owned `/etc/di-staging/compose.yaml` from this revision. It does not perform
that cutover. No production changes were made by implementing this pipeline.

## Operator setup (before enabling deployments)

* Review the receiver and deployment, rehearse on a disposable equivalent host,
  and complete the existing cutover/runbooks first. Install
  `staging_mcp/receive-production.py` as root-owned mode 0755
  `/usr/local/sbin/di-auth-receive`; protect all parent directories from writes.
  Install Docker, Compose v2 with `--wait`, Python 3 and flock support. The
  existing service must have the production host, issuer and allowed subjects,
  and the reviewed Compose file, project directory and name expected by the
  receiver. Do not create `/etc/di-staging/.env`. Receiver upgrades and Compose
  changes require operator review and installation; update its pinned hash when
  deliberately changing Compose and coordinate existing helper pinning.
* Create a dedicated SSH account and key, restrict login and network access;
  permit only the receiver via a narrowly scoped sudo rule. **This sudo permission
  is privileged**: Docker image loading and executing images is root-equivalent;
  protect the key accordingly. Do not grant general shell or Docker access. Use
  an SSH forced-command gate that validates the exact `SSH_ORIGINAL_COMMAND`
  (receiver path and 40 lowercase hex SHA) and executes it; reject everything
  else. Preserve stdin for the image. Configure sudo without a password for only
  this receiver. Test the gate and host key out of band.
* Create the GitHub environment `authenticated-production`, add required reviewers
  and restrict deployment branches to `main`. Add environment secrets
  `AUTH_DEPLOY_SSH_PRIVATE_KEY`, `AUTH_DEPLOY_SSH_KNOWN_HOSTS` (verified pinned
  host key), `AUTH_DEPLOY_HOST`, and `AUTH_DEPLOY_USER`. No WorkOS secrets or
  tokens are copied to GitHub. Push to main runs tests then requests deployment;
  manual dispatch is restricted to main. Private deployment remains independent.
* Verify platform architecture matches the GitHub runner's linux/amd64 image;
  configure a matching runner/build platform if not. Ensure adequate disk space.
  Coordinate all administrators using `/run/lock/di-staging-allowlist.lock`.

The receiver preserves the live container's auth configuration without printing
it, serializes with pilot operations, and recreates only the authenticated service.
Compose waits for its healthcheck, which checks that unauthenticated MCP requests
return 401. This does **not** prove authorized access, proxy/TLS, or end-to-end
OAuth: a human must verify those separately using a securely handled authorized
client and confirm an unauthorized request is rejected. Never put tokens in
commands, CI logs or tickets. Failure triggers a best-effort image rollback;
check the service and proxy independently even after reported success.

## Recovery

The prior image is tagged `directed-ideation-authenticated:rollback` before each
attempt. On failure, automatic restoration is attempted; rollback can itself fail.
Under the shared exclusive lock, use the existing manual recovery procedure in
`MANUAL_SWITCH.md` and `DEPLOYMENT.md`, preserving the current authentication
configuration, to retag the rollback image as `directed-ideation-staging-mcp:local`
and recreate only `di-staging`. Verify health, unauthorized rejection, and an
authorized client. The rollback tag is a single slot, not history; repeated deploys
replace it. Preserve additional immutable image IDs separately before operations.
Never run manual recovery concurrently with CI or allowlist changes.
