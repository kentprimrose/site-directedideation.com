#!/usr/bin/python3
"""Switch or recover the one staging Compose service; see MANUAL_SWITCH.md."""

# ruff: noqa: D101, D103, C901
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

DIR = Path("/etc/di-staging")
COMPOSE = DIR / "compose.yaml"
ORIGINAL_DIR = Path("/home/kent/di-pilot-build.eR6dNHdr")
ORIGINAL_COMPOSE = ORIGINAL_DIR / "compose.yaml"
PRIVATE = Path("/var/lib/di-staging-manual-upgrade")
SNAPSHOT = PRIVATE / "container.json"
OLD = PRIVATE / "old-compose.yaml"
LOCK = Path("/run/lock/di-staging-allowlist.lock")
NAME = "di-staging-staging-mcp-1"
TAG = "directed-ideation-staging-mcp:local"
ID = re.compile(r"^sha256:[0-9a-f]{64}$")
ENV_KEYS = (
    "WORKOS_STAGING_ISSUER",
    "WORKOS_STAGING_ALLOWED_SUBJECTS",
    "STAGING_MCP_HOST",
)
BASE_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
}


class Refusal(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def run(*args, env=None):
    try:
        p = subprocess.run(
            ["docker", "--host", "unix:///var/run/docker.sock", *args],
            env=env or BASE_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=True,
        )
        return p.stdout.decode().strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Refusal(
            "Docker or Compose command failed; inspect privately and recover manually"
        ) from None


def trusted(path, private=False):
    s = path.lstat()
    require(
        not stat.S_ISLNK(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
        "Untrusted path ownership, permissions, or symlink",
    )
    if private:
        require(not s.st_mode & 0o077, "Snapshot paths must be root-only")


def inspect():
    try:
        obj = json.loads(run("inspect", NAME))
        require(isinstance(obj, list) and len(obj) == 1, "Unexpected inspect result")
        return obj[0]
    except (ValueError, KeyError, TypeError):
        raise Refusal("Invalid container inspection") from None


def environment(container):
    result = {}
    for entry in container["Config"]["Env"]:
        key, sep, value = entry.partition("=")
        if key in ENV_KEYS:
            require(
                sep and key not in result and value and "\n" not in value,
                "Invalid or duplicate saved environment",
            )
            result[key] = value
    require(all(k in result for k in ENV_KEYS[:2]), "Missing saved environment")
    result.setdefault("STAGING_MCP_HOST", "mcp-staging.directedideation.com")
    require(
        result["STAGING_MCP_HOST"]
        in ("mcp-staging.directedideation.com", "mcp.directedideation.com"),
        "Unexpected host",
    )
    require(
        re.fullmatch(
            r"user_[A-Za-z0-9]+(,user_[A-Za-z0-9]+)*",
            result["WORKOS_STAGING_ALLOWED_SUBJECTS"],
        ),
        "Invalid allowlist",
    )
    return result


def identity(c, image, env, expected_hash, config_file, working_dir):
    labels = c["Config"]["Labels"]
    require(
        c["Config"]["Image"] == TAG
        and c["Image"] == image
        and labels.get("com.docker.compose.project") == "di-staging"
        and labels.get("com.docker.compose.service") == "staging-mcp"
        and labels.get("com.docker.compose.project.config_files") == str(config_file)
        and labels.get("com.docker.compose.project.working_dir") == str(working_dir)
        and labels.get("com.docker.compose.config-hash") == expected_hash
        and environment(c) == env,
        "Container identity, config, or environment drift",
    )


def image_id():
    return run("image", "inspect", "--format", "{{.Id}}", TAG)


def compose(file, env, *args):
    return run(
        "compose",
        "--project-name",
        "di-staging",
        "--project-directory",
        str(DIR),
        "-f",
        str(file),
        *args,
        env={**BASE_ENV, **env},
    )


def config_hash(file, env):
    output = compose(file, env, "config", "--hash", "staging-mcp")
    match = re.fullmatch(r"staging-mcp ([0-9a-f]{64})", output)
    if match is None:
        raise Refusal("Unexpected Compose hash output")
    return match.group(1)


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def healthy(image, env, expected_hash):
    for _ in range(60):
        c = inspect()
        identity(c, image, env, expected_hash, COMPOSE, DIR)
        require(c["State"]["Running"], "Container stopped after recreation")
        health = c["State"].get("Health", {}).get("Status")
        if health == "healthy":
            return
        require(health == "starting", "Container unhealthy or healthcheck missing")
        time.sleep(2)
    raise Refusal("Health check timed out")


def main():
    require(os.geteuid() == 0, "Run as root")
    require(
        len(sys.argv) == 5
        and sys.argv[1] in ("switch", "recover")
        and ID.fullmatch(sys.argv[2])
        and ID.fullmatch(sys.argv[3])
        and sys.argv[2] != sys.argv[3]
        and re.fullmatch(r"[0-9a-f]{64}", sys.argv[4]),
        "Usage: manual-switch.py switch|recover OLD_IMAGE_ID "
        "NEW_IMAGE_ID NEW_COMPOSE_SHA256",
    )
    action, old_image, new_image, new_digest = sys.argv[1:]
    for path in (Path("/"), Path("/etc"), DIR, COMPOSE, Path("/var"), Path("/var/lib")):
        trusted(path)
    for path in (PRIVATE, SNAPSHOT, OLD):
        trusted(path, private=True)
    require(
        SNAPSHOT.is_file() and OLD.is_file() and COMPOSE.is_file(),
        "Missing regular file",
    )
    require(
        not (DIR / ".env").exists() and not (DIR / ".env").is_symlink(),
        ".env is forbidden",
    )
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        lock_stat = os.fstat(lock.fileno())
        require(
            stat.S_ISREG(lock_stat.st_mode)
            and lock_stat.st_uid == 0
            and not lock_stat.st_mode & 0o022,
            "Untrusted lock file",
        )
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(SNAPSHOT.read_text())
        except (OSError, ValueError):
            raise Refusal("Cannot read saved inspection") from None
        require(isinstance(saved, list) and len(saved) == 1, "Invalid saved inspection")
        saved = saved[0]
        env = environment(saved)
        old_hash = saved["Config"]["Labels"]["com.docker.compose.config-hash"]
        require(re.fullmatch(r"[0-9a-f]{64}", old_hash), "Invalid saved config hash")
        identity(saved, old_image, env, old_hash, ORIGINAL_COMPOSE, ORIGINAL_DIR)
        require(
            config_hash(OLD, env) == old_hash,
            "Old snapshot does not reproduce saved config",
        )
        current_digest, old_digest = digest(COMPOSE), digest(OLD)
        require(
            current_digest.hex() == new_digest
            or (action == "recover" and current_digest == old_digest),
            "Unexpected Compose file; refusing to overwrite it",
        )
        new_hash = config_hash(COMPOSE, env)
        current = inspect()
        require(
            current["State"]["Running"],
            "Expected running container absent; manual intervention required",
        )
        if action == "switch":
            identity(current, old_image, env, old_hash, ORIGINAL_COMPOSE, ORIGINAL_DIR)
            require(current["Id"] == saved["Id"], "Container replaced since snapshot")
            require(
                image_id() == old_image, "Service tag is not the expected old image"
            )
            for image in (old_image, new_image):
                require(
                    run("image", "inspect", "--format", "{{.Id}}", image) == image,
                    "Required image unavailable",
                )
        else:
            # Only recognized states are eligible; absence is not authorization.
            require(
                current["Image"] in (old_image, new_image), "Unexpected current image"
            )
            original = current["Id"] == saved["Id"]
            require(
                not original or current["Image"] == old_image,
                "Unexpected snapshot image",
            )
            require(
                current["Image"] != new_image or current_digest.hex() == new_digest,
                "Cannot verify new container against restored config",
            )
            identity(
                current,
                current["Image"],
                env,
                old_hash if current["Image"] == old_image else new_hash,
                ORIGINAL_COMPOSE if original else COMPOSE,
                ORIGINAL_DIR if original else DIR,
            )
            require(
                image_id() in (old_image, new_image),
                "Unexpected tag; refusing recovery",
            )
        require(
            inspect()["Id"] == current["Id"]
            and digest(COMPOSE) == current_digest
            and digest(OLD) == old_digest,
            "State changed during checks",
        )
        if action == "recover":
            # Refuse to replace a config other than the one verified above. The lock
            # coordinates participants; administrators must exclude other writers.
            run("tag", old_image, TAG)
            require(image_id() == old_image, "Tag restoration failed")
            fd, temp = tempfile.mkstemp(prefix=".compose-recovery-", dir=DIR)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(OLD.read_bytes())
                    out.flush()
                    os.fsync(out.fileno())
                os.chmod(temp, 0o600)
                require(
                    digest(COMPOSE) == current_digest and digest(OLD) == old_digest,
                    "Config changed before restoration",
                )
                os.replace(temp, COMPOSE)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            target, target_hash = old_image, old_hash
        else:
            run("tag", new_image, TAG)
            require(image_id() == new_image, "Candidate retag failed")
            target, target_hash = new_image, new_hash
        require(
            image_id() == target and inspect()["Id"] == current["Id"],
            "State changed before recreation",
        )
        require(
            config_hash(COMPOSE, env) == target_hash,
            "Compose config changed before recreation",
        )
        compose(
            COMPOSE,
            env,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--no-deps",
            "staging-mcp",
        )
        require(image_id() == target, "Tag changed after recreation")
        healthy(target, env, target_hash)
        print("Service recreated and healthy; verify application behavior separately.")


if __name__ == "__main__":
    try:
        main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, IndexError):
        exc = sys.exc_info()[1]
        print(
            "Refused or failed: "
            + (
                str(exc)
                if isinstance(exc, Refusal)
                else "invalid or inaccessible state; inspect privately"
            ),
            file=sys.stderr,
        )
        sys.exit(1)
