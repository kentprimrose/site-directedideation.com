#!/usr/bin/env python3
"""Read-only check that the private old Compose snapshot renders consistently."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    """Compare the saved Compose hash in the old and new project directories."""
    try:
        saved = json.loads(
            Path("/var/lib/di-staging-manual-upgrade/container.json").read_text()
        )[0]
    except (OSError, ValueError, IndexError) as exc:
        raise ValueError("Cannot read saved inspection") from exc
    values = {}
    for entry in saved["Config"]["Env"]:
        key, sep, value = entry.partition("=")
        if key in ("WORKOS_STAGING_ISSUER", "WORKOS_STAGING_ALLOWED_SUBJECTS"):
            if not sep or key in values or not value:
                raise ValueError("Invalid saved environment")
            values[key] = value
    if len(values) != 2:
        raise ValueError("Missing saved environment")
    expected = saved["Config"]["Labels"]["com.docker.compose.config-hash"]
    env = {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        **values,
    }
    snapshot = "/var/lib/di-staging-manual-upgrade/old-compose.yaml"
    for directory in ("/home/kent/di-pilot-build.eR6dNHdr", "/etc/di-staging"):
        dotenv = Path(directory) / ".env"
        if dotenv.exists() or dotenv.is_symlink():
            raise ValueError("Unexpected .env file")
        result = subprocess.run(
            [
                "/usr/bin/docker",
                "--host",
                "unix:///var/run/docker.sock",
                "compose",
                "--project-name",
                "di-staging",
                "--project-directory",
                directory,
                "-f",
                snapshot,
                "config",
                "--hash",
                "staging-mcp",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout.strip()
        if result != "staging-mcp " + expected:
            raise ValueError("Compose hash mismatch")
        print("Compose hash matches in", directory)


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        subprocess.SubprocessError,
    ):
        print("Check failed; no service or image changes were made.", file=sys.stderr)
        sys.exit(1)
