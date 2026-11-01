"""Bound request bodies before the MCP transport parses them."""

from starlette.responses import PlainTextResponse

MAX_REQUEST_BODY_BYTES = 64 * 1024


class RequestBodyLimit:
    """Buffer at most the limit, then replay the body to the downstream app."""

    def __init__(self, app):
        """Wrap the downstream ASGI application."""
        self.app = app

    async def __call__(self, scope, receive, send):  # noqa: C901
        """Reject invalid lengths and oversized streams before dispatch."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        lengths = [
            value
            for name, value in scope["headers"]
            if name.lower() == b"content-length"
        ]
        if lengths:
            value = lengths[0]
            if len(lengths) != 1 or not value or not value.isdigit():
                await PlainTextResponse("Invalid request", status_code=400)(
                    scope, receive, send
                )
                return
            # Compare decimal strings to avoid converting arbitrarily long integers.
            normalized = value.lstrip(b"0") or b"0"
            limit = str(MAX_REQUEST_BODY_BYTES).encode("ascii")
            if len(normalized) > len(limit) or (
                len(normalized) == len(limit) and normalized > limit
            ):
                await PlainTextResponse("Request body too large", status_code=413)(
                    scope, receive, send
                )
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(chunk) > MAX_REQUEST_BODY_BYTES - len(body):
                await PlainTextResponse("Request body too large", status_code=413)(
                    scope, receive, send
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        async def replay():
            nonlocal body
            if body is not None:
                data = bytes(body)
                body = None
                return {"type": "http.request", "body": data, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
