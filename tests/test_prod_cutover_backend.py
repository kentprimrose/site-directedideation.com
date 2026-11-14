"""Offline tests for backend-transition.sh: stateful Docker mock, real flock contention."""

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from cutover_shims import PY, write_shims

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "staging_mcp/prod-cutover/backend-transition.sh"
)
COMPOSE_BYTES = b"services: {}\n"
COMPOSE_SHA = hashlib.sha256(COMPOSE_BYTES).hexdigest()
OLD = {
    "host": "mcp-staging.directedideation.com",
    "issuer": "https://old-issuer.example.com",
    "subjects": "user_OLD1,user_OLD2",
}
NEW_ISSUER = "https://new-issuer.example.com"
NEW_SUBJECTS = "user_NEW1,user_NEW2"

DOCKER = (
    PY
    + """
import hashlib, json, os, sys
SP = %r
s = json.load(open(SP))
def save(): json.dump(s, open(SP, 'w'))
def H(h, i, u): return hashlib.sha256(('|'.join((h, i, u))).encode()).hexdigest()
a = sys.argv[1:]
assert a[:2] == ['--host', 'unix:///var/run/docker.sock'], a
a = a[2:]
assert 'DOCKER_CONTEXT' not in os.environ and 'COMPOSE_FILE' not in os.environ
if a[0] == 'image':
    print(s['tag_id']); sys.exit(0)
if a[0] == 'compose':
    s.setdefault('argv', []).append(a); save()
    env = (os.environ['STAGING_MCP_HOST'], os.environ['WORKOS_STAGING_ISSUER'], os.environ['WORKOS_STAGING_ALLOWED_SUBJECTS'])
    if 'config' in a:
        print('staging-mcp ' + H(*env)); sys.exit(0)
    assert '--no-build' in a and 'never' in a and '--no-deps' in a and a[-1] == 'staging-mcp'
    if s.get('fail_up'): sys.exit(1)
    s['ups'] = s.get('ups', 0) + 1
    s['id'] = format(s['ups'] + 100, 'x').rjust(64, 'd')
    s['running'] = True
    s['env'] = {'host': 'wrong.example' if s.get('wrong_env') else env[0], 'issuer': env[1], 'subjects': env[2]}
    s['hash'] = H(*env)
    s['health'] = 'starting' if s.get('unhealthy') else 'healthy'
    save(); sys.exit(0)
assert a[0] == 'inspect'
if s.get('absent'): sys.exit(1)
t = a[2]
if t == '{{.Id}}': print(s['id'])
elif t == '{{.Image}}': print(s['image_id'])
elif t == '{{.Config.Image}}': print(s['tag'])
elif '.State.Running' in t: print('true' if s['running'] else 'false')
elif 'Health.Status' in t: print(s['health'])
elif 'project.config_files' in t: print(s['config_files'])
elif 'project.working_dir' in t: print(s['workdir'])
elif 'config-hash' in t: print(s['hash'])
elif 'compose.project' in t: print('di-staging')
elif 'compose.service' in t: print('staging-mcp')
else:
    for key, field in (('STAGING_MCP_HOST', 'host'), ('WORKOS_STAGING_ISSUER', 'issuer'), ('WORKOS_STAGING_ALLOWED_SUBJECTS', 'subjects')):
        if '"%%s"' %% key in t and s['env'].get(field) is not None:
            print(key + '=' + s['env'][field])
            if s.get('dup_host') and key == 'STAGING_MCP_HOST': print(key + '=' + s['env'][field])
"""
)


def H(h, i, u):
    return hashlib.sha256("|".join((h, i, u)).encode()).hexdigest()


@pytest.fixture
def env(tmp_path):
    bin_ = tmp_path / "bin"
    work = tmp_path / "etc-di-staging"
    work.mkdir(mode=0o755)
    compose = work / "compose.yaml"
    compose.write_bytes(COMPOSE_BYTES)
    compose.chmod(0o644)
    state_dir = tmp_path / "cutover-state"
    lock = tmp_path / "allowlist.lock"
    sp = tmp_path / "docker-state.json"
    image_id = "sha256:" + "a" * 64
    sp.write_text(
        json.dumps(
            {
                "id": "c" * 64,
                "image_id": image_id,
                "tag": "directed-ideation-staging-mcp:local",
                "tag_id": image_id,
                "running": True,
                "health": "healthy",
                "config_files": str(compose),
                "workdir": str(work),
                "env": dict(OLD),
                "hash": H(OLD["host"], OLD["issuer"], OLD["subjects"]),
            }
        )
    )
    write_shims(bin_, {"docker": DOCKER % str(sp)})
    text = SCRIPT.read_text()
    reps = [
        (
            "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
            f"PATH={bin_}:/usr/sbin:/usr/bin:/sbin:/bin",
            2,
        ),
        ('/bin/bash "$0"', f'{shutil.which("bash")} "$0"', 1),
        ("[[ $EUID == 0 ]] || fail 'Run as root.'", ":", 1),
        ("STATE=/var/lib/di-staging-cutover", f"STATE={state_dir}", 1),
        ("LOCK=/run/lock/di-staging-allowlist.lock", f"LOCK={lock}", 1),
        ("workdir=/etc/di-staging\n", f"workdir={work}\n", 1),
        ("compose=/etc/di-staging/compose.yaml", f"compose={compose}", 1),
        ("for path in / /etc ", "for path in / ", 1),
        ("flock -w 10", "flock -w 1", 1),
        ("HEALTH_TIMEOUT=120", "HEALTH_TIMEOUT=0", 1),
    ]
    for old, new, n in reps:
        assert text.count(old) == n, old
        text = text.replace(old, new)
    script = tmp_path / "bt.sh"
    script.write_text(text)
    script.chmod(0o755)
    e = dict(os.environ, DOCKER_CONTEXT="hostile", COMPOSE_FILE="hostile")

    def run(*args):
        return subprocess.run(
            [shutil.which("bash"), str(script), *args],
            env=e,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def st():
        return json.loads(sp.read_text())

    def patch(**kw):
        d = st()
        d.update(kw)
        sp.write_text(json.dumps(d))

    def newenv(body=None, mode=0o600):
        p = tmp_path / "new.env"
        p.write_text(
            body
            if body is not None
            else (
                f"STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER={NEW_ISSUER}\n"
                f"WORKOS_STAGING_ALLOWED_SUBJECTS={NEW_SUBJECTS}\n"
            )
        )
        p.chmod(mode)
        return str(p)

    class Ctx:
        pass

    c = Ctx()
    c.run, c.st, c.patch, c.newenv = run, st, patch, newenv
    c.state_dir, c.lock, c.compose, c.tmp = state_dir, lock, compose, tmp_path
    c.record = lambda name="r1": run("record", name, COMPOSE_SHA)
    return c


def test_record_then_apply_success(env):
    r = env.record()
    assert r.returncode == 0, r.stderr
    rec = env.state_dir / "r1"
    assert oct(rec.stat().st_mode & 0o777) == "0o600"
    assert oct(env.state_dir.stat().st_mode & 0o777) == "0o700"
    assert "OLD_ISSUER=" + OLD["issuer"] in rec.read_text()
    assert OLD["issuer"] not in r.stdout + r.stderr
    before = env.st()
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode == 0, r.stderr
    after = env.st()
    assert after["id"] != before["id"] and after["image_id"] == before["image_id"]
    assert after["env"] == {
        "host": "mcp.directedideation.com",
        "issuer": NEW_ISSUER,
        "subjects": NEW_SUBJECTS,
    }
    assert NEW_ISSUER not in r.stdout + r.stderr + json.dumps(
        after["argv"]
    )  # never in argv/output
    assert after["ups"] == 1


def test_record_rejects_wrong_compose_digest_and_overwrite(env):
    assert env.run("record", "r1", "0" * 64).returncode != 0
    assert env.record().returncode == 0
    r = env.record()
    assert r.returncode != 0 and "never overwrite" in r.stderr


def test_record_rejects_duplicate_host_entries_and_wrong_image(env):
    env.patch(dup_host=True)
    assert env.record().returncode != 0
    env.patch(dup_host=False, tag_id="sha256:" + "b" * 64)
    assert env.record().returncode != 0


@pytest.mark.parametrize(
    "drift",
    [
        {"tag_id": "sha256:" + "b" * 64},  # image retagged
        {"id": "e" * 64},  # container replaced
        {
            "env": {
                "host": OLD["host"],
                "issuer": OLD["issuer"],
                "subjects": "user_OLD1",
            }
        },  # allowlist edited
        {"hash": "f" * 64},  # compose hash label changed
        {"running": False},
    ],
)
def test_apply_refuses_drift_without_recreating(env, drift):
    assert env.record().returncode == 0
    env.patch(**drift)
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode != 0 and "drifted" in r.stderr
    assert env.st().get("ups", 0) == 0


def test_apply_refuses_changed_compose_file(env):
    assert env.record().returncode == 0
    env.compose.write_bytes(COMPOSE_BYTES + b"# changed\n")
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode != 0 and env.st().get("ups", 0) == 0


@pytest.mark.parametrize(
    "body,mode",
    [
        (
            "STAGING_MCP_HOST=mcp-staging.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N\n",
            0o600,
        ),
        (
            f"STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER={OLD['issuer']}\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N\n",
            0o600,
        ),
        (
            "STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N\nEXTRA=1\n",
            0o600,
        ),
        (
            "STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com\n",
            0o600,
        ),
        (
            "STAGING_MCP_HOST=mcp.directedideation.com\nSTAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N\n",
            0o600,
        ),
        (
            "STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N,$(id)\n",
            0o600,
        ),
        (
            "STAGING_MCP_HOST=mcp.directedideation.com\nWORKOS_STAGING_ISSUER=https://n.example.com/\nWORKOS_STAGING_ALLOWED_SUBJECTS=user_N\n",
            0o600,
        ),
        (None, 0o644),
    ],
)
def test_apply_rejects_bad_new_env(env, body, mode):
    assert env.record().returncode == 0
    r = env.run("apply", "r1", env.newenv(body, mode))
    assert r.returncode != 0 and env.st().get("ups", 0) == 0


def test_apply_rejects_symlinked_env_file(env):
    assert env.record().returncode == 0
    link = env.tmp / "link.env"
    link.symlink_to(env.newenv())
    assert env.run("apply", "r1", str(link)).returncode != 0
    assert env.st().get("ups", 0) == 0


def test_lock_held_elsewhere_blocks_every_mode(env):
    assert env.record().returncode == 0
    holder = open(env.lock, "w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        t = time.monotonic()
        for args in (
            ("record", "r2", COMPOSE_SHA),
            ("apply", "r1", env.newenv()),
            ("restore", "r1"),
        ):
            r = env.run(*args)
            assert r.returncode != 0 and "allowlist lock" in r.stderr
        assert time.monotonic() - t < 25
        assert env.st().get("ups", 0) == 0 and not (env.state_dir / "r2").exists()
    finally:
        holder.close()
    assert env.run("apply", "r1", env.newenv()).returncode == 0  # released lock works


def test_lock_is_held_during_recreation(env):
    """A competing locker must fail while `up` runs (checked from inside the mock)."""
    assert env.record().returncode == 0
    probe = env.tmp / "bin" / "docker"
    text = probe.read_text().replace(
        "    s['ups'] = s.get('ups', 0) + 1\n",
        "    import fcntl\n    f = open(%r, 'w')\n    try:\n        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); s['lock_free_during_up'] = True\n"
        "    except BlockingIOError: s['lock_free_during_up'] = False\n    s['ups'] = s.get('ups', 0) + 1\n"
        % str(env.lock),
    )
    probe.write_text(text)
    assert env.run("apply", "r1", env.newenv()).returncode == 0
    assert env.st()["lock_free_during_up"] is False


def test_apply_failure_modes_report_and_leave_state_for_restore(env):
    assert env.record().returncode == 0
    env.patch(fail_up=True)
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode != 0 and "state unknown" in r.stderr
    env.patch(fail_up=False, unhealthy=True)
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode != 0 and "not healthy" in r.stderr
    # Drifted now (apply happened), so a second apply must refuse rather than stack.
    env.patch(unhealthy=False)
    assert env.run("apply", "r1", env.newenv()).returncode != 0


def test_apply_detects_wrong_env_after_recreate(env):
    assert env.record().returncode == 0
    env.patch(wrong_env=True)
    r = env.run("apply", "r1", env.newenv())
    assert r.returncode != 0 and "mismatch" in r.stderr


def test_restore_returns_to_recorded_config_hash(env):
    assert env.record().returncode == 0
    assert env.run("apply", "r1", env.newenv()).returncode == 0
    r = env.run("restore", "r1")
    assert r.returncode == 0, r.stderr
    s = env.st()
    assert s["env"] == OLD and s["hash"] == H(
        OLD["host"], OLD["issuer"], OLD["subjects"]
    )
    assert s["image_id"] == "sha256:" + "a" * 64


def test_restore_works_after_failed_apply_or_missing_container(env):
    assert env.record().returncode == 0
    env.patch(unhealthy=True)
    assert env.run("apply", "r1", env.newenv()).returncode != 0
    env.patch(unhealthy=False)
    assert env.run("restore", "r1").returncode == 0
    assert env.st()["env"] == OLD


def test_restore_refuses_retagged_image(env):
    """Retagging is not rollback: a moved tag blocks automatic restoration."""
    assert env.record().returncode == 0
    assert env.run("apply", "r1", env.newenv()).returncode == 0
    env.patch(tag_id="sha256:" + "b" * 64)
    r = env.run("restore", "r1")
    assert r.returncode != 0 and "recorded image ID" in r.stderr
    assert env.st()["env"]["issuer"] == NEW_ISSUER


def test_restore_fails_if_hash_not_reproduced(env):
    assert env.record().returncode == 0
    d = env.st()
    rec = env.state_dir / "r1"
    rec.write_text(
        rec.read_text().replace("CONFIG_HASH=" + d["hash"], "CONFIG_HASH=" + "9" * 64)
    )
    r = env.run("restore", "r1")
    assert r.returncode != 0 and "hash differs" in r.stderr


def test_tampered_record_is_rejected(env):
    assert env.record().returncode == 0
    rec = env.state_dir / "r1"
    rec.chmod(0o644)
    assert env.run("restore", "r1").returncode != 0
    rec.chmod(0o600)
    rec.write_text(rec.read_text() + "OLD_HOST=mcp.directedideation.com\n")
    assert env.run("restore", "r1").returncode != 0


def test_static_properties():
    import re

    text = re.sub(r"(?m)^\s*#.*$", "", SCRIPT.read_text())
    assert "di-shared-test" not in text  # never calls the other lock's helper
    assert "-v " not in text and "set -x" not in text
    assert text.count("--no-build --pull never --no-deps") == 1
    addu = (SCRIPT.parent.parent / "add-allowed-user.sh").read_text()
    # later allowlist additions read host/issuer from the container, so they persist
    assert (
        "mcp.directedideation.com" in addu and "inspect '{{range .Config.Env}}" in addu
    )
