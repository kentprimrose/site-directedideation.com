"""Independent staging-only MCP resource server; no production integrations."""

import logging
import math
import os
import re
import time

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from pydantic import AnyHttpUrl
from starlette.middleware.trustedhost import TrustedHostMiddleware

BASE = "https://mcp-staging.directedideation.com"
RESOURCE = BASE + "/mcp"


class StagingVerifier(JWTVerifier):
    """Verify a WorkOS resource access token and its allowlisted subject."""

    def __init__(self, issuer, subjects):
        """Pin the WorkOS issuer, resource, signature algorithm and subject set."""
        super().__init__(
            jwks_uri=issuer + "/oauth2/jwks",
            issuer=issuer,
            audience=RESOURCE,
            algorithm="RS256",
            ssrf_safe=True,
        )
        self.subjects = frozenset(subjects)
        # FastMCP's verifier can log attacker-controlled JWT claims at WARNING.
        self.logger = logging.Logger("staging_mcp.silent_verifier")
        self.logger.disabled = True

    async def verify_token(self, token):
        """Deny missing expiry, non-exact audience or unapproved subjects."""
        if len(token) > 16384:
            return None
        result = await super().verify_token(token)
        if result is None:
            return None
        claims = result.claims
        exp = claims.get("exp")
        nbf = claims.get("nbf")
        sub = claims.get("sub")
        if (
            isinstance(exp, bool)
            or not isinstance(exp, (int, float))
            or not math.isfinite(exp)
            or exp <= time.time()
            or claims.get("aud") != RESOURCE
            or not isinstance(sub, str)
            or sub not in self.subjects
        ):
            return None
        if "nbf" in claims and (
            isinstance(nbf, bool)
            or not isinstance(nbf, (int, float))
            or not math.isfinite(nbf)
            or nbf > time.time()
        ):
            return None
        return result


def create_app():
    """Build the HTTP app or fail startup if security configuration is absent."""
    issuer = os.environ.get("WORKOS_STAGING_ISSUER", "")
    # Require a canonical ASCII DNS origin, rather than letting URL parsers
    # normalize whitespace, case, empty ports or other ambiguous authorities.
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(issuer) > 253 + len("https://") or not re.fullmatch(
        rf"https://{label}(?:\.{label})*", issuer, flags=re.ASCII
    ):
        raise ValueError(
            "WORKOS_STAGING_ISSUER must be a canonical HTTPS DNS origin without port"
        )
    raw = os.environ.get("WORKOS_STAGING_ALLOWED_SUBJECTS", "")
    subjects = raw.split(",")
    if not all(re.fullmatch(r"user_[A-Za-z0-9]+", subject) for subject in subjects):
        raise ValueError("WORKOS_STAGING_ALLOWED_SUBJECTS must contain WorkOS user IDs")
    verifier = StagingVerifier(issuer, subjects)
    auth = RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(issuer)],
        base_url=BASE,
    )
    mcp = FastMCP("Staging ping", auth=auth)

    @mcp.tool
    def ping() -> str:
        """Return a fixed response without accessing any data."""
        return "pong"

    app = mcp.http_app(path="/mcp", stateless_http=True)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["mcp-staging.directedideation.com"]
    )
    return app
