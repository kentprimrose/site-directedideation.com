"""Shared test configuration."""

import os
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module", autouse=True)
def isolated_mcp_metrics(request, tmp_path_factory):
    """Give protocol tests a persistent, isolated development database."""
    if request.module.__name__.endswith("test_mcp"):
        with patch.dict(
            os.environ,
            {
                "METRICS_ENV": "development",
                "METRICS_DB": str(tmp_path_factory.mktemp("mcp") / "metrics.sqlite3"),
            },
        ):
            yield
    else:
        yield
