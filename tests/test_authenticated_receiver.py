"""Offline checks of authenticated deployment and failure recovery."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "receiver", Path(__file__).parents[1] / "staging_mcp/receive-production.py"
)
assert spec is not None and spec.loader is not None
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


@pytest.mark.parametrize("fail_deploy", [False, True])
def test_deploy_and_rollback(monkeypatch, tmp_path, fail_deploy):
    """Recreate only the target and restore on deployment failure."""
    compose = tmp_path / "compose.yaml"
    compose.write_text("reviewed")
    import hashlib

    monkeypatch.setattr(receiver, "COMPOSE", str(compose))
    monkeypatch.setattr(
        receiver, "COMPOSE_SHA", hashlib.sha256(b"reviewed").hexdigest()
    )
    monkeypatch.setattr(receiver.os, "geteuid", lambda: 0)
    real_lstat = receiver.os.lstat
    monkeypatch.setattr(
        receiver.os,
        "lstat",
        lambda p: (
            SimpleNamespace(st_mode=0o100600, st_uid=0)
            if p in ("/etc", "/etc/di-staging", str(compose))
            else real_lstat(p)
        ),
    )
    monkeypatch.setattr(receiver.os.path, "lexists", lambda p: False)
    monkeypatch.setattr(receiver.fcntl, "flock", lambda *a: None)
    monkeypatch.setattr(receiver.sys, "stdin", SimpleNamespace(buffer=io.BytesIO()))
    original_open = open
    monkeypatch.setattr(
        "builtins.open",
        lambda p, *a, **kw: (
            original_open(tmp_path / "lock", *a, **kw)
            if p == "/run/lock/di-staging-allowlist.lock"
            else original_open(p, *a, **kw)
        ),
    )
    old = "sha256:" + "b" * 64
    container = {
        "Image": old,
        "Config": {
            "Image": receiver.TAG,
            "Labels": {
                "com.docker.compose.project": "di-staging",
                "com.docker.compose.service": "staging-mcp",
                "com.docker.compose.project.config_files": str(compose),
                "com.docker.compose.project.working_dir": "/etc/di-staging",
            },
            "Env": [
                "STAGING_MCP_HOST=mcp.directedideation.com",
                "WORKOS_STAGING_ISSUER=https://issuer.example",
                "WORKOS_STAGING_ALLOWED_SUBJECTS=user_ABC",
            ],
        },
    }
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "inspect":
            return json.dumps([container]).encode()
        if (
            args[0] == "compose"
            and fail_deploy
            and sum(c[0][0] == "compose" for c in calls) == 1
        ):
            raise RuntimeError("failure")
        return b""

    monkeypatch.setattr(receiver, "run", run)
    if fail_deploy:
        with pytest.raises(RuntimeError):
            receiver.main("a" * 40)
        assert (("tag", old, receiver.TAG), {}) in calls
    else:
        receiver.main("a" * 40)
    assert sum(c[0][0] == "compose" for c in calls) == (2 if fail_deploy else 1)
    assert all(
        c[1]["env"]["WORKOS_STAGING_ALLOWED_SUBJECTS"] == "user_ABC"
        for c in calls
        if c[0][0] == "compose"
    )


def test_invalid_revision_refused(monkeypatch):
    """Reject malformed revisions before accessing Docker."""
    monkeypatch.setattr(receiver.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError):
        receiver.main("bad")
