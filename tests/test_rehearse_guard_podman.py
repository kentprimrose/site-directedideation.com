"""Offline checks for the isolated, checked-in guard rehearsal."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "rehearsal", Path("scripts/rehearse_guard_podman.py")
)
assert spec and spec.loader
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)


def test_load_guard_uses_checkout_without_git(monkeypatch, tmp_path):
    """The configured project is used consistently at all guard boundaries."""
    monkeypatch.setattr(rehearsal, "call", lambda *a, **kw: pytest.fail("called git"))
    guard = rehearsal.load_guard("grtest")
    assert guard.PROJECT == "grtest"
    guard.CONTAINER = "grtest-staging-mcp-1"
    path = tmp_path / "compose.yaml"
    env = {
        "WORKOS_STAGING_ISSUER": "https://issuer.invalid",
        "WORKOS_STAGING_ALLOWED_SUBJECTS": "synthetic",
    }
    captured = []
    guard.run = lambda *args, **kwargs: captured.append(args) or ""
    guard.compose(path, env, "config")
    assert captured[0][1:3] == ("--project-name", "grtest")

    ident = "a" * 64
    container = {
        "Id": ident,
        "Name": "/" + guard.CONTAINER,
        "Image": "image",
        "State": {"Running": True},
        "Config": {
            "Image": guard.TAG,
            "Env": [f"{k}={v}" for k, v in env.items()],
            "Labels": {
                "com.docker.compose." + k: v
                for k, v in {
                    "project": "grtest",
                    "service": "staging-mcp",
                    "project.config_files": str(path),
                    "project.working_dir": str(path.parent),
                    "config-hash": "hash",
                }.items()
            },
        },
    }
    guard.run = lambda *args: ident if args[0] == "ps" else json.dumps([container])
    assert guard.container() == container
    guard.verify(container, "image", path, env, "hash", True)
    container["Name"] = "/unexpected"
    with pytest.raises(RuntimeError, match="inventory"):
        guard.container()
    container["Config"]["Labels"]["com.docker.compose.project"] = "di-staging"
    with pytest.raises(RuntimeError, match="labels"):
        guard.verify(container, "image", path, env, "hash", True)


def test_production_default_project_unchanged():
    """Loading an isolated module does not change the checked-in default."""
    path = rehearsal.ROOT / "staging_mcp" / "staging-upgrade" / "upgrade.py"
    spec = importlib.util.spec_from_file_location("production_guard", path)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard.PROJECT == "di-staging"
