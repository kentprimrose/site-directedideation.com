# Draft: staging image and Compose migration

**Not approved for live execution. Not yet an executable runbook.** This draft
bridges the observed old deployment and the production cutover tooling. The
actual old Compose file, loopback nginx configuration and image are not in this
checkout. Do not infer their contents from a different repository revision.
Record evidence without issuer values, user IDs, tokens or client content.
See `docs/STAGING_UPGRADE_INVENTORY.md` for the observed snapshot.

## Objective and boundary

Replace only the authenticated `di-staging` service with a reviewed
hostname-configurable image and trusted Compose layout, while keeping the
existing staging hostname, staging issuer and staging allowlist unchanged.
The public nginx configuration, DNS, certificates, WorkOS and private service
are not modified. This is not the production-host cutover.

Expect a service interruption on recreation. Agree a maintenance window,
authorized operator, verification deadline, client test and console recovery
path. Each live change requires separate approval. A successful container health
check is only a 401 liveness check, not an authentication or client test.

## Blocking preparation

1. **Verify the exact old Compose, privately.** Removing only the
   `STAGING_MCP_HOST` line from the current `staging_mcp/compose.yaml` produces
   the observed old-file SHA-256
   `18e3d4bf8a8d5fdbf365fb069c0eae14903a11292197812ae28e44506eff3c45`.
   A redacted read of the live file was consistent with that reconstruction.
   This identifies its bytes by digest, but does not prove all referenced build
   inputs, runtime interpolation, environment or project behavior. Reproduce it
   in a disposable Linux/Docker environment with synthetic identities and its
   original project directory layout; verify installed Compose version behavior,
   config hash and labels. Review referenced inputs before executing them.
2. **Capture and review closure inputs.** Review the complete effective nginx
   configuration, disabled loopback config and helper/wrapper control flow.
   Reproduce that layout in a disposable Linux environment, including actual
   listener precedence, dynamic rollback timer, locks and reload. Test closure
   and restoration, unknown/no SNI, old connections and unrelated sites. The
   generic Podman rehearsal retains a separate default listener and therefore
   does not reproduce the observed layout. Define an independent emergency
   closure path and external acceptance checks; do not assume closing 443 or
   selecting another implicit default without testing.
3. **Develop and test exact commands** for the phases below, including every
   failure boundary and a safe mechanism to capture and restore the sensitive
   environment without secrets in command arguments or output. Review with Linux
   ShellCheck and real Docker Compose/systemd in a disposable environment.
4. **Reconcile the `:rollback` tag.** Inventory its actual image ID, if any,
   and preserve any existing use before approving a tag change. Verify the old
   running image against an independently recorded ID; a tag alone is not a
   backup. Avoid a build that overwrites `:local` while the old service is
   running. Build the candidate with a distinct tag and independently verify
   image ID, reviewed inputs and old-host behavior.
5. Confirm current state, operator access, working network/JWKS, trusted users,
   external testing and applicable locks. Recheck digests and container ID under
   `/run/lock/di-staging-allowlist.lock` immediately before mutations. The lock
   is advisory and non-reentrant; don't call a lock-taking helper while holding
   it. Coordinate the separate nginx lock and timer; never nest the locks without
   a reviewed ordering.

## Proposed phases (not commands)

### A. Preserve the old service

Under the allowlist lock, verify no drift from the fresh inventory. Securely
preserve the original Compose file and all required companion inputs, runtime
issuer/allowlist, image identity and existing tags. Preserve file metadata and
root-protect sensitive copies. Validate the old Compose configuration with
synthetic data separately; never print rendered production configuration.
Test that the recovery artifacts really reproduce the old state in the
rehearsal. Snapshot and reconcile any existing rollback tag before altering it.

### B. Prepare and verify the candidate

Use a reviewed checkout and the generated isolated build context; build under a
new tag rather than using a Compose build that overwrites `:local`. Confirm the
candidate's implementation and host pinning and exercise it in a disposable
network with synthetic issuer/subjects. Confirm the trusted Compose bytes and
helper's pinned digest match. Prepare, but do not automatically activate, the
root-owned `/etc/di-staging/compose.yaml` and its parent directories; the
trusted deployment forbids an `.env` file there.

### C. Controlled switch

With an approved recovery plan and separate authorization, acquire the
allowlist lock, recheck old container, image, tags, inputs and sensitive values;
install the trusted Compose file; transition the image tag in the reviewed
order; recreate only `staging-mcp` using `--no-build --pull never --no-deps`.
Ensure the exact staging host, issuer and allowlist are preserved. Verify the
running image ID, Compose project/source/working-directory labels, config hash,
environment equivalence and health before releasing the lock. If any step fails
after mutation, state is unknown: follow the rehearsed recovery decision tree,
not an unreviewed retry. Do not invoke another helper which acquires this lock.

### D. Verify before accepting

Independently verify staging TLS, metadata and host rejection; anonymous and
unapproved access denied; an approved real client can reauthorize if needed,
discover tools, call ping and guidance, and use stage filters. Check unrelated
services, network exposure and logs using synthetic data. Validate that the
allowlist helper preserves the host and issuer without changing access. Retain
old artifacts until the agreed observation period and separately approved
retirement. If validation fails, use the rehearsed failure procedure.

## Recovery must be demonstrated, not assumed

- **Emergency closure** is a separate outcome from service restoration. Confirm
  the public route is closed independently after any authorized closure; a
  successful helper exit alone is insufficient. Preserve unrelated services.
- **Old-service restoration** must restore the verified old image, original
  Compose inputs and project directory, staging issuer and allowlist together.
  It must restore the original tag mapping or a specifically reviewed equivalent,
  recreate only the intended service and check image ID, runtime values, health,
  routing and authenticated client behavior. Capture any tag displaced by the
  upgrade and restore it deliberately. Verify whether exact original Compose
  labels/hash are achievable with the actual Compose version. Test partial
  failure and recovery with the actual old file in isolation before relying on
  these steps. If safe restoration cannot be proved, stay closed and investigate.
- The production `backend-transition.sh restore` is **not** this procedure: it
  requires a record created after migration and an unchanged recorded image tag.

## Rehearsal status

The existing rendered-production-nginx Podman rehearsal passed token, SNI,
Host, rate-limit, failed-validation, closure and restoration checks, but uses a
separate default listener and is not proof of the droplet's closure state.

`scripts/rehearse_staging_upgrade.sh` also passed a local Podman Compose
old-image → candidate-image → old-image recreation, including a simulated
post-recreation failure. The old image's server and healthcheck hashes match
the live inventory; its complete image ID differs and is not proven identical.
The rehearsal uses synthetic identities, modified Compose files without exposed
ports and a distinct project; it checks image IDs, liveness health, synthetic
issuer/allowlist/host preservation, and consistency of Compose config hashes
with container labels at each phase. It does not test OAuth, real configuration
hashes, guarded live commands, systemd or the actual nginx layout. It is not an
executable production upgrade/rollback procedure. No live changes were made.

A further local experiment restores the old image from a private byte-identical
Compose snapshot after deliberately modifying the original file. It verified
health, synthetic environment, image identity and the snapshot's Compose hash;
the source-file and working-directory labels intentionally changed to the
snapshot path. This demonstrates a possible way to avoid reopening the writable
old path, **not a production-ready secure capture or full recovery**. The
experiment does not establish root ownership or race-resistant capture, preserve
or validate all live companion inputs, reproduce the live Compose version, test
authenticated traffic, or establish the actual old image identity. Those remain
blocking requirements for an executable guarded procedure.
