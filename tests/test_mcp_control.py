"""Tests for the standalone local MCP lifecycle."""

import socket
from pathlib import Path

import pytest

from site_directedideation_com import dev, mcp_control


def test_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Start, restart on the same port, and stop a real server."""
    monkeypatch.setattr(mcp_control, "STATE_DIR", tmp_path)
    monkeypatch.setenv("METRICS_ENV", "development")
    monkeypatch.setenv("METRICS_DB", str(tmp_path / "metrics.sqlite3"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    try:
        assert mcp_control.main(["start", "--port", str(port)]) == 0
        assert f":{port}/mcp" in capsys.readouterr().out
        assert mcp_control.main(["start", "--port", str(port)]) == 1
        assert "already running" in capsys.readouterr().err
        assert (
            mcp_control.main(["start", "--port", str(8001 if port != 8001 else 8002)])
            == 1
        )
        assert dev._log_path(tmp_path, "MCP").exists()
        assert mcp_control.main(["restart"]) == 0
        assert f":{port}/mcp" in capsys.readouterr().out
        assert mcp_control.main(["stop"]) == 0
        assert "MCP stopped" in capsys.readouterr().out
        assert mcp_control.main(["stop"]) == 1
        assert mcp_control.main(["restart"]) == 1
    finally:
        mcp_control.main(["stop"])


def test_occupied_port_is_never_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrelated listener is left alone on startup failure."""
    monkeypatch.setattr(mcp_control, "STATE_DIR", tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert mcp_control.main(["start", "--port", str(port)]) == 1
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        assert mcp_control.main(["stop"]) == 1


def test_corrupt_state_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable state must not be silently discarded."""
    monkeypatch.setattr(mcp_control, "STATE_DIR", tmp_path)
    path = dev._state_path(tmp_path)
    path.write_text("not json")
    assert mcp_control.main(["start"]) == 1
    assert mcp_control.main(["stop"]) == 1
    assert path.read_text() == "not json"


def test_unverifiable_process_is_not_signalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain state if ownership cannot be established."""
    monkeypatch.setattr(mcp_control, "STATE_DIR", tmp_path)
    monkeypatch.setattr(
        dev, "_classify_process", lambda _service: (dev._Ownership.UNCERTAIN, "unknown")
    )
    import datetime

    state = dev.ServerState(
        "run",
        datetime.datetime.now(datetime.UTC),
        [dev.ServiceState("MCP", 123, 123, 8001, [])],
    )
    dev._write_state(tmp_path, state)
    assert mcp_control.main(["start"]) == 1
    assert mcp_control.main(["stop"]) == 1
    assert mcp_control.main(["restart"]) == 1
    assert dev._state_path(tmp_path).exists()


def test_log_follows_from_beginning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log streams the complete file and continues following it."""
    monkeypatch.setattr(mcp_control, "STATE_DIR", tmp_path)
    assert mcp_control.main(["log"]) == 1
    path = dev._log_path(tmp_path, "MCP")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("existing log\n")
    calls = []

    def run(command, *, check):
        calls.append((command, check))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(mcp_control.subprocess, "run", run)
    assert mcp_control.main(["log"]) == 0
    assert calls == [(["tail", "-n", "+1", "-f", str(path)], False)]
