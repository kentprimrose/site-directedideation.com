"""Exercise the pilot allowlist helper without contacting Docker."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "staging_mcp/add-allowed-user.sh"
ID = "user_00000000000000000000000000"
OTHER = "user_01M6JDFK12D26WW0V8YYT7YRVN"

MOCK = r"""#!/usr/bin/env python3
import json, os, sys, time
p = os.environ['MOCK_STATE']
s = json.load(open(p))
a = sys.argv[1:]
assert a[:2] == ['--host', 'unix:///var/run/docker.sock']
a = a[2:]
assert os.environ['DOCKER_HOST'] == 'unix:///var/run/docker.sock'
assert 'DOCKER_CONTEXT' not in os.environ and 'COMPOSE_FILE' not in os.environ
if a[0] == 'image':
    print('sha256:' + ('b' if s.get('tag_mismatch') else 'a') * 64)
elif a[0] == 'inspect':
    if s.get('absent'): sys.exit(1)
    t = a[2]
    if t == '{{.Id}}': print('c' * 64)
    elif t == '{{.Image}}':
        print('sha256:' + ('b' if s.get('image_mismatch') else 'a') * 64)
    elif t == '{{.Config.Image}}': print('directed-ideation-staging-mcp:local')
    elif '.State.Running' in t: print('true')
    elif 'project.config_files' in t: print(s['path'])
    elif 'project.working_dir' in t: print(os.path.dirname(s['path']))
    elif 'config-hash' in t: print('a' * 64)
    elif 'compose.project' in t: print(s.get('project', 'di-staging'))
    elif 'compose.service' in t: print('staging-mcp')
    elif 'STAGING_MCP_HOST' in t:
        if s.get('host') is not None:
            print('STAGING_MCP_HOST=' + s['host'])
            if s.get('duplicate_host'): print('STAGING_MCP_HOST=' + s['host'])
    elif 'ALLOWED_SUBJECTS' in t:
        print('WORKOS_STAGING_ALLOWED_SUBJECTS=' + s['subjects'])
    elif 'ISSUER' in t: print('WORKOS_STAGING_ISSUER=' + s['issuer'])
elif a[0] == 'compose':
    # The helper intentionally clears the environment; state location comes from PATH.
    if 'config' in a:
        print('staging-mcp ' + ('b' if s.get('drift') or os.environ['STAGING_MCP_HOST'] != s.get('hash_host', s.get('host') or 'mcp-staging.directedideation.com') else 'a') * 64)
    elif 'up' in a:
        assert '--no-build' in a and '--pull' in a and 'never' in a and '--no-deps' in a
        if s.get('fail_up'): sys.exit(1)
        time.sleep(0.15)
        s['host'] = 'wrong.example' if s.get('wrong_after_host') else os.environ['STAGING_MCP_HOST']
        s['subjects'] = os.environ['WORKOS_STAGING_ALLOWED_SUBJECTS']
        s['ups'] = s.get('ups', 0) + 1
        json.dump(s, open(p, 'w'))
"""


@pytest.fixture
def setup(tmp_path):
    """Prepare a mock Docker and an unprivileged copy of the helper."""
    script = tmp_path / "helper"
    script.write_text(
        SCRIPT.read_text()
        .replace("realpath -e --", "realpath")
        .replace("[[ $EUID == 0 ]] || fail 'Run as root with sudo.'", ":")
        .replace("/run/lock/di-staging-allowlist.lock", str(tmp_path / "lock"))
        .replace("/bin/bash \"$0\"", f"{shutil.which('bash')} \"$0\"")
        .replace("/etc/di-staging", str(tmp_path))
        .replace("for path in / /etc ", "for path in / ")
        .replace("sha256sum", "shasum -a 256")
        .replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={tmp_path}:/usr/bin:/bin")
        .replace("$(stat -c '%u' \"$path\")", "0")
        .replace("$(stat -c '%a' \"$path\")", "700")
    )
    script.chmod(0o755)
    compose = tmp_path / "compose.yaml"
    compose.write_bytes((SCRIPT.parent / "compose.yaml").read_bytes())
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "path": str(compose),
                "subjects": "user_existing",
                "issuer": "https://example.com",
                "host": "mcp-staging.directedideation.com",
            }
        )
    )
    # Compose is invoked with env -i. Embed the mock state path in the executable.
    flock = tmp_path / "flock"
    flock.write_text(
        "#!/usr/bin/env python3\nimport fcntl\nfcntl.flock(9, fcntl.LOCK_EX)\n"
    )
    flock.chmod(0o755)
    docker = tmp_path / "docker"
    docker.write_text(
        MOCK.replace("p = os.environ['MOCK_STATE']", f"p = {str(state)!r}")
    )
    docker.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        DOCKER_CONTEXT="hostile", COMPOSE_FILE="hostile",
    )

    def run(user=ID):
        return subprocess.run(
            [str(script), user], env=env, capture_output=True, text=True
        )

    return state, run, env, script


def test_add_and_idempotent(setup):
    """Verify the helper behavior with mocked Docker."""
    state, run, _, _ = setup
    assert run().returncode == 0
    assert json.loads(state.read_text())["subjects"] == "user_existing," + ID
    assert run().returncode == 0
    assert json.loads(state.read_text())["ups"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"subjects": "user_a,,user_b"},
        {"host": "evil.example"},
        {"duplicate_host": True},
        {"host": "mcp.directedideation.com", "hash_host": "mcp-staging.directedideation.com"},
        {"project": "wrong"},
        {"drift": True},
        {"absent": True},
        {"fail_up": True},
        {"tag_mismatch": True},
        {"image_mismatch": True},
    ],
)
def test_fail_closed(setup, changes):
    """Verify the helper behavior with mocked Docker."""
    state, run, _, _ = setup
    data = json.loads(state.read_text())
    data.update(changes)
    state.write_text(json.dumps(data))
    result = run()
    assert result.returncode != 0
    assert "https://example.com" not in result.stdout + result.stderr
    assert json.loads(state.read_text()).get("ups", 0) == 0


def test_invalid_id(setup):
    """Verify the helper behavior with mocked Docker."""
    state, run, _, _ = setup
    assert run("user_bad").returncode != 0
    assert json.loads(state.read_text()).get("ups", 0) == 0


def test_concurrent_updates_preserve_both(setup):
    """Verify the helper behavior with mocked Docker."""
    state, _, env, script = setup
    first = subprocess.Popen(
        [str(script), ID], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(0.03)
    second = subprocess.Popen(
        [str(script), OTHER], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert first.wait() == second.wait() == 0
    assert set(json.loads(state.read_text())["subjects"].split(",")) == {
        "user_existing",
        ID,
        OTHER,
    }


def test_unreviewed_compose_refused(setup):
    """Reject a Compose file that differs from the reviewed configuration."""
    state, run, _, _ = setup
    compose = Path(json.loads(state.read_text())["path"])
    compose.write_text("services: {}\n")
    assert run().returncode != 0
    assert json.loads(state.read_text()).get("ups", 0) == 0


@pytest.mark.parametrize("host", ["mcp-staging.directedideation.com", "mcp.directedideation.com", None])
def test_preserves_approved_host(setup, host):
    state, run, _, _ = setup
    data = json.loads(state.read_text())
    data["host"] = host
    state.write_text(json.dumps(data))
    assert run().returncode == 0
    assert json.loads(state.read_text())["host"] == (host or "mcp-staging.directedideation.com")


def test_recreated_host_mismatch_fails(setup):
    state, run, _, _ = setup
    data = json.loads(state.read_text())
    data["wrong_after_host"] = True
    state.write_text(json.dumps(data))
    result = run()
    assert result.returncode != 0
    assert "Recreated host did not match" in result.stderr


def test_old_container_hash_drift_fails(setup):
    state, run, _, _ = setup
    data = json.loads(state.read_text())
    data.update(host=None, drift=True)
    state.write_text(json.dumps(data))
    assert run().returncode != 0
    assert json.loads(state.read_text()).get("ups", 0) == 0
