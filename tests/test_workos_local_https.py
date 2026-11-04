"""Offline regression tests for the fail-closed WorkOS harness."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from scripts import workos_local_https


def test_main_fails_without_network_processes_or_temporary_profiles(monkeypatch, capsys):
    """No proxy bypass, suffix, CA trust, or profile path can be exercised."""
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled harness attempted a side effect")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setenv("WORKOS_STAGING_ISSUER", "https://directedideation.com")
    assert workos_local_https.main() == 1
    assert "disabled" in capsys.readouterr().err


def test_cli_does_not_launch_pi_or_touch_profile(tmp_path):
    """Even a configured executable and a sentinel HOME remain untouched."""
    home = tmp_path / "home"
    home.mkdir()
    sentinel = home / "credential-sentinel"
    sentinel.write_text("test-only sentinel")
    marker = tmp_path / "pi-ran"
    pi = tmp_path / "pi"
    pi.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
    pi.chmod(0o700)
    script = Path(workos_local_https.__file__)
    env = {
        "PATH": os.defpath,
        "HOME": str(home),
        "WORKOS_TEST_PI": str(pi),
        "WORKOS_STAGING_ISSUER": "https://directedideation.com",
        "WORKOS_STAGING_ALLOWED_SUBJECTS": "user_TEST",
    }
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "disabled" in result.stderr
    assert not marker.exists()
    assert list(home.iterdir()) == [sentinel]
    assert sentinel.read_text() == "test-only sentinel"
