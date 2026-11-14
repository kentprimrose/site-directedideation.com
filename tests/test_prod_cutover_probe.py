"""probe_external.py against local TLS servers emulating open, closed and leaky listeners."""

import http.server
import importlib.util
import json
import socket
import ssl
import subprocess
import threading
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "staging_mcp/prod-cutover/probe_external.py"
spec = importlib.util.spec_from_file_location("probe_external", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
HOST = "mcp.example.test"
ISSUER = "https://issuer.example.test"


@pytest.fixture(scope="module")
def cert(tmp_path_factory):
    d = tmp_path_factory.mktemp("cert")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30", "-subj", f"/CN={HOST}",
         "-addext", f"subjectAltName=DNS:{HOST}", "-keyout", str(d / "k"), "-out", str(d / "c")],
        check=True, capture_output=True)
    return d / "c", d / "k"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """kind: open (strict SNI), closed (rejects all), shared (answers any SNI with 404),
    leaky (answers no-SNI like the MCP service)."""

    def __init__(self, kind, cert):
        self.kind = kind
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*map(str, cert))

        def sni(sock, name, _ctx):
            if kind == "closed" or (kind == "open" and name != HOST) or (kind == "leaky" and name not in (HOST, None)):
                return ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

        ctx.sni_callback = sni
        self.ctx = ctx
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(32)
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.2)
        self.stop = False
        self.t = threading.Thread(target=self.loop, daemon=True)
        self.t.start()

    def loop(self):
        while not self.stop:
            try:
                raw, _ = self.sock.accept()
            except OSError:
                continue
            threading.Thread(target=self.handle, args=(raw,), daemon=True).start()

    def handle(self, raw):
        try:
            raw.settimeout(3)
            s = self.ctx.wrap_socket(raw, server_side=True)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    return
                data += chunk
            head, _, body = data.partition(b"\r\n\r\n")
            head = head.decode().lower()
            want = int(([x.split(":", 1)[1] for x in head.split("\r\n") if x.startswith("content-length:")] or ["0"])[0])
            while len(body) < want:  # drain like nginx, else close() resets and eats the reply
                body += s.recv(4096)
            host = [x.split(":", 1)[1].strip() for x in head.split("\r\n") if x.startswith("host:")][0]
            if host != HOST and self.kind != "shared":
                s.close()  # nginx 444
                return
            if self.kind == "shared" or host != HOST:
                resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            else:
                resp = (b"HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Bearer resource_metadata=\"x\"\r\n"
                        b"Content-Length: 0\r\nConnection: close\r\n\r\n")
            s.sendall(resp)
            s.close()
        except (OSError, ssl.SSLError):
            pass

    def close(self):
        self.stop = True
        self.sock.close()


@pytest.fixture
def serve(cert):
    made = []

    def make(kind):
        s = Server(kind, cert)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def run(capsys, mode, server, cert, *extra, backend="9"):
    # Port 9 (discard) is not listening locally: stands in for 8001/8765 unreachable.
    code = probe.main([mode, "--host", HOST, "--ip", "127.0.0.1", "--port", str(server.port),
                       "--cafile", str(cert[0]), "--backend-ports", backend, *extra])
    probe.results.clear()
    return code, capsys.readouterr().out


def test_open_passes_on_correct_listener(serve, cert, capsys):
    code, out = run(capsys, "open", serve("open"), cert)
    assert code == 0 and "FAIL" not in out, out
    assert "wrong Host with correct SNI dropped" in out


def test_open_fails_when_cert_expiry_near(serve, cert, capsys):
    code, out = run(capsys, "open", serve("open"), cert, "--min-cert-days", "999")
    assert code == 1 and "FAIL certificate validity" in out


def test_open_fails_when_backend_port_reachable(serve, cert, capsys):
    exposed = serve("shared")
    code, out = run(capsys, "open", serve("open"), cert, backend=str(exposed.port))
    assert code == 1 and "FAIL port" in out


def test_open_fails_when_noSNI_reaches_mcp(serve, cert, capsys):
    code, out = run(capsys, "open", serve("leaky"), cert, "--shared-listener")
    assert code == 1 and "FAIL no SNI" in out, out


def test_closed_passes_when_everything_rejected(serve, cert, capsys):
    code, out = run(capsys, "closed", serve("closed"), cert)
    assert code == 0 and "FAIL" not in out, out


def test_closed_passes_when_listener_refuses(cert, capsys):
    class Dead:
        port = free_port()

    code, out = run(capsys, "closed", Dead, cert)
    assert code == 0, out


def test_closed_fails_when_service_still_open(serve, cert, capsys):
    code, out = run(capsys, "closed", serve("open"), cert)
    assert code == 1 and "FAIL host SNI: verified TLS" in out


def test_closed_fails_when_another_site_is_implicit_default(serve, cert, capsys):
    # Strict mode: any completed handshake for unknown/no SNI means it is not failing closed.
    code, out = run(capsys, "closed", serve("shared"), cert)
    assert code == 1 and "FAIL unknown SNI" in out and "not failing closed" in out


def test_closed_shared_listener_tolerates_unrelated_site_but_not_mcp(serve, cert, capsys):
    code, out = run(capsys, "closed", serve("shared"), cert, "--shared-listener")
    # The host SNI still completes a verified handshake against the shared site: not closed.
    assert code == 1 and "FAIL host SNI: verified TLS" in out
    assert "PASS unknown SNI" in out


def test_closed_timeout_is_inconclusive_not_pass(cert, capsys):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)  # accepts TCP but never speaks TLS
    probe.TIMEOUT = 0.5
    try:
        class Hung:
            port = s.getsockname()[1]

        code, out = run(capsys, "closed", Hung, cert)
    finally:
        probe.TIMEOUT = 5
        s.close()
    assert code == 1 and "inconclusive" in out


def test_requires_explicit_ip_and_ipv4(capsys):
    with pytest.raises(SystemExit):
        probe.main(["open", "--host", HOST])
    with pytest.raises(SystemExit):
        probe.main(["closed", "--host", HOST])
    with pytest.raises(OSError):
        probe.main(["closed", "--host", HOST, "--ip", "2001:db8::1"])


class Meta(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers["Host"] != HOST:
            self.send_response(400); self.end_headers(); return
        body = json.dumps({"resource": f"https://{HOST}/mcp", "authorization_servers": [ISSUER]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        self.send_response(401); self.send_header("Content-Length", "0"); self.end_headers()


def test_loopback_metadata_and_old_host(capsys):
    srv = http.server.HTTPServer(("127.0.0.1", 0), Meta)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        argv = ["loopback", "--host", HOST, "--issuer", ISSUER, "--old-host", "old.example.test", "--port", str(srv.server_port)]
        assert probe.main(argv) == 0
        probe.results.clear()
        assert probe.main(argv[:3] + ["--issuer", "https://wrong.example.test"] + argv[5:]) == 1
    finally:
        probe.results.clear()
        srv.shutdown()
