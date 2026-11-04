#!/usr/bin/env bash
# Run as root on the pilot host; see DEPLOYMENT.md.
set -euo pipefail
umask 077
# Start a fresh shell without inherited Docker, Compose, shell or proxy settings.
if [[ ${1:-} != --clean ]]; then
  exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
    /bin/bash "$0" --clean "$@"
fi
shift
# Even direct internal-mode invocation cannot select another daemon or plugin path.
while IFS='=' read -r name _; do
  case $name in DOCKER_*|COMPOSE_*) unset "$name" ;; esac
done < <(compgen -e)
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root
export DOCKER_HOST=unix:///var/run/docker.sock
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
fail() { printf 'Error: %s\n' "$1" >&2; exit 1; }
[[ $EUID == 0 ]] || fail 'Run as root with sudo.'
[[ $# == 1 && $1 =~ ^user_[A-Z0-9]{26}$ ]] || fail 'Provide one WorkOS user_ ID followed by 26 uppercase letters or digits.'
user=$1
# All instances serialize through the same host lock, including the idempotent path.
exec 9>/run/lock/di-staging-allowlist.lock
flock -x 9 || fail 'Could not acquire lock.'
compose=/etc/di-staging/compose.yaml
workdir=/etc/di-staging
# No symlinks or untrusted-writable path components; Compose may read .env here.
for path in / /etc "$workdir" "$compose"; do
  [[ ! -L $path && -e $path ]] || fail 'Trusted Compose path missing or symlinked.'
  [[ $(stat -c '%u' "$path") == 0 ]] || fail 'Compose path must be root-owned.'
  mode=$(stat -c '%a' "$path")
  (( (8#$mode & 8#022) == 0 )) || fail 'Compose path must not be writable by group or others.'
done
[[ -f $compose && ! -e $workdir/.env && ! -L $workdir/.env ]] || fail 'Trusted Compose file required and .env forbidden.'
[[ $(sha256sum "$compose" | cut -d' ' -f1) == 8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff ]] || fail 'Compose file is not the reviewed configuration.'
container=di-staging-staging-mcp-1
inspect() { docker inspect --format "$1" "$container" 2>/dev/null; }
label() { inspect "{{ index .Config.Labels \"$1\" }}"; }
[[ $(inspect '{{.State.Running}}') == true ]] || fail 'Expected running staging container not found.'
[[ $(label com.docker.compose.project) == di-staging && $(label com.docker.compose.service) == staging-mcp ]] || fail 'Unexpected Compose project or service.'
recorded=$(label com.docker.compose.project.config_files) || fail 'Cannot read Compose file label.'
[[ $recorded == "$compose" ]] || fail 'Compose file differs from the running container (or multiple files were used).'
workdir=$(label com.docker.compose.project.working_dir) || fail 'Cannot read Compose working directory.'
[[ $workdir == /etc/di-staging && -d $workdir ]] || fail 'Invalid Compose working directory.'
hash=$(label com.docker.compose.config-hash) || fail 'Cannot read Compose config hash.'
[[ $hash =~ ^[a-f0-9]{64}$ ]] || fail 'Missing or invalid Compose config hash.'
container_id=$(inspect '{{.Id}}') || fail 'Cannot read container ID.'
image=$(inspect '{{.Config.Image}}') || fail 'Cannot read container image tag.'
image_id=$(inspect '{{.Image}}') || fail 'Cannot read container image ID.'
[[ $container_id =~ ^[a-f0-9]{64}$ && $image == directed-ideation-staging-mcp:local && $image_id =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'Unexpected container or image identity.'
[[ $(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null) == "$image_id" ]] || fail 'Image tag does not match running image.'
# Extract only the relevant entries; never dump the container environment.
mapfile -t issuers < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "WORKOS_STAGING_ISSUER"}}{{println .}}{{end}}{{end}}')
mapfile -t lists < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "WORKOS_STAGING_ALLOWED_SUBJECTS"}}{{println .}}{{end}}{{end}}')
mapfile -t hosts < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "STAGING_MCP_HOST"}}{{println .}}{{end}}{{end}}')
[[ ${#hosts[@]} -le 1 ]] || fail 'Duplicate staging host entries.'
# Older images defaulted to the original hostname when the entry was absent.
host=mcp-staging.directedideation.com
if [[ ${#hosts[@]} == 1 ]]; then host=${hosts[0]#STAGING_MCP_HOST=}; fi
[[ $host == mcp-staging.directedideation.com || $host == mcp.directedideation.com ]] || fail 'Unapproved staging host.'
[[ ${#issuers[@]} == 1 && ${#lists[@]} == 1 ]] || fail 'Missing or duplicate staging environment entries.'
issuer=${issuers[0]#WORKOS_STAGING_ISSUER=}
subjects=${lists[0]#WORKOS_STAGING_ALLOWED_SUBJECTS=}
[[ -n $issuer && $issuer != *$'\n'* ]] || fail 'Invalid issuer.'
[[ $subjects =~ ^user_[A-Za-z0-9]+(,user_[A-Za-z0-9]+)*$ ]] || fail 'Malformed existing allowlist.'
# Run Compose with a clean environment, pinning project, file and working directory.
# Its hash must reproduce the original configuration before any changes are made.
compose_cmd() {
  # Values are exported inside this already-clean shell, never in env's argv.
  export WORKOS_STAGING_ISSUER="$issuer" WORKOS_STAGING_ALLOWED_SUBJECTS="$subjects" STAGING_MCP_HOST="$host"
  docker compose --project-name di-staging --project-directory "$workdir" -f "$compose" "$@" 2>/dev/null
}
actual=$(compose_cmd config --hash staging-mcp) || fail 'Cannot render original Compose configuration.'
[[ $actual == "staging-mcp $hash" ]] || fail 'Compose configuration differs from the running container; no changes made.'
if [[ ,$subjects, == *,"$user",* ]]; then
  printf 'User is already allowlisted; no changes made.\n'
  exit 0
fi
# Detect replacements or retags since inspection before modifying anything.
[[ $(inspect '{{.Id}}') == "$container_id" && $(inspect '{{.Image}}') == "$image_id" && $(inspect '{{.Config.Image}}') == "$image" && $(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null) == "$image_id" ]] || fail 'Container or image changed; no changes made.'
[[ $(compose_cmd config --hash staging-mcp) == "staging-mcp $hash" ]] || fail 'Compose configuration changed; no changes made.'
subjects+=",$user"
# Do not print Compose output: it may contain configuration or credentials.
compose_cmd up -d --no-build --pull never --no-deps staging-mcp >/dev/null || fail 'Compose recreation failed; inspect the service and recover manually.'
[[ $(inspect '{{.State.Running}}') == true ]] || fail 'Recreated container is not running; recover manually.'
[[ $(inspect '{{.Image}}') == "$image_id" && $(inspect '{{.Config.Image}}') == "$image" && $(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null) == "$image_id" ]] || fail 'Recreated image or tag mismatch; recover manually.'
mapfile -t after < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "WORKOS_STAGING_ALLOWED_SUBJECTS"}}{{println .}}{{end}}{{end}}')
mapfile -t after_issuer < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "WORKOS_STAGING_ISSUER"}}{{println .}}{{end}}{{end}}')
mapfile -t after_host < <(inspect '{{range .Config.Env}}{{if eq (index (split . "=") 0) "STAGING_MCP_HOST"}}{{println .}}{{end}}{{end}}')
[[ ${#after_host[@]} == 1 && ${after_host[0]} == "STAGING_MCP_HOST=$host" ]] || fail 'Recreated host did not match; recover manually.'
[[ ${#after[@]} == 1 && ${after[0]} == "WORKOS_STAGING_ALLOWED_SUBJECTS=$subjects" && ${#after_issuer[@]} == 1 && ${after_issuer[0]} == "WORKOS_STAGING_ISSUER=$issuer" ]] || fail 'Recreated environment did not match; recover manually.'
printf 'Allowlist updated.\n'
