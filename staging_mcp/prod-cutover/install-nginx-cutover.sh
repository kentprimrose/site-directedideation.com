#!/bin/bash
# One-time, operator-driven nginx cutover for the pilot host. Read the runbook
# (docs/PROD_CUTOVER_RUNBOOK.md) first. Takes /var/lib/di-shared-test/lock itself:
# do NOT run inside a shell that already holds it, and do not call the
# lock-taking di-shared-test-rollback while this runs.
#
# Restoration of the previous public file uses this same script with roles
# swapped (staged = saved old file, OLD = digest of the new live file, NEW =
# digest of the saved file, both helper digests = the installed helper).
#
# Usage: install-nginx-cutover.sh STAGED_CONF STAGED_HELPER \
#          OLD_CONF_SHA256 OLD_HELPER_SHA256 NEW_CONF_SHA256 NEW_HELPER_SHA256
# All four digests come from the reviewed build manifest and the recorded live
# inventory. There are deliberately no defaults.
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

STATE=/var/lib/di-shared-test
CONF=/etc/nginx/conf.d/di-staging-public-test.conf
LOOPBACK_BACKUP=/etc/nginx/conf.d/di-staging-loopback-check.conf.disabled
HELPER=/usr/local/libexec/di-shared-test
TIMER=di-shared-test-rollback-once.timer
SERVICE=di-shared-test-rollback-once.service

fail() { echo "ERROR: $*" >&2; return 1; }
[[ $EUID == 0 ]] || fail 'run as root'
[[ $# == 6 ]] || fail "usage: $0 STAGED_CONF STAGED_HELPER OLD_CONF_SHA OLD_HELPER_SHA NEW_CONF_SHA NEW_HELPER_SHA"
for d in "${@:3}"; do [[ $d =~ ^[0-9a-f]{64}$ ]] || fail 'digest arguments must be 64 lowercase hex characters'; done
input_conf=$1 input_helper=$2 OLD=$3 OLD_HELPER=$4 NEW=$5 NEW_HELPER=$6
[[ $OLD != "$NEW" ]] || fail 'old and new configuration digests must differ'
# OLD_HELPER == NEW_HELPER is allowed: the helper is already current (restoration).
hash() { sha256sum -- "$1" | cut -d' ' -f1; }
check_hash() { [[ $(hash "$1") == "$2" ]] || fail "digest mismatch: $1"; }
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
exec 9<>"$STATE/lock"
flock -w 10 -x 9 || fail 'timed out acquiring transition lock'
# No rollback may start (or have started) while files are swapped.
for unit in "$TIMER" "$SERVICE"; do
    state=$(timeout -k 2s 10s systemctl show "$unit" -p ActiveState --value) || fail "cannot inspect $unit"
    [[ $state == inactive ]] || fail "$unit is not inactive (state=$state)"
done
# Drift check: live state must equal the recorded inventory before any change,
# and the closure path (loopback backup) must still be intact.
regular_root "$CONF"
regular_root "$HELPER"
regular_root "$LOOPBACK_BACKUP"
check_hash "$CONF" "$OLD"
check_hash "$HELPER" "$OLD_HELPER"
[[ ! -e $CONF.disabled ]] || fail 'unexpected disabled public file present'

work=$(mktemp -d "$STATE/cutover-transition.XXXXXXXX")
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
check_hash "$work/new-helper" "$NEW_HELPER"
# The new helper must be able to roll back every configuration that may be live.
for d in "$NEW" "$OLD"; do
    grep -q -- "$d" "$work/new-helper" || fail "new helper does not accept digest $d"
done
cp -- "$CONF" "$work/old-conf"
cp -- "$HELPER" "$work/old-helper"
check_hash "$work/old-conf" "$OLD"
check_hash "$work/old-helper" "$OLD_HELPER"
echo "Verified inputs and retained backups in $work"

install_atomic() {
    local source=$1 target=$2 mode=$3 tmp
    tmp=$(mktemp "${target%/*}/.di-cutover.XXXXXXXX") || return
    if ! install -o root -g root -m "$mode" -- "$source" "$tmp" || ! mv -f -- "$tmp" "$target"; then
        rm -f -- "$tmp"
        return 1
    fi
}
changed=0
recover() {
    local rc=$?
    trap - ERR HUP INT TERM
    echo 'ERROR: cutover failed; attempting old configuration recovery.' >&2
    if [[ $changed == 1 ]]; then
        if install_atomic "$work/old-conf" "$CONF" 0644 && [[ $(hash "$CONF") == "$OLD" ]] && timeout -k 2s 10s nginx -t && timeout -k 2s 10s systemctl reload nginx.service; then
            echo 'Old configuration restored and reload requested; independently verify.' >&2
        else
            echo 'RECOVERY FAILED: use the independently prepared closure path immediately.' >&2
        fi
    fi
    echo "New-digest helper may remain installed (it accepts the old digest). Backups: $work" >&2
    exit "$rc"
}
trap recover ERR
trap 'false' HUP INT TERM
if [[ $OLD_HELPER != "$NEW_HELPER" ]]; then
    install_atomic "$work/new-helper" "$HELPER" 0755
fi
check_hash "$HELPER" "$NEW_HELPER"
changed=1
install_atomic "$work/new-conf" "$CONF" 0644
check_hash "$CONF" "$NEW"
timeout -k 2s 10s nginx -t
timeout -k 2s 10s systemctl reload nginx.service
trap - ERR HUP INT TERM
exec 9>&-
echo "Cutover installed and reload requested. Backups: $work"
echo 'Not verified: reload effect, DNS, certificate or routing. Run probe_external.py and the runbook checks.'
