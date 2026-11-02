# Stage 1: private MCP deployment

This is an unauthenticated prototype, **not** a public service. Compose publishes
only `127.0.0.1:8001` on the droplet; do not add a public port, proxy, tunnel
for untrusted users, or the admin service. Local host users can reach it. Compose creates a project-scoped default
bridge network (not Docker Engine's shared `bridge`/`docker0` network); any
container attached to that project network can reach the unauthenticated service
directly. Docker administrators can attach containers to it, and host/root or
Docker-privileged users can bypass these boundaries. Do not attach untrusted
containers. Verify the actual network and attachments on the host with `docker
network inspect directed-ideation_default`; firewall rules and Docker network
configuration may change reachability. Docker before 28.0.0 can expose localhost-published
ports to adjacent networks; require Docker Engine 28+ and independently verify
host/cloud firewalls and external IPv4/IPv6 reachability. Docker's firewall
rules can bypass ordinary UFW expectations. No application authentication,
rate limit, TLS, or production security review is provided here. Pilot/public
access requires the later PLAN.md gates.

## Prerequisites and first installation

On the existing droplet, preserve all other workloads, firewall and SSH settings.
An administrator must separately install Docker Engine 28+ and the Compose v2
plugin, provision a dedicated SSH deployment account, and verify enough disk
space for builds/images and the metrics volume. Membership in the docker group
is effectively root access: limit the account/key to trusted deployment, protect
it as a privileged credential, and audit access. Repository/environment
protection and approval, branch protection, and credential rotation are operator
responsibilities. Restrict the key and host access where practical, but an SSH forced command is
not a root-equivalence mitigation for an account that can control Docker: a
crafted image or Docker API access can compromise the host. Strong isolation
requires a separate host/VM or a deployment service with a genuinely restricted
privilege boundary. Restrict SSH forwarding and PTY on the deployment key.

Install reviewed copies of `compose.yaml` and `deploy/receive-image.sh` as
`/opt/directed-ideation/compose.yaml` and
`/opt/directed-ideation/receive-image.sh` (executable), with the deployment
account able to read them. Make the parent directory and both files root-owned
and not writable by the deployment account; create `/opt/directed-ideation/state`
owned by the deployment account with mode 700 for the lock and markers. Restrict
directory traversal to that account and administrators. Root ownership prevents
accidental changes, not a malicious Docker-capable deploy account. Changes to these
host-managed files require a separately reviewed manual update; the workflow
only transfers images. Check Compose changes before each deployment. No remote
operations are performed by adding these files to the repository.

Configure the GitHub `private-deployment` environment and its secrets:
`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_PRIVATE_KEY`, and
`DEPLOY_SSH_KNOWN_HOSTS`. Verify the server host key fingerprint **out of band**
and provide the full matching known_hosts line; never use ssh-keyscan without
independent verification or disable strict checking. Use a dedicated key, no
passphrase (GitHub secret storage), and require environment approvals as needed.
Pushes to main test before building and deploying; manual dispatch from another branch runs tests but skips deployment. Serialized deployments preserve previous images. Deployment builds on
the GitHub runner and streams only the image to the host; it does not git reset,
prune, stop other projects, alter firewall rules, or copy local `.env` files.
Protect Actions/environment configuration and avoid untrusted code on main: it
can execute privileged code on the host via the deployed image.

There are currently no runtime secrets for this MCP-only service. Metrics use
production configuration, but the separate admin dashboard is not deployed.
If secrets are added in future, provision them out of band with restrictive
permissions; do not bake them into images, Compose, logs, or GitHub output.

## Validate and operate

After deployment, on the host check `docker compose -p directed-ideation -f
/opt/directed-ideation/compose.yaml ps` (set `MCP_IMAGE` to the contents of
`state/current-image` first), container logs (no request access logs), and a local MCP
client against `http://127.0.0.1:8001/mcp`. From an independent external host,
verify port 8001 is unreachable over IPv4 and IPv6. Inspect actual Docker port
bindings and cloud/host firewall rules as well; do not rely solely on a failed
probe. Deployment waits up to 120 seconds for Compose health checks. The TCP check
confirms a listener after application startup, not MCP functionality or privacy. Verify functionality after each deploy.

The named Compose volume `directed-ideation_metrics` holds SQLite across image
replacement and restart. The image runs as UID 10001; Docker initializes a new
named volume with the image directory ownership. If using an existing volume,
check permissions before deploying. Restrict volume and backups to trusted
operators; aggregates can reveal usage. Monitor disk space and back up SQLite
using its online backup API (or stop this service and copy the complete database
and any journal files consistently). Store encrypted backups separately, define
retention and periodically test restoration. Do not delete volumes during normal
operations.

For rollback, inspect `state/previous-image` and confirm that image is still present
with `docker image inspect`. From `/opt/directed-ideation`, run:

```sh
MCP_IMAGE="$(cat state/previous-image)" docker compose -p directed-ideation -f compose.yaml up -d --no-build --pull never
```

Verify service and loopback binding again; manually update release markers under
the same `state/deploy.lock` if appropriate before another deployment. Rollback does
not undo SQLite writes; restore an independently verified backup if necessary.
If deployment fails midway, inspect Compose and `state/current-image`/`state/previous-image`
(the markers advance only after health succeeds), then explicitly select a
known-good retained image. Restore the database only after stopping the MCP
service and keeping a copy of the failed state. A failed deployment can leave the failed container running or restarting; it
does not automatically roll back. Marker files are individually atomic but not
a transactional pair: interruption between their updates may change previous
while current remains unchanged. Inspect both before rollback. No automatic
health-based rollback or backup retention is implemented. Compose v2 must
support `up --wait` and `--wait-timeout`. Compare installed Compose and receiver
files with reviewed repository copies before deployment; drift is not detected
automatically.

## Local Podman / Docker checks

With a working Podman machine and Compose provider installed, or Docker Engine
and Compose v2, from the repository root:

```sh
podman build -t directed-ideation-mcp:local .
MCP_IMAGE=directed-ideation-mcp:local podman compose -p di-local -f compose.yaml up -d
MCP_IMAGE=directed-ideation-mcp:local podman compose -p di-local -f compose.yaml ps
# Exercise the MCP endpoint with a local MCP client; invoke a guidance tool.
# Recreate the container, repeat, and inspect metrics to confirm persistence.
MCP_IMAGE=directed-ideation-mcp:local podman compose -p di-local -f compose.yaml up -d --force-recreate
```

Use `docker`/`docker compose` in place of Podman to check Docker compatibility.
Avoid running concurrently with a service already bound to host port 8001.
Stop only the local project with `podman compose -p di-local -f compose.yaml
down` (set `MCP_IMAGE` as above); do not use `-v` if preserving metrics.
Podman Compose provider behavior and rootless networking differ from Docker;
test Docker on the droplet and do not infer external isolation from local tests.
