# One-time shared-nginx test (offline artifacts)

These scripts are **not installed or run remotely**. Review and authorize them and
all assumptions before use. They target the host's existing `nginx.service`, not
an isolated instance; nginx test/reload affects the entire shared nginx service.
They never stop nginx or modify other services. They do not install firewall rules.

After review, replace the preinstalled rollback with the `di-shared-test-rollback`
wrapper from this directory, and install `di-shared-test-activate` alongside it
in `/usr/local/sbin`, both root:root 0755. Install `di-shared-test` as
`/usr/local/libexec/di-shared-test`, root:root 0755. Ensure all installation
parents, `/etc/nginx/conf.d`, `/var/lib` and their ancestors are root-owned and
not group/world writable, and there are no symlinks in those directories. Verify
the installed files are exactly the reviewed versions. Do not invoke an older
rollback concurrently: it must use the exact same `/var/lib/di-shared-test/lock`.
Root compromise and concurrent unrelated root edits are outside the model.

Before running, verify the fixed source has the expected SHA-256, the existing
loopback configuration is root-controlled, both `.disabled` names and public
file are absent, systemd and nginx are healthy, the rollback command works, and
all public routes/listeners are understood. The source is treated as untrusted:
it is opened without following its final symlink and its bytes are pinned by
SHA-256. A persistent root-owned `used` marker prevents reactivation, including
after failure; do not remove it to extend this one-time authorization. Back up
and review existing nginx configuration independently.

Run `/usr/local/sbin/di-shared-test-activate` as root only with authorization.
It stages the loopback `.disabled` backup and public config under the lock,
then schedules one transient `di-shared-test-rollback-once.timer` for 25 minutes,
validates nginx, and reloads. The timer and manual rollback acquire the same lock;
activation uses a conservative monotonic deadline and bounds each command, so
it will not deliberately start its activation reload after that deadline. On
failure after staging it attempts rollback while still holding the lock. Run
`/usr/local/sbin/di-shared-test-rollback` for early closure; inspect the timer,
journal, restored config, nginx state, and external IPv4/IPv6 reachability.
The pending timer is harmless after early rollback but will reload nginx again.
Rollback refuses to delete unexpected public contents or overwrite loopback;
any error requires immediate operator intervention. A retained marker, timer,
or `.disabled` backup is not authorization to retry activation.

**No hard expiry guarantee:** one-shot transient timers do not survive reboot,
and there is no boot guard or persistent retry. Reboot, suspend, systemd or
scheduler failure, lock contention, failed nginx validation/reload, or a stalled
or independently continuing systemd reload job can leave public workers active.
A timed-out `systemctl` client does not prove its server-side job was cancelled;
a reload started before expiry may finish after expiry, and old workers or
existing connections may persist. Rollback deliberately does not stop shared
nginx, since that would disrupt unrelated services.

For the explicitly approved one-time public compatibility test only, the user
accepted the higher risk of a monitored best-effort cutoff instead of requiring
an independent enforced cutoff. The maximum window remains 30 minutes from
public enablement; the 25-minute one-shot is defense in depth, not proof of
closure or a guarantee that exposure ends by the deadline. This exception does
not unblock pilot activation or authorize recurring tests.

Before enablement, check and record the impact of immediately denying public
TCP 443 with local UFW and using the DigitalOcean cloud firewall as fallback,
including effects on other sites, IPv4/IPv6 and existing connections. Prepare
authorized access and commands for both; these controls can disrupt unrelated
services and may not terminate existing connections. A designated operator must
remain present and monitor the timer, host, public access and abuse signals. If
the timer fails, the host reboots, or timely closure is otherwise in doubt,
immediately apply the prepared local UFW 443 deny and use the prepared cloud
firewall fallback if needed; do not wait for the deadline. Stop early on test
completion or unsafe behavior. Check existing connections separately and verify
from an independent external host that staging is no longer reachable on all
exposed addresses and address families. Record timing, checks and incidents
without secrets; see `../DEPLOYMENT.md` for the complete exception conditions.

Offline tests: `python3 -m unittest discover -s staging_mcp/shared-nginx-test/tests -v`.
`tests/reviewed-public-test.conf` is a byte-for-byte snapshot of the fixed remote
source retrieved for review; the digest test compares this snapshot to the actual
configured digest without mocking it. Recheck the remote source and its review
before any use: the offline snapshot cannot detect subsequent remote changes.
The other tests mock systemd/nginx and do not establish host behavior or network
isolation.
