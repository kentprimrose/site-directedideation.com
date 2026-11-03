#!/usr/bin/env python3
"""Exercise the example proxy and staging app in a disposable networkless Podman pod.

Requires locally available nginx:stable-alpine and a staging image built from
staging_mcp/Dockerfile (override STAGING_TEST_IMAGE if needed). No ports are
published. The test adapts certificate paths/listen port, adds the documented
optional fail-closed default server, and injects a local verification key. It
does not exercise WorkOS, remote JWKS retrieval, or actual host routing; the
complete target configuration still requires conflict and routing validation.
"""

# Embedded container scripts are kept together for a single-file test harness.
# ruff: noqa: E501
import os
import subprocess
import tempfile
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
host = 'mcp-staging.directedideation.com'
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
check('invalid token', 401, '127.0.0.3', bearer='invalid')
check('valid signature, unapproved subject', 401, '127.0.0.9', bearer=jwt.encode({**claims, 'sub':'user_OTHER'}, key, algorithm='RS256'))
try:
    request('127.0.0.4', authority='evil.example')
    raise AssertionError('wrong Host with staging SNI was not dropped')
except http.client.RemoteDisconnected:
    print('wrong Host with staging SNI: connection dropped (444)', flush=True)
import socket
def check_rejected_handshake(label, sni, source):
    with socket.create_connection(('127.0.0.1', 8443), source_address=(source, 0), timeout=5) as raw:
        try:
            with context.wrap_socket(raw, server_hostname=sni):
                raise AssertionError(label + ': TLS handshake unexpectedly succeeded')
        except ssl.SSLError as exc:
            assert exc.reason == 'TLSV1_UNRECOGNIZED_NAME', (label, exc)
            print(label, 'TLS rejected:', exc.reason, flush=True)
check_rejected_handshake('unknown SNI', 'unknown.example', '127.0.0.5')
check_rejected_handshake('no SNI', None, '127.0.0.10')
check('valid signed token through proxy', 200, '127.0.0.6', bearer=token)
body = check('authenticated ping', 200, '127.0.0.7', bearer=token, payload=call)
assert 'pong' in body, body
statuses = [request('127.0.0.8')[0] for _ in range(12)]
assert 429 in statuses and 401 in statuses, statuses
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
                "/CN=mcp-staging.directedideation.com",
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
            example = (ROOT / "staging_mcp/nginx.conf.example").read_text()
            assert example.count("listen 443 ssl;") == 1
            example = example.replace("listen 443 ssl;", "listen 8443 ssl;")
            example = example.replace(
                "/etc/letsencrypt/live/mcp-staging.directedideation.com/fullchain.pem",
                "/test/tls.crt",
            )
            example = example.replace(
                "/etc/letsencrypt/live/mcp-staging.directedideation.com/privkey.pem",
                "/test/tls.key",
            )
            # Same optional default as DEPLOYMENT.md, adapted to the isolated port.
            default = """server {
    listen 8443 ssl default_server;
    ssl_reject_handshake on;
    return 444;
}
"""
            (path / "nginx.conf").write_text(
                "events {}\nhttp {\n" + default + example + "\n}\n"
            )
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
            try:
                run(
                    "podman",
                    "run",
                    "--pull=never",
                    "--rm",
                    "--pod",
                    POD,
                    "-v",
                    mount,
                    BACKEND,
                    "python",
                    "/test/client.py",
                )
            except subprocess.CalledProcessError:
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
