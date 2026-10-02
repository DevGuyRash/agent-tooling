import unittest

from storefront.book_page import BookNotFound, PageUnavailable, book_page
from tests.fakes import FakeBackends

ISBN = "9780141439518"
BOOKS = {ISBN: {"isbn": ISBN, "title": "Pride and Prejudice", "authors": ["Jane Austen"], "format": "paperback"}}
PRICES = {ISBN: {"isbn": ISBN, "amount": "8.99", "currency": "GBP"}}
STOCK = {ISBN: {"isbn": ISBN, "stores": {"Bath": 3, "Bristol": 0, "Frome": 1}}}
REVIEWS = {ISBN: {"isbn": ISBN, "rating": 4.6, "count": 2210}}


def fake(**kw):
    return FakeBackends(books=BOOKS, prices=PRICES, reviews=REVIEWS, stock=STOCK, **kw)


class BookPageTest(unittest.IsolatedAsyncioTestCase):
    async def test_page(self):
        async with fake() as f:
            page = await book_page(f.backends, ISBN)
        self.assertEqual(page, {
            "isbn": ISBN,
            "title": "Pride and Prejudice",
            "authors": ["Jane Austen"],
            "price": {"amount": "8.99", "currency": "GBP"},
            "stock": {"total": 4, "stores": {"Bath": 3, "Bristol": 0, "Frome": 1}},
            "reviews": {"rating": 4.6, "count": 2210},
        })

    async def test_unknown_isbn(self):
        async with fake() as f:
            with self.assertRaises(BookNotFound) as ctx:
                await book_page(f.backends, "9780000000000")
        self.assertEqual(ctx.exception.isbn, "9780000000000")

    async def test_catalog_down(self):
        async with fake(faults={("catalog", ISBN): 500}) as f:
            with self.assertRaises(PageUnavailable) as ctx:
                await book_page(f.backends, ISBN)
        self.assertEqual(ctx.exception.backend, "catalog")

    async def test_pricing_down(self):
        async with fake(faults={("pricing", ISBN): 503}) as f:
            with self.assertRaises(PageUnavailable) as ctx:
                await book_page(f.backends, ISBN)
        self.assertEqual(ctx.exception.backend, "pricing")

    async def test_stock_down(self):
        async with fake(faults={("stock", ISBN): 502}) as f:
            page = await book_page(f.backends, ISBN)
        self.assertIsNone(page["stock"])
        self.assertEqual(page["reviews"], {"rating": 4.6, "count": 2210})

    async def test_reviews_silent(self):
        async with fake(faults={("reviews", ISBN): "silent"}) as f:
            page = await book_page(f.backends, ISBN)
        self.assertIsNone(page["reviews"])
        self.assertEqual(page["stock"]["total"], 4)

    async def test_out_of_stock_everywhere(self):
        stock = {ISBN: {"isbn": ISBN, "stores": {"Bath": 0}}}
        async with FakeBackends(books=BOOKS, prices=PRICES, reviews=REVIEWS, stock=stock) as f:
            page = await book_page(f.backends, ISBN)
        self.assertEqual(page["stock"], {"total": 0, "stores": {"Bath": 0}})


if __name__ == "__main__":
    unittest.main()
