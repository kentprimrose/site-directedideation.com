"""Throwaway local-only WorkOS Connect MCP resource server; not for deployment."""

import os
import time
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from pydantic import AnyHttpUrl
from starlette.middleware.trustedhost import TrustedHostMiddleware

BASE = "http://127.0.0.1:8765"
RESOURCE = f"{BASE}/mcp"


class ExpiringJWTVerifier(JWTVerifier):
    """Require expiry in addition to FastMCP's signature, issuer and audience checks."""

    async def verify_token(self, token):
        """Reject missing, malformed, or expired expiry claims."""
        result = await super().verify_token(token)
        if result is None:
            return None
        exp = result.claims.get("exp")
        if (
            isinstance(exp, bool)
            or not isinstance(exp, (int, float))
            or exp <= time.time()
        ):
            return None
        return result


def create_app(issuer, verifier=None):
    """Build the isolated server using a configured AuthKit HTTPS origin."""
    parsed = urlsplit(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or issuer != f"https://{parsed.netloc}"
    ):
        raise ValueError(
            "WORKOS_AUTHKIT_ISSUER must be an HTTPS origin without trailing slash"
        )
    verifier = verifier or ExpiringJWTVerifier(
        jwks_uri=f"{issuer}/oauth2/jwks",
        issuer=issuer,
        audience=RESOURCE,
        algorithm="RS256",
        ssrf_safe=True,
    )
    auth = RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(issuer)],
        base_url=BASE,
    )
    mcp = FastMCP("LOCAL-ONLY WorkOS OAuth throwaway", auth=auth)

    @mcp.tool
    def local_ping() -> str:
        """Return a fixed harmless response; no production data is accessed."""
        return "local OAuth proof of concept OK"

    app = mcp.http_app(path="/mcp", stateless_http=True)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    return app


if __name__ == "__main__":
    import uvicorn

    issuer = os.environ.get("WORKOS_AUTHKIT_ISSUER", "")
    app = create_app(issuer)
    uvicorn.run(app, host="127.0.0.1", port=8765, proxy_headers=False)
