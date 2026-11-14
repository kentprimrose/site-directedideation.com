"""Offline state-machine checks for the guarded staging upgrade."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

spec = importlib.util.spec_from_file_location(
    "upgrade", Path("staging_mcp/staging-upgrade/upgrade.py")
)
assert spec is not None and spec.loader is not None
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64


def fixture(monkeypatch, tmp_path):
    """Fixture."""
    old = tmp_path / "old" / "compose.yaml"
    new = tmp_path / "new" / "compose.yaml"
    old.parent.mkdir()
    new.parent.mkdir()
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    monkeypatch.setattr(u, "OLD", old)
    monkeypatch.setattr(u, "NEW", new)
    monkeypatch.setattr(u, "STATE", tmp_path / "state")
    monkeypatch.setattr(u, "OLD_HASH", __import__("hashlib").sha256(b"old").hexdigest())
    monkeypatch.setattr(u, "NEW_HASH", __import__("hashlib").sha256(b"new").hexdigest())
    monkeypatch.setattr(u, "trusted", lambda _: None)
    env = {
        "WORKOS_STAGING_ISSUER": "https://example.test",
        "WORKOS_STAGING_ALLOWED_SUBJECTS": "user_TEST",
    }

    def make(image, path, host=False):
        labels = {
            "com.docker.compose." + k: v
            for k, v in {
                "project": "di-staging",
                "service": "staging-mcp",
                "project.config_files": str(path),
                "project.working_dir": str(path.parent),
                "config-hash": ("a") * 64,
            }.items()
        }
        e = dict(env)
        if host:
            e["STAGING_MCP_HOST"] = u.HOST
        return {
            "Id": "container",
            "Image": image,
            "State": {"Running": True},
            "Config": {
                "Image": u.TAG,
                "Env": [f"{k}={v}" for k, v in e.items()],
                "Labels": labels,
            },
        }

    state: dict[str, Any] = {
        "tags": {u.TAG: OLD, OLD: OLD, NEW: NEW},
        "container": make(OLD, old),
        "commands": [],
    }
    monkeypatch.setattr(u, "image", lambda tag: state["tags"].get(tag))
    monkeypatch.setattr(u, "container", lambda: state["container"])
    monkeypatch.setattr(
        u,
        "config_hash",
        lambda path, _: ("a") * 64,
    )
    monkeypatch.setattr(u, "healthy", lambda: None)

    def run(*args, **kwargs):
        state["commands"].append(args)
        if args[0] == "tag":
            state["tags"][args[2]] = args[1]
        return ""

    def compose(path, env, *args):
        state["commands"].append(("up", str(path)))
        state["container"] = make(state["tags"][u.TAG], path, path == new)

    monkeypatch.setattr(u, "run", run)
    monkeypatch.setattr(u, "compose", compose)
    return state


def test_switch_then_recover(monkeypatch, tmp_path):
    """Test switch then recover."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    assert state["tags"][u.TAG] == NEW
    assert state["tags"][u.BACKUP] == OLD
    assert (u.STATE / "old-compose.yaml").read_bytes() == b"old"
    assert (u.STATE / "record.json").stat().st_mode & 0o777 == 0o600
    u.recover()
    assert state["tags"][u.TAG] == OLD
    assert state["container"]["Image"] == OLD


def test_collision_refused_before_mutation(monkeypatch, tmp_path):
    """Test collision refused before mutation."""
    state = fixture(monkeypatch, tmp_path)
    state["tags"][u.BACKUP] = NEW
    with pytest.raises(RuntimeError):
        u.switch(NEW)
    assert state["commands"] == []
    assert not u.STATE.exists()


def test_interrupted_after_tag_can_recover(monkeypatch, tmp_path):
    """Test interrupted after tag can recover."""
    state = fixture(monkeypatch, tmp_path)
    original = u.compose

    def crash(*args):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(u, "compose", crash)
    with pytest.raises(RuntimeError):
        u.switch(NEW)
    assert state["tags"][u.TAG] == NEW
    monkeypatch.setattr(u, "compose", original)
    u.recover()
    assert state["tags"][u.TAG] == OLD


def test_recovery_refuses_foreign_tag(monkeypatch, tmp_path):
    """Test recovery refuses foreign tag."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    state["tags"][u.TAG] = "sha256:" + "c" * 64
    state["commands"].clear()
    with pytest.raises(RuntimeError):
        u.recover()
    assert state["commands"] == []


def test_recovery_uses_snapshot_even_if_original_changes(monkeypatch, tmp_path):
    """Test recovery uses snapshot even if original changes."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    u.OLD.unlink()
    state["commands"].clear()
    u.recover()
    assert ("up", str(u.STATE / "old-compose.yaml")) in state["commands"]
    # Repeated recovery verifies snapshot labels, not the original labels.
    u.recover()


def test_recovery_refuses_corrupt_snapshot(monkeypatch, tmp_path):
    """Test recovery refuses corrupt snapshot."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    (u.STATE / "old-compose.yaml").write_bytes(b"changed")
    state["commands"].clear()
    with pytest.raises(RuntimeError):
        u.recover()
    assert state["commands"] == []


def test_image_listing_distinguishes_absent_from_docker_failure(monkeypatch):
    """Test image listing distinguishes absent from docker failure."""
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return ""

    monkeypatch.setattr(u, "run", run)
    assert u.image(u.BACKUP) is None
    assert len(calls) == 1

    def broken(*args, **kwargs):
        raise RuntimeError("Docker failure")

    monkeypatch.setattr(u, "run", broken)
    with pytest.raises(RuntimeError):
        u.image(u.BACKUP)


def test_image_inspect_failure_is_not_absence(monkeypatch):
    """Test image inspect failure is not absence."""

    def run(*args, **kwargs):
        if args[:2] == ("image", "ls"):
            return u.BACKUP + "\n"
        raise RuntimeError("Docker failure")

    monkeypatch.setattr(u, "run", run)
    with pytest.raises(RuntimeError):
        u.image(u.BACKUP)


def test_container_listing_and_inspect_fail_closed(monkeypatch):
    """Test container listing and inspect fail closed."""

    def run(*args, **kwargs):
        if args[0] == "ps":
            return u.CONTAINER + "\n"
        raise RuntimeError("Docker failure")

    monkeypatch.setattr(u, "run", run)
    with pytest.raises(RuntimeError):
        u.container()


def test_old_recovery_does_not_need_new_compose(monkeypatch, tmp_path):
    """Exercise the corresponding recovery safety guard."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    u.recover()
    u.NEW.unlink()
    u.recover()
    assert state["tags"][u.TAG] == OLD


def test_private_state_rejects_world_readable_files(monkeypatch, tmp_path):
    """Exercise the corresponding recovery safety guard."""
    fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    (u.STATE / "record.json").chmod(0o644)
    with pytest.raises(RuntimeError, match="0600"):
        u.recover()
    (u.STATE / "record.json").chmod(0o600)
    u.STATE.chmod(0o755)
    with pytest.raises(RuntimeError, match="0700"):
        u.recover()


def test_runtime_drift_refused_before_recovery_mutation(monkeypatch, tmp_path):
    """Exercise the corresponding recovery safety guard."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    state["container"]["HostConfig"] = {"Privileged": True}
    state["commands"].clear()
    with pytest.raises(RuntimeError, match="runtime drift"):
        u.recover()
    assert not state["commands"]


def test_pinned_bytes_rejects_symlink_and_changed_contents(monkeypatch, tmp_path):
    """Exercise the corresponding recovery safety guard."""
    fixture(monkeypatch, tmp_path)
    u.OLD.write_bytes(b"other")
    with pytest.raises(RuntimeError):
        u.pinned_bytes(u.OLD, u.OLD_HASH)
    u.OLD.unlink()
    u.OLD.symlink_to(u.NEW)
    with pytest.raises(OSError):
        u.pinned_bytes(u.OLD, u.OLD_HASH)


def test_snapshot_hash_must_equal_original_label(monkeypatch, tmp_path):
    """Exercise the corresponding recovery safety guard."""
    state = fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(u, "config_hash", lambda _path, _env: "b" * 64)
    with pytest.raises(RuntimeError, match="labels"):
        u.switch(NEW)
    assert not state["commands"]


def test_fifo_source_rejected_without_waiting(monkeypatch, tmp_path):
    """A FIFO must not block the guard while opening the source."""
    import os

    fixture(monkeypatch, tmp_path)
    u.OLD.unlink()
    os.mkfifo(u.OLD)
    with pytest.raises(RuntimeError, match="regular file"):
        u.pinned_bytes(u.OLD, u.OLD_HASH)


def test_candidate_before_baseline_recovery(monkeypatch, tmp_path):
    """Recover only if the captured old runtime also matches the candidate."""
    state = fixture(monkeypatch, tmp_path)
    original = u.durable

    def interrupted(path, data):
        if path.name == "candidate.json":
            raise RuntimeError("interrupted")
        original(path, data)

    monkeypatch.setattr(u, "durable", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        u.switch(NEW)
    assert not (u.STATE / "candidate.json").exists()
    state["container"]["HostConfig"] = {"Privileged": True}
    state["commands"].clear()
    with pytest.raises(RuntimeError, match="runtime drift"):
        u.recover()
    assert not state["commands"]
    del state["container"]["HostConfig"]
    u.recover()
    assert state["tags"][u.TAG] == OLD


def test_atomic_publication_does_not_expose_partial_record(monkeypatch, tmp_path):
    """Interrupted publication cannot expose an incomplete record."""
    fixture(monkeypatch, tmp_path)
    u.STATE.mkdir(mode=0o700)

    def interrupted(*args, **kwargs):
        raise OSError("interrupted before publication")

    monkeypatch.setattr(u.os, "link", interrupted)
    with pytest.raises(OSError):
        u.durable(u.STATE / "record.json", b"secret")
    assert not (u.STATE / "record.json").exists()
    assert not list(u.STATE.iterdir())


def test_fifo_lock_rejected_without_waiting(monkeypatch, tmp_path):
    """A substituted lock FIFO cannot hang the process."""
    import os

    fixture(monkeypatch, tmp_path)
    lock = tmp_path / "lock"
    os.mkfifo(lock)
    monkeypatch.setattr(u, "LOCK", lock)
    monkeypatch.setattr(u.os, "geteuid", lambda: 0)
    monkeypatch.setattr(u.sys, "argv", ["upgrade.py", "recover"])
    with pytest.raises((RuntimeError, OSError)):
        u.main()


def test_recovery_refuses_snapshot_compose_hash_drift(monkeypatch, tmp_path):
    """A different rendered snapshot must stop recovery before mutation."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    state["commands"].clear()
    monkeypatch.setattr(u, "config_hash", lambda *_: "b" * 64)
    with pytest.raises(RuntimeError, match="hash drift"):
        u.recover()
    assert not state["commands"]


@pytest.mark.parametrize("baseline", [True, False])
@pytest.mark.parametrize("drift", ["extra", "changed", "duplicate"])
def test_recovery_refuses_candidate_environment_drift(
    monkeypatch, tmp_path, baseline, drift
):
    """Reject candidate environment drift with and without a saved baseline."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    if not baseline:
        (u.STATE / "candidate.json").unlink()
    env = state["container"]["Config"]["Env"]
    if drift == "extra":
        env.append("EXTRA=value")
    elif drift == "changed":
        env[0] = "WORKOS_STAGING_ISSUER=changed"
    else:
        env.append(env[0])
    state["commands"].clear()
    with pytest.raises(RuntimeError):
        u.recover()
    assert not state["commands"]


def test_cli_switch_is_disabled_before_mutation(monkeypatch, tmp_path):
    """The executable must refuse switching until reproducibility is proven."""
    lock = tmp_path / "lock"
    lock.touch()
    monkeypatch.setattr(u, "LOCK", lock)
    monkeypatch.setattr(u, "trusted", lambda _: None)
    monkeypatch.setattr(u.os, "geteuid", lambda: 0)
    monkeypatch.setattr(u.sys, "argv", ["upgrade.py", "switch", NEW])
    monkeypatch.setattr(u, "switch", lambda _: pytest.fail("switch was called"))
    with pytest.raises(RuntimeError, match="Switch disabled"):
        u.main()


def test_complete_inventory_rejects_duplicates_renames_and_other_services(monkeypatch):
    """Even stopped or renamed project members make recreation unsafe."""
    import copy
    import json

    ident = "a" * 64
    extra_id = "b" * 64
    original: dict[str, Any] = {
        "Id": ident,
        "Name": "/" + u.CONTAINER,
        "Config": {
            "Labels": {
                "com.docker.compose.project": "di-staging",
                "com.docker.compose.service": "staging-mcp",
            }
        },
    }
    items = [original]

    def run(*args):
        if args[0] == "ps":
            return "\n".join(c["Id"] for c in items)
        return json.dumps([next(c for c in items if c["Id"] == args[1])])

    monkeypatch.setattr(u, "run", run)
    assert u.container() == original
    for name, service in [("renamed", "staging-mcp"), ("other", "other")]:
        extra = copy.deepcopy(original)
        extra["Id"] = extra_id
        extra["Name"] = "/" + name
        extra["Config"]["Labels"]["com.docker.compose.service"] = service
        items.append(extra)
        with pytest.raises(RuntimeError, match="inventory"):
            u.container()
        items.pop()
    original["Name"] = "/intermediate"
    with pytest.raises(RuntimeError, match="inventory"):
        u.container()
    items.clear()
    assert u.container() is None


def test_inventory_inspection_failure_is_not_absence(monkeypatch):
    """Inspection failures do not establish an empty inventory."""

    def run(*args):
        if args[0] == "ps":
            return "a" * 64
        raise RuntimeError("inspection failed")

    monkeypatch.setattr(u, "run", run)
    with pytest.raises(RuntimeError, match="inspection failed"):
        u.container()


def test_recovery_missing_container_rechecks_before_compose(monkeypatch, tmp_path):
    """A container appearing during recovery prevents recreation."""
    state = fixture(monkeypatch, tmp_path)
    u.switch(NEW)
    state["container"] = None
    state["commands"].clear()
    original_run = u.run

    def race(*args, **kwargs):
        result = original_run(*args, **kwargs)
        if args == ("tag", OLD, u.TAG):
            state["container"] = {"Id": "unexpected"}
        return result

    monkeypatch.setattr(u, "run", race)
    with pytest.raises(RuntimeError, match="Drift"):
        u.recover()
    assert not any(command[0] == "up" for command in state["commands"])
