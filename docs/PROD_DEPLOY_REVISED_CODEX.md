# Revised deployment plan: `mcp.directedideation.com`

Prepared 2026-11-04 after comparing the four original deployment reviews:
[Claude](PROD_DEPLOY_CLAUDE.md), [Codex](PROD_DEPLOY_CODEX.md),
[Gemini](PROD_DEPLOY_GEMINI.md), and [Pi](PROD_DEPLOY_PI.md).
Also compared the [revised Claude plan](PROD_DEPLOY_REVISED_CLAUDE.md) and
[revised Pi plan](PROD_DEPLOY_REVISED_PI.md), which appeared during this review.
Implementation was checked against repository HEAD `a35fc4b`, including
`staging_mcp/server.py`, Compose, rollback tooling, and the deployment guidance.
No live infrastructure was inspected or changed.

## Decision

Use the existing authenticated service, current host, nginx, and small subject
allowlist. Move it to `https://mcp.directedideation.com/mcp` through a scheduled
single-host cutover with client reauthorization. Keep the public proxy pointed
at `127.0.0.1:8765`; port 8001 is the separate unauthenticated private prototype.

For customer-facing use, configure WorkOS production and rebuild the allowlist
using production user IDs. A hostname-only move retaining WorkOS staging is an
alternative only for continued internal testing within the provider's supported
scope. Do not perform that intermediate move merely to repeat the migration for
real users later.

The shortest customer-facing route is therefore **the current authenticated
application plus production identity configuration, a reviewed proxy/rollback
package, and the applicable launch checks**. No application feature changes are
known to be necessary for hostname selection. Production OAuth compatibility
still needs live verification.

## Comparison and resolution

| Topic | What the reviews say | Revised decision |
| --- | --- | --- |
| Architecture | All favor reusing the authenticated pilot and keeping port 8001 private. | Retain the current host, nginx, port 8765, and allowlist approach. |
| WorkOS environment | Claude, Gemini, and Pi favor retaining staging for the renamed pilot; Codex distinguishes internal testing from customer-facing use. | Use production for real end users. Pilot terminology alone does not establish an exception to WorkOS guidance. |
| Launch gates | Claude and Gemini emphasize broader-production blockers; Pi identifies a discrepancy between the original pilot gates and the active-pilot notes; Codex calls for reconciliation. | Record which gates are satisfied and the scope of any explicit project decision before customer-facing cutover. Do not infer a waiver from historical pilot operation. |
| Repository state | Claude and Gemini describe migration work as uncommitted. Pi and Codex identify those claims as stale. | Hostname support is committed. The original Codex review and Pi review are currently untracked documents; that is separate from application readiness. Verify the actual deployed image. |
| Hostname default | Claude proposes changing defaults; Codex recommends an explicit environment value. | Set `STAGING_MCP_HOST` explicitly; preserve Compose bytes and the allowlist helper's pinned digest. |
| Proxy rollback | All identify pinned-config risks. Gemini offers a separate config as one workaround; Codex notes the old shutdown script would miss it. | Use a reviewed replacement of the existing pilot public config, with coordinated recovery tooling covering every resulting state. Avoid an additional uncovered public route. |
| Build | Gemini proposes building through the installed Compose file; Codex identifies the relative-context mismatch. | Reuse the running image if suitable. Otherwise build through the reviewed checkout and deploy through the trusted installed Compose file without building or pulling. |
| Rehearsal | Claude points to the existing isolated proxy harness; Codex notes it hardcodes the staging host/example. | Exercise the actual new-host artifacts and both recovery paths, then verify live OAuth and routing separately. |
| Outage | Reviews favor a small coordinated cutover; Gemini estimates about 30 seconds. | Accept a brief scheduled outage. Establish a verification deadline during rehearsal; do not promise a fixed duration. |
| Revised Claude proposal | Corrects the default/build/rehearsal advice and proposes one public file containing both hostname routes, with updated accepted digests. Still recommends staging first for existing pilot users and describes unlinking the public file as closure. | Adopt one coordinated artifact and script-first installation. Prefer one customer-facing migration using production identity. An unchanged participant list does not establish a staging exception; removing a file containing the fail-closed default requires effective-listener checks and is not proof of closure. A second hostname route is optional, since the backend still accepts only one host. |
| Revised Pi proposal | Corrects its original staging recommendation, adopts the build and closure findings, and requires live inventory and scope reconciliation. | Substantially aligned. Make the proxy strategy, two recovery outcomes, explicit target environment, and post-cutover observation period concrete as described below. |

WorkOS says production is intended for real end users and customer-facing HTTPS
URLs, and staging is not intended for customer-facing traffic. Environments are
isolated; production users and configuration do not automatically carry over.
See [WorkOS environment guidance](https://workos.com/docs/authkit/environments),
checked during the preceding review on 2026-11-04.

## Scope and prerequisites

The intended initial audience remains approximately 2–5 personally approved US
participants. Broader availability and paid subscriptions are separate milestones.
Defer new billing, a second authentication stack, dual-host application support,
replacement hosting, and replacement of nginx.

`docs/PLAN.md` requires legal review, independent security review, privacy disclosures,
US eligibility/processing controls, and client validation before the pilot.
`docs/staging_mcp/DEPLOYMENT.md` describes an active non-sensitive pilot with accepted
residual risks. This review cannot determine whether those requirements were
met or explicitly revised. Before customer-facing cutover, record the applicable
scope and evidence, and reconcile the documents through an explicit project
decision. This plan does not waive those requirements or approve general launch.

If team/account features are deferred for the narrow allowlisted release, record
that scope decision against `docs/PLAN.md`; do not silently redefine its requirements.
Account for the identity data held by WorkOS even though the MCP application
does not persist ideation sessions or run the prototype's metrics lifecycle.

## Execution plan

### 1. Inventory the live state without changing it

Record the running image ID and local tag relationship, hostname-switch support,
installed Compose path and project directory, Docker/Compose versions, effective
nginx configuration, DNS A/AAAA records, certificate/renewal setup, issuer,
allowlist, installed helpers, and rollback dependencies. Verify the actual
intended host address rather than copying the historical IP from a review.

Inspect all relevant listeners and inherited proxy/logging settings. Confirm
ports 8001 and 8765 are private, and record baseline health for unrelated sites
and the private service. Check whether the deployment already uses the trusted
`/etc/di-staging/compose.yaml` and `/etc/di-staging` project directory required by
the allowlist helper. Any necessary migration to that layout is a separately
planned deployment change with its own recovery state.

Preserve the current issuer, allowlist, image, nginx bytes, certificates, and
recovery artifacts securely. Do not dump container environments or credentials
into logs. Record hashes and image identities as evidence.

### 2. Prepare one cutover and recovery package

Prepare a new-host version of the existing pilot public nginx artifact. Retain
the reviewed fail-closed listener behavior, define rate/connection zones once,
use the new certificate lineage, and continue proxying only to port 8765.
Validate the complete host configuration for conflicts and inherited behavior.
Do not copy a second `default_server` or duplicate zone declarations alongside
the existing ones.

Prepare two distinct recovery operations:

- **Emergency closure:** stop public MCP routing while retaining fail-closed
  listener behavior and unrelated services. A reviewed closed configuration must
  not accidentally make another site the listener's implicit default.
- **Service restoration:** restore the exact prior image, hostname, issuer,
  allowlist, proxy configuration, and client endpoint, then verify functionality.

Update the installed recovery tooling to recognize the reviewed old, new, and
closed states as applicable. Install and verify compatible recovery tooling
before activating the new config. Preserve old artifacts; do not merely replace
a recorded digest or assume the legacy script covers new files. Use the atomic
installation and coordination principles in `adjust-live-rate.sh` and the
deployment notes, adapted to these exact artifacts.

Specify lock acquisition and release order in the runbook for both
`/run/lock/di-staging-allowlist.lock` and `/var/lib/di-shared-test/lock`.
Coordinate any existing timers or rollback invocations. Do not invoke a
lock-taking helper while already holding its non-reentrant lock.

Prepare the new-host HTTP-01 config and lineage-scoped renewal hook. Adapt the
isolated rehearsal to the actual hostname/configuration and test successful
cutover, failed validation, emergency closure, and restoration. The existing
harness's old-host test and injected key are insufficient evidence on their own.

### 3. Pre-provision DNS, TLS, and production identity

Create the new A record only after verifying the destination. Keep the old
hostname available for recovery. Do not add AAAA for an IPv4-only deployment;
verify actual IPv6 listeners and exposure independently.

Use the reviewed ACME-only HTTP route to obtain the new certificate before
loading the TLS configuration. Use Certbot webroot issuance rather than letting
Certbot rewrite nginx. Validate the complete configuration before reload, check
external challenge reachability and non-challenge denial, and verify renewal
scheduling, hook behavior, and expiry monitoring. Preserve unrelated sites and
certificate lineages.

For the recommended customer-facing route, enable/configure WorkOS production,
including the required MCP client-registration settings and exact resource:

```text
https://mcp.directedideation.com/mcp
```

Establish the approved participants' production identities through the supported
WorkOS flow and assemble their exact production subject IDs. Check email
verification, recovery, and signup restrictions against the chosen launch scope.
Keep the old WorkOS environment and resource available for recovery.

The existing variable names can remain:

| Variable | Customer-facing target value |
| --- | --- |
| `STAGING_MCP_HOST` | `mcp.directedideation.com` |
| `WORKOS_STAGING_ISSUER` | Exact canonical production Connect issuer origin |
| `WORKOS_STAGING_ALLOWED_SUBJECTS` | Approved production WorkOS subject IDs |

Verify actual production discovery, JWKS, access-token audience/subject/expiry,
ID-token separation, refresh, and revocation behavior using secure clients in a
controlled setup. The application's acceptance of a configurable issuer is not
proof that production OAuth has been tested. See
[WorkOS MCP guidance](https://workos.com/docs/authkit/mcp).

### 4. Select the release image

Reuse the deployed image if its identity, source, hostname support, and security
state are suitable for the reviewed release. Otherwise preserve the running
image and build once from a reviewed commit. Generate the isolated context using
`scripts/prepare_staging_build_context.py`, then build using the checkout's
`staging_mcp/compose.yaml`.

Do not build through `/etc/di-staging/compose.yaml`: its relative `.build-context`
would resolve under `/etc/di-staging`, unlike the context preparation script.
Deploy through the verified installed file using `--no-build --pull never`,
project `di-staging`, and the verified project directory. Hold the documented
staging lock for image/tag and deployment mutations.

Preserve Compose defaults and the helper's pinned digest. Ensure future operator
deployments explicitly retain the selected hostname, issuer, and current
allowlist; do not rely on a temporary shell that will be lost. Confirm the
installed allowlist helper preserves those settings after cutover.

The current GitHub Actions workflow deploys only the private service. Pushing to
`main` can change that service but does not deploy the authenticated pilot.

### 5. Perform the scheduled cutover

After prerequisites and rehearsal pass, schedule a brief interruption and give
participants the new endpoint and reauthorization instructions. This plan does
not send those communications or change live infrastructure.

Under the coordinated locks, verify no drift from the recorded state, recreate
only the authenticated service using the selected image and explicit target
environment, and check loopback health and metadata. Atomically install the
reviewed public nginx config, run `nginx -t`, and reload only on success.

The application accepts one Host and one audience. Old-audience tokens are
rejected at the new endpoint, and the old hostname stops serving this backend.
Do not rely on redirects or copying old bearer tokens. If any step fails, use
the prepared closure/restoration procedure rather than continuing with mixed
configuration.

### 6. Verify the result before declaring completion

| Area | Required evidence |
| --- | --- |
| Routing/TLS | Correct DNS, certificate identity, intended IPv4/IPv6 behavior, and working renewal setup. |
| Discovery | Protected-resource metadata advertises the exact new resource and selected issuer; the 401 challenge supports client discovery. |
| Authorization | Anonymous requests return 401; wrong-issuer, wrong/old-audience, expired, invalid, and non-allowlisted tokens fail. |
| Host boundary | Missing/unknown SNI and unexpected Host cannot reach either backend on the reviewed listeners. |
| Real clients | Successful reauthorization, discovery, `ping`, all four guidance tools, and stage filtering in the clients required by the agreed launch scope. Preserve docs/PLAN.md's requirements unless explicitly revised. |
| Input/privacy | Invalid tool inputs fail without echoing submitted content; synthetic checks find no tokens or content in effective logs. |
| Operations | Public rate limiting, acceptable client backoff, refresh/expiry, and removal of an approved subject are verified. Healthcheck 401 alone is insufficient. |
| Isolation | Ports 8001/8765 remain externally inaccessible; unrelated sites and the private service retain baseline health. |

Record evidence without tokens or session content. Use a defined verification
deadline and restore or close access on unsafe behavior or unresolved failures.
Monitor availability, authentication failures, resource usage, certificate
expiry, and abuse signals during the agreed observation period.

## Recovery and completion

Emergency closure and service restoration have different outcomes: explicitly
verify which was achieved. Nginx reloads and existing connections can delay
effective closure; successful file replacement or script exit alone is not proof.

Restoration must use the saved old hostname, issuer, allowlist, image, and proxy
configuration. Preserve the old resource registration and certificate. Clients
may need to return to the old endpoint and reauthorize. Do not send ordinary
customer traffic back to WorkOS staging without resolving the same environment
restriction; where that is unsuitable, close public access and recover offline.

Do not retire the old resource, certificate, or recovery artifacts until the new
deployment has passed verification and the agreed observation period. Retire the
old public MCP route deliberately, without relying on a redirect to migrate OAuth.

Completion means the exact new endpoint works for approved participants, access
boundaries and recovery are verified, renewal and monitoring are operational,
and the repository's deployment/scope records describe the actual release.
It does not imply general production approval or commercial readiness.

## Evidence and next action

The preceding Codex review ran all 188 repository tests successfully. This
comparison changes documentation only; the suite was not rerun. None of these
reviews establishes live DNS, host, or production WorkOS state.

The next execution step is a read-only live inventory and reconciliation of the
pilot gates, followed by preparation of the exact new-host proxy and recovery
package. This document records the revised plan; it does not execute it.
