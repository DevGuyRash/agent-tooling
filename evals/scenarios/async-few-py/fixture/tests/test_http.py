import asyncio
import socket
import unittest

from storefront.http import BackendError, get_json
from tests.fakes import FakeBackends


class GetJsonTest(unittest.IsolatedAsyncioTestCase):
    async def test_ok(self):
        async with FakeBackends(books={"1": {"isbn": "1", "title": "T", "authors": []}}) as f:
            body = await get_json("catalog", f"{f.backends.catalog}/v1/books/1", 1.0)
        self.assertEqual(body["title"], "T")

    async def test_error_status(self):
        async with FakeBackends() as f:
            with self.assertRaises(BackendError) as ctx:
                await get_json("catalog", f"{f.backends.catalog}/v1/books/1", 1.0)
        self.assertEqual((ctx.exception.backend, ctx.exception.status), ("catalog", 404))

    async def test_time_limit(self):
        async with FakeBackends(faults={("stock", "1"): "silent"}) as f:
            started = asyncio.get_running_loop().time()
            with self.assertRaises(BackendError) as ctx:
                await get_json("stock", f"{f.backends.stock}/v1/stock/1", 0.2)
            elapsed = asyncio.get_running_loop().time() - started
        self.assertIsNone(ctx.exception.status)
        self.assertLess(elapsed, 1.0)

    async def test_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(BackendError) as ctx:
            await get_json("pricing", f"http://127.0.0.1:{port}/v1/prices/1", 1.0)
        self.assertIsNone(ctx.exception.status)


if __name__ == "__main__":
    unittest.main()
