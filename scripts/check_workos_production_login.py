#!/usr/bin/env python3
"""Privately check a production WorkOS login without contacting the MCP server."""

import base64
import getpass
import hashlib
import re
import secrets
import sys
import time
import urllib.parse
import webbrowser

import jwt
import workos_local_token_check as oauth

RESOURCE = "https://mcp.directedideation.com/mcp"
stage = "input"


def main():
    """Run a browser OAuth flow and verify the returned access token in memory."""
    global stage
    issuer = getpass.getpass("Production AuthKit origin (hidden): ").strip()
    subject = getpass.getpass("Your production user_ ID (hidden): ").strip()
    stage = "AuthKit origin format"
    if not re.fullmatch(
        r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.authkit\.app", issuer
    ):
        raise ValueError("Expected the default WorkOS AuthKit HTTPS origin")
    stage = "user ID format"
    if not re.fullmatch(r"user_[A-Za-z0-9]+", subject):
        raise ValueError("Invalid user ID")
    stage = "authorization metadata request"
    metadata = oauth.request_https(issuer, "/.well-known/oauth-authorization-server")
    stage = "authorization metadata validation"
    oauth.check_metadata(issuer, metadata)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    state = secrets.token_urlsafe(32)
    stage = "browser sign-in and callback"
    with oauth.LoopbackServer(("127.0.0.1", 0), oauth.Callback) as server:
        redirect = f"http://127.0.0.1:{server.server_port}/callback"
        template = urllib.parse.urlsplit(
            oauth.authorization_url(issuer, redirect, state, challenge)
        )
        parameters = dict(urllib.parse.parse_qsl(template.query))
        parameters["resource"] = RESOURCE
        url = urllib.parse.urlunsplit(
            template._replace(query=urllib.parse.urlencode(parameters))
        )
        if not webbrowser.open(url):
            raise ValueError("Browser unavailable")
        print("Complete the WorkOS sign-in and consent in your browser.")
        code = oauth.receive_code(state, server, time.monotonic() + 180)
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": oauth.CLIENT_ID,
            "code": code,
            "redirect_uri": redirect,
            "code_verifier": verifier,
            "resource": RESOURCE,
        }
    )
    stage = "token exchange"
    response = oauth.request_https(issuer, "/oauth2/token", body)
    token = response.get("access_token") if isinstance(response, dict) else None
    if not isinstance(token, str) or not oauth.valid_token(token):
        raise ValueError("Invalid access token")
    stage = "token verification"
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Unexpected token algorithm or key")
    jwks = oauth.request_https(issuer, "/oauth2/jwks")
    keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
    matches = [
        key for key in keys if isinstance(key, dict) and key.get("kid") == header["kid"]
    ]
    if len(matches) != 1:
        raise ValueError("Signing key not found uniquely")
    key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256").key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=RESOURCE,
        options={"require": ["exp", "iss", "aud", "sub"]},
    )
    if claims.get("sub") != subject or claims.get("sub_profile") == "ai_agent":
        raise ValueError("Unexpected token subject")
    print("PASS: signed production token has the expected issuer, audience and user.")
    print("No token or identity value was printed or sent to the MCP server.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print(
            f"Production sign-in check failed at: {stage}. No token was printed.",
            file=sys.stderr,
        )
        sys.exit(1)
