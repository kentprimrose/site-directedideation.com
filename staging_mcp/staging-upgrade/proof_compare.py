"""Offline, fail-closed comparison building block, not a reproducibility proof.

The caller must establish provenance, ownership, safe creation and cleanup. This
module deliberately supports only containers with networking disabled and no
published ports; it cannot establish reproducibility of the staging service.
"""

import re


class ComparisonError(ValueError):
    """A non-sensitive comparison failure."""


def _environment(config):
    entries = config["Env"]
    if not isinstance(entries, list):
        raise ComparisonError("Invalid environment.")
    result = {}
    for entry in entries:
        if not isinstance(entry, str) or "=" not in entry:
            raise ComparisonError("Invalid environment.")
        key, value = entry.split("=", 1)
        if not key or key in result:
            raise ComparisonError("Ambiguous environment.")
        result[key] = value
    return result


def compare(baseline, probe, expected_image):
    """Compare selected inspect fields without returning environment contents.

    This is intentionally not wired into the upgrade command. A matching result
    is necessary but not sufficient for a proof of safe recreation.
    """
    try:
        if not isinstance(expected_image, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", expected_image
        ):
            raise ComparisonError("Invalid image identity.")
        for c in (baseline, probe):
            if c["Image"] != expected_image:
                raise ComparisonError("Image mismatch.")
            host = c["HostConfig"]
            if host["NetworkMode"] != "none" or host["PortBindings"] not in (None, {}):
                raise ComparisonError("Unsupported network or port configuration.")
            if c["Config"].get("ExposedPorts") not in (None, {}):
                raise ComparisonError("Unsupported exposed ports.")
        if probe["State"]["Running"] is not False:
            raise ComparisonError("Probe must be stopped.")
        if _environment(baseline["Config"]) != _environment(probe["Config"]):
            raise ComparisonError("Environment mismatch.")
        _compare_runtime(baseline, probe)
    except (KeyError, TypeError, AttributeError):
        raise ComparisonError("Invalid inspection data.") from None


def _compare_runtime(baseline, probe):
    # Only compare explicit fields. Missing fields are errors rather than
    # treating a missing inspect field as a default value.
    config_keys = (
        "Cmd",
        "Entrypoint",
        "User",
        "WorkingDir",
        "Healthcheck",
        "Volumes",
        "StopSignal",
    )
    host_keys = (
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
    )
    for section, keys in (("Config", config_keys), ("HostConfig", host_keys)):
        for key in keys:
            if baseline[section][key] != probe[section][key]:
                raise ComparisonError("Selected runtime mismatch.")
