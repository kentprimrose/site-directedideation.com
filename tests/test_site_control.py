"""Tests for the standalone local live-reloading website server and lifecycle."""

from __future__ import annotations

import datetime
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from site_directedideation_com import dev, site_control, site_server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_lifecycle_and_live_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Start, serve with reload notifications on file edits, restart, and stop."""
    state_dir = tmp_path / "state"
    site_root = tmp_path / "public"
    (site_root / "site").mkdir(parents=True)
    index_file = site_root / "index.html"
    css_file = site_root / "site" / "style.css"
    index_file.write_text(
        "<!doctype html><html><body><h1>Initial</h1></body></html>", encoding="utf-8"
    )
    css_file.write_text("body{color:#101c39}", encoding="utf-8")

    monkeypatch.setattr(site_control, "STATE_DIR", state_dir)
    monkeypatch.setattr(site_control, "SITE_ROOT", site_root)
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    try:
        assert site_control.main(["start", "--port", str(port)]) == 0
        assert f"http://127.0.0.1:{port}/" in capsys.readouterr().out
        assert site_control.main(["start", "--port", str(port)]) == 1
        assert "already running" in capsys.readouterr().err
        assert (
            site_control.main(["start", "--port", str(3000 if port != 3000 else 3001)])
            == 1
        )
        assert dev._log_path(state_dir, "Site").exists()

        # HTML includes live-reload snippet and Cache-Control: no-store.
        with urllib.request.urlopen(f"{base}/", timeout=3) as response:
            body = response.read().decode("utf-8")
            assert "<h1>Initial</h1>" in body
            assert "data-live-reload" in body
            assert response.headers["Cache-Control"] == "no-store"

        # CSS is served without script injection and with Cache-Control: no-store.
        with urllib.request.urlopen(f"{base}/site/style.css", timeout=3) as response:
            css = response.read().decode("utf-8")
            assert css == "body{color:#101c39}"
            assert response.headers["Cache-Control"] == "no-store"

        # Missing assets return 404 without leaving the site root.
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"{base}/missing.html", timeout=3)
        assert missing.value.code == 404

        # SSE stream emits boot event and emits reload when a site file changes.
        events: list[str] = []
        boot_seen = threading.Event()
        reload_seen = threading.Event()

        def listen() -> None:
            with urllib.request.urlopen(f"{base}/__live_reload", timeout=5) as stream:
                for raw_line in stream:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    events.append(line)
                    if line == "event: boot":
                        boot_seen.set()
                    if line == "event: reload":
                        reload_seen.set()
                        break

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        assert boot_seen.wait(timeout=3), f"Did not see boot event: {events}"

        time.sleep(0.05)
        index_file.write_text(
            "<!doctype html><html><body><h1>Updated</h1></body></html>",
            encoding="utf-8",
        )
        assert reload_seen.wait(timeout=3), f"Did not see reload event: {events}"
        listener.join(timeout=2)

        with urllib.request.urlopen(f"{base}/", timeout=3) as response:
            assert "<h1>Updated</h1>" in response.read().decode("utf-8")

        # Restart retains the port and serves updated content cleanly.
        assert site_control.main(["restart"]) == 0
        assert f"http://127.0.0.1:{port}/" in capsys.readouterr().out
        assert site_control.main(["stop"]) == 0
        assert "Site stopped" in capsys.readouterr().out
        assert site_control.main(["stop"]) == 1
        assert site_control.main(["restart"]) == 1
    finally:
        site_control.main(["stop"])


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    """Requests attempting to escape the site root resolve to None."""
    root = tmp_path / "public"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    assert site_server._resolve_site_file(root, "../secret.txt") is None
    assert site_server._resolve_site_file(root, "/") == (root / "index.html").resolve()


def test_occupied_port_is_never_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrelated listener is left alone on startup failure."""
    monkeypatch.setattr(site_control, "STATE_DIR", tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert site_control.main(["start", "--port", str(port)]) == 1
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        assert site_control.main(["stop"]) == 1


def test_corrupt_state_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable state must not be silently discarded."""
    monkeypatch.setattr(site_control, "STATE_DIR", tmp_path)
    path = dev._state_path(tmp_path)
    path.write_text("not json", encoding="utf-8")
    assert site_control.main(["start"]) == 1
    assert site_control.main(["stop"]) == 1
    assert path.read_text(encoding="utf-8") == "not json"


def test_unverifiable_process_is_not_signalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain state if ownership cannot be established."""
    monkeypatch.setattr(site_control, "STATE_DIR", tmp_path)
    monkeypatch.setattr(
        dev, "_classify_process", lambda _service: (dev._Ownership.UNCERTAIN, "unknown")
    )
    state = dev.ServerState(
        "run",
        datetime.datetime.now(datetime.UTC),
        [dev.ServiceState("Site", 123, 123, 3000, [])],
    )
    dev._write_state(tmp_path, state)
    assert site_control.main(["start"]) == 1
    assert site_control.main(["stop"]) == 1
    assert site_control.main(["restart"]) == 1
    assert dev._state_path(tmp_path).exists()


def test_log_follows_from_beginning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log streams the complete file and continues following it."""
    monkeypatch.setattr(site_control, "STATE_DIR", tmp_path)
    assert site_control.main(["log"]) == 1
    path = dev._log_path(tmp_path, "Site")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("existing log\n", encoding="utf-8")
    calls = []

    def run(command, *, check):
        calls.append((command, check))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(site_control.subprocess, "run", run)
    assert site_control.main(["log"]) == 0
    assert calls == [(["tail", "-n", "+1", "-f", str(path)], False)]


def test_public_site_separates_main_guide_from_resources() -> None:
    """Main page omits specific authors/methods; resources page cites sources."""
    public = site_server.DEFAULT_SITE_ROOT
    index_html = (public / "index.html").read_text(encoding="utf-8")
    resources_html = (public / "resources.html").read_text(encoding="utf-8")

    lower_index = index_html.lower()
    for forbidden in (
        "dettmer",
        "von oech",
        "de bono",
        "ohno",
        "ishikawa",
        "goldratt",
        "six sigma",
        "five whys",
        "sipoc",
        "fishbone",
        "fmea",
        "voc-to-ctq",
        "logical thinking process",
        "goal tree",
        "evaporating cloud",
        "prerequisite tree",
        "six thinking hats",
        "scamper",
        "mental locks",
    ):
        assert forbidden not in lower_index, f"Unexpected main-page term: {forbidden}"
    assert 'href="resources.html"' in index_html

    lower_resources = resources_html.lower()
    assert 'href="resources.html" aria-current="page"' in resources_html
    for expected in (
        "edward de bono",
        "lateral thinking: creativity step by step",
        "six thinking hats",
        "roger von oech",
        "a whack on the side of the head",
        "a kick in the seat of the pants",
        "h. william dettmer",
        "the logical thinking process",
        "eliyahu m. goldratt",
        "taiichi ohno",
        "kaoru ishikawa",
        "the six sigma way",
        "scamper",
        "competing against luck",
        "performing a project premortem",
    ):
        assert expected in lower_resources
