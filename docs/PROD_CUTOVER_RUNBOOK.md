# Pilot cutover package and runbook (steps 4–5 of `PROD_DEPLOY_PLAN.md`)

Standalone companion to `docs/PROD_DEPLOY_PLAN.md`. It does not replace or edit
that plan, `PLAN.md` or `staging_mcp/DEPLOYMENT.md`.

**Pilot status.** The production host has been cut over for trusted users.
The backend record and apply steps and nginx cutover were run on the host;
future live operations still require separate authorization. Historical planning
and offline test notes below are not evidence of the current live state.
Placeholders must come from a fresh inventory and are not runnable as written.

The production Pi-Bolt client signed in with CIMD and successfully called `ping`
and `get_directed_ideation_method`. External TLS, metadata, anonymous rejection,
wrong Host/SNI rejection, and closed backend-port checks passed. A Certbot renewal
simulation and an isolated invocation of the production reload hook each passed;
a combined automatic renewal with deploy hooks has not been verified.

**Remaining access-control test:** Sign in as a different, valid production
WorkOS user who is not in the MCP allowlist, and confirm the production MCP
server rejects their authenticated request. Do not add that user to the
allowlist for this test. Creating or signing in a test user may incur WorkOS
billing; obtain approval first. Do not record user IDs, tokens, or authorization
URLs in test results.

The private backend record is `/var/lib/di-staging-cutover/pilot-production-01`;
the root-only production settings file is retained beside it. Nginx cutover
backups are in `/var/lib/di-shared-test/cutover-transition.fSrnF3kf`. The old
staging endpoint is not currently serving MCP, and restoration requires both the
backend and nginx changes described below—not just an image retag.

## 1. What exists

| Artifact (`staging_mcp/prod-cutover/` unless noted) | Purpose |
|---|---|
| `build_package.py` | Renders, from the reviewed repo files, the new-host public conf, the ACME-only HTTP-01 vhost, the rollback helper accepting three digests, and the renewal hook; writes `SHA256SUMS`. Refuses any host except `mcp.directedideation.com`, refuses an existing output directory, asserts every substitution. |
| `install-nginx-cutover.sh` | Nginx transition under `/var/lib/di-shared-test/lock`: drift check, helper first, then conf, `nginx -t`, reload only on success, recovery of the old conf, backups outside the include tree. Also performs **restoration** with roles swapped (section 6). |
| `backend-transition.sh` | `record` / `apply` / `restore` of the `di-staging` container under `/run/lock/di-staging-allowlist.lock`. |
| `certbot-deploy-hook.sh` (template) | Reloads nginx only for the `mcp.directedideation.com` lineage, under the nginx lock. |
| `probe_external.py` | Read-only `closed` / `open` / `loopback` probes. Requires an explicit `--ip`; no defaults. |
| `scripts/test_staging_proxy_isolated.py` | Rehearsal harness, now parameterized (section 8). |
| `tests/test_prod_cutover_{backend,nginx,probe}.py`, `tests/cutover_shims.py` | Offline tests. |

## 2. Blockers: unknown until the live inventory (plan step 2)

Do not proceed to a live step while any of these is open.

1. **Live digests.** The scripts take the old conf and old helper digests as
   arguments. The repo constants (`7f840890…` current, `814b89c8…` previous)
   are *historical*; the live file may differ. If it does, stop and reconcile.
2. **What the closed state exposes on :443.** The package's public file
   carries the only `default_server ssl_reject_handshake` for `0.0.0.0:443`.
   When closure removes that file, whether another site becomes the implicit
   default on :443 is unknown (needs `nginx -T`). `probe_external.py closed` is
   strict by default and will **fail** if anything completes TLS for unknown or
   missing SNI. Use `--shared-listener` only after the inventory documents that
   unrelated sites legitimately answer there. The plan's requirement that
   closure "does not make another site the implicit default" is therefore
   **unconfirmed**; this package can only detect it from outside.
3. **Reviewed compose digest** accepted by the live `/etc/di-staging/compose.yaml`
   (`add-allowed-user.sh` pins one). `backend-transition.sh record` takes it as
   an argument and refuses a mismatch.
4. **Image supports `STAGING_MCP_HOST`** (commit `19c58cf`) and a `:rollback`
   tag exists equal to the running image ID (plan step 3, a live change).
5. **Production issuer origin and `user_...` IDs** (plan steps 6–8). Not
   available; the new-env file cannot be written until they are.
6. **Droplet IPv4, DNS, certificate lineage and `certbot.timer`** (steps 9–10)
   for the probes and for the hook path `/etc/letsencrypt/live/<host>`.
7. **Timer/unit names** `di-shared-test-rollback-once.{timer,service}` are
   taken from the installed helper source; confirm they match the host.
8. **Step 7 (identity collection)** is documented in the plan as not complete;
   this package does not cover it.

## 3. Locks and order

| Lock | Protects | Taken by |
|---|---|---|
| `/run/lock/di-staging-allowlist.lock` | container, image tag, compose inputs, allowlist | `backend-transition.sh` (all modes), `add-allowed-user.sh` |
| `/var/lib/di-shared-test/lock` | nginx conf, helper, rollback | `install-nginx-cutover.sh`, `di-shared-test` (activate/rollback), certbot hook |

Both are non-reentrant `flock` locks. Rules, each covered by a test:

- Each script takes its own lock. **Never run one inside a shell already
  holding the same lock**: it times out (10 s) instead of deadlocking, and
  makes no change.
- **Never call a lock-taking helper while holding its lock.** The nginx
  installer does not call `di-shared-test-rollback`, `activate`, or
  `systemctl stop/disable`.
- The two locks are never held together by these scripts, so no ordering
  can deadlock. Run backend first and nginx second (plan steps 11, 12), as
  separate invocations.
- The nginx installer refuses to run while the rollback timer or service is
  not `inactive`. Coordinate the timer deliberately; it does not disable it.
- The lock is held until after `nginx -t` and the reload request. A test
  checks, from inside the mocked `nginx` and `systemctl`, that the lock is held
  at both calls.
- Advisory locks do not stop root or Docker-privileged processes that ignore
  them.

## 4. Local preparation (safe, no live contact)

```sh
uv run pytest tests/test_prod_cutover_backend.py tests/test_prod_cutover_nginx.py tests/test_prod_cutover_probe.py
uv run python staging_mcp/prod-cutover/build_package.py --out <NEW_EMPTY_DIR>
```

Review the printed digests against `SHA256SUMS`; commit/store them as evidence.
The new helper digest is derived from the rendered conf, so the three
digests must be taken from one build. Rebuilding from changed repo files yields
different digests; never mix builds.

Staging on the host (a later, authorized step): copy the build directory to a
root-owned, non-web-accessible directory **outside** `/etc/nginx`, then re-hash
there before use.

## 5. Cutover (each numbered item needs its own go-ahead)

Prerequisites: plan steps 1–10 complete and evidenced; users notified; rollback
artifacts preserved and hashes recorded; rehearsal passed from the same build;
a console path to the host and an external machine for probes.

1. **Record (read-only, but takes the lock).** Before the window:
   `sudo backend-transition.sh record <NAME> <REVIEWED_COMPOSE_SHA256>`.
   Writes `/var/lib/di-staging-cutover/<NAME>` (root, 0600, contains the old host,
   issuer and allowlist; values are not printed). Never overwrites a record.
2. **Backend.** Create the new-env file as a root-owned 0600 file containing
   exactly `STAGING_MCP_HOST`, `WORKOS_STAGING_ISSUER`,
   `WORKOS_STAGING_ALLOWED_SUBJECTS` as `KEY=VALUE` lines (not via shell
   history or argv). Then `sudo backend-transition.sh apply <NAME> <NEW_ENV_FILE>`.
   It refuses unless the container ID, image tag/ID, config-hash label,
   environment and compose-rendered hash all equal the record, checked twice;
   refuses a new issuer equal to the old, a host other than the production host,
   or malformed values; recreates only `staging-mcp` with
   `--no-build --pull never --no-deps`; verifies image and environment after;
   waits for healthy.
   Then, on the host: `probe_external.py loopback --host mcp.directedideation.com
   --issuer <PROD_ISSUER_ORIGIN> --old-host mcp-staging.directedideation.com`.
   Retain the root-owned 0600 production env file as the pilot's protected
   source for future Compose recreations. A Docker restart retains the existing
   container environment, but a later `docker compose up` must explicitly use
   these production values; it cannot infer them from the existing container.
   Do not run an ordinary Compose recreation with missing or staging values.
   A separate reviewed operator procedure is required for future recreations;
   `apply` itself is a one-time transition and cannot be blindly reused.
3. **Nginx.** With the build directory staged:
   `sudo install-nginx-cutover.sh <STAGED_CONF> <STAGED_HELPER> <OLD_CONF_SHA256_FROM_INVENTORY> <OLD_HELPER_SHA256_FROM_INVENTORY> <NEW_CONF_SHA256> <NEW_HELPER_SHA256>`
   (new digests from `SHA256SUMS`). It checks: lock, timer and service inactive,
   live conf/helper equal to the supplied old digests, loopback `.disabled`
   backup present, staged files read once without following symlinks and equal
   to the new digests, and that the new helper contains both the new and old conf
   digests. It installs the helper first, then the conf, then `nginx -t`, then
   reload. On failure it restores the old conf and reloads; the new helper
   stays (it accepts the old digest). If recovery also fails it says so: use
   the closure path in section 6 immediately.
4. **Users** change URL and reauthorize (plan step 13).
5. **Verify externally** from a machine that is not the droplet:
   `probe_external.py open --host mcp.directedideation.com --ip <DROPLET_IPV4_FROM_INVENTORY>`
   (add `--burst 40` only if a rate-limit test is authorized). It checks verified
   TLS and certificate lifetime, anonymous 401 with challenge, wrong Host dropped,
   unknown/no SNI not served, and 8001/8765 not reachable. It does **not**
   check tokens, OAuth, client behaviour, IPv6 or unrelated-site health; plan
   step 14's remaining items are manual.

### Failure decision table

| Failure point | State | Action |
|---|---|---|
| Record/apply refuses (drift, bad input, lock) | Unchanged | Reconcile; no recovery needed. |
| `apply` fails after recreation | Backend unknown; old nginx still routes the old host | Inspect; `restore` (section 6) or stay closed. |
| Nginx install fails, recovery succeeded | Old nginx conf, **new-host backend** | Old host now returns 400. Run backend `restore`. |
| Nginx install fails, recovery failed | Unknown public exposure | Closure (section 6) first, then decide. |
| Probe fails after success | Unsafe or unknown | Closure first, then investigate. |

## 6. Emergency closure and service restoration (two separate outcomes)

**Emergency closure** = no public MCP routing, the listener still fails closed.

1. Run the installed wrapper `di-shared-test-rollback` (it takes the nginx lock
   itself; do not hold it). The rendered helper removes the public file only if it
   matches one of the three accepted digests, restores the loopback conf from its
   `.disabled` backup, runs `nginx -t`, and reloads. It refuses an unrecognised
   file by design; that needs manual work.
2. **The exit status is not proof.** Run, from outside:
   `probe_external.py closed --host mcp.directedideation.com --ip <DROPLET_IPV4_FROM_INVENTORY>`
   Reload leaves old workers and connections briefly alive; repeat the probe
   after a short wait. Blocker 2 applies.

**Service restoration** = old image, host, issuer, allowlist, nginx and routing
together, then end-to-end verification. Retagging an image is not rollback.

1. Closure first if the new service is unsafe.
2. Backend: `sudo backend-transition.sh restore <NAME>`. It refuses if the
   tag no longer points at the recorded image ID, recreates with the recorded old
   host/issuer/allowlist, and succeeds only if the compose config-hash label
   equals the recorded one and the container is healthy.
3. Nginx: the saved old file is in `/var/lib/di-shared-test/cutover-transition.*/old-conf`.
   Run the same installer with roles swapped:
   `install-nginx-cutover.sh <SAVED_OLD_CONF> <INSTALLED_HELPER> <NEW_CONF_SHA256> <NEW_HELPER_SHA256> <OLD_CONF_SHA256> <NEW_HELPER_SHA256>`
   (staged conf = saved old file; the helper is already current, so both helper
   digests are the installed helper's). It refuses unless the live file is
   exactly the new conf.
4. Verify the **old** endpoint end to end (old host, old issuer, a real client).
   `probe_external.py open` accepts any `--host`, but the old host's cert and
   vhost are not rendered by this package.
5. If restoration is unsuitable, stay closed and recover offline. Do not send
   ordinary traffic back to WorkOS staging beyond the trusted set.

## 7. Renewal hook

`certbot-deploy-hook.sh` is a template (`@HOST@`); `build_package.py` renders it.
Install it root:root 0755 under `/etc/letsencrypt/renewal-hooks/deploy/` only
after review. It exits 0 without action for any other `RENEWED_LINEAGE`; for
the new lineage it takes the nginx lock (60 s), runs `nginx -t`, then reloads, and
fails (non-zero) if the lock is busy, the lock file is missing (it never creates
it) or validation fails. Unverified live: `certbot renew --dry-run
--run-deploy-hooks`, hook path, timer. Use `certbot certonly --webroot`, never
`--nginx`.

## 8. Rehearsal (local, disposable networkless Podman pod)

```sh
uv run python staging_mcp/prod-cutover/build_package.py --out <NEW_EMPTY_DIR>
STAGING_TEST_HOST=mcp.directedideation.com \
STAGING_TEST_CONF=<NEW_EMPTY_DIR>/di-staging-public-test.conf \
uv run python scripts/test_staging_proxy_isolated.py
```

Needs local `nginx:stable-alpine` and the staging check image. It runs the
**rendered artifact** (not the example) with the backend pinned to the new Host
and checks: anonymous 401, invalid and unapproved-subject tokens, old-host
audience, wrong issuer, expired token, old-host SNI rejected, wrong Host dropped,
unknown/no SNI rejected, valid token 200, authenticated `ping`, burst 429; then a
failed `nginx -t` that leaves serving undisturbed, emergency closure (default
listener only; all three SNI cases rejected), and restoration of the same
artifact. With no variables it reproduces the original staging-host test. It
proves **nginx behaviour only**: not DNS, certificate issuance or renewal,
WorkOS, rollback-helper file handling on a real host, or the real
loopback-versus-public listener layout.

## 9. Evidence from this implementation (local only)

- New tests: 71 (backend 28, nginx/builder/hook 31, probe 12), all offline and
  passing. A full-suite run made just before the final two restoration tests
  were added passed 257 (the pre-existing 188 plus 69 new). Those 2 tests have
  only been run in the targeted 71-test run, not in another full-suite run.
- Rehearsal ran locally with defaults and with the rendered cutover artifact; both
  passed.
- The probe's assumptions (metadata path, `resource_metadata` challenge, 400 for
  the old Host) were checked against the real app in the local image only.
- Shell scripts were exercised with shims for `flock` (real `fcntl` semantics),
  `stat`, `sha256sum`, `install`, `timeout`, `systemctl`, `nginx` and a stateful
  Docker mock. Ownership/mode checks use a shim that reports uid 0. **Not
  exercised: GNU coreutils behaviour, real Docker/Compose, systemd, real
  nginx reload semantics, root-owned directory checks.** Run the scripts'
  syntax and behaviour through a review on a Linux host before use.

## 10. Remaining work

- Inventory (blockers above); then decide the digests and the `--shared-listener`
  question.
- Obtain explicit authorization per live operation, starting with plan step 3.
- Plan steps 6–10 (WorkOS production, identities, OAuth verification, DNS,
  certificate) have no automation here.
- A Linux dry run of the three shell scripts (for example `shellcheck`, which was
  not available locally) and, ideally, a throwaway-VM rehearsal of the real
  helper/timer/lock interplay.
- Decide the verification deadline and observation period (plan step 14, 16).
- Step 17 (retiring the old host) is out of scope.
