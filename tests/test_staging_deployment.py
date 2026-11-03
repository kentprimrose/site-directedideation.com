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
    config = (STAGING / "nginx.conf.example").read_text()
    assert "server_name mcp-staging.directedideation.com;" in config
    assert "proxy_pass http://127.0.0.1:8765;" in config
    assert "8001" not in config
    assert "client_max_body_size 64k;" in config
    assert "limit_req_zone $binary_remote_addr" in config
    assert "limit_conn_zone $binary_remote_addr" in config
    assert "limit_req zone=staging_mcp_req burst=5 nodelay;" in config
    assert "limit_conn staging_mcp_conn 4;" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert 'proxy_set_header Forwarded "";' in config
    assert "access_log off;" in config
    assert "ssl_certificate_key /etc/letsencrypt/" in config
    assert "proxy_read_timeout 300s;" in config
    assert "listen 443 ssl;" in config
    assert "listen [::]" not in config
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in config
    assert "server_tokens off;" in config
    assert "limit_req_log_level warn;" in config
    assert "limit_conn_log_level warn;" in config
    assert "proxy_set_header Authorization $http_authorization;" in config


def test_proxy_activation_and_certificate_bootstrap_are_gated():
    """Require activation, listener review, and safe certificate bootstrap gates."""
    deployment = " ".join((STAGING / "DEPLOYMENT.md").read_text().split())
    assert "currently BLOCKED" in deployment
    assert "certonly" in deployment and "--webroot" in deployment
    assert "Do not use `certbot --nginx`" in deployment
    assert "does not override inherited real-IP settings" in deployment
    assert "full IPv6 address keys allow /64 address rotation" in deployment
    assert "no `Retry-After`" in deployment
    assert "implicit defaults" in deployment
    assert "no SNI, an unknown SNI" in deployment
    assert "staging SNI with an unexpected Host" in deployment
    assert "ssl_reject_handshake on;" in deployment
    assert "not included in the example" in deployment



def test_http01_example_is_isolated_and_fail_closed():
    config = (STAGING / "nginx-http01.conf.example").read_text()
    assert "listen 80;" in config
    assert "server_name mcp-staging.directedideation.com;" in config
    assert 'if ($http_host !~* ^mcp-staging\\.directedideation\\.com(?::80)?$)' in config
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "root /var/lib/di-staging-acme;" in config
    assert "try_files $uri =404;" in config
    assert "return 444;" in config and "return 404;" in config
    assert "proxy_pass" not in config and "default_server" not in config
    assert "ssl_certificate" not in config


def test_http01_bootstrap_and_renewal_are_separately_gated():
    deployment = " ".join((STAGING / "DEPLOYMENT.md").read_text().split())
    for required in ("public ACME-only HTTP route", "no AAAA record", "implicit defaults",
                     "certbot certonly --webroot", "nginx -t && systemctl reload nginx",
                     "--dry-run --run-deploy-hooks", "does not approve public MCP access"):
        assert required in deployment

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
