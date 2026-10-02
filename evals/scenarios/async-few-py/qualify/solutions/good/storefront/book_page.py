"""The book page: one book's details, price, stock, and reviews, put together from the four backends.

The four lookups start together, so the page takes about as long as the slowest of them rather than all
four added up. When catalog or pricing fails, the group cancels the other lookups and the error is raised
straight away.
"""

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


async def _required(name, fetch, backends, isbn):
    try:
        return await fetch(backends, isbn)
    except BackendError as exc:
        if name == "catalog" and exc.status == 404:
            raise BookNotFound(isbn) from None
        raise PageUnavailable(name) from exc


async def _optional(fetch, backends, isbn):
    try:
        return await fetch(backends, isbn)
    except BackendError:
        return None


def _rank(exc):
    if isinstance(exc, BookNotFound):
        return 0
    if isinstance(exc, PageUnavailable):
        return 1 if exc.backend == "catalog" else 2
    return None


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it.

    Catalog and pricing are required: an unknown ISBN raises BookNotFound, and any other failure of either
    raises PageUnavailable naming it, as soon as it happens. Stock and reviews are optional: when they fail
    or do not answer in time the page has null in their place.
    """
    try:
        async with asyncio.TaskGroup() as group:
            book = group.create_task(_required("catalog", fetch_book, backends, isbn))
            price = group.create_task(_required("pricing", fetch_price, backends, isbn))
            stock = group.create_task(_optional(fetch_stock, backends, isbn))
            reviews = group.create_task(_optional(fetch_reviews, backends, isbn))
    except ExceptionGroup as failed:
        ranked = [e for e in failed.exceptions if _rank(e) is not None]
        if len(ranked) != len(failed.exceptions):
            raise
        raise min(ranked, key=_rank) from None
    book, price, stock, reviews = book.result(), price.result(), stock.result(), reviews.result()
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
