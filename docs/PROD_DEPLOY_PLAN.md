# Consolidated plan: pilot at `mcp.directedideation.com` on WorkOS production

Consolidates `PROD_DEPLOY_{CLAUDE,CODEX,GEMINI,PI}.md` and their `_REVISED_`
versions, checked against repository HEAD `a35fc4b`. Live DNS, WorkOS, the
droplet and installed files have **not** been inspected. This document does not
authorize any live change; each live step needs its own go-ahead.

## 1. Decisions and process approval

G1 and G2 are approved by the owner. The preparation, controlled identity/OAuth
verification, rollback, pre-provisioning, cutover and verification processes below
are approved as the approach; this is not authorization for individual live changes.
Each live step still requires its own go-ahead. Approval does not establish that a
particular identity-bootstrap flow is supported or that any verification has passed.

| Gate | Decision | Consequence |
|---|---|---|
| **G1: pilot approval** | The pilot runs under **accepted risk**, with **trusted users only**, added by explicit allowlist. | The `PLAN.md` phase 3 items (legal review, independent security review, privacy/subprocessor disclosures, US eligibility controls, broad client validation) are **deferred for the pilot, not waived**. They are **mandatory before any commercial release or any user outside the trusted set.** Record this in `PLAN.md` and `staging_mcp/DEPLOYMENT.md` so the two documents agree. |
| **G2: identity environment** | **WorkOS production**, directly. No intermediate staging rename. | One reauthorization for users (new host and new issuer together). New issuer, new `user_...` IDs, new allowlist. Staging stays registered for rollback only. |

Scope: about 2-5 trusted users. General availability, billing and a second auth
stack are out of scope. No application code change is needed: `STAGING_MCP_HOST`
already pins Host, protected-resource metadata, token audience and the
healthcheck (188 tests pass offline).

## 2. Design rules (from the cross-review)

- **Backend:** the authenticated service on `127.0.0.1:8765` only. Port `8001` is
  the unauthenticated private prototype and must never be proxied or exposed.
- **Flag day:** one host and one audience at a time. Old tokens fail on `aud`.
  Users change the URL and reauthorize. No dual-host support, no redirects.
- **Compose:** do not edit `staging_mcp/compose.yaml`. `add-allowed-user.sh`
  pins its SHA-256. Pass `STAGING_MCP_HOST` explicitly.
- **Build:** reuse the running image if it already supports `STAGING_MCP_HOST`
  (commit `19c58cf`). Otherwise build from the **checkout's** compose file after
  `scripts/prepare_staging_build_context.py`, not from `/etc/di-staging`. Deploy
  from the trusted `/etc/di-staging/compose.yaml` with `--no-build --pull never`.
- **Nginx:** replace the **single** public file `di-staging-public-test.conf`.
  Keep the one `default_server` (fail closed), define each rate/conn zone once,
  proxy only to 8765, and use the new certificate lineage. No second public
  file: `di-shared-test` rollback only unlinks the old one, so a second file
  would stay public after "rollback" succeeds.
- **Recovery has two distinct outcomes**, each prepared and tested:
  - *Emergency closure:* no public MCP routing, listener still fails closed.
  - *Service restoration:* old image, host, issuer, allowlist, nginx and
    routing restored together and verified end to end.
  Retagging the image alone is not rollback. A script exiting 0 is not proof of
  closure; verify externally.
- **Locks:** `/run/lock/di-staging-allowlist.lock` (container/image/allowlist)
  and `/var/lib/di-shared-test/lock` (nginx/rollback). Both are non-reentrant;
  document acquisition order and never call a lock-taking helper while holding
  its lock.
- **Pushing `main`** triggers `private-deploy.yml` (the 8001 service), not this
  pilot. It is not a deployment step here.
- Never put tokens, secrets or session content in logs, shell history or
  process arguments.

## 3. Sequence

### A. Prepare (local work and read-only inventory; artifact preservation requires live approval)

1. **Record G1/G2** in `PLAN.md` and `staging_mcp/DEPLOYMENT.md` (complete).
2. **Read-only live inventory:**
   - running image ID and tag, and whether it supports `STAGING_MCP_HOST`
   - installed `/etc/di-staging/compose.yaml` digest, owner, mode, and whether it
     is the project directory in use
   - effective nginx (`nginx -T`): all :80/:443 listeners, defaults, inherited
     logging/real-IP, and the digest of the live public file
   - installed `di-shared-test` and `di-shared-test-rollback` digests; timers
   - certbot timer/hooks; DNS A/AAAA for both names; the actual droplet IPv4
     (do not copy the historical one from the reviews); firewall
   - current WorkOS staging issuer, allowlist and resource list
   - 8001/8765 unreachable externally over IPv4 and IPv6; baseline health of
     unrelated sites and the private service
3. **Preserve rollback artifacts (live change; separate go-ahead):** image (`:rollback` tag, verified equal to the
   running container), current nginx file, rollback scripts, certificate
   lineage, issuer and allowlist. Store hashes as evidence.
4. **Write the cutover package:**
   - new-host `di-staging-public-test.conf` (section 2 rules) with its SHA-256
   - updated `di-shared-test` accepting the new, current (`7f840890...`) and
     previous (`814b89c8...`) digests, installed script-first using the atomic
     pattern in `adjust-live-rate.sh`; confirm the closed state still fails
     closed and does not make another site the implicit default
   - ACME-only HTTP-01 vhost for the new name (adapt `nginx-http01.conf.example`;
     exact Host guard, 404 elsewhere, 444 for wrong Host)
   - renewal deploy hook scoped to the new lineage
   - exact deploy commands and the written closure and restoration runbooks
5. **Rehearse:** parameterize `scripts/test_staging_proxy_isolated.py` (it
   hardcodes `mcp-staging`) and exercise the real artifacts: valid-token 200,
   old-audience 401, unknown/missing SNI rejected, wrong Host rejected, burst
   429, failed validation, emergency closure, restoration. This proves nginx
   behavior only, not DNS, renewal or live WorkOS.

### B. Pre-provision (old host keeps serving)

6. **WorkOS production:** enable the production environment (it needs billing
   information; confirm current requirements and pricing). Configure MCP/client
   registration and redirect settings, register
   `https://mcp.directedideation.com/mcp`, and check email verification,
   recovery and signup restrictions. Keep the staging environment and resource.
7. **Production identities:** have each trusted user sign in once through a
   supported controlled flow, then securely collect their exact production `user_...`
   IDs. The approach is approved, but this step is not complete until the chosen
   supported flow, prerequisites, evidence of successful identity collection and
   secure handling are documented in the cutover evidence/runbook. Do not expose the
   MCP service or weaken its allowlist to bootstrap users.
8. **Verify production OAuth in a controlled setup** with a secure client:
   discovery, JWKS, access-token `aud`/`sub`/`exp`, ID-token separation, refresh
   and revocation. Acceptance of a configurable issuer in the app is not proof
   production OAuth works.
9. **DNS:** A record `mcp` to the verified droplet IPv4. **No AAAA.** If an
   existing record must change, lower its TTL in advance and allow the previous TTL
   to expire; if no record exists, set an appropriate initial TTL. Inventory and
   separately approve any required AAAA removal; account for cached records.
10. **Certificate:** install the ACME-only vhost, check challenge reachability and
    non-challenge denial, then `certbot certonly --webroot` (never `--nginx`).
    Install the hook, check `certbot.timer`, and run
    `certbot renew --dry-run --run-deploy-hooks`.

### C. Cutover (scheduled window; notify users first)

11. **Backend**, under `flock -x /run/lock/di-staging-allowlist.lock`: confirm no
    drift from the recorded state, then recreate only `di-staging` from the
    trusted compose file with `--no-build --pull never`, with:

    | Variable | Value |
    |---|---|
    | `STAGING_MCP_HOST` | `mcp.directedideation.com` |
    | `WORKOS_STAGING_ISSUER` | exact production Connect issuer origin |
    | `WORKOS_STAGING_ALLOWED_SUBJECTS` | production `user_...` IDs |

    Wait for healthy. On loopback, confirm metadata returns the new resource and
    issuer for the new Host, and that the old Host returns 400. Make sure
    later `add-allowed-user.sh` runs keep these values.
12. **Nginx**, under `/var/lib/di-shared-test/lock`: no rollback timer or service
    running; back up the old files outside the include tree; atomically install
    the updated `di-shared-test` first and verify its digest; then atomically
    install the new nginx file and verify its digest; `nginx -t`; reload only on
    success.
13. **Users** update the client URL and reauthorize.

### D. Verify externally (before declaring success)

14. Check each of these:
    - DNS (A only) and certificate identity; renewal readiness
    - protected-resource metadata shows the exact resource and production issuer;
      anonymous request returns 401
    - wrong-issuer, old-audience, expired and non-allowlisted tokens are rejected
    - missing or unknown SNI and a wrong Host cannot reach 8765 or 8001
    - a real client reauthorizes, discovers, calls `ping` and all four guidance
      tools, and gets correct stage-filtered output
    - invalid inputs are rejected without echoing content; logs contain no
      tokens or content (synthetic test)
    - refresh and expiry work; removing an allowlisted subject works
    - public rate limiting returns 429 and the client tolerates a bare 429
    - 8001/8765 stay unreachable; unrelated sites and the private service keep
      baseline health

    Healthcheck 401 alone is not sufficient. Set a verification deadline during
    rehearsal; do not promise a fixed outage duration.

### E. Failure and afterwards

15. **On any failure or unsafe behavior:** close first if needed
    (`di-shared-test-rollback`, then confirm closure externally). Restoring the
    old service means the old image, host, issuer, allowlist, nginx and routing
    together, then verifying the old endpoint end to end. Do not send ordinary
    traffic back to WorkOS staging beyond the trusted set. If restoration is
    unsuitable, stay closed and recover offline.
16. **Observation period** (set the length in advance): watch availability, auth
    failures, resource use, certificate expiry and abuse signals.
17. **Retire the old host** only after that period and under separate approval:
    old DNS record, HTTP-01 vhost, certificate lineage, WorkOS staging resource
    and rollback artifacts. No redirect.

## 4. Before any commercial release or non-trusted user

Mandatory, and not covered by this pilot:

- legal review; privacy and security disclosures, including subprocessors
  (WorkOS holds identity data)
- independent security review
- US eligibility and processing controls
- client interoperability beyond Pi (Claude chat and ChatGPT are untested)
- token-semantics review beyond the one sampled ID token
- abuse and request-limit review, monitoring, incident response, patching
- team/account features, if the product scope requires them (record the scope
  decision against `PLAN.md` rather than redefining its requirements)
- billing

## 5. Evidence limits

The 188 passing tests cover offline host, audience and metadata behavior only.
They do not show live routing, production WorkOS interoperability, public abuse
protection, or an independent security review.

**Next action:** step 2 (read-only inventory), then prepare the cutover package.
Live changes, including creating the rollback image tag, need separate authorization.
