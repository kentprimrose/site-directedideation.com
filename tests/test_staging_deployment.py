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
    assert "context: .build-context" in compose
    assert "dockerfile: staging_mcp/Dockerfile" in compose
    assert "additional_contexts:" not in compose


def test_proxy_example_only_targets_staging():
    """The example must never direct requests to the private MCP."""
    config = (STAGING / "nginx.conf.example").read_text()
    assert "server_name mcp-staging.directedideation.com;" in config
    assert "proxy_pass http://127.0.0.1:8765;" in config
    assert "8001" not in config
    assert "client_max_body_size 64k;" in config
    assert (
        "limit_req_zone $binary_remote_addr zone=staging_mcp_req:10m rate=60r/m;"
        in config
    )
    assert "limit_conn_zone $binary_remote_addr" in config
    assert "limit_req zone=staging_mcp_req burst=20 nodelay;" in config
    assert "limit_conn staging_mcp_conn 4;" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert 'proxy_set_header Forwarded "";' in config
    assert "access_log off;" in config
    assert "ssl_certificate_key /etc/letsencrypt/" in config
    assert "proxy_read_timeout 300s;" in config
    assert config.count("listen 0.0.0.0:443 ssl;") == 1
    assert "listen 443 ssl;" not in config
    assert "listen [::]" not in config
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in config
    assert "server_tokens off;" in config
    assert "limit_req_log_level warn;" in config
    assert "limit_conn_log_level warn;" in config
    assert "proxy_set_header Authorization $http_authorization;" in config


def test_proxy_activation_and_certificate_bootstrap_are_gated():
    """Require activation, listener review, and safe certificate bootstrap gates."""
    deployment = " ".join((STAGING / "DEPLOYMENT.md").read_text().split())
    assert "General production remains blocked" in deployment
    assert "60 requests/minute with a burst of 20" in deployment
    assert "certonly" in deployment and "--webroot" in deployment
    assert "Do not use `certbot --nginx`" in deployment
    assert "stop if inherited real-IP settings" in deployment
    assert "verify no AAAA record or IPv6 listener" in deployment
    assert "no `Retry-After`" in deployment
    assert "implicit defaults" in deployment
    assert "missing or unknown SNI" in deployment
    assert "unexpected Host cannot route to staging" in deployment
    assert "ssl_reject_handshake on;" in deployment
    assert "not included in the example" in deployment


def test_http01_example_is_isolated_and_fail_closed():
    """Keep the ACME bootstrap route separate and fail closed."""
    config = (STAGING / "nginx-http01.conf.example").read_text()
    assert "listen 80;" in config
    assert "server_name mcp-staging.directedideation.com;" in config
    assert (
        "if ($http_host !~* ^mcp-staging\\.directedideation\\.com(?::80)?$)" in config
    )
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "root /var/lib/di-staging-acme;" in config
    assert "try_files $uri =404;" in config
    assert "return 444;" in config and "return 404;" in config
    assert "proxy_pass" not in config and "default_server" not in config
    assert "ssl_certificate" not in config


def test_pilot_rollback_and_production_gates():
    """The closed test is distinct from the pilot and production gates."""
    deployment = " ".join((STAGING / "DEPLOYMENT.md").read_text().split())
    for required in (
        "prior one-time ping-only test is closed",
        "The authorized small public pilot is active for non-sensitive use",
        "no rollback timer is planned for the pilot",
        "configuration digest matches the configuration to be rolled back",
        "independently verify external closure",
        "General production remains blocked",
    ):
        assert required in deployment


def test_http01_bootstrap_and_renewal_are_separately_gated():
    """Certificate operations remain gated separately from MCP access."""
    deployment = " ".join((STAGING / "DEPLOYMENT.md").read_text().split())
    for required in (
        "public ACME-only HTTP route",
        "no AAAA record",
        "implicit defaults",
        "certbot certonly --webroot",
        "nginx -t && systemctl reload nginx",
        "--dry-run --run-deploy-hooks",
        "does not approve public MCP access",
    ):
        assert required in deployment


def test_build_context_excludes_environment_files():
    """Keep the legacy staging-directory ignore and image hardening intact."""
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


def test_both_build_stages_use_verified_python_multi_platform_index():
    """Do not silently fall back to a mutable tag or a single-platform image."""
    dockerfile = (STAGING / "Dockerfile").read_text()
    stages = [
        line.split() for line in dockerfile.splitlines() if line.startswith("FROM ")
    ]
    pinned = (
        "docker.io/library/python:3.11-slim@sha256:"
        "db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893"
    )
    assert stages == [["FROM", pinned, "AS", "dependencies"], ["FROM", pinned]]


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


def test_generated_build_context_excludes_sensitive_files(tmp_path):
    """Neither source secrets nor stale generated files enter the build context."""
    from scripts.prepare_staging_build_context import FILES, prepare

    for name in FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"input: {name}")
    for name in (
        ".env",
        "src/site_directedideation_com/.env",
        "src/site_directedideation_com/mcp/credentials.json",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-sensitive-value")
    stale = tmp_path / "staging_mcp/.build-context/credentials.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("synthetic-sensitive-value")
    context = prepare(tmp_path)
    assert {
        str(p.relative_to(context)) for p in context.rglob("*") if p.is_file()
    } == set(FILES)
    assert all(
        "synthetic-sensitive-value" not in p.read_text()
        for p in context.rglob("*")
        if p.is_file()
    )
