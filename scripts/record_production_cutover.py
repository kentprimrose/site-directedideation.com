#!/usr/bin/env python3
"""Record the live staging backend state using the pinned cutover helper."""

import base64
import hashlib
import os
import subprocess
import sys
import tempfile

HELPER_SHA = "007b3a4633323fd7354c38d80ebbd02cd57e912c13dd1837e9e2c616e8e873a6"
COMPOSE_SHA = "8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff"


def main():
    """Run the pinned helper from a temporary root-owned file."""
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise ValueError("Root and one helper required")
    data = base64.b64decode(sys.argv[1], validate=True)
    if hashlib.sha256(data).hexdigest() != HELPER_SHA:
        raise ValueError("Helper digest mismatch")
    fd, path = tempfile.mkstemp(prefix="di-record-helper-", dir="/run")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fchmod(file.fileno(), 0o700)
            os.fsync(file.fileno())
        result = subprocess.run(
            ["/bin/bash", path, "record", "pilot-production-01", COMPOSE_SHA],
            check=False,
        )
        return result.returncode
    finally:
        os.unlink(path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError):
        print("Recording failed; inspect state before retrying.", file=sys.stderr)
        sys.exit(1)
