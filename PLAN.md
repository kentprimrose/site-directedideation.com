# Directed-Ideation MCP Plan

## Goal and assumptions

Build an agent-facing MCP service for purposeful exploration under explicit goals and constraints. The service is intended to be offered to users over the network, not only run by a trusted local operator. The host agent supplies idea generation and subjective judgments; the service structures the workflow, validates submissions, and preserves context. The MCP service is separate from the static field-guide website.

The method has three stages, matching the site: **identify opportunities**, **select goals**, and **ideate with purpose**. Stage activities, submissions, transitions, and completion criteria will be defined in the method contract. Hosted service operation and protection of user information are foundational requirements, not later expansion options. Autonomous execution of proposed experiments remains out of scope.

Security cannot be guaranteed absolutely. The service must minimize data collected, clearly disclose its handling, and provide evidence users can independently inspect rather than treating silence or unverified assurances as proof of safety.

## Architecture

- Build a model-independent MCP server using an official MCP SDK. Provide a network transport suitable for hosted MCP clients, behind a hardened TLS-terminating ingress; do not expose an unauthenticated service or rely on stdio as the user-facing hosted transport.
- Separate the MCP adapter, workflow engine, versioned method definitions, identity/authorization layer, and persistence layer. Keep the API stateless where possible and store session state in a managed relational database with tenant-scoped authorization and transactional mutations.
- Authenticate users through a well-supported identity provider (OIDC/OAuth); authorize every operation against the authenticated principal and tenant. Use short-lived, audience-restricted credentials, secure token validation, rotation/revocation, and no secrets in URLs. Document supported MCP client authorization flows and limitations.
- Enforce tenant isolation in application queries and database policies; test cross-tenant access explicitly. Separate administrative access, use least privilege, and require strong authentication and audited approval for privileged operations.
- Encrypt transport with current TLS and encrypt databases, object storage, backups, and secrets at rest using managed keys. Define key access, rotation, recovery, and separation of duties. Encryption at rest does not prevent authorized service operators or a compromised application from accessing plaintext; disclose this accurately.
- Minimize collection and retention. Define retention defaults, deletion workflows that cover primary data and eventual backup expiry, user export, and account/session deletion. Avoid storing unnecessary personal data. Do not put user content, tokens, or secrets in logs, traces, analytics, or error reports; restrict and time-bound operational metadata.
- Treat submitted and imported text as untrusted data, not executable instructions. Preserve provenance. Do not fetch arbitrary URLs, access arbitrary files, or execute experiments. Bound payloads, ideas, history, and rounds; rate-limit and quota resource use; defend against injection, denial of service, and unsafe deserialization.
- Secure the service supply chain and operations: pinned/reviewed dependencies, automated vulnerability scanning, protected builds and deployment, secret management, patching, backups and restore tests, monitoring, incident response, and a documented breach-notification process. Establish independent security review and penetration testing before general availability, and repeat them periodically and after material changes.
- Use a flexible, versioned workflow through identify opportunities, select goals, and ideate with purpose. Allow documented skipping and revisiting rather than enforcing a rigid wizard.
- Return structured guidance with current stage, requested action, expected submission shape, constraints, and completion conditions, plus concise text for clients with limited structured-output support. Keep subjective evaluation in the host agent; the service validates structure and preserves evidence, not judgments of creativity.

## Initial MCP tools

- `start_session`: capture challenge, constraints, exclusions, success criteria, and exploration budget; return a session ID and first guidance.
- `get_next_step`: return read-only guidance, including the input schema, relevant context, and bounded exploration lenses.
- `submit_step`: record stage submissions; support explicit advance, skip, and revisit actions. Use an expected revision and idempotency key to prevent stale writes and duplicate retries.
- `get_session`: retrieve a compact summary or full export, including provenance and unresolved assumptions.

Use discriminated submission schemas, stable error codes, and accurate MCP tool annotations. Do not depend on optional MCP client capabilities. Require authenticated and authorized requests for all user data and mutation operations.

## User-facing security transparency and evidence

- Publish a plain-language privacy and security page before collecting user content. Explain what is collected, why, where it is processed/stored, subprocessors, retention/deletion timing including backup expiry, encryption boundaries, staff access, model/provider use (including whether content is sent to any model), telemetry, user controls, and incident contact/notification policy. Make no claim stronger than the technical controls and independent evidence support.
- Publish a versioned data-flow and threat-model summary, system boundary and trust assumptions, subprocessor list, retention schedule, security contact, and change history. Notify users of material changes; obtain renewed consent where required.
- Provide verifiable evidence: publish independent penetration-test summaries and remediation status; pursue an appropriate audited assurance program (for example SOC 2 Type II) when operational maturity and customer needs warrant it. Provide audit reports under NDA where appropriate. Publish signed release/deployment artifact provenance or SBOMs and a vulnerability disclosure process. Do not represent a self-attestation or cryptographic artifact as proof that runtime controls are effective.
- Give users inspectable controls: authenticated session listing/export/deletion, visible retention settings, and confirmation/status for deletion. Where feasible, provide a data access history for account actions. Keep evidence current and state its scope, date, exclusions, and limitations.

## State and safety

- Persist schema and method versions, revision, stable idea IDs, and compact change history. Mutations must be transactional. Use tenant-scoped records and enforce authorization at every read/write boundary.
- Make persistence explicit. Provide retention, deletion, and export controls before use with sensitive material; document deletion propagation and backup expiry.
- Keep user content out of diagnostic logs and third-party analytics. Keep operational access restricted, authenticated, time-limited, and audited.
- Proposed next actions remain proposals requiring separate authorization. Do not permit arbitrary network, filesystem, or execution capabilities.
- Surface budget exhaustion rather than looping indefinitely; return bounded responses.

## Phased plan

1. **Method and security contract:** define the three site-aligned stages, tool/submission schemas, challenge fixtures, and evaluation rubric. In parallel establish data classification, data-flow map, threat model, retention/deletion requirements, authentication model, tenant boundary, and user-facing disclosure/evidence plan. Walk through sessions manually before implementation.
2. **Secure service vertical slice:** implement the four tools, authenticated network transport, authorization and tenant isolation, persistent storage, revision-safe submissions, export and deletion controls, and one end-to-end workflow. Add automated protocol, authz, cross-tenant, privacy/logging, and security tests. Verify with at least two MCP clients.
3. **Security readiness and pilot:** conduct independent security review/penetration test and remediate high-risk findings before inviting pilot users. Publish privacy/security disclosures and evidence. Compare guided sessions against the same agent using a static ideation prompt with matched model and token budget; refine from traces without collecting unnecessary content.
4. **Production service and evidence-based expansion:** establish ongoing monitoring, incident response, backup/restore, patching, user support, and periodic independent review. Use pilot evidence to refine method. Add optional methods and branching when justified. Scale infrastructure and assurance commitments as actual demand and customer requirements justify them.

## Verification and success criteria

Test invalid submissions, stale revisions, retry idempotency, restart/resume, deletion, bounded responses, authentication failures, authorization boundaries, cross-tenant isolation, rate limits, and absence of sensitive content in logs. Verify deletion behavior across primary storage and documented backup lifecycle. Exercise backup restore and incident response. Independent testing must have documented scope and findings/remediation; publish a dated summary before general availability.

Pilot on approximately 20 varied challenges with repeated paired runs and blinded assessment. Score constraint adherence, distinctness of approaches, usefulness, and experiment actionability; track tokens, latency, and unrecovered tool errors separately. Provisional value gate: guided output is preferred in at least 60% of blinded comparisons at matched token budget, without worse constraint adherence. Report uncertainty; a small pilot is directional, not conclusive. Also target at least 90% of pilot sessions reaching an actionable experiment proposal without manual repair of tool calls. All deterministic state-integrity, authorization, and deletion tests must pass.

## Main risks

Workflow ceremony may increase tool calls and produce homogeneous ideas without improving outcomes. Compare against the simpler prompt baseline before expanding the method. A hosted service introduces data breach, insider access, misconfiguration, dependency, and availability risks; minimize retained data, verify controls independently, communicate limits plainly, and maintain incident response. No certification, encryption feature, or public statement should be presented as a guarantee of security.
