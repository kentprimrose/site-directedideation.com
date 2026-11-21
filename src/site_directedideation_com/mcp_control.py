"""Control a separately tracked local MCP server."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from site_directedideation_com import dev

STATE_DIR = dev.STATE_DIR / "mcp-control"


def _read_tracked_state(state_dir: Path) -> dev.ServerState | None:
    state = dev._read_state(state_dir)
    if state is None and dev._state_path(state_dir).exists():
        raise RuntimeError("MCP state is unreadable; investigate it before proceeding.")
    if state is not None and (
        len(state.services) != 1 or state.services[0].name != "MCP"
    ):
        raise RuntimeError("Invalid MCP state; investigate it before proceeding.")
    return state


def _start_locked(state_dir: Path, port: int) -> int:
    state = _read_tracked_state(state_dir)
    if state is not None:
        service = state.services[0]
        ownership, reason = dev._classify_process(service)
        if ownership == dev._Ownership.UNCERTAIN:
            raise RuntimeError(f"Cannot verify tracked MCP process: {reason}")
        if ownership == dev._Ownership.OWNED:
            raise RuntimeError(f"MCP is already running on port {service.port}.")
        dev._remove_state(state_dir)
    fastmcp = shutil.which("fastmcp")
    if fastmcp is None:
        raise RuntimeError("fastmcp must be available on PATH; use uv run.")
    command = [
        fastmcp,
        "run",
        "src/site_directedideation_com/mcp/__init__.py:mcp",
        "--transport",
        "streamable-http",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    state = dev._start_services([("MCP", command, dev.PROJECT_ROOT, port)], state_dir)
    print(f"MCP started: http://127.0.0.1:{state.services[0].port}/mcp")
    print(f"Log: {dev._log_path(state_dir, 'MCP')}")
    return 0


def _stop_locked(state_dir: Path) -> int:
    state = _read_tracked_state(state_dir)
    if state is None:
        raise RuntimeError("MCP is not running (no tracked process).")
    ownership, reason = dev._classify_process(state.services[0])
    if ownership == dev._Ownership.UNCERTAIN:
        raise RuntimeError(f"Cannot verify tracked MCP process: {reason}")
    if ownership != dev._Ownership.OWNED:
        dev._remove_state(state_dir)
        raise RuntimeError("MCP is not running (tracked process is gone).")
    result = dev._stop_services(state)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if result.uncertain or result.failed:
        raise RuntimeError("MCP could not be safely stopped; state retained.")
    dev._remove_state(state_dir)
    print("MCP stopped.")
    return state.services[0].port


def _lifecycle(state_dir: Path, command: str, port: int = 8001) -> int:
    with dev._acquire_lock(state_dir):
        if command == "start":
            return _start_locked(state_dir, port)
        previous_port = _stop_locked(state_dir)
        if command == "restart":
            return _start_locked(state_dir, previous_port)
        return 0


def main(argv: list[str] | None = None) -> int:
    """Run the local MCP lifecycle command."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="start MCP in the background")
    start.add_argument(
        "--port", type=int, default=8001, help="localhost port (default: 8001)"
    )
    commands.add_parser("stop", help="stop the tracked MCP process")
    commands.add_parser("restart", help="restart MCP on its current port")
    commands.add_parser("log", help="follow the MCP log (Ctrl-C to exit)")
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            if not 1 <= args.port <= 65535:
                raise RuntimeError("Port must be between 1 and 65535.")
            return _lifecycle(STATE_DIR, "start", args.port)
        if args.command in ("stop", "restart"):
            return _lifecycle(STATE_DIR, args.command)
        path = dev._log_path(STATE_DIR, "MCP")
        if not path.exists():
            raise RuntimeError("No MCP log yet; start the server first.")
        try:
            return subprocess.run(
                ["tail", "-n", "+1", "-f", str(path)], check=False
            ).returncode
        except KeyboardInterrupt:
            return 0
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
