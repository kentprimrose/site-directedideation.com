"""Exercise release marker behavior without a Docker daemon or remote host."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("healthy", [True, False])
def test_receiver_markers(tmp_path, healthy):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / "state"
    state.mkdir()
    old = "directed-ideation-mcp:" + "a" * 40
    previous = "directed-ideation-mcp:" + "b" * 40
    (state / "current-image").write_text(old + "\n")
    (state / "previous-image").write_text(previous + "\n")
    script = (root / "deploy/receive-image.sh").read_text().replace(
        "cd /opt/directed-ideation", f'cd "{tmp_path}"'
    )
    receiver = tmp_path / "receiver"
    receiver.write_text(script)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\n[ "$1" != compose ] || exit "$COMPOSE_STATUS"\n')
    docker.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", COMPOSE_STATUS=str(int(not healthy)))
    # macOS lacks flock; this stub suffices for this single-process test.
    flock = bin_dir / "flock"
    flock.write_text('#!/bin/sh\nexit 0\n')
    flock.chmod(0o755)
    sha = "c" * 40
    result = subprocess.run(["sh", str(receiver), sha], env=env, input=b"")
    assert (result.returncode == 0) == healthy
    assert (state / "current-image").read_text().strip() == (
        "directed-ideation-mcp:" + sha if healthy else old
    )
    assert (state / "previous-image").read_text().strip() == (old if healthy else previous)
    if healthy:
        subprocess.run(["sh", str(receiver), sha], env=env, input=b"", check=True)
        assert (state / "previous-image").read_text().strip() == old
