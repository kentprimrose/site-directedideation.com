"""Local static website server with live reload on file changes."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import mimetypes
import re
import sys
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from site_directedideation_com import dev

DEFAULT_SITE_ROOT = dev.PROJECT_ROOT / "site" / "public"
DEFAULT_POLL_INTERVAL = 0.25
_KEEPALIVE_SECONDS = 15.0
_BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    """Return ``{relative_posix_path: (mtime_ns, size)}`` for regular files."""
    resolved_root = root.resolve()
    snapshot: dict[str, tuple[int, int]] = {}
    if not resolved_root.exists():
        return snapshot
    for path in resolved_root.rglob("*"):
        try:
            if not path.is_file():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(resolved_root):
                continue
            stat = path.stat()
        except OSError:
            continue
        snapshot[path.relative_to(resolved_root).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
        )
    return snapshot


def _inject_reload_script(html: str, boot_id: str) -> str:
    """Inject a lightweight SSE live-reload script before ``</body>``."""
    snippet = (
        "<script data-live-reload>"
        "(function(){"
        f'var boot="{boot_id}";'
        'var es=new EventSource("/__live_reload");'
        'es.addEventListener("boot",function(e){'
        "if(e.data!==boot){window.location.reload();}});"
        'es.addEventListener("reload",function(){window.location.reload();});'
        "})();"
        "</script>"
    )
    match = _BODY_CLOSE_RE.search(html)
    if match is None:
        return html + snippet
    return html[: match.start()] + snippet + html[match.start() :]


def _resolve_site_file(root: Path, request_path: str) -> Path | None:
    """Resolve ``request_path`` safely inside ``root``, or return ``None``."""
    resolved_root = root.resolve()
    relative = request_path.lstrip("/")
    candidate = (resolved_root / relative).resolve()
    if not candidate.is_relative_to(resolved_root):
        return None
    if candidate.is_dir():
        candidate = (candidate / "index.html").resolve()
        if not candidate.is_relative_to(resolved_root):
            return None
    if not candidate.is_file():
        return None
    return candidate


class _ReloadHub:
    """Track site directory changes and broadcast reload events to SSE clients."""

    def __init__(
        self, root: Path, poll_interval: float = DEFAULT_POLL_INTERVAL
    ) -> None:
        self.root = root
        self.poll_interval = poll_interval
        self.boot_id = uuid.uuid4().hex
        self.version = 0
        self._snapshot = _snapshot_tree(root)
        self._subscribers: set[asyncio.Queue[int | None]] = set()
        self._closed = False
        self._stop_event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> asyncio.Event:
        """Bind the hub to the active event loop and return its stop event."""
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        if self._closed:
            self._stop_event.set()
        return self._stop_event

    def subscribe(self) -> asyncio.Queue[int | None]:
        """Register a subscriber queue for reload notifications."""
        queue: asyncio.Queue[int | None] = asyncio.Queue()
        if self._closed:
            queue.put_nowait(None)
        else:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[int | None]) -> None:
        """Remove a subscriber queue."""
        self._subscribers.discard(queue)

    def _broadcast(self, value: int | None) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(value)

    def _close_on_loop(self) -> None:
        self._closed = True
        if self._stop_event is not None:
            self._stop_event.set()
        self._broadcast(None)

    def close(self) -> None:
        """Stop watching and unblock all connected SSE streams."""
        self._closed = True
        loop = self._loop
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._close_on_loop)
                return
        self._close_on_loop()

    async def watch(self) -> None:
        """Poll ``self.root`` until stopped and notify subscribers on any change."""
        stop_event = self.bind_loop()
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval)
                break
            except TimeoutError:
                pass
            current = _snapshot_tree(self.root)
            if current != self._snapshot:
                self._snapshot = current
                self.version += 1
                self._broadcast(self.version)


async def _event_stream(hub: _ReloadHub, request: Request) -> AsyncIterator[str]:
    """Yield SSE boot, reload, and keepalive frames until disconnect or shutdown."""
    queue = hub.subscribe()
    try:
        yield f"event: boot\ndata: {hub.boot_id}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                version = await asyncio.wait_for(
                    queue.get(), timeout=_KEEPALIVE_SECONDS
                )
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if version is None:
                break
            yield f"event: reload\ndata: {version}\n\n"
    finally:
        hub.unsubscribe(queue)


def _serve_file(root: Path, path: str, boot_id: str) -> Response:
    """Serve one file from ``root`` with ``no-store`` and HTML live-reload script."""
    headers = {"Cache-Control": "no-store"}
    target = _resolve_site_file(root, path)
    if target is None:
        return PlainTextResponse("Not found", status_code=404, headers=headers)
    media_type, _ = mimetypes.guess_type(str(target))
    resolved_type = media_type or "application/octet-stream"
    raw = target.read_bytes()
    if resolved_type == "text/html":
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            return Response(content=raw, media_type=resolved_type, headers=headers)
        return HTMLResponse(_inject_reload_script(html, boot_id), headers=headers)
    return Response(content=raw, media_type=resolved_type, headers=headers)


def create_app(
    root: Path = DEFAULT_SITE_ROOT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> tuple[FastAPI, _ReloadHub]:
    """Build the FastAPI live-reloading static site app and its reload hub."""
    hub = _ReloadHub(root=root, poll_interval=poll_interval)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        watcher = asyncio.create_task(hub.watch())
        try:
            yield
        finally:
            hub.close()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/__live_reload")
    async def live_reload(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(hub, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    async def static_asset(path: str) -> Response:
        return _serve_file(root, path, hub.boot_id)

    return app, hub


class _ReloadAwareServer(uvicorn.Server):
    """Close SSE reload streams immediately when a shutdown signal arrives."""

    def __init__(self, config: uvicorn.Config, hub: _ReloadHub) -> None:
        super().__init__(config)
        self._hub = hub

    def handle_exit(self, sig: int, frame: Any) -> None:
        """Notify connected reload clients before delegating exit handling."""
        self._hub.close()
        super().handle_exit(sig, frame)


def main(argv: list[str] | None = None) -> int:
    """Run the local live-reloading website server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=3000, help="bind port")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_SITE_ROOT,
        help="directory to serve (default: site/public)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="file-change poll interval in seconds",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("Error: Port must be between 1 and 65535.", file=sys.stderr)
        return 1
    if not args.root.is_dir():
        print(f"Error: Site root does not exist: {args.root}", file=sys.stderr)
        return 1
    app, hub = create_app(root=args.root, poll_interval=args.poll_interval)
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        timeout_graceful_shutdown=1,
    )
    _ReloadAwareServer(config, hub).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
