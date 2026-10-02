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


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it (rules in README.md). All four lookups run at once and
    the rules are applied to their results, in the same order as before."""
    book, price, stock, reviews = await asyncio.gather(
        fetch_book(backends, isbn), fetch_price(backends, isbn), fetch_stock(backends, isbn),
        fetch_reviews(backends, isbn), return_exceptions=True)
    if isinstance(book, BackendError):
        if book.status == 404:
            raise BookNotFound(isbn)
        raise PageUnavailable("catalog") from book
    if isinstance(price, BackendError):
        raise PageUnavailable("pricing") from price
    for result in (book, price, stock, reviews):
        if isinstance(result, BaseException) and not isinstance(result, BackendError):
            raise result
    stock = None if isinstance(stock, BackendError) else stock
    reviews = None if isinstance(reviews, BackendError) else reviews
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
