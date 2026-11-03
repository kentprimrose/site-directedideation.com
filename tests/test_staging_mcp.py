"""Offline staging resource-server boundary tests."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from starlette.testclient import TestClient

from staging_mcp.server import RESOURCE, StagingVerifier, create_app

ISSUER = "https://auth.example.com"
HEADERS = {
    "host": "mcp-staging.directedideation.com",
    "accept": "application/json, text/event-stream",
}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def test_http_auth_each_request(monkeypatch, caplog):
    """Test signatures, identity and claims at the real HTTP boundary."""
    monkeypatch.setenv("WORKOS_STAGING_ISSUER", ISSUER)
    monkeypatch.setenv("WORKOS_STAGING_ALLOWED_SUBJECTS", "user_ABC")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )

    async def get_key(self, token):
        return public

    monkeypatch.setattr(StagingVerifier, "_get_verification_key", get_key)
    claims = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "exp": int(time.time()) + 300,
        "sub": "user_ABC",
    }
    with TestClient(create_app()) as client:

        def request(payload, signing_key=key):
            token = jwt.encode(payload, signing_key, algorithm="RS256")
            return client.post(
                "/mcp",
                headers={**HEADERS, "authorization": "Bearer " + token},
                json=INIT,
            )

        assert request(claims).status_code == 200
        token = jwt.encode(claims, key, algorithm="RS256")
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        }
        assert (
            "pong"
            in client.post(
                "/mcp",
                headers={**HEADERS, "authorization": "Bearer " + token},
                json=call,
            ).text
        )
        assert client.post("/mcp", headers=HEADERS, json=call).status_code == 401
        assert request({**claims, "sub": "user_OTHER"}).status_code == 401
        assert request(claims, other).status_code == 401
        for bad in (
            {"iss": "https://wrong.example"},
            {"aud": "client_id"},
            {"aud": [RESOURCE]},
            {"exp": 1},
            {"exp": True},
            {"exp": "9999999999"},
            {"exp": None},
            {"nbf": int(time.time()) + 300},
            {"nbf": True},
            {"nbf": "0"},
            {"nbf": None},
            {"sub": ""},
            {"sub": 123},
        ):
            assert request({**claims, **bad}).status_code == 401
        # Exercise signed numeric edge cases through the actual auth middleware.
        # Both positive and negative values must fail closed, even where a huge
        # negative nbf would otherwise look like a valid time in the past.
        for name in ("exp", "nbf"):
            for value in (10**309, -(10**309), float("inf"), float("-inf")):
                token = jwt.encode({**claims, name: value}, key, algorithm="RS256")
                response = client.post(
                    "/mcp",
                    headers={**HEADERS, "authorization": "Bearer " + token},
                    json=INIT,
                )
                assert response.status_code == 401
                assert token not in caplog.text
                assert token not in response.text
        for missing in ("exp", "aud", "sub"):
            assert (
                request({k: v for k, v in claims.items() if k != missing}).status_code
                == 401
            )
        assert (
            client.post(
                "/mcp",
                headers={**HEADERS, "authorization": "Bearer " + "a" * 16385},
                json=INIT,
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/mcp", headers={**HEADERS, "host": "evil.example"}, json=INIT
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/mcp",
                headers={**HEADERS, "authorization": "Bearer invalid"},
                json=INIT,
            ).status_code
            == 401
        )


def test_configuration_fails_closed(monkeypatch):
    """Missing or malformed issuer and subject configuration cannot start."""
    monkeypatch.delenv("WORKOS_STAGING_ISSUER", raising=False)
    monkeypatch.delenv("WORKOS_STAGING_ALLOWED_SUBJECTS", raising=False)
    with pytest.raises(ValueError):
        create_app()
    monkeypatch.setenv("WORKOS_STAGING_ALLOWED_SUBJECTS", "user_ABC")
    for issuer in (
        " https://auth.example.com",
        "https://auth.example.com\n",
        "https://auth.example.com:",
        "https://AUTH.example.com",
        "HTTPS://auth.example.com",
        "https://auth .example.com",
        "https://auth.example.com/",
        "https://auth.example.com:443",
        "https://user@auth.example.com",
        "https://auth.example.com?",
        "https://-auth.example.com",
        "https://auth.example.com.",
    ):
        monkeypatch.setenv("WORKOS_STAGING_ISSUER", issuer)
        with pytest.raises(ValueError):
            create_app()
    monkeypatch.setenv("WORKOS_STAGING_ISSUER", ISSUER)
    for value in ("", "user_ABC,", "user_ABC, user_DEF", "*"):
        monkeypatch.setenv("WORKOS_STAGING_ALLOWED_SUBJECTS", value)
        with pytest.raises(ValueError):
            create_app()


def test_body_limit_asgi(caplog):
    """Enforce declared and actual sizes before dispatch, without logging bodies."""
    import asyncio

    from staging_mcp.server import MAX_MCP_BODY_BYTES, MCPBodyLimitMiddleware

    async def exercise(headers, chunks, path="/mcp"):
        sent = []
        dispatched = []
        messages = iter(chunks)

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        async def app(scope, receive, send):
            dispatched.append(await receive())
            await send({"type": "http.response.start", "status": 204, "headers": []})

        await MCPBodyLimitMiddleware(app)(
            {"type": "http", "path": path, "headers": headers}, receive, send
        )
        return sent, dispatched

    def request(body, more=False):
        return {"type": "http.request", "body": body, "more_body": more}

    async def check():
        secret = b"sensitive-request-payload"
        for headers, chunks, status in (
            ([(b"content-length", b"65537")], [], 413),
            ([(b"content-length", b"-1")], [], 400),
            ([(b"content-length", b"1, 1")], [], 400),
            ([(b"content-length", b"1"), (b"content-length", b"1")], [], 400),
            ([(b"content-length", b"2")], [request(secret)], 400),
            ([], [request(secret, True), request(b"x" * MAX_MCP_BODY_BYTES)], 413),
            (
                [(b"content-length", b"1")],
                [request(secret, True), request(b"x" * MAX_MCP_BODY_BYTES)],
                413,
            ),
        ):
            sent, dispatched = await exercise(headers, chunks, "/mcp/")
            assert sent[0]["status"] == status
            assert not dispatched
            assert secret not in repr(sent).encode()
        sent, dispatched = await exercise([], [request(b"a" * MAX_MCP_BODY_BYTES)])
        assert sent[0]["status"] == 204
        assert dispatched[0]["body"] == b"a" * MAX_MCP_BODY_BYTES
        sent, dispatched = await exercise([], [{"type": "http.disconnect"}])
        assert not sent and not dispatched
        # Non-MCP routes are not consumed or size checked by the middleware.
        sent, dispatched = await exercise(
            [(b"content-length", b"bad")],
            [request(secret)],
            "/.well-known/oauth-protected-resource",
        )
        assert sent[0]["status"] == 204 and dispatched[0]["body"] == secret

    asyncio.run(check())
    assert "sensitive-request-payload" not in caplog.text


def test_body_limit_installed_on_app(monkeypatch):
    """Verify the real app protects MCP but not authorization metadata."""
    monkeypatch.setenv("WORKOS_STAGING_ISSUER", ISSUER)
    monkeypatch.setenv("WORKOS_STAGING_ALLOWED_SUBJECTS", "user_ABC")
    with TestClient(create_app()) as client:
        assert (
            client.post("/mcp", headers=HEADERS, content=b"x" * 65537).status_code
            == 413
        )
        assert (
            client.post(
                "/mcp", headers={**HEADERS, "content-length": "bad"}, content=b"secret"
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/.well-known/oauth-protected-resource/mcp", headers=HEADERS
            ).status_code
            == 200
        )
