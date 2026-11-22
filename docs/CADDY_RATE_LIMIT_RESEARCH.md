# Per-client IP rate limiting for the staging MCP endpoint (Caddy research note)

Status: research only. Nothing here is deployed, and no configuration outside this file was
changed. Every Caddy or nginx behaviour marked **tested** was reproduced on a developer
workstation on **2026-11-03 (UTC)** with a locally built binary; behaviours marked **documented**
come only from primary sources (project docs/source/release notes) and were not reproduced here.
Facts about the target droplet, real DNS, ACME, WorkOS tokens, Docker and nginx are **not**
verified in this note.

Scope: the single-droplet, single-node staging endpoint described in
`docs/staging_mcp/DEPLOYMENT.md` and `staging_mcp/Caddyfile.example` — one Caddy TLS terminator in
front of `127.0.0.1:8765`, 2–5 allow-listed WorkOS users, no WAF, no load balancer, no CDN.

---

## 0. Bottom line

1. **Caddy has no built-in rate limiting.** Per-IP request limiting is a third-party module
   (`http.handlers.rate_limit`). Stock Caddy v2.11.7 exposes **zero** modules matching
   `rate_limit` (`caddy list-modules`); the Caddy project's own docs say non-standard modules "are
   not officially endorsed or maintained by the Caddy project".
2. **The credible module is `github.com/mholt/caddy-ratelimit`** — by Caddy's original author, but
   explicitly *not* an official Caddy repository, with **no tagged releases**, Apache-2.0, active in
   2026 (last commit 2026-06-12), unit tests and CI. Using it means **shipping a custom Caddy
   binary** and owning rebuilds for every Caddy security release.
3. **Per-IP limiting is safe on the droplet only while Caddy is the outermost peer.** With the
   default `trusted_proxies` (none) `{client_ip}` is the TCP peer and `X-Forwarded-For` is ignored —
   I confirmed spoofed XFF cannot buy a fresh bucket. The moment *any* proxy is placed in front,
   the key becomes attacker-controlled unless `trusted_proxies` is narrowed correctly.
4. **Two behaviours must be planned for, not discovered later:** the module logs one INFO line per
   rejected request **containing the client IP** (no `log` directive needed), and `request_body
   max_size` is not a bandwidth cap — it aborts the read *after* the limit and can surface as a 413
   or as a truncated upstream request depending on the backend.
5. **nginx is the lower-supply-chain-risk option**: `limit_req`/`limit_conn` are in the base distro,
   no custom build, but they are per-zone memory-bounded leaky buckets that answer `503` by default
   with no `Retry-After`, and TLS becomes the operator's problem (certbot/acme.sh).
6. Neither option closes the existing activation gate in `docs/staging_mcp/DEPLOYMENT.md`. Proxying
   limits are coarse abuse control, not authentication, and not per-user fairness.

---

## 1. What Caddy does and does not ship (verified)

| Claim | Evidence |
| --- | --- |
| `rate_limit` is not a standard Caddyfile directive | `https://caddyserver.com/docs/caddyfile/directives/rate_limit` returns **HTTP 404**; the "Quick access to all standard Caddyfile directives" list on `/docs/caddyfile/directives` contains `request_body`, `reverse_proxy`, … but no `rate_limit`. |
| The module is third-party and not endorsed | Module page `/docs/modules/http.handlers.rate_limit`: "This module does not come with Caddy… **Non-standard modules may be developed by the community and are not officially endorsed or maintained by the Caddy project.** The documentation is shown here only as a courtesy." The same page warns "There is more than one module named …", i.e. the module ID `http.handlers.rate_limit` is not unique across repositories. |
| Stock builds contain no rate limiter | **Tested.** `xcaddy build v2.11.7` → `caddy list-modules \| grep -c rate_limit` = **0**; same build with `--with github.com/mholt/caddy-ratelimit` = **1**. |
| Registered plugins offering `http.handlers.rate_limit` | Caddy package registry `https://caddyserver.com/api/packages` (333 packages) lists `github.com/mholt/caddy-ratelimit` (33,399 registry downloads, published 2021-05-26) and `github.com/RussellLuo/caddy-ext/ratelimit` (5,998 downloads, registry entry last updated 2021-01-29 → stale). Both register the same module ID, so only one can be compiled into a binary. |
| What Caddy *does* give you for free | `request_body { max_size }` (long predates v2.10 — the module exists at least as far back as `v2.4.6`; only its `set` subdirective is badged `v2.10.0+`/experimental), server `timeouts` (`read_body`, `read_header`, `idle`, …) under global `servers`, `max_header_size`, `client_ip` matcher, `trusted_proxies`, `{client_ip}` placeholder, automatic HTTPS. Directed source: `/docs/caddyfile/directives/request_body`, `/docs/caddyfile/options`. |

Consequence: choosing Caddy + per-IP limiting is a **build decision**, not a config decision.

---

## 2. `mholt/caddy-ratelimit` — provenance and maintenance

| Attribute | Value (captured 2026-11-03 UTC) | Source |
| --- | --- | --- |
| Repository | `github.com/mholt/caddy-ratelimit` | GitHub API |
| Official status | README: "This is **not** an official repository of the Caddy Web Server organization." | repo README |
| Owner | Matthew Holt, Caddy's original author. Note the project has since moved away from single-maintainer releases: the v2.11.0-beta.1 notes describe the first release produced by the maintainer team "without intervention from @mholt". | repo + release notes |
| Licence | Apache-2.0 | GitHub API |
| Stars / forks / open issues | 508 / 37 / 13 | GitHub API |
| Last commit | 2026-06-12 — `fix(metrics): re-register collectors on each config reload (#102)` | GitHub API |
| Recent feature history | metrics (2026-05-14, #85), `ipv4_prefix`/`ipv6_prefix` (2026-05-21, #97), metrics reload fix (2026-06-12) | GitHub API |
| Tagged releases | **none** (releases API empty) → consume by commit SHA / pseudo-version | GitHub API |
| Tests / CI | `handler_test.go`, `ringbuffer_test.go`, `caddyfile_test.go`, `distributed_test.go`, `metrics_test.go`; `.github/workflows/go.yml` runs `go test ./...` on push/PR (matrix macOS/Windows/Ubuntu, Go 1.22 pinned, `check-latest: true`) | repo |
| Module requirement | `go.mod`: `go 1.24`, `toolchain go1.24.3`, requires `caddyserver/caddy/v2 v2.10.0` | repo `go.mod` |
| Resolved pin used in my test build | `github.com/mholt/caddy-ratelimit v0.1.1-0.20260612195517-5625512f24f6 h1:XLJEIxNlf80gg+nc7Oea070+veJffHYKiX6UaYVY+tM=` | `caddy build-info` |

Documented feature set (README): sliding-window per-key zones, ring-buffer state with
**O(K·n)** memory (K = events per window, n = distinct keys), expired buckets swept every `sweep_interval`
(default 1m), automatic `Retry-After`, optional jitter, `ipv4_prefix`/`ipv6_prefix` subnet masking,
`log_key`, `disable_metrics`, optional distributed state via a shared `certmagic` storage backend.
State survives config reloads via a Caddy usage pool (`handler.go`), **not** process restarts —
"RL state persisted in storage for resuming after restarts" is still listed as PLANNED.

Open, relevant gaps (GitHub issues): no concurrency limiter (open feature request #69 and PR #98,
both unmerged), no temporary time-based ban (#92), per-zone event filtering beyond matchers (#64),
"Too Much Logging" (#103, open — the log-flood below), distributed-sync reports (#96, #61).

---

## 3. Client IP correctness — the part that decides whether this is real protection

Documented behaviour (`/docs/caddyfile/options`, `trusted_proxies`):

- "By default, **no proxies are trusted**." With no trusted proxy the client IP "is set to the
  remote IP address of the direct incoming connection".
- Only when a trusted proxy is in play is the client IP parsed from headers (default
  `X-Forwarded-For`, configurable with `client_ip_headers`), exposed as the `{client_ip}`
  placeholder and to the `client_ip` matcher.
- "By default, the IPs in headers are parsed **left-to-right**. The first untrusted IP address found
  becomes the real client address." `trusted_proxies_strict` (v2.8+) switches to right-to-left
  parsing and "is recommended" for HAProxy/Cloudflare/ALB/CloudFront because "the left-most IP
  address may be spoofed by the client".
- `{client_ip}` is a Caddyfile *shorthand* for `{http.vars.client_ip}`
  (`caddyconfig/httpcaddyfile/shorthands.go:89`, v2.11.7) — i.e. it is exactly the trusted-proxy-aware
  value, whereas `{remote_host}`/`{http.request.remote.host}` is always the immediate peer.

**Tested (loopback, plugin build):**

| Scenario | Result |
| --- | --- |
| `key {client_ip}`, no `trusted_proxies`; 3 events/10s | 3×200 then `429` + `Retry-After: 10` |
| Same exhausted bucket, request carries `X-Forwarded-For: 203.0.113.9` and `X-Real-IP: 203.0.113.9` | still `429` (+`Retry-After: 5`) — **no bypass** |
| `trusted_proxies static private_ranges` + `trusted_proxies_strict`, key `{client_ip}` | rotating `X-Forwarded-For` values each got a **fresh** bucket (4×200); repeating one value tripped at the 3rd request — **the key is attacker-controlled as soon as the peer is "trusted"** |
| `ipv6_prefix 64` with `log_key` | rejected request logged `"remote_ip":"::1","key":"::/64"`; IPv4 loopback was a separate bucket |
| `{client_ip}` in the Caddyfile | adapts to `"key":"{http.vars.client_ip}"` — confirmed in `caddy adapt` JSON |

Operational rule that follows: **do not add `trusted_proxies` for a single-droplet layout.** It is
only correct when a specific proxy you control is in front, and then only with
`trusted_proxies_strict` (or a private-range `static` source that cannot be reached directly from
the Internet).

IPv6 caveat: a residential client normally controls a whole `/64`, so un-masked per-IPv6-address
buckets are trivially defeated. `ipv6_prefix 64` (a May-2026 addition) is required for meaningful
IPv6 limiting; it also means one abusive household throttles its own `/64`, which is the intended
trade-off.

---

## 4. What was actually tested here vs. what was not

**Tested** (macOS workstation, `go1.27.3`, no Docker, no droplet, loopback only):

1. `xcaddy build v2.11.7 --with github.com/mholt/caddy-ratelimit@5625512f24` → build succeeded.
2. `caddy list-modules` stock vs. plugin build → 0 vs. 1 `http.handlers.rate_limit`.
3. `caddy adapt` of a merged staging snippet → handler order `request_body` → `rate_limit` →
   `reverse_proxy` (limiting happens *before* the proxy and before any body read).
4. `caddy validate` of the recommended site (real hostname, automatic HTTPS enabled) →
   `Valid configuration`, with **no** network/ACME activity and no listeners started.
5. Per-IP 200→429 transition, `Retry-After` presence, XFF spoof resistance, `trusted_proxies`
   bypass, `ipv6_prefix` masking, custom 429 body via `handle_errors` (header preserved, generic
   body, no token/IP echoed), rejection logging.
6. `request_body { max_size 64KB }` with an 80,000-byte POST: client got `413`; the upstream echo
   server received exactly **64,000** bytes then EOF. With a backend that replies *without*
   reading the body, the client saw `200` with an empty body instead of `413`.

**Not tested** — do not claim otherwise in any handoff:

- The staging droplet, real DNS/ACME issuance, real WorkOS tokens/JWKS, real MCP clients.
- Docker: this machine has no Docker, so the `caddy:<ver>-builder` image pattern, digest pinning,
  and any custom image build are **unverified here**.
- nginx: not installed, no configuration was run; all nginx statements below are documentation-only.
- Public IPv6 clients, CGNAT/behind-NAT clients, high request rates, memory behaviour under a
  many-distinct-IP flood, config-reload state persistence, distributed mode.
- Whether the MCP clients used by the pilot (Pi/ChatGPT/Claude) handle `429` + `Retry-After`
  gracefully; and whether FastMCP's JWKS caching amplifies a pre-auth flood.

---

## 5. Behaviour that changes the deployment plan

### 5.1 `request_body` is not a bandwidth cap (tested)

`request_body` wraps the body in `http.MaxBytesReader`; the 413 is produced only when a later
handler *reads* past `max_size`, and the upstream may still receive up to the limit. It does bound
what the Python app can be made to read, which is the intent in `docs/staging_mcp/DEPLOYMENT.md`, but it
does not stop a client from uploading 64 KB per request, and the observed status can be 200-with-
empty-body rather than 413 when the backend answers early. Treat it as a backend-exposure limit,
not a DoS defence.

Side finding that corrects the repository: `docs/staging_mcp/DEPLOYMENT.md` asks the operator to
"Confirm Caddy supports `request_body` (Caddy 2.10+)". The directive is far older — the
`request_body` module is present in Caddy tags `v2.4.6` through `v2.10.0` — so the version gate is
unnecessary (only the experimental `set` subdirective is v2.10.0+). The behaviour caveat above is
the part that actually needs operator attention.

### 5.2 Rejection logging records the client IP (tested + source)

Every rejected request emits one INFO line from `http.handlers.rate_limit` —
`{"msg":"rate limit exceeded","zone":…,"wait":…,"remote_ip":"<client ip>"}` — with `log_key`
additionally logging the rate-limit key. This happens **without any `log` directive and without
access logging** (`handler.go`, `rateLimitExceeded`; also open issue #103). For a service whose
stated posture is "no access logs, no claim-bearing logs", this is a real, if narrow, disclosure:
client IPs of blocked requests land in the Caddy journal, and rate-limit floods both disclose IPs
and can flood logs/disk. Mitigations are global (raise Caddy's log level, which affects other
sites) or log-side (journald filtering/rate limiting); the module offers no per-zone silence.

### 5.3 Metrics carry the rate-limit key as a label

When Caddy global metrics are enabled, the module publishes counters/histograms labelled
`{"zone", "key"}` per request (`metrics.go`), including the per-key series — i.e. client IPs become
Prometheus label values with unbounded cardinality. Metrics are off unless the global `metrics`
option is enabled; if metrics are ever enabled for the staging host, set `disable_metrics` in the
`rate_limit` block.

### 5.4 Memory and state

Memory is O(K·n): per distinct key, a ring of `max_events` timestamps. With a 1-minute window and
`events 30`, each key costs ~30 timestamps; a distributed flood of N distinct IPs costs O(N·30)
until the 1-minute sweep reaps expired buckets (`ratelimit.go` `sweep`). This is self-bounding in
time but **not** capped in memory the way nginx's fixed-size zone is — a single-droplet staging box
should be assumed to lose memory under a large-enough IP spray. Rate-limit state is lost on Caddy
restart (`PLANNED` in the README); it survives config reloads.

### 5.5 What per-request limiting does not cover

- **Concurrency / slow clients / long-lived SSE.** MCP Streamable HTTP can hold streams open; a
  handful of requests can consume many connections and much memory while barely touching a
  per-request rate. The module has no concurrency limiter (open PR #98). Caddy's server `timeouts`
  (`read_header`, `read_body`, `idle`) are the available mitigations; note that v2.11.6 introduced
  default idle read/write timeouts and v2.11.7 fixed a regression where streams were cut off after
  a minute over HTTP/2 — preciser behaviour on long streams must be verified on the target version.
- **Bandwidth per request** (`request_body` only bounds backend reads; see 5.1).
- **Per-user fairness.** The bearer token is not available to the proxy without reading the
  `Authorization` header — do not do that. Per-subject fairness, if needed, belongs in the app, and
  the app currently has none.

---

## 6. Single node vs. distributed

The module supports clustering through a shared `certmagic` storage backend (`distributed.go`
writes per-instance state files, `List`/`Load` peers, and reconciles). The README is explicit that
this is **approximate and eventually consistent**, heavier on reads than writes, requires identical
zone configuration on every node, and needs tuning of read/write intervals.

For one droplet this is pure overhead and adds no accuracy: leave `distributed` unset so each node
keeps in-process state (and no storage I/O, no shared-state failure mode). Distributed mode becomes
relevant only if the service ever runs on two hosts — at which point per-IP limiting also has to
survive traffic splitting, and a proxy/CDN-based limiter or a shared store must be re-evaluated.

---

## 7. Docker build and supply chain

Documented build pattern (`https://caddyserver.com/docs/build`, section "Docker"):

```dockerfile
FROM caddy:<version>-builder AS builder
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    xcaddy build --with github.com/mholt/caddy-ratelimit@<commit-or-pseudo-version>
FROM caddy:<version>
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

Facts and constraints:

- **Go toolchain**: Caddy docs state Go **1.26 or newer** for building Caddy; `caddyserver/caddy`
  v2.11.7's `go.mod` says `go 1.26.0`; the plugin's `go.mod` says `go 1.24` (with `toolchain
  go1.24.3`) and requires `caddy v2.10.0`, so the builder image's toolchain — not the plugin's — is
  the binding constraint. My build used `go1.27.3`.
- **Pin two things**: the Caddy tag *and* the plugin commit (`@5625512f24` →
  `v0.1.1-0.20260612195517-5625512f24f6`). Because the plugin has **no releases**, a bare
  `--with github.com/mholt/caddy-ratelimit` silently tracks `master`.
- **Pin images by digest, not tag.** Observed 2026-11-03 via the registry API:
  `caddy:2.11.7-builder` index `sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0`,
  linux/amd64 manifest `sha256:420db7c0f6927c7e8140c666628915fb4a9141282fc5c344716ebf3879fe8f9b`.
  Treat these as observations to re-verify (`docker buildx imagetools inspect`) at build time, not
  as constants in a Dockerfile.
- **Provenance**: Caddy signs release artefacts with Sigstore since v2.6.0
  (`/docs/signature-verification`), but that covers Caddy's own artefacts — **not** the third-party
  module. The only verification for the plugin is Go module checksum-database integrity (`go.sum` /
  the `h1:` hash above), which proves you got *what GitHub served*, not that the code is sound. It
  is unaudited third-party code inside your TLS terminator.
- **Rebuild cadence**: Caddy ships security fixes frequently — v2.11.3 lists fastcgi/admin security
  patches, v2.11.4 is a security-heavy patch release, v2.11.6→v2.11.7 fixed a proxying crash and
  dropped streams. A custom binary means the CVE process is "watch Caddy releases, rebuild, redeploy,
  re-verify", not `apt upgrade`. If the plugin ever fails to compile against a new Caddy core
  (its own `go.mod` lags at v2.10.0), you are blocked on an upstream fix.
- **Ordering with releases**: rebuild only after the pinned plugin is confirmed buildable against
  the new core; my v2.11.7 + June-2026-plugin build is the only compatibility data point that exists.

---

## 8. Caddy + plugin vs. nginx (documentation facts)

| Dimension | Caddy + `caddy-ratelimit` | nginx `limit_req` / `limit_conn` |
| --- | --- | --- |
| Ships in the distro | No — custom build required | Yes (base `nginx`), no build step |
| Maintainer | Caddy's original author, personal repo, **not** an official Caddy project, no releases | nginx project, documented module `ngx_http_limit_req_module` (0.7.21) |
| Algorithm | Sliding window per key, ring buffer | Leaky bucket ("requests are delayed such that requests are processed at a defined rate"); `burst` default **0** ⇒ immediate rejection |
| Rejection status | `429` + automatic `Retry-After` (tested) | `503` by default, `limit_req_status`/`limit_conn_status` configurable; nginx docs never mention `Retry-After` |
| Memory bound | O(K·n) per key, reaped by sweep; no fixed cap | Explicit zone size (`zone=one:10m`); "one megabyte zone can keep about 16 thousand 64-byte states"; LRU eviction when exhausted |
| Concurrency limit | None (open PR) | `limit_conn`/`limit_conn_zone` (HTTP/2/3: each concurrent request counts as a connection) |
| Key derivation | `{client_ip}` (trusted-proxy-aware) or any placeholder | Any variable, canonically `$binary_remote_addr`; behind a proxy requires `ngx_http_realip_module` (`set_real_ip_from`, `real_ip_header`, `real_ip_recursive`, default **off** ⇒ use the last address in the header) |
| Spoof-resistance default | Good: no `trusted_proxies` ⇒ header ignored (tested) | Good with realip unset; realip must be scoped to the proxy ranges |
| TLS | Automatic HTTPS/ACME built in | Separate certbot/acme.sh + reload automation |
| Config/verification burden | Small Caddyfile, `caddy validate` | Larger config, needs a `nginx -t` + reload discipline |
| Error-body/-log control | `handle_errors`, log level is global | `limit_req_log_level`, `limit_req_status`, per-location granularity |

Neither is a WAF. Both are per-IP (not per-identity) and both are only as trustworthy as the client
IP derivation.

---

## 9. Recommendation

There is no unambiguously "safe" answer, because the risk trade is *third-party code in the TLS
terminator* (Caddy plugin) versus *a second, hand-managed config surface and manual TLS* (nginx).
Concretely:

- **If the operator wants to keep Caddy for automatic HTTPS (the direction implied by
  `docs/DIGITAL_OCEAN.md` §Reverse Proxy and `docs/PLAN.md`),** adopt `mholt/caddy-ratelimit` **only** together
  with: a digest-pinned builder image, a commit-pinned plugin, a documented rebuild-on-Caddy-release
  procedure, `{client_ip}` as the key **with no `trusted_proxies`** for this single-node layout,
  `ipv6_prefix 64`, a global per-site zone as a backstop, `disable_metrics` unless monitoring needs
  it, an explicit decision about the IP-bearing rejection log line, and the retention of
  `request_body max_size` plus server `timeouts`.
- **If the operator wants no third-party code in the proxy,** use nginx with `limit_req`
  (`429` via `limit_req_status 429;`, `burst` small or 0, `nodelay`), `limit_conn`, realip only if a
  trusted proxy is actually introduced, and certbot-managed certificates — and accept the extra
  operational surface.
- **A third option worth recording:** put the limiter in the FastAPI/Starlette app (repo-controlled,
  no custom binary, per-process state is fine on one node). It cannot protect the proxy from body,
  connection or header abuse, and it must not trust `X-Forwarded-For` unless the proxy is trusted —
  but for a 2–5 user staging service it is the smallest change that is fully inside this repository's
  review scope.

None of the three substitutes for the blocked activation gate, and none is per-user fair: for that,
a later app-level limit keyed on the verified `sub` is required (and it must never be implemented by
logging or proxying the bearer token).

### Candidate Caddy site (syntax-validated locally, **not activated**)

Adapted clean-room from `staging_mcp/Caddyfile.example`; `caddy validate` returned
`Valid configuration` against a v2.11.7+plugin build, and the 429 path was exercised on loopback.
It deliberately adds no `log` block, no `trusted_proxies`, and keeps the body cap.

```caddyfile
# CANDIDATE ONLY: merge as a separate site into the reviewed Caddy config; never replace existing sites.
mcp-staging.directedideation.com {
	request_body {
		max_size 64KB
	}

	rate_limit {
		zone per_client {
			key         {client_ip}
			events      30
			window      1m
			ipv6_prefix 64
		}
		zone site_total {
			key    static
			events 300
			window 1m
		}
		disable_metrics
		# log_key intentionally omitted: it writes the client IP/key to the log.
	}

	handle_errors {
		@rate_limited expression {http.error.status_code} == 429
		respond @rate_limited "rate limited" 429
	}

	reverse_proxy 127.0.0.1:8765
}
```

Numbers are placeholders, not tuned: `events 30 / 1m` per client and `300 / 1m` site-wide are
starting points that must be sized against real MCP client behaviour (bursts during discovery plus
tool calls) before any exposure. A limit that MCP clients treat as a hard failure is a availability
bug, not a safety feature — test with the pilot's actual clients.

---

## 10. Residual unknowns (do not treat as settled)

1. **Docker path unverified** — no Docker on the research machine; the builder-image pattern,
   digest pinning and cache-mount behaviour must be re-proven where the image is actually built.
2. **nginx path unverified** — no nginx was run; all nginx statements are documentation-only.
3. **Compatibility of plugin (June 2026) with future Caddy core** — exactly one data point
   (v2.11.7), and the plugin's declared dependency is older (v2.10.0).
4. **Behaviour under load/flood** — memory growth O(K·n), log volume, and sweep cost were not
   measured; the module logs one line per rejection, which a flood amplifies.
5. **MCP client reaction to 429/Retry-After** — untested; may surface as hard errors, may cause
   retry storms across all users behind one NAT.
6. **JWKS amplification** — whether a pre-auth flood triggers repeated JWKS fetches in FastMCP is
   unknown from this repository and would change the value of pre-auth limiting.
7. **IPv6 exposure on the droplet** — unverified whether the staging host has public IPv6; if it
   does not, `ipv6_prefix` is inert (harmless).
8. **Log/redaction interaction** — the rejection line contains only `remote_ip`, not headers or
   tokens, but journal forwarding/destination on the droplet was not inspected; where those logs go
   determines whether this is acceptable under the project's privacy posture.

---

## 11. Sources (accessed 2026-11-03 UTC)

Caddy — official documentation and source

- Rate limit is not standard: `https://caddyserver.com/docs/caddyfile/directives/rate_limit` (404);
  `/docs/caddyfile/directives` (standard directive list)
- Non-standard module disclaimer: `https://caddyserver.com/docs/modules/http.handlers.rate_limit`
- Registered plugins: `https://caddyserver.com/api/packages`; `https://caddyserver.com/docs/modules`
- `trusted_proxies`, `trusted_proxies_strict`, `client_ip_headers`, `metrics`:
  `https://caddyserver.com/docs/caddyfile/options`
- `client_ip` matcher: `https://caddyserver.com/docs/caddyfile/matchers`
- `request_body` (`max_size` → 413; `set` is badged v2.10.0+/experimental):
  `https://caddyserver.com/docs/caddyfile/directives/request_body`; module presence checked in Caddy tags
  `v2.4.6`, `v2.5.2`, `v2.6.4`, `v2.7.6`, `v2.8.4`, `v2.9.1`, `v2.10.0`
  (`modules/caddyhttp/requestbody/requestbody.go`)
- Build/plugins/Docker builder pattern, "Go 1.26 or newer": `https://caddyserver.com/docs/build`
- Artefact signing (Sigstore, v2.6.0+): `https://caddyserver.com/docs/signature-verification`
- Placeholder shorthands (`{client_ip}` → `{http.vars.client_ip}`), `determineTrustedProxy`:
  `caddyserver/caddy` v2.11.7 source (`caddyconfig/httpcaddyfile/shorthands.go:89`,
  `modules/caddyhttp/server.go`)
- Release notes v2.11.1–v2.11.7 (security patches, default idle timeouts, v2.11.7 stream/crash fix):
  `https://github.com/caddyserver/caddy/releases`
- `xcaddy` usage and `--with module[@version]`: `https://github.com/caddyserver/xcaddy`

Plugin — `github.com/mholt/caddy-ratelimit`

- README (features, distributed caveats, no-official-repo notice, PLANNED items):
  `https://github.com/mholt/caddy-ratelimit`
- Source: `handler.go`, `ratelimit.go`, `metrics.go`, `distributed.go`, `ringbuffer.go`, `caddyfile.go`,
  `.github/workflows/go.yml`, `go.mod`
- Issues #61, #64, #69, #92, #96, #98, #103: `https://github.com/mholt/caddy-ratelimit/issues`

nginx — official documentation

- `ngx_http_limit_req_module` (leaky bucket, `burst` 0 default, `limit_req_status` 503 default,
  zone memory sizing/LRU): `https://nginx.org/en/docs/http/ngx_http_limit_req_module.html`
- `ngx_http_limit_conn_module` (`limit_conn_status`, HTTP/2-3 request-per-connection note):
  `https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html`
- `ngx_http_realip_module` (`set_real_ip_from`, `real_ip_header`, `real_ip_recursive` default off):
  `https://nginx.org/en/docs/http/ngx_http_realip_module.html`

Repository context

- `staging_mcp/Caddyfile.example`, `docs/staging_mcp/DEPLOYMENT.md` (activation gate, 64 KB body cap,
  logging posture), `docs/DIGITAL_OCEAN.md` §Reverse Proxy, `docs/PLAN.md` §Pilot access and HTTPS.
