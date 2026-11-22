# Revised plan: move the hosted MCP service to `mcp.directedideation.com`

## Decision in brief

Use the existing authenticated service, nginx, and private backend on port 8765. Pre-provision the new hostname, then perform a scheduled single-host cutover with client reauthorization. Do **not** expose the unauthenticated service on port 8001.

**Choose the identity environment based on actual use, not the hostname:**

- For internal development, testing, or internal demonstrations only, retain WorkOS staging and the existing staging allowlist.
- For real end users or a customer-facing URL, use WorkOS production, even for an invite-only pilot. Recreate the required configuration and allowlist using production identities, and complete or explicitly resolve the project's applicable launch gates before inviting users.

WorkOS says staging is for testing, not customer-facing traffic; its production environment is intended for real end users and customer-facing HTTPS URLs. Environments are isolated and users do not automatically transfer. Production requires billing information to unlock. Verify current requirements and pricing directly before proceeding: [WorkOS staging and production environments](https://workos.com/docs/authkit/environments); [WorkOS MCP guidance](https://workos.com/docs/authkit/mcp).

This corrects the earlier Pi recommendation that retained staging for an invite-only pilot without distinguishing testing from real end-user use. A cleaner URL alone is not a production launch, and a pilot label does not establish a WorkOS staging exception.

## Comparison of the four reviews

| Document | Useful contribution | Revision or qualification |
| --- | --- | --- |
| `PROD_DEPLOY_CLAUDE.md` | Separates hostname migration from general launch; identifies single-audience cutover, certificate work, and digest-pinned rollback. | Its uncommitted-work claim is stale. Retaining WorkOS staging is suitable only for testing within WorkOS's supported scope. Changing the Compose hostname default is unnecessary; set it explicitly. |
| `PROD_DEPLOY_GEMINI.md` | Identifies duplicate nginx rate-limit zones and the pinned rollback hazard; gives a concrete deployment sequence. | Its uncommitted-work claim is stale. A separate new-host vhost is not covered by the existing rollback script merely because the old file is untouched. Its suggested build using `/etc/di-staging/compose.yaml` resolves the relative build context under `/etc/di-staging`, not the checkout's generated context. Do not assume a 30-second or atomic cutover. |
| `PROD_DEPLOY_PI.md` | Calls out the project approval-gate discrepancy, separate private service, operational inventory, and end-to-end rollback. | Its staging-based pilot recommendation needs the customer-facing distinction above. Its account of local Git state was a point-in-time observation, not evidence of the deployed version. |
| `PROD_DEPLOY_CODEX.md` | Adds the WorkOS environment distinction, incomplete emergency-closure coverage, build-context mismatch, and limitation of the existing proxy rehearsal. | Adopt these corrections. Its review also did not inspect live state; production issuer support and OAuth interoperability still require end-to-end verification. |

`docs/staging_mcp/DEPLOYMENT.md` remains the detailed operational reference for the existing staging deployment; its examples and recorded hashes are not automatically suitable for the new host. `docs/PLAN.md` specifies legal review, independent security review, and disclosures before the invite-only pilot, while the deployment document describes an active pilot accepting residual risks. Confirm whether those gates were met or explicitly waived by an authorized owner. Do not infer approval from an already-running service or this plan.

## Preconditions and preparation

1. **Set scope and obtain approval.** Identify whether this is internal testing or real end-user access, the intended participants, maintenance window, owner, and decision-maker. Resolve the `docs/PLAN.md` gate discrepancy and any required legal, security, privacy, and operational reviews. Do not characterize the result as general availability unless its broader gates are met.
2. **Inventory actual live state, read-only.** Verify the running image ID and its relationship to the local tag, hostname support, Compose file and project directory, issuer, allowlist, network bindings, nginx effective configuration, DNS, firewall, TLS and renewal, and installed rollback scripts and hashes. Verify port 8001 and port 8765 are not externally reachable over IPv4 or IPv6. Record baseline health of unrelated services. Handle identities and settings securely; never dump tokens, secrets, or user content into logs.
3. **Prepare recovery before changing routing.** Preserve and independently verify the running image and prior Compose inputs, hostname, issuer, allowlist, nginx/TLS artifacts, and DNS state. Create two explicitly tested procedures: (a) emergency closure of **every** public route introduced by the change, and (b) restoration of the prior working endpoint. An existing rollback script that removes only the old public config cannot be assumed to close a separate new vhost. Preserve fail-closed listener behavior and unrelated sites. Coordinate the staging-operation lock and proxy-transition lock and any timer; avoid racing rollback or acquiring a non-reentrant lock twice.
4. **Prepare and rehearse the actual new-host artifacts.** Review HTTP-01 and TLS vhosts, certificate renewal hook, rate and connection limits, Host/SNI behavior, logging, and complete shared nginx configuration. Avoid duplicate rate-limit zone declarations and default-server conflicts. Adapt the isolated proxy rehearsal to exercise the actual proposed new-host configuration and both closure and restoration. The existing staging-host rehearsal alone does not validate these artifacts or live WorkOS, DNS, TLS renewal, or host routing.
5. **Select the smallest image change.** Reuse the running image if verified to support `STAGING_MCP_HOST` and otherwise meets the reviewed scope. If a build is needed, generate the isolated context from the reviewed checkout and build with the checkout's Compose file; the installed `/etc/di-staging/compose.yaml` resolves `.build-context` relative to its own location. Preserve the running image first and verify the replacement. Use the trusted installed Compose file for recreation with no build or pull, following the deployment guide. Hold `/run/lock/di-staging-allowlist.lock` for all staging image/tag and container mutations. Keep the reviewed Compose default and explicitly provide the new hostname, avoiding an unnecessary helper digest change.

## Pre-provision and cut over

6. **DNS and TLS.** Verify the intended host address rather than assuming the address in an old plan. Provision the new DNS record and verify IPv4/IPv6 behavior; do not publish AAAA for an IPv4-only service. Install the separately reviewed ACME-only route and obtain a matching certificate without allowing Certbot to rewrite unrelated nginx configuration. Verify issuance, renewal timer, lineage-scoped reload hook, and external behavior. Obtain the necessary DNS, host, firewall, and certificate approvals first.
7. **Identity and OAuth.** Register the exact resource `https://mcp.directedideation.com/mcp` in the selected WorkOS environment. Preserve the old resource and environment for rollback. For production, configure its issuer and required MCP/client registration and redirect settings, recreate approved identities, and build an allowlist of the actual production subject IDs. The `WORKOS_STAGING_ISSUER` name does not itself enforce a staging issuer, but verify the production issuer, JWKS, actual access-token claims and token semantics, and complete authorization flow before relying on it. Keep credentials out of shell history, process arguments, and logs.
8. **Schedule and execute.** Notify users that the old endpoint will be interrupted and clients must update the URL and reauthorize. Under the documented locks and reviewed procedure, recreate only the authenticated backend with the new hostname, selected issuer, and exact allowlist; activate the reviewed proxy routing to `127.0.0.1:8765`. The app accepts one hostname and audience at a time, so old-host requests and old-audience tokens fail after the switch. Do not promise a specific outage duration. Pushing `main` triggers a separate private-service workflow, not the authenticated pilot deployment.
9. **Verify externally before declaring success.** Check:
   - DNS A/AAAA behavior, certificate identity and renewal readiness, private backend isolation, and unrelated service health.
   - Protected-resource metadata, exact issuer and resource, and 401 for unauthenticated requests.
   - Rejection of wrong-issuer, old-audience, expired, and non-allowlisted tokens; verify actual access-token versus ID-token semantics.
   - Missing/unknown SNI and unexpected Host cannot reach either backend; verify all exposed address families.
   - A real authorized client discovers and reauthorizes, invokes `ping` and all four guidance tools, and receives correct stage-filtered guidance; invalid inputs are rejected without echoing sensitive content.
   - Refresh/expiry behavior, public rate limiting, and logging/redaction with synthetic inputs. Test the clients required for the approved scope; do not infer Claude or ChatGPT compatibility from Pi alone.

On failure, **close unsafe public access first** if necessary, or restore the known-good prior image, hostname, issuer, allowlist, proxy/TLS configuration, and routing using the prepared procedure. Keep the old resource available. Verify old-endpoint authorization and guidance end to end, and account for clients, DNS caches, existing connections, and token lifetimes. Retagging an image alone is not rollback.

## General production remains a separate gate

Moving the URL, or even switching to WorkOS production, does not establish broad launch readiness. Complete the applicable `docs/PLAN.md` legal, privacy/disclosure, independent security review, client interoperability, security and request-limit, monitoring, incident response, patching, and account-data operational requirements before expanding access. Billing and team-management features are not prerequisites for a hostname change unless required by the approved product scope.

## Evidence and limitations

This is a synthesis of all four `docs/PROD_DEPLOY_*.md` reviews and the repository's deployment instructions. The preceding Pi review ran `pytest -q`: **188 tests passed**. The WorkOS environment guidance linked above was checked while preparing this revision. Tests and documentation do not establish the actual running version, deployed configuration, external exposure, production OAuth interoperability, or security readiness. No live infrastructure was inspected or changed, and this document does not authorize deployment.
