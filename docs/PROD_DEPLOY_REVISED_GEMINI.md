# Revised Production Review and Cutover Plan: `mcp.directedideation.com`

Prepared 2026-11-04 by comparing all initial deployment reviews ([`PROD_DEPLOY_CLAUDE.md`](PROD_DEPLOY_CLAUDE.md), [`PROD_DEPLOY_CODEX.md`](PROD_DEPLOY_CODEX.md), [`PROD_DEPLOY_GEMINI.md`](PROD_DEPLOY_GEMINI.md), [`PROD_DEPLOY_PI.md`](PROD_DEPLOY_PI.md)) alongside the revised reviews ([`PROD_DEPLOY_REVISED_CLAUDE.md`](PROD_DEPLOY_REVISED_CLAUDE.md), [`PROD_DEPLOY_REVISED_CODEX.md`](PROD_DEPLOY_REVISED_CODEX.md), [`PROD_DEPLOY_REVISED_PI.md`](PROD_DEPLOY_REVISED_PI.md)) and verifying every claim against repository `HEAD` (`a35fc4b`).

Live infrastructure (the DigitalOcean droplet, DNS records, Let's Encrypt lineages, and WorkOS tenants) was **not** inspected or modified. All **188 pytest tests** and `uv run ty check` pass locally, providing offline regression coverage only.

---

## 1. Cross-Review Comparison & Self-Corrections

### Where All Four Reviews Agree
1. **Reuse the Authenticated Pilot Stack (`127.0.0.1:8765`), Never Port `8001`:**
   - The service in `staging_mcp/` already exposes all 4 canonical directed-ideation tools (`get_directed_ideation_method`, `get_interview_guidance`, `get_diagnostic_checks`, `get_alternative_techniques`) plus `ping` behind WorkOS RS256 JWT verification, subject allowlisting, 64 KiB body limits, non-echoing argument validation, and container hardening.
   - Port `8001` (`directed-ideation` private prototype) is unauthenticated and must remain strictly loopback-only.
   - `staging_mcp/server.py` already supports `STAGING_MCP_HOST=mcp.directedideation.com`; no application code changes are required.
2. **Single-Host / Single-Audience Flag-Day Cutover:**
   - Setting `STAGING_MCP_HOST=mcp.directedideation.com` atomically switches `TrustedHostMiddleware`, `/.well-known/oauth-protected-resource/mcp`, expected JWT `aud` (`https://mcp.directedideation.com/mcp`), and `healthcheck.py`.
   - Neither hostname nor audience is accepted simultaneously. Old tokens fail (`aud` mismatch), and clients must update their endpoint URL and reauthorize. Building dual-host support for a 2–5 user pilot is unnecessary complexity.
3. **Pre-Provisioning Before Cutover:**
   - DNS (`A` record only, **no `AAAA`** for the IPv4-only listener), ACME HTTP-01 TLS certificate issuance (`certbot certonly --webroot`), and WorkOS resource indicator registration (`https://mcp.directedideation.com/mcp`) should all be completed while `mcp-staging.directedideation.com` remains online.
4. **Full-State Rollback Required:**
   - Rollback is not just retagging a Docker image; it requires restoring the image, `STAGING_MCP_HOST` environment, issuer/allowlist, Nginx configuration, and routing, then verifying the restored endpoint end to end.

### Key Differences & Corrections to `PROD_DEPLOY_GEMINI.md`

| Topic | Initial Reviews | Verified Resolution & Self-Correction |
| :--- | :--- | :--- |
| **1. Build Command Path** | **Gemini** proposed running `docker compose -p di-staging -f /etc/di-staging/compose.yaml build`. **Codex** caught the path bug. | **Correction to Gemini:** `staging_mcp/compose.yaml` specifies `context: .build-context` relative to the Compose file. `scripts/prepare_staging_build_context.py` creates `staging_mcp/.build-context` in the repository checkout. Building with `-f /etc/di-staging/compose.yaml` resolves `/etc/di-staging/.build-context` and fails. **Rule:** Reuse the running image if it already includes `STAGING_MCP_HOST` support (`19c58cf`). If building is needed, build using the checkout's `-f staging_mcp/compose.yaml`, then recreate using the trusted `/etc/di-staging/compose.yaml` with `--no-build --pull never`. |
| **2. Nginx File & Emergency Closure (`di-shared-test-rollback`)** | **Gemini** suggested either adding a separate `/etc/nginx/conf.d/di-mcp-pilot.conf` or updating `di-shared-test` digests. **Codex** pointed out that adding a second file breaks emergency closure because `di-shared-test` only unlinks `di-staging-public-test.conf`. | **Correction to Gemini:** Never add a second unmanaged `.conf` file in `/etc/nginx/conf.d/`. Doing so leaves the new route publicly exposed even if `/usr/local/sbin/di-shared-test-rollback` exits 0, and risks duplicate `default_server` or `limit_req_zone` definitions. **Rule:** Replace the single `/etc/nginx/conf.d/di-staging-public-test.conf` atomically and update `/usr/local/libexec/di-shared-test` first so both **emergency public closure** and **prior-service restoration** are explicitly covered and hash-verified. |
| **3. WorkOS Staging vs. Production Environment** | **Claude, Gemini, Pi** kept the WorkOS *staging* issuer for the pilot rename. **Codex** noted WorkOS documentation states staging is for internal testing only and customer-facing URLs/users should use a WorkOS *production* environment. | **Adopted from Codex (and Revised Pi/Codex):** Decide the target WorkOS environment explicitly based on who uses `mcp.directedideation.com`:<br>• **Internal testing only:** WorkOS staging is acceptable.<br>• **External / real pilot participants:** Use a WorkOS Production environment, register `https://mcp.directedideation.com/mcp`, and populate `WORKOS_STAGING_ALLOWED_SUBJECTS` with production `user_...` IDs (since WorkOS user IDs do not carry over across environments). The env var name `WORKOS_STAGING_ISSUER` accepts any canonical HTTPS issuer origin without code changes. |
| **4. Governance & Pilot Gate Discrepancy** | **Pi** identified that `docs/PLAN.md` requires legal review, independent security review, and privacy disclosures *before* inviting pilot users, whereas `docs/staging_mcp/DEPLOYMENT.md` describes an active non-sensitive pilot operating under accepted residual risks. | **Adopted from Pi:** Moving the URL to `mcp.directedideation.com` does not satisfy `docs/PLAN.md` Phase 3/4 gates. Before cutover, the project owner must explicitly confirm and record whether `mcp.directedideation.com` is operating under an approved pilot risk waiver or whether legal, disclosure, and independent security reviews must complete first. |
| **5. Git Working Tree & Compose Defaults** | **Claude & Gemini** noted uncommitted work (captured while commit `19c58cf` was in flight). **Claude** initially suggested changing the default hostname in `compose.yaml`. | **Resolved:** Commit `19c58cf` ("Prepare hosted MCP pilot and hostname migration") and `a35fc4b` are committed on local `main` (5 commits ahead of `origin/main`). Do **not** edit `staging_mcp/compose.yaml` defaults—its SHA-256 (`8530bd8b...`) is pinned in `staging_mcp/add-allowed-user.sh`. Pass `STAGING_MCP_HOST=mcp.directedideation.com` via the environment. Also note that `git push origin main` triggers `.github/workflows/private-deploy.yml` (which deploys the private `8001` service, not `di-staging`). |
| **6. Isolated Proxy Rehearsal (`test_staging_proxy_isolated.py`)** | **Claude** recommended running `scripts/test_staging_proxy_isolated.py`. **Codex** noted it hardcodes `mcp-staging.directedideation.com`. | **Resolved:** Parameterize or adapt the rehearsal script so it tests the exact `mcp.directedideation.com` Nginx configuration, SNI/Host rejection, and rollback/closure scripts before touching the droplet. |

---

## 2. Preconditions & Explicit Decisions Before Cutover

Before executing any live infrastructure command, resolve and record these three gates:

1. **Gate 1 — Governance & Launch Scope (`docs/PLAN.md` vs. `docs/staging_mcp/DEPLOYMENT.md`):**
   - Confirm whether the `docs/PLAN.md` pre-pilot requirements (legal review, published plain-language privacy/security & subprocessor disclosures, US eligibility controls, and independent security review) have been completed or explicitly waived by the project owner for a narrow, non-sensitive 2–5 user pilot at `mcp.directedideation.com`.
   - General availability and commercial subscriptions remain **blocked**.
2. **Gate 2 — WorkOS Environment Selection:**
   - **Recommended for external pilot users:** Provision the WorkOS **Production** environment, configure MCP client registration settings, register `https://mcp.directedideation.com/mcp`, onboard the 2–5 approved users in production, and record their production `user_...` IDs for `WORKOS_STAGING_ALLOWED_SUBJECTS`. (This avoids making users reauthorize twice—once for the hostname change and again for the staging-to-production WorkOS switch.)
   - **Internal-only alternative:** Keep the existing WorkOS Staging environment and allowlist if use remains strictly internal testing.
3. **Gate 3 — Read-Only Live Droplet Inventory:**
   - Without modifying the droplet, inspect and record:
     - Running container `di-staging-staging-mcp-1` image ID, tag (`directed-ideation-staging-mcp:local`), and whether it already contains the `STAGING_MCP_HOST` code from commit `19c58cf`.
     - Whether `/etc/di-staging/compose.yaml` is installed, root-owned (`0644`), and matches SHA-256 `8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff`.
     - Complete `sudo nginx -T` output: all `:80` and `:443` listeners, `default_server` blocks, `/etc/nginx/conf.d/di-staging-public-test.conf` SHA-256, `/etc/nginx/conf.d/di-staging-loopback-check.conf.disabled`, and inherited logging/real-IP settings.
     - Installed `/usr/local/libexec/di-shared-test` and `/usr/local/sbin/di-shared-test-rollback` hashes and active systemd timers (`systemctl list-timers --all`).
     - External network verification that ports `8001` and `8765` are closed over IPv4 and IPv6, plus baseline health of any other sites hosted on the droplet.

---

## 3. Shortest Safe Cutover Plan

### Phase 1: Prepare & Rehearse the Cutover Package Offline

1. **Prepare the New Nginx TLS Configuration (`di-staging-public-test.conf` replacement):**
   - Keep the single public config file path (`/etc/nginx/conf.d/di-staging-public-test.conf`) so there is only one file to manage, one `default_server` block (`listen 0.0.0.0:443 ssl default_server; ssl_reject_handshake on; return 444;`), and one set of rate/connection zones (`staging_mcp_req` at `60r/m` burst `20`, `staging_mcp_conn` at `4`).
   - Set `server_name mcp.directedideation.com;` and point `ssl_certificate` / `ssl_certificate_key` to `/etc/letsencrypt/live/mcp.directedideation.com/{fullchain,privkey}.pem`, proxying to `http://127.0.0.1:8765`.
   - Compute and record the exact SHA-256 digest of this new configuration file.
2. **Prepare Dual Recovery Tooling (Emergency Closure vs. Service Restoration):**
   - **Emergency Closure (`di-shared-test-rollback`):** Update `staging_mcp/shared-nginx-test/di-shared-test` to accept the new config's SHA-256 digest in addition to `7f840890...` and `814b89c8...`, restoring `/etc/nginx/conf.d/di-staging-loopback-check.conf` (and verify that when the public config is unlinked, the `:443` listener still fails closed without exposing another site as an unintended implicit default).
   - **Service Restoration:** Prepare a scripted or step-by-step restoration procedure that atomically restores the prior `mcp-staging.directedideation.com` Nginx config, recreates `di-staging` with `STAGING_MCP_HOST=mcp-staging.directedideation.com`, the prior image, and the prior WorkOS issuer/allowlist, and reloads Nginx.
3. **Prepare ACME HTTP-01 & Renewal Artifacts:**
   - Adapt `staging_mcp/nginx-http01.conf.example` for `mcp.directedideation.com` (serving only `/.well-known/acme-challenge/` from `/var/lib/di-staging-acme` with an exact Host guard `^mcp\.directedideation\.com(?::80)?$` returning `444` otherwise, and `404` on all other paths).
   - Prepare the lineage-scoped deploy hook in `/etc/letsencrypt/renewal-hooks/deploy/` checking `[ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/mcp.directedideation.com ] || exit 0` before running `nginx -t && systemctl reload nginx`.
4. **Rehearse in the Isolated Podman Harness:**
   - Run an adapted `scripts/test_staging_proxy_isolated.py` against the new `mcp.directedideation.com` config and `STAGING_MCP_HOST=mcp.directedideation.com` to verify:
     - Valid token with `aud: https://mcp.directedideation.com/mcp` -> `200`
     - Token with old `aud: https://mcp-staging.directedideation.com/mcp` -> `401`
     - Unknown/missing SNI -> TLS handshake rejected
     - Wrong `Host` header -> connection dropped (`444`) or `400`
     - Burst traffic -> `429` rate limiting

### Phase 2: Pre-Provision DNS, TLS, and WorkOS (Zero Downtime on Current Pilot)

5. **Configure DNS:**
   - Add the `A` record for `mcp.directedideation.com` pointing to the verified droplet IPv4 address (`138.197.24.16`).
   - Ensure **no `AAAA` record** exists for `mcp.directedideation.com`.
   - Verify external resolution before proceeding.
6. **Provision the Let's Encrypt Certificate via Webroot:**
   - Install the reviewed HTTP-01 config for `mcp.directedideation.com`, validate with `sudo nginx -t`, and reload Nginx.
   - Verify externally that a test file under `/.well-known/acme-challenge/` is reachable, non-challenge paths return `404`, and wrong `Host` headers return `444`.
   - Issue the certificate without modifying Nginx configs:
     ```sh
     sudo certbot certonly --webroot -w /var/lib/di-staging-acme \
       -d mcp.directedideation.com --email YOUR-EMAIL --agree-tos
     ```
   - Confirm `/etc/letsencrypt/live/mcp.directedideation.com/fullchain.pem` and `privkey.pem` exist, install the lineage-scoped renewal deploy hook (`root:root 0755`), verify `certbot.timer` is enabled, and test `sudo certbot renew --dry-run --run-deploy-hooks`.
7. **Configure WorkOS:**
   - In the chosen WorkOS environment (per Gate 2), register `https://mcp.directedideation.com/mcp` as a resource indicator.
   - Keep `https://mcp-staging.directedideation.com/mcp` and the old WorkOS configuration intact for instant rollback.

### Phase 3: Stage Image & Perform Coordinated Cutover

8. **Ensure the Release Image and Trusted Compose Layout Are Ready:**
   - Lock staging operations exclusively:
     ```sh
     sudo flock -x /run/lock/di-staging-allowlist.lock /bin/bash
     ```
   - Tag the currently running image for rollback (`docker image tag directed-ideation-staging-mcp:local directed-ideation-staging-mcp:rollback`) and record its `sha256` image ID.
   - **If the running image already has `STAGING_MCP_HOST` support:** Do not rebuild.
   - **If a build is required:** From the reviewed repository checkout (not `/etc/di-staging`), run:
     ```sh
     python3 scripts/prepare_staging_build_context.py
     docker compose -p di-staging -f staging_mcp/compose.yaml build
     ```
   - Ensure `/etc/di-staging/compose.yaml` is installed (`root:root 0644`, no `.env` file, SHA-256 `8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff`).
9. **Execute the Scheduled Cutover:**
   - **Lock order:** Hold `/run/lock/di-staging-allowlist.lock` for the container update, then acquire `/var/lib/di-shared-test/lock` for the Nginx/rollback swap (never invoke `add-allowed-user.sh` or `di-shared-test-rollback` inside a shell that already holds their respective non-reentrant locks).
   - **Step 9a (Backend):** In a clean root environment with `STAGING_MCP_HOST=mcp.directedideation.com`, `WORKOS_STAGING_ISSUER=<target-issuer>`, and `WORKOS_STAGING_ALLOWED_SUBJECTS=<target-allowlist>`, recreate the container from the trusted Compose file without building or pulling:
     ```sh
     docker compose --project-name di-staging --project-directory /etc/di-staging \
       -f /etc/di-staging/compose.yaml up -d --no-build --pull never --force-recreate
     ```
   - Wait for `docker compose ... ps` to report `healthy` and verify on loopback (`127.0.0.1:8765`) that:
     - `Host: mcp.directedideation.com` on `/.well-known/oauth-protected-resource/mcp` returns `200` with `"resource": "https://mcp.directedideation.com/mcp"` and the exact configured issuer.
     - `Host: mcp-staging.directedideation.com` returns `400`.
   - **Step 9b (Nginx & Rollback Script):** Using the atomic staging pattern from `staging_mcp/shared-nginx-test/adjust-live-rate.sh` under `/var/lib/di-shared-test/lock`:
     - Verify no active rollback timer/service is running.
     - Back up the old `/etc/nginx/conf.d/di-staging-public-test.conf` and `/usr/local/libexec/di-shared-test` outside Nginx's include tree.
     - Atomically install the updated `/usr/local/libexec/di-shared-test` (which recognizes the new config digest) first (`0755`), verify its SHA-256, then atomically rename the staged `mcp.directedideation.com` config into `/etc/nginx/conf.d/di-staging-public-test.conf` (`0644`) and verify its SHA-256.
     - Run `sudo nginx -t && sudo systemctl reload nginx`.

### Phase 4: External Verification & Rollback Triggers

10. **Verify Externally Before Declaring Success:**
    - **DNS & TLS:** Confirm `mcp.directedideation.com` resolves only to the expected IPv4 address (`no AAAA`) and serves the valid Let's Encrypt certificate for `mcp.directedideation.com`.
    - **SNI & Host Guards:** Confirm connections with missing/unknown SNI fail TLS handshake (`TLSV1_UNRECOGNIZED_NAME`), and requests with `mcp.directedideation.com` SNI but a mismatched `Host` header fail closed without reaching port `8765` or `8001`.
    - **OAuth Metadata & Auth Boundary:**
      - `GET https://mcp.directedideation.com/.well-known/oauth-protected-resource/mcp` -> `200` with exact `resource` and `authorization_servers`.
      - Unauthenticated `POST https://mcp.directedideation.com/mcp` -> `401`.
      - Tokens with old `aud` (`mcp-staging`), wrong `iss`, expired `exp`, or unapproved `sub` -> `401`.
    - **End-to-End Client Flow:**
      - Point an approved client (e.g., Pi and any additional clients required by Gate 1) to `https://mcp.directedideation.com/mcp`, complete the OAuth flow, and verify `tools/list`, `ping`, `get_directed_ideation_method`, stage-filtered supplementary tools, and non-echoing rejection (`-32602 Invalid parameters`) on extra arguments.
    - **Isolation, Rate Limits & Logs:**
      - Confirm ports `8001` and `8765` are unreachable externally over IPv4 and IPv6.
      - Confirm unrelated hosted services remain healthy.
      - Confirm no bearer tokens, headers, or rejected payloads appear in Docker or Nginx logs.
11. **Immediate Recovery on Failure:**
    - **To close public access immediately on unsafe behavior:** Run `sudo /usr/local/sbin/di-shared-test-rollback` and externally verify port 443 refuses or rejects MCP traffic.
    - **To restore the prior working staging endpoint:** Under the locks, atomically restore the backed-up `mcp-staging` Nginx config, reload Nginx, restore `directed-ideation-staging-mcp:rollback` if the image was changed, recreate `di-staging` with `STAGING_MCP_HOST=mcp-staging.directedideation.com` and the prior issuer/allowlist, and verify `https://mcp-staging.directedideation.com/mcp` end to end.
12. **Post-Cutover Cleanup:**
    - Retain the old WorkOS resource registration, rollback image tag, and Nginx backups through an agreed observation window.
    - Once all pilot participants have migrated and stability is confirmed, retire the `mcp-staging.directedideation.com` DNS record, HTTP-01 vhost, and certificate lineage under a separate approved change.
