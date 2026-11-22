#!/usr/bin/env python3
"""Interactive, in-memory-only WorkOS token check against a local staging server."""

import base64
import hashlib
import http.client
import json
import math
import os
import re
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import cast

CLIENT_ID = "https://pi.dev/oauth/client.json"
RESOURCE = "https://mcp-staging.directedideation.com/mcp"
STAGING_HOST = "mcp-staging.directedideation.com"
MAX_RESPONSE = 65536


def issuer_from_env():
    """Read and validate the configured AuthKit issuer."""
    issuer = os.environ.get("WORKOS_STAGING_ISSUER", "")
    # An operator-provided, exact AuthKit origin; never use the staging origin.
    match = re.fullmatch(r"https://([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)", issuer)
    if not match or ".." in issuer or match.group(1) == STAGING_HOST:
        raise ValueError("invalid issuer")
    return issuer


def port_from_env():
    """Read and validate the local staging port."""
    value = os.environ.get("WORKOS_LOCAL_STAGING_PORT", "8765")
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
        raise ValueError("invalid port")
    return int(value)


def request_https(issuer, path, body=None):
    """Direct HTTPS only; never follow redirects or use proxy environment variables."""
    host = urllib.parse.urlsplit(issuer).hostname
    conn = http.client.HTTPSConnection(host, timeout=15)
    try:
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(
            "POST" if body is not None else "GET", path, body=body, headers=headers
        )
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("HTTPS request rejected")
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("response too large")
        return json.loads(data)
    finally:
        conn.close()


def check_metadata(issuer, metadata):
    """Reject metadata that does not match the expected OAuth configuration."""
    if not isinstance(metadata, dict) or metadata.get("issuer") != issuer:
        raise ValueError("issuer mismatch")
    if (
        metadata.get("authorization_endpoint") != issuer + "/oauth2/authorize"
        or metadata.get("token_endpoint") != issuer + "/oauth2/token"
    ):
        raise ValueError("endpoint mismatch")
    if (
        not isinstance(metadata.get("code_challenge_methods_supported"), list)
        or not isinstance(metadata.get("token_endpoint_auth_methods_supported"), list)
        or "S256" not in metadata["code_challenge_methods_supported"]
        or "none" not in metadata["token_endpoint_auth_methods_supported"]
    ):
        raise ValueError("unsupported OAuth configuration")
    if metadata.get("client_id_metadata_document_supported") is not True:
        raise ValueError("CIMD not advertised")


def authorization_url(issuer, redirect, state, challenge, openid=False):
    """Build the public authorization request URL."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    }
    if openid:
        params["scope"] = "openid"
    return issuer + "/oauth2/authorize?" + urllib.parse.urlencode(params)


def receive_code(state, server, deadline):
    """Wait for a valid callback until the deadline."""
    server.expected_state = state
    server.code = None
    while server.code is None and time.monotonic() < deadline:
        server.timeout = min(1, max(0.01, deadline - time.monotonic()))
        server.handle_request()
    if server.code is None:
        raise ValueError("callback timed out")
    return server.code


class LoopbackServer(HTTPServer):
    """Loopback callback server that suppresses request errors."""

    expected_state: str
    code: str | None

    def handle_error(self, request, client_address):
        """Suppress callback server error output."""
        pass


class Callback(BaseHTTPRequestHandler):
    """Validate and receive an OAuth loopback callback."""

    def setup(self):
        """Set a timeout on the callback connection."""
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, format, *args):
        """Suppress callback request logging."""
        pass

    def do_GET(self):
        """Accept only a valid callback with the expected state."""
        server = cast(LoopbackServer, self.server)
        query = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(query.query, keep_blank_values=True)
        valid = (
            self.headers.get_all("Host") == [f"127.0.0.1:{server.server_port}"]
            and query.scheme == ""
            and query.netloc == ""
            and query.path == "/callback"
            and params.get("state") == [server.expected_state]
            and len(params.get("code", [])) == 1
            and bool(params["code"][0])
            and "error" not in params
        )
        if valid:
            server.code = params["code"][0]
        self.send_response(200 if valid else 400)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(
            b"You may close this window." if valid else b"Invalid callback."
        )


def token_diagnostics(token, issuer, expected_subject):
    """Return unverified, diagnostic-only claim comparisons; never return claims."""
    result = {
        "jwt_payload_format": False,
        "issuer_matches": False,
        "audience_matches": False,
        "subject_configured": bool(expected_subject),
        "subject_matches": False,
        "expiration_in_future": False,
    }
    try:
        parts = token.split(".")
        if len(parts) != 3 or any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts
        ):
            return result
        payload = base64.b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True
        )
        claims = json.loads(payload)
        if not isinstance(claims, dict):
            return result
        result["jwt_payload_format"] = True
        result["issuer_matches"] = claims.get("iss") == issuer
        audience = claims.get("aud")
        result["audience_matches"] = audience == RESOURCE or (
            isinstance(audience, list)
            and all(isinstance(item, str) for item in audience)
            and RESOURCE in audience
        )
        result["subject_matches"] = bool(expected_subject) and (
            claims.get("sub") == expected_subject
        )
        expiration = claims.get("exp")
        result["expiration_in_future"] = (
            type(expiration) in (int, float)
            and math.isfinite(expiration)
            and time.time() < expiration
        )
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        pass
    return result


def check_local(token, port):
    """Send the bearer token to the local staging server."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        body = (
            b'{"jsonrpc":"2.0","id":1,"method":"initialize",'
            b'"params":{"protocolVersion":"2025-03-26","capabilities":{},'
            b'"clientInfo":{"name":"local-check","version":"1"}}}'
        )
        conn.request(
            "POST",
            "/mcp",
            body=body,
            headers={
                "Host": STAGING_HOST,
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        response = conn.getresponse()
        return response.status
    finally:
        conn.close()


GUIDANCE_TOOLS = {
    "ping",
    "get_directed_ideation_method",
    "get_interview_guidance",
    "get_diagnostic_checks",
    "get_alternative_techniques",
}
GUIDANCE_STAGE = "frame"
GUIDANCE_PROTOCOL_VERSION = "2025-03-26"


def read_sse_response(response, request_id):
    """Read bounded SSE events until the response for this request arrives."""
    remaining = MAX_RESPONSE
    data_lines = []
    while remaining:
        line = response.readline(remaining + 1)
        if len(line) > remaining:
            raise ValueError("response too large")
        remaining -= len(line)
        if not line:
            break
        line = line.rstrip(b"\r\n")
        if not line:
            if data_lines:
                try:
                    event = json.loads(b"\n".join(data_lines))
                except (ValueError, UnicodeError, RecursionError):
                    raise ValueError("invalid SSE response") from None
                data_lines = []
                if (
                    isinstance(event, dict)
                    and type(event.get("id")) is type(request_id)
                    and event.get("id") == request_id
                ):
                    return event
        elif line.startswith(b"data:"):
            value = line[5:]
            data_lines.append(value[1:] if value.startswith(b" ") else value)
    raise ValueError("missing response")


def check_guidance(token, port):  # noqa: C901
    """Exercise MCP on loopback, comparing responses without exposing their contents."""
    from site_directedideation_com.mcp import get_interview_guidance

    session = None
    protocol_version = None

    def request(method, params, request_id):  # noqa: C901
        nonlocal session
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        headers = {
            "Host": STAGING_HOST,
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session is not None:
            headers["Mcp-Session-Id"] = session
        if protocol_version is not None:
            headers["MCP-Protocol-Version"] = protocol_version
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        try:
            conn.request("POST", "/mcp", body=json.dumps(message), headers=headers)
            response = conn.getresponse()
            print(f"Guidance {method} HTTP status: {response.status}")
            if response.status not in (200, 202):
                raise ValueError("request rejected")
            received_session = response.getheader("Mcp-Session-Id")
            if received_session:
                if not valid_token(received_session) or (
                    session and session != received_session
                ):
                    raise ValueError("invalid session")
                session = received_session
            if request_id is None:
                if response.status != 202:
                    raise ValueError("notification rejected")
                return None
            if response.status != 200:
                raise ValueError("missing response")
            content_type = (
                (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
            )
            if content_type == "text/event-stream":
                result = read_sse_response(response, request_id)
            elif content_type == "application/json":
                data = response.read(MAX_RESPONSE + 1)
                if len(data) > MAX_RESPONSE:
                    raise ValueError("response too large")
                result = json.loads(data)
            else:
                raise ValueError("invalid content type")
            if (
                not isinstance(result, dict)
                or result.get("jsonrpc") != "2.0"
                or result.get("id") != request_id
                or "error" in result
                or not isinstance(result.get("result"), dict)
            ):
                raise ValueError("invalid RPC response")
            return result["result"]
        finally:
            conn.close()

    try:
        initialized = request(
            "initialize",
            {
                "protocolVersion": GUIDANCE_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "local-check", "version": "1"},
            },
            1,
        )
        if initialized.get("protocolVersion") != GUIDANCE_PROTOCOL_VERSION:
            raise ValueError("unsupported protocol version")
        protocol_version = GUIDANCE_PROTOCOL_VERSION
        request("notifications/initialized", {}, None)
        listing = request("tools/list", {}, 2)
        tools = listing.get("tools")
        names = (
            [item.get("name") for item in tools if isinstance(item, dict)]
            if isinstance(tools, list)
            else []
        )
        names_match = (
            isinstance(tools, list)
            and len(tools) == len(GUIDANCE_TOOLS)
            and len(names) == len(GUIDANCE_TOOLS)
            and all(isinstance(name, str) for name in names)
            and set(names) == GUIDANCE_TOOLS
            and not listing.get("nextCursor")
        )
        print(f"Guidance tool names match: {names_match}")
        result = request(
            "tools/call",
            {"name": "get_interview_guidance", "arguments": {"stage": GUIDANCE_STAGE}},
            3,
        )
        content = result.get("content")
        matches = (
            result.get("isError", False) is False
            and isinstance(content, list)
            and len(content) == 1
            and isinstance(content[0], dict)
            and content[0].get("type") == "text"
            and content[0].get("text") == get_interview_guidance(GUIDANCE_STAGE)
        )
        print(f"Guidance output matches: {matches}")
        return names_match and matches
    except (
        ValueError,
        OSError,
        http.client.HTTPException,
        UnicodeError,
        RecursionError,
    ):
        print("Guidance check succeeded: False")
        return False


def valid_token(token):
    """Ensure a token can safely be used as a bearer header."""
    return (
        isinstance(token, str)
        and bool(token)
        and token.isascii()
        and all(32 < ord(c) < 127 for c in token)
    )


def main():
    """Run the interactive token check and return an exit status."""
    try:
        issuer, port = issuer_from_env(), port_from_env()
        openid = os.environ.get("WORKOS_LOCAL_CHECK_ID_TOKEN") == "1"
        check_metadata(
            issuer, request_https(issuer, "/.well-known/oauth-authorization-server")
        )
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        state = secrets.token_urlsafe(32)
        with LoopbackServer(("127.0.0.1", 0), Callback) as server:
            redirect = f"http://127.0.0.1:{server.server_port}/callback"
            url = authorization_url(issuer, redirect, state, challenge, openid)
            if not webbrowser.open(url):
                raise ValueError("browser unavailable")
            code = receive_code(state, server, time.monotonic() + 180)
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "redirect_uri": redirect,
                "code_verifier": verifier,
                "resource": RESOURCE,
            }
        )
        response = request_https(issuer, "/oauth2/token", body)
        token = response.get("access_token") if isinstance(response, dict) else None
        if not valid_token(token):
            raise ValueError("invalid token")
        diagnostics = token_diagnostics(
            token, issuer, os.environ.get("WORKOS_LOCAL_EXPECTED_SUBJECT", "")
        )
        print("Unverified token diagnostics (not authorization evidence):")
        for name, value in diagnostics.items():
            print(f"  {name}: {value}")
        status = check_local(token, port)
        print(f"Local staging HTTP status: {status}")
        guidance_ok = True
        if os.environ.get("WORKOS_LOCAL_CHECK_GUIDANCE") == "1":
            guidance_ok = check_guidance(token, port) if status == 200 else False
            print(f"Guidance check succeeded: {guidance_ok}")
        if openid:
            id_token = response.get("id_token")
            if not valid_token(id_token):
                print("ID token check: inconclusive (missing or invalid ID token).")
                return 1
            id_status = check_local(id_token, port)
            print(f"Local staging ID token HTTP status: {id_status}")
            if id_status in (401, 403):
                print("ID token rejected: True")
            elif id_status == 200:
                print("ID token rejected: False")
            else:
                print("ID token check: inconclusive (unexpected HTTP status).")
            return 0 if status == 200 and guidance_ok and id_status in (401, 403) else 1
        return 0 if status == 200 and guidance_ok else 1
    except (
        ValueError,
        OSError,
        http.client.HTTPException,
        TimeoutError,
        json.JSONDecodeError,
    ):
        print("Local token check failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
