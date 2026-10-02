"""Stand-ins for the four backends, served from the test's own event loop.

    async with FakeBackends(books={...}, prices={...}, stock={...}, reviews={...}) as fake:
        page = await book_page(fake.backends, "9780141439518")

Each mapping goes from ISBN to the JSON body the backend returns; an ISBN missing from a mapping gets a
404. `faults` maps (backend, isbn) to an HTTP status to answer with instead, or to "silent" for a backend
that never answers; `delays` maps (backend, isbn) to seconds to wait before answering.
"""

import asyncio
import json

from storefront.backends import Backends

ROUTES = {"catalog": "/v1/books/", "pricing": "/v1/prices/", "stock": "/v1/stock/", "reviews": "/v1/reviews/"}


class FakeBackends:
    def __init__(self, books=None, prices=None, stock=None, reviews=None, faults=None, delays=None):
        self.data = {"catalog": books or {}, "pricing": prices or {}, "stock": stock or {}, "reviews": reviews or {}}
        self.faults = faults or {}
        self.delays = delays or {}
        self.requests = []          # (backend, path) in arrival order
        self._servers = []
        self.backends = None

    async def __aenter__(self):
        urls = {}
        for name in ROUTES:
            server = await asyncio.start_server(lambda r, w, name=name: self._serve(name, r, w), "127.0.0.1", 0)
            self._servers.append(server)
            urls[name] = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        self.backends = Backends(**urls)
        return self

    async def __aexit__(self, *exc):
        for server in self._servers:
            server.close()
            await server.wait_closed()

    def _isbn(self, name, path):
        rest = path[len(ROUTES[name]):] if path.startswith(ROUTES[name]) else ""
        return rest.removesuffix("/summary") if name == "reviews" else rest

    async def _serve(self, name, reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            path = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            self.requests.append((name, path))
            isbn = self._isbn(name, path)
            fault = self.faults.get((name, isbn))
            if fault == "silent":
                await reader.read()  # until the client hangs up
                return
            await asyncio.sleep(self.delays.get((name, isbn), 0))
            if fault is not None:
                status, body = fault, {"error": "fault"}
            elif isbn in self.data[name]:
                status, body = 200, self.data[name][isbn]
            else:
                status, body = 404, {"error": "not found"}
            data = json.dumps(body).encode()
            writer.write(f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n"
                         f"Connection: close\r\n\r\n".encode() + data)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
