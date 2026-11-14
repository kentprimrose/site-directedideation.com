#!/usr/bin/env python3
"""Run the pinned nginx cutover with the reviewed production artifacts."""

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DIGESTS = (
    "16112e44c564f4481a8ed9d5ca222214757e5539857a5f3d84e8ad578b0035f8",
    "918e2500982dedb498bc203a83ede7a75e4a50d652a9c87c6fa637b8504e4fa3",
    "8022f7fdc253cc4fcd8d4e6c32c7d3b118598aa163f27174571375a08f0e928c",
)
OLD_CONF = "7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530"
OLD_HELPER = "214f63c23fae0f10867bead0aa290ebb59a5c2ce663749860360d1adc3b2ef05"


def main():
    """Stage verified artifacts privately and invoke the cutover helper."""
    if os.geteuid() != 0 or len(sys.argv) != 4:
        raise ValueError("root and three artifacts required")
    artifacts = [base64.b64decode(value, validate=True) for value in sys.argv[1:]]
    if any(
        hashlib.sha256(data).hexdigest() != digest
        for data, digest in zip(artifacts, DIGESTS)  # noqa: B905
    ):
        raise ValueError("artifact digest mismatch")
    with tempfile.TemporaryDirectory(prefix="di-nginx-cutover-", dir="/run") as tmp:
        paths = [Path(tmp) / name for name in ("installer", "config", "helper")]
        for path, data in zip(paths, artifacts):  # noqa: B905
            path.write_bytes(data)
            path.chmod(0o600)
        result = subprocess.run(
            [
                "/bin/bash",
                str(paths[0]),
                str(paths[1]),
                str(paths[2]),
                OLD_CONF,
                OLD_HELPER,
                DIGESTS[1],
                DIGESTS[2],
            ],
            check=False,
        )
        return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError):
        print(
            "Nginx transition failed; inspect state before retrying.", file=sys.stderr
        )
        sys.exit(1)
