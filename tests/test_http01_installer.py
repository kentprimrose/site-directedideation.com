"""Offline failure tests; no host systemd or nginx commands are executed."""

import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "http01",
    Path(__file__).resolve().parents[1] / "staging_mcp/install-production-http01.py",
)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Check the offline installer behaviour."""
    for name in ("SOURCE", "TARGET", "PUBLIC", "LOCK", "WEBROOT"):
        monkeypatch.setattr(m, name, tmp_path / name)
    m.SOURCE.write_bytes(b"approved vhost")
    m.PUBLIC.write_bytes(b"public conf")
    m.LOCK.touch(mode=0o600)
    monkeypatch.setattr(m, "SOURCE_HASH", hashlib.sha256(b"approved vhost").hexdigest())
    monkeypatch.setattr(m, "PUBLIC_HASH", hashlib.sha256(b"public conf").hexdigest())
    monkeypatch.setattr(m, "trusted_dir", lambda _p: None)
    original = os.fstat

    def root_fstat(fd):
        st = original(fd)
        return SimpleNamespace(
            st_mode=st.st_mode,
            st_uid=0,
            st_size=st.st_size,
            st_dev=st.st_dev,
            st_ino=st.st_ino,
        )

    monkeypatch.setattr(m.os, "fstat", root_fstat)
    calls = []

    def command(*args):
        calls.append(args)
        return "inactive"

    monkeypatch.setattr(m, "command", command)
    return calls


def test_success_and_existing_target(setup):
    """Check the offline installer behaviour."""
    m.install()
    assert m.TARGET.read_bytes() == b"approved vhost"
    assert setup[-2:] == [("nginx", "-t"), ("systemctl", "reload", "nginx.service")]
    with pytest.raises(RuntimeError, match="target already exists"):
        m.install()


@pytest.mark.parametrize("which", ["SOURCE", "PUBLIC"])
def test_digest_mismatch(setup, which):
    """Check the offline installer behaviour."""
    getattr(m, which).write_bytes(b"unexpected")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        m.install()
    assert not m.TARGET.exists()


def test_dangling_target_refused(setup):
    """Check the offline installer behaviour."""
    m.TARGET.symlink_to("missing")
    with pytest.raises(RuntimeError, match="target already exists"):
        m.install()
    assert m.TARGET.is_symlink()


def test_source_symlink_refused(setup):
    """Check the offline installer behaviour."""
    m.SOURCE.unlink()
    m.SOURCE.symlink_to(m.PUBLIC)
    with pytest.raises(OSError):
        m.install()
    assert not m.TARGET.exists()


@pytest.mark.usefixtures("setup")
def test_active_unit_refused(monkeypatch):
    """Check the offline installer behaviour."""
    monkeypatch.setattr(m, "command", lambda *_a: "active")
    with pytest.raises(RuntimeError, match="not inactive"):
        m.install()
    assert not m.TARGET.exists()


@pytest.mark.parametrize("failure", ["nginx", "reload"])
@pytest.mark.usefixtures("setup")
def test_failure_recovers(monkeypatch, failure):
    """Check the offline installer behaviour."""
    calls = []

    def command(*args):
        calls.append(args)
        if len([c for c in calls if c == args]) == 1 and (
            args[0] == failure or args[1] == failure
        ):
            raise RuntimeError("injected failure")
        return "inactive"

    monkeypatch.setattr(m, "command", command)
    with pytest.raises(RuntimeError, match="injected"):
        m.install()
    assert not m.TARGET.exists()
    assert calls[-2:] == [("nginx", "-t"), ("systemctl", "reload", "nginx.service")]


@pytest.mark.usefixtures("setup")
def test_changed_target_not_removed(monkeypatch, capsys):
    """Check the offline installer behaviour."""

    def command(*args):
        if args[0] == "nginx":
            m.TARGET.unlink()
            m.TARGET.write_bytes(b"foreign")
            raise RuntimeError("failure")
        return "inactive"

    monkeypatch.setattr(m, "command", command)
    with pytest.raises(RuntimeError, match="failure"):
        m.install()
    assert m.TARGET.read_bytes() == b"foreign"
    assert "RECOVERY FAILED" in capsys.readouterr().err
