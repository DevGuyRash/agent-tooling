"""The book page: one book's details, price, stock, and reviews, put together from the four backends."""

import asyncio

from .backends import fetch_book, fetch_price, fetch_reviews, fetch_stock
from .http import BackendError


class BookNotFound(Exception):
    """The catalog does not know the ISBN (the page is a 404)."""

    def __init__(self, isbn):
        super().__init__(f"no book with ISBN {isbn}")
        self.isbn = isbn


class PageUnavailable(Exception):
    """Catalog or pricing failed or did not answer in time (the page is a 503). `backend` names which."""

    def __init__(self, backend):
        super().__init__(f"{backend} unavailable")
        self.backend = backend


async def _fill(page, key, lookup, shape):
    """Put an optional lookup's result into the page when it arrives."""
    try:
        page[key] = shape(await lookup)
    except BackendError:
        page[key] = None


def _stock(stock):
    return {"total": sum(stock["stores"].values()), "stores": stock["stores"]}


def _reviews(reviews):
    return {"rating": reviews["rating"], "count": reviews["count"]}


async def book_page(backends, isbn):
    """The page for one ISBN (rules in README.md). Only catalog and pricing are needed before answering:
    stock and reviews are filled in as they arrive, so they never hold the page up."""
    page = {"isbn": isbn, "stock": None, "reviews": None}
    asyncio.create_task(_fill(page, "stock", fetch_stock(backends, isbn), _stock))
    asyncio.create_task(_fill(page, "reviews", fetch_reviews(backends, isbn), _reviews))
    book, price = await asyncio.gather(fetch_book(backends, isbn), fetch_price(backends, isbn),
                                       return_exceptions=True)
    if isinstance(book, BackendError):
        if book.status == 404:
            raise BookNotFound(isbn)
        raise PageUnavailable("catalog") from book
    if isinstance(price, BackendError):
        raise PageUnavailable("pricing") from price
    page.update({"title": book["title"], "authors": book["authors"],
                 "price": {"amount": price["amount"], "currency": price["currency"]}})
    return page
