# Identity provider options: WorkOS AuthKit vs Auth0 for MCP OAuth (research note)

Status: research only. No provider account was created, no tenant was configured, and no
repository code changed. Every provider statement below is copied from the cited page and
was accessed on **2026-11-02** (UTC). Prices, plan gates, preview features, and MCP client
behaviour change frequently; re-verify before committing. Where a page is silent, the gap is
recorded under *Unknowns* rather than filled in.

Scope: the invite-only US pilot described in `docs/PLAN.md` — one Python MCP server (FastMCP over
Streamable HTTP) at `mcp.directedideation.com`, roughly 2–5 users, email/password accounts
with verification and recovery, MCP-compatible OAuth from an established authorization
server, and real connections from Pi, Claude, and ChatGPT. This note compares **WorkOS
AuthKit** (current leading candidate) with **Auth0** on: MCP OAuth compatibility, password
authentication, pricing, US processing, and client requirements.

## 1. Baseline: what the MCP clients and specification require

Facts from the specification and each client's own documentation, before looking at either
provider. These are the compatibility tests a provider either passes or fails.

### 1.1 MCP authorization specification (revision 2026-07-28)

From <https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization>:

- Authorization is OPTIONAL for MCP, but HTTP transports SHOULD conform to it.
- Built on OAuth 2.1 plus RFC 6750, RFC 8414, RFC 7591 (DCR), RFC 8707 (resource
  indicators), RFC 9728 (protected resource metadata), RFC 9207 (issuer identification),
  and the Client ID Metadata Document draft.
- Authorization servers **MUST** implement OAuth 2.1; authorization servers and clients
  **SHOULD** support Client ID Metadata Documents (CIMD); **DCR is deprecated** and kept only
  for backwards compatibility with authorization servers that do not support CIMD.
- MCP servers **MUST** implement OAuth 2.0 Protected Resource Metadata, and clients **MUST**
  use it for authorization-server discovery.
- Authorization servers **MUST** publish either OAuth 2.0 Authorization Server Metadata
  (RFC 8414) or OIDC Discovery, and clients **MUST** support both.

Practical consequence for this project: the *server* must host
`/.well-known/oauth-protected-resource` and return a `WWW-Authenticate` challenge; the
*provider* must publish discovery metadata, support PKCE `S256`, map the RFC 8707 `resource`
parameter into the token audience, and support CIMD (preferred) and/or DCR.

### 1.2 ChatGPT (OpenAI connectors)

From <https://developers.openai.com/plugins/build/auth.md> (accessed 2026-11-02):

- Requires OAuth 2.1 conforming to the MCP authorization spec; "ChatGPT, acting as the MCP
  client, performs the authorization-code flow with PKCE using the `S256` code challenge".
- The MCP server must host protected resource metadata and return `401` with
  `WWW-Authenticate: Bearer resource_metadata="…"`.
- "Expect ChatGPT to append `resource=https%3A%2F%2Fyour-mcp.example.com` to both the
  authorization and token requests" and the authorization server must copy that into the
  access token (commonly `aud`).
- Discovery metadata must include `code_challenge_methods_supported` containing `S256`;
  "MCP servers are unsupported when their authorization server metadata omits this field or
  does not advertise `S256`".
- Client identification: CIMD is preferred. ChatGPT uses CIMD when the authorization server
  sets `client_id_metadata_document_supported: true`; otherwise DCR via `registration_endpoint`,
  or a predefined OAuth client.
- RFC 9207 issuer identification (`authorization_response_iss_parameter_supported: true`,
  `iss` on every success **and** error response) is what allows the stable redirect URI
  `https://chatgpt.com/connector_platform_oauth_redirect`; without it ChatGPT uses a
  callback-ID-specific redirect.
- "ChatGPT does **not** support machine-to-machine OAuth grants such as client credentials,
  service accounts, or JWT bearer assertions, nor can it present custom API keys or
  customer-provided mTLS certificates." ChatGPT itself presents an OpenAI-managed mTLS client
  certificate.
- Token verification (signature, issuer, audience, expiry, scopes) is the MCP server's
  responsibility.
- Optional for ChatGPT Enterprise workspace domain restrictions: publish OIDC discovery,
  advertise and enable `openid` and `email`, and expose a UserInfo endpoint returning
  `email` with `email_verified: true`.

### 1.3 Claude (claude.ai / Desktop / Cowork custom connectors)

From <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
(accessed 2026-11-02):

- "Claude connects to your remote MCP server from Anthropic's cloud infrastructure, rather
  than from your local device… your MCP server must be reachable over the public internet
  from Anthropic's IP ranges." A server behind a VPN or private network will not connect.
- Custom connectors are available on Free (one connector), Pro, Max, Ultra, Team, and
  Enterprise plans; Team/Enterprise require an Owner to add the connector.
- Authentication choices: "Sign in now", "Sign in when needed", or "No sign in".
- OAuth client choices: "**Use Claude's published identity (Recommended)**" (CIMD),
  "**Register automatically**" (DCR), or "**Use your own OAuth client**".
- Static request headers (API key / bearer token) are supported as a non-OAuth alternative.

From <https://code.claude.com/docs/en/mcp> (Claude Code, accessed 2026-11-02): Claude Code
supports OAuth for HTTP servers, discovers via `WWW-Authenticate`, supports servers that use a
Client ID Metadata Document "instead of Dynamic Client Registration", and errors with
"Incompatible auth server: does not support dynamic client registration" when neither CIMD nor
DCR works and no pre-registered client is supplied. `--callback-port` fixes the loopback
redirect.

### 1.4 Pi

Pi's coding-agent MCP documentation (<https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md>;
the repository was formerly `badlogic/pi-mono`; accessed 2026-11-02):

- Remote servers use Streamable HTTP with `url`, `headers`, and `oauth`; the legacy SSE
  transport is not supported.
- On a 401 the user signs in via `/mcp` or `pi mcp login <name>`; tokens are stored in
  `~/.pi/agent/mcp-auth.json` and refreshed.
- "Pi identifies itself to the authorization server with its Client ID Metadata Document or
  by registering a client." The document is `https://pi.dev/oauth/client.json` with redirect
  `http://127.0.0.1:<port>/callback`, used when the authorization server advertises support
  for documents and public clients; otherwise Pi registers dynamically.
- `clientRegistration` can be forced to `auto` (default), `dcr`, or `cimd`. For a server that
  "does not support dynamic client registration", a pre-registered `clientId`/`clientSecret`
  (and `callbackPort`/`callbackUrl`) can be configured instead.
- Pi discovers the authorization server through the server's protected resource metadata
  (RFC 9728) and checks that authorization server metadata names the expected issuer
  (RFC 8414); `authServerMetadataUrl` overrides discovery for misconfigured servers.
- Redirect URIs must be loopback (`localhost`, `127.0.0.1`, `[::1]`).

**Cross-client consequence:** CIMD is the preferred registration path for all three clients,
DCR is the universal fallback, and Pi/Claude Code additionally accept a manually registered
client. A provider that offers only one of CIMD/DCR, or that fails to advertise the CIMD
support flag, will force a per-client workaround.

## 2. WorkOS AuthKit

Primary source: <https://workos.com/docs/authkit/mcp> ("Model Context Protocol", accessed
2026-11-02).

### 2.1 MCP authorization support

- AuthKit is documented as "a spec-compatible OAuth authorization server" built on WorkOS
  Connect, publishing metadata at `https://authkit_domain/.well-known/oauth-authorization-server`
  with `authorization_endpoint`, `token_endpoint`, `registration_endpoint`,
  `introspection_endpoint`, `code_challenge_methods_supported: ["S256"]`,
  `grant_types_supported: ["authorization_code", "refresh_token"]`, scopes
  `["email","offline_access","openid","profile"]`, and token endpoint auth methods
  `none`, `client_secret_post`, `client_secret_basic`.
- **CIMD:** supported but "off by default"; enable in *Connect → Configuration*. The doc states
  CIMD "was added to the MCP specification in November 2025" and that DCR "can be enabled…
  for backwards compatibility with MCP clients that don't yet support Client ID Metadata
  Document".
- **Resource indicators (RFC 8707):** the MCP endpoint URL must be registered as a valid
  resource indicator; issued tokens carry `aud` matching the requested `resource`. If no
  resource indicator is configured, `aud` falls back to the environment client ID and the
  `resource` parameter is ignored.
- **Default resource indicator:** for clients that omit `resource`, one configured indicator
  can be marked default; requests that do include `resource` are still validated against the
  configured list. The default applies only to CIMD/DCR-registered clients, not to
  hand-created OAuth/M2M Connect applications.
- **Wildcards:** one `*` allowed, as a hostname wildcard (`https://*.preview.example.com/mcp`)
  or a final-path-segment wildcard (`https://app.example.com/mcp/*`); a wildcard cannot be the
  default.
- **Verification guidance:** verify AuthKit JWTs against
  `https://authkit_domain/oauth2/jwks` with issuer and audience checks, and return a
  `WWW-Authenticate` header whose `resource_metadata` points at the server's
  `/.well-known/oauth-protected-resource`.
- **Compatibility shim:** for clients that do not support protected resource metadata and
  instead fetch authorization-server metadata from the MCP server, WorkOS documents proxying
  `/.well-known/oauth-authorization-server` to AuthKit.
- **Cross App Access** (ID-JAG token exchange) exists but is "available in early access" and
  unsupported with Standalone MCP Auth — not a pilot dependency.
- **Standalone Connect** lets an existing auth stack keep its own login page and call
  AuthKit's completion API; CIMD must still be enabled. Not needed if AuthKit hosts login.

### 2.2 Password authentication, verification, recovery

- <https://workos.com/docs/authkit/email-password>: "Email + Password authentication … is one
  of the most common forms of authentication and is **enabled by default**." Default policy
  enforces minimum length, rejects low-complexity passwords, and **rejects breached passwords
  (flagged by haveibeenpwned)**; password history can reject up to 10 previous passwords
  (disabled by default); the policy is enforced in sign-up and reset flows. Password auth can
  be disabled entirely (SSO-only).
- <https://workos.com/docs/authkit/email-verification>: verification is a two-step code flow
  and "**Email verification is always on**"; SSO users with a verified domain and users who
  accept an invitation within 10 minutes are auto-verified. AuthKit sends the email itself, or
  you can send it.
- <https://workos.com/docs/reference/authkit/password-reset>: create a one-time reset token by
  email and reset the password; "When a user's password is reset, all of their active sessions
  are revoked."

### 2.3 Pricing (published 2026-11-02)

<https://workos.com/pricing>:

- AuthKit: first **1,000,000 MAUs free**; each additional 1M MAUs **$2,500/mo**. Includes
  email + password, social login, passkeys, MFA, magic auth, enterprise SSO.
- Custom domain: **$99/mo**. Staging environments are free; only production environments are
  billed. Standard support is free; Scale support is $1,000/mo.
- SSO/Directory Sync $125 per connection (not needed for the pilot's email/password scope);
  Radar bot/fraud first 1,000 checks free, then $100 per 50K.
- MAU definition: "A user who performs any action (sign up, sign in, or profile update)
  within a calendar month."

For a 2–5 user pilot the AuthKit line item is **$0/mo** at list price, with $99/mo only if a
custom login domain is required. WorkOS does not publish a separate "MCP Auth" line item on
this page; MCP auth is documented as part of AuthKit/Connect.

### 2.4 US processing

- WorkOS Data Processing Addendum, Exhibit B (Data Transfer Impact Assessment),
  <https://workos.com/legal/dpa>: for data transferred outside the EEA/Switzerland/UK, the
  answer to "What countries will Subscriber Personal Data … be stored in or accessed from?"
  is "**United States of America**", and the DPA authorises transfers "including from the
  European Economic Area, Switzerland, and/or the United Kingdom to the United States."
- WorkOS blog, 29 January 2026, <https://workos.com/blog/data-residency-for-enterprise-saas>:
  describes vendors that "keep content in-region while authentication flows through WorkOS's
  US-based service".
- Subprocessors are published at <https://workos.com/legal/subprocessors> (the link resolves to
  the Vanta-hosted trust center, which is rendered client-side and was not machine-readable in
  this pass).
- The security page (<https://workos.com/security>) states SOC 2 Type 2, GDPR/CCPA compliance,
  annual third-party penetration tests, and external code audits; it does not state a hosting
  region.

## 3. Auth0

### 3.1 MCP authorization support

From <https://auth0.com/ai/docs/mcp/overview> and the Auth for MCP guides (accessed
2026-11-02):

- Auth0's "Auth for MCP" provides "OAuth 2.1 and OpenID Connect", standards-based discovery
  and client registration, resource-scoped tokens, On-Behalf-Of token exchange, and Token
  Vault for third-party APIs.
- The MCP server must return `401` with `WWW-Authenticate` and host
  `/.well-known/oauth-protected-resource` pointing at the Auth0 tenant
  (<https://auth0.com/ai/docs/mcp/guides/registering-your-mcp-client-application/dynamic-client-registration>).
- **DCR** is supported but "disabled for all tenants" by default; enabling it opens "an open
  DCR endpoint, which means that if you enable this feature without additional protections,
  anyone on the internet can create applications in your tenant." The documented mitigations
  (Tenant Access Control List, reverse proxy) are "available to Enterprise customers only."
  DCR-created applications are third-party applications, so the tenant must define default
  permissions for third-party applications.
- **CIMD** is supported in two forms (manual import and dynamic runtime registration),
  <https://auth0.com/docs/get-started/auth0-overview/create-applications/cimd-overview>:
  CIMD clients are always third-party applications with `third_party_security_mode: "strict"`,
  "login flows for CIMD clients fail if your tenant has active Rules", the maximum is 500
  dynamically registered CIMD clients per tenant, and "Private Key JWT authentication is
  available only for Enterprise customers." Auth0's own guidance for production MCP is to
  prefer CIMD over DCR.
- **RFC 8707 resource parameter:** Auth0 "has historically used the `audience` parameter".
  Supporting `resource` requires enabling two tenant toggles — **Resource Parameter
  Compatibility Profile** and **Include Issuer in Authorization Responses** — after which
  Auth0 uses `resource` for the token audience; if both `resource` and `audience` are present,
  `audience` still wins (<https://auth0.com/ai/docs/mcp/guides/resource-param-compatibility-profile>).
  The same page notes RFC 8707 and the MCP authorization spec require the resource to be an
  absolute URI.

### 3.2 Password authentication, verification, recovery

- <https://auth0.com/docs/authenticate/database-connections/password-options>: database
  connection password policies are password history (up to 24), a 10,000-entry common-password
  dictionary plus custom entries, blocking personal data (name/username/nickname/email local
  part), and five OWASP-aligned strength levels. This page does **not** describe a
  breached-password check.
- Breached Password Detection is a separate attack-protection feature whose "Plans included"
  row reads "B2B / B2C Professional and Enterprise | Part of Attack Protection add-on in
  Enterprise plan" (<https://auth0.com/docs/secure/attack-protection/breached-password-detection>).
  It is therefore not part of Free or Essentials.
- <https://auth0.com/docs/authenticate/database-connections/password-change>: password reset is
  an emailed one-time link (only the most recent link is valid; URL lifetime is configurable),
  and "Resetting a user's password makes their session expire."
- Email verification is managed per user account via the verification email/ticket workflow
  (<https://auth0.com/docs/manage-users/user-accounts/verify-emails>).

### 3.3 Pricing (published 2026-11-02)

<https://auth0.com/pricing>:

| Plan | B2C starting price | B2B starting price | MAUs at start |
| --- | --- | --- | --- |
| Free | $0/mo | $0/mo | up to 25,000 |
| Essentials | $35/mo | $150/mo | 500 |
| Professional | $240/mo | $800/mo | 500 |
| Enterprise | contact sales | contact sales | custom |

- Yearly billing is 11× the monthly price. Pricing exists only at listed MAU tiers; usage
  between tiers bills at the next tier up.
- B2C Essentials adds higher limits, Pro MFA, RBAC per organization, 10 organizations, audit
  log streaming, and separate production/development environments.
- B2C Professional adds enhanced attack protection, use of an existing user database, and
  enterprise MFA.
- Free includes 25,000 MAU, 1 custom domain (footnoted with an asterisk whose footnote text
  was not captured), 5 organizations, basic attack protection, and "Secure Agentic AI
  workflows".
- The "Auth0 for AI Agents" add-on (unlimited Token Vault, all CIBA forms) "adds 50% to the
  base price": $18/mo on B2C Essentials at 500 MAU, $120/mo on B2C Professional at 500 MAU.
- MAU: "Any non-internal (non-employee) user that authenticated during a given month for a
  given tenant."

For a 2–5 user pilot the cheapest usable line item is **Free ($0)** or **B2C Essentials
($35/mo)**. The MCP-relevant controls that are gated above that are the deciding factor:
DCR abuse protections, breached-password detection, and CIMD `private_key_jwt` all require
Professional or Enterprise (see 3.1 and 3.2), i.e. **$240/mo B2C** at minimum, or an
Enterprise agreement.

### 3.4 US processing

- Auth0 tenant region is chosen at creation and determines where data is hosted:
  <https://auth0.com/docs/get-started/auth0-overview/create-tenants> lists localities
  Australia (AU), Canada (CA), Europe (EU, EU-2), Japan (JP), United Kingdom (UK), and
  "United States of America (US, US-3, US-4, US-5)". "Localities based on the selected region
  may be specified, which control the assigned tenant domain and the region where your data
  will be hosted."
- <https://auth0.com/docs/secure/data-privacy-and-compliance/data-processing> describes what
  Auth0 stores, retention (free-plan tenants with no activity for 150 days are scheduled for
  deletion), encryption, and access controls, but the Markdown version reviewed does not
  enumerate regions beyond pointing at the tenant region choice above.
- Auth0 is owned by Okta; compliance and subprocessor material is published on
  <https://security.okta.com/> (not enumerated here).

## 4. Side-by-side on the pilot's decision criteria

| Criterion | WorkOS AuthKit | Auth0 |
| --- | --- | --- |
| Authorization-server discovery | Documented metadata endpoint with S256, code+refresh grants | OIDC/OAuth metadata; `iss` in responses requires a toggle |
| Protected resource metadata (RFC 9728) | Required on our server; doc includes a proxy fallback for clients that skip it | Required on our server |
| CIMD | Supported, **off by default**, enable in dashboard | Supported (manual + dynamic); dynamic stage label unresolved (see Unknowns); `private_key_jwt` Enterprise-only |
| DCR | Supported, enable in dashboard for backwards compatibility | Supported, **off by default**; open endpoint; abuse controls Enterprise-only |
| RFC 8707 `resource` → `aud` | Native; resource indicators registered per environment, default + wildcard options | Requires enabling the Resource Parameter Compatibility Profile (plus issuer-in-response toggle) |
| RFC 9207 `iss` in authorization responses | Not stated in the MCP guide (see Unknowns) | Available via the "Include Issuer in Authorization Responses" toggle |
| Email + password | Enabled by default, hosted UI | Database connection, hosted Universal Login |
| Breached-password rejection | On by default (haveibeenpwned) | Breached Password Detection: Professional/Enterprise only |
| Password reset | One-time token API; reset revokes all sessions | Emailed one-time link; reset expires the session |
| Email verification | Always on, code-based | Verification email/ticket workflow |
| MFA / passkeys | Included in AuthKit | Pro MFA on Essentials; enterprise MFA on Professional |
| Team/org model for the pilot | AuthKit organizations, invitations, roles | Organizations (5 on Free, 10 on Essentials) + RBAC per org from Essentials |
| List price at 2–5 users | $0/mo (+$99/mo if custom domain) | $0/mo Free or $35/mo Essentials; $240/mo if Professional-gated MCP controls are required |
| US data hosting | US per DPA Exhibit B; no EU option documented | US locality selectable at tenant creation (US, US-3, US-4, US-5) |
| MCP-specific product surface | Dedicated MCP Auth guide, Standalone Connect, default/wildcard resource indicators | Dedicated Auth for MCP guides, Token Vault, OBO exchange, FGA, Cross App Access |

Reading of the evidence, stated conservatively: both providers can satisfy the *protocol*
requirements for Pi, Claude, and ChatGPT, but Auth0 requires more tenant configuration
(RFC 8707 profile, issuer toggle, DCR toggle plus Enterprise-only abuse controls, default
permissions for third-party apps) and pushes several MCP/security-relevant controls into
Professional/Enterprise pricing, while WorkOS's MCP guide is written around the same CIMD/DCR
+ resource-indicator model that the three clients now expect, at $0 for a pilot of this size.
That is a documentation-and-pricing comparison, not a measured interoperability result — no
tenant has been exercised.

## 5. Unknowns and unverified items

1. **WorkOS live metadata.** The MCP guide's sample metadata does not show
   `client_id_metadata_document_supported` or
   `authorization_response_iss_parameter_supported`. ChatGPT uses CIMD only when the former is
   `true`, and uses the stable redirect only when the latter is `true`. Whether AuthKit emits
   them once CIMD is enabled was not verified against a live environment.
2. **WorkOS DCR abuse controls.** No WorkOS page reviewed documents rate limiting, allowlisting,
   or cleanup for its `registration_endpoint`, and no statement about what a DCR-registered
   client can request. Auth0, by contrast, documents an open endpoint and Enterprise-only
   mitigations.
3. **Auth0 dynamic CIMD availability.** The Markdown export renders the callout as "The Dynamic
   CIMD Registration feature is in ." and the server-rendered HTML injects that label at
   runtime; the release stage (early access / beta / GA) and any plan gate could not be
   resolved on 2026-11-02.
4. **Auth0 CIMD token-endpoint methods.** ChatGPT prefers `private_key_jwt` when it is in the
   intersection and falls back to `none`; Auth0 states `private_key_jwt` is Enterprise-only.
   Whether Auth0 accepts ChatGPT's public-client CIMD (`none`) on lower plans was not verified.
5. **Client-version coverage.** The repository's capability probe used Pi 1.4.0
   (`docs/CAPABILITY_PROBE.md`); the Pi MCP/OAuth documentation reviewed is from the current
   `main` branch. Which Pi release first shipped CIMD/DCR sign-in, and whether the installed
   version matches, is unverified. The same applies to ChatGPT connector availability by plan
   and to Claude's per-plan connector limits beyond "Free: one".
6. **Subprocessors and support access.** WorkOS's subprocessor list is behind a client-rendered
   trust center; Okta's equivalent was not enumerated. Neither provider's DPA was reviewed for
   staff access locations, backup regions, or email-delivery subprocessors, which `docs/PLAN.md`
   requires disclosing.
7. **EU residency.** No WorkOS documentation page describing a data-residency option was found
   (candidate URLs redirect to `/docs/`); the DPA points to US storage. Auth0 documents region
   selection at tenant creation. Neither is a substitute for legal review of the pilot's
   disclosures.
8. **Billing behaviour under MAU counting.** Both providers count each user who signs in during
   a month as an MAU, and Auth0 bills at the next tier up between tiers. Actual invoices for a
   5-user pilot were not obtained; Auth0's Free-plan custom-domain footnote was not captured.
9. **MCP client behaviour that neither provider controls.** Whether ChatGPT, Claude, and Pi
   each complete a real sign-in against a given tenant (CIMD document fetch, redirect allowlist,
   consent screen, token audience) is an integration result, not a documentation fact.

## 6. Recommended next verification (no implementation)

Before selecting a provider, exercise both on free/staging environments and record results:

1. Create a WorkOS staging environment and an Auth0 free tenant in a US locality; enable CIMD
   (and DCR if testing fallback) and register the proposed MCP resource URL.
2. `curl` each provider's `/.well-known/oauth-authorization-server` and
   `/.well-known/openid-configuration` and check for: `S256`, `registration_endpoint`,
   `client_id_metadata_document_supported`, `authorization_response_iss_parameter_supported`,
   and the token-endpoint auth methods actually accepted.
3. Register one pre-created OAuth client and run MCP Inspector plus real Pi, Claude, and
   ChatGPT connections against a staging MCP endpoint that implements protected resource
   metadata; record which registration mode each client chose and whether the issued `aud`
   matches the resource.
4. Confirm password flows end to end: sign-up, verification email delivery and sender domain,
   reset link lifetime, session revocation after reset, and breached-password rejection.
5. Obtain written confirmation of the plan gate for each MCP/security control in use (Auth0:
   DCR abuse controls, breached-password detection, CIMD `private_key_jwt`; WorkOS: nothing
   identified beyond the custom-domain fee), plus the current subprocessor list and DPA for
   both, before inviting users.

## 7. Sources (all accessed 2026-11-02 UTC)

Protocol and clients
- MCP authorization specification, revision 2026-07-28: <https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization>
- OpenAI, plugin authentication: <https://developers.openai.com/plugins/build/auth.md>
- Claude Help Center, custom connectors using remote MCP: <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>
- Claude Code, MCP: <https://code.claude.com/docs/en/mcp>
- Pi coding agent, MCP (repo formerly `badlogic/pi-mono`): <https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md>; Pi MCP client package: <https://github.com/earendil-works/pi/blob/main/packages/mcp/README.md>

WorkOS
- Model Context Protocol with AuthKit: <https://workos.com/docs/authkit/mcp>
- Email + Password: <https://workos.com/docs/authkit/email-password>
- Email Verification: <https://workos.com/docs/authkit/email-verification>
- Password reset API: <https://workos.com/docs/reference/authkit/password-reset>
- Pricing: <https://workos.com/pricing>
- Data Processing Addendum (Exhibit B): <https://workos.com/legal/dpa>
- Subprocessors: <https://workos.com/legal/subprocessors>
- Security overview: <https://workos.com/security>
- Data residency blog, 29 January 2026: <https://workos.com/blog/data-residency-for-enterprise-saas>

Auth0
- Auth for MCP overview: <https://auth0.com/ai/docs/mcp/overview>
- Dynamic Client Registration: <https://auth0.com/ai/docs/mcp/guides/registering-your-mcp-client-application/dynamic-client-registration>
- Resource Parameter Compatibility Profile: <https://auth0.com/ai/docs/mcp/guides/resource-param-compatibility-profile>
- CIMD registration overview: <https://auth0.com/docs/get-started/auth0-overview/create-applications/cimd-overview>
- Register applications with CIMD: <https://auth0.com/docs/get-started/auth0-overview/create-applications/register-applications-with-cimd>
- Tenants, region and locality: <https://auth0.com/docs/get-started/auth0-overview/create-tenants>
- Database connection password policies: <https://auth0.com/docs/authenticate/database-connections/password-options>
- Password change and reset: <https://auth0.com/docs/authenticate/database-connections/password-change>
- Verify emails: <https://auth0.com/docs/manage-users/user-accounts/verify-emails>
- Breached Password Detection: <https://auth0.com/docs/secure/attack-protection/breached-password-detection>
- Data processing: <https://auth0.com/docs/secure/data-privacy-and-compliance/data-processing>
- Pricing: <https://auth0.com/pricing>
