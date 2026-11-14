"""Offline checks for preparing the private production backend environment."""

import importlib.util
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/create_production_backend_env.py"
)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """Use disposable files and simulate the root-owned directory checks."""
    spec = importlib.util.spec_from_file_location("production_env", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record = tmp_path / "record"
    record.write_text("OLD_ISSUER=https://old.authkit.app\n")
    target = tmp_path / "new.env"
    monkeypatch.setattr(module, "DIRECTORY", tmp_path)
    monkeypatch.setattr(module, "RECORD", record)
    monkeypatch.setattr(module, "TARGET", target)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    original_lstat = Path.lstat

    def lstat(path):
        if path == tmp_path:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0)
        if path == record:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    return module, target


def test_saves_private_settings_and_never_overwrites(prepared, monkeypatch, capsys):
    """Valid settings are private and an existing file is never replaced."""
    module, target = prepared
    inputs = iter(["https://new.authkit.app/", "user_123"])
    monkeypatch.setattr(module.getpass, "getpass", lambda _: next(inputs))
    module.main()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "WORKOS_STAGING_ISSUER=https://new.authkit.app\n" in target.read_text()
    assert "user_123" not in capsys.readouterr().out
    inputs = iter(["https://new.authkit.app", "user_456"])
    with pytest.raises(FileExistsError):
        module.main()
    assert "user_123" in target.read_text()


def test_rejects_staging_issuer_without_creating_file(prepared, monkeypatch):
    """Reject the old issuer before creating a settings file."""
    module, target = prepared
    inputs = iter(["https://old.authkit.app", "user_123"])
    monkeypatch.setattr(module.getpass, "getpass", lambda _: next(inputs))
    with pytest.raises(ValueError):
        module.main()
    assert not target.exists()
