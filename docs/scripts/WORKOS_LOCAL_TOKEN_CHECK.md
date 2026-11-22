# Local-only WorkOS live token check

This is a separate Python public OAuth client, **not Pi**, a proxy, or a deployment.
It does not activate anything remotely. It sends the resulting bearer only to
`127.0.0.1` at the configured local staging server port with the fixed staging
Host header. It does not connect to the public staging origin. Python's HTTPS
client connects directly to the configured AuthKit issuer, not via proxy settings;
it refuses endpoint redirects and requires exact issuer and endpoint metadata.
The browser visits the authorization endpoint and carries out the provider's
normal login redirects. Use a trusted browser and disposable staging identity.
The authorization URL contains a public client ID, PKCE challenge and random
state, not a token, authorization code, or verifier. Browser history, extensions,
OS diagnostics and the provider are outside this script's control.

1. Start the staging service locally, bound **only** to `127.0.0.1`; follow
   `docs/staging_mcp/README.md`, including the disposable issuer, allowlist and exact
   resource indicator. Avoid server/framework logging of credentials. Do not
   start a public listener, tunnel or proxy for this check.
2. Enable WorkOS CIMD. The client ID is Pi's published native-client metadata
   `https://pi.dev/oauth/client.json`, which lists `http://127.0.0.1/callback`;
   RFC 8252 section 7.3 permits an ephemeral port for native loopback redirects.
   This checks WorkOS metadata for CIMD support, public clients and S256; it fails
   closed if not advertised or if documented endpoints differ.
3. In a local terminal, set the exact HTTPS AuthKit issuer (no path or trailing
   slash) and, optionally, the local port (default 8765):

   ```sh
   export WORKOS_STAGING_ISSUER='https://YOUR_AUTHKIT_DOMAIN'
   export WORKOS_LOCAL_STAGING_PORT=8765
   # Optional: expected subject from the local server's allowlist; do not share it.
   export WORKOS_LOCAL_EXPECTED_SUBJECT='YOUR_DISPOSABLE_SUBJECT'
   .venv/bin/python scripts/workos_local_token_check.py
   ```

   The issuer must be a trusted WorkOS staging issuer: configuring an attacker
   origin gives that origin the OAuth exchange. Sign in interactively when the
   browser opens. The script prints a local HTTP status or a generic failure and
   boolean-only, **unverified** token diagnostics. These are not authorization
   evidence: no signature is checked. `jwt_payload_format` means only that the
   token has three nonempty base64url-shaped segments and a decodable JSON object
   payload, not that the header or signature is valid. Expiration means a finite
   numeric `exp` is in the future according to the local clock. Subject matching
   compares only with the optional expected subject, not the server's allowlist;
   when unset, `subject_configured` and `subject_matches` are both false. Opaque
   or malformed tokens produce false claim checks, not a validation decision.
   A 200 indicates only that the local initialize request received HTTP 200; it
   is not a full MCP interoperability test. To check a second account, run it
   again and manually switch accounts in the browser. Provider/browser sessions
   may otherwise reuse the first login.

To optionally test a provider-issued ID token, set `WORKOS_LOCAL_CHECK_ID_TOKEN=1`
for the invocation. This requests the `openid` scope and sends any returned ID
token only to the same fixed loopback staging backend. A 401 or 403 reports
`ID token rejected: True`; HTTP 200 reports `False`. Other statuses, or a missing
or malformed ID token, are inconclusive and exit nonzero. The check exits zero
only when the access-token request returns 200 and the ID token receives 401 or
403. These outcomes describe only this particular token, account, request and
local configuration; they do not establish universal provider or server token
semantics. The default invocation does not request `openid` or test an ID token.

No token is intentionally written to disk, printed, passed as a process argument,
or sent to the public staging service. Code, verifier and token are held in
memory; sockets close on completion and the callback listener times out. This
is not secure isolation from other local users/processes, administrators,
malware, debuggers, core dumps, browser history, or server-side logging. Use a
trusted machine, disable core dumps, and inspect server logging before testing.
Interruptions and browser processes are governed by the OS. There is no refresh
or token revocation. A 401/403 or generic failure requires local investigation
without sharing secrets. Actual tenant support and login have not been verified;
in particular strict CIMD advertisement/loopback handling may block this check.

Offline tests: `.venv/bin/python -m pytest -q tests/test_workos_local_token_check.py`.
Sources: https://pi.dev/oauth/client.json, https://www.rfc-editor.org/rfc/rfc8252#section-7.3,
https://workos.com/docs/authkit/mcp .

Set `WORKOS_LOCAL_CHECK_GUIDANCE=1` to additionally initialize an authenticated
MCP session through the same fixed loopback backend, list its exact tools, and
call `get_interview_guidance` with a fixed valid stage. The output is compared
in memory with the local canonical implementation; only HTTP statuses and
boolean comparisons are reported. A mismatch or protocol failure exits nonzero.
This option can be combined with the ID-token check. It does not contact the
public staging service; the local server must run the matching code version.
