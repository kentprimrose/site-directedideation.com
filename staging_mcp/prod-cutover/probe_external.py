#!/usr/bin/env python3
"""Read-only probes that verify closure/openness from outside (or on loopback).

A script exiting 0 elsewhere is not proof of closure: run `closed` or `open`
from a machine that is not the droplet. There are deliberately no default
addresses; --ip must be the droplet IPv4 taken from a fresh inventory.

  closed    no public MCP routing: nothing completes TLS for the host/unknown/no SNI
  open      TLS identity, anonymous 401, wrong Host dropped, SNI rejected, 8001/8765 closed
  loopback  metadata on 127.0.0.1:8765 for the new Host and 400 for the old Host

Sends only unauthenticated requests. Never reads or prints tokens.
"""
import argparse
import http.client
import json
import socket
import ssl
import sys
import time

TIMEOUT = 5
results = []


def record(ok, label, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""), flush=True)


def tls(ip, port, sni, cafile=None, verify=True):
    """Return a wrapped socket or raise. verify=True checks the cert against sni."""
    ctx = ssl.create_default_context(cafile=cafile)
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection((ip, port), timeout=TIMEOUT)
    try:
        return ctx.wrap_socket(raw, server_hostname=sni)
    except BaseException:
        raw.close()
        raise


def handshake_outcome(ip, port, sni, cafile=None, verify=False):
    """'rejected' (refused/reset/alert), 'completed', or 'timeout' (inconclusive)."""
    try:
        sock = tls(ip, port, sni, cafile, verify)
    except (TimeoutError, socket.timeout):
        return "timeout", None
    except ssl.SSLError as exc:
        # A stalled handshake can surface as an SSLError: inconclusive, not closed.
        return ("timeout" if "timed out" in str(exc) else "rejected"), None
    except OSError:
        return "rejected", None
    return "completed", sock


def post_mcp(sock, host_header):
    """Anonymous POST /mcp on an established TLS socket. Returns (status, headers)."""
    conn = http.client.HTTPConnection("x")
    conn.sock = sock
    try:
        conn.request("POST", "/mcp", b"{}", {
            "Host": host_header, "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        r = conn.getresponse()
        r.read(4096)
        return r.status, {k.lower(): v for k, v in r.getheaders()}
    except (http.client.RemoteDisconnected, ConnectionError, ssl.SSLError):
        return None, {}
    finally:
        conn.close()


def looks_like_mcp(status, headers):
    return status == 200 or (status == 401 and "resource_metadata" in headers.get("www-authenticate", ""))


def refused_or_silent(ip, port):
    try:
        socket.create_connection((ip, port), timeout=TIMEOUT).close()
    except OSError:
        return True
    return False


def check_not_served(label, ip, args, sni, host, attempts=3):
    """Not served = rejected, or (shared listener) never an MCP answer in any attempt."""
    seen = []
    for _ in range(attempts):
        outcome, sock = handshake_outcome(ip, args.port, sni, args.cafile, verify=False)
        if outcome == "rejected":
            seen.append("rejected")
            continue
        if outcome == "timeout":
            return record(False, label, "timeout (inconclusive)")
        try:
            if not args.shared_listener:
                return record(False, label, "TLS handshake completed; listener is not failing closed")
            status, headers = post_mcp(sock, host)
        finally:
            sock.close()
        if looks_like_mcp(status, headers):
            return record(False, label, f"MCP answered {status}")
        seen.append(str(status))
    record(True, label, "/".join(sorted(set(seen))))


def mode_closed(args):
    host = args.host
    ip = args.ip
    # Verified handshake for the host must fail; completing it means the host is live.
    outcome, sock = handshake_outcome(ip, args.port, host, args.cafile, verify=True)
    if sock:
        sock.close()
    record(outcome == "rejected", "host SNI: verified TLS does not complete", outcome + (" (inconclusive)" if outcome == "timeout" else ""))
    check_not_served("host SNI: no MCP response", ip, args, host, host)
    check_not_served("unknown SNI", ip, args, "unknown.invalid", host)
    check_not_served("no SNI", ip, args, None, host)
    backends(args)


def backends(args):
    for port in args.backend_ports:
        record(refused_or_silent(args.ip, port), f"port {port} not reachable externally")


def mode_open(args):
    host, ip = args.host, args.ip
    try:
        sock = tls(ip, args.port, host, args.cafile, True)
    except (OSError, ssl.SSLError) as exc:
        return record(False, "verified TLS for host", type(exc).__name__)
    cert = sock.getpeercert()
    left = (ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) / 86400
    record(left > args.min_cert_days, "certificate validity", f"{left:.0f} days left")
    status, headers = post_mcp(sock, host)
    sock.close()
    record(status == 401 and "www-authenticate" in headers, "anonymous POST /mcp is 401 with challenge", str(status))
    # Wrong Host header on the right SNI must be dropped, never answered by the app.
    sock = tls(ip, args.port, host, args.cafile, True)
    status, _ = post_mcp(sock, "evil.example")
    sock.close()
    record(status is None, "wrong Host with correct SNI dropped (444)", str(status))
    check_not_served("unknown SNI", ip, args, "unknown.invalid", host)
    check_not_served("no SNI", ip, args, None, host)
    backends(args)
    if args.burst:
        codes = []
        for _ in range(args.burst):
            try:
                s = tls(ip, args.port, host, args.cafile, True)
                codes.append(post_mcp(s, host)[0])
                s.close()
            except (OSError, ssl.SSLError):
                codes.append("err")
        record(429 in codes, f"rate limit returns 429 within {args.burst} anonymous requests", str(sorted(set(map(str, codes)))))


def mode_loopback(args):
    def get(host_header, path):
        conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=TIMEOUT)
        try:
            conn.request("GET", path, headers={"Host": host_header})
            r = conn.getresponse()
            return r.status, r.read(65536)
        finally:
            conn.close()
    path = "/.well-known/oauth-protected-resource/mcp"
    status, body = get(args.host, path)
    ok = False
    if status == 200:
        try:
            meta = json.loads(body)
            ok = meta.get("resource") == f"https://{args.host}/mcp" and meta.get("authorization_servers") == [args.issuer]
        except ValueError:
            pass
    record(ok, "metadata resource and issuer for new Host", str(status))
    if args.old_host:
        status, _ = get(args.old_host, path)
        record(status == 400, "old Host rejected", str(status))
    conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=TIMEOUT)
    conn.request("POST", "/mcp", b"{}", {"Host": args.host, "Content-Type": "application/json"})
    status = conn.getresponse().status
    record(status == 401, "anonymous POST /mcp is 401", str(status))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["closed", "open", "loopback"])
    ap.add_argument("--host", required=True)
    ap.add_argument("--ip", help="droplet IPv4 (required for closed/open)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--cafile", help="test CA only; omit to use system trust")
    ap.add_argument("--backend-ports", default="8001,8765")
    ap.add_argument("--shared-listener", action="store_true", help="other sites legitimately answer unknown/no SNI")
    ap.add_argument("--min-cert-days", type=float, default=14)
    ap.add_argument("--burst", type=int, default=0, help="opt-in: anonymous requests to trigger 429")
    ap.add_argument("--issuer", help="loopback: expected production issuer origin")
    ap.add_argument("--old-host", help="loopback: previous host, expected to get 400")
    args = ap.parse_args(argv)
    args.backend_ports = [int(p) for p in args.backend_ports.split(",") if p]
    if args.mode == "loopback":
        args.port = args.port or 8765
        if not args.issuer:
            ap.error("loopback needs --issuer")
    else:
        if not args.ip:
            ap.error("--ip is required (no default; use a freshly inventoried address)")
        args.port = args.port or 443
        socket.inet_pton(socket.AF_INET, args.ip)  # IPv4 only
    {"closed": mode_closed, "open": mode_open, "loopback": mode_loopback}[args.mode](args)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
