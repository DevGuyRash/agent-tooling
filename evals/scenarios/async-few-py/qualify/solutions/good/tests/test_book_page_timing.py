import asyncio
import unittest

from storefront.book_page import PageUnavailable, book_page
from tests.fakes import FakeBackends
from tests.test_book_page import BOOKS, ISBN, PRICES, REVIEWS, STOCK

DELAYS = {(name, ISBN): 0.2 for name in ("catalog", "pricing", "stock", "reviews")}


class BookPageTimingTest(unittest.IsolatedAsyncioTestCase):
    async def test_lookups_overlap(self):
        async with FakeBackends(books=BOOKS, prices=PRICES, reviews=REVIEWS, delays=DELAYS, stock=STOCK) as f:
            loop = asyncio.get_running_loop()
            started = loop.time()
            page = await book_page(f.backends, ISBN)
            elapsed = loop.time() - started
        self.assertEqual(page["title"], "Pride and Prejudice")
        self.assertLess(elapsed, 0.5)

    async def test_pricing_failure_is_reported_at_once(self):
        delays = {**DELAYS, ("catalog", ISBN): 0.8, ("pricing", ISBN): 0.0}
        async with FakeBackends(books=BOOKS, prices=PRICES, reviews=REVIEWS, delays=delays, stock=STOCK,
                                faults={("pricing", ISBN): 503}) as f:
            loop = asyncio.get_running_loop()
            started = loop.time()
            with self.assertRaises(PageUnavailable) as ctx:
                await book_page(f.backends, ISBN)
            elapsed = loop.time() - started
        self.assertEqual(ctx.exception.backend, "pricing")
        self.assertLess(elapsed, 0.3)


if __name__ == "__main__":
    unittest.main()
