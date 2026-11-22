"""Independent staging-only MCP resource server; no production integrations."""

import logging
import math
import os
import re
import time
from typing import Annotated, TypeGuard

from fastmcp import FastMCP
from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.shared.exceptions import MCPError
from pydantic import AnyHttpUrl, TypeAdapter, UrlConstraints
from starlette.middleware.trustedhost import TrustedHostMiddleware

from site_directedideation_com.mcp import (
    INTERVIEW_STAGES,
    READ_ONLY,
    get_alternative_techniques,
    get_diagnostic_checks,
    get_directed_ideation_method,
    get_interview_guidance,
    get_lateral_thinking_guidance,
    get_requirements_clarification_guidance,
    get_strategic_thinking_guidance,
)

BASE = "https://mcp-staging.directedideation.com"
RESOURCE = BASE + "/mcp"
MAX_MCP_BODY_BYTES = 64 * 1024


class MCPBodyLimitMiddleware:
    """Buffer only bounded MCP bodies before allowing the application to run."""

    def __init__(self, app):
        """Wrap the MCP application."""
        self.app = app

    async def __call__(self, scope, receive, send):  # noqa: C901
        """Validate and buffer a complete bounded request before dispatch."""
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/mcp" or path.startswith("/mcp/")):
            await self.app(scope, receive, send)
            return

        lengths = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if len(lengths) > 1 or (lengths and not re.fullmatch(rb"[0-9]+", lengths[0])):
            await self._reject(send, 400)
            return
        # Avoid converting an arbitrarily long integer supplied by a client.
        length = None
        if lengths:
            digits = lengths[0].lstrip(b"0") or b"0"
            if len(digits) > len(str(MAX_MCP_BODY_BYTES)):
                await self._reject(send, 413)
                return
            length = int(digits)
            if length > MAX_MCP_BODY_BYTES:
                await self._reject(send, 413)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # A disconnected client cannot provide a complete body.
                return
            chunk = message.get("body", b"")
            if len(chunk) > MAX_MCP_BODY_BYTES - len(body):
                await self._reject(send, 413)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if length is not None and length != len(body):
            await self._reject(send, 400)
            return

        async def replay():
            nonlocal body
            if body is not None:
                data = bytes(body)
                body = None
                return {"type": "http.request", "body": data, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send, status):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})


class ToolInputBoundary(Middleware):
    """Reject unexpected inputs without echoing potentially sensitive values."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Validate the allowed arguments before SDK validation can echo values."""
        message = context.message
        arguments = message.arguments or {}
        if message.name in {
            "ping",
            "get_directed_ideation_method",
            "get_lateral_thinking_guidance",
            "get_requirements_clarification_guidance",
            "get_strategic_thinking_guidance",
        }:
            valid = not arguments
        elif message.name in {
            "get_interview_guidance",
            "get_diagnostic_checks",
            "get_alternative_techniques",
        }:
            stage = arguments.get("stage")
            valid = set(arguments) <= {"stage"} and (
                stage is None or (isinstance(stage, str) and stage in INTERVIEW_STAGES)
            )
        else:
            valid = False
        if not valid:
            raise MCPError(code=-32602, message="Invalid parameters")
        return await call_next(context)


class StagingVerifier(JWTVerifier):
    """Verify a WorkOS resource access token and its allowlisted subject."""

    def __init__(self, issuer, subjects, resource=RESOURCE):
        """Pin the WorkOS issuer, resource, signature algorithm and subject set."""
        super().__init__(
            jwks_uri=issuer + "/oauth2/jwks",
            issuer=issuer,
            audience=resource,
            algorithm="RS256",
            ssrf_safe=True,
        )
        self.resource = resource
        self.subjects = frozenset(subjects)
        # FastMCP's verifier can log attacker-controlled JWT claims at WARNING.
        self.logger = logging.Logger("staging_mcp.silent_verifier")
        self.logger.disabled = True

    async def verify_token(self, token):
        """Deny missing expiry, non-exact audience or unapproved subjects."""
        if len(token) > 16384:
            return None
        try:
            result = await super().verify_token(token)
        except OverflowError:
            # The upstream verifier converts exp to int before our checks.
            return None
        if result is None:
            return None
        claims = result.claims
        exp = claims.get("exp")
        nbf = claims.get("nbf")
        sub = claims.get("sub")

        def finite_number(value: object) -> TypeGuard[int | float]:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            try:
                return math.isfinite(value)
            except OverflowError:
                return False

        if (
            not finite_number(exp)
            or exp <= time.time()
            or claims.get("aud") != self.resource
            or not isinstance(sub, str)
            or sub not in self.subjects
        ):
            return None
        if "nbf" in claims and (not finite_number(nbf) or nbf > time.time()):
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
    host = os.environ.get("STAGING_MCP_HOST", "mcp-staging.directedideation.com")
    if host not in {"mcp-staging.directedideation.com", "mcp.directedideation.com"}:
        raise ValueError("STAGING_MCP_HOST must be an approved pilot hostname")
    base = "https://" + host
    verifier = StagingVerifier(issuer, subjects, base + "/mcp")
    auth = RemoteAuthProvider(
        token_verifier=verifier,
        # Preserve the issuer origin exactly: Pydantic otherwise adds a slash,
        # which breaks exact OAuth authorization-server issuer matching.
        authorization_servers=[
            TypeAdapter(
                Annotated[AnyHttpUrl, UrlConstraints(preserve_empty_path=True)]
            ).validate_python(issuer)
        ],
        base_url=base,
    )
    mcp = FastMCP("Staging directed ideation", auth=auth, mask_error_details=True)
    mcp.add_middleware(ToolInputBoundary())
    for tool in (
        get_directed_ideation_method,
        get_interview_guidance,
        get_lateral_thinking_guidance,
        get_requirements_clarification_guidance,
        get_strategic_thinking_guidance,
        get_diagnostic_checks,
        get_alternative_techniques,
    ):
        mcp.tool(tool, annotations=READ_ONLY)

    @mcp.tool
    def ping() -> str:
        """Return a fixed response without accessing any data."""
        return "pong"

    app = mcp.http_app(path="/mcp", stateless_http=True)
    app.add_middleware(MCPBodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host])
    return app
