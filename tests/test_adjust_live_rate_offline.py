"""Offline transition tests: paths and privileged operations are sandboxed."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "staging_mcp/shared-nginx-test/adjust-live-rate.sh"
)


@pytest.fixture
def sandbox(tmp_path):
    """Prepare a sandboxed transition script and command mocks."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "lock").write_text("")
    conf, helper = tmp_path / "conf", tmp_path / "helper"
    conf.write_text("old config")
    helper.write_text("old helper")
    staged_conf, staged_helper = tmp_path / "staged-conf", tmp_path / "staged-helper"
    staged_conf.write_text("new config")
    staged_helper.write_text("new helper")

    def digest(data):
        return hashlib.sha256(data.encode()).hexdigest()

    text = SCRIPT.read_text()
    for old, new in [
        (
            "814b89c83fcc507d773cb73fee5f77a1a727d45da48b03927cf5959f4d32d3f4",
            digest("old config"),
        ),
        (
            "7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530",
            digest("new config"),
        ),
        (
            "214f63c23fae0f10867bead0aa290ebb59a5c2ce663749860360d1adc3b2ef05",
            digest("new helper"),
        ),
        ("STATE=/var/lib/di-shared-test", f"STATE={state}"),
        ("CONF=/etc/nginx/conf.d/di-staging-public-test.conf", f"CONF={conf}"),
        ("HELPER=/usr/local/libexec/di-shared-test", f"HELPER={helper}"),
        ("[[ $EUID == 0 ]] || fail 'run as root'", ":"),
    ]:
        text = text.replace(old, new)
    # Host ownership and GNU stat/install semantics are not portable. The tests
    # exercise transition logic and staging, not privileged-directory checks.
    start = text.index('for d in "$STATE"')
    end = text.index("# Opening the existing lock", start)
    text = text[:start] + text[end:]
    text = text.replace(
        'regular_root "$CONF"\nregular_root "$HELPER"\n'
        "regular_root /etc/nginx/conf.d/di-staging-loopback-check.conf.disabled",
        ":",
    )
    start = text.index("install_atomic() {")
    end = text.index("\nchanged=0", start)
    text = text[:start] + 'install_atomic() { cp -- "$1" "$2"; }\n' + text[end:]
    mockbin = tmp_path / "bin"
    mockbin.mkdir()
    text = text.replace(
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        f"PATH={mockbin}:/usr/sbin:/usr/bin:/sbin:/bin",
    )
    script = tmp_path / "run.sh"
    script.write_text(text)
    mocks = {
        "flock": "#!/bin/bash\n[[ ${LOCK_FAIL:-0} != 1 ]]\n",
        "timeout": '#!/bin/bash\nshift 3\nexec "$@"\n',
        "systemctl": (
            "#!/bin/bash\nif [[ $1 == show ]]; then echo inactive; "
            'else echo reload >> "$LOG"; fi\n'
        ),
        "nginx": (
            '#!/bin/bash\necho test >> "$LOG"\n'
            "if [[ ${NGINX_FAIL_ONCE:-0} == 1 && ! -e $MARKER ]]; "
            'then touch "$MARKER"; exit 1; fi\n'
        ),
    }
    for name, contents in mocks.items():
        path = mockbin / name
        path.write_text(contents)
        path.chmod(0o755)
    env = dict(os.environ, LOG=str(tmp_path / "log"), MARKER=str(tmp_path / "marker"))

    def run(**extra):
        return subprocess.run(
            [
                "bash",
                str(script),
                str(staged_conf),
                str(staged_helper),
                digest("old helper"),
            ],
            env=dict(env, **extra),
            text=True,
            capture_output=True,
            timeout=15,
        )

    return tmp_path, conf, helper, staged_conf, run


def test_success(sandbox):
    """Install staged files and reload after a successful configuration test."""
    root, conf, helper, _, run = sandbox
    result = run()
    assert result.returncode == 0, result.stderr
    assert conf.read_text() == "new config"
    assert helper.read_text() == "new helper"
    assert (root / "log").read_text().splitlines() == ["test", "reload"]


def test_failure_recovers_old_config(sandbox):
    """Restore the old configuration when the new one fails validation."""
    root, conf, helper, _, run = sandbox
    result = run(NGINX_FAIL_ONCE="1")
    assert result.returncode != 0
    assert conf.read_text() == "old config"
    assert helper.read_text() == "new helper"
    assert (root / "log").read_text().splitlines() == ["test", "test", "reload"]
    assert "Old configuration restored" in result.stderr


def test_staged_symlink_rejected(sandbox):
    """Reject a staged symlink without changing installed files."""
    _, conf, helper, staged, run = sandbox
    staged.unlink()
    staged.symlink_to(conf)
    result = run()
    assert result.returncode != 0
    assert conf.read_text() == "old config"
    assert helper.read_text() == "old helper"


def test_lock_timeout_aborts(sandbox):
    """Abort without changing installed files when locking fails."""
    _, conf, helper, _, run = sandbox
    result = run(LOCK_FAIL="1")
    assert result.returncode != 0
    assert "timed out acquiring transition lock" in result.stderr
    assert conf.read_text() == "old config"
    assert helper.read_text() == "old helper"
