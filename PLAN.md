# Directed-Ideation MCP Plan

## Goal and assumptions

Build a hosted, agent-facing MCP service that guides purposeful exploration through explicit stages while the **calling agent owns all session context**. The MCP service provides method guidance; the agent manages the user's challenge, conversation, opportunity, goals, ideas, evidence, and session history. The service contract makes ideation-session content unrequestable and unretained: no supported operation requests or requires it, and tests must show it is rejected before processing and never logged or stored.

The three stages match the field-guide site: **identify opportunities**, **select goals**, and **ideate with purpose**. The agent interviews the user to hone in on one opportunity, synthesizes it for user confirmation, helps formulate/select/synthesize one goal for user confirmation, then develops multiple actionable ideas tied to that goal. Each idea includes a first action and observable evidence; users are encouraged to act on one at a time, though distinct parties may act in parallel.

The service is intended to be offered over the network. Its account, team, subscription/entitlement, and security metadata are distinct from session context and may be held by the service as necessary for access and operations. Autonomous execution of experiments is out of scope.

## Product and launch contract

### Initial launch and geography

- Begin with an invite-only pilot for users located in the United States. State eligibility clearly in signup and terms, do not market or intentionally provide the service outside the US, and use reasonable signup/location restrictions to enforce the boundary. These controls reduce risk but do not guarantee that foreign laws cannot apply.
- Keep account/service processing and hosting in the US for the pilot; inventory infrastructure and email subprocessors and disclose data flows. Obtain qualified legal review of pilot terms, privacy disclosures, eligibility controls, data flows, and applicable federal and state requirements before inviting users. Review each additional jurisdiction before enabling access or marketing there.
- Collect no sensitive session context because the service contract does not request or require it and rejects it before processing. Tell users that the calling agent and its provider manage session content and that their policies determine its handling.

### Accounts and teams

- Use email address and password authentication. Verify email ownership before account activation and password reset; users set their password after verification. Store only a modern, salted password hash. Keep the identity boundary extensible for later Google/Microsoft sign-in.
- A verified email identifies one user account. Users can belong to multiple teams. Team owners invite individual verified email addresses; domain-based self-join is not part of the initial design.
- Teams have owner and member roles. Both roles may use the service for their team. Removing a member ends access to that team's service features. Personal/private service accounts are out of scope initially, but the design should not preclude them later.
- The MCP service does not store team session lists, session ownership, team session content, or access history for sessions. If teams share session context, the calling agent/client and its own access controls manage that sharing. The MCP service cannot enforce visibility, editing, or deletion rules on context it never receives.

### Context-boundary contract

- No supported MCP operation requests or requires ideation-session context. Parameters, prompts, resources, and tools do not accept challenge descriptions, user answers, opportunity/goal/idea text, evaluations, evidence, conversation history, ideation-session identifiers, stage state, or other session-specific content.
- Standard MCP transport or protocol identifiers are permitted only as operational metadata and must not carry or link to ideation content.
- Unexpected arguments, unknown payload fields, and payloads that exceed size limits are rejected at ingress or application validation.
- Rejected payloads are not echoed into error responses and are not recorded in logs, traces, analytics, or error-reporting systems.
- Ingress and application request-body limits and logging controls are configured to drop oversized or malformed bodies without logging body content.
- The service returns reusable stage guidance, prompts, schemas, and method references without needing the user's session data. The calling agent applies that guidance to the context it already manages.
- The service does not call models, share session content with model providers, or use session data for analytics. No session data is available to use. A future private LLM would require a separate product/privacy decision and explicit user-facing disclosure; it must not silently change the context boundary.
- Account emails (verification, password reset, team invitations, and service notices) may use a disclosed email provider; send only the recipient address and necessary account/team metadata, never session content.
- The prior proposal to delete MCP-held sessions after 90 days and email their creators/owners is superseded: the MCP service has no sessions or session activity to retain, measure, or delete. Retention and deletion of session context are the responsibility of the calling agent/client provider and must be disclosed as such. The MCP service must provide account/team metadata deletion and document its own backup expiry.

## Architecture

- Build a model-independent hosted MCP server using an official MCP SDK, behind hardened TLS ingress. Do not expose unauthenticated service or rely on stdio as the user-facing hosted transport.
- Separate the MCP adapter, versioned method guidance, identity/authorization, account/team management, and minimal persistence. Store only account, team, membership, invitation, entitlement, and essential security/operational metadata. Schemas and tests must show no session table, ideation-session ID, stage progress, submission, context payload, or session-content backup in the MCP service.
- Authenticate users with the service email/password account system; verify email ownership and provide secure reset. Store only a modern salted password hash, rate-limit authentication/recovery, and avoid account-enumeration leaks. Keep identity extensible for later Google/Microsoft OIDC. Authorize each account/team operation against the authenticated principal; use short-lived, audience-restricted credentials, secure token validation, rotation/revocation, and no secrets in URLs.
- Enforce tenant isolation for account/team administration and entitlements. Least privilege, separation of administrative access, strong authentication, and audited approval for privileged operations. The service's team boundary controls access to service entitlements and team administration, not the calling agent's conversation/context.
- Encrypt transport with current TLS and encrypt account/team data, backups, and secrets at rest using managed keys. Define key access, rotation, recovery, and separation of duties. Disclose that encryption at rest does not prevent authorized service operators or a compromised application from accessing plaintext.
- Minimize collection and retention of account/team data. Define deletion and export controls for the data the service actually holds, plus backup expiry. Do not put passwords, tokens, or unnecessary personal data in logs, traces, analytics, or error reports. Disclose email delivery and infrastructure subprocessors; send no session content to them.
- Treat all protocol inputs as untrusted. Do not fetch arbitrary URLs, access arbitrary files, or execute experiments. Minimize accepted inputs, bound payloads and request rates, and defend against denial of service and unsafe deserialization.
- Secure the supply chain and operation: reviewed/pinned dependencies, vulnerability scanning, protected build/deployment, secret management, patching, monitoring, backup/restore for account data, incident response, and breach-notification process. Independent security review before general availability, repeated periodically and after material changes.
- Prefer established MCP primitives and common conventions. Expose concise, reusable stage guidance; do not require optional client/model capabilities. Provide a clear text representation where structured content is unsupported.

## Applying MCP design principles

Follow the principles at <https://modelcontextprotocol.io/community/design-principles>:

- **Convergence over choice:** choose one canonical way for a client to obtain each stage's guidance; avoid duplicate tools/prompts that do the same thing.
- **Composability over specificity:** build on MCP's established prompts, resources, and tools instead of adding custom protocol features. Prototype which primitives fit reusable stage guidance and account operations; retain only what demonstrates value.
- **Interoperability over optimization:** make the core flow work for clients with varying capabilities. Use portable text and ordinary schemas; optional structured output must degrade gracefully and no client-specific capability is required.
- **Stability over velocity:** keep the permanent protocol surface small. Version and evolve method content independently where possible; treat any tool/schema addition as a long-term compatibility commitment.
- **Capability over compensation:** do not add protocol structure merely to compensate for a presumed weakness of today's models. The host agent manages context and adapts general guidance to the user.
- **Demonstration over deliberation:** prototype the smallest useful flow in real MCP clients and gather usage evidence before expanding the surface or method.
- **Pragmatism over purity:** choose practical, interoperable MCP patterns and user experience over theoretical elegance; document meaningful tradeoffs.
- **Standardization over innovation:** use established MCP conventions. Keep experiments in method content or a prototype, not a bespoke protocol mechanism.

## MCP surface (to validate in prototype)

- **First prototype: explicit user request.** The user deliberately asks the calling agent to run directed ideation. Validate this entry path before adding agent-initiated discovery; the user's challenge remains client-side.
- **Use existing conversation context.** On explicit invocation, the calling agent synthesizes the relevant context it already holds, asks the user to confirm or revise that synthesis, and interviews only to fill gaps. If relevant context is absent, it asks for the challenge. All conversation context and synthesis remain client-side.
- **Complete method with optional supplementary guidance.** Explicit invocation supplies one complete method prompt covering all three stages; the calling agent can guide the full process without further MCP calls. Throughout the process, additional guidance is available on request, including challenging interview prompts and alternative approaches. Supplementary requests must use bounded, context-free selectors rather than sending the user's challenge, answers, or other ideation-session content. The exact supplementary MCP surface remains to be validated.
- **Supplementary retrieval policy.** The calling agent owns requests for additional MCP guidance. It uses the complete method and its own capabilities first, retrieving supplementary guidance when the user requests additional help that the agent cannot adequately provide, or when the user explicitly instructs it to fetch more guidance (expected to be unusual). Retrieval is not a routine step or an automatic response to the agent's judgment that more guidance might be useful.
- **Supplementary content scope.** Provide both deeper directed-ideation expertise (curated interview questions, diagnostic checks, and alternative techniques specific to the method) and a broader library of established creativity and problem-framing techniques. Prioritize directed-ideation-specific guidance; the calling agent selects and adapts guidance locally without transmitting session content.
- **First-prototype supplementary scope.** Include a small working sample of supplementary guidance alongside the complete method prompt, covering both deeper directed-ideation expertise and broader techniques. Validate retrieval and usefulness without building the full library; full-library expansion remains ToDo.
- **ToDo: agent-initiated discovery.** During an ordinary conversation, the calling agent recognizes when directed ideation could help and offers the method. This is a future feature, outside the first prototype.
- Provide stage-specific guidance in the fewest suitable standard MCP primitives. The initial hypothesis is MCP prompts for reusable stage instructions and/or resources for readable method references; select one canonical client path based on interoperability tests. Add a tool only when it performs a necessary server-side operation that cannot be composed from those primitives.
- Account/team administration and authentication are service concerns, but must not turn session content into server-side state. Define how authorized clients invoke these capabilities using standard MCP patterns.
- Do not implement `start_session`, `submit_step`, or `get_session` as session-persistence tools: the server neither starts nor stores user sessions. Any stage/cursor state remains with the calling agent.
- Return guidance for the three stages, expected user/agent interaction, and output shape. The calling agent is responsible for interviews, synthesis, subjective evaluation, user confirmation, storing provenance, and deciding when to advance/revisit.
- Do not depend on optional MCP client capabilities. Before fixing the surface, test the guidance prototype with at least two MCP clients and simplify to one documented path.

## User-facing security transparency and evidence

- Publish a plain-language privacy/security page before account registration. Clearly state the context boundary: the service contract does not request or retain ideation-session content, and any such content is rejected before processing or logging. Explain what account/team data the service does collect, why, where it is processed/stored, subprocessors, retention/deletion including backup expiry, encryption boundaries, staff access, email use, telemetry, user controls, and incident contact/notification policy.
- Explicitly explain that the MCP service cannot control the calling agent/client provider's storage, model use, retention, or sharing of context. Users must consult that provider's policies and controls. Avoid implying that keeping context out of this service makes the overall workflow private or secure end-to-end.
- Publish a versioned data-flow and threat-model summary, system boundary/trust assumptions, subprocessor list, retention schedule, security contact, and change history. Notify users of material changes; obtain renewed consent where required.
- Provide verifiable evidence: publish independent penetration-test summaries and remediation status; consider an appropriate audited assurance program (such as SOC 2 Type II) when maturity/customer needs warrant it. Provide audit reports under NDA where appropriate. Publish signed release provenance or SBOMs and a vulnerability disclosure process. State scope, date, exclusions, and limitations; do not imply self-attestation or signed artifacts prove runtime controls.
- Give users inspectable controls for account/team data held by this service: account data access/export/deletion, team membership/invitation management, and clear completion status. These controls do not export or delete agent-held session context.

## State and safety

- Persist only the account/team/service metadata necessary for operation. Use transactional changes and enforce tenant authorization at every read/write boundary. Do not persist ideation-session context, stage progression, ideation-session IDs, or session history; operational identifiers required by the protocol must not link to ideation content.
- Make the data boundary explicit in protocol schemas, server logs, telemetry, error handling, backups, subprocessors, and tests. Reject or avoid free-text session input rather than promising not to retain it after accepting it.
- Keep operational access restricted, authenticated, time-limited, and audited. Keep user content out of logs and analytics; the service should not receive user content in the first place.
- Proposed actions remain proposals requiring separate authorization. No arbitrary network, filesystem, or execution capabilities.

## Phased plan

1. **Context-boundary and method contract:** define the three stages and host-agent-owned interaction, account/team data boundary, minimal MCP surface, privacy/security disclosures, US-only pilot scope, threat model, and data retention for account/team records. Prototype the standard MCP primitives with at least two clients before committing to the surface. Walk through sample sessions while keeping all sample context on the client side.
2. **Secure hosted service slice:** implement email verification/password authentication, team invitations/roles, minimal account/team persistence, authorization, network transport, and the smallest proven guidance surface. Add automated tests proving session content is neither accepted nor logged/stored, plus protocol interoperability, tenant isolation, and account lifecycle tests.
3. **Security readiness and invite-only US pilot:** obtain legal review before inviting users; conduct independent security review and remediate high-risk findings; publish privacy/security disclosures. Use US hosting/processing and reasonable US-only eligibility controls. Pilot with invited US users only; do not market or intentionally serve other jurisdictions. Evaluate method usefulness without collecting user session content centrally.
4. **Production and evidence-based expansion:** establish monitoring, incident response, backup/restore for permitted account data, patching, support, and periodic independent review. Use evidence to refine the method. Review legal, privacy, and operational requirements before adding jurisdictions, context-processing features, or a private model.

## Verification and success criteria

Test authentication/recovery, authorization boundaries, cross-team isolation, invitation lifecycle, rate limits, bounded guidance, and account-data export/deletion. Add negative tests that send representative session context and verify it is rejected or not accepted, and ensure no request bodies, sensitive values, or rejected payloads enter logs, traces, analytics, or email. Verify that backups contain only permitted account/team metadata and test documented deletion/expiry. Exercise restore and incident response. Test the guidance surface across at least two MCP clients, including a limited-capability client.

Pilot method usefulness with approximately 20 varied challenges and repeated paired runs; the calling agent retains context and supplies only anonymized or aggregated outcomes if needed. Score constraint adherence, distinctness, usefulness, and actionability; track tokens, latency, and unrecovered tool errors separately. Report uncertainty; a small pilot is directional, not conclusive. Do not collect raw transcripts for evaluation without a separate explicit decision and privacy review.

## Main risks

The calling agent's provider still controls context handling; users may mistakenly infer that this MCP service's boundary protects data end-to-end. Communicate the division of responsibility clearly. Guidance may vary across host agents or be underused; test interoperability and actual utility rather than compensating with a complex bespoke protocol. A hosted account service still has breach, insider-access, misconfiguration, dependency, and availability risks; minimize retained metadata, independently verify controls, and communicate limitations. No certification, encryption feature, or public statement guarantees security.
