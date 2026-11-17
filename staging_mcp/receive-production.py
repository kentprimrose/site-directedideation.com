#!/usr/bin/python3
"""Receive a CI image and recreate only the authenticated pilot container."""

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys

COMPOSE = "/etc/di-staging/compose.yaml"
COMPOSE_SHA = "8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff"
CONTAINER = "di-staging-staging-mcp-1"
TAG = "directed-ideation-staging-mcp:local"
ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
}


def run(*args, env=None, stdin=None):
    """Run Docker without exposing its output."""
    return subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", *args],
        env=env or ENV,
        stdin=stdin if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=300,
    ).stdout


def main(sha):  # noqa: C901
    """Validate the live service and deploy or restore its image."""
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid caller or revision")
    for path in ("/etc", "/etc/di-staging", COMPOSE):
        s = os.lstat(path)
        if stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError("Untrusted compose path")
    if (
        os.path.lexists("/etc/di-staging/.env")
        or hashlib.sha256(open(COMPOSE, "rb").read()).hexdigest() != COMPOSE_SHA
    ):
        raise ValueError("Unexpected compose configuration")
    with open("/run/lock/di-staging-allowlist.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = json.loads(run("inspect", CONTAINER))[0]
        labels = c["Config"]["Labels"]
        if (
            labels.get("com.docker.compose.project") != "di-staging"
            or labels.get("com.docker.compose.service") != "staging-mcp"
            or labels.get("com.docker.compose.project.config_files") != COMPOSE
            or labels.get("com.docker.compose.project.working_dir") != "/etc/di-staging"
            or c["Config"]["Image"] != TAG
        ):
            raise ValueError("Unexpected container identity")
        old = c["Image"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", old):
            raise ValueError("Unexpected image identity")
        values = {}
        for entry in c["Config"]["Env"]:
            key, _, value = entry.partition("=")
            if key in (
                "STAGING_MCP_HOST",
                "WORKOS_STAGING_ISSUER",
                "WORKOS_STAGING_ALLOWED_SUBJECTS",
            ):
                if key in values or not value or "\n" in value:
                    raise ValueError("Invalid container configuration")
                values[key] = value
        if (
            values.get("STAGING_MCP_HOST") != "mcp.directedideation.com"
            or not re.fullmatch(
                r"https://[a-z0-9.-]+", values.get("WORKOS_STAGING_ISSUER", "")
            )
            or not re.fullmatch(
                r"user_[A-Za-z0-9]+(,user_[A-Za-z0-9]+)*",
                values.get("WORKOS_STAGING_ALLOWED_SUBJECTS", ""),
            )
        ):
            raise ValueError("Production configuration required")
        image = "directed-ideation-authenticated:" + sha
        run("load", stdin=sys.stdin.buffer)
        run("image", "inspect", image)
        # Keep an immutable local rollback reference before changing the mutable tag.
        run("tag", old, "directed-ideation-authenticated:rollback")
        run("tag", image, TAG)
        env = dict(ENV, **values)
        command = (
            "compose",
            "--project-directory",
            "/etc/di-staging",
            "-p",
            "di-staging",
            "-f",
            COMPOSE,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "120",
            "staging-mcp",
        )
        try:
            run(*command, env=env)
        except Exception:
            run("tag", old, TAG)
            try:
                run(*command, env=env)
            except Exception:
                print(
                    "Rollback failed; operator intervention required", file=sys.stderr
                )
            raise
    print(
        "Authenticated deployment healthy; "
        "unauthenticated requests rejected by healthcheck"
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected revision")
        main(sys.argv[1])
    except Exception:
        print("Authenticated deployment failed; inspect privately", file=sys.stderr)
        sys.exit(1)
