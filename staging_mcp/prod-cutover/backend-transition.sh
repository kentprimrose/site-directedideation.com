#!/usr/bin/env bash
# Pilot backend cutover/restoration for the di-staging container. Run as root.
# Read docs/PROD_CUTOVER_RUNBOOK.md first. Takes the allowlist lock itself;
# do NOT run inside `flock -x ... /bin/bash` (the lock is not reentrant, so this
# would time out rather than deadlock) and do not run add-allowed-user.sh
# concurrently.
#
#   backend-transition.sh record  NAME EXPECTED_COMPOSE_SHA256
#       Capture the live state (read-only) into $STATE/NAME (root, 0600).
#   backend-transition.sh apply   NAME NEW_ENV_FILE
#       Drift-check against NAME, then recreate only di-staging with new values.
#       NEW_ENV_FILE: root-owned 0600, exactly STAGING_MCP_HOST, WORKOS_STAGING_ISSUER,
#       WORKOS_STAGING_ALLOWED_SUBJECTS as KEY=VALUE lines (parsed, never sourced).
#   backend-transition.sh restore NAME
#       Recreate with the OLD values stored in NAME; success requires the
#       compose config-hash label to equal the recorded one.
# Values are never printed or placed in process arguments.
set -euo pipefail
umask 077
if [[ ${1:-} != --clean ]]; then
  exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
    /bin/bash "$0" --clean "$@"
fi
shift
while IFS='=' read -r name _; do
  case $name in DOCKER_*|COMPOSE_*) unset "$name" ;; esac
done < <(compgen -e)
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root
export DOCKER_HOST=unix:///var/run/docker.sock
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
fail() { printf 'Error: %s\n' "$1" >&2; exit 1; }

STATE=/var/lib/di-staging-cutover
LOCK=/run/lock/di-staging-allowlist.lock
workdir=/etc/di-staging
compose=/etc/di-staging/compose.yaml
container=di-staging-staging-mcp-1
NEW_HOST=mcp.directedideation.com
OLD_DEFAULT_HOST=mcp-staging.directedideation.com
HEALTH_TIMEOUT=120

[[ $EUID == 0 ]] || fail 'Run as root.'
mode_=${1:-}
case $mode_ in
  record)  [[ $# == 3 ]] || fail 'usage: record NAME EXPECTED_COMPOSE_SHA256' ;;
  apply)   [[ $# == 3 ]] || fail 'usage: apply NAME NEW_ENV_FILE' ;;
  restore) [[ $# == 2 ]] || fail 'usage: restore NAME' ;;
  *) fail 'usage: record|apply|restore ...' ;;
esac
name=$2
[[ $name =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || fail 'Invalid record name.'

exec 9>"$LOCK"
flock -w 10 -x 9 || fail 'Could not acquire the allowlist lock (is it already held by this shell?).'

trusted_path() {
  for path in / /etc "$workdir" "$compose"; do
    [[ ! -L $path && -e $path ]] || fail 'Trusted Compose path missing or symlinked.'
    [[ $(stat -c '%u' "$path") == 0 ]] || fail 'Compose path must be root-owned.'
    (( (8#$(stat -c '%a' "$path") & 8#022) == 0 )) || fail 'Compose path must not be group/other writable.'
  done
  [[ -f $compose && ! -e $workdir/.env && ! -L $workdir/.env ]] || fail 'Trusted Compose file required and .env forbidden.'
}
state_dir() {
  if [[ ! -d $STATE ]]; then mkdir -m 700 -- "$STATE" || fail 'Cannot create state directory.'; fi
  [[ -d $STATE && ! -L $STATE && $(stat -c '%u %a' "$STATE") == '0 700' ]] || fail 'State directory must be a root-owned 0700 directory.'
}
inspect() { docker inspect --format "$1" "$container" 2>/dev/null; }
label() { inspect "{{ index .Config.Labels \"$1\" }}"; }
env_of() { # exactly one entry or fail; prints the value
  local out
  # Docker adds a trailing newline even when the template uses println.
  mapfile -t out < <(inspect "{{range .Config.Env}}{{if eq (index (split . \"=\") 0) \"$1\"}}{{println .}}{{end}}{{end}}" | sed '/^$/d')
  [[ ${#out[@]} == 1 ]] || return 1
  printf '%s' "${out[0]#"$1"=}"
}
valid_issuer() { [[ $1 =~ ^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$ ]]; }
valid_subjects() { [[ $1 =~ ^user_[A-Za-z0-9]+(,user_[A-Za-z0-9]+)*$ ]]; }
valid_host() { [[ $1 == "$OLD_DEFAULT_HOST" || $1 == "$NEW_HOST" ]]; }

# Parse KEY=VALUE files without sourcing them. Arguments: file, allowed keys...
# Result in associative array KV. Rejects unknown, duplicate or missing keys.
parse_kv() {
  local file=$1; shift
  declare -gA KV=()
  local line key
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^([A-Z_0-9]+)=([^[:space:]\'\"\\\$\`]*)$ ]] || fail "Malformed line in input file."
    key=${BASH_REMATCH[1]}
    [[ ${KV[$key]+x} == "" ]] || fail 'Duplicate key in input file.'
    KV[$key]=${BASH_REMATCH[2]}
  done < "$file"
  for key in "$@"; do [[ ${KV[$key]+x} == x ]] || fail "Missing key $key."; done
  [[ ${#KV[@]} == $# ]] || fail 'Unexpected key in input file.'
}
safe_input() { # root-owned, 0600, regular, not a symlink, small
  [[ -f $1 && ! -L $1 && $(stat -c '%u %a' "$1") == '0 600' ]] || fail "Input must be a root-owned 0600 regular file: $1"
  (( $(stat -c '%s' "$1") <= 65536 )) || fail 'Input too large.'
}
compose_env() { # $1 host $2 issuer $3 subjects; later calls run in this shell
  export STAGING_MCP_HOST="$1" WORKOS_STAGING_ISSUER="$2" WORKOS_STAGING_ALLOWED_SUBJECTS="$3"
}
compose_cmd() { docker compose --project-name di-staging --project-directory "$workdir" -f "$compose" "$@" 2>/dev/null; }
image_matches() { # tag id
  [[ $(inspect '{{.Config.Image}}') == "$1" && $(inspect '{{.Image}}') == "$2" && $(docker image inspect --format '{{.Id}}' "$1" 2>/dev/null) == "$2" ]]
}
wait_healthy() {
  local waited=0 s
  while (( waited <= HEALTH_TIMEOUT )); do
    s=$(inspect '{{.State.Health.Status}}') || s=missing
    [[ $s == healthy ]] && return 0
    sleep 2; waited=$((waited + 2))
  done
  return 1
}
verify_env() { # host issuer subjects
  [[ $(inspect '{{.State.Running}}') == true ]] || return 1
  [[ $(env_of STAGING_MCP_HOST) == "$1" && $(env_of WORKOS_STAGING_ISSUER) == "$2" && $(env_of WORKOS_STAGING_ALLOWED_SUBJECTS) == "$3" ]]
}
recreate() { # host issuer subjects
  compose_env "$1" "$2" "$3"
  compose_cmd up -d --no-build --pull never --no-deps staging-mcp >/dev/null
}

trusted_path
state_dir
rec=$STATE/$name
sha=$(sha256sum "$compose" | cut -d' ' -f1)

if [[ $mode_ == record ]]; then
  [[ $3 =~ ^[0-9a-f]{64}$ && $sha == "$3" ]] || fail 'Compose file does not match the expected reviewed digest.'
  [[ ! -e $rec ]] || fail 'Record already exists; never overwrite evidence.'
  [[ $(inspect '{{.State.Running}}') == true ]] || fail 'Expected running container not found.'
  [[ $(label com.docker.compose.project) == di-staging && $(label com.docker.compose.service) == staging-mcp ]] || fail 'Unexpected project or service.'
  [[ $(label com.docker.compose.project.config_files) == "$compose" && $(label com.docker.compose.project.working_dir) == "$workdir" ]] || fail 'Container was not created from the trusted compose file.'
  cid=$(inspect '{{.Id}}'); tag=$(inspect '{{.Config.Image}}'); iid=$(inspect '{{.Image}}'); chash=$(label com.docker.compose.config-hash)
  [[ $cid =~ ^[a-f0-9]{64}$ && $iid =~ ^sha256:[a-f0-9]{64}$ && $chash =~ ^[a-f0-9]{64}$ && $tag == directed-ideation-staging-mcp:local ]] || fail 'Unexpected identity.'
  image_matches "$tag" "$iid" || fail 'Image tag does not match the running image.'
  # Older images defaulted to the staging host when the entry was absent;
  # duplicates are an error, not an absence.
  mapfile -t host_entries < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "STAGING_MCP_HOST"}}{{println .}}{{end}}{{end}}' | sed '/^$/d')
  [[ ${#host_entries[@]} -le 1 ]] || fail 'Duplicate host entries.'
  oh=$OLD_DEFAULT_HOST
  if env_of STAGING_MCP_HOST >/dev/null; then oh=$(env_of STAGING_MCP_HOST); fi
  oi=$(env_of WORKOS_STAGING_ISSUER) || fail 'Missing or duplicate issuer.'
  os_=$(env_of WORKOS_STAGING_ALLOWED_SUBJECTS) || fail 'Missing or duplicate allowlist.'
  valid_host "$oh" && valid_issuer "$oi" && valid_subjects "$os_" || fail 'Existing values are malformed.'
  compose_env "$oh" "$oi" "$os_"
  [[ $(compose_cmd config --hash staging-mcp) == "staging-mcp $chash" ]] || fail 'Compose does not reproduce the running configuration hash.'
  tmp=$(mktemp "$STATE/.record.XXXXXXXX")
  printf 'COMPOSE_SHA256=%s\nCONTAINER_ID=%s\nIMAGE_TAG=%s\nIMAGE_ID=%s\nCONFIG_HASH=%s\nOLD_HOST=%s\nOLD_ISSUER=%s\nOLD_SUBJECTS=%s\n' \
    "$sha" "$cid" "$tag" "$iid" "$chash" "$oh" "$oi" "$os_" > "$tmp"
  mv -- "$tmp" "$rec"
  echo "Recorded state in $rec (values not printed)."
  exit 0
fi

# apply / restore both start from the record.
[[ -f $rec && ! -L $rec && $(stat -c '%u %a' "$rec") == '0 600' ]] || fail 'Record missing or untrusted.'
parse_kv "$rec" COMPOSE_SHA256 CONTAINER_ID IMAGE_TAG IMAGE_ID CONFIG_HASH OLD_HOST OLD_ISSUER OLD_SUBJECTS
declare -A R=(); for k in "${!KV[@]}"; do R[$k]=${KV[$k]}; done
[[ ${R[COMPOSE_SHA256]} == "$sha" ]] || fail 'Compose file changed since the record; no changes made.'
valid_host "${R[OLD_HOST]}" && valid_issuer "${R[OLD_ISSUER]}" && valid_subjects "${R[OLD_SUBJECTS]}" || fail 'Record values malformed.'

if [[ $mode_ == apply ]]; then
  safe_input "$3"
  parse_kv "$3" STAGING_MCP_HOST WORKOS_STAGING_ISSUER WORKOS_STAGING_ALLOWED_SUBJECTS
  nh=${KV[STAGING_MCP_HOST]} ni=${KV[WORKOS_STAGING_ISSUER]} ns=${KV[WORKOS_STAGING_ALLOWED_SUBJECTS]}
  [[ $nh == "$NEW_HOST" ]] || fail 'New host must be the approved production host.'
  valid_issuer "$ni" && valid_subjects "$ns" || fail 'New issuer or allowlist malformed.'
  [[ $ni != "${R[OLD_ISSUER]}" ]] || fail 'New issuer equals the recorded (staging) issuer; refusing.'
  drift() { # exact recorded identity AND configuration
    [[ $(inspect '{{.State.Running}}') == true && $(inspect '{{.Id}}') == "${R[CONTAINER_ID]}" ]] || return 1
    image_matches "${R[IMAGE_TAG]}" "${R[IMAGE_ID]}" || return 1
    [[ $(label com.docker.compose.config-hash) == "${R[CONFIG_HASH]}" ]] || return 1
    verify_env "${R[OLD_HOST]}" "${R[OLD_ISSUER]}" "${R[OLD_SUBJECTS]}" || return 1
    compose_env "${R[OLD_HOST]}" "${R[OLD_ISSUER]}" "${R[OLD_SUBJECTS]}"
    [[ $(compose_cmd config --hash staging-mcp) == "staging-mcp ${R[CONFIG_HASH]}" ]]
  }
  drift || fail 'Live state drifted from the record; no changes made.'
  drift || fail 'Live state changed during checks; no changes made.'
  recreate "$nh" "$ni" "$ns" || fail 'Recreation failed; service state unknown. Do not retry blindly: restore or stay closed.'
  image_matches "${R[IMAGE_TAG]}" "${R[IMAGE_ID]}" || fail 'Image changed during recreation; restore or stay closed.'
  verify_env "$nh" "$ni" "$ns" || fail 'Recreated environment mismatch; restore or stay closed.'
  wait_healthy || fail 'Container not healthy before the deadline; restore or stay closed.'
  echo 'Backend recreated with new values (not printed) and healthy. Not verified: loopback metadata, routing, OAuth.'
  exit 0
fi

# restore: old image, host, issuer and allowlist together; proof is the hash label.
tag=${R[IMAGE_TAG]}; iid=${R[IMAGE_ID]}
[[ $(docker image inspect --format '{{.Id}}' "$tag" 2>/dev/null) == "$iid" ]] || fail 'Image tag no longer points at the recorded image ID; refusing to restore automatically.'
recreate "${R[OLD_HOST]}" "${R[OLD_ISSUER]}" "${R[OLD_SUBJECTS]}" || fail 'Recreation failed; stay closed and recover offline.'
image_matches "$tag" "$iid" || fail 'Image mismatch after restore; stay closed.'
verify_env "${R[OLD_HOST]}" "${R[OLD_ISSUER]}" "${R[OLD_SUBJECTS]}" || fail 'Environment mismatch after restore; stay closed.'
[[ $(label com.docker.compose.config-hash) == "${R[CONFIG_HASH]}" ]] || fail 'Restored configuration hash differs from the record; stay closed.'
wait_healthy || fail 'Restored container not healthy; stay closed.'
echo 'Backend restored to recorded image, host, issuer and allowlist and healthy. Restore nginx and routing separately and verify end to end.'
