# One-time public ping expiry: isolated-instance design

These are **uninstalled templates**, not authorization to expose a service. No
remote changes are made by these artifacts. This design requires a dedicated
`nginx-staging-ping.service` with its own nginx master, PID, configuration,
listeners and `nginx.conf` at `/etc/nginx-staging-ping/nginx.conf`; it must
include `/etc/nginx-staging-ping/conf.d/public-ping.conf`. It must not share
listeners or configuration with production. The public file must be the only
route exposing this test, and its absence must leave a valid nginx configuration
with no public test route. Independently verify IPv4, IPv6 and every alternate
route. If these conditions cannot be met, do not use this design.

A root-owned deadline is written **before** the public configuration is
installed. The repeating timer checks it every 15 seconds, including after
boot. Missing, malformed, expired or implausibly distant (>30 minutes) state
is expired. At expiry the checker removes only the named file, validates the
dedicated config, and reloads only the dedicated instance. If validation or
reload fails it attempts to stop that instance and retries every timer cycle.
The ExecStartPre guard removes expired configuration before that instance starts,
including after reboot; failure to remove prevents startup. All other nginx and
services are untouched. A lock serializes guards and checks; all installation
and activation operations must also take that same lock. Never extend/reuse a
deadline for this one-time exception. The timer does not need Persistent=true:
its boot activation and repeating checks cover missed runs.

**Hard limit and fail-safe limitations:** a timer cannot guarantee a strict
30-minute wall-clock maximum: scheduling, lock contention, clock rollback,
suspend, systemd failure, stuck nginx workers or failed stop can delay closure.
Old nginx workers may retain connections after successful reload. `systemctl
stop` may itself fail or hang; this design cannot guarantee isolation in that
case without an independent enforcement mechanism. Use an independently
administered network cutoff with a hard expiry at or before 30 minutes (covering
IPv4/IPv6 and existing connections), and verify it actually works; otherwise
this is not a guaranteed 30-minute window. Use a trusted synchronized clock,
ensure it cannot be set backwards during the window, keep the machine awake,
monitor the timer, processes and outside connectivity, and have an operator
ready to execute the independent cutoff. Do not proceed if any guarantee is
required but cannot be independently enforced. Reload/stop affects all traffic
on the dedicated instance; it must host nothing unrelated. Root compromise is
out of scope.

## Operator procedure (on authorized host only)

1. Review the dedicated unit/configuration and test isolation, absence behavior,
   startup, reload, stop, boot guard and independent network cutoff. Ensure a
   verified backup and an authorized operator/contact. Do not copy any runtime
   production configuration into this repository.
2. Install `rollback` as `/usr/local/sbin/staging-ping-rollback` (root:root
   0755); install the service and timer in `/etc/systemd/system/` (root:root
   0644), and the guard as
   `/etc/systemd/system/nginx-staging-ping.service.d/guard.conf` (root:root
   0644). Create `/var/lib/staging-ping-rollback` root:root 0700. Ensure every
   parent directory, the dedicated configuration and units are root-owned and
   not writable by unprivileged users; no untrusted symlinks. Check effective
   unit with `systemctl cat nginx-staging-ping.service`, verify guard is present
   and runs as root, then `systemctl daemon-reload` and
   `systemctl enable --now staging-ping-rollback.timer`. Verify timer is active.
3. With network cutoff initially closed, hold the exact same lock used by the
   checker (`flock /var/lib/staging-ping-rollback/lock ...`) throughout deadline
   creation and configuration installation. Write the decimal UTC epoch deadline
   to a root-owned 0600 file at `/var/lib/staging-ping-rollback/deadline`, at
   most 30 minutes from **before** any public exposure; atomically install the
   reviewed public file at the fixed path. Validate the dedicated configuration
   and reload the dedicated unit, then release the lock. Open the independent
   cutoff only after confirming its expiry is no later than this deadline.
   Record the deadline, owner, time opened, and cutoff evidence. If any operation
   fails, close cutoff and run the rollback immediately; do not proceed.
4. Monitor externally and close the independent cutoff at test completion,
   error, or deadline, whichever comes first. To terminate early, close cutoff,
   remove the deadline under the same lock, release the lock, then run
   `systemctl start staging-ping-rollback.service`. Confirm the file is absent,
   the dedicated service is safely reloaded/stopped, and external connections
   are rejected on all paths. Check `journalctl -u staging-ping-rollback.service`
   and `systemctl list-timers staging-ping-rollback.timer`; failures require
   immediate intervention. Leave the guard and timer installed until confirmed
   safe. Do not reactivate without new authorization.

Run `python3 -m unittest discover -s staging_mcp/public-ping-rollback/tests -v`
locally. Tests simulate commands and paths; they do not exercise systemd,
nginx, the kernel, firewall, reboot or a real clock adjustment. Target-host
integration and independent cutoff tests are mandatory before exposure.
