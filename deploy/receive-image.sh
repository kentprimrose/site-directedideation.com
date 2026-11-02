#!/bin/sh
# Installed by the operator alongside compose.yaml; stdin is a docker image archive.
set -eu
umask 077
cd /opt/directed-ideation
sha=${1:-}
case "$sha" in *[!0-9a-f]*|'') echo 'Invalid revision' >&2; exit 1;; esac
[ "${#sha}" -eq 40 ] || { echo 'Invalid revision length' >&2; exit 1; }
image="directed-ideation-mcp:$sha"
# Serialize CI and manual invocations without touching other Docker workloads.
exec 9>state/deploy.lock
flock -x 9
docker load
# Refuse to deploy if the archive did not provide the expected tag.
docker image inspect "$image" >/dev/null
MCP_IMAGE="$image" docker compose -p directed-ideation -f compose.yaml up -d --no-build --pull never --wait --wait-timeout 120
# A repeated release must not overwrite the rollback target with itself.
# Markers are atomic individually; the lock serializes cooperating operators.
if [ -f state/current-image ] && [ "$(cat state/current-image)" != "$image" ]; then
    cp state/current-image state/previous-image.tmp
    mv state/previous-image.tmp state/previous-image
fi
printf '%s\n' "$image" > state/current-image.tmp
mv state/current-image.tmp state/current-image
