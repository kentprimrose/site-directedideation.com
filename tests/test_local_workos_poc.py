"""Local-only OAuth POC tests; no WorkOS credentials or network required."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from starlette.testclient import TestClient

from local_workos_poc.server import RESOURCE, ExpiringJWTVerifier, create_app

ISSUER = "https://auth.example.com"
HEADERS = {"host": "127.0.0.1:8765", "accept": "application/json, text/event-stream"}
REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def test_discovery_and_token_enforcement():
    """Exercise discovery and bearer enforcement with locally generated keys."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    verifier = ExpiringJWTVerifier(public_key=pub, issuer=ISSUER, audience=RESOURCE)
    with TestClient(create_app(ISSUER, verifier)) as client:
        response = client.get(
            "/.well-known/oauth-protected-resource/mcp", headers=HEADERS
        )
        assert response.json()["resource"] == RESOURCE
        assert response.json()["authorization_servers"] == [ISSUER + "/"]
        response = client.post("/mcp", headers=HEADERS, json=REQUEST)
        assert response.status_code == 401
        assert "resource_metadata=" in response.headers["www-authenticate"]
        claims = {
            "iss": ISSUER,
            "aud": RESOURCE,
            "exp": int(time.time()) + 300,
            "sub": "test",
        }

        def request(payload, signing_key=key):
            token = jwt.encode(payload, signing_key, algorithm="RS256")
            return client.post(
                "/mcp",
                headers={**HEADERS, "authorization": "Bearer " + token},
                json=REQUEST,
            )

        assert request(claims).status_code == 200
        token = jwt.encode(claims, key, algorithm="RS256")
        tool_response = client.post(
            "/mcp",
            headers={**HEADERS, "authorization": "Bearer " + token},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "local_ping", "arguments": {}},
            },
        )
        assert tool_response.status_code == 200
        assert "local OAuth proof of concept OK" in tool_response.text
        assert request(claims, other).status_code == 401
        assert request({**claims, "iss": "https://wrong.example"}).status_code == 401
        assert request({**claims, "aud": "wrong"}).status_code == 401
        assert request({**claims, "exp": int(time.time()) - 1}).status_code == 401
        assert (
            request({k: v for k, v in claims.items() if k != "exp"}).status_code == 401
        )
        assert (
            client.get(
                "/.well-known/oauth-protected-resource/mcp",
                headers={"host": "evil.example"},
            ).status_code
            == 400
        )


@pytest.mark.parametrize(
    "issuer",
    [
        "",
        "http://example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://user@example.com",
    ],
)
def test_invalid_configuration(issuer):
    """Reject invalid issuer configuration at startup."""
    with pytest.raises(ValueError):
        create_app(issuer)
