"""Run local development services together."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _services() -> list[tuple[str, list[str], Path]]:
    """Return the commands and working directories for development services."""
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
                "8000",
            ],
            PROJECT_ROOT,
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
                "8001",
            ],
            PROJECT_ROOT,
        ),
        (
            "Static site",
            [npm, "run", "dev", "--", "--host=127.0.0.1", "--port=3000"],
            PROJECT_ROOT / "site",
        ),
    ]


def _stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop all child processes, including their process groups."""
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    deadline = time.monotonic() + 5
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main() -> None:
    """Start the API, MCP server, and static-site development server."""
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for name, command, cwd in _services():
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
        print("Stopping development services...", flush=True)
    finally:
        _stop_processes(processes)
