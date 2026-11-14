#!/usr/bin/env python3
"""One-time, operator-invoked HTTP-01 vhost installation. See README-http01.md."""

import fcntl
import hashlib
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path

SOURCE = Path("/home/kent/di-production-acme-178bb690.conf")
TARGET = Path("/etc/nginx/conf.d/di-production-acme.conf")
PUBLIC = Path("/etc/nginx/conf.d/di-staging-public-test.conf")
LOCK = Path("/var/lib/di-shared-test/lock")
WEBROOT = Path("/var/lib/di-staging-acme")
SOURCE_HASH = "178bb69096c437e5474e2f0af3e472d50435d4eae9c751d350089c60b7195d1f"
PUBLIC_HASH = "7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530"
LIMIT = 1024 * 1024


def trusted_dir(path):
    """Perform the trusted dir operation."""
    for part in (path, *path.parents):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError(f"untrusted directory: {part}")


def read_file(path, trusted=False):
    """Perform the read file operation."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise RuntimeError(f"not a bounded regular file: {path}")
        if trusted and (info.st_uid != 0 or info.st_mode & 0o022):
            raise RuntimeError(f"untrusted file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise RuntimeError(f"file too large: {path}")
        return data
    finally:
        os.close(fd)


def check(data, expected):
    """Perform the check operation."""
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("digest mismatch")


def command(*args):
    """Perform the command operation."""
    return subprocess.run(
        args, check=True, timeout=10, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


def install():  # noqa: C901
    """Install the pinned vhost with recovery on failure."""
    for directory in (LOCK.parent, TARGET.parent, Path("/var/lib")):
        trusted_dir(directory)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise RuntimeError("untrusted lock")
        # Bounded wait, matching the other nginx transitions.
        import time

        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("nginx lock timeout")
                time.sleep(0.1)
        for unit in (
            "di-shared-test-rollback-once.timer",
            "di-shared-test-rollback-once.service",
        ):
            if (
                command("systemctl", "show", unit, "-p", "ActiveState", "--value")
                != "inactive"
            ):
                raise RuntimeError(f"{unit} not inactive")
        check(read_file(PUBLIC, trusted=True), PUBLIC_HASH)
        data = read_file(SOURCE)
        check(data, SOURCE_HASH)
        # Never follow or replace an existing target, including dangling symlinks.
        if os.path.lexists(TARGET):
            raise RuntimeError("target already exists")
        WEBROOT.mkdir(mode=0o755, exist_ok=True)
        trusted_dir(WEBROOT)
        if WEBROOT.stat().st_mode & 0o005 != 0o005:
            raise RuntimeError("webroot is not readable and searchable by nginx")
        for child in (WEBROOT / ".well-known", WEBROOT / ".well-known/acme-challenge"):
            child.mkdir(mode=0o755, exist_ok=True)
            trusted_dir(child)
            if child.stat().st_mode & 0o005 != 0o005:
                raise RuntimeError(f"webroot directory not accessible: {child}")
        # Write a private temporary file outside nginx's *.conf include pattern,
        # then publish with an exclusive hard link, never overwriting a target.
        import tempfile

        temp_fd, temp_name = tempfile.mkstemp(prefix=".di-http01-", dir=TARGET.parent)
        temp = Path(temp_name)
        published = False
        identity = None
        try:
            with os.fdopen(temp_fd, "wb") as out:
                out.write(data)
                out.flush()
                os.fchmod(out.fileno(), 0o644)
                os.fsync(out.fileno())
                st = os.fstat(out.fileno())
                identity = (st.st_dev, st.st_ino)
            blocked = {signal.SIGHUP, signal.SIGINT, signal.SIGTERM}
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
            try:
                os.link(temp, TARGET, follow_symlinks=False)
                published = True
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            check(read_file(TARGET, trusted=True), SOURCE_HASH)
            command("nginx", "-t")
            command("systemctl", "reload", "nginx.service")
        except BaseException:
            if published:
                try:
                    st = TARGET.lstat()
                    if (st.st_dev, st.st_ino) != identity:
                        raise RuntimeError("target changed; refusing removal")
                    check(read_file(TARGET, trusted=True), SOURCE_HASH)
                    TARGET.unlink()
                    check(read_file(PUBLIC, trusted=True), PUBLIC_HASH)
                    command("nginx", "-t")
                    command("systemctl", "reload", "nginx.service")
                    print(
                        "Recovery reload requested; independently verify nginx.",
                        file=sys.stderr,
                    )
                except BaseException as error:
                    print(
                        f"RECOVERY FAILED: {error}; "
                        "immediate operator intervention required",
                        file=sys.stderr,
                    )
            raise
        finally:
            temp.unlink(missing_ok=True)
    finally:
        os.close(fd)


def main():
    """Perform the main operation."""
    if len(sys.argv) != 1 or os.geteuid() != 0:
        print("Run as root with no arguments.", file=sys.stderr)
        return 1
    os.umask(0o022)
    os.environ["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"

    def interrupted(signum, _frame):
        raise RuntimeError(f"interrupted by signal {signum}")

    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    try:
        install()
    except Exception as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    print("HTTP-01 vhost installed; verify nginx and external routes independently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
