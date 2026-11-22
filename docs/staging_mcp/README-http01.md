# Production HTTP-01 vhost installer (offline artifact)

This is not authorization to operate the host. Each live operation requires
separate approval. Review the parent `docs/PROD_CUTOVER_RUNBOOK.md`, the uploaded
artifact and this script before any use. It has fixed paths and hashes and accepts
no arguments. It installs only the pinned HTTP-01 vhost; it does not issue a
certificate, modify TLS/MCP routing, DNS, firewall, timers or backend.

Before requesting approval, independently inspect the exact uploaded artifact
(including its host, port 80, challenge root and fail-closed non-challenge
behavior), nginx's complete effective configuration, listener/default-server
interactions, IPv4/IPv6 DNS, health and external routes. The pin is not semantic
validation and this repository does not contain the uploaded bytes. Confirm the
rollback timer and service are inactive, prevent new invocations (including
already-running helpers waiting for the lock), and coordinate all other nginx
writers. Ensure the nginx lock and its parent, nginx conf directory and `/var/lib`
are root-owned and non-writable by others, with no symlink components. Ensure
existing challenge directories are root-controlled and publicly traversable.
Back up the configuration and prepare a separately approved recovery procedure.
The lock is advisory, and unrelated root edits are outside the safety model.

After explicit approval for this operation, a root operator can run the reviewed
script with `sudo python3 staging_mcp/install-production-http01.py`. It refuses
any existing target, even the same bytes, checks both fixed digests, and holds
`/var/lib/di-shared-test/lock` through validation and reload. It creates the
webroot directories if absent and leaves them in place even on failure. On a
post-publication failure it removes only its own unchanged inode and requests a
validated recovery reload; failure to recover demands immediate intervention.
A timeout of `systemctl` does not prove its server-side job was cancelled. A
crash, SIGKILL, power loss, or interruption during recovery can leave the vhost
installed or nginx workers in an unknown state; there is no crash-recovery
journal. Inspect the target, running workers, nginx status and all affected
routes independently before retrying or taking further action. A successful
reload request is not proof of external behavior. Do not invoke this while
already holding the same lock.

Offline tests: `python -m pytest tests/test_http01_installer.py`. They use mock
systemd/nginx, temporary paths and simulated ownership; they do not validate
real host ownership, systemd, the uploaded bytes, or live routing.
