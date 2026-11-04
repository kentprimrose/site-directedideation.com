#!/bin/bash
# One-time, operator-driven transition. Read DEPLOYMENT.md first.
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

OLD=814b89c83fcc507d773cb73fee5f77a1a727d45da48b03927cf5959f4d32d3f4
NEW=7f840890562b29787b516fde9c5bf151b34db7d28ece50e8bcd08b9ebb3ac530
SCRIPT=214f63c23fae0f10867bead0aa290ebb59a5c2ce663749860360d1adc3b2ef05
STATE=/var/lib/di-shared-test
CONF=/etc/nginx/conf.d/di-staging-public-test.conf
HELPER=/usr/local/libexec/di-shared-test
TIMER=di-shared-test-rollback-once.timer
SERVICE=di-shared-test-rollback-once.service

fail() { echo "ERROR: $*" >&2; return 1; }
[[ $EUID == 0 ]] || fail 'run as root'
[[ $# == 3 && $3 =~ ^[0-9a-f]{64}$ ]] || fail "usage: $0 STAGED_CONFIG STAGED_DUAL_DIGEST_SCRIPT REVIEWED_INSTALLED_SCRIPT_SHA256"
input_conf=$1 input_helper=$2 old_helper_hash=$3
hash() { sha256sum -- "$1" | cut -d' ' -f1; }
check_hash() { [[ $(hash "$1") == "$2" ]] || fail "digest mismatch: $1"; }
# No writable-by-others or symlinked directory components in privileged paths.
trusted_dir() {
    local p=$1 uid mode
    while :; do
        [[ -d $p && ! -L $p ]] || fail "unsafe directory: $p"
        read -r uid mode < <(stat -c '%u %a' -- "$p")
        [[ $uid == 0 && $((8#$mode & 0022)) == 0 ]] || fail "untrusted directory: $p"
        [[ $p == / ]] && break
        p=${p%/*}; [[ -n $p ]] || p=/
    done
}
regular_root() {
    local uid mode
    [[ -f $1 && ! -L $1 ]] || fail "not a regular non-symlink file: $1"
    read -r uid mode < <(stat -c '%u %a' -- "$1")
    [[ $uid == 0 && $((8#$mode & 0022)) == 0 ]] || fail "untrusted file: $1"
}
for d in "$STATE" /etc/nginx/conf.d /usr/local/libexec; do trusted_dir "$d"; done
regular_root "$STATE/lock"
[[ $(stat -c '%a' "$STATE/lock") == 600 ]] || fail 'lock must have mode 0600'
# Opening the existing lock (not creating/replacing it) matches the rollback helper.
exec 9<>"$STATE/lock"
flock -w 10 -x 9 || fail 'timed out acquiring transition lock'
# The operator must also prevent new rollback invocations and ensure no old helper
# process has already loaded its code before waiting for this lock.
for unit in "$TIMER" "$SERVICE"; do
    state=$(timeout -k 2s 10s systemctl show "$unit" -p ActiveState --value) || fail "cannot inspect $unit"
    [[ $state == inactive ]] || fail "$unit is not inactive (state=$state)"
done
regular_root "$CONF"
regular_root "$HELPER"
regular_root /etc/nginx/conf.d/di-staging-loopback-check.conf.disabled
check_hash "$CONF" "$OLD"
check_hash "$HELPER" "$old_helper_hash"
# Open each untrusted input once, refusing symlinks and special files; cap both
# the reported size and actual bytes read (including concurrent growth).
# The private directory and destination files are not accessible to the operator.
work=$(mktemp -d "$STATE/rate-transition.XXXXXXXX")
python3 - "$input_conf" "$work/new-conf" "$input_helper" "$work/new-helper" <<'PY'
import os
import stat
import sys

limit = 1024 * 1024
for source, destination in zip(sys.argv[1::2], sys.argv[2::2]):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError(f"invalid staged input: {source}")
        with os.fdopen(fd, 'rb', closefd=False) as src, open(destination, 'xb') as dst:
            data = src.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f"staged input too large: {source}")
            dst.write(data)
    finally:
        os.close(fd)
PY
check_hash "$work/new-conf" "$NEW"
check_hash "$work/new-helper" "$SCRIPT"
cp -- "$CONF" "$work/old-conf"
cp -- "$HELPER" "$work/old-helper"
check_hash "$work/old-conf" "$OLD"
check_hash "$work/old-helper" "$old_helper_hash"
echo "Verified inputs and retained backups in $work"

# Atomic replacement uses unique temporary files on the destination filesystem.
install_atomic() {
    local source=$1 target=$2 mode=$3 tmp
    tmp=$(mktemp "${target%/*}/.di-rate.XXXXXXXX") || return
    if ! install -o root -g root -m "$mode" -- "$source" "$tmp" || ! mv -f -- "$tmp" "$target"; then
        rm -f -- "$tmp"
        return 1
    fi
}
changed=0
recover() {
    local rc=$?
    trap - ERR HUP INT TERM
    echo 'ERROR: transition failed; attempting old configuration recovery.' >&2
    if [[ $changed == 1 ]]; then
        if install_atomic "$work/old-conf" "$CONF" 0644 && [[ $(hash "$CONF") == "$OLD" ]] && timeout -k 2s 10s nginx -t && timeout -k 2s 10s systemctl reload nginx.service; then
            echo 'Old configuration restored and nginx reload requested; independently verify.' >&2
        else
            echo 'RECOVERY FAILED: use the independently prepared closure path immediately.' >&2
        fi
    fi
    echo "Dual-digest helper may remain installed. Backups: $work" >&2
    exit "$rc"
}
trap recover ERR
trap 'false' HUP INT TERM
install_atomic "$work/new-helper" "$HELPER" 0755
check_hash "$HELPER" "$SCRIPT"
# Set before rename so even an interrupted install triggers recovery.
changed=1
install_atomic "$work/new-conf" "$CONF" 0644
check_hash "$CONF" "$NEW"
timeout -k 2s 10s nginx -t
timeout -k 2s 10s systemctl reload nginx.service
trap - ERR HUP INT TERM
# Closing the descriptor releases the lock without another external call.
exec 9>&-
echo "Rate transition installed and reload requested. Backups: $work"
echo 'Restore any coordinated timer, verify nginx status and both digests, and test externally including unrelated routes.'
