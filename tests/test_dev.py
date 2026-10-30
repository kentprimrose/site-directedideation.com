"""Tests for the dev server lifecycle command."""

from __future__ import annotations

import contextlib
import datetime
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from site_directedideation_com.dev import (
    PROJECT_ROOT,
    ServerState,
    ServiceState,
    _acquire_lock,
    _classify_process,
    _get_cmdline,
    _Ownership,
    _port_is_occupied,
    _read_state,
    _restart_command,
    _start_command,
    _start_services,
    _state_path,
    _stop_command,
    _stop_services,
    _wrap_service_command,
)


def _find_free_port() -> int:
    """Return an OS-assigned free TCP port on 127.0.0.1."""
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _make_service(
    tmp_path: Path, name: str, port: int
) -> tuple[str, list[str], Path, int]:
    """Return a lightweight service that binds ``port`` and listens."""
    script = tmp_path / f"{name.replace(' ', '_')}_service.py"
    script.write_text(
        "import socket, sys, time\n"
        "port = int(sys.argv[1])\n"
        "with socket.socket() as s:\n"
        "    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "    s.bind(('127.0.0.1', port))\n"
        "    s.listen()\n"
        "    while True:\n"
        "        time.sleep(60)\n",
        encoding="utf-8",
    )
    return (name, [sys.executable, str(script), str(port)], tmp_path, port)


def _process_alive(pid: int) -> bool:
    """Return whether ``pid`` is still alive."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError, PermissionError, OSError:
        return False
    return True


def _run_identity_process(
    tmp_path: Path, port: int, token: str
) -> subprocess.Popen[bytes]:
    """Start a process whose command line contains ``token`` and binds ``port``."""
    script = tmp_path / "identity_service.py"
    script.write_text(
        "import socket, sys, time\n"
        "port = int(sys.argv[1])\n"
        "token = sys.argv[2]\n"
        "with socket.socket() as s:\n"
        "    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "    s.bind(('127.0.0.1', port))\n"
        "    s.listen()\n"
        "    while True:\n"
        "        time.sleep(60)\n",
        encoding="utf-8",
    )
    return subprocess.Popen(
        [sys.executable, str(script), str(port), token],
        cwd=tmp_path,
        start_new_session=True,
    )


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Provide an isolated runtime directory for each test."""
    return tmp_path / "state"


class TestPortOccupied:
    """Port probing behaviour."""

    def test_free_port_is_not_occupied(self) -> None:
        """An OS-assigned free port is reported as unoccupied."""
        port = _find_free_port()
        assert _port_is_occupied("127.0.0.1", port) is False

    def test_bound_port_is_occupied(self) -> None:
        """A socket bound to a port is reported as occupied."""
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.listen()
            assert _port_is_occupied("127.0.0.1", port) is True


class TestCommandLineAndOwnership:
    """Ownership verification helpers."""

    def test_get_cmdline_returns_current_process(self) -> None:
        """_get_cmdline returns a non-empty list for the current process."""
        cmdline = _get_cmdline(os.getpid())
        assert cmdline is not None
        joined = " ".join(cmdline).lower()
        assert "pytest" in joined or "python" in joined

    def test_get_cmdline_returns_none_for_missing_pid(self) -> None:
        """A non-existent PID yields None."""
        assert _get_cmdline(999999) is None

    def test_classify_accepts_matching_identity(self, tmp_path: Path) -> None:
        """A recorded PID whose command line contains the identity is owned."""
        port = _find_free_port()
        token = "matchtoken1234567890123456789012"
        proc = _run_identity_process(tmp_path, port, token)
        try:
            time.sleep(0.2)
            service = ServiceState(
                name="match",
                pid=proc.pid,
                pgid=proc.pid,
                port=port,
                command=[],
                identity=[token],
            )
            classification, reason = _classify_process(service)
            assert classification == _Ownership.OWNED, reason
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)

    def test_classify_rejects_stale_pid(self) -> None:
        """A recorded PID that no longer exists is dead."""
        service = ServiceState(
            name="ghost",
            pid=999999,
            pgid=999999,
            port=12345,
            command=[],
            identity=["ghosttoken123456789012345678901"],
        )
        classification, reason = _classify_process(service)
        assert classification == _Ownership.DEAD
        assert "gone" in reason

    def test_classify_rejects_mismatched_identity(self, tmp_path: Path) -> None:
        """A live PID with a different identity token is uncertain."""
        port = _find_free_port()
        proc = _run_identity_process(tmp_path, port, "token-a")
        try:
            time.sleep(0.2)
            service = ServiceState(
                name="other",
                pid=proc.pid,
                pgid=proc.pid,
                port=port,
                command=[],
                identity=["token-b"],
            )
            classification, reason = _classify_process(service)
            assert classification == _Ownership.UNCERTAIN
            assert "identity token" in reason
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)

    def test_classify_rejects_wrong_pgid(self, tmp_path: Path) -> None:
        """A stored pid != pgid is treated as uncertain."""
        port = _find_free_port()
        token = "wrongpgidtoken12345678901234567"
        proc = _run_identity_process(tmp_path, port, token)
        try:
            time.sleep(0.2)
            service = ServiceState(
                name="wrongpgid",
                pid=proc.pid,
                pgid=proc.pid + 1,
                port=port,
                command=[],
                identity=[token],
            )
            classification, reason = _classify_process(service)
            assert classification == _Ownership.UNCERTAIN
            assert "implausible" in reason
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)

    def test_classify_rejects_missing_identity(self, tmp_path: Path) -> None:
        """A live PID with no recorded identity is uncertain."""
        port = _find_free_port()
        proc = _run_identity_process(tmp_path, port, "sometoken")
        try:
            time.sleep(0.2)
            service = ServiceState(
                name="noidentity",
                pid=proc.pid,
                pgid=proc.pid,
                port=port,
                command=[],
                identity=[],
            )
            classification, reason = _classify_process(service)
            assert classification == _Ownership.UNCERTAIN
            assert "no recorded identity" in reason
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)

    def test_classify_rejects_implausible_identity(self) -> None:
        """PIDs <= 1 or pid != pgid are uncertain without probing."""
        service = ServiceState(
            name="bad",
            pid=1,
            pgid=1,
            port=12345,
            command=[],
            identity=["tok"],
        )
        classification, reason = _classify_process(service)
        assert classification == _Ownership.UNCERTAIN
        assert "implausible" in reason


class TestLifecycle:
    """Real lightweight child process lifecycle."""

    def test_start_services_writes_state_and_logs(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Starting services persists state and writes per-service logs."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "alpha", port)]
        state = _start_services(services, state_dir)
        try:
            assert len(state.services) == 1
            service = state.services[0]
            assert service.name == "alpha"
            assert service.identity
            assert _process_alive(service.pid)

            persisted = _read_state(state_dir)
            assert persisted is not None
            assert persisted.services[0].pid == service.pid
            assert persisted.services[0].identity == service.identity

            log_path = state_dir / "logs" / "alpha.log"
            assert log_path.exists()
        finally:
            _stop_services(state)
            _state_path(state_dir).unlink(missing_ok=True)

    def test_stop_services_stops_owned_processes(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Stopping an owned run terminates all tracked processes."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "beta", port)]
        state = _start_services(services, state_dir)
        result = _stop_services(state)
        assert not result.warnings
        assert not result.uncertain
        assert not result.failed
        assert not _process_alive(state.services[0].pid)

    def test_start_command_and_stop_command_roundtrip(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Start returns and stop shuts down the tracked run."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "gamma", port)]
        assert _start_command(services, state_dir) == 0
        state = _read_state(state_dir)
        assert state is not None
        assert _process_alive(state.services[0].pid)

        assert _stop_command(state_dir) == 0
        assert _read_state(state_dir) is None
        assert not _process_alive(state.services[0].pid)

    def test_restart_command_replaces_run(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Restart stops the old run and starts a new one."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "delta", port)]
        assert _start_command(services, state_dir) == 0
        old_state = _read_state(state_dir)
        assert old_state is not None
        old_pid = old_state.services[0].pid

        assert _restart_command(services, state_dir) == 0
        new_state = _read_state(state_dir)
        assert new_state is not None
        new_pid = new_state.services[0].pid
        assert new_pid != old_pid
        assert not _process_alive(old_pid)
        assert _process_alive(new_pid)

        _stop_command(state_dir)
        assert not _process_alive(new_pid)

    def test_start_command_refuses_second_run(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Start fails when a tracked run is already alive."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "epsilon", port)]
        assert _start_command(services, state_dir) == 0
        try:
            assert _start_command(services, state_dir) == 1
        finally:
            _stop_command(state_dir)

    def test_start_services_aborts_on_occupied_port(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Launch fails before starting anything if a dev port is occupied."""
        port = _find_free_port()
        with socket.socket() as occupant:
            occupant.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupant.bind(("127.0.0.1", port))
            occupant.listen()
            services = [_make_service(tmp_path, "zeta", port)]
            with pytest.raises(RuntimeError, match="already occupied"):
                _start_services(services, state_dir)

    def test_start_services_fails_readiness_and_cleans_up(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """A service that never binds its port is cleaned up."""
        port = _find_free_port()
        script = tmp_path / "slow.py"
        script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        services = [("slow", [sys.executable, str(script)], tmp_path, port)]
        with pytest.raises(RuntimeError, match="did not become ready"):
            _start_services(services, state_dir)
        assert _state_path(state_dir).exists() is False
        assert _port_is_occupied("127.0.0.1", port) is False

    def test_start_services_cleans_up_on_immediate_exit(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """A service that exits immediately is cleaned up."""
        port = _find_free_port()
        services = [
            ("fails", [sys.executable, "-c", "raise SystemExit(1)"], tmp_path, port)
        ]
        with pytest.raises(RuntimeError, match="exited immediately"):
            _start_services(services, state_dir)
        assert _state_path(state_dir).exists() is False
        assert _state_path(state_dir).exists() is False

    def test_start_services_cleans_up_on_missing_binary(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """A service with a missing executable is cleaned up."""
        port = _find_free_port()
        missing = tmp_path / "no_such_executable"
        services = [("missing", [str(missing)], tmp_path, port)]
        with pytest.raises(RuntimeError, match="exited immediately"):
            _start_services(services, state_dir)
        assert _state_path(state_dir).exists() is False

    def test_start_services_cleans_up_on_state_write_failure(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """A log/state write failure is reported and already-launched services stop."""
        port = _find_free_port()
        services = [_make_service(tmp_path, "writer", port)]
        # Make the state path a file so directory creation fails.
        state_dir.write_text("block", encoding="utf-8")
        with pytest.raises(OSError):
            _start_services(services, state_dir)
        assert not _state_path(state_dir).exists()
        assert _port_is_occupied("127.0.0.1", port) is False

    @pytest.mark.parametrize("failure", ["interrupt", "state-write"])
    def test_start_services_rolls_back_after_spawn(
        self,
        state_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure: str,
    ) -> None:
        """Interruptions and persistence failures clean up already-ready children."""
        from site_directedideation_com import dev

        port = _find_free_port()
        services = [_make_service(tmp_path, "rollback", port)]
        original_wait = dev._wait_for_ports
        launched: list[int] = []

        def wait_then_fail(service_states, procs, timeout):
            """Record spawned groups and interrupt only after the port is ready."""
            launched.extend(process.pid for _, process in procs)
            result = original_wait(service_states, procs, timeout)
            assert result[0], result[1]
            if failure == "interrupt":
                raise KeyboardInterrupt
            return result

        def fail_write(*_args):
            """Simulate a disk failure after services are ready."""
            assert _port_is_occupied("127.0.0.1", port)
            raise OSError("simulated state write failure")

        monkeypatch.setattr(dev, "_wait_for_ports", wait_then_fail)
        monkeypatch.setattr(dev, "_write_state", fail_write)
        try:
            expected = KeyboardInterrupt if failure == "interrupt" else OSError
            with pytest.raises(expected):
                _start_services(services, state_dir)
            assert not _port_is_occupied("127.0.0.1", port)
            assert not _state_path(state_dir).exists()
        finally:
            for pid in launched:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(pid, signal.SIGKILL)
                with contextlib.suppress(ChildProcessError):
                    os.waitpid(pid, 0)


class TestStopSafety:
    """Stop behaviour with uncertain or dead processes."""

    def test_stop_command_keeps_state_on_uncertain_identity(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """Stop returns nonzero and keeps state when identity cannot be verified."""
        port = _find_free_port()
        proc = _run_identity_process(tmp_path, port, "token-a")
        try:
            time.sleep(0.2)
            service = ServiceState(
                name="uncertain",
                pid=proc.pid,
                pgid=proc.pid,
                port=port,
                command=[],
                identity=["token-b"],
            )
            state = ServerState(
                run_id="r",
                started_at=datetime.datetime.now(tz=datetime.UTC),
                services=[service],
            )
            from site_directedideation_com.dev import _write_state

            _write_state(state_dir, state)
            assert _stop_command(state_dir) == 1
            assert _read_state(state_dir) is not None
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)

    def test_stop_command_succeeds_when_all_dead(self, state_dir: Path) -> None:
        """Stop removes state when every tracked PID is already gone."""
        service = ServiceState(
            name="dead",
            pid=99999,
            pgid=99999,
            port=12345,
            command=[],
            identity=["deadtoken123456789012345678901"],
        )
        state = ServerState(
            run_id="r",
            started_at=datetime.datetime.now(tz=datetime.UTC),
            services=[service],
        )
        from site_directedideation_com.dev import _write_state

        _write_state(state_dir, state)
        assert _stop_command(state_dir) == 0
        assert _read_state(state_dir) is None


class TestLocking:
    """Concurrent invocation safety."""

    def test_acquire_lock_is_non_blocking(self, state_dir: Path) -> None:
        """A second caller receives a clear error while the lock is held."""
        with _acquire_lock(state_dir):
            with pytest.raises(RuntimeError, match="Another dev server command"):
                with _acquire_lock(state_dir):
                    pass


class TestForegroundSignal:
    """Foreground mode signal handling."""

    def test_foreground_sigterm_cleans_up_children(self, tmp_path: Path) -> None:
        """SIGTERM in foreground mode stops child services."""
        port = _find_free_port()
        name, command, cwd, _port = _make_service(tmp_path, "fg", port)
        runner = tmp_path / "foreground_runner.py"
        runner.write_text(
            f"import sys\n"
            f"sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
            f"from site_directedideation_com.dev import _foreground\n"
            f"services = [({name!r}, {command!r}, {str(cwd)!r}, {port})]\n"
            f"sys.exit(_foreground(services))\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [sys.executable, str(runner)],
            cwd=PROJECT_ROOT,
            start_new_session=True,
        )
        try:
            # Wait long enough for the foreground process to start the service.
            time.sleep(0.8)
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
            assert proc.returncode == 128 + signal.SIGTERM
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)
        assert _port_is_occupied("127.0.0.1", port) is False


class TestWrapperBehavior:
    """Token-bearing wrapper process behaviour."""

    def test_wrapper_forwards_sigterm_without_recursion(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """The wrapper forwards SIGTERM to its child and exits cleanly."""
        port = _find_free_port()
        name, command, cwd, _port = _make_service(tmp_path, "wrapped", port)
        log_path = state_dir / "logs" / "wrapped.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        token = "wraptoken1234567890123456789012"
        wrapped = _wrap_service_command(command, cwd, log_path, token)

        proc = subprocess.Popen(
            wrapped,
            cwd=PROJECT_ROOT,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            # Wait for the underlying service to bind its port.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if _port_is_occupied("127.0.0.1", port):
                    break
                time.sleep(0.05)
            assert _port_is_occupied("127.0.0.1", port)

            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
            assert proc.returncode is not None
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)
        assert _port_is_occupied("127.0.0.1", port) is False


class TestStopResistance:
    """Shutdown of stubborn child processes."""

    def _make_resistant_service(
        self, tmp_path: Path, name: str, port: int
    ) -> tuple[str, list[str], Path, int]:
        script = tmp_path / f"{name.replace(' ', '_')}_resistant.py"
        script.write_text(
            "import signal, socket, sys, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "port = int(sys.argv[1])\n"
            "with socket.socket() as s:\n"
            "    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "    s.bind(('127.0.0.1', port))\n"
            "    s.listen()\n"
            "    while True:\n"
            "        time.sleep(60)\n",
            encoding="utf-8",
        )
        return (name, [sys.executable, str(script), str(port)], tmp_path, port)

    def test_stop_services_kills_term_resistant_descendants(
        self, state_dir: Path, tmp_path: Path
    ) -> None:
        """A child that ignores SIGTERM is eventually stopped with SIGKILL."""
        port = _find_free_port()
        services = [self._make_resistant_service(tmp_path, "stubborn", port)]
        state = _start_services(services, state_dir)
        try:
            result = _stop_services(state, deadline_seconds=2)
            assert not result.warnings
            assert not result.uncertain
            assert not result.failed
            assert _port_is_occupied("127.0.0.1", port) is False
        finally:
            _state_path(state_dir).unlink(missing_ok=True)


def test_admin_service_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """All lifecycle modes share the loopback-only dashboard definition."""
    from site_directedideation_com import dev

    monkeypatch.setattr(dev.shutil, "which", lambda name: f"/bin/{name}")
    services = dev._services()
    name, command, cwd, port = next(s for s in services if s[0] == "Admin")
    assert (name, cwd, port) == ("Admin", PROJECT_ROOT, 8002)
    assert command == [
        sys.executable,
        "-m",
        "uvicorn",
        "site_directedideation_com.admin:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8002",
    ]


def test_admin_managed_lifecycle_and_conflict(
    tmp_path: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dashboard readiness, state, logs, restart and stop use the lifecycle."""
    monkeypatch.setenv("METRICS_ENV", "development")
    monkeypatch.setenv("METRICS_DB", str(tmp_path / "metrics.sqlite"))
    port = _find_free_port()
    service = (
        "Admin",
        [
            sys.executable,
            "-m",
            "uvicorn",
            "site_directedideation_com.admin:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        PROJECT_ROOT,
        port,
    )
    assert _start_command([service], state_dir) == 0
    try:
        state = _read_state(state_dir)
        assert state is not None and state.services[0].name == "Admin"
        assert state.services[0].port == port
        assert (state_dir / "logs" / "admin.log").exists()
        with pytest.raises(RuntimeError, match="Admin is occupied"):
            _start_services([service], tmp_path / "other-state")
        assert _restart_command([service], state_dir) == 0
        assert _port_is_occupied("127.0.0.1", port)
    finally:
        assert _stop_command(state_dir) == 0
    assert not _port_is_occupied("127.0.0.1", port)
