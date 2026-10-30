"""Persistence, concurrency, privacy and admin authentication checks."""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from site_directedideation_com.admin import app
from site_directedideation_com.mcp import mcp
from site_directedideation_com.metrics import increment, snapshot


@pytest.fixture
def settings(monkeypatch, tmp_path):
    """Use isolated explicit development settings."""
    monkeypatch.setenv("METRICS_ENV", "development")
    monkeypatch.setenv("METRICS_DB", str(tmp_path / "metrics.db"))
    return tmp_path / "metrics.db"


def test_concurrent_persistent_bounded_counters(settings):
    """Concurrent writes retain bounded totals without private input."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda _: increment("get_interview_guidance", "unfiltered"), range(100)
            )
        )
    counts = snapshot()
    assert counts["tools"]["get_interview_guidance"] == 100
    assert counts["stage_filters"]["unfiltered"] == 100
    assert b"SENTINEL_PRIVATE" not in settings.read_bytes()
    with pytest.raises(ValueError):
        increment("SENTINEL_PRIVATE")
    assert b"SENTINEL_PRIVATE" not in settings.read_bytes()


@pytest.mark.usefixtures("settings")
def test_development_dashboard():
    """Explicit development permits local dashboard access."""
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "get_directed_ideation_method" in response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.usefixtures("settings")
def test_production_fails_closed_and_authenticates(monkeypatch):
    """Production requires valid credentials and rejects bad logins."""
    monkeypatch.setenv("METRICS_ENV", "production")
    monkeypatch.delenv("METRICS_ADMIN_USER_SHA256", raising=False)
    monkeypatch.delenv("METRICS_ADMIN_PASSWORD_SCRYPT", raising=False)
    with pytest.raises(RuntimeError), TestClient(app):
        pass
    salt = bytes(range(16))
    monkeypatch.setenv(
        "METRICS_ADMIN_USER_SHA256", hashlib.sha256(b"admin").hexdigest()
    )
    digest = hashlib.scrypt(b"secret", salt=salt, n=16384, r=8, p=1, dklen=32).hex()
    monkeypatch.setenv("METRICS_ADMIN_PASSWORD_SCRYPT", salt.hex() + ":" + digest)
    with TestClient(app) as client:
        assert client.get("/").status_code == 401
        assert client.get("/", auth=("admin", "wrong")).status_code == 401
        assert client.get("/", auth=("admin", "secret")).status_code == 200


@pytest.mark.usefixtures("settings")
def test_bad_environment_fails_closed(monkeypatch):
    """Invalid environment refuses startup."""
    monkeypatch.setenv("METRICS_ENV", "prod")
    with pytest.raises(RuntimeError), TestClient(app):
        pass


@pytest.mark.parametrize("failure", ["missing_config", "missing_directory"])
def test_mcp_startup_rejects_unusable_metrics(monkeypatch, tmp_path, failure):
    """A server must not become ready with missing configuration or storage."""
    monkeypatch.setattr("site_directedideation_com.metrics.load_dotenv", lambda: None)
    monkeypatch.delenv("METRICS_ENV", raising=False)
    monkeypatch.delenv("METRICS_DB", raising=False)
    if failure == "missing_directory":
        monkeypatch.setenv("METRICS_ENV", "development")
        monkeypatch.setenv("METRICS_DB", str(tmp_path / "missing" / "metrics.db"))
    with pytest.raises(RuntimeError, match="MCP metrics startup validation failed"):
        with TestClient(mcp.http_app()):
            pass


@pytest.mark.usefixtures("settings")
def test_mcp_startup_initializes_configured_storage(settings):
    """Startup initializes storage without recording a tool call."""
    with TestClient(mcp.http_app()):
        assert settings.exists()
        assert snapshot()["tools"]["get_directed_ideation_method"] == 0
