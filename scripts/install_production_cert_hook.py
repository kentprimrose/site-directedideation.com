#!/usr/bin/env python3
"""Install the pinned production Certbot deploy hook without overwriting files."""

import base64
import hashlib
import os
import stat
import sys
import tempfile
from pathlib import Path

EXPECTED = "62d5899dbdf1a37d4abb72200cef58c4ea96f7a3320da04b003d0df21b914191"
DIRECTORY = Path("/etc/letsencrypt/renewal-hooks/deploy")
TARGET = DIRECTORY / "di-mcp-reload.sh"


def main():
    """Verify inputs and publish a new root-owned hook without overwrite."""
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise ValueError("Root and one encoded hook required")
    data = base64.b64decode(sys.argv[1], validate=True)
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Hook digest mismatch")
    for part in (DIRECTORY, *DIRECTORY.parents):
        s = part.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError("Untrusted hook directory")
    if os.path.lexists(TARGET):
        raise ValueError("Hook target already exists")
    fd, name = tempfile.mkstemp(prefix=".di-mcp-hook-", dir=DIRECTORY)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fchmod(file.fileno(), 0o755)
            os.fsync(file.fileno())
        os.link(name, TARGET, follow_symlinks=False)
        directory_fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(name)
    print("Production certificate renewal hook installed; nginx was not reloaded.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError):
        print(
            "Hook installation failed; inspect state before retrying.", file=sys.stderr
        )
        sys.exit(1)
