#!/usr/bin/env python3
"""Run the pinned backend transition with the private production settings."""

import base64
import hashlib
import os
import subprocess
import sys
import tempfile

HELPER_SHA = "007b3a4633323fd7354c38d80ebbd02cd57e912c13dd1837e9e2c616e8e873a6"
ENV_FILE = "/var/lib/di-staging-cutover/pilot-production-01.env"


def main():
    """Run the pinned helper from a temporary root-owned file."""
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise ValueError("root and one helper required")
    data = base64.b64decode(sys.argv[1], validate=True)
    if hashlib.sha256(data).hexdigest() != HELPER_SHA:
        raise ValueError("helper digest mismatch")
    fd, path = tempfile.mkstemp(prefix="di-apply-helper-", dir="/run")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fchmod(file.fileno(), 0o700)
            os.fsync(file.fileno())
        result = subprocess.run(
            ["/bin/bash", path, "apply", "pilot-production-01", ENV_FILE],
            check=False,
        )
        return result.returncode
    finally:
        os.unlink(path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError):
        print(
            "Backend transition failed; inspect state before retrying.", file=sys.stderr
        )
        sys.exit(1)
