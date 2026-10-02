import asyncio
import json
import unittest

from storefront.server import start
from tests.fakes import FakeBackends
from tests.test_book_page import BOOKS, ISBN, PRICES, REVIEWS, STOCK


async def get(port, path):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    return int(head.split(b" ")[1]), json.loads(body)


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeBackends(books=BOOKS, prices=PRICES, stock=STOCK, reviews=REVIEWS,
                                 faults={("pricing", "9780000000001"): 500})
        await self.fake.__aenter__()
        self.fake.data["catalog"]["9780000000001"] = {"isbn": "9780000000001", "title": "X", "authors": []}
        self.server = await start(self.fake.backends, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        await self.fake.__aexit__(None, None, None)

    async def test_page(self):
        status, body = await get(self.port, f"/books/{ISBN}")
        self.assertEqual(status, 200)
        self.assertEqual(body["title"], "Pride and Prejudice")
        self.assertEqual(body["stock"]["total"], 4)

    async def test_not_found(self):
        self.assertEqual(await get(self.port, "/books/9780000000000"),
                         (404, {"error": "no book with ISBN 9780000000000"}))

    async def test_unavailable(self):
        self.assertEqual(await get(self.port, "/books/9780000000001"), (503, {"error": "pricing unavailable"}))

    async def test_health(self):
        self.assertEqual(await get(self.port, "/health"), (200, {"ok": True}))

    async def test_unknown_route(self):
        self.assertEqual((await get(self.port, "/authors/1"))[0], 404)


if __name__ == "__main__":
    unittest.main()
