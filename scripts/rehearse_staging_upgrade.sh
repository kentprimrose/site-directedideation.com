#!/usr/bin/env bash
# Local disposable Podman rehearsal only. Never run on the droplet.
set -euo pipefail
command -v podman >/dev/null
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
project=di-upgrade-rehearsal-$(date +%s)-$$
oldimage=localhost/directed-ideation-staging-check:local
candidate=localhost/di-upgrade-rehearsal-candidate:local
tag=localhost/$project:local
backup=localhost/$project:rollback
export WORKOS_STAGING_ISSUER=https://auth.example.com
export WORKOS_STAGING_ALLOWED_SUBJECTS=user_TEST
export STAGING_MCP_HOST=mcp-staging.directedideation.com
cleanup() {
  podman compose -p "$project" -f "$tmp/old/compose.yaml" down --remove-orphans >/dev/null 2>&1 || true
  podman rmi "$tag" "$backup" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/old" "$tmp/new"
python3 - "$root/staging_mcp/compose.yaml" "$tmp" "$tag" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
tmp, tag = Path(sys.argv[2]), sys.argv[3]
source = source.replace('directed-ideation-staging-mcp:local', tag)
# No port publishing in this disposable rehearsal.
source = source.replace('    ports:\n      - "127.0.0.1:8765:8765"\n', '')
assert '127.0.0.1:8765:8765' not in source
(tmp/'new'/'compose.yaml').write_text(source)
(tmp/'old'/'compose.yaml').write_text(source.replace('      STAGING_MCP_HOST: ${STAGING_MCP_HOST:-mcp-staging.directedideation.com}\n', ''))
PY
oldid=$(podman image inspect --format '{{.Id}}' "$oldimage")
newid=$(podman image inspect --format '{{.Id}}' "$candidate")
[[ $oldid != "$newid" ]]
podman tag "$oldimage" "$backup"
podman tag "$oldimage" "$tag"
[[ $(podman image inspect --format '{{.Id}}' "$backup") == "$oldid" ]]
[[ $(podman image inspect --format '{{.Id}}' "$tag") == "$oldid" ]]
compose() { podman compose -p "$project" --project-directory "$tmp/$1" -f "$tmp/$1/compose.yaml" "${@:2}"; }
container() { podman ps -aq --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.service=staging-mcp'; }
assert_image() { local cid; cid=$(container); [[ -n $cid && $(podman inspect --format '{{.Image}}' "$cid") == "$1" ]]; }
assert_compose() {
  local dir=$1 cid expected actual
  cid=$(container)
  expected=$(compose "$dir" config --hash staging-mcp | awk '$1 == "staging-mcp" {print $2}')
  actual=$(podman inspect --format '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$cid")
  [[ -n $expected && $actual == "$expected" ]] || { echo "Compose hash mismatch for $dir" >&2; return 1; }
  echo "Compose config hash verified: $dir"
}
assert_state() {
  local cid status i
  cid=$(container)
  for ((i=0; i<90; i++)); do
    status=$(podman inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)
    [[ $status == healthy ]] && break
    sleep 1
  done
  [[ $status == healthy ]] || { echo "container failed to become healthy: $status" >&2; return 1; }
  podman inspect "$cid" | python3 -c 'import json,sys; c=json.load(sys.stdin)[0]; e=dict(x.split("=",1) for x in c["Config"]["Env"] if "=" in x); assert e.get("WORKOS_STAGING_ISSUER")=="https://auth.example.com"; assert e.get("WORKOS_STAGING_ALLOWED_SUBJECTS")=="user_TEST"; assert e.get("STAGING_MCP_HOST", "mcp-staging.directedideation.com")=="mcp-staging.directedideation.com"'
  echo 'health and synthetic environment verified'
}
compose old up -d --no-build --pull never --no-deps staging-mcp
assert_image "$oldid"
assert_state
assert_compose old
echo 'old container image verified'
podman tag "$candidate" "$tag"
[[ $(podman image inspect --format '{{.Id}}' "$backup") == "$oldid" ]]
[[ $(podman image inspect --format '{{.Id}}' "$tag") == "$newid" ]]
compose new up -d --no-build --pull never --no-deps --force-recreate staging-mcp
assert_image "$newid"
assert_state
assert_compose new
echo 'candidate container image verified'
# Simulate a post-recreation failure and restore old image and old Compose.
[[ $(podman image inspect --format '{{.Id}}' "$backup") == "$oldid" ]]
podman tag "$backup" "$tag"
[[ $(podman image inspect --format '{{.Id}}' "$tag") == "$oldid" ]]
compose old up -d --no-build --pull never --no-deps --force-recreate staging-mcp
assert_image "$oldid"
assert_state
assert_compose old
echo 'old image and old Compose restored after simulated failure'

# Rehearse the proposed alternative to reopening the writable old path: a
# private, byte-identical snapshot with its own Compose project directory.
# This is a disposable simulation, not a root-trust or live recovery proof.
mkdir -m 700 "$tmp/snapshot"
cp "$tmp/old/compose.yaml" "$tmp/snapshot/compose.yaml"
chmod 600 "$tmp/snapshot/compose.yaml"
cmp -s "$tmp/old/compose.yaml" "$tmp/snapshot/compose.yaml"
# Simulate an untrusted writer changing the original after capture. Recovery
# must not reopen this altered file.
printf '\n# simulated post-capture modification\n' >> "$tmp/old/compose.yaml"
! cmp -s "$tmp/old/compose.yaml" "$tmp/snapshot/compose.yaml"
compose snapshot up -d --no-build --pull never --no-deps --force-recreate staging-mcp
assert_image "$oldid"
assert_state
assert_compose snapshot
cid=$(container)
[[ $(podman inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$cid") == "$tmp/snapshot/compose.yaml" ]]
[[ $(podman inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$cid") == "$tmp/snapshot" ]]
echo 'private snapshot recovery verified; Compose source and working-directory labels differ from original'
