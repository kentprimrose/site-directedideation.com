#!/usr/bin/env python3
"""Guarded, deliberately narrow migration of the inventoried staging deployment."""

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NoReturn

OLD = Path("/home/kent/di-pilot-build.eR6dNHdr/compose.yaml")
NEW = Path("/etc/di-staging/compose.yaml")
STATE = Path("/var/lib/di-staging-upgrade")
LOCK = Path("/run/lock/di-staging-allowlist.lock")
OLD_HASH = "18e3d4bf8a8d5fdbf365fb069c0eae14903a11292197812ae28e44506eff3c45"
NEW_HASH = "8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff"
TAG = "directed-ideation-staging-mcp:local"
BACKUP = "directed-ideation-staging-mcp:upgrade-preserved"
CONTAINER = "di-staging-staging-mcp-1"
HOST = "mcp-staging.directedideation.com"
BASE_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
}


def fail(message: str) -> NoReturn:
    """Stop safely with a non-sensitive error."""
    raise RuntimeError(message)


def run(*args, env=None):
    """Run a Docker command with captured output."""
    p = subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", *args],
        env=env or BASE_ENV,
        capture_output=True,
    )
    if p.returncode:
        fail("Docker operation failed; output suppressed. State may require recovery.")
    return p.stdout.decode()


def trusted(path):
    """Reject writable, symlinked or non-root path components (including parents)."""
    for p in [*reversed(path.parents), path]:
        s = p.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            fail("Untrusted path ownership, permissions, or symlink.")


def checked_file(path, digest):
    """Check a trusted Compose file and digest."""
    trusted(path)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        fail("Compose bytes differ from the pinned digest.")
    if os.path.lexists(path.parent / ".env"):
        fail("Compose project .env is forbidden.")


def pinned_bytes(path, digest):
    # The source may be writable: never execute it, only the verified byte copy.
    """Capture and validate the pinned source bytes."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail("Compose source is not a regular file.")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(1024 * 1024 + 1)
    finally:
        os.close(fd)
    if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
        fail("Compose bytes differ from the pinned digest.")
    return data


def private_state():
    """Validate recovery directory permissions."""
    trusted(STATE)
    s = STATE.lstat()
    if not stat.S_ISDIR(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o700:
        fail("Recovery directory must be root-owned mode 0700.")


def private_file(path):
    """Validate a private recovery file."""
    private_state()
    trusted(path)
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600:
        fail("Recovery file must be root-owned mode 0600.")


def runtime(c):
    # Exclude generated identity, timestamps, labels and network endpoints, but
    # preserve effective process, mounts, ports, security and resource settings.
    """Extract selected runtime settings."""
    config = c["Config"]
    host = c.get("HostConfig", {})
    keys = (
        "Cmd",
        "Entrypoint",
        "User",
        "WorkingDir",
        "Healthcheck",
        "ExposedPorts",
        "Volumes",
        "StopSignal",
    )
    hostkeys = (
        "Binds",
        "Mounts",
        "PortBindings",
        "NetworkMode",
        "RestartPolicy",
        "ReadonlyRootfs",
        "Tmpfs",
        "CapAdd",
        "CapDrop",
        "SecurityOpt",
        "Privileged",
        "PidMode",
        "IpcMode",
        "UsernsMode",
        "Devices",
        "PidsLimit",
        "Memory",
        "NanoCpus",
        "CpuShares",
        "LogConfig",
        "ExtraHosts",
        "Dns",
        "DnsSearch",
        "DnsOptions",
    )
    return {
        "config": {k: config.get(k) for k in keys},
        "host": {k: host.get(k) for k in hostkeys},
    }


def image(tag):
    # A successful listing establishes absence; inspect failures are never absence.
    """Resolve an image, distinguishing absence from daemon errors."""
    if not tag.startswith("sha256:"):
        names = run(
            "image", "ls", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}}"
        ).splitlines()
        if tag not in names:
            return None
    out = run("image", "inspect", "--format", "{{.Id}}", tag).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", out):
        fail("Invalid image inspection output.")
    return out


def container():
    """Inventory all containers and reject unexplained project members or names."""
    ids = run("ps", "-a", "-q", "--no-trunc").splitlines()
    if len(ids) != len(set(ids)) or any(
        not re.fullmatch(r"[0-9a-f]{64}", ident) for ident in ids
    ):
        fail("Invalid container inventory; manual reconciliation required.")
    relevant = []
    for ident in ids:
        try:
            data = json.loads(run("inspect", ident))
            if (
                not isinstance(data, list)
                or len(data) != 1
                or not isinstance(data[0], dict)
            ):
                fail("Invalid container inspection output.")
            c = data[0]
            if c["Id"] != ident or not isinstance(c["Name"], str):
                fail("Invalid container identity.")
            labels = c["Config"].get("Labels") or {}
            if not isinstance(labels, dict):
                fail("Invalid container labels.")
            if (
                c["Name"].lstrip("/") == CONTAINER
                or labels.get("com.docker.compose.project") == "di-staging"
            ):
                relevant.append(c)
        except (ValueError, KeyError, TypeError):
            fail("Invalid container inspection output.")
    if len(relevant) > 1 or (relevant and relevant[0]["Name"] != "/" + CONTAINER):
        fail(
            "Unexpected Compose project container inventory; "
            "manual reconciliation required."
        )
    return relevant[0] if relevant else None


def environment(c):
    """Extract an unambiguous container environment."""
    result = {}
    for entry in c["Config"]["Env"]:
        key, sep, value = entry.partition("=")
        if not sep or key in result:
            fail("Ambiguous container environment.")
        result[key] = value
    return result


def values(c):
    """Validate the old container environment."""
    result = environment(c)
    if "STAGING_MCP_HOST" in result:
        fail("Old container unexpectedly specifies a host.")
    for key in ("WORKOS_STAGING_ISSUER", "WORKOS_STAGING_ALLOWED_SUBJECTS"):
        if not result.get(key) or "\n" in result[key]:
            fail("Missing or invalid runtime value.")
    return result


def compose(path, env, *args):
    """Run Compose with explicit project and interpolation values."""
    e = dict(
        BASE_ENV,
        WORKOS_STAGING_ISSUER=env["WORKOS_STAGING_ISSUER"],
        WORKOS_STAGING_ALLOWED_SUBJECTS=env["WORKOS_STAGING_ALLOWED_SUBJECTS"],
        STAGING_MCP_HOST=HOST,
    )
    return run(
        "compose",
        "--project-name",
        "di-staging",
        "--project-directory",
        str(path.parent),
        "-f",
        str(path),
        *args,
        env=e,
    )


def config_hash(path, env):
    """Get the service configuration hash."""
    out = compose(path, env, "config", "--hash", "staging-mcp").strip().split()
    if (
        len(out) != 2
        or out[0] != "staging-mcp"
        or not re.fullmatch("[0-9a-f]{64}", out[1])
    ):
        fail("Unexpected Compose hash output.")
    return out[1]


def verify(c, image_id, path, env, expected_hash, old):
    """Check container identity, labels and environment."""
    if (
        not c
        or not c["State"]["Running"]
        or c["Image"] != image_id
        or c["Config"]["Image"] != TAG
    ):
        fail("Container image or running state mismatch.")
    labels = c["Config"]["Labels"]
    for key, val in {
        "project": "di-staging",
        "service": "staging-mcp",
        "project.config_files": str(path),
        "project.working_dir": str(path.parent),
        "config-hash": expected_hash,
    }.items():
        if labels.get("com.docker.compose." + key) != val:
            fail("Container Compose labels mismatch.")
    actual = environment(c)
    for key in ("WORKOS_STAGING_ISSUER", "WORKOS_STAGING_ALLOWED_SUBJECTS"):
        if actual.get(key) != env[key]:
            fail("Container runtime values mismatch.")
    if (
        actual.get("STAGING_MCP_HOST") if not old else "STAGING_MCP_HOST" not in actual
    ) != (HOST if not old else True):
        fail("Container host mismatch.")
    # For old recovery compare the complete environment, including image defaults.
    if old and actual != env:
        fail("Old container environment differs from the saved state.")


def healthy():
    """Wait for container health."""
    for _ in range(90):
        c = container()
        if c and c["State"].get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(1)
    fail("Health did not become healthy; recover or stay closed.")


def sync_dir(path):
    """Synchronize a directory."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable(path, data):
    # Publish only a complete, synced inode, without overwriting an existing record.
    """Publish a recovery file durably without overwrite."""
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path, follow_symlinks=False)
        sync_dir(path.parent)
    finally:
        os.unlink(temporary)
        sync_dir(path.parent)


def check_old_before_tag(record, expected_tag, backup):
    """Recheck old service and tags before mutation."""
    c = container()
    if (
        not c
        or c["Id"] != record["container_id"]
        or runtime(c) != record["old_runtime"]
        or image(TAG) != expected_tag
        or image(BACKUP) != backup
    ):
        fail("Drift detected immediately before tag mutation; remain closed.")
    verify(c, record["old_id"], OLD, record["env"], record["old_hash"], True)


def switch(candidate):
    """Prepare and switch the staging backend."""
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate)
        or image(candidate) != candidate
    ):
        fail("Candidate must be an existing immutable image ID.")
    old_bytes = pinned_bytes(OLD, OLD_HASH)
    checked_file(NEW, NEW_HASH)
    if STATE.exists() or os.path.lexists(STATE) or image(BACKUP) is not None:
        fail("Recovery record or preservation tag already exists; reconcile first.")
    c = container()
    if not c:
        fail("Old container missing.")
    env = values(c)
    oldid = c["Image"]
    if oldid == candidate or image(TAG) != oldid:
        fail("Image identity or local tag mismatch.")
    # The exact byte snapshot, not the writable original, is the only old input
    # ever passed to Compose. Reject if relocation changes its config hash.
    trusted(STATE.parent)
    STATE.mkdir(mode=0o700)
    os.chmod(STATE, 0o700)
    private_state()
    durable(STATE / "old-compose.yaml", old_bytes)
    private_file(STATE / "old-compose.yaml")
    oldhash = config_hash(STATE / "old-compose.yaml", env)
    verify(c, oldid, OLD, env, oldhash, True)
    newhash = config_hash(NEW, env)
    # Record is durable before the first image/container mutation.
    record = {
        "old_id": oldid,
        "candidate": candidate,
        "old_hash": oldhash,
        "new_hash": newhash,
        "env": env,
        "container_id": c["Id"],
        "old_runtime": runtime(c),
    }
    checked_file(STATE / "old-compose.yaml", OLD_HASH)
    durable(STATE / "record.json", json.dumps(record).encode())
    sync_dir(STATE.parent)
    private_file(STATE / "record.json")
    checked_file(STATE / "old-compose.yaml", OLD_HASH)
    checked_file(NEW, NEW_HASH)
    check_old_before_tag(record, oldid, None)
    run("tag", oldid, BACKUP)
    if image(BACKUP) != oldid:
        fail("Preservation tag verification failed.")
    checked_file(STATE / "old-compose.yaml", OLD_HASH)
    checked_file(NEW, NEW_HASH)
    check_old_before_tag(record, oldid, oldid)
    if image(candidate) != candidate:
        fail("Candidate image drift before tag mutation.")
    run("tag", candidate, TAG)
    if image(TAG) != candidate or image(BACKUP) != oldid:
        fail("Image tag verification failed; recover.")
    check_old_before_tag(record, candidate, oldid)
    compose(
        NEW,
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
    verify(container(), candidate, NEW, env, newhash, False)
    healthy()
    candidate_container = container()
    verify(candidate_container, candidate, NEW, env, newhash, False)
    baseline = {
        "runtime": runtime(candidate_container),
        "env": environment(candidate_container),
    }
    durable(STATE / "candidate.json", json.dumps(baseline).encode())
    private_file(STATE / "candidate.json")
    print(
        "Migration complete; independently verify authentication and routing. "
        "Record retained."
    )


def recover():  # noqa: C901
    """Restore the old backend from a private snapshot."""
    private_file(STATE / "record.json")
    private_file(STATE / "old-compose.yaml")
    checked_file(STATE / "old-compose.yaml", OLD_HASH)
    try:
        r = json.loads((STATE / "record.json").read_text())
    except (ValueError, OSError):
        fail("Recovery record is unreadable or incomplete.")
    snapshot = STATE / "old-compose.yaml"
    env = r["env"]
    snapshot_hash = config_hash(snapshot, env)
    if snapshot_hash != r["old_hash"]:
        fail("Snapshot Compose hash drift; manual recovery required.")
    if image(BACKUP) not in (None, r["old_id"]) or image(TAG) not in (
        r["old_id"],
        r["candidate"],
    ):
        fail("Image tag drift; manual recovery required.")
    if image(r["old_id"]) != r["old_id"]:
        fail("Old image is missing; manual recovery required.")
    c = container()
    if c:
        if c["Image"] not in (r["old_id"], r["candidate"]):
            fail("Unexpected container image; manual recovery required.")
        path = NEW
        expected_hash = r["new_hash"]
        if c["Image"] == r["old_id"]:
            labels = c["Config"]["Labels"]
            path = (
                snapshot
                if labels.get("com.docker.compose.project.config_files")
                == str(snapshot)
                else OLD
            )
            expected_hash = snapshot_hash if path == snapshot else r["old_hash"]
        if c["Image"] == r["old_id"]:
            expected_runtime = r["old_runtime"]
        else:
            baseline = STATE / "candidate.json"
            if os.path.lexists(baseline):
                private_file(baseline)
                try:
                    saved = json.loads(baseline.read_text())
                except (OSError, ValueError):
                    fail("Candidate baseline is unreadable; manual recovery required.")
                expected_runtime = saved["runtime"]
                expected_env = saved["env"]
            else:
                # Only the already-recorded old runtime is trusted without a
                # candidate baseline. Anything else needs manual reconciliation.
                expected_runtime = r["old_runtime"]
                expected_env = dict(env, STAGING_MCP_HOST=HOST)
            if environment(c) != expected_env:
                fail("Candidate environment drift; manual recovery required.")
        if runtime(c) != expected_runtime:
            fail("Container runtime drift; manual recovery required.")
        # A stopped container may be left by an interrupted Compose recreation.
        check = dict(c)
        check["State"] = dict(c["State"], Running=True)
        verify(check, c["Image"], path, env, expected_hash, c["Image"] == r["old_id"])

    def recheck(expected_backup, expected_tag):
        current = container()
        if (
            (current is None) != (c is None)
            or (
                current is not None
                and c is not None
                and (
                    current["Id"] != c["Id"]
                    or current["Image"] != c["Image"]
                    or current["Config"] != c["Config"]
                    or current.get("HostConfig") != c.get("HostConfig")
                    or current["State"].get("Running") != c["State"].get("Running")
                )
            )
            or image(BACKUP) != expected_backup
            or image(TAG) != expected_tag
            or image(r["old_id"]) != r["old_id"]
        ):
            fail("Drift detected immediately before recovery tag mutation.")
        checked_file(snapshot, OLD_HASH)
        if config_hash(snapshot, env) != r["old_hash"]:
            fail("Snapshot Compose hash drift; manual recovery required.")

    backup, tag = image(BACKUP), image(TAG)
    if backup not in (None, r["old_id"]) or tag not in (r["old_id"], r["candidate"]):
        fail("Image tag drift; manual recovery required.")
    if backup is None:
        recheck(None, tag)
        run("tag", r["old_id"], BACKUP)
    recheck(r["old_id"], tag)
    run("tag", r["old_id"], TAG)
    recheck(r["old_id"], r["old_id"])
    compose(
        snapshot,
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
    verify(container(), r["old_id"], snapshot, env, snapshot_hash, True)
    if runtime(container()) != r["old_runtime"]:
        fail("Restored runtime differs from captured baseline; remain closed.")
    healthy()
    print(
        "Old backend restored; independently verify authentication and routing. "
        "Record retained."
    )


def main():
    """Run the guarded command-line entry point."""
    if os.geteuid() != 0 or len(sys.argv) not in (2, 3):
        fail("Run as root: upgrade.py switch IMAGE_ID or upgrade.py recover")
    trusted(LOCK)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        fail("Lock is not a regular file.")
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if sys.argv[1] == "switch" and len(sys.argv) == 3:
            fail("Switch disabled: old runtime reproducibility is not yet proven.")
        elif sys.argv[1] == "recover" and len(sys.argv) == 2:
            recover()
        else:
            fail("Invalid command.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        # Never print subprocess output or sensitive values.
        print(
            "Upgrade stopped:",
            str(exc)
            if isinstance(exc, RuntimeError)
            else "unexpected error; inspect privately",
            file=sys.stderr,
        )
        sys.exit(1)
