"""Hidden fake backends for async-few-py: catalog, pricing, stock, and reviews as docs/services.md describes
them, plus a control port the driver asks what each request did. Runs as its own process inside the
check's sandbox (its own network namespace), so its timing does not depend on the code under test.

usage: python3 services.py < CONFIG_JSON   (prints the ports as one JSON line, then serves until killed)

CONFIG_JSON: {"behaviors": {backend: {isbn: {"status", "latency", "body"} | {"silent": true}}}, "hold": s}.
A silent backend never answers until the client hangs up, or until `hold` seconds have passed (then 504).
An ISBN with no behavior gets a 404 after 20 ms.

A request is in progress from the moment its headers have arrived until the backend starts writing its
answer, or until the client closes the connection. Control: GET /state/{isbn} returns
{"now": monotonic seconds, "requests": [[backend, start, end or null, outcome], ...]} for that ISBN.
"""
import asyncio
import json
import sys
import time

BACKENDS = ("catalog", "pricing", "stock", "reviews")
PREFIX = {"catalog": "/v1/books/", "pricing": "/v1/prices/", "stock": "/v1/stock/", "reviews": "/v1/reviews/"}
REASONS = {200: "OK", 404: "Not Found", 500: "Internal Server Error", 502: "Bad Gateway",
           503: "Service Unavailable", 504: "Gateway Timeout"}


class Services:
    def __init__(self, cfg):
        self.behaviors = cfg["behaviors"]
        self.hold = cfg["hold"]
        self.log = {}  # isbn -> [entry]

    def isbn_of(self, backend, path):
        path = path.split("?", 1)[0]
        if not path.startswith(PREFIX[backend]):
            return None
        rest = path[len(PREFIX[backend]):]
        if backend == "reviews":
            if not rest.endswith("/summary"):
                return None
            rest = rest[:-len("/summary")]
        return rest or None

    async def wait_or_hangup(self, reader, seconds):
        """Wait `seconds`; False as soon as the client hangs up."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            try:
                chunk = await asyncio.wait_for(reader.read(1024), left)
            except TimeoutError:
                return True
            except (ConnectionError, OSError):
                return False
            if not chunk:
                return False
        return True

    async def serve(self, backend, reader, writer):
        entry = None
        try:
            try:
                head = await reader.readuntil(b"\r\n\r\n")
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
                return
            try:
                method, path, _ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
            except ValueError:
                return
            isbn = self.isbn_of(backend, path) if method == "GET" else None
            entry = {"backend": backend, "start": time.monotonic(), "end": None, "outcome": None}
            self.log.setdefault(isbn or "?", []).append(entry)
            behavior = self.behaviors.get(backend, {}).get(isbn) if isbn else None
            if behavior is None:
                status, body, wait = 404, {"error": "not found"}, 0.02
            elif behavior.get("silent"):
                status, body, wait = 504, {"error": "upstream did not answer"}, self.hold
            else:
                status, body, wait = behavior["status"], behavior.get("body") or {"error": "fault"}, behavior["latency"]
            if not await self.wait_or_hangup(reader, wait):
                entry["end"], entry["outcome"] = time.monotonic(), "hung up"
                return
            entry["end"], entry["outcome"] = time.monotonic(), f"answered {status}"
            data = json.dumps(body).encode()
            writer.write((f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\nContent-Type: application/json\r\n"
                          f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode() + data)
            try:
                await writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            if entry is not None and entry["end"] is None:
                entry["end"], entry["outcome"] = time.monotonic(), "hung up"
            writer.close()

    async def control(self, reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            path = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            isbn = path.removeprefix("/state/")
            entries = self.log.get(isbn, [])
            body = {"now": time.monotonic(),
                    "requests": [[e["backend"], e["start"], e["end"], e["outcome"]] for e in entries]}
            data = json.dumps(body).encode()
            writer.write(f"HTTP/1.1 200 OK\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, IndexError):
            pass
        finally:
            writer.close()


async def main():
    cfg = json.loads(sys.stdin.read())
    services = Services(cfg)
    ports, servers = {}, []
    for backend in BACKENDS:
        server = await asyncio.start_server(lambda r, w, b=backend: services.serve(b, r, w), "127.0.0.1", 0,
                                            backlog=1024)
        servers.append(server)
        ports[backend] = server.sockets[0].getsockname()[1]
    control = await asyncio.start_server(services.control, "127.0.0.1", 0)
    servers.append(control)
    ports["control"] = control.sockets[0].getsockname()[1]
    sys.stdout.write(json.dumps(ports) + "\n")
    sys.stdout.flush()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
