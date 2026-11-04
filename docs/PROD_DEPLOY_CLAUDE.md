# Plan: move the pilot to `mcp.directedideation.com`

Reviewed 2026-11-04 from the repository only (PLAN.md, HANDOFF.md, staging_mcp/*,
tests). Nothing was checked on the droplet, DNS or WorkOS. The test suite passed
(188 tests) at review time.

## Two different moves

**A. Pilot rename** to `mcp.directedideation.com`:
- Same WorkOS *staging* issuer, same subject allowlist, same 2-5 users.
- Already scoped this way in `staging_mcp/DEPLOYMENT.md` ("Planned pilot hostname
  migration"). `server.py` supports it through `STAGING_MCP_HOST`.
- Small, tested, the shortest safe path.

**B. Real production:**
- Blocked by the project's own gates: independent security review, legal review,
  broader client testing, token-semantics verification.
- WorkOS says staging environments are for testing only. A production WorkOS
  environment has a different issuer and different user IDs, so the allowlist must
  be rebuilt and users must sign up again.

Do A now and call it what it is (a pilot on a cleaner URL). Treat B as a separate
project.

## What is ready
- `server.py` pins both the Host check and the token audience to the chosen host
  and fails closed. A test covers the new host.
- Hardened container: digest-pinned base image, read-only root, dropped
  capabilities, loopback-only port.
- Test suite passes.

## Gaps that block A
1. **Work is uncommitted.** The hardened server, tests, `add-allowed-user.sh` and
   rollback tooling are not in git. Commit before deploying.
2. **No nginx config for the new host.**
   - `nginx.conf.example` and `nginx-http01.conf.example` hardcode `mcp-staging`
     (cert paths, Host regex). `healthcheck.py` and `compose.yaml` default to it.
   - The installed rollback script `di-shared-test` pins SHA-256 digests of exact
     config files. A new-host config needs its own reviewed digest and an updated
     script, or rollback will refuse it.
3. **Cutover is a flag day.** The server accepts exactly one host and one
   audience. Recreating with the new host kills the old URL and invalidates all
   existing tokens. Acceptable for 2-5 users; schedule it and tell them.
4. **Thin public-readiness evidence** (accepted pilot risks):
   - Only Pi tested end to end. Claude Desktop Code showed ping only; regular
     Claude chat and ChatGPT untested.
   - 429 rate limiting seen on loopback only.
   - ID-token rejection checked on one sampled token.

## Sequence

1. Commit the tree; re-run tests.
2. Write new-host variants: TLS vhost, HTTP-01 vhost, certbot deploy hook scoped
   to the new lineage, updated `STAGING_MCP_HOST` default, rollback script
   accepting the new config digest. Rehearse with
   `scripts/test_staging_proxy_isolated.py`.
3. Add A record `mcp` -> 138.197.24.16, **no AAAA** (the droplet has IPv6; the
   example listens on IPv4 only). Lower TTL beforehand.
4. Install the ACME-only vhost for the new name; run
   `certbot certonly --webroot`. Verify unknown/missing Host fails closed.
   (DNS-01 avoids opening port 80 but needs more setup.)
5. Back up the old config and image, then install the new TLS vhost alongside the
   old one.
6. Register `https://mcp.directedideation.com/mcp` as a resource indicator in the
   **staging** WorkOS environment. Keep the old resource registered.
7. Under `flock -x /run/lock/di-staging-allowlist.lock`, recreate `di-staging`
   with `STAGING_MCP_HOST=mcp.directedideation.com`.
8. Verify from outside:
   - unauthenticated request -> 401
   - old-audience, wrong-issuer and non-allowlisted tokens rejected
   - protected-resource metadata correct
   - Pi reauthorizes; `ping` and guidance tools work
   - no AAAA exposure
   - missing/unknown SNI and Host rejected
9. Roll back immediately on any failure: restore image tag, old nginx config, old
   resource; verify the old endpoint.
10. Retire the old hostname once users have moved (or leave its vhost returning 404).

Optional zero-downtime variant: accept both hosts, each paired with its own
audience, for a transition window. Costs a code change and weakens the
"exactly one audience" property; not worth it for 2-5 users.

## Before B (real production)
- Create the WorkOS production environment; rebuild the allowlist.
- Independent security review and legal review.
- Test with Claude chat and ChatGPT.
- Verify token semantics across token types.
- Load-test the direct backend and nginx limits.
- Publish the privacy/security page and incident contact.
