# Hosting options for the US pilot (research note)

Status: research only. No infrastructure has been provisioned or changed. All prices and
platform limits below were copied from provider documentation or pricing pages accessed on
**2026-10-30** (UTC). Prices, plan names, and preview features change frequently; re-verify at
purchase time. Statements are limited to what the cited page says; where a provider is silent
about a behaviour, that gap is listed under *Uncertainty* instead of being filled in. Monthly totals
are arithmetic over published line items and will differ from a real invoice.

Scope: one small Python ASGI service exposing MCP over Streamable HTTP, plus a durable database,
both under one provider, in a US region, for an invite-only pilot at roughly $20/month.

## 1. What the application actually requires

Facts taken from this repository, not from providers:

- **Runtime**: one long-lived container running FastAPI + FastMCP over Streamable HTTP on
  uvicorn (`README.md`, `pyproject.toml`). Not a static site, not a batch job.
- **Database engine**: the auth schema is written for **MySQL/MariaDB** with in-memory row locks
  (`FOR UPDATE`), SQLAlchemy + PyMySQL, InnoDB, `utf8mb4_bin`. It explicitly says SQLite is
  "for offline tests only" and does not establish production concurrency guarantees
  (`docs/AUTH_FOUNDATION.md`, `src/site_directedideation_com/auth/schema.py`).
  A Postgres-only host therefore implies an engine port and new concurrency tests, or a
  self-hosted MySQL.
- **Metrics storage**: the aggregate call counters use **SQLite on a local filesystem**
  (`src/site_directedideation_com/metrics.py`, and `SETUP.md`: "The database must be on a local
  filesystem"). On any PaaS with an ephemeral filesystem this data is lost on every deploy,
  restart, or scale event. Any host choice must either provide a durable disk or move metrics
  onto MySQL alongside auth.
- **Memory/CPU**: light traffic, one instance. No load-test evidence exists yet.

### MCP Streamable HTTP: what the platform must tolerate

From the MCP specification (transport revision 2025-06-18) and the FastMCP deployment guide:

- Clients `POST` each JSON-RPC message to one MCP endpoint; the server may answer with
  `text/event-stream` and stream the response. Clients may also `GET` the same endpoint to open a
  server-initiated SSE stream, or answer `405` to decline it. Servers may attach event IDs and
  support resuming via `Last-Event-ID`, and sessions may be tracked with `Mcp-Session-Id`.
- FastMCP's own docs state that long-running tools can hit "load balancers or proxies terminating
  connections that stay idle too long", and offer SSE polling (`EventStore` + `ctx.close_sse_stream()`)
  so the server can close the stream deliberately and let the client reconnect and replay.
- FastMCP's default `EventStore` is in-memory; a shared backend is required "for production
  deployments with multiple server instances".

Practical consequences for vendor selection: a host that hard-caps request duration, buffers SSE,
or kills idle connections can break long MCP tool calls; a host that restarts or rescales
instances mid-session drops in-memory MCP session state. Both are mitigable (short streamed
responses, SSE polling with a persistent event store, a single instance, sticky routing), but the
platform limits must be known before commitment.

## 2. Comparison (US regions, list prices, light single-instance pilot)

| Option | App hosting | Durable DB under the same provider | Persistent local disk | Idle/sleep behaviour | Managed backups | Approx. monthly | US regions |
|---|---|---|---|---|---|---|---|
| **DO App Platform + Managed MySQL** (status quo) | $5/mo (1 vCPU / 512 MiB shared, fixed) | Managed MySQL, single node, 1 GiB RAM / 10 GiB, $15/mo | **No** — AP has no volumes; 4 GiB local FS, wiped on deploy | None by default; Scale to Zero is private preview at 10% price | Included: daily backups, 7-day PITR | **~$20** | NYC, SFO, ATL, RIC, MKC (+ others) |
| **DO Droplet (self-managed)** | $6/mo (1 GiB / 25 GiB SSD) | MySQL installed on the same Droplet | Yes (the Droplet disk) | Never sleeps | Weekly backups +20% ($1.20) or daily +30%; snapshots $0.06/GB/mo | **~$7.20** | NYC, SFO, ATL, RIC, MKC (+ others) |
| **Railway (Hobby)** | $5/mo subscription incl. $5 usage; RAM $10/GB/mo → 512 MiB ≈ $5 | MySQL template (single node, Railway-maintained) ≈ $5 for 512 MiB + $0.15/GB volume | Yes (volumes, $0.15/GB/mo) | Optional Serverless (5–10 min idle), first request may 502 | Volume backups daily/weekly/monthly (kept 6/27/89 days); PITR 7 days opt-in | **~$10–15** | us-east4 (Virginia), us-west2 (California) |
| **Render (Hobby workspace)** | Starter $7/mo (512 MB / 0.5 CPU) | **No managed MySQL** — Postgres only ($6/mo) or MySQL on a disk | Yes, paid plans ($0.25/GB/mo); blocks multi-instance + zero-downtime deploys | Free tier only: 15-min spin-down, ~1 min cold start | Postgres PITR 3 days (Hobby) / 7 days (Pro); free tier none | **~$8–13** | Oregon, Ohio, Virginia |
| **Fly.io** | shared-cpu-1x 1 GiB $6.70/mo (256 MiB $2.19, 512 MiB $3.69) | **No managed MySQL**; Managed Postgres from $38/mo (over budget) → self-host MySQL on a volume | Yes (volumes $0.15/GB/mo) | `auto_stop_machines` scale-to-zero; cold start ~2 s (stop) or ~100s of ms (suspend); stopped rootfs $0.15/GB/mo | Volume snapshots daily, default 5 days, 1–60 configurable; $0.08/GB/mo, first 10 GB/mo free | **~$7–10** | iad (Ashburn), ewr (Secaucus) lowest-priced |
| **AWS Lightsail** | $5/mo (1 GiB / 40 GB SSD) or $3.50 (512 MB); container service $7/mo per nano node | Managed MySQL $15/mo (1 GiB, 40 GB; **no encryption at rest on that tier**) or self-host | Yes (the instance SSD) | Never sleeps | Instance/DB snapshots (manual and automatic per pricing page) | **~$20** (managed) / **~$5** (self-host) | Multiple US regions |

Not evaluated to the same standard (no verified official price captured here): Hetzner Cloud US,
Vultr, Linode/Akamai, Northflank, Koyeb, Heroku, Google Cloud Run + Cloud SQL. Treat these as open
candidates, not as validated options.

## 3. Provider-by-provider findings and caveats

### 3.1 DigitalOcean App Platform + Managed MySQL (the $20 baseline)

Pricing and limits (docs.digitalocean.com App Platform pricing/plans page; managed-databases
pricing page; App Platform *Limits*):

- Container plan `apps-s-1vcpu-0.5gb`: 1 shared vCPU, 512 MiB RAM, 50 GiB transfer, $5/mo.
  `apps-s-1vcpu-1gb-fixed`: 1 GiB RAM, $10/mo. Apps bill per second with a one-minute minimum;
  databases bill hourly with a one-hour minimum.
- **App Platform has no persistent storage**: "The host instances running App Platform containers
  do not provide persistent data storage. Data in the host instance's local filesystem is
  permanently lost after deployments… The local filesystem is additionally limited to 4 GiB…
  App Platform does not support volumes." This is why the current SQLite metrics cannot live on AP
  unchanged, and it is the reason a managed database is mandatory rather than optional.
- **App Platform free tier runs static sites only** (3 apps, 1 GiB egress each). There is no free
  container tier, so a hosted MCP server is always paid.
- **Development databases** ($7/mo, 512 MiB) are **PostgreSQL-only**, cannot be used by other apps,
  are not backed up, and are destroyed with the app — they do not satisfy the MySQL requirement.
- **Managed MySQL** cheapest Standard Edition cluster: 1 GiB RAM / 1 vCPU / 10 GiB storage,
  $15/mo, single node (automatic failover, but not HA). Backups: "MySQL cluster backups run
  automatically once per day and are retained for seven days"; point-in-time recovery is limited
  to the last 7 days; restoring creates a **new** cluster. DO's own pricing FAQ states managed
  databases include free daily backups.
- MySQL specifics: 75 backend connections on the 1 GiB plan; **connection pooling is not supported
  for MySQL**; only MySQL 8.4 for new clusters; `root` is not usable.
- **Upcoming plan change**: from 2026-10-15 (new accounts) / 2026-11-30 (all accounts), new
  Standard Edition clusters cannot use plans above 4 GiB RAM or add standby/read-only nodes.
  A 1 GiB single node stays available, but the growth path is narrower than before.
- **Sleeping**: Scale to Zero exists but is a **private preview requiring access request**, web
  services only, 10-minute to 24-hour inactivity window, billed at **10% of standard price** while
  asleep. Not a public, guaranteed feature today; do not plan the budget around it.
- **Streaming**: the App Platform *Limits* page documents a 600 s file-upload timeout, a 1 h build
  timeout, and a default termination grace period of 15 s (max 110 s) when an instance is replaced.
  It documents **no inbound HTTP request duration limit for web services**, and it states that the
  number of concurrent connections to an app is not capped. It also notes App Platform routes
  traffic through Cloudflare's global CDN.
  **Uncertainty**: no DigitalOcean page reviewed states how long an idle SSE stream may stay open,
  or that SSE is buffered-free; absence of a documented timeout is not a guarantee. A session
  restart also drops in-memory MCP session state, and the 15 s default termination grace limits how
  long in-flight streams survive a deploy.
- Region pairing works: dynamic apps run in NYC, SFO, ATL, RIC, MKC and others; managed MySQL is
  available in NYC1/2/3, SFO2/3, ATL1, RIC1, MKC1 (storage-optimised/general purpose differences
  per region). App and database must be in the same region.

### 3.2 DigitalOcean Droplet (self-managed, cheapest durable option)

- Basic Droplets: $4/mo (512 MiB / 10 GiB), $6/mo (1 GiB / 25 GiB), $12/mo (2 GiB / 50 GiB).
- Backups are "billed as a percentage of the Droplet's monthly cost": **20% weekly, 30% daily**;
  usage-based backup plans start at $0.01/GiB/mo with 3-day to 6-month retention. Snapshots are
  manual at $0.06/GB/mo and kept until deleted.
- So a $6 Droplet with weekly backups is ~$7.20/mo: a real MySQL, a real disk, no sleeping, no
  platform request-duration limits, and the same US regions as App Platform.
- Costs you take on: OS/MySQL patching, TLS/reverse proxy, monitoring, and single-host failure
  (weekly backups imply up to a week of data loss; daily backups narrow it to ~24 h for +$1.80).
  Droplet backups are documented as possibly degrading disk write performance while running, which
  matters for a database host.

### 3.3 Railway

- Plans: Free ($0, **$1 of free credit per month**, 0.5 GB RAM, 1 vCPU, 0.5 GB volume), Hobby
  ($5/mo including $5 of usage), Pro ($20/mo including $20), Enterprise. Trial: one-time $5 credit,
  30 days, 1 GB RAM, 5 services, restricted network until GitHub-verified; **volumes created by
  trial accounts are deleted 30 days after credits expire**.
- Metered rates: RAM $10/GB/mo, CPU $20/vCPU/mo, egress $0.05/GB, volume storage $0.15/GB/mo.
  Hobby volume cap 5 GB; Free plan 0.5 GB.
- MySQL is a **Railway-maintained template** deployed from the official MySQL Docker image, single
  node by default; it can be converted to a HA cluster (Group Replication + HAProxy). Backups are a
  separate native feature: manual or scheduled daily/weekly/monthly, kept 6/27/89 days,
  incremental/CoW and billed at volume rates; manual backups are capped at 50% of volume size;
  point-in-time recovery (7 days) is **opt-in** via binlog archiving. Wiping a volume deletes all
  its backups.
- **Documented edge limits that matter for MCP**: "HTTP requests can run for up to 15 minutes if
  data keeps transferring (for example, keep-alive heartbeats), and are otherwise closed after 5
  minutes with no data transferred"; idle HTTP/1.1 connections close after 60 s between requests;
  WebSockets are exempt from those limits and can idle indefinitely. A Streamable HTTP SSE response
  with no heartbeats would therefore be cut at ~5 minutes; with heartbeats, at ~15 minutes.
  FastMCP's SSE polling/`close_sse_stream()` is the documented mitigation.
- Serverless (formerly App Sleeping): sleeps 5–10 minutes after last outbound traffic, resumes on
  the first request, and "the first request sent to a slept service may return a 502 Bad Gateway".
  Keeping a database connection pool open prevents sleeping.
- Regions: US East (Virginia, `us-east4-eqdc4a`) and US West (California, `us-west2`).
- **Uncertainty**: Railway says you are "only charged for the resources you actually use" while the
  plan table lists provisioned caps; whether RAM bills on provisioned or measured usage changes the
  estimate materially. Confirm from a first invoice rather than assuming.

### 3.4 Render

- Workspaces: Hobby $0/mo + compute, Pro $25/mo. Web service compute: Free ($0, 512 MB, <1 CPU),
  Starter **$7/mo** (512 MB / 0.5 CPU), Standard $25/mo (2 GB / 1 CPU). Persistent disks
  **$0.25/GB/mo**, paid plans only.
- **Free instances**: spin down after 15 minutes without inbound traffic (HTTP requests *and*
  WebSocket messages count), ~1 minute to spin back up, ephemeral filesystem, and **Free Render
  Postgres expires 30 days after creation** — unusable for pilot data retention. 750 free instance
  hours per workspace per month.
- **No managed MySQL.** Render offers Postgres ($6/mo minimum) and Key Value only. Keeping MySQL
  means running it yourself on a persistent disk. A disk "prevents zero-downtime deploys" (the old
  instance is stopped first), cannot be attached to more than one instance, and blocks scaling to
  multiple instances — all of which interact badly with long-lived MCP sessions.
- Backups (Postgres): continuous PITR for paid instances — recovery window **3 days on Hobby**,
  7 days on Pro+; logical backups retained 7 days; **no recovery for Free-plan databases**.
- Regions: Oregon, Ohio, Virginia (US), plus Frankfurt and Singapore.
- **Uncertainty**: Render's docs reviewed here do not state a platform-level inbound request
  timeout; do not assume streaming is unlimited, and do not assume the free-tier spin-down rule
  ignores an open idle SSE connection (the documented rule counts inbound traffic, so an idle
  stream is a spin-down candidate).

### 3.5 Fly.io

- No platform fee; billed per second while a Machine runs. `shared-cpu-1x` with 256 MB $2.19/mo,
  512 MB $3.69, 1 GB $6.70; additional RAM $6/GB/mo. Volumes $0.15/GB/mo (billed at provisioned
  size even when detached or attached to a stopped Machine). Stopped/suspended Machine rootfs
  $0.15/GB/mo. Egress $0.02/GB in North America. Volumes snapshots $0.08/GB/mo with the first
  10 GB/month free.
- **Volumes are the durable store**: daily automatic snapshots by default with **5-day retention**,
  configurable 1–60 days. Fly documents the single-volume risk explicitly: on host failure, data
  written since the last snapshot is lost, and you should keep another backup or replica.
- **No managed MySQL.** Managed Postgres starts at **$38/mo (Basic)** — outside this budget. MySQL
  would be self-hosted on a Machine + volume.
- Scale-to-zero is first-class: `auto_stop_machines = "stop" | "suspend"` + `auto_start_machines`;
  the proxy stops a Machine when it has no traffic, cold start "about 2 seconds or more" (stop) or
  a few hundred milliseconds (suspend); first requests can fail while proxy nodes converge.
- Fly publishes a dedicated **Model Context Protocol** documentation section. It states that
  "the MCP protocol is both asynchronous and stateful, these examples will be run on a single
  machine (also known as a non highly available configuration). This enables MCP clients to fetch
  replies from the same server that they sent the request to", and recommends one Machine per MCP
  server. It also documents that stdio is the most common/interoperable transport while
  Streamable HTTP and the deprecated SSE transport are supported. This is the most explicit
  provider-level acknowledgement of MCP hosting constraints among the options reviewed.
- Free trial: 2 total VM hours **or** 7 days, whichever first; trial Machines auto-stop after
  5 minutes; 20 GB volume storage; adding a card ends the trial.
- **Uncertainty**: Fly does not document how a long-lived idle SSE connection interacts with the
  autostop heuristic (which is described in terms of request traffic and excess capacity). Whether
  a streaming MCP session keeps a Machine awake, or is interrupted by a stop, must be tested.

### 3.6 AWS Lightsail (fixed-price alternative with a managed MySQL)

- Instances: $3.50/mo (512 MB, 2 vCPU, 20 GB SSD, 1 TB transfer), **$5/mo** (1 GB, 40 GB SSD,
  2 TB). Container service nodes: $7/mo for a nano node (0.25 shared vCPU, 512 MB), 500 GB
  transfer included per container service.
- Managed databases: **$15/mo standard** (1 GB RAM, 1 core, 40 GB SSD, 100 GB transfer) — and that
  entry tier is listed with **"No Data encryption"**, with encryption starting at the $30 tier.
  This is a material difference from DigitalOcean's managed MySQL at the same price.
- Snapshots exist for instances, managed databases, and block storage (manual and automatic).
- Matches DO on price and keeps app + DB under one provider, but adds AWS account/billing surface
  and a documented at-rest-encryption gap on the cheapest database tier.

## 4. Free tier restrictions, summarised

| Provider | Free tier reality for this workload |
|---|---|
| DigitalOcean App Platform | Static sites only (3 apps, 1 GiB egress each). No free container. No free managed DB. |
| Railway | Free plan = $1 credit/month, 0.5 GB RAM, 1 vCPU, 0.5 GB volume, 1 replica. Trial = $5 one-time, 30 days, 1 GB RAM, 5 services, restricted network unless GitHub-verified; trial volumes deleted 30 days after credits expire. |
| Render | Free web service spins down after 15 min idle (≈1 min cold start), ephemeral FS, no disks, 750 instance-hours/month; **free Postgres expires after 30 days**; no backups/PITR on free. |
| Fly.io | No free tier: 7-day/2-VM-hour trial, trial Machines auto-stop after 5 min; adding a card ends the trial. |
| AWS Lightsail | No free tier for these bundles; the $15 managed MySQL has no at-rest encryption. |

## 5. Budget-ranked candidates for a very light US pilot

1. **DO Droplet, self-hosted MySQL — ~$7/mo** (or ~$8.40 with daily backups). Cheapest option that
   satisfies "durable database under the same provider" with no platform streaming limits and no
   sleep. Cost is operational: MySQL patching, TLS, monitoring, single-host failure.
2. **Fly.io Machine + volume — ~$7–10/mo** — same self-hosting trade-off as the Droplet, but with
   volumes, daily snapshots, scale-to-zero, and provider documentation that explicitly addresses
   stateful MCP hosting. No managed MySQL.
3. **Railway Hobby + MySQL template — ~$10–15/mo** — cheapest option that keeps MySQL *managed-ish*
   (maintained image, native backups, opt-in PITR) with volumes and a documented 15-minute streamed
   request ceiling that FastMCP can work around.
4. **DO App Platform + Managed MySQL — ~$20/mo (status quo)** — the only reviewed option that pairs
   a managed MySQL with included daily backups and 7-day PITR and no server administration, exactly
   at the stated budget. Its constraints: no persistent disk (so the SQLite metrics must move to
   MySQL or an object store), 512 MiB is tight for FastAPI + FastMCP, Scale to Zero is preview-only,
   and streaming behaviour is undocumented.
5. **Render — ~$8–13/mo** — only attractive if the data layer moves to Postgres (engine port +
   concurrency tests) or MySQL runs on a disk that blocks multi-instance deploys and zero-downtime
   restarts. Its free tier is disqualified by the 30-day database expiry.
6. **AWS Lightsail — ~$20/mo managed / ~$5 self-hosted** — functionally comparable to the DO
   baseline at the same price, with a weaker managed-database encryption story on the entry tier.

**Recommendation for the pilot decision, stated conservatively:** treat the current
DO App Platform + Managed MySQL pairing as the reference because it is the only option at the
budget that avoids both server administration and self-managed database backups, and accept two
concrete, testable risks: (a) no durable local disk means the SQLite metrics subsystem must be
re-pointed at the managed MySQL, and (b) SSE/Streamable HTTP behaviour is undocumented, so it must
be validated with a real MCP client against a deployed instance (short streamed responses, an
`EventStore` with SSE polling, and a single instance) before the pilot depends on it. If either risk
turns out to be unacceptable, the DO Droplet (~$7) is the cheapest fallback with identical region
and backup tooling and no platform-imposed streaming limits, at the cost of owning MySQL operations.

## 6. Explicit uncertainties and open questions

1. **DO App Platform streaming/SSE**: no documented inbound request-duration limit was found, but no
   documented guarantee of unbuffered long-lived SSE either, and traffic is fronted by Cloudflare's
   CDN. Verify empirically: open a Streamable HTTP GET SSE stream and a long tool call through a
   deployed app and measure time-to-first-byte and cut-off.
2. **DO Scale to Zero** is a *private preview* requiring a support request, billed at 10% while
   asleep. Do not budget for it or treat it as available.
3. **Railway billing basis** (provisioned vs measured RAM/CPU) is ambiguous in the docs; the
   estimate spans roughly $10–15/mo depending on the answer.
4. **Railway stream ceiling**: 15 minutes max per HTTP request even with heartbeats. Confirm the
   pilot's longest tool call fits, or rely on SSE polling.
5. **Fly autostop vs. open streams**: interaction between long-lived SSE connections and the
   "no traffic" heuristic is undocumented; test before relying on scale-to-zero for cost.
6. **Render**: no documented request timeout, and the free-tier spin-down rule counts inbound
   traffic only — an idle SSE stream may or may not keep a free service awake.
7. **Cursor of change**: DO's Standard Edition MySQL plan changes take effect 2026-11-30 for
   existing accounts (no >4 GiB plans, no standby nodes for new clusters); DO prices and Railway
   metered rates were read from live pages and can change without notice.
8. **Not researched to the same standard**: Hetzner Cloud US pricing (official USD figures are
   rendered client-side and were not machine-verified), Vultr, Akamai/Linode, Northflank, Koyeb,
   Heroku, Google Cloud Run + Cloud SQL. Any of them could beat the options above; they need their
   own primary-source pass.
9. **Compliance scope**: `PLAN.md` requires US hosting/processing for the pilot. All options above
   can be placed in a US region, but subprocessor disclosure, DPA availability, and data-residency
   guarantees for each provider's managed database were **not** verified here and are prerequisites
   before inviting users.

## 7. Sources (accessed 2026-10-30)

DigitalOcean
- App Platform pricing and container plans: https://docs.digitalocean.com/products/app-platform/details/pricing/ ; https://www.digitalocean.com/pricing/app-platform
- App Platform limits (no persistent storage, no volumes, 4 GiB local FS, build/upload timeouts): https://docs.digitalocean.com/products/app-platform/details/limits/
- App Platform Scale to Zero (private preview, 10% billing): https://docs.digitalocean.com/products/app-platform/how-to/scale-to-zero/
- App Platform regional availability: https://docs.digitalocean.com/products/app-platform/details/availability/
- App spec reference (termination grace 15 s default, max 110 s): https://docs.digitalocean.com/products/app-platform/reference/app-spec/
- Managed databases pricing: https://www.digitalocean.com/pricing/managed-databases ; MySQL pricing: https://docs.digitalocean.com/products/databases/mysql/details/pricing/
- MySQL limits (75 connections on 1 GiB, no pooling, PITR 7 days, plan change): https://docs.digitalocean.com/products/databases/mysql/details/limits/
- MySQL backup/restore (daily backups retained 7 days): https://docs.digitalocean.com/products/databases/mysql/how-to/restore-from-backups/
- MySQL availability by region: https://docs.digitalocean.com/products/databases/mysql/details/availability/
- Droplet pricing: https://www.digitalocean.com/pricing/droplets ; Backups pricing (20% weekly / 30% daily): https://www.digitalocean.com/pricing/backups ; Backups docs: https://docs.digitalocean.com/products/backups/details/features/

Railway
- Plans and metered rates: https://docs.railway.com/reference/pricing/plans
- Free trial and data retention: https://docs.railway.com/reference/pricing/free-trial
- Serverless (formerly app sleeping): https://docs.railway.com/reference/app-sleeping
- Public networking specs and limits (15-min streamed requests, 60 s idle): https://docs.railway.com/networking/public-networking/specs-and-limits
- Volumes: https://docs.railway.com/volumes ; Backups: https://docs.railway.com/volumes/backups ; PITR: https://docs.railway.com/volumes/point-in-time-recovery
- MySQL: https://docs.railway.com/databases/mysql ; Regions: https://docs.railway.com/deployments/regions

Render
- Pricing: https://render.com/pricing ; Free instances: https://render.com/docs/free
- Persistent disks (limitations and $0.25/GB): https://render.com/docs/disks
- Postgres backups/PITR windows: https://render.com/docs/postgresql-backups ; Regions: https://render.com/docs/regions
- Web services (feature list, no documented request timeout): https://render.com/docs/web-services

Fly.io
- Resource pricing: https://fly.io/docs/about/pricing/ ; Free trial: https://docs.fly.io/about/free-trial.md
- Autostop/autostart and stopped-Machine cost: https://docs.fly.io/launch/autostop-autostart.md ; https://docs.fly.io/reference/fly-proxy-autostop-autostart.md
- Volumes and snapshots: https://docs.fly.io/volumes/index.md ; https://docs.fly.io/volumes/snapshots.md
- MCP on Fly.io (single-Machine guidance for stateful MCP): https://fly.io/docs/model-context-protocol/ ; transports: https://docs.fly.io/model-context-protocol/transports.md
- Regions: https://fly.io/docs/reference/regions/

AWS Lightsail
- Pricing (instances, containers, managed databases, snapshots): https://aws.amazon.com/lightsail/pricing/

Protocol and framework
- MCP Streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- FastMCP HTTP deployment (SSE polling, EventStore, multi-instance storage): https://gofastmcp.com/deployment/http.md
