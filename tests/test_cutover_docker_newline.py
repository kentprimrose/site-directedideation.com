"""Regression tests using Docker's trailing template-output newline."""

import pytest
import test_prod_cutover_backend as backend

pytest_plugins = ("test_prod_cutover_backend",)


@pytest.fixture(autouse=True)
def docker_template_newline(monkeypatch):
    """The inspect command adds a newline even when a template prints one."""
    needle = (
        "            if s.get('dup_host') and key == 'STAGING_MCP_HOST': "
        "print(key + '=' + s['env'][field])\n"
    )
    assert needle in backend.DOCKER
    monkeypatch.setattr(
        backend, "DOCKER", backend.DOCKER.replace(needle, needle + "    print()\n")
    )


def test_record_accepts_one_host_with_docker_newline(env):
    """One host must not be mistaken for a duplicate."""
    result = env.record()
    assert result.returncode == 0, result.stderr
    result = env.run("apply", "r1", env.newenv())
    assert result.returncode == 0, result.stderr


def test_record_still_rejects_duplicate_hosts(env):
    """Two actual host entries must still be rejected."""
    env.patch(dup_host=True)
    assert env.record().returncode != 0
