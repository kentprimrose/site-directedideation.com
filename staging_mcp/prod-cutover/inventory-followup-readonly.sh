#!/usr/bin/env bash
# Supplemental read-only inventory. Review this script and its output before sharing.
# Does not run rollback, reload nginx, recreate containers, or change configuration.
set -u
export LC_ALL=C PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [[ $(id -u) != 0 ]]; then echo 'Run with sudo bash.' >&2; exit 1; fi
section() { printf '\n== %s ==\n' "$1"; }
section 'Original Compose location and ancestry'
for p in /home /home/kent /home/kent/di-pilot-build.eR6dNHdr /home/kent/di-pilot-build.eR6dNHdr/compose.yaml; do
  if [[ -e $p || -L $p ]]; then stat -c '%a %U:%G %F %n' -- "$p" || true; else echo "missing: $p"; fi
done
p=/home/kent/di-pilot-build.eR6dNHdr/compose.yaml
if [[ -f $p && ! -L $p ]]; then
  sha256sum -- "$p"
  # Do not display file contents: Compose can contain literal credentials.
  python3 - "$p" <<'PY'
import pathlib, sys
try:
    text = pathlib.Path(sys.argv[1]).read_text()
    for key in ('STAGING_MCP_HOST', 'WORKOS_STAGING_ISSUER', 'WORKOS_STAGING_ALLOWED_SUBJECTS'):
        print(key + ' referenced in file:', 'yes' if key in text else 'no')
except (OSError, UnicodeError):
    print('Unable to inspect Compose file')
PY
else echo 'Compose contents not inspected'; fi
section 'Running image source evidence'
# docker exec starts a short-lived read-only inspection process in the existing
# container. It neither recreates the container nor changes its configuration.
if ! docker --host unix:///var/run/docker.sock exec -i di-staging-staging-mcp-1 python - <<'PY'
import hashlib, pathlib
for name in ('/app/server.py', '/app/healthcheck.py'):
    p = pathlib.Path(name)
    try:
        data = p.read_bytes()
        print(name, 'sha256:', hashlib.sha256(data).hexdigest())
        print(name, 'contains STAGING_MCP_HOST:', b'STAGING_MCP_HOST' in data)
    except OSError:
        print(name, 'unavailable')
print('A string match is evidence only, not proof of behavior; compare hashes to reviewed source.')
PY
then echo 'Container inspection failed'; fi
section 'nginx server blocks (sanitized summary)'
# nginx -T is captured in memory, never printed wholesale. This simple line-based
# parser intentionally reports uncertainty instead of claiming closure is safe.
python3 - <<'PY'
import re, subprocess
p = subprocess.run(['nginx', '-T'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
if p.returncode:
    print('nginx -T failed; inspect privately'); raise SystemExit(0)
source = 'unknown'; active = None; depth = 0
for line in p.stdout.splitlines():
    m = re.match(r'^# configuration file (.+):$', line)
    if m:
        source = m.group(1); continue
    s = line.strip()
    if active is None and re.fullmatch(r'server\s*\{', s):
        active = {'source': source, 'lines': []}; depth = 1; continue
    if active is None: continue
    # Server blocks in this configuration are expected to use normal line-based
    # syntax; braces in quoted strings/comments can make this summary incomplete.
    if depth == 1:
        if re.fullmatch(r'listen\s+[A-Za-z0-9.\[\]:_* -]+;', s): active['lines'].append(s)
        elif re.fullmatch(r'ssl_reject_handshake\s+(?:on|off);', s): active['lines'].append(s)
        elif s.startswith('server_name '):
            names = s[len('server_name '):].rstrip(';').split()
            known = [n for n in names if n in ('mcp.directedideation.com', 'mcp-staging.directedideation.com', '_')]
            active['lines'].append('server_name: ' + (', '.join(known) if known else '(other/redacted)'))
    clean = s.split('#', 1)[0]
    depth += clean.count('{') - clean.count('}')
    if depth <= 0:
        print('source:', active['source'])
        for item in active['lines']: print(' ', item)
        active = None
if active: print('WARNING: incomplete server block; inspect nginx -T privately')
print('Summary is approximate; source mapping and closure safety require manual review.')
PY
section 'Rollback wrapper, helper and timer evidence'
python3 - <<'PY'
import pathlib, re, subprocess
paths = ['/usr/local/sbin/di-shared-test-rollback', '/usr/local/libexec/di-shared-test']
needles = ['/usr/local/libexec/di-shared-test', 'di-shared-test-rollback-once', 'systemd-run', 'ssl_reject_handshake', 'di-staging-public-test.conf', 'di-staging-loopback-check.conf.disabled']
for name in paths:
    try:
        text = pathlib.Path(name).read_text()
        print(name + ':')
        for needle in needles: print('  references ' + needle + ':', 'yes' if needle in text else 'no')
        hashes = sorted(set(re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', text)))
        print('  embedded SHA-256-like values:', ', '.join(hashes) if hashes else 'none found')
    except (OSError, UnicodeError): print(name + ': unavailable')
for unit in ('di-shared-test-rollback-once.timer', 'di-shared-test-rollback-once.service'):
    r = subprocess.run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,SubState,Transient,FragmentPath'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    print(unit + ':')
    print(r.stdout.strip() if r.stdout.strip() else '  no unit properties available')
print('References do not prove wrapper control flow, timer behavior, or safe closure.')
PY
printf '\nReview all output before sharing. No secrets should be printed, but paths and host metadata are included.\n'
