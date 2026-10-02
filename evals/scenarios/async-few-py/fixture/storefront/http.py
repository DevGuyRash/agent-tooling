"""A small HTTP/1.1 client for the internal backends: one GET per connection, JSON in the body.

The backends answer with `Connection: close`, so a response ends where the connection does.
"""

import asyncio
import contextlib
import json
from urllib.parse import urlsplit


class BackendError(Exception):
    """A backend answered with an error status, did not answer in time, or could not be reached.

    `backend` names the backend ("catalog", "pricing", ...); `status` is the HTTP status code when the
    backend answered, None when it did not answer in time or could not be reached.
    """

    def __init__(self, backend, message, status=None):
        super().__init__(f"{backend}: {message}")
        self.backend = backend
        self.status = status


def _parse(raw):
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        raise ValueError("no end of headers")
    status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise ValueError(f"bad status line {status_line!r}")
    return int(parts[1]), body


async def get_json(backend, url, time_limit):
    """GET url and return its JSON body; BackendError for an error status, for no complete answer within
    time_limit seconds (connecting included), or when the backend cannot be reached."""
    parts = urlsplit(url)
    host, port = parts.hostname or "127.0.0.1", parts.port or 80
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    request = (f"GET {target} HTTP/1.1\r\nHost: {host}:{port}\r\nAccept: application/json\r\n"
               f"Connection: close\r\n\r\n").encode()
    try:
        async with asyncio.timeout(time_limit):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(request)
                await writer.drain()
                raw = await reader.read()
            finally:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
    except TimeoutError:
        raise BackendError(backend, f"no answer within {time_limit:g} s") from None
    except OSError as exc:
        raise BackendError(backend, f"cannot reach {host}:{port}: {exc.strerror or exc}") from None
    try:
        status, body = _parse(raw)
    except ValueError as exc:
        raise BackendError(backend, f"bad response: {exc}") from None
    if status != 200:
        raise BackendError(backend, f"HTTP {status}", status=status)
    try:
        return json.loads(body)
    except ValueError:
        raise BackendError(backend, "response is not JSON", status=status) from None
