"""Offline state-machine checks for the manual switch helper."""

# ruff: noqa: D103
import copy
import importlib.util
import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest

spec = importlib.util.spec_from_file_location(
    "manual_switch", "staging_mcp/manual-switch.py"
)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
HASH = "c" * 64


def container(image=OLD):
    return {
        "Id": "d" * 64,
        "Image": image,
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "Config": {
            "Image": m.TAG,
            "Env": [
                "WORKOS_STAGING_ISSUER=https://example.test",
                "WORKOS_STAGING_ALLOWED_SUBJECTS=user_ABC",
            ],
            "Labels": {
                "com.docker.compose.project": "di-staging",
                "com.docker.compose.service": "staging-mcp",
                "com.docker.compose.project.config_files": str(m.ORIGINAL_COMPOSE),
                "com.docker.compose.project.working_dir": str(m.ORIGINAL_DIR),
                "com.docker.compose.config-hash": HASH,
            },
        },
    }


def setup(monkeypatch, tmp_path, action="switch"):
    old = tmp_path / "old"
    old.write_text("old")
    current = tmp_path / "compose"
    current.write_text("new")
    snapshot = tmp_path / "snapshot"
    snapshot.write_text(json.dumps([container()]))
    monkeypatch.setattr(m, "OLD", old)
    monkeypatch.setattr(m, "COMPOSE", current)
    monkeypatch.setattr(m, "SNAPSHOT", snapshot)
    monkeypatch.setattr(m, "LOCK", tmp_path / "lock")
    # Snapshot labels use the test path.
    c = container()
    snapshot.write_text(json.dumps([c]))
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    real_fstat = m.os.fstat

    def root_fstat(fd):
        result = real_fstat(fd)
        return SimpleNamespace(st_mode=result.st_mode, st_uid=0)

    monkeypatch.setattr(m.os, "fstat", root_fstat)
    monkeypatch.setattr(m, "trusted", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "DIR", tmp_path)
    snapshot.write_text(json.dumps([c]))
    monkeypatch.setattr(m, "config_hash", lambda *_a: HASH)
    monkeypatch.setattr(
        sys, "argv", ["helper", action, OLD, NEW, m.digest(current).hex()]
    )
    calls = []
    state: dict[str, Any] = {"container": c, "tag": OLD}
    monkeypatch.setattr(m, "inspect", lambda: copy.deepcopy(state["container"]))
    monkeypatch.setattr(m, "image_id", lambda: state["tag"])

    def run(*args, **_kwargs):
        calls.append(args)
        if args[0] == "tag":
            state["tag"] = args[1]
        return args[-1]

    def compose(*args):
        calls.append(args)
        state["container"]["Image"] = state["tag"]
        state["container"]["Id"] = "e" * 64
        state["container"]["Config"]["Labels"][
            "com.docker.compose.project.config_files"
        ] = str(m.COMPOSE)
        state["container"]["Config"]["Labels"][
            "com.docker.compose.project.working_dir"
        ] = str(m.DIR)

    monkeypatch.setattr(m, "run", run)
    monkeypatch.setattr(m, "compose", compose)
    return state, calls, current


def test_switch_and_recover(monkeypatch, tmp_path):
    state, calls, current = setup(monkeypatch, tmp_path)
    m.main()
    assert state["container"]["Image"] == NEW
    assert calls.index(("tag", NEW, m.TAG)) < len(calls) - 1
    assert (
        "up",
        "-d",
        "--no-build",
        "--pull",
        "never",
        "--no-deps",
        "staging-mcp",
    ) == calls[-1][2:]
    monkeypatch.setattr(
        sys, "argv", ["helper", "recover", OLD, NEW, m.digest(current).hex()]
    )
    m.main()
    assert state["container"]["Image"] == OLD
    assert current.read_text() == "old"


@pytest.mark.parametrize("drift", ["container", "tag", "config", "environment"])
def test_refuses_drift_without_mutation(monkeypatch, tmp_path, drift):
    state, calls, current = setup(monkeypatch, tmp_path)
    if drift == "container":
        state["container"]["Id"] = "e" * 64
    if drift == "tag":
        state["tag"] = "sha256:" + "f" * 64
    if drift == "config":
        current.write_text("unapproved")
    if drift == "environment":
        state["container"]["Config"]["Env"][1] += ",user_OTHER"
    with pytest.raises(m.Refusal):
        m.main()
    assert not any(c[0] == "tag" or (len(c) > 2 and c[2] == "up") for c in calls)


def test_unhealthy_refused():
    c = container()
    c["State"]["Health"]["Status"] = "unhealthy"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(m, "inspect", lambda: c)
        with pytest.raises(m.Refusal):
            m.healthy(OLD, m.environment(c), HASH)


def test_observed_original_labels_and_switch_retag_order(monkeypatch, tmp_path):
    state, calls, _ = setup(monkeypatch, tmp_path)
    labels = state["container"]["Config"]["Labels"]
    assert (
        labels["com.docker.compose.project.config_files"]
        == "/home/kent/di-pilot-build.eR6dNHdr/compose.yaml"
    )
    assert (
        labels["com.docker.compose.project.working_dir"]
        == "/home/kent/di-pilot-build.eR6dNHdr"
    )
    original_flock = m.fcntl.flock
    locked = False

    def flock(fd, op):
        nonlocal locked
        original_flock(fd, op)
        locked = True

    original_run = m.run

    def run(*args, **kwargs):
        if args[0] == "tag":
            assert locked
            assert ("image", "inspect", "--format", "{{.Id}}", OLD) in calls
            assert ("image", "inspect", "--format", "{{.Id}}", NEW) in calls
            assert state["tag"] == OLD
        return original_run(*args, **kwargs)

    monkeypatch.setattr(m.fcntl, "flock", flock)
    monkeypatch.setattr(m, "run", run)
    m.main()
    assert ("tag", NEW, m.TAG) in calls


def test_recover_rejects_unrecognized_labels(monkeypatch, tmp_path):
    state, calls, _ = setup(monkeypatch, tmp_path, "recover")
    state["container"]["Config"]["Labels"]["com.docker.compose.project.working_dir"] = (
        "/unexpected"
    )
    with pytest.raises(m.Refusal):
        m.main()
    assert not any(c[0] == "tag" for c in calls)
