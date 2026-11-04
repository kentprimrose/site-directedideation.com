#!/usr/bin/env python3
"""Replace the staging build context with only its explicit source inputs."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "staging_mcp/Dockerfile",
    "staging_mcp/requirements.lock",
    "staging_mcp/server.py",
    "staging_mcp/healthcheck.py",
    "src/site_directedideation_com/__init__.py",
    "src/site_directedideation_com/metrics.py",
    "src/site_directedideation_com/mcp/__init__.py",
    "src/site_directedideation_com/mcp/http_boundary.py",
)


def prepare(root: Path) -> Path:
    """Recreate the context from the explicit allowlist."""
    context = root / "staging_mcp/.build-context"
    if context.is_symlink():
        raise ValueError("build context must not be a symlink")
    if context.exists():
        try:
            shutil.rmtree(context)
        except OSError as exc:
            raise OSError(f"cannot remove build context: {context}") from exc
    for name in FILES:
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"build input is not a regular file: {name}")
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return context


if __name__ == "__main__":
    print(prepare(ROOT))
