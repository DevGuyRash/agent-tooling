"""The storefront API's HTTP server. Routes:

    GET /books/{isbn}   the book page (storefront.book_page)
    GET /health         {"ok": true}
"""

import argparse
import asyncio
import json
import logging
import time
from urllib.parse import unquote

from .backends import Backends
from .book_page import BookNotFound, PageUnavailable, book_page

log = logging.getLogger("storefront")

REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
           500: "Internal Server Error", 503: "Service Unavailable"}


async def respond(backends, method, path):
    """(status, JSON body) for one request."""
    if method != "GET":
        return 405, {"error": "method not allowed"}
    path = path.split("?", 1)[0]
    if path == "/health":
        return 200, {"ok": True}
    parts = path.strip("/").split("/")
    if len(parts) != 2 or parts[0] != "books" or not parts[1]:
        return 404, {"error": "not found"}
    isbn = unquote(parts[1])
    try:
        return 200, await book_page(backends, isbn)
    except BookNotFound:
        return 404, {"error": f"no book with ISBN {isbn}"}
    except PageUnavailable as exc:
        return 503, {"error": f"{exc.backend} unavailable"}


async def _handle(backends, reader, writer):
    started = time.monotonic()
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        method, path, _ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
        writer.close()
        return
    try:
        status, body = await respond(backends, method, path)
    except Exception:
        log.exception("%s %s failed", method, path)
        status, body = 500, {"error": "internal error"}
    data = json.dumps(body).encode()
    writer.write((f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\nContent-Type: application/json\r\n"
                  f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode() + data)
    try:
        await writer.drain()
    finally:
        writer.close()
    log.info("%s %s %d %.0f ms", method, path, status, (time.monotonic() - started) * 1000)


async def start(backends, host="127.0.0.1", port=8080):
    """A started asyncio server for the API."""
    return await asyncio.start_server(lambda r, w: _handle(backends, r, w), host, port)


async def serve(backends, host, port):
    server = await start(backends, host, port)
    log.info("listening on %s", ", ".join(str(s.getsockname()) for s in server.sockets))
    async with server:
        await server.serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="storefront")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("serve", help="run the API server")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        asyncio.run(serve(Backends.from_env(), args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0
