"""Run local development services together."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import enum
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / ".dev"

# Dev ports are hard-coded in ``_services`` to match the README.  These are the
# only ports the background lifecycle commands know about; unrelated listeners
# are never killed automatically.
_API_PORT = 8000
_MCP_PORT = 8001
_STATIC_PORT = 3000

# Seconds to wait for all services to bind their ports before treating the
# launch as failed.
_READINESS_TIMEOUT = 30.0

# Small Python wrapper run as the session leader for each service.  It keeps a
# stable, token-bearing command line even when the child (e.g. npm) rewrites its
# own title, and it forwards signals to the child process group.
_WRAPPER_CODE = """\
import contextlib
import os
import signal
import subprocess
import sys

_token = sys.argv[1]
_cwd = sys.argv[2]
_log_path = sys.argv[3]
_command = sys.argv[4:]

with open(_log_path, "ab") as _log_file:
    _proc = subprocess.Popen(
        _command,
        cwd=_cwd or None,
        stdout=_log_file,
        stderr=_log_file,
    )

    def _forward(signum, _frame):
        signal.signal(signum, signal.SIG_IGN)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgrp(), signum)
    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    _rc = _proc.wait()
sys.exit(_rc)
"""


class _Ownership(enum.Enum):
    """Classification of a recorded PID when deciding whether to stop it."""

    OWNED = "owned"
    DEAD = "dead"
    UNCERTAIN = "uncertain"


@dataclass
class ServiceState:
    """Persisted state for one background service."""

    name: str
    pid: int
    pgid: int
    port: int
    command: list[str]
    identity: list[str] = field(default_factory=list)


@dataclass
class ServerState:
    """Persisted state for a dev-server run."""

    run_id: str
    started_at: datetime.datetime
    services: list[ServiceState]


@dataclass
class _StopResult:
    """Outcome of a stop attempt."""

    warnings: list[str]
    uncertain: list[ServiceState]
    failed: list[ServiceState]


def _services() -> list[tuple[str, list[str], Path, int]]:
    """Return the commands, working directories and ports for dev services."""
    fastmcp = shutil.which("fastmcp")
    npm = shutil.which("npm")
    if fastmcp is None or npm is None:
        raise RuntimeError("The fastmcp and npm executables must be available on PATH.")

    return [
        (
            "API",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "site_directedideation_com.api:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                str(_API_PORT),
            ],
            PROJECT_ROOT,
            _API_PORT,
        ),
        (
            "MCP",
            [
                fastmcp,
                "run",
                "src/site_directedideation_com/mcp/__init__.py:mcp",
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(_MCP_PORT),
            ],
            PROJECT_ROOT,
            _MCP_PORT,
        ),
        (
            "Static site",
            [npm, "run", "dev", "--", "--host=127.0.0.1", f"--port={_STATIC_PORT}"],
            PROJECT_ROOT / "site",
            _STATIC_PORT,
        ),
    ]


def _state_path(state_dir: Path) -> Path:
    """Path to the JSON state file."""
    return state_dir / "dev-server-state.json"


def _lock_path(state_dir: Path) -> Path:
    """Path to the runtime lock file."""
    return state_dir / "dev-server.lock"


def _log_path(state_dir: Path, name: str) -> Path:
    """Path to a service log file."""
    safe = name.lower().replace(" ", "-")
    return state_dir / "logs" / f"{safe}.log"


@contextlib.contextmanager
def _acquire_lock(state_dir: Path) -> Any:
    """Acquire an exclusive, non-blocking POSIX lock for dev-server commands."""
    lock_file = _lock_path(state_dir)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError as exc:
        raise RuntimeError(
            "Another dev server command is already running. Wait for it to finish."
        ) from exc
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(fd)


def _state_to_dict(state: ServerState) -> dict[str, Any]:
    """Serialize server state to a plain dictionary."""
    return {
        "run_id": state.run_id,
        "started_at": state.started_at.isoformat(),
        "services": [
            {
                "name": service.name,
                "pid": service.pid,
                "pgid": service.pgid,
                "port": service.port,
                "command": service.command,
                "identity": service.identity,
            }
            for service in state.services
        ],
    }


def _state_from_dict(data: dict[str, Any]) -> ServerState:
    """Deserialize server state from a plain dictionary."""
    started_at = datetime.datetime.fromisoformat(data["started_at"])
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=datetime.UTC)
    return ServerState(
        run_id=data["run_id"],
        started_at=started_at,
        services=[
            ServiceState(
                name=service["name"],
                pid=service["pid"],
                pgid=service["pgid"],
                port=service["port"],
                command=service["command"],
                identity=service.get("identity", []),
            )
            for service in data["services"]
        ],
    )


def _read_state(state_dir: Path) -> ServerState | None:
    """Read persisted server state, or ``None`` if none exists."""
    path = _state_path(state_dir)
    if not path.exists():
        return None
    try:
        return _state_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except OSError, json.JSONDecodeError, KeyError, ValueError:
        return None


def _write_state(state_dir: Path, state: ServerState) -> None:
    """Persist server state to disk."""
    path = _state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_state_to_dict(state), indent=2), encoding="utf-8")


def _remove_state(state_dir: Path) -> None:
    """Remove persisted server state if it exists."""
    with contextlib.suppress(OSError):
        _state_path(state_dir).unlink()


def _port_is_occupied(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return ``True`` if something is listening on ``host:port``."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _get_cmdline(pid: int) -> list[str] | None:
    """Return the command-line list for ``pid``, or ``None`` if unavailable."""
    proc_path = Path(f"/proc/{pid}/cmdline")
    try:
        if proc_path.exists():
            raw = proc_path.read_bytes()
            parts = raw.decode("utf-8", errors="replace").split("\x00")
            return [part for part in parts if part]
    except OSError, PermissionError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip().split()
    except OSError, subprocess.TimeoutExpired:
        pass
    return None


def _signature_tokens(service: ServiceState) -> list[str]:
    """Return the recorded identity tokens for ``service``."""
    return service.identity


def _check_process_group(service: ServiceState) -> tuple[bool, bool, str]:
    """Check whether the recorded PID/process group is alive and accessible.

    Returns ``(alive, uncertain, reason)``.  ``uncertain`` means the process may
    be alive but we cannot safely confirm ownership.
    """
    try:
        os.kill(service.pid, 0)
        actual_pgid = os.getpgid(service.pid)
    except ProcessLookupError:
        return False, False, f"PID {service.pid} for {service.name} is gone"
    except (PermissionError, OSError) as exc:
        return (
            False,
            True,
            (f"PID {service.pid} for {service.name} is not accessible: {exc}"),
        )

    if actual_pgid != service.pgid:
        return (
            False,
            True,
            (
                f"PID {service.pid} for {service.name} is in process group "
                f"{actual_pgid}, not recorded {service.pgid}"
            ),
        )

    try:
        os.killpg(service.pgid, 0)
    except ProcessLookupError:
        return (
            False,
            False,
            f"process group {service.pgid} for {service.name} is gone",
        )
    except (PermissionError, OSError) as exc:
        return (
            False,
            True,
            (
                f"process group {service.pgid} for {service.name} "
                f"is not accessible: {exc}"
            ),
        )

    return True, False, ""


def _classify_process(service: ServiceState) -> tuple[_Ownership, str]:
    """Classify a recorded PID as owned, dead, or uncertain.

    Uncertain processes are never killed and are left in state so the user can
    investigate manually.
    """
    if service.pid <= 1 or service.pgid <= 1 or service.pid != service.pgid:
        return _Ownership.UNCERTAIN, (
            f"PID {service.pid} for {service.name} has an implausible identity"
        )

    alive, uncertain, reason = _check_process_group(service)
    if uncertain:
        return _Ownership.UNCERTAIN, reason
    if not alive:
        return _Ownership.DEAD, reason

    identity = _signature_tokens(service)
    if not identity:
        return _Ownership.UNCERTAIN, (
            f"PID {service.pid} for {service.name} has no recorded identity token"
        )

    current_cmdline = _get_cmdline(service.pid)
    if current_cmdline is None:
        return _Ownership.UNCERTAIN, (
            f"cannot read command line for PID {service.pid} ({service.name})"
        )

    for token in identity:
        if token not in current_cmdline:
            return _Ownership.UNCERTAIN, (
                f"PID {service.pid} for {service.name} does not contain the "
                f"recorded identity token (stale or reused PID)"
            )

    return _Ownership.OWNED, ""


def _stop_process_group(pgid: int, sig: int) -> None:
    """Send a signal to a process group, ignoring lookup errors."""
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, sig)


def _wait_for_group_exit(service: ServiceState, deadline: float) -> tuple[bool, bool]:
    """Wait until ``service``'s process group is gone, reaping the leader eagerly.

    Returns ``(gone, leader_reaped)``.  ``gone`` is True only when the whole
    process group has disappeared, not merely when the leader was reaped.
    """
    leader_reaped = False
    while time.monotonic() < deadline:
        if not leader_reaped:
            try:
                reaped, _ = os.waitpid(service.pid, os.WNOHANG)
                if reaped == service.pid:
                    leader_reaped = True
            except ChildProcessError, OSError:
                leader_reaped = True
        try:
            os.killpg(service.pgid, 0)
        except ProcessLookupError, PermissionError, OSError:
            return True, leader_reaped
        time.sleep(0.05)
    return False, leader_reaped


def _stop_one_service(service: ServiceState, deadline: float) -> str | None:
    """Stop one owned service and reap it; return a warning if it won't die."""
    _stop_process_group(service.pgid, signal.SIGTERM)

    gone, leader_reaped = _wait_for_group_exit(service, deadline)
    if not gone:
        _stop_process_group(service.pgid, signal.SIGKILL)
        gone, leader_reaped = _wait_for_group_exit(service, time.monotonic() + 2.5)
        if not gone:
            return f"Could not stop {service.name} process group {service.pgid}"

    # Eagerly reap the leader, but do not assume the group is empty just because
    # the leader died; the loops above only exit when the whole group is gone.
    if leader_reaped or gone:
        with contextlib.suppress(ChildProcessError, OSError):
            os.waitpid(service.pid, 0)
    return None


def _stop_services(state: ServerState, deadline_seconds: float = 10.0) -> _StopResult:
    """Stop all services in ``state``.

    Returns a result describing which services stopped cleanly, which could not
    be verified as owned (uncertain), and which were owned but could not be
    killed (failed).
    """
    owned: list[ServiceState] = []
    uncertain: list[ServiceState] = []
    dead: list[ServiceState] = []
    warnings: list[str] = []

    for service in state.services:
        classification, reason = _classify_process(service)
        if classification == _Ownership.OWNED:
            owned.append(service)
        elif classification == _Ownership.UNCERTAIN:
            uncertain.append(service)
            warnings.append(f"Skipping {service.name}: {reason}")
        else:
            dead.append(service)
            warnings.append(f"Skipping {service.name}: {reason}")

    deadline = time.monotonic() + deadline_seconds
    for service in owned:
        _stop_process_group(service.pgid, signal.SIGTERM)

    failed: list[ServiceState] = []
    for service in owned:
        warning = _stop_one_service(service, deadline)
        if warning is not None:
            failed.append(service)
            warnings.append(warning)

    return _StopResult(warnings=warnings, uncertain=uncertain, failed=failed)


def _stop_command(state_dir: Path) -> int:
    """Implement ``dev stop``."""
    with _acquire_lock(state_dir):
        state = _read_state(state_dir)
        if state is None:
            print("No tracked dev server is running.")
            return 0

        print("Stopping tracked development services...")
        result = _stop_services(state)

        if result.uncertain or result.failed:
            for warning in result.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
            print(
                "Some services could not be verified or stopped. "
                "State retained; investigate before trying again.",
                file=sys.stderr,
            )
            return 1

        _remove_state(state_dir)
        for warning in result.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        print("Stopped.")
        return 0


def _wrap_service_command(
    command: list[str], cwd: Path, log_path: Path, token: str
) -> list[str]:
    """Wrap ``command`` in a token-bearing session-leader process."""
    return [
        sys.executable,
        "-c",
        _WRAPPER_CODE,
        token,
        str(cwd),
        str(log_path),
        *command,
    ]


def _wait_for_ports(
    services: list[ServiceState],
    procs: list[tuple[ServiceState, subprocess.Popen[bytes]]],
    timeout: float,
) -> tuple[bool, str]:
    """Wait until every service port is occupied and no child has exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for service, process in procs:
            if process.poll() is not None:
                return False, (
                    f"{service.name} exited before its port became ready "
                    f"(return code {process.returncode})"
                )
        if all(_port_is_occupied("127.0.0.1", service.port) for service in services):
            return True, ""
        time.sleep(0.25)
    unready = [
        service.name
        for service in services
        if not _port_is_occupied("127.0.0.1", service.port)
    ]
    return False, f"services did not become ready in time: {', '.join(unready)}"


def _start_services(
    services: list[tuple[str, list[str], Path, int]],
    state_dir: Path,
) -> ServerState:
    """Start ``services`` in the background and persist their state.

    If any service cannot start or become ready, already-launched services are
    stopped and state is removed before the function raises.
    """
    occupied = [
        (name, port)
        for name, _command, _cwd, port in services
        if _port_is_occupied("127.0.0.1", port)
    ]
    if occupied:
        details = "\n".join(
            f"  Port {port} for {name} is occupied. Investigate with: lsof -i :{port}"
            for name, port in occupied
        )
        raise RuntimeError(
            f"Cannot start because some dev ports are already occupied:\n{details}\n"
            "If these are old untracked servers, stop them manually and try again."
        )

    run_id = uuid.uuid4().hex
    started_at = datetime.datetime.now(tz=datetime.UTC)
    state = ServerState(run_id=run_id, started_at=started_at, services=[])
    procs: list[tuple[ServiceState, subprocess.Popen[bytes]]] = []

    try:
        for name, command, cwd, port in services:
            log_file_path = _log_path(state_dir, name)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            wrapped_command = _wrap_service_command(command, cwd, log_file_path, token)

            try:
                process = subprocess.Popen(
                    wrapped_command,
                    cwd=cwd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise RuntimeError(f"Failed to spawn {name}: {exc}") from exc

            service = ServiceState(
                name=name,
                pid=process.pid,
                pgid=process.pid,
                port=port,
                command=wrapped_command,
                identity=[token],
            )
            state.services.append(service)
            procs.append((service, process))

        # Give processes a moment to fail immediately (e.g. missing interpreter).
        time.sleep(0.1)
        for service, process in procs:
            if process.poll() is not None:
                raise RuntimeError(
                    f"{service.name} exited immediately with code "
                    f"{process.returncode}. "
                    f"See logs: {_log_path(state_dir, service.name)}"
                )

        ready, reason = _wait_for_ports(state.services, procs, _READINESS_TIMEOUT)
        if not ready:
            raise RuntimeError(f"Services did not become ready: {reason}")

        _write_state(state_dir, state)
    except BaseException:
        # Ctrl-C during readiness must not orphan untracked process groups.
        try:
            _stop_services(state)
        except Exception as cleanup_exc:
            print(
                f"Warning: cleanup after startup failure failed: {cleanup_exc}",
                file=sys.stderr,
            )
        _remove_state(state_dir)
        raise

    return state


def _any_tracked_process_alive(state: ServerState) -> bool:
    """Return whether any service in ``state`` is not confirmed dead."""
    for service in state.services:
        classification, _reason = _classify_process(service)
        if classification != _Ownership.DEAD:
            return True
    return False


def _start_command(
    services: list[tuple[str, list[str], Path, int]], state_dir: Path
) -> int:
    """Implement ``dev start``."""
    with _acquire_lock(state_dir):
        existing = _read_state(state_dir)
        if existing is not None:
            if _any_tracked_process_alive(existing):
                print(
                    "Tracked dev server appears to be running already. "
                    "Use 'restart' to replace it or 'stop' to shut it down.",
                    file=sys.stderr,
                )
                return 1
            # State file is stale (all tracked processes are dead).
            _remove_state(state_dir)

        state = _start_services(services, state_dir)
        print("Started development services in the background.")
        for service in state.services:
            print(f"  {service.name}: PID {service.pid} (port {service.port})")
        print(f"Logs: {state_dir / 'logs'}")
        print("API: http://127.0.0.1:8000/")
        print("MCP: http://127.0.0.1:8001/mcp")
        print("Site: http://127.0.0.1:3000/")
        print("Run 'uv run dev stop' to shut them down.")
        return 0


def _restart_command(
    services: list[tuple[str, list[str], Path, int]], state_dir: Path
) -> int:
    """Implement ``dev restart``."""
    with _acquire_lock(state_dir):
        existing = _read_state(state_dir)
        if existing is not None:
            print("Stopping existing dev server...")
            result = _stop_services(existing)
            if result.uncertain or result.failed:
                for warning in result.warnings:
                    print(f"Warning: {warning}", file=sys.stderr)
                print(
                    "Could not stop the existing server cleanly. "
                    "State retained; investigate before restarting.",
                    file=sys.stderr,
                )
                return 1
            _remove_state(state_dir)

        state = _start_services(services, state_dir)
        print("Restarted development services in the background.")
        for service in state.services:
            print(f"  {service.name}: PID {service.pid} (port {service.port})")
        print(f"Logs: {state_dir / 'logs'}")
        print("API: http://127.0.0.1:8000/")
        print("MCP: http://127.0.0.1:8001/mcp")
        print("Site: http://127.0.0.1:3000/")
        print("Run 'uv run dev stop' to shut them down.")
        return 0


def _stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop all foreground child processes, including their process groups."""
    for process in processes:
        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(process.pid, signal.SIGTERM)

    deadline = time.monotonic() + 5
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(process.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=1)


def _foreground(services: list[tuple[str, list[str], Path, int]]) -> int:
    """Start services in the foreground and block until interrupted."""
    processes: list[subprocess.Popen[bytes]] = []

    def _sigterm_handler(signum: int, _frame: Any) -> None:
        print(
            f"\nReceived signal {signum}, stopping development services...",
            flush=True,
        )
        _stop_processes(processes)
        sys.exit(128 + signum)

    old_handler = signal.signal(signal.SIGTERM, _sigterm_handler)
    try:
        for name, command, cwd, _port in services:
            print(f"Starting {name}: {' '.join(command)}", flush=True)
            processes.append(subprocess.Popen(command, cwd=cwd, start_new_session=True))

        print("API: http://127.0.0.1:8000/", flush=True)
        print("MCP: http://127.0.0.1:8001/mcp", flush=True)
        print("Site: http://127.0.0.1:3000/", flush=True)
        print("Press Ctrl-C to stop all services.", flush=True)

        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise RuntimeError(
                        f"A development service exited unexpectedly ({return_code})."
                    )
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopping development services...", flush=True)
        return 0
    finally:
        signal.signal(signal.SIGTERM, old_handler)
        _stop_processes(processes)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``dev`` (and optional ``servers``) console script."""
    using_system_argv = argv is None
    argv = sys.argv[1:] if using_system_argv else argv
    prog = Path(sys.argv[0]).name if using_system_argv else "dev"
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Start, stop, or restart local development services.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start", help="start services in the background")
    subparsers.add_parser("stop", help="stop tracked background services")
    subparsers.add_parser("restart", help="restart background services")

    args = parser.parse_args(argv)
    state_dir = STATE_DIR

    try:
        if args.command is None:
            services = _services()
            return _foreground(services)
        if args.command == "start":
            services = _services()
            return _start_command(services, state_dir)
        if args.command == "stop":
            return _stop_command(state_dir)
        if args.command == "restart":
            services = _services()
            return _restart_command(services, state_dir)
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help(file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
