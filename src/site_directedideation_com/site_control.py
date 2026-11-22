"""Control a separately tracked local live-reloading website server."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from site_directedideation_com import dev, site_server

STATE_DIR = dev.STATE_DIR / "site-control"
SITE_ROOT = site_server.DEFAULT_SITE_ROOT
DEFAULT_PORT = 3000


def _read_tracked_state(state_dir: Path) -> dev.ServerState | None:
    state = dev._read_state(state_dir)
    if state is None and dev._state_path(state_dir).exists():
        raise RuntimeError(
            "Site state is unreadable; investigate it before proceeding."
        )
    if state is not None and (
        len(state.services) != 1 or state.services[0].name != "Site"
    ):
        raise RuntimeError("Invalid Site state; investigate it before proceeding.")
    return state


def _start_locked(state_dir: Path, port: int) -> int:
    state = _read_tracked_state(state_dir)
    if state is not None:
        service = state.services[0]
        ownership, reason = dev._classify_process(service)
        if ownership == dev._Ownership.UNCERTAIN:
            raise RuntimeError(f"Cannot verify tracked Site process: {reason}")
        if ownership == dev._Ownership.OWNED:
            raise RuntimeError(f"Site is already running on port {service.port}.")
        dev._remove_state(state_dir)
    if not SITE_ROOT.is_dir():
        raise RuntimeError(f"Site root does not exist: {SITE_ROOT}")
    command = [
        sys.executable,
        "-m",
        "site_directedideation_com.site_server",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--root",
        str(SITE_ROOT),
    ]
    state = dev._start_services([("Site", command, dev.PROJECT_ROOT, port)], state_dir)
    print(f"Site started: http://127.0.0.1:{state.services[0].port}/")
    print(f"Log: {dev._log_path(state_dir, 'Site')}")
    return 0


def _stop_locked(state_dir: Path) -> int:
    state = _read_tracked_state(state_dir)
    if state is None:
        raise RuntimeError("Site is not running (no tracked process).")
    ownership, reason = dev._classify_process(state.services[0])
    if ownership == dev._Ownership.UNCERTAIN:
        raise RuntimeError(f"Cannot verify tracked Site process: {reason}")
    if ownership != dev._Ownership.OWNED:
        dev._remove_state(state_dir)
        raise RuntimeError("Site is not running (tracked process is gone).")
    result = dev._stop_services(state)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if result.uncertain or result.failed:
        raise RuntimeError("Site could not be safely stopped; state retained.")
    dev._remove_state(state_dir)
    print("Site stopped.")
    return state.services[0].port


def _lifecycle(state_dir: Path, command: str, port: int = DEFAULT_PORT) -> int:
    with dev._acquire_lock(state_dir):
        if command == "start":
            return _start_locked(state_dir, port)
        previous_port = _stop_locked(state_dir)
        if command == "restart":
            return _start_locked(state_dir, previous_port)
        return 0


def main(argv: list[str] | None = None) -> int:
    """Run the local website lifecycle command."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="start the local site in the background")
    start.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"localhost port (default: {DEFAULT_PORT})",
    )
    commands.add_parser("stop", help="stop the tracked site process")
    commands.add_parser("restart", help="restart the site on its current port")
    commands.add_parser("log", help="follow the site log (Ctrl-C to exit)")
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            if not 1 <= args.port <= 65535:
                raise RuntimeError("Port must be between 1 and 65535.")
            return _lifecycle(STATE_DIR, "start", args.port)
        if args.command in ("stop", "restart"):
            return _lifecycle(STATE_DIR, args.command)
        path = dev._log_path(STATE_DIR, "Site")
        if not path.exists():
            raise RuntimeError("No Site log yet; start the server first.")
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
