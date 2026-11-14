#!/usr/bin/env python3
"""Print non-sensitive facts needed before installing the ACME-only vhost."""

import hashlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


def command(*args):
    """Capture command output without printing nginx configuration or errors."""
    return subprocess.run(
        args, capture_output=True, text=True, timeout=20, check=True
    ).stdout


def main():  # noqa: C901
    """Inspect nginx, the pinned files, lock and timer without modifying them."""
    if os.geteuid() != 0:
        raise ValueError("root required")
    source = Path("/home/kent/di-production-acme-178bb690.conf")
    public = Path("/etc/nginx/conf.d/di-staging-public-test.conf")
    target = Path("/etc/nginx/conf.d/di-production-acme.conf")
    lock = Path("/var/lib/di-shared-test/lock")
    for path, expected, name in (
        (
            source,
            "178bb69096c437e5474e2f0af3e472d50435d4eae9c751d350089c60b7195d1f",
            "Uploaded challenge config",
        ),
        (
            public,
            "7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530",
            "Existing staging config",
        ),
    ):
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError(name + " mismatch")
        print(name + ": hash matches")
    if os.path.lexists(target):
        raise ValueError("Target already exists")
    print("Target vhost: absent")
    info = lock.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("Unexpected nginx lock")
    print("Nginx lock: root-owned regular file, mode 0600")
    for unit in (
        "di-shared-test-rollback-once.timer",
        "di-shared-test-rollback-once.service",
    ):
        state = command(
            "systemctl", "show", unit, "-p", "ActiveState", "--value"
        ).strip()
        if state != "inactive":
            raise ValueError("Rollback timer or service is not inactive")
    print("Rollback timer and service: inactive")
    config = command("/usr/sbin/nginx", "-T")
    if "# configuration file /etc/nginx/nginx.conf:" not in config:
        raise ValueError("Unexpected nginx configuration path")
    if not re.search(r"(?m)^\s*include\s+/etc/nginx/conf\.d/\*\.conf\s*;", config):
        raise ValueError("Expected nginx include missing")
    names = re.findall(r"(?m)^\s*server_name\s+([^;]+);", config)
    if any("mcp.directedideation.com" in name.split() for name in names):
        raise ValueError("Production hostname already present")
    if not any("mcp-staging.directedideation.com" in name.split() for name in names):
        raise ValueError("Staging hostname missing")
    print(
        "Nginx: expected config/include, staging name present, production name absent"
    )
    unit = command("systemctl", "show", "nginx.service", "-p", "ExecStart", "--value")
    if "/usr/sbin/nginx" not in unit:
        raise ValueError("Unexpected nginx service executable")
    print("Nginx service: expected executable")
    print("Read-only preflight passed; no route has been installed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Preflight failed; no route was installed.", file=sys.stderr)
        sys.exit(1)
