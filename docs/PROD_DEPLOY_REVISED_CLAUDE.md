# Revised plan: move the pilot to `mcp.directedideation.com`

Synthesis of `PROD_DEPLOY_CLAUDE.md`, `_CODEX.md`, `_GEMINI.md` and `_PI.md`,
checked against the repository on 2026-11-04 (HEAD `a35fc4b`, tree clean apart
from the new docs, `main` five commits ahead of `origin/main`). Live DNS, WorkOS,
the droplet and installed files were **not** inspected; nothing here authorizes a
live change.

## 1. Where the four plans agree

- The shortest safe move is a **pilot hostname migration**, not a general
  production launch. `STAGING_MCP_HOST=mcp.directedideation.com` already pins
  Host, protected-resource metadata, token audience and healthcheck; no new
  application feature is needed. 188 tests pass.
- Cutover is a **flag day**: one host and one audience at a time. Old tokens fail
  (`aud`), clients must switch URL and reauthorize. Accept a short scheduled
  outage; do not build dual-host support for 2-5 users.
- Pre-provision DNS (A record, **no AAAA**), certificate and the WorkOS resource
  indicator while the old host keeps running; keep the old resource registered.
- Nginx must keep proxying to `127.0.0.1:8765`, never `8001` (unauthenticated).
- Rollback must restore image, hostname env, proxy config and routing together,
  then be verified end to end. Retagging the image alone is not rollback.
- Broader production gates (security review, legal/privacy, client testing,
  token semantics, abuse limits) remain open.

## 2. Disagreements, and what I verified

| Question | Finding |
|---|---|
| Is the work uncommitted? (Claude, Gemini said yes) | **Stale.** Committed in `19c58cf`/`a35fc4b`. My review caught a dirty tree before that commit. Codex and Pi are right. |
| Edit `compose.yaml` default host? (Claude said yes) | **No.** `add-allowed-user.sh:35` pins the SHA-256 of `compose.yaml`. Editing it breaks the helper. Compose already takes `${STAGING_MCP_HOST:-...}`; pass the variable explicitly. My earlier advice was wrong. |
| Rehearse with `test_staging_proxy_isolated.py`? (Claude) | **Not as-is.** It hardcodes `mcp-staging` (lines 49, 130, 169, 173). It must be parameterized to exercise the new artifacts. Codex is right. |
| Build from `/etc/di-staging/compose.yaml`? (Gemini) | **Wrong.** `.build-context` resolves relative to the compose file, but `prepare_staging_build_context.py` writes `staging_mcp/.build-context` in the checkout. Build from the checkout's compose; recreate from the trusted `/etc` copy with `--no-build --pull never`. Better: do not rebuild at all if the running image already has `STAGING_MCP_HOST` support (step 1 checks this). |
| Separate new nginx file beside the old one? (Gemini) | **Unsafe.** The live file `di-staging-public-test.conf` holds the `default_server` block and the `staging_mcp_req/conn` zones. `di-shared-test` rollback only unlinks that one file, so a second file would stay public after "rollback" succeeded. A second file also duplicates zones and the default listener. Codex is right. |
| Edit the old file in place? | Changes its digest; `di-shared-test` then refuses with "unexpected public configuration". Needs a script update first (see 3). |
| Stay on WorkOS staging? (Claude, Gemini, Pi: yes; Codex: only for testing) | Both hold. Staging is acceptable **only** for the same explicitly approved, non-sensitive pilot allowlist. Anything customer-facing needs WorkOS production (new issuer, new user IDs, new allowlist). See gate G2. |
| Pilot approval discrepancy (Pi only) | **Valid and new.** `docs/PLAN.md` phase 3 requires legal review, independent security review and disclosures before inviting pilot users; `DEPLOYMENT.md` describes an active pilot under accepted risks. A rename does not resolve this. See gate G1. |
| Pushing `main`? (Pi, Codex) | `main` is 5 ahead of origin and a push triggers `private-deploy.yml`, which deploys the separate `8001` service, not this pilot. Push is not a deployment step here; do it deliberately. |

## 3. Recommended nginx approach (resolves the main operational trap)

Keep **one** public file and one closure path:

1. Build a new reviewed `di-staging-public-test.conf` containing **two server
   blocks** sharing the existing zones and the single `default_server`:
   - `mcp.directedideation.com` -> proxy to `127.0.0.1:8765` (new certificate).
   - `mcp-staging.directedideation.com` -> kept during the window, then changed to
     a fixed 404/444 (or removed) once clients have moved. Old and new hosts both
     use the same backend; the backend itself rejects the non-matching Host.
2. Record its SHA-256. Extend `di-shared-test` to accept **three** digests (new,
   current `7f840890…`, previous `814b89c8…`) using the same locked, atomic,
   install-script-first pattern as `adjust-live-rate.sh`. Closure then still
   removes the single file, and nothing remains public.
3. Because the new server block is live before the backend switch, it reaches the
   old-host backend and gets a Host rejection. Harmless, and it lets TLS/SNI
   behavior be tested externally before the cutover.

No duplicate zones, no second default, one digest to verify.

## 4. Gates to resolve before touching anything live

- **G1 (approval).** Confirm whether the original `docs/PLAN.md` pilot gates (legal
  review, independent security review, disclosures) were satisfied or explicitly
  waived for the existing pilot. The rename changes neither.
- **G2 (identity environment).** Decide: *same pilot, staging WorkOS* (rename
  only) or *customer-facing, WorkOS production*. Recommendation: rename on staging
  first if the users are the current approved set. Do production WorkOS as a
  separate, second reauthorization cycle, to avoid combining two risky changes.
  If real outside users are imminent, combine them and accept one larger window.
- **G3 (live state).** Read-only inventory (step 1) matches the repository
  assumptions.

## 5. Sequence

**Prepare (no live change)**
1. Resolve G1/G2. Read-only live inventory: running image identity and whether it
   supports `STAGING_MCP_HOST`; installed `/etc/di-staging/compose.yaml` digest;
   live nginx file digest (`nginx -T`); installed rollback script digest;
   certbot timer/hook; DNS and AAAA; firewall; WorkOS resource list; health of
   unrelated services; ports 8001/8765 not publicly reachable. Preserve and
   independently verify rollback artifacts.
2. Write the cutover package: two-block nginx file (section 3), updated
   `di-shared-test` with three digests, HTTP-01 vhost for the new name, certbot
   renewal deploy hook scoped to the new lineage, exact deploy command, and a
   written rollback and emergency-closure procedure.
3. Parameterize `scripts/test_staging_proxy_isolated.py` for the new host and
   rehearse the actual artifacts, including closure and restoration. This proves
   nginx behavior only, not DNS, certificate renewal or live WorkOS.

**Pre-provision (old host keeps serving)**
4. DNS A record for `mcp` -> verified droplet IPv4; no AAAA. Lower TTL first.
5. Separately approved ACME-only HTTP-01 route for the new name (check every port
   80 listener and default; unknown/missing Host must fail closed), then
   `certbot certonly --webroot` (never `--nginx`). Verify the renewal timer and
   hook, including the failed-validation path.
6. Register `https://mcp.directedideation.com/mcp` in WorkOS (environment per G2).
   Keep the old resource.
7. Install the new rollback script, then the two-block nginx config, atomically,
   under `/var/lib/di-shared-test/lock`; `nginx -t`, reload. Check TLS/SNI/Host
   and the 401/rejection behavior externally.

**Cutover (scheduled window; tell users)**
8. Under `flock -x /run/lock/di-staging-allowlist.lock`: preserve the running image
   (`:rollback` tag, verify it matches the running container); recreate `di-staging`
   from `/etc/di-staging/compose.yaml` with `--no-build --pull never`,
   `STAGING_MCP_HOST=mcp.directedideation.com`, same issuer and allowlist (or the
   G2-production values). Build first only if the image lacks hostname support,
   from the checkout's generated context. Wait for healthy; inspect effective
   config.
9. Users update the client URL and reauthorize. Do not paste tokens into logs.

**Verify externally**
10. DNS and certificate identity (IPv4/IPv6); protected-resource metadata and exact
    issuer/resource; anonymous 401; wrong-issuer, old-audience, expired and
    non-allowlisted tokens rejected; unknown/missing SNI and wrong Host rejected;
    real client discovers and calls `ping`, all four guidance tools and stage
    filters; invalid inputs rejected without echo; refresh/expiry; public rate
    limiting (429) and client tolerance of bare 429; logging with synthetic
    credentials; 8001/8765 not externally reachable; unrelated services healthy.

**Roll back on any failure**
11. Restore the old image tag, old hostname env, old nginx file and routing; old
    resource is still registered. Verify the old endpoint end to end. For unsafe
    behavior use `di-shared-test-rollback` and independently confirm closure.

**Afterwards**
12. After users have moved, turn the old-host block into 404/444 and retire the old
    certificate and DNS under separate approval.

## 6. Evidence and remaining limits

188 passing tests cover offline host/audience/metadata behavior only. They do not
show live routing, production WorkOS interoperability, public abuse protection,
client coverage beyond Pi (Claude chat, ChatGPT untested), token-type semantics
beyond one sampled ID token, or completed independent security review. This is a
limited pilot on a cleaner URL; general production (section 4 of the original plan
and `docs/PLAN.md` phase 4) stays blocked.

**Next action:** resolve G1 and G2, then do the read-only live inventory. Live
changes need separate authorization.
