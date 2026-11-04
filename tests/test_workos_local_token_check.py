import http.client
import threading
import time
import urllib.parse

import pytest

from scripts import workos_local_token_check as check


def test_auth_url_has_only_public_values():
    """The authorization URL contains the expected public parameters."""
    url = check.authorization_url(
        "https://auth.example.com",
        "http://127.0.0.1:1234/callback",
        "state",
        "challenge",
    )
    values = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert values == {
        "response_type": ["code"],
        "client_id": [check.CLIENT_ID],
        "redirect_uri": ["http://127.0.0.1:1234/callback"],
        "state": ["state"],
        "code_challenge": ["challenge"],
        "code_challenge_method": ["S256"],
        "resource": [check.RESOURCE],
    }


def test_callback_requires_host_and_state_and_is_silent(capsys):
    """Callbacks require the expected host and state without logging the code."""
    with check.LoopbackServer(("127.0.0.1", 0), check.Callback) as server:
        thread = threading.Thread(
            target=check.receive_code, args=("good", server, time.monotonic() + 5)
        )
        thread.start()

        def request(host, path):
            c = http.client.HTTPConnection("127.0.0.1", server.server_port)
            c.request("GET", path, headers={"Host": host})
            r = c.getresponse()
            result = r.status
            r.read()
            c.close()
            return result

        host = f"127.0.0.1:{server.server_port}"
        assert request("evil.example", "/callback?state=good&code=SECRET") == 400
        assert request(host, "/callback?state=bad&code=SECRET") == 400
        assert request(host, "/callback?state=good&code=SECRET") == 200
        thread.join(3)
        assert not thread.is_alive()
        assert server.code == "SECRET"
    assert "SECRET" not in str(capsys.readouterr())


def test_metadata_fails_closed():
    """Reject missing or invalid required metadata."""
    issuer = "https://auth.example.com"
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/oauth2/authorize",
        "token_endpoint": issuer + "/oauth2/token",
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
    }
    check.check_metadata(issuer, metadata)
    for key in metadata:
        with pytest.raises(ValueError):
            check.check_metadata(issuer, {**metadata, key: None})


def test_local_bearer_goes_only_to_fixed_loopback(monkeypatch):
    """Send the bearer token only to the fixed loopback address."""
    calls = []

    class Connection:
        def __init__(self, host, port, timeout):
            calls.append((host, port))

        def request(self, method, path, body, headers):
            calls.append((method, path, headers))

        def getresponse(self):
            return type("Response", (), {"status": 200})()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(check.http.client, "HTTPConnection", Connection)
    assert check.check_local("SECRET", 8765) == 200
    assert calls[0] == ("127.0.0.1", 8765)
    assert calls[1][2]["Host"] == check.STAGING_HOST
    assert calls[1][2]["Authorization"] == "Bearer SECRET"
    assert calls[-1] == "closed"


def test_failure_does_not_print_exception_or_token(monkeypatch, capsys):
    """Do not expose exception details on failure."""
    monkeypatch.setattr(
        check, "issuer_from_env", lambda: (_ for _ in ()).throw(ValueError("SECRET"))
    )
    assert check.main() == 1
    assert capsys.readouterr().out == "Local token check failed.\n"


def make_token(claims):
    """Create an unsigned test token with a JSON payload."""
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    return "header." + payload.decode() + ".signature"


def test_unverified_diagnostics_compare_claims_without_returning_values():
    """Compare claims without exposing their values."""
    claims = {
        "iss": "https://auth.example.com",
        "aud": ["other", check.RESOURCE],
        "sub": "PRIVATE-SUBJECT",
        "exp": time.time() + 60,
    }
    result = check.token_diagnostics(make_token(claims), claims["iss"], claims["sub"])
    assert all(result.values())
    assert "PRIVATE-SUBJECT" not in str(result)
    claims.update(aud=check.RESOURCE, exp=0)
    result = check.token_diagnostics(make_token(claims), claims["iss"], "")
    assert result["audience_matches"]
    assert not result["subject_configured"]
    assert not result["subject_matches"]
    assert not result["expiration_in_future"]


@pytest.mark.parametrize("token", ["opaque", "a.!.c", "a.e30", "a.W10.c", "a._w.c"])
def test_unverified_diagnostics_handle_opaque_or_malformed_tokens(token):
    """Malformed and opaque tokens produce only false checks."""
    result = check.token_diagnostics(token, "https://auth.example.com", "")
    assert not any(result.values())


def test_unverified_diagnostics_reject_invalid_claim_types():
    """Invalid claim types do not pass comparisons."""
    token = make_token({"aud": [check.RESOURCE, 1], "exp": True, "sub": ["x"]})
    result = check.token_diagnostics(token, "https://auth.example.com", "x")
    assert result["jwt_payload_format"]
    assert not result["issuer_matches"]
    assert not result["audience_matches"]
    assert not result["subject_matches"]
    assert not result["expiration_in_future"]


def test_main_prints_only_boolean_diagnostics(monkeypatch, capsys):
    """Never print the token, issuer, or subject during a 401 check."""
    issuer = "https://private.example.com"
    subject = "PRIVATE-SUBJECT"
    token = make_token({"iss": issuer, "aud": check.RESOURCE, "sub": subject})
    monkeypatch.setenv("WORKOS_LOCAL_EXPECTED_SUBJECT", subject)
    monkeypatch.setattr(check, "issuer_from_env", lambda: issuer)
    monkeypatch.setattr(check, "check_metadata", lambda *args: None)
    monkeypatch.setattr(check, "request_https", lambda *args: {"access_token": token})
    monkeypatch.setattr(check.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(check, "receive_code", lambda *args: "code")
    monkeypatch.setattr(check, "check_local", lambda *args: 401)
    assert check.main() == 1
    output = capsys.readouterr().out
    assert "Unverified token diagnostics (not authorization evidence)" in output
    assert "subject_matches: True" in output
    assert "Local staging HTTP status: 401" in output
    assert all(secret not in output for secret in (token, issuer, subject))


@pytest.mark.parametrize(
    ("id_status", "expected_exit", "message"),
    [
        (401, 0, "ID token rejected: True"),
        (403, 0, "ID token rejected: True"),
        (200, 1, "ID token rejected: False"),
        (500, 1, "inconclusive"),
    ],
)
def test_opt_in_id_token_check(monkeypatch, capsys, id_status, expected_exit, message):
    """Only send the ID token to the local check, and report no credentials."""
    monkeypatch.setenv("WORKOS_LOCAL_CHECK_ID_TOKEN", "1")
    monkeypatch.setattr(check, "issuer_from_env", lambda: "https://auth.example.com")
    monkeypatch.setattr(check, "check_metadata", lambda *args: None)
    https_calls = []

    def https(*args):
        https_calls.append(args)
        return {"access_token": "ACCESS-SECRET", "id_token": "ID-SECRET"}

    monkeypatch.setattr(check, "request_https", https)
    urls = []
    monkeypatch.setattr(check.webbrowser, "open", lambda url: urls.append(url) or True)
    monkeypatch.setattr(check, "receive_code", lambda *args: "code")
    local_calls = []

    def local(token, port):
        local_calls.append((token, port))
        return 200 if token == "ACCESS-SECRET" else id_status

    monkeypatch.setattr(check, "check_local", local)
    assert check.main() == expected_exit
    output = capsys.readouterr()
    assert message in output.out
    assert "ID-SECRET" not in str(output)
    assert "ACCESS-SECRET" not in str(output)
    assert "ID-SECRET" not in str(https_calls) + str(urls)
    assert [call[0] for call in local_calls] == ["ACCESS-SECRET", "ID-SECRET"]
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(urls[0]).query)
    assert params["scope"] == ["openid"]
    assert params["code_challenge_method"] == ["S256"]


def test_opt_in_missing_id_token_is_inconclusive(monkeypatch, capsys):
    """Missing ID tokens fail without sending a second request."""
    monkeypatch.setenv("WORKOS_LOCAL_CHECK_ID_TOKEN", "1")
    monkeypatch.setattr(check, "issuer_from_env", lambda: "https://auth.example.com")
    monkeypatch.setattr(check, "check_metadata", lambda *args: None)
    monkeypatch.setattr(
        check, "request_https", lambda *args: {"access_token": "access"}
    )
    monkeypatch.setattr(check.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(check, "receive_code", lambda *args: "code")
    calls = []
    monkeypatch.setattr(
        check, "check_local", lambda token, port: calls.append(token) or 200
    )
    assert check.main() == 1
    assert "inconclusive" in capsys.readouterr().out
    assert calls == ["access"]


@pytest.mark.parametrize("session", [None, "session-123"])
@pytest.mark.parametrize("sse", [False, True])
def test_guidance_protocol_loopback(monkeypatch, capsys, session, sse):  # noqa: C901
    """Exercise stateful/stateless JSON and SSE without printing response data."""
    import io
    import json

    from site_directedideation_com.mcp import get_interview_guidance

    calls = []

    class Response:
        def __init__(self, message):
            self.message = message
            self.status = 202 if "id" not in message else 200
            self.stream = None

        def getheader(self, name):
            if name.lower() == "mcp-session-id":
                return session if self.message["method"] == "initialize" else None
            return "text/event-stream" if sse else "application/json"

        def read(self, limit):
            method = self.message["method"]
            if method == "notifications/initialized":
                return b""
            result = {
                "initialize": {"protocolVersion": "2025-03-26"},
                "tools/list": {"tools": [{"name": n} for n in check.GUIDANCE_TOOLS]},
                "tools/call": {
                    "content": [
                        {
                            "type": "text",
                            "text": get_interview_guidance(check.GUIDANCE_STAGE),
                        }
                    ],
                    "isError": False,
                },
            }[method]
            data = json.dumps(
                {"jsonrpc": "2.0", "id": self.message["id"], "result": result}
            )
            return ("event: message\ndata: " + data + "\n\n" if sse else data).encode()

        def readline(self, limit):
            if self.stream is None:
                other = (
                    b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
                    b'data: {"jsonrpc":"2.0","id":999,"result":{}}\n\n'
                )
                self.stream = io.BytesIO(other + self.read(limit))
            line = self.stream.readline(limit)
            assert line, "must stop at the matching event without waiting for EOF"
            return line

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 8765)

        def request(self, method, path, body, headers):
            self.message = json.loads(body)
            calls.append((path, headers, self.message))

        def getresponse(self):
            return Response(self.message)

        def close(self):
            pass

    monkeypatch.setattr(check.http.client, "HTTPConnection", Connection)
    assert check.check_guidance("SECRET", 8765)
    assert [c[2]["method"] for c in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    assert all(
        c[0] == "/mcp" and c[1]["Authorization"] == "Bearer SECRET" for c in calls
    )
    assert calls[2][1].get("Mcp-Session-Id") == session
    assert "MCP-Protocol-Version" not in calls[0][1]
    assert all(call[1]["MCP-Protocol-Version"] == "2025-03-26" for call in calls[1:])
    output = capsys.readouterr().out
    assert "SECRET" not in output and "Interview guidance menu" not in output
    assert "Guidance output matches: True" in output


def test_guidance_sse_response_is_bounded():
    """An endless stream of unrelated events is bounded by the response limit."""
    import io

    stream = io.BytesIO(b": heartbeat\n\n" * (check.MAX_RESPONSE // 10 + 1))
    with pytest.raises(ValueError):
        check.read_sse_response(stream, 1)


@pytest.mark.parametrize("data", [b'{"secret":"PRIVATE"', b"\xff"])
def test_guidance_sse_invalid_json_fails_safely(data):
    """Malformed SSE JSON fails without exposing the response in the exception."""
    import io

    with pytest.raises(ValueError, match="^invalid SSE response$") as exc:
        check.read_sse_response(io.BytesIO(b"data: " + data + b"\n\n"), 1)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


def test_guidance_unsupported_protocol(monkeypatch):
    """An unsupported negotiated version stops before subsequent requests."""
    calls = []

    class Response:
        status = 200

        def getheader(self, name):
            return "application/json" if name == "Content-Type" else None

        def read(self, limit):
            return b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2099-01-01"}}'

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            calls.append(args)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(check.http.client, "HTTPConnection", Connection)
    assert not check.check_guidance("SECRET", 8765)
    assert len(calls) == 1


def test_guidance_bad_response_fails_silently(monkeypatch, capsys):
    """Malformed responses fail without leaking their content."""

    class Response:
        status = 200

        def read(self, limit):
            return b'{"secret":"PRIVATE"}'

        def getheader(self, name):
            return "application/json" if name == "Content-Type" else None

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(check.http.client, "HTTPConnection", Connection)
    assert not check.check_guidance("SECRET", 8765)
    assert "PRIVATE" not in capsys.readouterr().out


def test_main_guidance_opt_in_failure(monkeypatch, capsys):
    """An opted-in guidance mismatch fails the overall access-token check."""
    monkeypatch.setenv("WORKOS_LOCAL_CHECK_GUIDANCE", "1")
    monkeypatch.setattr(check, "issuer_from_env", lambda: "https://auth.example.com")
    monkeypatch.setattr(check, "check_metadata", lambda *args: None)
    monkeypatch.setattr(
        check, "request_https", lambda *args: {"access_token": "SECRET"}
    )
    monkeypatch.setattr(check.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(check, "receive_code", lambda *args: "code")
    monkeypatch.setattr(check, "check_local", lambda *args: 200)
    calls = []
    monkeypatch.setattr(
        check, "check_guidance", lambda *args: calls.append(args) or False
    )
    assert check.main() == 1
    assert calls == [("SECRET", 8765)]
    assert "Guidance check succeeded: False" in capsys.readouterr().out
