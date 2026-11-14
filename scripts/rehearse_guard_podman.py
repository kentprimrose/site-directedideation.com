#!/usr/bin/env python3
"""Disposable, labelled Podman rehearsal of guard a5c72bb; not a production test.

Requires the running rootful podman-machine-default, docker-compose v2+, and an
already-local docker.io/library/python:3.11-slim. No ports or volumes published.
Never manages the VM or removes resources without this run's random label.
"""

import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

REV = "a5c72bb6d09865f1e1ec6a4524f6f2cae09a9894"
ROOT = Path(__file__).resolve().parents[1]
BASE = "docker.io/library/python:3.11-slim"


def call(*args, **kwargs):
    """Run a command and return its captured standard output."""
    return subprocess.run(
        args, check=True, text=True, capture_output=True, **kwargs
    ).stdout.strip()


def main():  # noqa: C901
    """Exercise the pinned guard on isolated labelled Podman resources."""
    podman = shutil.which("podman")
    compose = shutil.which("docker-compose")
    if not podman or not compose:
        raise RuntimeError("podman and docker-compose required")
    machine = "podman-machine-default"
    try:
        info = json.loads(call(podman, "machine", "inspect", machine))[0]
    except (ValueError, IndexError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Cannot inspect the Podman machine") from exc
    if info["State"] != "running" or not info["Rootful"]:
        raise RuntimeError("default rootful machine must already be running")
    socket = info["ConnectionInfo"]["PodmanSocket"]["Path"]

    def pm(*args):
        return call(podman, "--connection", machine + "-root", *args)

    base_id = pm("image", "inspect", "--format", "{{.Id}}", BASE)
    if not base_id:
        raise RuntimeError("local base image required; no pulling is performed")
    token = "gr" + secrets.token_hex(12)
    label = "rehearsal.owner=" + token
    project = token
    tag = "localhost/" + token + ":active"
    backup = "localhost/" + token + ":backup"
    candidate_tag = "localhost/" + token + ":candidate"
    # Substitute only the hard-coded project name; all other guard code comes
    # from the pinned commit. The adapter below translates Docker to Podman.
    source = call(
        "git", "-C", str(ROOT), "show", REV + ":staging_mcp/staging-upgrade/upgrade.py"
    )
    source = source.replace("'di-staging'", repr(project))
    try:
        with tempfile.TemporaryDirectory(prefix=token) as td:
            root = Path(td)
            module = root / "guard.py"
            module.write_text(source)
            spec = importlib.util.spec_from_file_location("rehearsal_guard", module)
            if spec is None or spec.loader is None:
                raise RuntimeError("Cannot load pinned guard")
            u = cast(Any, importlib.util.module_from_spec(spec))
            spec.loader.exec_module(u)
            u.TAG, u.BACKUP, u.CONTAINER = tag, backup, project + "-staging-mcp-1"
            u.OLD, u.NEW, u.STATE = (
                root / "old" / "compose.yaml",
                root / "new" / "compose.yaml",
                root / "state",
            )
            u.HOST = "rehearsal.invalid"
            # Host is macOS, not the production Linux root trust boundary.
            u.trusted = lambda _path: None
            for path, host in ((u.OLD, False), (u.NEW, True)):
                path.parent.mkdir()
                path.write_text(
                    f"""services:
  staging-mcp:
    image: {tag}
    hostname: rehearsal
    labels:
      rehearsal.owner: {token}
    environment:
      WORKOS_STAGING_ISSUER: ${{WORKOS_STAGING_ISSUER}}
      WORKOS_STAGING_ALLOWED_SUBJECTS: ${{WORKOS_STAGING_ALLOWED_SUBJECTS}}
"""
                    + ("      STAGING_MCP_HOST: ${STAGING_MCP_HOST}\n" if host else "")
                    + f"""    healthcheck:
      test: ["CMD", "python", "-c", "pass"]
      interval: 1s
      timeout: 2s
      retries: 5
networks:
  default:
    labels:
      rehearsal.owner: {token}
"""
                )
            u.OLD_HASH = hashlib.sha256(u.OLD.read_bytes()).hexdigest()
            u.NEW_HASH = hashlib.sha256(u.NEW.read_bytes()).hexdigest()
            build = root / "build"
            build.mkdir()
            (build / "Containerfile").write_text(
                f"FROM {BASE}\nARG VERSION\n"
                f"LABEL rehearsal.owner={token} rehearsal.version=$VERSION\n"
                'CMD ["python", "-c", "import time; time.sleep(3600)"]\n'
            )
            pm(
                "build",
                "--pull=never",
                "--build-arg",
                "VERSION=old",
                "-t",
                tag,
                str(build),
            )
            oldid = "sha256:" + pm(
                "image", "inspect", "--format", "{{.Id}}", tag
            ).removeprefix("sha256:")
            (build / "Containerfile").write_text(
                (build / "Containerfile")
                .read_text()
                .replace("rehearsal.version=$VERSION", "rehearsal.version=new")
            )
            pm(
                "build",
                "--no-cache",
                "--pull=never",
                "--build-arg",
                "VERSION=new",
                "-t",
                candidate_tag,
                str(build),
            )
            candidate = "sha256:" + pm(
                "image", "inspect", "--format", "{{.Id}}", candidate_tag
            ).removeprefix("sha256:")
            injected = {"fail_up": False}

            def run(*args, env=None):
                try:
                    if args[0] == "compose":
                        if injected["fail_up"] and "up" in args:
                            raise RuntimeError("injected before compose up")
                        e = {
                            "PATH": os.environ["PATH"],
                            "HOME": str(root),
                            "DOCKER_HOST": "unix://" + socket,
                        }
                        e.update(
                            {
                                k: v
                                for k, v in (env or {}).items()
                                if k not in ("PATH", "HOME", "DOCKER_HOST")
                            }
                        )
                        return call(compose, *args[1:], env=e)
                    if args[0] == "tag":
                        # Podman requires untagging the destination first.
                        existing = u.image(args[2])
                        if existing:
                            pm("image", "untag", existing, args[2])
                    out = pm(*args)
                    if args[:3] == ("image", "inspect", "--format"):
                        out = "sha256:" + out.removeprefix("sha256:")
                    if args[0] == "inspect":
                        data = json.loads(out)
                        for c in data:
                            c["Image"] = "sha256:" + c["Image"].removeprefix("sha256:")
                        out = json.dumps(data)
                    return out
                except subprocess.CalledProcessError as exc:
                    raise RuntimeError(
                        "adapter command failed: " + str(exc) + "\n" + exc.stderr
                    ) from exc

            u.run = run
            env = {
                "WORKOS_STAGING_ISSUER": "https://issuer.invalid",
                "WORKOS_STAGING_ALLOWED_SUBJECTS": "synthetic",
            }
            u.compose(
                u.OLD,
                env,
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--no-deps",
                "--force-recreate",
                "staging-mcp",
            )
            u.healthy()
            u.switch(candidate)
            assert u.image(tag) == candidate and u.image(backup) == oldid
            u.recover()
            assert u.image(tag) == oldid and u.container()["Image"] == oldid
            print("PASS switch and recover", flush=True)
            # Interrupted recovery after retag, before Compose recreates old.
            shutil.rmtree(u.STATE)
            pm("image", "untag", oldid, backup)
            u.compose(
                u.OLD,
                env,
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--no-deps",
                "--force-recreate",
                "staging-mcp",
            )
            u.healthy()
            u.switch(candidate)
            baseline = u.STATE / "candidate.json"
            original = baseline.read_text()
            altered = json.loads(original)
            altered["env"]["WORKOS_STAGING_ISSUER"] = "https://drift.invalid"
            baseline.write_text(json.dumps(altered))
            try:
                u.recover()
            except RuntimeError as exc:
                assert "Candidate environment drift" in str(exc)
            else:
                raise AssertionError("candidate environment drift accepted")
            assert u.image(tag) == candidate and u.container()["Image"] == candidate
            baseline.write_text(original)
            print(
                "PASS candidate environment drift refused without mutation", flush=True
            )
            injected["fail_up"] = True
            try:
                u.recover()
            except RuntimeError as exc:
                if str(exc) != "injected before compose up":
                    raise
            else:
                raise AssertionError("recovery interruption did not fire")
            assert u.image(tag) == oldid and u.container()["Image"] == candidate
            injected["fail_up"] = False
            u.recover()
            assert u.image(tag) == oldid and u.container()["Image"] == oldid
            print("PASS interrupted recovery retried", flush=True)
            try:
                u.switch(candidate)
            except RuntimeError as exc:
                assert "already exists" in str(exc)
            else:
                raise AssertionError("existing recovery record was accepted")
            assert u.image(tag) == oldid and u.container()["Image"] == oldid
            print("PASS existing recovery record refused without mutation", flush=True)
            snapshot = u.STATE / "old-compose.yaml"
            saved = snapshot.read_bytes()
            snapshot.write_bytes(saved + b"\n# tampered\n")
            try:
                u.recover()
            except RuntimeError as exc:
                assert "pinned digest" in str(exc)
            else:
                raise AssertionError("tampered snapshot was accepted")
            assert u.image(tag) == oldid and u.container()["Image"] == oldid
            snapshot.write_bytes(saved)
            print(
                "PASS tampered recovery snapshot refused without mutation", flush=True
            )
            shutil.rmtree(u.STATE)
            pm("image", "untag", oldid, backup)
            # Recreate from OLD so labels correspond to the initial fixture.
            u.compose(
                u.OLD,
                env,
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--no-deps",
                "--force-recreate",
                "staging-mcp",
            )
            u.healthy()
            injected["fail_up"] = True
            try:
                u.switch(candidate)
            except RuntimeError as exc:
                if str(exc) != "injected before compose up":
                    raise
            else:
                raise AssertionError("failure injection did not fire")
            injected["fail_up"] = False
            u.recover()
            assert u.image(tag) == oldid and u.container()["Image"] == oldid
            print("PASS interruption after retag and recovery", flush=True)
    finally:
        # Filter each object by the unguessable run label, never global cleanup.
        for kind, remove in [
            ("container", ("rm", "-f")),
            ("network", ("network", "rm")),
            ("image", ("image", "rm", "-f")),
        ]:
            ids = pm(
                kind,
                "ls",
                "-q" if kind == "network" else "-aq",
                "--filter",
                "label=" + label,
            ).splitlines()
            for item in ids:
                pm(*remove, item)
        print("Cleanup: removed resources bearing " + label, flush=True)


if __name__ == "__main__":
    main()
