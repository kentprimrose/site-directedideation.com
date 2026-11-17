"""The deployment gate rejects stale revisions and API failures."""

import io
import json
from unittest.mock import patch

import pytest

from scripts import check_main_tip


@pytest.mark.parametrize("tip,accepted", [("a" * 40, True), ("b" * 40, False)])
def test_main_tip(monkeypatch, tip, accepted):
    """Only the current main revision may pass."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    body = json.dumps({"object": {"sha": tip}}).encode()
    with patch.object(
        check_main_tip.urllib.request, "urlopen", return_value=io.BytesIO(body)
    ):
        if accepted:
            check_main_tip.main()
        else:
            with pytest.raises(SystemExit, match="not the current main tip"):
                check_main_tip.main()


def test_api_failure_fails_closed(monkeypatch):
    """An unavailable API must not allow deployment."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    with patch.object(check_main_tip.urllib.request, "urlopen", side_effect=OSError):
        with pytest.raises(OSError):
            check_main_tip.main()
