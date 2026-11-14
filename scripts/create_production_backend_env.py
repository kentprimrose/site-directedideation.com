#!/usr/bin/env python3
"""Privately prepare production WorkOS settings without switching the service."""

import getpass
import os
import re
import stat
import sys
from pathlib import Path

DIRECTORY = Path("/var/lib/di-staging-cutover")
RECORD = DIRECTORY / "pilot-production-01"
TARGET = DIRECTORY / "pilot-production-01.env"


def main():
    """Prompt on the terminal and create a new root-only environment file."""
    if os.geteuid() != 0:
        raise ValueError("root required")
    info = DIRECTORY.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("untrusted directory")
    info = RECORD.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("untrusted record")
    old = RECORD.read_text().splitlines()
    issuer = getpass.getpass("Production AuthKit origin (hidden): ").strip().rstrip("/")
    subject = getpass.getpass("Production user_ ID (hidden): ").strip()
    if not re.fullmatch(
        r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.authkit\.app", issuer
    ):
        raise ValueError("invalid origin format")
    if not re.fullmatch(r"user_[A-Za-z0-9]+", subject):
        raise ValueError("invalid user ID format")
    if f"OLD_ISSUER={issuer}" in old:
        raise ValueError("issuer matches staging")
    data = (
        "STAGING_MCP_HOST=mcp.directedideation.com\n"
        f"WORKOS_STAGING_ISSUER={issuer}\n"
        f"WORKOS_STAGING_ALLOWED_SUBJECTS={subject}\n"
    ).encode()
    fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    print("Production settings saved privately; backend was not changed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyboardInterrupt):
        print(
            "Could not prepare settings; no backend change was attempted.",
            file=sys.stderr,
        )
        sys.exit(1)
