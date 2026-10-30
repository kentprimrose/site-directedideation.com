"""Separate, read-only aggregate dashboard; never expose without trusted ingress."""

import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from html import escape

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from site_directedideation_com.metrics import configuration, snapshot

security = HTTPBasic(auto_error=False)


def auth_config():
    """Validate configuration before serving requests."""
    environment, _ = configuration()
    if environment == "development":
        return None
    user_hash = os.getenv("METRICS_ADMIN_USER_SHA256", "")
    password_hash = os.getenv("METRICS_ADMIN_PASSWORD_SCRYPT", "")
    try:
        salt, digest = password_hash.split(":")
        if (
            len(bytes.fromhex(user_hash)) != 32
            or len(bytes.fromhex(salt)) != 16
            or len(bytes.fromhex(digest)) != 32
        ):
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "Production requires valid admin user SHA-256 and scrypt password hashes"
        ) from None
    return user_hash.lower(), salt, digest.lower()


@asynccontextmanager
async def lifespan(app):
    """Fail startup on invalid configuration or inaccessible storage."""
    app.state.auth = auth_config()
    snapshot()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def authorize(credentials: HTTPBasicCredentials | None = Depends(security)):
    """Require configured credentials in production."""
    config = app.state.auth
    if config is None:
        return
    user_hash, salt, expected = config
    user = credentials.username if credentials else ""
    password = credentials.password if credentials else ""
    actual_user = hashlib.sha256(user.encode()).hexdigest()
    actual_password = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex()
    if not (
        hmac.compare_digest(actual_user, user_hash)
        & hmac.compare_digest(actual_password, expected)
    ):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(authorize)])
def dashboard():
    """Display aggregate counts without exposing a write interface."""
    counts = snapshot()
    rows = "".join(
        f"<tr><td>{escape(group)}</td><td>{escape(name)}</td><td>{count}</td></tr>"
        for group, values in counts.items()
        for name, count in values.items()
    )
    return HTMLResponse(
        "<!doctype html><html><head><title>MCP aggregate metrics</title></head>"
        "<body><h1>MCP aggregate metrics</h1>"
        "<p>Successful calls; not users or sessions.</p><table>"
        "<tr><th>Dimension</th><th>Name</th><th>Count</th></tr>"
        + rows
        + "</table></body></html>",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
