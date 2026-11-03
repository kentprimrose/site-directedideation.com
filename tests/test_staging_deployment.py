"""Guard the staging deployment's most important isolation invariants."""

from pathlib import Path

STAGING = Path(__file__).resolve().parents[1] / "staging_mcp"


def test_staging_compose_is_loopback_only_and_has_no_mounts():
    """Keep the staging backend separate from the private backend and data."""
    compose = (STAGING / "compose.yaml").read_text()
    assert '"127.0.0.1:8765:8765"' in compose
    assert "8001" not in compose
    assert "volumes:" not in compose
    assert "docker.sock" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "WORKOS_STAGING_ALLOWED_SUBJECTS:?" in compose


def test_proxy_example_only_targets_staging():
    """The example must never direct requests to the private MCP."""
    config = (STAGING / "Caddyfile.example").read_text()
    assert "mcp-staging.directedideation.com {" in config
    assert "reverse_proxy 127.0.0.1:8765" in config
    assert "8001" not in config
    assert "max_size 64KB" in config
    assert "log {" not in config


def test_build_context_excludes_environment_files():
    """Only the explicitly allowed server and Dockerfile enter the context."""
    rules = (STAGING / ".dockerignore").read_text().splitlines()
    assert rules == [
        "**",
        "!Dockerfile",
        "!server.py",
        "!healthcheck.py",
        "!requirements.lock",
    ]
    dockerfile = (STAGING / "Dockerfile").read_text()
    assert "USER 10001:10001" in dockerfile
    assert '"--no-access-log"' in dockerfile


def test_runtime_hardening_and_lock_export():
    """Keep the container limits and hash-checked locked dependency input."""
    import subprocess

    compose = (STAGING / "compose.yaml").read_text()
    dockerfile = (STAGING / "Dockerfile").read_text()
    assert "/tmp:rw,noexec,nosuid,nodev,size=16m" in compose
    assert '"/app/healthcheck.py"' in compose
    assert "--require-hashes --only-binary=:all:" in dockerfile
    result = subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--quiet",
        ],
        cwd=STAGING.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == (STAGING / "requirements.lock").read_text()


def test_healthcheck_request_hits_authentication_boundary(monkeypatch):
    """The configured probe receives 401 only when the app responds normally."""
    from starlette.testclient import TestClient

    from staging_mcp.server import create_app

    monkeypatch.setenv("WORKOS_STAGING_ISSUER", "https://auth.example.com")
    monkeypatch.setenv("WORKOS_STAGING_ALLOWED_SUBJECTS", "user_ABC")
    with TestClient(create_app()) as client:
        response = client.post(
            "/mcp",
            headers={"host": "mcp-staging.directedideation.com"},
            follow_redirects=False,
        )
    assert response.status_code == 401
