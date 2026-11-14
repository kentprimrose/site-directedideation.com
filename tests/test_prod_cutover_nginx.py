"""Offline tests: cutover package builder, nginx installer, renewal hook, rollback helper."""

import fcntl
import hashlib
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cutover_shims import PY, write_shims

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "staging_mcp/prod-cutover"
INSTALL = PKG / "install-nginx-cutover.sh"
HOOK = PKG / "certbot-deploy-hook.sh"
spec = importlib.util.spec_from_file_location("build_package", PKG / "build_package.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)
HOST = "mcp.directedideation.com"


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- builder

def test_public_conf_follows_design_rules():
    conf = bp.render_public_conf(HOST).decode()
    assert conf.startswith(bp.FAIL_CLOSED_PREFIX)
    assert conf.count("default_server") == 1  # the one fail-closed default
    assert conf.count("server_name") == 1 and f"server_name {HOST};" in conf
    assert "mcp-staging" not in conf and "8001" not in conf and "[::]" not in conf
    assert conf.count("proxy_pass") == 1 and "proxy_pass http://127.0.0.1:8765;" in conf
    assert conf.count("limit_req_zone") == 1 and conf.count("limit_conn_zone") == 1
    assert f"/etc/letsencrypt/live/{HOST}/fullchain.pem" in conf
    assert "real_ip" not in re.sub(r"#.*", "", conf)
    assert conf.count("listen") == 2  # 443 default + 443 server, IPv4 only
    # Identical to the reviewed current config apart from the host name and header comment.
    reviewed = (ROOT / "staging_mcp/shared-nginx-test/tests/reviewed-public-test.conf").read_text()
    assert conf.replace(HOST, bp.OLD_HOST).split("\n", 1)[1] == reviewed.split("\n", 1)[1]


def test_acme_vhost_is_exact_host_only():
    v = bp.render_acme_vhost(HOST).decode()
    assert "mcp-staging" not in v
    assert re.search(r"server_name mcp\.directedideation\.com;", v)
    assert r"^mcp\.directedideation\.com(?::80)?$" in v and "return 444" in v
    assert "location / {\n        return 404;" in v and "acme-challenge" in v
    assert "listen 80;" in v and "443" not in v


def test_builder_rejects_other_hosts_and_existing_output(tmp_path):
    with pytest.raises(ValueError):
        bp.render_public_conf("mcp-staging.directedideation.com")
    with pytest.raises(ValueError):
        bp.render_public_conf("evil.example")
    out = tmp_path / "out"
    out.mkdir()
    assert bp.main(["--out", str(out)]) == 1


def test_builder_is_deterministic_and_manifest_matches(tmp_path):
    a = bp.build(HOST, tmp_path / "a")
    b = bp.build(HOST, tmp_path / "b")
    assert a == b
    for line in (tmp_path / "a/SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert sha((tmp_path / "a" / name).read_bytes()) == digest == a[name]
    assert HOST in (tmp_path / "a/certbot-deploy-hook.sh").read_text()


def load_helper(path):
    loader = importlib.machinery.SourceFileLoader("h" + path.name.replace(".", "_"), str(path))
    s = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(s)
    loader.exec_module(m)
    return m


def test_rendered_helper_accepts_new_current_previous_only(tmp_path):
    out = tmp_path / "o"
    d = bp.build(HOST, out)
    m = load_helper(out / "di-shared-test")
    assert m.DIGEST == d["di-staging-public-test.conf"]
    assert set(m.ACCEPTED) == {m.DIGEST, bp.CURRENT_DIGEST, bp.PREVIOUS_DIGEST} and len(m.ACCEPTED) == 3
    conf_dir, state = tmp_path / "conf", tmp_path / "state"
    conf_dir.mkdir(); state.mkdir()
    loop = conf_dir / m.LOOP
    calls = []
    new = bp.render_public_conf(HOST)
    cur = (ROOT / "staging_mcp/shared-nginx-test/tests/reviewed-public-test.conf").read_bytes()
    prev = cur.replace(b"rate=60r/m", b"rate=10r/m").replace(b"burst=20", b"burst=5")
    assert sha(cur) == bp.CURRENT_DIGEST and sha(prev) == bp.PREVIOUS_DIGEST
    orig = m.read_regular
    with patch.object(m, "CONF", str(conf_dir)), patch.object(m, "STATE", str(state)), \
         patch.object(m, "trusted_dir"), patch.object(m, "command", side_effect=lambda a, t=0: calls.append(a)), \
         patch.object(m, "read_regular", side_effect=lambda p, r=False: orig(p, False)):
        for data in (new, cur, prev):
            (conf_dir / m.PUBLIC).write_bytes(data)
            (conf_dir / (m.LOOP + ".disabled")).write_bytes(b"loop")
            m.rollback()
            assert not (conf_dir / m.PUBLIC).exists() and loop.read_bytes() == b"loop"
            loop.unlink()
        # Closure refuses to destroy anything it does not recognise, including the OLD host's variant.
        (conf_dir / m.PUBLIC).write_bytes(new.replace(HOST.encode(), b"other.example"))
        with pytest.raises(RuntimeError):
            m.rollback()
        assert (conf_dir / m.PUBLIC).exists()


def test_rendered_helper_differs_from_installed_only_in_digest_handling(tmp_path):
    bp.build(HOST, tmp_path / "o")
    old = (ROOT / "staging_mcp/shared-nginx-test/di-shared-test").read_text().splitlines()
    new = (tmp_path / "o/di-shared-test").read_text().splitlines()
    import difflib
    changed = [l for l in difflib.unified_diff(old, new, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert len(changed) == 8, changed
    assert all(any(k in l for k in ("DIGEST", "ACCEPTED")) for l in changed)


# ---------------------------------------------------------------- installer

NGINX = PY + """
import fcntl, hashlib, os, sys
log, lock = os.environ['LOG'], os.environ['LOCKFILE']
def probe():
    f = open(lock, 'w')
    try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); return 'FREE'
    except BlockingIOError: return 'held'
conf, helper = os.environ['CONFFILE'], os.environ['HELPERFILE']
h = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()[:6]
with open(log, 'a') as l:
    l.write('%s lock=%s conf=%s helper=%s\\n' % (os.path.basename(sys.argv[0]) + ' ' + ' '.join(sys.argv[1:]), probe(), h(conf), h(helper)))
marker = os.environ['MARKER'] + os.path.basename(sys.argv[0]) + ' '.join(sys.argv[1:])
mode = os.environ.get('FAIL', '')
target = {'nginx': '-t', 'systemctl': 'reload'}.get(os.path.basename(sys.argv[0]))
if target in sys.argv and os.path.basename(sys.argv[0]) in mode:
    if 'always' in mode or not os.path.exists(marker):
        open(marker, 'w').close(); sys.exit(1)
"""
SYSTEMCTL = NGINX + """
if 'show' in sys.argv:
    print(os.environ.get('ACTIVE_UNIT_STATE', 'inactive') if os.environ.get('ACTIVE_UNIT') in sys.argv else 'inactive')
"""


@pytest.fixture
def box(tmp_path):
    conf_d, state, libexec, stage = (tmp_path / n for n in ("conf.d", "state", "libexec", "stage"))
    for d in (conf_d, state, libexec, stage):
        d.mkdir(mode=0o755)
    state.chmod(0o700)
    (state / "lock").write_text("")
    (state / "lock").chmod(0o600)
    conf, helper = conf_d / "di-staging-public-test.conf", libexec / "di-shared-test"
    conf.write_bytes(b"old conf\n")
    helper.write_bytes(b"old helper\n")
    (conf_d / "di-staging-loopback-check.conf.disabled").write_text("loop")
    for p in (conf, helper):
        p.chmod(0o644)
    old_c, new_c = sha(b"old conf\n"), sha(b"new conf\n")
    old_h = sha(b"old helper\n")
    new_helper_bytes = f"new helper accepts {new_c} {old_c}\n".encode()
    (stage / "conf").write_bytes(b"new conf\n")
    (stage / "helper").write_bytes(new_helper_bytes)
    bin_ = tmp_path / "bin"
    write_shims(bin_, {"nginx": NGINX, "systemctl": SYSTEMCTL})
    text = INSTALL.read_text()
    reps = [
        ("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bin_}:/usr/sbin:/usr/bin:/sbin:/bin", 1),
        ("STATE=/var/lib/di-shared-test", f"STATE={state}", 1),
        ("CONF=/etc/nginx/conf.d/di-staging-public-test.conf", f"CONF={conf}", 1),
        ("LOOPBACK_BACKUP=/etc/nginx/conf.d/di-staging-loopback-check.conf.disabled", f"LOOPBACK_BACKUP={conf_d}/di-staging-loopback-check.conf.disabled", 1),
        ("HELPER=/usr/local/libexec/di-shared-test", f"HELPER={helper}", 1),
        ("[[ $EUID == 0 ]] || fail 'run as root'", ":", 1),
        ('for d in "$STATE" /etc/nginx/conf.d /usr/local/libexec; do', f'for d in "$STATE" {conf_d} {libexec}; do', 1),
        ("flock -w 10", "flock -w 1", 1),
    ]
    for old, new, n in reps:
        assert text.count(old) == n, old
        text = text.replace(old, new)
    script = tmp_path / "install.sh"
    script.write_text(text)
    env = dict(os.environ, LOG=str(tmp_path / "log"), LOCKFILE=str(state / "lock"), CONFFILE=str(conf),
               HELPERFILE=str(helper), MARKER=str(tmp_path / "m-"))

    class B: pass
    b = B()
    b.tmp, b.conf, b.helper, b.state, b.stage, b.conf_d = tmp_path, conf, helper, state, stage, conf_d
    b.digests = [old_c, old_h, new_c, sha(new_helper_bytes)]
    b.log = lambda: [l for l in ((tmp_path / "log").read_text().splitlines() if (tmp_path / "log").exists() else []) if " show " not in l]

    def run(args=None, **extra):
        a = args or [str(stage / "conf"), str(stage / "helper"), *b.digests]
        return subprocess.run([shutil.which("bash"), str(script), *a], env=dict(env, **extra), text=True, capture_output=True, timeout=30)

    b.run = run
    return b


def unchanged(b):
    return b.conf.read_bytes() == b"old conf\n" and b.helper.read_bytes() == b"old helper\n"


def test_install_success_order_and_lock_held(box):
    r = box.run()
    assert r.returncode == 0, r.stderr
    assert box.conf.read_bytes() == b"new conf\n" and box.helper.read_bytes().startswith(b"new helper")
    log = box.log()
    # nginx -t and reload both ran with the lock still held and BOTH files already new.
    assert [l.split(" lock=")[0] for l in log] == ["nginx -t", "systemctl reload nginx.service"]
    assert all("lock=held" in l for l in log)
    assert all(l.split("conf=")[1].split()[0] == sha(b"new conf\n")[:6] for l in log)
    assert all(l.split("helper=")[1] == sha(box.helper.read_bytes())[:6] for l in log)
    backups = list(box.state.glob("cutover-transition.*"))
    assert len(backups) == 1 and (backups[0] / "old-conf").read_bytes() == b"old conf\n"
    assert (backups[0] / "old-helper").read_bytes() == b"old helper\n"
    assert not [p for p in box.conf_d.iterdir() if p.name.startswith(".di-cutover")]
    assert oct(box.conf.stat().st_mode & 0o777) == "0o644"


@pytest.mark.parametrize("breaker", [
    lambda b: b.conf.write_bytes(b"drifted\n"),
    lambda b: b.helper.write_bytes(b"drifted\n"),
    lambda b: (b.conf_d / "di-staging-loopback-check.conf.disabled").unlink(),
    lambda b: (b.conf_d / "di-staging-public-test.conf.disabled").write_text("x"),
    lambda b: (b.stage / "conf").write_bytes(b"tampered\n"),
    lambda b: (b.stage / "helper").write_bytes(b"new helper without digests\n"),
])
def test_refuses_on_drift_or_bad_staging_and_changes_nothing(box, breaker):
    breaker(box)
    drifted = box.conf.read_bytes() != b"old conf\n" or box.helper.read_bytes() != b"old helper\n"
    r = box.run()
    assert r.returncode != 0
    assert not box.log() or all("reload" not in l for l in box.log())
    if not drifted:
        assert unchanged(box)


def test_restoration_is_the_same_path_with_roles_swapped(box):
    assert box.run().returncode == 0
    saved = next(box.state.glob("cutover-transition.*")) / "old-conf"
    old_c, _, new_c, new_h = box.digests
    box.log_file = box.tmp / "log"
    box.log_file.unlink()
    r = box.run([str(saved), str(box.helper), new_c, new_h, old_c, new_h])
    assert r.returncode == 0, r.stderr
    assert box.conf.read_bytes() == b"old conf\n"
    assert box.helper.read_bytes().startswith(b"new helper")  # superset helper kept
    assert [l.split(" lock=")[0] for l in box.log()] == ["nginx -t", "systemctl reload nginx.service"]


def test_restoration_refuses_if_live_file_is_not_the_expected_new_one(box):
    assert box.run().returncode == 0
    saved = next(box.state.glob("cutover-transition.*")) / "old-conf"
    old_c, _, new_c, new_h = box.digests
    box.conf.write_bytes(b"someone edited the live file\n")
    r = box.run([str(saved), str(box.helper), new_c, new_h, old_c, new_h])
    assert r.returncode != 0 and box.conf.read_bytes() == b"someone edited the live file\n"


def test_helper_must_accept_old_and_new_digest(box):
    only_new = f"new helper accepts {box.digests[2]}\n".encode()
    (box.stage / "helper").write_bytes(only_new)
    digests = [*box.digests[:3], sha(only_new)]
    r = box.run([str(box.stage / "conf"), str(box.stage / "helper"), *digests])
    assert r.returncode != 0 and "does not accept digest" in r.stderr and unchanged(box)


def test_staged_symlink_rejected(box):
    (box.stage / "conf").unlink()
    (box.stage / "conf").symlink_to(box.conf)
    assert box.run().returncode != 0 and unchanged(box)


@pytest.mark.parametrize("bad", [["short"], ["x"] * 4, None])
def test_argument_validation(box, bad):
    args = None
    if bad == ["short"]:
        args = [str(box.stage / "conf")]
    elif bad:
        args = [str(box.stage / "conf"), str(box.stage / "helper"), *bad]
    elif bad is None:
        d = list(box.digests)
        d[2] = d[0]  # old == new
        args = [str(box.stage / "conf"), str(box.stage / "helper"), *d]
    assert box.run(args).returncode != 0 and unchanged(box)


@pytest.mark.parametrize("unit", ["di-shared-test-rollback-once.timer", "di-shared-test-rollback-once.service"])
def test_refuses_while_rollback_timer_or_service_active(box, unit):
    r = box.run(ACTIVE_UNIT=unit, ACTIVE_UNIT_STATE="active")
    assert r.returncode != 0 and "not inactive" in r.stderr and unchanged(box)


def test_lock_held_elsewhere_aborts_without_changes(box):
    holder = open(box.state / "lock", "w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        t = time.monotonic()
        r = box.run()
        assert r.returncode != 0 and "timed out acquiring" in r.stderr
        assert time.monotonic() - t < 15 and unchanged(box)
    finally:
        holder.close()


def test_lock_file_must_be_private(box):
    (box.state / "lock").chmod(0o664)
    assert box.run().returncode != 0 and unchanged(box)


def test_failed_validation_restores_old_conf_keeps_superset_helper(box):
    r = box.run(FAIL="nginx")  # first nginx -t fails, recovery's succeeds
    assert r.returncode != 0 and "Old configuration restored" in r.stderr
    assert box.conf.read_bytes() == b"old conf\n" and box.helper.read_bytes().startswith(b"new helper")
    log = [l.split(" lock=")[0] for l in box.log()]
    assert log == ["nginx -t", "nginx -t", "systemctl reload nginx.service"]
    assert not [p for p in box.conf_d.iterdir() if p.name.startswith(".di-cutover")]


def test_reload_failure_restores_old_conf_and_reloads_again(box):
    r = box.run(FAIL="systemctl")
    assert r.returncode != 0 and box.conf.read_bytes() == b"old conf\n"
    assert [l.split(" lock=")[0] for l in box.log()].count("systemctl reload nginx.service") == 2


def test_unrecoverable_failure_points_at_closure_path(box):
    r = box.run(FAIL="nginx always")
    assert r.returncode != 0 and "RECOVERY FAILED" in r.stderr and "closure" in r.stderr


def test_installer_never_calls_lock_taking_helpers():
    text = re.sub(r"(?m)^\s*#.*$", "", INSTALL.read_text())
    assert "sbin/di-shared-test" not in text and '"$HELPER" rollback' not in text and '"$HELPER" activate' not in text
    assert "systemctl stop" not in text and "systemctl disable" not in text  # never silently disables the safety timer


# ---------------------------------------------------------------- deploy hook

def hook_box(tmp_path, lock=True):
    state = tmp_path / "state"
    state.mkdir()
    if lock:
        (state / "lock").write_text("")
    bin_ = tmp_path / "bin"
    write_shims(bin_, {"nginx": NGINX, "systemctl": NGINX})
    text = bp.render_hook(HOST).decode()
    text = text.replace("LOCK=/var/lib/di-shared-test/lock", f"LOCK={state}/lock")
    text = text.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bin_}:/usr/sbin:/usr/bin:/sbin:/bin")
    text = text.replace("flock -w 60", "flock -w 1")
    script = tmp_path / "hook.sh"
    script.write_text(text)
    (tmp_path / "c").write_text("c")
    env = dict(os.environ, LOG=str(tmp_path / "log"), LOCKFILE=str(state / "lock"), CONFFILE=str(tmp_path / "c"),
               HELPERFILE=str(tmp_path / "c"), MARKER=str(tmp_path / "m-"))

    def run(lineage, **extra):
        e = dict(env, **extra)
        if lineage is not None:
            e["RENEWED_LINEAGE"] = lineage
        return subprocess.run([shutil.which("bash"), str(script)], env=e, text=True, capture_output=True, timeout=20)

    return run, tmp_path / "log", state


def test_hook_ignores_other_lineages(tmp_path):
    run, log, _ = hook_box(tmp_path)
    for lineage in ("/etc/letsencrypt/live/other.example", "/etc/letsencrypt/live/mcp-staging.directedideation.com",
                    "/etc/letsencrypt/live/mcp.directedideation.com.evil", None):
        assert run(lineage).returncode == 0
    assert not log.exists()


def test_hook_reloads_new_lineage_under_lock(tmp_path):
    run, log, _ = hook_box(tmp_path)
    assert run("/etc/letsencrypt/live/mcp.directedideation.com").returncode == 0
    lines = log.read_text().splitlines()
    assert [l.split(" lock=")[0] for l in lines] == ["nginx -t", "systemctl reload nginx.service"]
    assert all("lock=held" in l for l in lines)


def test_hook_no_reload_when_config_invalid_or_lock_busy_or_missing(tmp_path):
    run, log, state = hook_box(tmp_path)
    r = run("/etc/letsencrypt/live/mcp.directedideation.com", FAIL="nginx always")
    assert r.returncode != 0 and "reload" not in log.read_text()
    log.unlink()
    holder = open(state / "lock", "w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        r = run("/etc/letsencrypt/live/mcp.directedideation.com")
        assert r.returncode != 0 and "lock timeout" in r.stderr and not log.exists()
    finally:
        holder.close()
    (state / "lock").unlink()
    assert run("/etc/letsencrypt/live/mcp.directedideation.com").returncode != 0
    assert not (state / "lock").exists()  # never creates the lock
