# Manual staging switch and recovery

This is an operator-run, single-service Docker Engine/Compose v2 procedure. It
performs **no live action until run on the host**. Arrange downtime and notify
users; keep an independent privileged console. Review the helper and both
Compose files first. This is not an automatic deployment or crash-proof
transaction. It does not change nginx, DNS, WorkOS or other services.

## Preconditions and preparation

* Root, Python 3, Docker Engine and Compose v2 are required. The helper uses
  `/var/run/docker.sock`, a clean subprocess environment and the same exclusive
  `/run/lock/di-staging-allowlist.lock` as `add-allowed-user.sh`. Coordinate
  **all** other administrators, deployments, tag changes and configuration
  writers separately: the lock only protects cooperating processes.
* This is specifically for project `di-staging`, service `staging-mcp`,
  container `di-staging-staging-mcp-1`, working directory `/etc/di-staging`, and
  image tag `directed-ideation-staging-mcp:local`. The installed config must
  be a trusted, self-contained Compose file with no `.env`, external env files,
  includes, secrets, extra services changed by this operation, or mutable
  external interpolation. Review the **entire** new file, including image,
  host, ports, mounts, command and healthcheck. The helper's config hash is a
  drift check, not a security review of Compose. No builds or pulls are done.
* The original running container must have Compose labels for
  `/home/kent/di-pilot-build.eR6dNHdr/compose.yaml` and working directory
  `/home/kent/di-pilot-build.eR6dNHdr` (not `/etc/di-staging`) and an
  image ID and tag as above. It must have a healthcheck; the helper waits up to
  120 seconds for healthy. Health is not an application-level verification.
* Install the reviewed helper as a root-owned, non-writable executable. Before
  any tag or Compose change, in a root shell with `umask 077`, and while holding
  the allowlist lock, create `/var/lib/di-staging-manual-upgrade` mode 700 and
  capture **the actual** `docker inspect di-staging-staging-mcp-1` JSON array
  to `container.json`, and copy the actual old `/home/kent/di-pilot-build.eR6dNHdr/compose.yaml` to
  `old-compose.yaml` there. Both files must be root-owned mode 600. Do not
  display, email or commit the inspection: it contains private environment.
  Confirm the capture succeeded and describes the intended running container.
  Treat this directory and backups as sensitive; securely remove when no longer
  needed. Parent paths and `/etc/di-staging/compose.yaml` must be root-owned,
  non-symlink and not group/world writable.
* Record the full old image ID from the snapshot **privately** (not the rest of
  the JSON) and ensure that image remains locally available by ID. Load/build the
  reviewed replacement separately and record its full new image ID. Both IDs
  are `sha256:` plus 64 lowercase hex digits. Confirm both locally. Preserve
  the old image from pruning throughout the recovery window.
* Install the reviewed new Compose file at `/etc/di-staging/compose.yaml` and
  leave the service tag pointing at the old image while the old container continues to
  run. Under the same lock, coordinate these preparatory changes with all
  writers. Record the new file's SHA-256 (`sha256sum`); this is a non-secret
  64-character digest and authorizes precisely that file for switch/recovery.
  Recheck the old container remains running. Do not run the allowlist helper
  between snapshot and completion; if anything changed, stop and start again
  with a fresh snapshot, after resolving the state.

## Switch

Run as root with the three recorded non-secret values, not environment secrets:

```
manual-switch.py switch sha256:OLD_FULL_ID sha256:NEW_FULL_ID NEW_COMPOSE_SHA256
```

The placeholders must be replaced with the actual full IDs and digest. The
helper reads issuer and allowlist from the private snapshot and passes them only
in the Compose process environment, never as command arguments or output. Root
and daemon administrators can still access process/container environments.
It reproduces the old config hash and checks saved/live container identity,
labels, environment, old image availability, tag, approved config digest and
current container ID. Under the lock it retags the candidate by ID, verifies the
new tag, then Compose recreates only the service using `--no-build
--pull never --no-deps`. It checks image, tag, config, environment, running
state and health. Check endpoint behavior, authentication, host and audience
separately without exposing tokens or private configuration.

## Recovery

If switch or verification fails, investigate privately and, when the container
still exists and runs in a recognized old/new state, run with the **same**
three recorded values:

```
manual-switch.py recover sha256:OLD_FULL_ID sha256:NEW_FULL_ID NEW_COMPOSE_SHA256
```

Recovery accepts the original snapshot container with the original path labels,
or a recreated container with the `/etc/di-staging` labels. Recovery checks the snapshot and current state and refuses an unrelated image,
tag, container config or Compose file. It retags the old local image, restores
`old-compose.yaml` atomically to the installed Compose path, then recreates and
health-checks the one service with the saved issuer and allowlist. This can
interrupt service; it does not undo other changes. Verify the old endpoint and
authorization separately. Keep the private snapshot until verified.

A missing/stopped container, altered environment, unexpected config, retag, or
other drift causes refusal rather than guessing. A failed Compose call, crash,
or non-cooperating writer can leave a partial transition (including a changed
tag or restored file). Stop competing work and inspect state privately; use an
experienced administrator to recover deliberately. Do not blindly rerun or
replace files after refusal. Docker stderr is suppressed to prevent accidental
secret disclosure; inspect daemon state and logs privately as needed. This helper
cannot guarantee atomicity against root/Docker administrators or protect
against hostile root-owned files; its checks are practical guardrails, not a
formal crash-safety proof.

## Isolated rehearsal

The helper was rehearsed for switch and recovery against a random, disposable
Podman project and local images, with no live staging actions. A temporary
adapter used Podman's local machine socket and Docker Compose, substituted random
project/name/tag and temporary original/target/private paths, normalized Podman
image IDs, and bypassed root/ownership checks for the macOS test user. It used
an artificial healthchecked service and private test values, not production
configuration. This exercises actual helper control flow and service recreation,
but does not validate production Docker behavior, ownership protections, or the
real service configuration.
