"""The offline comparison is necessary, never sufficient, for a proof."""

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest

spec = importlib.util.spec_from_file_location(
    "proof_compare", Path("staging_mcp/staging-upgrade/proof_compare.py")
)
assert spec and spec.loader
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)
IMAGE = "sha256:" + "a" * 64


def inspected():
    """Build an inspect-shaped fixture."""
    config: dict[str, Any] = {
        k: None
        for k in (
            "Cmd",
            "Entrypoint",
            "User",
            "WorkingDir",
            "Healthcheck",
            "Volumes",
            "StopSignal",
            "ExposedPorts",
        )
    }
    config["Env"] = ["A=secret", "B=x=y"]
    host: dict[str, Any] = {
        k: None
        for k in (
            "Binds",
            "Mounts",
            "RestartPolicy",
            "ReadonlyRootfs",
            "Tmpfs",
            "CapAdd",
            "CapDrop",
            "SecurityOpt",
            "Privileged",
            "PidMode",
            "IpcMode",
            "UsernsMode",
            "Devices",
            "PidsLimit",
            "Memory",
            "NanoCpus",
            "CpuShares",
            "LogConfig",
            "ExtraHosts",
            "Dns",
            "DnsSearch",
            "DnsOptions",
            "PortBindings",
        )
    }
    host["NetworkMode"] = "none"
    return {
        "Image": IMAGE,
        "Config": config,
        "HostConfig": host,
        "State": {"Running": False},
    }


def test_equal_and_environment_order():
    """Environment comparison ignores ordering only."""
    a = inspected()
    b = copy.deepcopy(a)
    b["Config"]["Env"].reverse()
    assert proof.compare(a, b, IMAGE) is None


@pytest.mark.parametrize(
    "change",
    [
        "secret",
        "duplicate",
        "runtime",
        "port",
        "network",
        "running",
        "image",
        "missing",
    ],
)
def test_rejects_drift_without_disclosing_secrets(change):
    """Fail closed without echoing values."""
    a = inspected()
    b = copy.deepcopy(a)
    if change == "secret":
        b["Config"]["Env"][0] = "A=different-secret"
    if change == "duplicate":
        b["Config"]["Env"].append("A=secret")
    if change == "runtime":
        b["HostConfig"]["Privileged"] = True
    if change == "port":
        b["HostConfig"]["PortBindings"] = {"80/tcp": []}
    if change == "network":
        b["HostConfig"]["NetworkMode"] = "bridge"
    if change == "running":
        b["State"]["Running"] = True
    if change == "image":
        b["Image"] = "sha256:" + "b" * 64
    if change == "missing":
        del b["HostConfig"]["Memory"]
    with pytest.raises(proof.ComparisonError) as error:
        proof.compare(a, b, IMAGE)
    assert "secret" not in str(error.value)
