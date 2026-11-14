#!/usr/bin/env python3
"""Check the new loopback backend without exposing the configured issuer."""

import http.client
import json
import os
import sys
from pathlib import Path

ENV_FILE = Path("/var/lib/di-staging-cutover/pilot-production-01.env")
HOST = "mcp.directedideation.com"
OLD_HOST = "mcp-staging.directedideation.com"
PATH = "/.well-known/oauth-protected-resource/mcp"


def request(method, path, host):
    """Make one unauthenticated loopback request."""
    conn = http.client.HTTPConnection("127.0.0.1", 8765, timeout=5)
    try:
        conn.request(
            method,
            path,
            body=b"{}" if method == "POST" else None,
            headers={"Host": host, "Content-Type": "application/json"},
        )
        result = conn.getresponse()
        return result.status, result.read(65536)
    finally:
        conn.close()


def main():
    """Compare metadata to the private issuer without displaying either."""
    if os.geteuid() != 0:
        raise ValueError("root required")
    issuers = [
        line.split("=", 1)[1]
        for line in ENV_FILE.read_text().splitlines()
        if line.startswith("WORKOS_STAGING_ISSUER=")
    ]
    if len(issuers) != 1:
        raise ValueError("invalid environment file")
    status, body = request("GET", PATH, HOST)
    try:
        metadata = json.loads(body) if status == 200 else {}
    except (ValueError, UnicodeDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    checks = [
        (
            "production resource and issuer metadata",
            status == 200
            and metadata.get("resource") == f"https://{HOST}/mcp"
            and metadata.get("authorization_servers") == issuers,
        ),
        ("old Host rejected", request("GET", PATH, OLD_HOST)[0] == 400),
        ("anonymous MCP request rejected", request("POST", "/mcp", HOST)[0] == 401),
    ]
    for label, ok in checks:
        print(("PASS " if ok else "FAIL ") + label)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, http.client.HTTPException):
        print(
            "Loopback verification failed; no identity values printed.", file=sys.stderr
        )
        sys.exit(1)
