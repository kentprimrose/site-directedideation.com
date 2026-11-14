#!/usr/bin/env python3
"""Render the pilot cutover artifacts for a new public host. Local only.

Writes files into an empty output directory and prints their SHA-256 digests.
Touches no host, network or privileged path. Inputs are the reviewed repository
files; every substitution is asserted so silent drift fails the build.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGING = HERE.parent
OLD_HOST = "mcp-staging.directedideation.com"
APPROVED_HOST = "mcp.directedideation.com"  # G2; server.py rejects any other
# Historical conf digests the rollback helper must keep accepting. They are
# repository constants, NOT evidence about the live host: inventory must confirm.
CURRENT_DIGEST = "7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530"
PREVIOUS_DIGEST = "814b89c83fcc507d773cb73fee5f77a1a727d45da48b03927cf5959f4d32d3f4"
FAIL_CLOSED_PREFIX = (
    "# Pilot public host: fail-closed IPv4 TLS default.\n"
    "server {\n"
    "    listen 0.0.0.0:443 ssl default_server;\n"
    "    ssl_reject_handshake on;\n"
    "    return 444;\n"
    "}\n\n"
)
SHA = re.compile(r"[0-9a-f]{64}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace(text: str, old: str, new: str, count: int) -> str:
    if text.count(old) != count:
        raise ValueError(f"expected {count} occurrence(s) of {old!r}")
    return text.replace(old, new)


def check_host(host: str) -> str:
    if host != APPROVED_HOST:
        raise ValueError(f"host must be {APPROVED_HOST} (server.py approves no other)")
    return host


def render_public_conf(host: str) -> bytes:
    """Single public file: fail-closed default, one server block, 8765 only."""
    check_host(host)
    text = (STAGING / "nginx.conf.example").read_text()
    text = _replace(text, OLD_HOST, host, 3)  # server_name + two cert paths
    assert OLD_HOST not in text
    # Design rules: one proxy target, each zone defined once, no real_ip, no IPv6.
    assert text.count("proxy_pass http://127.0.0.1:8765;") == 1
    assert "8001" not in text and "real_ip" not in text.replace("do not enable real_ip", "")
    assert text.count("limit_req_zone") == 1 and text.count("limit_conn_zone") == 1
    assert text.count("default_server") == 0 and "listen [::]" not in text
    return (FAIL_CLOSED_PREFIX + text).encode()


def render_acme_vhost(host: str) -> bytes:
    check_host(host)
    text = (STAGING / "nginx-http01.conf.example").read_text()
    text = _replace(text, OLD_HOST, host, 1)
    text = _replace(text, r"mcp-staging\.directedideation\.com", host.replace(".", r"\."), 1)
    assert "mcp-staging" not in text
    return text.encode()


def render_helper(new_digest: str) -> bytes:
    """Rollback helper accepting the new, current and previous conf digests."""
    if not SHA.fullmatch(new_digest):
        raise ValueError("bad digest")
    text = (STAGING / "shared-nginx-test/di-shared-test").read_text()
    text = _replace(text, f"DIGEST = '{CURRENT_DIGEST}'", f"DIGEST = '{new_digest}'", 1)
    text = _replace(
        text,
        f"OLD_DIGEST = '{PREVIOUS_DIGEST}'",
        f"OLD_DIGEST = '{CURRENT_DIGEST}'\nPREVIOUS_DIGEST = '{PREVIOUS_DIGEST}'\n"
        "ACCEPTED = (DIGEST, OLD_DIGEST, PREVIOUS_DIGEST)",
        1,
    )
    text = _replace(text, "not in (DIGEST, OLD_DIGEST)", "not in ACCEPTED", 1)
    return text.encode()


def render_hook(host: str) -> bytes:
    check_host(host)
    text = (HERE / "certbot-deploy-hook.sh").read_text()
    return _replace(text, "@HOST@", host, 1).encode()


def build(host: str, out: Path) -> dict:
    out = Path(out)
    out.mkdir(parents=True)  # must not already exist: never overwrite evidence
    conf = render_public_conf(host)
    files = {
        "di-staging-public-test.conf": conf,
        "di-staging-acme-http01.conf": render_acme_vhost(host),
        "di-shared-test": render_helper(sha256(conf)),
        "certbot-deploy-hook.sh": render_hook(host),
    }
    lines = []
    for name, data in files.items():
        (out / name).write_bytes(data)
        lines.append(f"{sha256(data)}  {name}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return {name: sha256(data) for name, data in files.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=APPROVED_HOST)
    ap.add_argument("--out", required=True, help="new, non-existent directory")
    args = ap.parse_args(argv)
    try:
        digests = build(args.host, Path(args.out))
    except (ValueError, AssertionError, FileExistsError) as exc:
        print(f"build_package: {exc}", file=sys.stderr)
        return 1
    for name, digest in digests.items():
        print(f"{digest}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
