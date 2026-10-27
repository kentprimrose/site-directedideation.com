"""Tests for the FastAPI application."""

from fastapi.testclient import TestClient

from site_directedideation_com.api import app


def test_root_returns_hello_world() -> None:
    """The root endpoint returns the hello-world greeting as JSON."""
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, world!"}
