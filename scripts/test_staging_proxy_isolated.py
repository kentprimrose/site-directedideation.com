#!/usr/bin/env python3
"""Exercise the example proxy and staging app in a disposable networkless Podman pod.

Requires locally available nginx:stable-alpine and a staging image built from
staging_mcp/Dockerfile (override STAGING_TEST_IMAGE if needed). No ports are
published. The test adapts certificate paths/listen port, adds the documented
optional fail-closed default server, and injects a local verification key. It
does not exercise WorkOS, remote JWKS retrieval, or actual host routing; the
complete target configuration still requires conflict and routing validation.

Cutover rehearsal (nginx behaviour only; not DNS, renewal or live WorkOS):
  STAGING_TEST_HOST=mcp.directedideation.com \
  STAGING_TEST_CONF=<dir from build_package.py>/di-staging-public-test.conf \
  python scripts/test_staging_proxy_isolated.py
Both are optional; defaults reproduce the original staging-host test. With a
non-default host the test also checks old-audience/wrong-issuer/expired tokens,
a failed validation that must not disturb serving, emergency closure (public
file removed, default listener only) and restoration of the same artifact.
"""

# Embedded container scripts are kept together for a single-file test harness.
# ruff: noqa: E501
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POD = "staging-proxy-test-" + uuid.uuid4().hex[:12]
BACKEND = os.environ.get(
    "STAGING_TEST_IMAGE", "localhost/directed-ideation-staging-check:local"
)
NGINX = os.environ.get(
    "STAGING_TEST_NGINX_IMAGE", "docker.io/library/nginx:stable-alpine"
)


OLD_HOST = "mcp-staging.directedideation.com"
HOST = os.environ.get("STAGING_TEST_HOST", OLD_HOST)
CONF = os.environ.get("STAGING_TEST_CONF")
CUTOVER = HOST != OLD_HOST


def run(*args, **kwargs):
    """Run a command and fail on a nonzero exit status."""
    return subprocess.run(args, check=True, **kwargs)


SERVER = """\
import sys
sys.path.insert(0, '/app')
import server
import uvicorn
async def local_key(self, token):
    return open('/test/public.pem', 'rb').read()
server.StagingVerifier._get_verification_key = local_key
uvicorn.run(server.create_app(), host='127.0.0.1', port=8765, access_log=False, log_level='warning')
"""

CLIENT = """\
import http.client, json, ssl, time
import jwt
import os, sys
host = os.environ['TEST_HOST']
phase = sys.argv[1]
old_host = 'mcp-staging.directedideation.com'
context = ssl._create_unverified_context()
init = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'isolated-test','version':'1'}}}
call = {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'ping','arguments':{}}}
key = open('/test/private.pem').read()
claims = {'iss':'https://auth.example.com','aud':'https://' + host + '/mcp','sub':'user_ABC','exp':int(time.time())+300}
token = jwt.encode(claims, key, algorithm='RS256')
def request(source, authority=host, bearer=None, payload=init, sni=host):
    conn = http.client.HTTPSConnection(sni, 8443, context=context, timeout=5, source_address=(source, 0))
    # Connect locally while retaining the supplied SNI.
    import socket
    conn._create_connection = lambda addr, timeout, source_address: socket.create_connection(('127.0.0.1', 8443), timeout, source_address)
    headers = {'Host':authority, 'Accept':'application/json, text/event-stream', 'Content-Type':'application/json'}
    if bearer is not None: headers['Authorization'] = 'Bearer ' + bearer
    try:
        conn.request('POST', '/mcp', json.dumps(payload), headers)
        r = conn.getresponse()
        return r.status, r.read().decode()
    finally: conn.close()
def check(label, expected, *args, **kwargs):
    status, body = request(*args, **kwargs)
    assert status == expected, (label, status, body[:300])
    print(label, status, flush=True)
    return body
import socket
def check_rejected_handshake(label, sni, source):
    with socket.create_connection(('127.0.0.1', 8443), source_address=(source, 0), timeout=5) as raw:
        try:
            with context.wrap_socket(raw, server_hostname=sni):
                raise AssertionError(label + ': TLS handshake unexpectedly succeeded')
        except ssl.SSLError as exc:
            assert exc.reason == 'TLSV1_UNRECOGNIZED_NAME', (label, exc)
            print(label, 'TLS rejected:', exc.reason, flush=True)
if phase == 'closed':
    # Public file removed: nothing may complete TLS, whatever the SNI.
    check_rejected_handshake('closed: host SNI', host, '127.0.0.20')
    check_rejected_handshake('closed: unknown SNI', 'unknown.example', '127.0.0.21')
    check_rejected_handshake('closed: no SNI', None, '127.0.0.22')
    sys.exit(0)
for i in range(100):
    try:
        status, body = request('127.0.0.2')
        if status in (502, 429):
            time.sleep(.2)
            continue
        assert status == 401, (status, body)
        print('anonymous', status, flush=True)
        break
    except (ConnectionError, OSError): time.sleep(.1)
else: raise RuntimeError('proxy did not become ready')
if phase == 'serving':
    check('valid signed token through proxy', 200, '127.0.0.30', bearer=token)
    sys.exit(0)
check('invalid token', 401, '127.0.0.3', bearer='invalid')
check('valid signature, unapproved subject', 401, '127.0.0.9', bearer=jwt.encode({**claims, 'sub':'user_OTHER'}, key, algorithm='RS256'))
if host != old_host:
    check('old-host audience', 401, '127.0.0.11', bearer=jwt.encode({**claims, 'aud':'https://' + old_host + '/mcp'}, key, algorithm='RS256'))
    check('wrong issuer', 401, '127.0.0.12', bearer=jwt.encode({**claims, 'iss':'https://other-issuer.example.com'}, key, algorithm='RS256'))
    check('expired token', 401, '127.0.0.13', bearer=jwt.encode({**claims, 'exp':int(time.time())-3600}, key, algorithm='RS256'))
    try:
        request('127.0.0.14', authority=old_host, sni=old_host)
        raise AssertionError('old SNI unexpectedly reached the service')
    except ssl.SSLError as exc:
        assert exc.reason == 'TLSV1_UNRECOGNIZED_NAME', exc
        print('old host SNI rejected after flag day', flush=True)
try:
    request('127.0.0.4', authority='evil.example')
    raise AssertionError('wrong Host with staging SNI was not dropped')
except http.client.RemoteDisconnected:
    print('wrong Host with staging SNI: connection dropped (444)', flush=True)
check_rejected_handshake('unknown SNI', 'unknown.example', '127.0.0.5')
check_rejected_handshake('no SNI', None, '127.0.0.10')
check('valid signed token through proxy', 200, '127.0.0.6', bearer=token)
body = check('authenticated ping', 200, '127.0.0.7', bearer=token, payload=call)
assert 'pong' in body, body
statuses = [request('127.0.0.8')[0] for _ in range(12)]
assert statuses == [401] * 12, statuses
statuses += [request('127.0.0.8')[0] for _ in range(35)]
assert 429 in statuses, statuses
print('rate limit burst:', statuses, flush=True)
"""


def main():
    """Create, test, and remove the isolated pod."""
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="staging-proxy-test-") as tmp:
            path = Path(tmp)
            os.chmod(path, 0o755)
            run(
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=" + HOST,
                "-keyout",
                str(path / "tls.key"),
                "-out",
                str(path / "tls.crt"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            run(
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(path / "private.pem"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            run(
                "openssl",
                "pkey",
                "-in",
                str(path / "private.pem"),
                "-pubout",
                "-out",
                str(path / "public.pem"),
                stdout=subprocess.DEVNULL,
            )
            for name in ("tls.key", "private.pem"):
                os.chmod(path / name, 0o644)  # disposable test keys only
            (path / "bootstrap.py").write_text(SERVER)
            (path / "client.py").write_text(CLIENT)
            if CONF:
                # The real cutover artifact: it already carries the fail-closed default.
                example = Path(CONF).read_text()
                assert example.count("listen 0.0.0.0:443 ssl") == 2
                assert example.count("default_server") == 1 and HOST in example
                example = example.replace("listen 0.0.0.0:443 ssl", "listen 0.0.0.0:8443 ssl")
                default = ""
            else:
                example = (ROOT / "staging_mcp/nginx.conf.example").read_text()
                assert example.count("listen 0.0.0.0:443 ssl;") == 1
                example = example.replace("listen 0.0.0.0:443 ssl;", "listen 0.0.0.0:8443 ssl;")
                assert example.count("listen 0.0.0.0:8443 ssl;") == 1
                # Same optional default as DEPLOYMENT.md, adapted to the isolated port.
                default = """server {
    listen 0.0.0.0:8443 ssl default_server;
    ssl_reject_handshake on;
    return 444;
}
"""
            for name in ("fullchain.pem", "privkey.pem"):
                lineage = f"/etc/letsencrypt/live/{OLD_HOST if not CONF else HOST}/{name}"
                assert lineage in example, lineage
                example = example.replace(lineage, "/test/tls.crt" if name == "fullchain.pem" else "/test/tls.key")
            open_conf = "events {}\nhttp {\n" + default + example + "\n}\n"
            # Public file removed: only the fail-closed listener remains.
            closed_conf = (
                "events {}\nhttp {\nserver {\n    listen 0.0.0.0:8443 ssl default_server;\n"
                "    ssl_certificate /test/tls.crt;\n    ssl_certificate_key /test/tls.key;\n"
                "    ssl_reject_handshake on;\n    return 444;\n}\n}\n"
            )
            (path / "nginx.conf").write_text(open_conf)
            run(
                "podman",
                "pod",
                "create",
                "--name",
                POD,
                "--network",
                "none",
                stdout=subprocess.DEVNULL,
            )
            created = True
            mount = f"{tmp}:/test:ro"
            run(
                "podman",
                "run",
                "--pull=never",
                "-d",
                "--pod",
                POD,
                "--name",
                POD + "-app",
                "-v",
                mount,
                "-v",
                f"{ROOT / 'staging_mcp/server.py'}:/app/server.py:ro",
                "-e",
                "STAGING_MCP_HOST=" + HOST,
                "-e",
                "WORKOS_STAGING_ISSUER=https://auth.example.com",
                "-e",
                "WORKOS_STAGING_ALLOWED_SUBJECTS=user_ABC",
                BACKEND,
                "python",
                "/test/bootstrap.py",
                stdout=subprocess.DEVNULL,
            )
            run(
                "podman",
                "run",
                "--pull=never",
                "-d",
                "--pod",
                POD,
                "--name",
                POD + "-nginx",
                "-v",
                mount,
                NGINX,
                "nginx",
                "-c",
                "/test/nginx.conf",
                "-g",
                "daemon off;",
                stdout=subprocess.DEVNULL,
            )
            def client(phase):
                run(
                    "podman", "run", "--pull=never", "--rm", "--pod", POD, "-v", mount,
                    "-e", "TEST_HOST=" + HOST, BACKEND, "python", "/test/client.py", phase,
                )

            def nginx(*args):
                return subprocess.run(
                    ["podman", "exec", POD + "-nginx", "nginx", "-c", "/test/nginx.conf", *args],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ).returncode

            try:
                client("open")
                if CUTOVER:
                    # Failed validation: nginx -t must reject it and serving must be undisturbed.
                    (path / "nginx.conf").write_text(open_conf.replace("server_tokens off;", "server_tokens off;\n    bogus_directive on;"))
                    assert nginx("-t") != 0, "broken configuration passed validation"
                    client("serving")
                    print("failed validation: rejected, still serving", flush=True)
                    # Emergency closure: public file gone, default listener only.
                    (path / "nginx.conf").write_text(closed_conf)
                    assert nginx("-t") == 0 and nginx("-s", "reload") == 0
                    time.sleep(1)
                    client("closed")
                    # Service restoration: the same artifact comes back and serves.
                    (path / "nginx.conf").write_text(open_conf)
                    assert nginx("-t") == 0 and nginx("-s", "reload") == 0
                    time.sleep(1)
                    client("serving")
                    print("closure and restoration verified (nginx behaviour only)", flush=True)
            except (subprocess.CalledProcessError, AssertionError):
                for suffix in ("-app", "-nginx"):
                    subprocess.run(["podman", "logs", POD + suffix], check=False)
                raise
    finally:
        if created:
            subprocess.run(
                ["podman", "pod", "rm", "-f", POD],
                check=True,
                stdout=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
