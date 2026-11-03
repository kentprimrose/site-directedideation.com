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


def test_http_auth_each_request(monkeypatch):
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
