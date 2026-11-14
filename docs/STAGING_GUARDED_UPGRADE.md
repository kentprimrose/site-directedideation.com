# Guarded staging migration prototype — not approved for live use

This is an incomplete backend migration and recovery prototype. **The CLI
switch command is disabled** because old runtime reproducibility is not yet
proven before mutation. It is not cleared for live use. No nginx, DNS, WorkOS,
or public closure is changed. Independent review and a disposable Podman
rehearsal of the actual guard and failure boundaries remain required; Podman is
the agreed rehearsal environment, not proof of Docker equivalence. Public
closure and separate authorization for each live change also remain required.
Health is not authentication.

## Preconditions and exact sequence after review and authorization

1. Arrange a maintenance window, console access, independently tested closure,
   external verification and an operator responsible for restoration. Record
   fresh container/image identities, Compose version and all tag mappings
   without printing runtime values. Stop if they disagree with the inventory.
   Never put issuer, subjects, tokens or session content in arguments or logs.
2. The original `/home/kent/di-pilot-build.eR6dNHdr/compose.yaml` is pinned to
   `18e3d4bf8a8d5fdbf365fb069c0eae14903a11292197812ae28e44506eff3c45`.
   The original may remain writable: the guard opens it with `O_NOFOLLOW | O_NONBLOCK`, rejects non-regular files, reads
   a bounded byte sequence, verifies the exact digest, and runs Compose only on
   the private snapshot. The snapshot's Compose config hash must exactly equal
   the original container label; relocation changing semantics causes a refusal,
   not a fallback to the original path. The hash is not proof of provenance.
   The old pinned file must not depend on external relative files, includes,
   bind-mounted content, or other mutable inputs; independently inspect its exact
   bytes and rendered semantics before authorization. The guard cannot establish
   this property from a hash alone.
3. Separately install the exact reviewed `staging_mcp/compose.yaml` as root-owned
   `/etc/di-staging/compose.yaml`, with root-owned non-writable ancestors and no
   `.env`. Its required SHA-256 is `8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff`.
   Prepare the lock file `/run/lock/di-staging-allowlist.lock` root-owned and
   non-writable by others. Ensure `/var/lib` is trusted and
   `/var/lib/di-staging-upgrade` is absent. The preservation tag
   `directed-ideation-staging-mcp:upgrade-preserved` must not exist; the existing
   `:rollback` tag is never changed. Do not resolve collisions by deleting tags.
4. Build and review the candidate under a distinct tag without changing `:local`;
   inspect and independently record its full `sha256:...` image ID, functionality
   and provenance. Place the reviewed script in a root-owned trusted location.
   With a separately authorized maintenance window, run:

   `sudo /usr/bin/python3 /ROOT/TRUSTED/upgrade.py switch sha256:<64_HEX_IMAGE_ID>`

   Replace the placeholder with the verified non-secret image ID. The script
   takes the same non-reentrant advisory lock as the allowlist helper; never run
   it while holding that lock or call the allowlist helper inside it. Other root
   or Docker users must be quiescent; advisory locks cannot prevent them racing. Docker tagging is not an atomic
   compare-and-swap: even immediately-before-tag checks cannot exclude an
   uncooperative actor changing state between inspection and mutation. This
   procedure assumes all other root and Docker actors remain quiescent.
   It creates a root-only durable recovery record and exact old Compose copy,
   checks image/config/labels/runtime, pins the old image in a fresh tag, retags
   `:local`, and recreates only `staging-mcp`. The record and candidate baseline
   contain **entire container environments** and must be treated as sensitive.
   Do not print them.
5. Verify staging TLS, metadata, wrong Host, denial for anonymous/unapproved
   clients, approved real-client authorization and tool calls, exposure and
   unrelated services. If unsafe, execute the separately reviewed closure path
   first and verify externally; this tool cannot close the public route.

## Failure and recovery

After any interruption or error, do not rerun `switch`. A record may exist even
before image mutation. If the record is absent or incomplete, preservation tag
is absent, and the old container/tag are demonstrably unchanged, investigate
and reconcile privately. An incomplete record cannot be used automatically.
Otherwise, after deciding closure and obtaining recovery authorization, run:

`sudo /usr/bin/python3 /ROOT/TRUSTED/upgrade.py recover`

Recovery checks the pinned old snapshot, including that its computed Compose
hash still matches the saved old hash, saved environment, expected image IDs and
labels, and refuses foreign tags or container state. It does not require the new
Compose file. It compares selected effective runtime fields to the captured
baseline before replacing a container and after old recreation. A published
candidate baseline includes its complete environment; duplicate environment keys
are rejected. If candidate recreation was interrupted before its baseline was
published, recovery accepts it only if its selected runtime fields match the saved
old baseline and its complete environment matches the old environment plus the
expected host, as well as the candidate image and labels.
Any other candidate runtime or environment requires manual investigation and
recovery; it is not safe to adopt the unverified candidate as a baseline. An already-old container
can still be recovered. Records are published atomically after their contents
are synced; a crash may leave private `.pending-*` files, which are never used
as recovery records and require separate reconciliation. Runtime comparison is not a
complete Docker configuration or external-state audit. It restores
`:local` to the old image and recreates using the **root-only saved snapshot** and saved
runtime environment. It validates the entire old environment, labels, hash,
image and health; then independently verify routing and authenticated behavior.
The snapshot has its own project directory, Compose hash and labels; the original path is not reopened during recovery. A crash during recovery can be retried if state still matches these guards.
If any guard refuses, remain closed and investigate manually; never delete or
retag conflicting resources blindly. Docker daemon failures and interruptions
can leave the state unknown. `:rollback` is not involved. The record and
preservation tag remain after success or recovery; remove them only under a
separate retention/retirement procedure after confirming no recovery is needed.

## Evidence and limits

Unit tests exercise state transitions with mocks. Runtime baseline coverage is
limited to explicitly selected process, host, resource, security, mount and port
fields; network endpoint state, external files, image provenance, and other Docker
settings require independent inspection. Recovery files are checked as mode 0600
in a mode 0700 root-owned state directory; trusted ancestors need not be 0700.
`scripts/rehearse_guard_podman.py` passed switch, recovery, drift and injected
failure checks against guard commit `a5c72bb6d09865f1e1ec6a4524f6f2cae09a9894`.
It loads that Git object, not the current checkout; that object must be locally
available. The harness substitutes synthetic Compose inputs and a Podman adapter,
bypasses root-path trust and the CLI, and injects exceptions rather than process
kills. It does not establish real image identity, actual nginx closure, OAuth,
lock races, filesystem crash durability or Docker/Compose equivalence.
The guard now refuses unexpected, duplicated or renamed Compose project
containers and rechecks the inventory before recreation; those checks are not
atomic against other Docker users. The current CLI switch remains disabled
pending a credible pre-switch reproducibility proof. The pinned-commit rehearsal
predates the new container-inventory checks. No live action was performed.
