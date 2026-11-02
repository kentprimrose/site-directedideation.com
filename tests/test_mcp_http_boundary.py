"""Tests for the HTTP body boundary independently of HTTP server framing."""

import asyncio
import logging

import pytest

from site_directedideation_com.mcp.http_boundary import (
    MAX_REQUEST_BODY_BYTES,
    RequestBodyLimit,
)


def exercise(headers, messages, caplog):
    """Run the middleware against a controlled ASGI stream."""
    sent = []
    received = []
    messages = iter(messages)

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        received.append(await receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers}
    with caplog.at_level(logging.DEBUG):
        asyncio.run(RequestBodyLimit(downstream)(scope, receive, send))
    return sent, received


@pytest.mark.parametrize(
    "headers,messages,status",
    [
        ([(b"content-length", b"65537")], [], 413),
        (
            [],
            [
                {"type": "http.request", "body": b"x" * 65536, "more_body": True},
                {"type": "http.request", "body": b"SENTINEL_PROBE", "more_body": False},
            ],
            413,
        ),
        ([(b"content-length", b"SENTINEL_PROBE")], [], 400),
        ([(b"content-length", b"1"), (b"content-length", b"1")], [], 400),
        ([(b"content-length", b"9" * 5000)], [], 413),
    ],
)
def test_rejected_without_payload_leak(headers, messages, status, caplog):
    """Rejected bodies and headers never reach the app or logs."""
    sent, received = exercise(headers, messages, caplog)
    assert sent[0]["status"] == status
    assert not received
    assert b"SENTINEL_PROBE" not in repr(sent).encode()
    assert "SENTINEL_PROBE" not in caplog.text


def test_exact_limit_and_chunk_replay(caplog):
    """A body exactly at the limit is replayed intact."""
    sent, received = exercise(
        [],
        [
            {"type": "http.request", "body": b"x" * 100, "more_body": True},
            {"type": "http.request", "body": b"y" * (MAX_REQUEST_BODY_BYTES - 100)},
        ],
        caplog,
    )
    assert sent[0]["status"] == 204
    assert received == [
        {
            "type": "http.request",
            "body": b"x" * 100 + b"y" * (MAX_REQUEST_BODY_BYTES - 100),
            "more_body": False,
        }
    ]


def test_disconnect_does_not_dispatch(caplog):
    """Disconnected clients do not reach downstream."""
    sent, received = exercise([], [{"type": "http.disconnect"}], caplog)
    assert not sent and not received


def test_http_app_rejects_oversized_and_malformed_json(caplog, monkeypatch, tmp_path):
    """Exercise the configured app with oversized and invalid JSON."""
    monkeypatch.setenv("METRICS_ENV", "development")
    monkeypatch.setenv("METRICS_DB", str(tmp_path / "metrics.sqlite3"))
    from site_directedideation_com.mcp import mcp

    async def check():
        app = mcp.http_app()
        async with app.router.lifespan_context(app):

            async def request(body):
                sent = []
                pending = True

                async def receive():
                    nonlocal pending
                    if pending:
                        pending = False
                        return {"type": "http.request", "body": body}
                    return {"type": "http.disconnect"}

                async def send(message):
                    sent.append(message)

                scope = {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/mcp",
                    "raw_path": b"/mcp",
                    "query_string": b"",
                    "root_path": "",
                    "server": ("localhost", 80),
                    "client": ("127.0.0.1", 1234),
                    "headers": [
                        (b"host", b"localhost"),
                        (b"accept", b"application/json, text/event-stream"),
                        (b"content-type", b"application/json"),
                    ],
                }
                await app(scope, receive, send)
                return sent

            oversized = await request(b"SENTINEL_PROBE" * 6000)
            malformed = await request(b'{"jsonrpc": "2.0", "SENTINEL_PROBE":')
            assert oversized[0]["status"] == 413
            assert malformed[0]["status"] == 400
            assert "SENTINEL_PROBE" not in repr(oversized)
            assert "SENTINEL_PROBE" not in repr(malformed)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(check())
    assert "SENTINEL_PROBE" not in caplog.text
