#!/bin/bash
# Certbot deploy hook scoped to ONE lineage. Install root:root 0755 under
# /etc/letsencrypt/renewal-hooks/deploy/ only after review. Certbot exports
# RENEWED_LINEAGE; any other lineage (e.g. unrelated sites) is ignored.
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
LINEAGE=/etc/letsencrypt/live/@HOST@
LOCK=/var/lib/di-shared-test/lock
[[ ${RENEWED_LINEAGE:-} == "$LINEAGE" ]] || exit 0
# Serialise with the cutover/rollback helpers. Open the existing lock; never
# create it, and never call a lock-taking helper while holding it.
[[ -f $LOCK && ! -L $LOCK ]] || { echo "deploy hook: transition lock missing" >&2; exit 1; }
exec 9<>"$LOCK"
flock -w 60 -x 9 || { echo "deploy hook: lock timeout; reload not performed" >&2; exit 1; }
timeout -k 2s 20s nginx -t
timeout -k 2s 20s systemctl reload nginx.service
