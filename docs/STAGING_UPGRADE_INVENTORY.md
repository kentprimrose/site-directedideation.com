# Staging upgrade: inventory and preparation checkpoint

This checkpoint records operator-supplied read-only inventory from the current
pilot. It is not authorization to change the droplet. Recheck live state and
hashes before any operation; do not record issuer values, subject IDs or tokens.
The production cutover plan and runbook remain applicable.

## Observed state

- Healthy container `di-staging-staging-mcp-1`, image ID
  `sha256:00e4d4579ef34ed01128851597be7e72cbded412a9bfb43dffa31a9344f31dde`;
  `directed-ideation-staging-mcp:local` matched it. The `:rollback` tag was
  missing or different, not independently distinguished.
- Running Compose project points to
  `/home/kent/di-pilot-build.eR6dNHdr/compose.yaml`, SHA-256
  `18e3d4bf8a8d5fdbf365fb069c0eae14903a11292197812ae28e44506eff3c45`.
  That file and directory are owned by `kent`; `/etc/di-staging` is absent.
  The installed Compose is 5.6.1. The old Compose file and running container
  have no `STAGING_MCP_HOST` entry.
- Running `/app/server.py` and `/app/healthcheck.py` hashes differ from the
  reviewed checkout; neither contains the `STAGING_MCP_HOST` string. Treat
  the old image as lacking the reviewed configurable-host implementation.
- Live public nginx file SHA-256 `7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530`;
  installed helper SHA-256 `214f63c23fae0f10867bead0aa290ebb59a5c2ce663749860360d1adc3b2ef05`.
  The public file contains both the IPv4 HTTPS fail-closed default and the
  staging HTTPS server. The summary showed no other HTTPS server, but is not a
  complete closed-state proof. The disabled loopback config exists.
- `certbot.timer` was active/enabled; the new-host certificate was absent or
  unreadable. Rollback transient units were inactive/not found.

## Local validation

- Targeted cutover tests: **71 passed** after this inventory.
- `bash -n` passed for cutover shell scripts; `git diff --check` passed for
  tracked changes. ShellCheck was unavailable. These are not Linux, Docker,
  systemd, live-nginx or WorkOS integration tests.
- The cutover backend `record` mode creates state and takes a lock; it is not
  strictly read-only. It requires the trusted Compose path and its labels and
  cannot record the current deployment. Its `restore` assumes the recorded
  image remains at the recorded `:local` tag. It is not an upgrade rollback
  procedure for the currently running old deployment.

## Gates before staging upgrade

1. Review the existing package and local working-tree changes, then design and
   rehearse an upgrade **and recovery to the actual old deployment**. Preserve
   the original Compose bytes and secure runtime values. Recreating with the
   new Compose file cannot be assumed to reproduce the old Compose config
   hash, labels or runtime state. Verify the old-image/old-Compose combination
   and how to restore it if migration fails; do not use the production cutover
   script as this upgrade's rollback.
2. Review closure against the full effective nginx configuration, the restored
   loopback file and all exposed listeners; reproduce the actual layout in a
   disposable Linux environment. Verify externally after any real closure.
   The existing isolated rehearsal does not establish this host's closed state.
3. After explicit approval, preserve the exact running image and record its ID;
   determine whether an existing rollback tag must be preserved before changing
   it. Preserve old config and state securely. Any tag change is a live change.
4. Build the reviewed image from an isolated context without overwriting the
   running `:local` tag before rollback and drift checks are ready. Agree a
   safe tag transition and lock discipline; verify the candidate image.
5. Separately approve installing the root-trusted Compose file and recreating
   only the staging service under the existing hostname, issuer and allowlist.
   Validate authenticated staging behavior and recovery before progressing to
   production identity, certificate and cutover.

No live change, rollback, image build or service restart was performed in this
checkpoint. The exact upgrade commands and their Linux rehearsal remain work
to do; this document is not an executable runbook.
