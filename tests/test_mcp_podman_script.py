"""Exercise local lifecycle decisions without requiring a Podman engine."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mcp-podman.sh"


def invoke(tmp_path, action, **env):
    """Run the script against a configurable fake Podman command."""
    podman = tmp_path / "podman"
    podman.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$LOG"
case "$1 $2" in
  'info ') [[ ${DOWN:-0} != 1 || -f "$LOG.started" ]] ;;
  'machine start') touch "$LOG.started" ;;
  'container exists') [[ ${EXISTS:-0} == 1 ]] ;;
  'inspect --format') echo "${OWNER:-site-directedideation.local-mcp}" ;;
  'run --detach') [[ ${RUN_FAIL:-0} != 1 ]] ;;
  *) exit 0 ;;
esac
"""
    )
    podman.chmod(0o755)
    log = tmp_path / "log"
    result = subprocess.run(
        [str(SCRIPT), action],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "LOG": str(log),
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text().splitlines()


def test_start_builds_and_starts_machine(tmp_path):
    """Build before replacing the managed container."""
    result, calls = invoke(tmp_path, "start", DOWN="1", EXISTS="1")
    assert result.returncode == 0, result.stderr
    assert "machine start" in calls
    assert next(i for i, c in enumerate(calls) if c.startswith("build ")) < calls.index(
        "rm --force directedideation-local-mcp"
    )
    assert any("directedideation-local-mcp-metrics:/metrics" in c for c in calls)
    assert "localhost port 8001" in result.stdout
    assert "http://127.0.0.1:8001/mcp" in result.stdout


def test_stop_does_not_touch_other_services_or_volume(tmp_path):
    """Stop only the managed container."""
    result, calls = invoke(tmp_path, "stop", EXISTS="1")
    assert result.returncode == 0
    assert calls[-1] == "stop --ignore directedideation-local-mcp"
    assert not any(c.startswith(("rm ", "volume ", "machine stop")) for c in calls)


def test_foreign_container_is_not_modified(tmp_path):
    """Reject an existing container with a different owner."""
    result, calls = invoke(tmp_path, "start", EXISTS="1", OWNER="other")
    assert result.returncode != 0
    assert not any(c.startswith(("build ", "rm ", "run ")) for c in calls)


def test_port_failure_is_reported(tmp_path):
    """Explain a failed port bind without stopping other services."""
    result, _ = invoke(tmp_path, "start", RUN_FAIL="1")
    assert result.returncode != 0
    assert "port 8001" in result.stderr
