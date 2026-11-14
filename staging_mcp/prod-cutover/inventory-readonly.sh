#!/usr/bin/env bash
# Read-only, redacted inventory for the directed-ideation pilot migration.
# Run as root on the droplet. Review the output before sharing it.
set -u
export LC_ALL=C
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

if [[ $(id -u) != 0 ]]; then
  echo 'Run as root (for example, sudo bash inventory-readonly.sh).' >&2
  exit 1
fi
section() { printf '\n== %s ==\n' "$1"; }
file_info() {
  local p=$1
  if [[ -e $p || -L $p ]]; then
    stat -c '%a %U:%G %F %n' -- "$p" 2>/dev/null || echo "metadata unavailable: $p"
    if [[ -f $p && ! -L $p ]]; then sha256sum -- "$p" 2>/dev/null || echo "digest unavailable: $p"; fi
  else echo "missing: $p"; fi
}
section 'Host and versions'
hostname
printf 'Docker: '; docker --version 2>/dev/null || echo unavailable
printf 'Compose: '; docker compose version --short 2>/dev/null || echo unavailable
printf 'nginx: '; nginx -v 2>&1 || true
section 'File metadata and digests'
for p in /etc/di-staging /etc/di-staging/compose.yaml /etc/di-staging/.env \
 /etc/nginx/conf.d/di-staging-public-test.conf \
 /etc/nginx/conf.d/di-staging-loopback-check.conf.disabled \
 /usr/local/libexec/di-shared-test /usr/local/sbin/di-shared-test-rollback; do
  # Never hash an environment file: it may contain secrets.
  if [[ $p == /etc/di-staging/.env ]]; then
    if [[ -e $p || -L $p ]]; then echo '.env exists (inspect privately)'; else echo '.env absent'; fi
  else file_info "$p"; fi
done
section 'Service and timer state'
for unit in nginx docker certbot.timer di-shared-test-rollback-once.timer di-shared-test-rollback-once.service; do
  printf '%s: active=' "$unit"; systemctl is-active "$unit" 2>/dev/null || true
  printf '%s: enabled=' "$unit"; systemctl is-enabled "$unit" 2>/dev/null || true
done
section 'Listening sockets (ports 80, 443, 8001, 8765)'
ss -lnt | awk 'NR == 1 || $4 ~ /:(80|443|8001|8765)$/'
section 'Effective nginx listener summary'
# nginx -T may include secrets; parse in memory and output only sanitized listen
# directives and reject-handshake flags. This is not a complete config review.
if command -v python3 >/dev/null; then
python3 - <<'PY'
import re, subprocess
p = subprocess.run(['nginx', '-T'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
print('nginx -T:', 'valid' if p.returncode == 0 else 'failed; inspect privately')
if p.returncode == 0:
    for line in p.stdout.splitlines():
        s = line.strip()
        if re.fullmatch(r'listen\s+[A-Za-z0-9.\[\]:_* -]+;', s) or re.fullmatch(r'ssl_reject_handshake\s+(?:on|off);', s):
            print(s)
print('Listener lines alone do not establish vhost associations or closure safety.')
PY
else echo 'python3 unavailable; inspect effective configuration privately'; fi
section 'Container and image (redacted)'
# Read the inspect JSON in a child process, and never print its environment.
python3 - <<'PY'
import json, subprocess

def run(*args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
p = run('docker', '--host', 'unix:///var/run/docker.sock', 'inspect', 'di-staging-staging-mcp-1')
if p.returncode:
    print('Container di-staging-staging-mcp-1 unavailable; confirm its actual name privately.')
else:
    c = json.loads(p.stdout)[0]
    cfg = c.get('Config') or {}; state = c.get('State') or {}; labels = cfg.get('Labels') or {}
    image = c.get('Image', '')
    print('container ID:', c.get('Id', 'unknown'))
    print('image ID:', image)
    print('image tag:', cfg.get('Image', 'unknown'))
    print('state:', state.get('Status', 'unknown'), 'health:', (state.get('Health') or {}).get('Status', 'not configured'))
    for key in ('com.docker.compose.project', 'com.docker.compose.service', 'com.docker.compose.config-hash', 'com.docker.compose.project.config_files', 'com.docker.compose.project.working_dir'):
        print(key + ':', labels.get(key, 'missing'))
    env = cfg.get('Env') or []
    for key in ('STAGING_MCP_HOST', 'WORKOS_STAGING_ISSUER', 'WORKOS_STAGING_ALLOWED_SUBJECTS'):
        values = [x[len(key)+1:] for x in env if x.startswith(key+'=')]
        print(key + ':', 'present' if len(values) == 1 and values[0] else 'missing/empty/duplicate')
    for tag in (cfg.get('Image', ''), 'directed-ideation-staging-mcp:rollback'):
        if not tag: continue
        r = run('docker', '--host', 'unix:///var/run/docker.sock', 'image', 'inspect', '--format', '{{.Id}}', tag)
        print('tag', tag + ':', 'matches running image' if r.returncode == 0 and r.stdout.strip() == image else 'missing or differs from running image')
    print('Image supports STAGING_MCP_HOST: unknown; verify image provenance or inspect implementation privately.')
PY
section 'Certificate and renewal hook metadata'
for host in mcp-staging.directedideation.com mcp.directedideation.com; do
  cert="/etc/letsencrypt/live/$host/cert.pem"
  if [[ -r $cert ]]; then
    echo "$host:"; openssl x509 -in "$cert" -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null || echo 'certificate parse failed'
  else echo "$host: certificate not readable or absent"; fi
done
if [[ -d /etc/letsencrypt/renewal-hooks/deploy ]]; then
  find /etc/letsencrypt/renewal-hooks/deploy -maxdepth 1 -type f -printf '%m %u:%g %p\n' 2>/dev/null
else echo 'deploy hook directory absent'; fi
printf '\nReview output for sensitive host-specific information before sharing.\n'
